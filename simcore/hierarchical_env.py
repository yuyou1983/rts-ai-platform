"""Hierarchical RTS environment: high-level Manager picks goals every c_step,
low-level Worker executes goal-conditioned rules by directly constructing
SimCore commands (bypassing MultiDiscrete _decode_action for precision).

Manager action space: Discrete(6)
  0=GATHER, 1=BUILD_SUPPLY, 2=BUILD_BARRACKS, 3=TRAIN_WORKER, 4=TRAIN_COMBAT, 5=ATTACK

Worker auto-executes the chosen goal for c_step ticks via _execute_option(),
which directly constructs well-formed SimCore command dicts and feeds them
to engine.step().  This guarantees correct building_type / unit_type routing.
"""
from __future__ import annotations

import enum
import math
from typing import Any

import gymnasium as gym
import numpy as np

from simcore.engine import SimCore
from simcore.gym_env import (
    ACTION_DIM_EID,
    ACTION_DIM_X,
    ACTION_DIM_Y,
    COMMAND_TYPES,
    MAP_SIZE,
    MAX_ENTITIES,
    ENTITY_FEATURES,
    RTSSimCoreEnv,
    UNIT_TYPES,
    UNIT_TYPE_MAP,
)
from simcore.reward_shaping import RewardShapingConfig, compute_dense_reward, SubgoalTracker
from simcore.reward_shaping import (
    _count_barracks,
    _count_workers,
    _count_combat_units,
    _has_barracks,
    _has_combat_units,
    _BARRACKS_TYPES,
    _COMBAT_UNIT_TYPES,
    _WORKER_TYPES,
)

# ─── Goal enum ───────────────────────────────────────────────

class Goal(enum.IntEnum):
    GATHER = 0
    BUILD_SUPPLY = 1
    BUILD_BARRACKS = 2
    TRAIN_WORKER = 3
    TRAIN_COMBAT = 4
    ATTACK = 5

N_GOALS = len(Goal)
GOAL_NAMES = [g.name for g in Goal]

# ─── Race-specific type mappings ─────────────────────────────

_RACE_SUPPLY = {"terran": "SupplyDepot", "protoss": "Pylon", "zerg": "Overlord"}
_RACE_BARRACKS = {"terran": "Barracks", "protoss": "Gateway", "zerg": "SpawningPool"}
_RACE_WORKER = {"terran": "SCV", "protoss": "Probe", "zerg": "Drone"}
_RACE_COMBAT = {"terran": "Marine", "protoss": "Zealot", "zerg": "Zergling"}


def _get_race(state, owner: int) -> str:
    """Determine race from GameState."""
    if hasattr(state, 'player_races') and state.player_races:
        r = state.player_races.get(owner, "").lower()
        if r:
            return r
    # Fallback: inspect own entities
    for eid, e in state.entities.items():
        if e.get("owner") == owner:
            r = e.get("race", "").lower()
            if r:
                return r
    return "terran"


# ─── Low-level rule executor (direct SimCore commands) ───────

def _dist(x1, y1, x2, y2):
    return abs(x1 - x2) + abs(y1 - y2)


