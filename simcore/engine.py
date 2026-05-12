"""RTS SimCore — Headless deterministic game engine.

Produces immutable state snapshots per tick. No rendering, no I/O delays.
Designed for: parallel batch simulation, deterministic replay, RL training.

Pipeline per tick:
  step(commands) → validate → move → collision_separate → process_attacks
                 → gather → build → train → fog → check_terminal
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from simcore.map import TileMap, generate_tile_map, PLAIN, WATER, MOUNTAIN
from simcore.commands import (
    validate_command, apply_command,
    MOVE, STOP, ATTACK, GATHER, BUILD, TRAIN, HOLD, PATROL,
)
from simcore.movement import move_entities, collision_separate, is_at_target
from simcore.pathfinder import find_path as astar_find_path
from simcore.rules import (
    RuleEngine, validate_commands, apply_movement, resolve_combat,
    process_gathering as rules_process_gathering,
    process_construction as rules_process_construction,
    update_fog_of_war,
    check_terminal, KillFeed, _find_nearest_base, _unit_stats,
    GATHER_RATE, BUILD_PROGRESS_PER_TICK, PRODUCTION_TICKS,
    WORKER_RETURN_SPEED,
    calculate_damage, get_armor_type,
)
from simcore.economy import (
    process_gathering as economy_process_gathering,
    process_resources,
    process_larva_spawn,
    process_shield_regen,
)
from simcore.construction import (
    process_construction as new_process_construction,
)
from simcore.projectile import process_projectiles
from simcore.spells import process_spells, regen_energy
from simcore.upgrades import apply_upgrade_effects
from simcore.state import GameState


class AgentInterface(Protocol):
    """Protocol for agent integration — AgentScope ReActAgent implements this."""

    def decide(self, obs: dict) -> dict: ...


@dataclass
class SimCore:
    """Main game engine loop. Tick-based, deterministic, headless.

    Usage:
        engine = SimCore()
        engine.initialize(map_seed=42)
        state = engine.step(commands=[{"unit": "worker_1", "action": "gather"}])
    """

    tick_rate: float = 20.0  # ticks per second
    max_ticks: int = 10_000
    rule_engine: RuleEngine = field(default_factory=RuleEngine)

    _tick: int = field(default=0, init=False)
    _state: GameState | None = field(default=None, init=False)
    _replay: list[dict] = field(default_factory=list, init=False)
    _tile_map: TileMap | None = field(default=None, init=False)

    def initialize(self, map_seed: int = 42, config: dict | None = None) -> None:
        """Initialize game state from seed + config (deterministic).

        Args:
            map_seed: Seed for procedural map generation.
            config: Optional game configuration (unit stats, resources, etc.).
        """
        from simcore.mapgen import generate_map

        self._state = generate_map(seed=map_seed, config=config or {})
        self._tick = 0
        self._replay = [self._state.to_snapshot()]

        # Generate tile map for pathfinding
        self._tile_map = generate_tile_map(seed=map_seed, config=config or {})

        # Sync building positions to tile map occupied set
        if self._tile_map and self._state:
            for eid, e in self._state.entities.items():
                if e.get("entity_type") == "building":
                    tx, ty = self._tile_map.world_to_tile(
                        e.get("pos_x", 0), e.get("pos_y", 0)
                    )
                    self._tile_map.occupy([(tx, ty)])

    def step(self, commands: list[dict]) -> GameState:
        """Advance one tick: apply commands → resolve rules → snapshot state.

        Pipeline:
          1. Validate commands (both old and new systems)
          2. Apply MOVE/STOP commands via new command system (sets A* paths)
          3. Apply ATTACK/GATHER/BUILD/TRAIN via old rule engine
          4. Move entities: old system for chase/return + new system for A* paths
          5. Collision separation
          6. Process attacks (combat with damage matrix)
          7. Process projectiles
          8. Process spells
          9. Process gathering (economy system)
         10. Process construction (new construction system with tech tree)
         11. Apply upgrade effects
         12. Zerg larva spawning
         13. Protoss shield regeneration
         14. Energy regeneration
         15. Update resource counters (supply used/cap)
         16. Update fog-of-war
         17. Check terminal state

        Args:
            commands: List of command dicts matching cmd.proto schema.

        Returns:
            New immutable GameState after tick resolution.
        """
        if self._state is None:
            raise RuntimeError("SimCore not initialized. Call initialize() first.")

        self._tick += 1

        # 1. Validate commands using old system
        valid = validate_commands(self._state, commands)

        # Separate commands by type for dual-system processing
        move_cmds = [c for c in valid if c.get("action") == MOVE]
        other_cmds = [c for c in valid if c.get("action") != MOVE]

        entities = dict(self._state.entities)

        # 2. Apply MOVE commands via new command system (sets path + target)
        for cmd in move_cmds:
            entity_id = cmd.get("unit_id", "")
            if not entity_id or entity_id not in entities:
                continue
            entity = entities[entity_id]
            if validate_command(cmd, entity, self._state):
                if self._tile_map is not None:
                    entities[entity_id] = apply_command(
                        cmd, entity, self._tile_map
                    )
                else:
                    # Fallback: just set target without path
                    entities[entity_id] = {
                        **entity,
                        "target_x": cmd.get("target_x", entity["pos_x"]),
                        "target_y": cmd.get("target_y", entity["pos_y"]),
                        "is_idle": False,
                        "returning_to_base": False,
                        "attack_target_id": "",
                    }

        # 2b. Apply STOP commands via new command system
        for cmd in valid:
            if cmd.get("action") == STOP:
                entity_id = cmd.get("unit_id", "")
                if entity_id and entity_id in entities:
                    entity = entities[entity_id]
                    if validate_command(cmd, entity, self._state):
                        entities[entity_id] = apply_command(cmd, entity)

        # 3. Apply ATTACK commands — set attack_target_id on entities
        for cmd in other_cmds:
            if cmd.get("action") == ATTACK:
                attacker_id = cmd.get("attacker_id", "")
                if attacker_id and attacker_id in entities:
                    entity = entities[attacker_id]
                    if validate_command(cmd, entity, self._state):
                        entities[attacker_id] = {
                            **entity,
                            "attack_target_id": cmd.get("target_id", ""),
                            "is_idle": False,
                            "returning_to_base": False,
                            "deposit_pending": False,
                        }

        # Build temp state for old rule engine movement
        temp_state = GameState(
            tick=self._state.tick,
            entities=entities,
            fog_of_war=self._state.fog_of_war,
            resources=self._state.resources,
            is_terminal=self._state.is_terminal,
            winner=self._state.winner,
        )

        # 4. Movement
        # Old system handles: worker return-to-base, attack chase
        # It also handles any remaining move commands in other_cmds,
        # but we already processed move_cmds above.
        # Pass only non-move commands to old system's apply_movement
        entities = apply_movement(temp_state.entities, other_cmds, self._tick)

        # New system: advance entities along A* paths
        entities = move_entities(entities, dt=1.0, tile_map=self._tile_map)

        # 5. Collision separation
        entities = collision_separate(entities)

        # 6. Combat
        entities, resources = resolve_combat(
            entities, temp_state.resources, other_cmds, self._tick,
            kill_feed=self.rule_engine.kill_feed,
        )

# 7. Gathering (use new economy system)
        entities, resources = economy_process_gathering(entities, temp_state.resources, other_cmds, self._tick)

        # 8. Construction (use new construction system with tech tree validation)
        entities, resources = new_process_construction(entities, resources, other_cmds, self._tick)

        # 9. Process projectiles
        entities = process_projectiles(entities, self._tick)

        # 10. Process spells
        spell_cmds = [c for c in other_cmds if c.get("action") == "spell"]
        entities, resources = process_spells(entities, resources, spell_cmds, self._tick)

        # 11. Apply upgrade effects (from completed upgrades)
        completed_upgrades = self._state.entities.get("__completed_upgrades__", {})
        upgrade_list = []
        if isinstance(completed_upgrades, dict):
            for owner, upg_list in completed_upgrades.items():
                if isinstance(upg_list, list):
                    upgrade_list.extend(upg_list)
        elif isinstance(completed_upgrades, list):
            upgrade_list = completed_upgrades
        entities = apply_upgrade_effects(entities, upgrade_list)

        # 12. Zerg larva spawning
        entities = process_larva_spawn(entities, self._tick)

        # 13. Protoss shield regeneration
        entities = process_shield_regen(entities, self._tick)

        # 14. Energy regeneration (for casters)
        entities = regen_energy(entities, self._tick)

        # 15. Update resource counters (supply used/cap)
        temp_state2 = GameState(
            tick=self._tick,
            entities=entities,
            fog_of_war=temp_state.fog_of_war,
            resources=resources,
            is_terminal=temp_state.is_terminal,
            winner=temp_state.winner,
        )
        resources = process_resources(temp_state2)

        # Update tile map occupied set from current buildings
        if self._tile_map is not None:
            self._tile_map.occupied.clear()
            for eid, e in entities.items():
                if e.get("entity_type") == "building" and e.get("health", 0) > 0:
                    tx, ty = self._tile_map.world_to_tile(
                        e.get("pos_x", 0), e.get("pos_y", 0)
                    )
                    self._tile_map.occupy([(tx, ty)])

        # 16. Fog-of-war
        fog = update_fog_of_war(entities, temp_state.fog_of_war, self._tick)

        # 17. Terminal check
        is_terminal, winner, reason = check_terminal(entities, self._tick, self.max_ticks)

        self._state = GameState(
            tick=self._tick,
            entities=entities,
            fog_of_war=fog,
            resources=resources,
            is_terminal=is_terminal,
            winner=winner,
        )
        self._replay.append(self._state.to_snapshot())
        return self._state

    def run(self, agents: list[AgentInterface]) -> GameState:
        """Run full game loop with agent decisions each tick.

        Args:
            agents: List of agents implementing AgentInterface.

        Returns:
            Final GameState when game terminates.
        """
        self.initialize()
        while self._tick < self.max_ticks and not self._state.is_terminal:
            obs = self._state.get_observations()
            commands = [a.decide(o) for a, o in zip(agents, obs, strict=True)]
            self.step(commands)
        return self._state

    def get_observations(self, player_id: int) -> dict:
        """Get fog-filtered view for a specific player.

        Args:
            player_id: Player ID (1 or 2).

        Returns:
            Observation dict filtered by fog-of-war.
        """
        if self._state is None:
            return {}
        obs_list = self._state.get_observations()
        idx = player_id - 1
        if 0 <= idx < len(obs_list):
            return obs_list[idx]
        return {}

    @property
    def tile_map(self) -> TileMap | None:
        """Current tile map."""
        return self._tile_map

    @property
    def tick(self) -> int:
        """Current tick number."""
        return self._tick

    @property
    def state(self) -> GameState | None:
        """Current game state (or None if not initialized)."""
        return self._state

    @property
    def replay(self) -> list[dict]:
        """Full replay trace — can be replayed deterministically."""
        return list(self._replay)