def _execute_option(goal: Goal, engine: SimCore, owner: int = 1) -> list[dict]:
    """Directly construct SimCore command dicts for the given goal.

    Returns a list of command dicts ready for engine.step().
    This bypasses _decode_action entirely, ensuring correct building_type / unit_type.
    """
    state = engine.state
    if state is None:
        return [{"action": "noop", "issuer": owner}]

    race = _get_race(state, owner)

    # ── Categorize entities ──
    own = {eid: e for eid, e in state.entities.items()
           if e.get("owner") == owner and e.get("health", 0) > 0}
    workers = {eid: e for eid, e in own.items()
               if e.get("unit_type", "").lower() in ("scv", "worker", "probe", "drone")}
    bases = {eid: e for eid, e in own.items()
             if e.get("unit_type", "").lower() in ("commandcenter", "nexus", "hatchery")
             or e.get("building_type", "").lower() == "base"}
    supply_buildings = {eid: e for eid, e in own.items()
                         if e.get("unit_type", "").lower() in ("supplydepot", "pylon")
                         or e.get("building_type", "").lower() == "supplydepot"}
    barracks = {eid: e for eid, e in own.items()
                if e.get("unit_type", "").lower() in ("barracks", "gateway", "spawningpool")
                or e.get("building_type", "").lower() == "barracks"}
    combat_units = {eid: e for eid, e in own.items()
                    if e.get("unit_type", "").lower() in ("marine", "zealot", "zergling", "soldier", "combat")}
    enemies = {eid: e for eid, e in state.entities.items()
               if e.get("owner", 0) not in (0, owner) and e.get("health", 0) > 0}
    resources = {eid: e for eid, e in state.entities.items()
                 if e.get("entity_type") == "resource" and e.get("resource_amount", 0) > 0}

    # Find idle workers (not gathering, not constructing)
    idle_workers = {eid: e for eid, e in workers.items()
                    if not e.get("is_gathering", False) and not e.get("is_constructing", False)}

    # Get resource info
    p1_key = f"p{owner}_mineral"
    p1_gas_key = f"p{owner}_gas"
    minerals = state.resources.get(p1_key, 0) if hasattr(state, 'resources') else 0
    gas = state.resources.get(p1_gas_key, 0) if hasattr(state, 'resources') else 0
    supply_used = 0
    supply_cap = 0
    # Estimate supply from entity counts
    supply_used = sum(1 for e in own.values() if e.get("entity_type") == "unit")
    supply_cap = sum(
        e.get("max_health", 0) // 500  # rough: each supply building = 8 supply
        for e in own.values()
        if e.get("entity_type") == "building" and e.get("building_type", "").lower() in ("supplydepot", "pylon")
    ) + 10  # base supply
    if bases:
        supply_cap += len(bases) * 10

    if goal == Goal.GATHER:
        if idle_workers and resources:
            # Find base position for nearest-resource heuristic
            if bases:
                bx = next(iter(bases.values())).get("pos_x", 32)
                by = next(iter(bases.values())).get("pos_y", 32)
            else:
                bx, by = 32, 32
            # Closest resource to base
            best_rid = min(resources, key=lambda rid: _dist(bx, by, resources[rid].get("pos_x", 32), resources[rid].get("pos_y", 32)))
            rx = resources[best_rid].get("pos_x", 32)
            ry = resources[best_rid].get("pos_y", 32)
            # Closest idle worker to that resource
            best_wid = min(idle_workers, key=lambda wid: _dist(idle_workers[wid].get("pos_x", 32), idle_workers[wid].get("pos_y", 32), rx, ry))
            return [{"action": "gather", "issuer": owner, "unit_id": best_wid, "target_id": best_rid}]
        # If no idle workers but we have workers and resources, re-issue gather
        elif workers and resources:
            wid = next(iter(workers))
            rid = min(resources, key=lambda rid: _dist(workers[wid].get("pos_x", 32), workers[wid].get("pos_y", 32), resources[rid].get("pos_x", 32), resources[rid].get("pos_y", 32)))
            return [{"action": "gather", "issuer": owner, "unit_id": wid, "target_id": rid}]
        return [{"action": "noop", "issuer": owner}]

    elif goal == Goal.BUILD_SUPPLY:
        supply_type = _RACE_SUPPLY.get(race, "SupplyDepot")
        if workers and minerals >= 50:
            if bases:
                bx = next(iter(bases.values())).get("pos_x", 32)
                by = next(iter(bases.values())).get("pos_y", 32)
                w = min(workers, key=lambda wid: _dist(workers[wid].get("pos_x", 32), workers[wid].get("pos_y", 32), bx, by))
            else:
                w = next(iter(workers))
            # Place near base with offset
            tx = workers[w].get("pos_x", 32) + 5
            ty = workers[w].get("pos_y", 32) + 5
            return [{"action": "build", "issuer": owner, "unit_id": w,
                      "x": tx, "y": ty, "building_type": supply_type}]
        return [{"action": "noop", "issuer": owner}]

    elif goal == Goal.BUILD_BARRACKS:
        barracks_type = _RACE_BARRACKS.get(race, "Barracks")
        if workers and minerals >= 100:
            if bases:
                bx = next(iter(bases.values())).get("pos_x", 32)
                by = next(iter(bases.values())).get("pos_y", 32)
                w = min(workers, key=lambda wid: _dist(workers[wid].get("pos_x", 32), workers[wid].get("pos_y", 32), bx, by))
            else:
                w = next(iter(workers))
            tx = workers[w].get("pos_x", 32) - 5
            ty = workers[w].get("pos_y", 32) + 5
            return [{"action": "build", "issuer": owner, "unit_id": w,
                      "x": tx, "y": ty, "building_type": barracks_type}]
        return [{"action": "noop", "issuer": owner}]

    elif goal == Goal.TRAIN_WORKER:
        worker_type = _RACE_WORKER.get(race, "SCV")
        if bases and minerals >= 50:
            bid = next(iter(bases))
            return [{"action": "train", "issuer": owner, "building_id": bid,
                      "unit_type": worker_type}]
        return [{"action": "noop", "issuer": owner}]

    elif goal == Goal.TRAIN_COMBAT:
        combat_type = _RACE_COMBAT.get(race, "Marine")
        if barracks and minerals >= 50:
            brid = next(iter(barracks))
            return [{"action": "train", "issuer": owner, "building_id": brid,
                      "unit_type": combat_type}]
        # Fallback: if no barracks, try to build one
        if not barracks:
            return _execute_option(Goal.BUILD_BARRACKS, engine, owner)
        return [{"action": "noop", "issuer": owner}]

    elif goal == Goal.ATTACK:
        if combat_units and enemies:
            cid = next(iter(combat_units))
            cx = combat_units[cid].get("pos_x", 32)
            cy = combat_units[cid].get("pos_y", 32)
            tid = min(enemies, key=lambda eid: _dist(cx, cy, enemies[eid].get("pos_x", 32), enemies[eid].get("pos_y", 32)))
            return [{"action": "attack", "issuer": owner, "attacker_id": cid, "unit_id": cid, "target_id": tid}]
        # If no combat units, try to train some first
        if not combat_units:
            return _execute_option(Goal.TRAIN_COMBAT, engine, owner)
        return [{"action": "noop", "issuer": owner}]

    return [{"action": "noop", "issuer": owner}]


# ─── Hierarchical environment ────────────────────────────────

class HierarchicalRTSEnv(gym.Env):
    """High-level environment for training a Manager with Discrete(6) action space.

    Every c_step ticks, the Manager chooses a goal.  The low-level Worker
    auto-executes that goal for c_step ticks by directly constructing
    SimCore commands (not via MultiDiscrete _decode_action).
    The Manager receives the cumulative reward over those c_step ticks.
    """

    metadata = {"render_modes": ["ascii"]}

    def __init__(
        self,
        seed: int = 42,
        max_ticks: int = 1000,
        c_step: int = 20,
        two_player: bool = False,
        reward_shaping: str = "dense",
        reward_config: RewardShapingConfig | None = None,
    ):
        super().__init__()
        self._seed = seed
        self._max_ticks = max_ticks
        self._c_step = c_step
        self._two_player = two_player
        self._reward_config = reward_config or RewardShapingConfig()

        # Create raw SimCore engine directly (not via RTSSimCoreEnv wrapper)
        self._engine = SimCore(max_ticks=max_ticks)
        self._subgoal_tracker = SubgoalTracker()

        # Build observation space matching _state_to_obs output
        flat_dim = MAX_ENTITIES * ENTITY_FEATURES + 4 + 1  # entities + resources + tick
        self._obs_dim = flat_dim + N_GOALS + 1  # +goal_onehot + ticks_frac
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(self._obs_dim,), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(N_GOALS)

        self._current_goal = Goal.GATHER
        self._ticks_elapsed = 0
        self._last_obs = None

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._seed = seed
        self._engine = SimCore(max_ticks=self._max_ticks)
        self._engine.initialize(map_seed=self._seed)
        self._subgoal_tracker = SubgoalTracker()
        self._current_goal = Goal.GATHER
        self._ticks_elapsed = 0
        self._last_obs = self._make_flat_obs()
        info = {"goal": self._current_goal.name}
        # V11: action mask in info for SB3 MaskablePPO compatibility
        info["action_masks"] = self._compute_action_mask()
        return self._make_obs(), info

    def step(self, action: int):
        goal = Goal(action)
        self._current_goal = goal
        self._subgoal_tracker.goals_chosen.append(int(action))  # v10: track goals
        total_r = 0.0
        term = trunc = False
        last_info: dict[str, Any] = {}

        for _ in range(self._c_step):
            # Get P2 AI commands
            p2_cmds = self._get_p2_commands()

            # Get P1 commands from low-level rule executor
            p1_cmds = _execute_option(goal, self._engine, owner=1)

            # Combine and step
            all_cmds = p1_cmds + p2_cmds
            prev_state = self._engine.state
            new_state = self._engine.step(all_cmds)

            # Compute reward — v10: pass p1_cmds as agent_commands
            r = compute_dense_reward(
                prev_state, new_state, self._subgoal_tracker,
                self._reward_config, player_id=1, agent_commands=p1_cmds,
            )
            total_r += r
            self._ticks_elapsed += 1

            if new_state.is_terminal or self._ticks_elapsed >= self._max_ticks:
                term = new_state.is_terminal
                trunc = not term and self._ticks_elapsed >= self._max_ticks
                break

        # Build info
        last_info["subgoals"] = {
            "milestones": {k: v for k, v in self._subgoal_tracker.__dict__.items()},
            "goal": goal.name,
            "ticks": self._ticks_elapsed,
        }
        # V11: action mask in info for SB3 MaskablePPO compatibility
        last_info["action_masks"] = self._compute_action_mask()
        self._last_obs = self._make_flat_obs()
        return self._make_obs(), total_r, term, trunc, last_info

    # ─── V11: Action mask computation ───────────────────────────

    def _compute_action_mask(self) -> np.ndarray:
        """Compute which goals are legal given the current game state.

        Returns a boolean numpy array of shape (N_GOALS,) where True means
        the action is *available* (not masked).

        Mask rules (mask=False = disabled):
          1. ≥2 completed barracks → BUILD_BARRACKS disabled
          2. Has barracks + minerals≥50 + supply headroom → TRAIN_COMBAT must be available
          3. No workers → GATHER, BUILD_SUPPLY, BUILD_BARRACKS disabled
          4. No completed barracks → TRAIN_COMBAT disabled
          5. No combat units → ATTACK disabled
          6. Supply full (cap==used) + minerals<50 → BUILD_SUPPLY disabled
          7. No base → BUILD_SUPPLY disabled (can't build without a base placement reference)

        We also mask BUILD_BARRACKS when ≥1 completed barracks AND another
        is under construction (to prevent over-investment before production
        starts).

        TRAIN_WORKER is masked when no base exists (can't train without a base).
        """
        state = self._engine.state
        if state is None:
            # Before first reset: only GATHER is legal
            mask = np.zeros(N_GOALS, dtype=bool)
            mask[Goal.GATHER] = True
            return mask

        entities = state.entities
        owner = 1  # We are player 1

        # ── Query game state ──
        n_workers = _count_workers(entities, owner)
        n_barracks = _count_barracks(entities, owner)
        n_combat = _count_combat_units(entities, owner)
        has_barracks = n_barracks >= 1
        has_combat = n_combat >= 1

        # Count barracks under construction
        n_constructing_barracks = self._count_constructing_barracks(entities, owner)

        # Resources
        minerals = 0
        supply_used = 0
        supply_cap = 0
        if hasattr(state, 'resources'):
            minerals = state.resources.get(f"p{owner}_mineral", 0)

        # Estimate supply from entities (same logic as _execute_option)
        own = {eid: e for eid, e in entities.items()
               if e.get("owner") == owner and e.get("health", 0) > 0}
        supply_used = sum(1 for e in own.values() if e.get("entity_type") == "unit")
        supply_cap = 10  # base supply
        # Add supply from supply buildings
        supply_cap += sum(
            8 for e in own.values()
            if e.get("entity_type") == "building"
            and not e.get("is_constructing", False)
            and e.get("building_type", "").lower() in ("supplydepot", "pylon")
        )
        # Add supply from bases
        bases = {eid: e for eid, e in own.items()
                 if e.get("unit_type", "").lower() in ("commandcenter", "nexus", "hatchery")
                 or e.get("building_type", "").lower() == "base"}
        supply_cap += len(bases) * 10

        supply_full = supply_used >= supply_cap

        # Has base (needed for train worker, build placement)
        has_base = len(bases) >= 1

        # ── Apply mask rules ──
        mask = np.ones(N_GOALS, dtype=bool)  # Start with everything legal

        # Rule 3: No workers → GATHER, BUILD_SUPPLY, BUILD_BARRACKS disabled
        if n_workers == 0:
            mask[Goal.GATHER] = False
            mask[Goal.BUILD_SUPPLY] = False
            mask[Goal.BUILD_BARRACKS] = False

        # Rule 1: ≥2 completed barracks → BUILD_BARRACKS disabled
        if n_barracks >= 2:
            mask[Goal.BUILD_BARRACKS] = False

        # Also mask BUILD_BARRACKS if we have 1 completed + 1 constructing
        # (prevents the V10 pathology of building many barracks)
        if n_barracks >= 1 and n_constructing_barracks >= 1:
            mask[Goal.BUILD_BARRACKS] = False

        # Rule 4: No completed barracks → TRAIN_COMBAT disabled
        if not has_barracks:
            mask[Goal.TRAIN_COMBAT] = False

        # Rule 2: Has barracks + minerals≥50 + supply headroom → TRAIN_COMBAT available
        # (This is a "must-be-available" rule, overriding any accidental mask.
        #  We ensure it's True when conditions are met.)
        if has_barracks and minerals >= 50 and not supply_full:
            mask[Goal.TRAIN_COMBAT] = True

        # Rule 5: No combat units → ATTACK disabled
        if not has_combat:
            mask[Goal.ATTACK] = False

        # Rule 6: Supply full + can't afford supply → BUILD_SUPPLY disabled
        if supply_full and minerals < 50:
            mask[Goal.BUILD_SUPPLY] = False

        # Rule 7: No base → BUILD_SUPPLY disabled (no placement reference)
        if not has_base:
            mask[Goal.BUILD_SUPPLY] = False

        # No base → TRAIN_WORKER disabled (need base to train workers)
        if not has_base:
            mask[Goal.TRAIN_WORKER] = False

        # Safety: At least one action must always be legal.
        # If everything is masked, enable GATHER (the safest default).
        if not mask.any():
            mask[Goal.GATHER] = True

        return mask

    @staticmethod
    def _count_constructing_barracks(entities: dict, owner: int) -> int:
        """Count barracks-type buildings currently under construction for owner."""
        count = 0
        for e in entities.values():
            if e.get("owner") != owner:
                continue
            if e.get("health", 0) <= 0:
                continue
            if not e.get("is_constructing", False):
                continue
            if e.get("entity_type") != "building":
                continue
            bt = e.get("building_type", e.get("unit_type", ""))
            if bt in _BARRACKS_TYPES:
                count += 1
            else:
                bt_norm = bt.lower().replace("_", "").replace(" ", "")
                if bt_norm in ("barracks", "gateway", "spawningpool", "factory", "starport"):
                    count += 1
        return count

    def _make_flat_obs(self) -> np.ndarray:
        """Build flat obs using _state_to_obs logic from gym_env."""
        state = self._engine.state
        if state is None:
            return np.zeros(MAX_ENTITIES * ENTITY_FEATURES + 4 + 1, dtype=np.float32)

        # Entity grid
        entity_features = np.zeros((MAX_ENTITIES, ENTITY_FEATURES), dtype=np.float32)
        sorted_entities = sorted(state.entities.items(), key=lambda kv: kv[0])[:MAX_ENTITIES]
        for i, (eid, e) in enumerate(sorted_entities):
            # Position normalized
            entity_features[i, 0] = e.get("pos_x", 0) / MAP_SIZE
            entity_features[i, 1] = e.get("pos_y", 0) / MAP_SIZE
            # Health normalized
            entity_features[i, 2] = e.get("health", 0) / max(e.get("max_health", 1), 1)
            entity_features[i, 3] = e.get("max_health", 0) / 3000.0
            # Speed
            entity_features[i, 4] = e.get("speed", 0) / 10.0
            # Attack
            entity_features[i, 5] = e.get("attack", 0) / 50.0
            # Range
            entity_features[i, 6] = e.get("range", 0) / 10.0
            # Owner
            entity_features[i, 7] = e.get("owner", 0) / 2.0
            # Type idx
            ut = e.get("unit_type", "").lower()
            entity_features[i, 8] = UNIT_TYPE_MAP.get(ut, 0) / len(UNIT_TYPES)
            # Is idle
            entity_features[i, 9] = 1.0 if e.get("is_idle", False) else 0.0
            # Shields
            entity_features[i, 10] = e.get("shields", 0) / max(e.get("max_shields", 1), 1)
            entity_features[i, 11] = e.get("max_shields", 0) / 300.0
            # Armor
            entity_features[i, 12] = e.get("armor", 0) / 5.0
            # Domain (0=ground, 1=air)
            entity_features[i, 13] = 1.0 if e.get("domain", "ground") == "air" else 0.0
            # Is powered
            entity_features[i, 14] = 1.0 if e.get("is_powered", True) else 0.0
            # Energy
            entity_features[i, 15] = e.get("energy", 0) / 200.0
            # Is spellcaster
            entity_features[i, 16] = 1.0 if e.get("is_spellcaster", False) else 0.0

        flat = entity_features.flatten()

        # Resources (4 values)
        res = np.zeros(4, dtype=np.float32)
        if hasattr(state, 'resources'):
            res[0] = state.resources.get(f"p1_mineral", 0) / 10000.0
            res[1] = state.resources.get(f"p1_gas", 0) / 5000.0
            res[2] = state.resources.get(f"p2_mineral", 0) / 10000.0
            res[3] = state.resources.get(f"p2_gas", 0) / 5000.0

        # Tick
        tick = np.array([state.tick / self._max_ticks], dtype=np.float32)

        return np.concatenate([flat, res, tick])

    def _make_obs(self) -> np.ndarray:
        goal_oh = np.zeros(N_GOALS, dtype=np.float32)
        goal_oh[self._current_goal] = 1.0
        ticks_frac = np.array([self._ticks_elapsed / self._max_ticks], dtype=np.float32)
        return np.concatenate([self._last_obs, goal_oh, ticks_frac])

    def _get_p2_commands(self) -> list[dict]:
        """Generate simple AI commands for player 2."""
        if self._two_player:
            return []  # In two-player mode, P2 is controlled externally
        state = self._engine.state
        if state is None:
            return []

        own2 = {eid: e for eid, e in state.entities.items()
                if e.get("owner") == 2 and e.get("health", 0) > 0}
        workers2 = {eid: e for eid, e in own2.items()
                    if e.get("unit_type", "").lower() in ("scv", "worker", "probe", "drone")}
        resources2 = {eid: e for eid, e in state.entities.items()
                      if e.get("entity_type") == "resource" and e.get("resource_amount", 0) > 0}

        cmds = []
        if workers2 and resources2:
            # Simple: send each idle worker to nearest resource
            for wid, w in workers2.items():
                if not w.get("is_gathering", False) and not w.get("is_constructing", False):
                    if resources2:
                        rid = min(resources2, key=lambda rid: _dist(w.get("pos_x", 32), w.get("pos_y", 32), resources2[rid].get("pos_x", 32), resources2[rid].get("pos_y", 32)))
                        cmds.append({"action": "gather", "issuer": 2, "unit_id": wid, "target_id": rid})
        return cmds

    def render(self):
        # ASCII render
        state = self._engine.state
        if state is None:
            return
        grid_size = 32
        grid = [['.' for _ in range(grid_size)] for _ in range(grid_size)]
        for eid, e in state.entities.items():
            x = int(e.get("pos_x", 0) * grid_size / MAP_SIZE)
            y = int(e.get("pos_y", 0) * grid_size / MAP_SIZE)
            x = min(max(x, 0), grid_size - 1)
            y = min(max(y, 0), grid_size - 1)
            owner = e.get("owner", 0)
            et = e.get("entity_type", "")
            if et == "resource":
                ch = "◙"
            elif et == "building":
                ch = "█" if owner == 1 else "▓"
            elif et == "unit":
                if e.get("unit_type", "").lower() in ("scv", "worker", "probe", "drone"):
                    ch = "♂" if owner == 1 else "♠"
                else:
                    ch = "♦" if owner == 1 else "♣"
            else:
                ch = "?"
            grid[y][x] = ch
        for row in grid:
            print("".join(row))

    def close(self):
        pass


# ─── Helper: map AI command to Goal ──────────────────────────

def command_to_goal(cmd: dict) -> Goal:
    """Map an AI agent command to a high-level goal."""
    action = cmd.get("action", "noop")
    building = cmd.get("building_type", "").lower()
    unit = cmd.get("unit_type", "").lower()

    if action == "gather" or action == "move":
        return Goal.GATHER
    elif action == "build":
        if building in ("supplydepot", "pylon", "overlord"):
            return Goal.BUILD_SUPPLY
        return Goal.BUILD_BARRACKS  # default build → barracks
    elif action == "train":
        if unit in ("scv", "probe", "drone", "worker"):
            return Goal.TRAIN_WORKER
        return Goal.TRAIN_COMBAT
    elif action == "attack":
        return Goal.ATTACK
    return Goal.GATHER


# ─── SB3-compatible ActionMasker wrapper ────────────────────

class ActionMasker(gym.Wrapper):
    """Wrapper that extracts action_masks from info dict and makes them
    available via env.action_masks() — the interface expected by
    sb3_contrib MaskablePPO.

    Usage:
        env = HierarchicalRTSEnv(...)
        env = ActionMasker(env)
        model = MaskablePPO("MlpPolicy", env, ...)

    The inner HierarchicalRTSEnv computes masks in step() / reset()
    and puts them in info["action_masks"].  This wrapper exposes
    env.action_masks() which reads from the most recent info.
    """

    def __init__(self, env: gym.Env):
        super().__init__(env)
        self._last_action_masks: np.ndarray = np.ones(N_GOALS, dtype=bool)

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        self._last_action_masks = np.asarray(
            info.get("action_masks", np.ones(N_GOALS, dtype=bool)), dtype=bool
        )
        return obs, info

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        self._last_action_masks = np.asarray(
            info.get("action_masks", np.ones(N_GOALS, dtype=bool)), dtype=bool
        )
        return obs, reward, terminated, truncated, info

    def action_masks(self) -> np.ndarray:
        """Return the action mask from the most recent step/reset.

        Returns a boolean array of shape (N_GOALS,) where True = legal.
        """
        return self._last_action_masks
