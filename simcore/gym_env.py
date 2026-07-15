"""Gymnasium-compatible environment wrapper for RTS SimCore.

Provides a standard Gym interface (reset/step) over SimCore, enabling:
  - RL training with stable-baselines3, TRL, etc.
  - Multi-agent self-play
  - Reward shaping for GRPO

Observation space: flat dict with entities, resources, tick.
Action space: discrete command index (maps to structured command dicts).

Usage:
    import gymnasium as gym
    env = gym.make("rts-ai-v0", seed=42)
    obs, info = env.reset()
    for _ in range(1000):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
"""
from __future__ import annotations

import math
from typing import Any, Callable

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from simcore.engine import SimCore
from simcore.state import GameState
from simcore.reward_shaping import (
    RewardShapingConfig,
    SubgoalTracker,
    compute_dense_reward,
    get_subgoal_info,
)

# ─── Constants ─────────────────────────────────────────────

MAP_SIZE = 64
MAX_ENTITIES = 64
ACTION_DIM_X = 4   # X position quantisation buckets (simplified: 8→4)
ACTION_DIM_Y = 2   # Y position quantisation buckets (simplified: 4→2)
ACTION_DIM_EID = 2 # entity selection buckets (simplified: 4→2)
ENTITY_FEATURES = 17  # x, y, health, max_health, speed, attack, range, owner, type_idx, is_idle,
                      # shields, max_shields, armor, domain, is_powered, energy, is_spellcaster

UNIT_TYPES = ["worker", "soldier", "scout", "base", "barracks", "resource"]
UNIT_TYPE_MAP = {t: i for i, t in enumerate(UNIT_TYPES)}

COMMAND_TYPES = ["gather", "attack", "build", "train", "noop"]
COMMAND_TYPE_MAP = {t: i for i, t in enumerate(COMMAND_TYPES)}

# Race-specific building and unit type lists for decode mapping
PROTOSS_BUILDINGS = ["Nexus", "Pylon", "Assimilator", "Gateway", "Forge",
                     "PhotonCannon", "CyberneticsCore", "ShieldBattery",
                     "RoboticsFacility", "Stargate", "CitadelOfAdun",
                     "RoboticsSupportBay", "FleetBeacon", "TemplarArchives",
                     "Observatory", "ArbiterTribunal"]
TERRAN_BUILDINGS = ["CommandCenter", "SupplyDepot", "Refinery", "Barracks",
                    "EngineeringBay", "MissileTurret", "Academy", "Bunker",
                    "Factory", "Starport", "ScienceFacility", "Armory"]
ZERG_BUILDINGS = ["Hatchery", "Lair", "Hive", "Extractor", "SpawningPool",
                  "EvolutionChamber", "HydraliskDen", "Spire", "GreaterSpire",
                  "QueenNest", "NydusCanal", "UltraliskCavern", "DefilerMound",
                  "CreepColony", "SunkenColony", "SporeColony"]
# Simplified building types for backward compatibility
SIMPLIFIED_BUILDINGS = ["base", "barracks", "factory", "starport", "supply_depot", "refinery"]
ALL_BUILDINGS = SIMPLIFIED_BUILDINGS + TERRAN_BUILDINGS + ZERG_BUILDINGS + PROTOSS_BUILDINGS

PROTOSS_UNITS = ["Probe", "Zealot", "Dragoon", "Templar", "DarkTemplar",
                 "Archon", "DarkArchon", "Reaver", "Shuttle", "Observer",
                 "Arbiter", "Scout", "Carrier", "Corsair"]
TERRAN_UNITS = ["SCV", "Marine", "Firebat", "Ghost", "Medic",
                "Vulture", "Tank", "Goliath", "Wraith", "Dropship",
                "Vessel", "BattleCruiser", "Valkyrie"]
ZERG_UNITS = ["Drone", "Zergling", "Hydralisk", "Lurker", "Ultralisk",
              "Overlord", "Queen", "Defiler", "Mutalisk", "Guardian",
              "Devourer", "Scourge", "Larva", "Broodling", "InfestedTerran"]
SIMPLIFIED_UNITS = ["worker", "soldier", "scout"]
ALL_UNITS = SIMPLIFIED_UNITS + TERRAN_UNITS + ZERG_UNITS + PROTOSS_UNITS

# Mapping from simplified type → race-aware default
_DEFAULT_BUILDING_MAP = {
    "terran": {"base": "CommandCenter", "barracks": "Barracks"},
    "protoss": {"base": "Nexus", "barracks": "Gateway"},
    "zerg": {"base": "Hatchery", "barracks": "SpawningPool"},
}
_DEFAULT_UNIT_MAP = {
    "terran": {"worker": "SCV", "soldier": "Marine", "scout": "Wraith"},
    "protoss": {"worker": "Probe", "soldier": "Zealot", "scout": "Scout"},
    "zerg": {"worker": "Drone", "soldier": "Zergling", "scout": "Mutalisk"},
}

# Type alias: agent_factory(player_id) -> agent with .decide(obs)
AgentFactory = Callable[[int], Any]


def _infer_is_powered(entity: dict) -> bool:
    """Infer is_powered for Protoss buildings that lack the explicit field.

    A building is considered powered if:
      - It is a Pylon or Nexus (always powered / provides power)
      - It is owned by a non-Protoss race (Terran/Zerg buildings don't need pylon power)
      - It has the explicit 'is_powered' field already set
    Otherwise defaults to False (needs pylon check at engine level).
    """
    if "is_powered" in entity:
        return bool(entity["is_powered"])
    btype = entity.get("building_type", entity.get("unit_type", ""))
    if btype in ("Pylon", "Nexus"):
        return True
    # Non-Protoss buildings never need pylon power
    owner = entity.get("owner", 0)
    # Heuristic: if entity_type is building and no shields, likely Terran/Zerg
    if entity.get("entity_type") == "building" and entity.get("shields", 0) == 0:
        return True
    return False


def _get_player_race(state: GameState | None, owner: int) -> str:
    """Resolve a player's race from game state."""
    if state is None:
        return "terran"
    races = getattr(state, "player_races", None)
    if races and str(owner) in races:
        return races[str(owner)]
    if races and owner in races:
        return races[owner]
    # Heuristic: if player owns any Protoss units, assume Protoss
    for e in state.entities.values():
        if e.get("owner") == owner:
            utype = e.get("unit_type", e.get("building_type", ""))
            if utype in PROTOSS_UNITS + PROTOSS_BUILDINGS:
                return "protoss"
            if utype in ZERG_UNITS + ZERG_BUILDINGS:
                return "zerg"
    return "terran"


class RTSSimCoreEnv(gym.Env):
    """Gymnasium environment wrapping SimCore for RL training.

    Two modes:
      - single_player: control P1, P2 is ScriptAI
      - two_player: control both sides (for self-play)

    The action is a dict with:
      - command_type: int (index into COMMAND_TYPES)
      - unit_id: int (index into entity list)
      - target_x, target_y: float (world coordinates)

    For discrete action space, we encode as a single integer:
      action = command_type * (MAX_ENTITIES * MAP_SIZE * MAP_SIZE)
             + unit_idx * (MAP_SIZE * MAP_SIZE)
             + tx * MAP_SIZE + ty
    """

    metadata = {"render_modes": ["human", "ascii"], "name": "rts-ai-v0"}

    def __init__(
        self,
        seed: int = 42,
        max_ticks: int = 10000,
        two_player: bool = False,
        reward_shaping: str = "sparse",
        reward_config: RewardShapingConfig | None = None,
        render_mode: str | None = None,
        agent_factory: AgentFactory | None = None,
        enable_state_hash: bool = False,
        enable_order_queue: bool = False,
        enable_event_log: bool = False,
        enable_replay_v2: bool = False,
        action_mode: str = "discrete",
        opponent_difficulty: str = "medium",
    ) -> None:
        super().__init__()

        self._seed = seed
        self._max_ticks = max_ticks
        self._two_player = two_player
        self._reward_shaping = reward_shaping
        self._reward_config = reward_config or RewardShapingConfig()
        self.render_mode = render_mode
        self._action_mode = action_mode

        # Opponent difficulty — controls ScriptAI / CoordinatorAgent difficulty
        self._opponent_difficulty = opponent_difficulty

        # Subgoal tracker — per-episode mutable state for dense milestones
        self._subgoal_tracker = SubgoalTracker()

        # Agent factory — injected by the runtime layer.
        # If not provided, we lazily import from runtime when needed.
        self._agent_factory = agent_factory

        # SimCore feature flags
        self._enable_state_hash = enable_state_hash
        self._enable_order_queue = enable_order_queue
        self._enable_event_log = enable_event_log
        self._enable_replay_v2 = enable_replay_v2

        self._engine = SimCore(
            max_ticks=max_ticks,
            enable_state_hash=enable_state_hash,
            enable_order_queue=enable_order_queue,
            enable_event_log=enable_event_log,
            enable_replay_v2=enable_replay_v2,
        )
        self._prev_resources: dict[str, int] = {}

        # Observation: (MAX_ENTITIES, ENTITY_FEATURES) + resource vector
        self.observation_space = spaces.Dict({
            "entities": spaces.Box(
                low=0, high=1.0,
                shape=(MAX_ENTITIES, ENTITY_FEATURES),
                dtype=np.float32,
            ),
            "resources": spaces.Box(
                low=0, high=100000,
                shape=(4,),  # p1_mineral, p1_gas, p2_mineral, p2_gas
                dtype=np.float32,
            ),
            "tick": spaces.Box(low=0, high=max_ticks, shape=(1,), dtype=np.float32),
        })

        # Action: discrete over command_type × entity_bucket × target_cell
        # Simplified: 6 command types × 8 X buckets × 4 Y buckets × 4 entity buckets = 768
        n_cmd = len(COMMAND_TYPES)
        n_x = ACTION_DIM_X
        n_y = ACTION_DIM_Y
        n_eid = ACTION_DIM_EID
        n_targets = n_x * n_y  # 32
        self._n_actions = n_cmd * n_eid * n_targets  # 6*4*32 = 768

        if self._action_mode == "multidiscrete":
            self.action_space = spaces.MultiDiscrete([n_cmd, n_eid, n_x, n_y])
        else:
            self.action_space = spaces.Discrete(self._n_actions)

    def _get_agent_factory(self) -> AgentFactory:
        """Return the agent factory, dynamically loading from runtime if needed.

        When no external factory was injected, we import
        :func:`runtime.agent_factory.create_ai_agent` and wrap it to
        pass the configured ``opponent_difficulty``.
        """
        if self._agent_factory is None:
            import importlib
            import functools
            _mod = importlib.import_module("runtime.agent_factory")
            _create = _mod.create_ai_agent
            # Bind the difficulty so agent_factory(player_id=2) uses it
            self._agent_factory = functools.partial(
                _create, difficulty=self._opponent_difficulty
            )
        return self._agent_factory

    def reset(
        self, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        super().reset(seed=seed)
        actual_seed = seed if seed is not None else self._seed
        self._engine.initialize(map_seed=actual_seed)
        self._prev_resources = dict(self._engine.state.resources) if self._engine.state else {}
        # Reset subgoal tracker for new episode
        self._subgoal_tracker.reset()

        obs = self._state_to_obs(self._engine.state)
        info = self._build_info()
        return obs, info

    def step(
        self, action: int
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        # Decode action
        commands = self._decode_action(action)

        # Inject AI commands for P2 in single-player mode via runtime
        all_commands = list(commands)
        if not self._two_player and self._engine.state is not None:
            factory = self._get_agent_factory()
            import importlib
            _gym_ai = importlib.import_module("runtime.gym_ai")
            all_commands = _gym_ai.inject_ai_commands(
                self._engine, commands, self._two_player, factory,
            )

        # Step engine
        prev_state = self._engine.state
        new_state = self._engine.step(all_commands)

        obs = self._state_to_obs(new_state)
        reward = self._compute_reward(prev_state, new_state, commands)
        terminated = new_state.is_terminal
        truncated = new_state.tick >= self._max_ticks
        info = self._build_info()

        return obs, reward, terminated, truncated, info

    def render(self) -> None:
        if self.render_mode == "ascii":
            self._render_ascii()

    def close(self) -> None:
        pass

    # ─── Internal ──────────────────────────────────────────

    def _state_to_obs(self, state: GameState | None) -> dict[str, np.ndarray]:
        if state is None:
            return {
                "entities": np.zeros((MAX_ENTITIES, ENTITY_FEATURES), dtype=np.float32),
                "resources": np.zeros(4, dtype=np.float32),
                "tick": np.zeros(1, dtype=np.float32),
            }

        entities_arr = np.zeros((MAX_ENTITIES, ENTITY_FEATURES), dtype=np.float32)
        for i, (_eid, e) in enumerate(state.entities.items()):
            if i >= MAX_ENTITIES:
                break
            etype = e.get("entity_type", e.get("building_type", e.get("unit_type", "resource")))
            # Domain mapping: 0=ground, 1=air, 2=both
            _domain_map = {"ground": 0, "air": 1, "both": 2}
            domain_raw = e.get("domain", "ground")
            domain_val = _domain_map.get(domain_raw, 0) / 2.0  # normalize to [0, 1]

            entities_arr[i] = [
                e.get("pos_x", 0.0) / MAP_SIZE,                       # 0: x
                e.get("pos_y", 0.0) / MAP_SIZE,                       # 1: y
                e.get("health", 0.0) / max(e.get("max_health", 1.0), 1.0),  # 2: health_ratio
                e.get("max_health", 0.0) / 2000.0,                   # 3: max_health (norm)
                e.get("speed", 0.0) / 5.0,                           # 4: speed (norm)
                e.get("attack", 0.0) / 50.0,                         # 5: attack (norm)
                e.get("attack_range", 0.0) / 10.0,                  # 6: range (norm)
                e.get("owner", 0) / 2.0,                             # 7: owner (norm)
                UNIT_TYPE_MAP.get(etype, 0) / max(len(UNIT_TYPES), 1),  # 8: type_idx (norm)
                float(e.get("is_idle", False)),                      # 9: is_idle
                e.get("shields", 0.0) / max(e.get("max_shields", 1.0), 1.0),  # 10: shields_ratio
                e.get("max_shields", 0.0) / 500.0,                   # 11: max_shields (norm)
                e.get("armor", 0.0) / 10.0,                         # 12: armor (norm)
                domain_val,                                          # 13: domain (norm 0-1)
                float(e.get("is_powered", _infer_is_powered(e))),    # 14: is_powered
                e.get("energy", 0.0) / 250.0,                       # 15: energy (norm)
                float(e.get("is_spellcaster", False)),               # 16: is_spellcaster
            ]

        res = state.resources
        resources_arr = np.array([
            res.get("p1_mineral", 0),
            res.get("p1_gas", 0),
            res.get("p2_mineral", 0),
            res.get("p2_gas", 0),
        ], dtype=np.float32)

        tick_arr = np.array([state.tick], dtype=np.float32)

        return {"entities": entities_arr, "resources": resources_arr, "tick": tick_arr}

    def _decode_action(self, action: int | np.ndarray) -> list[dict]:
        n_x = ACTION_DIM_X
        n_y = ACTION_DIM_Y
        n_eid = ACTION_DIM_EID
        n_targets = n_x * n_y  # 32
        n_cmd = len(COMMAND_TYPES)

        if isinstance(action, np.ndarray) and action.shape == (4,):
            # MultiDiscrete mode: action = [ct_idx, eid_bucket, x_bucket, y_bucket]
            ct_idx = int(action[0])
            eid_bucket = int(action[1])
            x_bucket = int(action[2])
            y_bucket = int(action[3])
        else:
            # Discrete mode: action = ct_idx * (n_eid * n_targets) + eid_bucket * n_targets + target_idx
            ct_idx = int(action) // (n_eid * n_targets)
            remainder = int(action) % (n_eid * n_targets)
            eid_bucket = remainder // n_targets
            target_idx = remainder % n_targets
            x_bucket = target_idx % n_x
            y_bucket = target_idx // n_x

        ct_idx = min(ct_idx, n_cmd - 1)
        cmd_type = COMMAND_TYPES[ct_idx]

        # Map quantised buckets back to world coordinates
        tx = x_bucket * (MAP_SIZE / n_x)   # e.g. 0..7 → 0,8,16,24,32,40,48,56
        ty = y_bucket * (MAP_SIZE / n_y)   # e.g. 0..3 → 0,16,32,48

        # Find actual entity id — select from first N own entities
        if self._engine.state is None:
            return []

        # Collect owned entities (P1 in single-player, both in two-player)
        controlled_owners = {1, 2} if self._two_player else {1}
        own_entities = [
            (eid, e)
            for eid, e in self._engine.state.entities.items()
            if e.get("owner", 0) in controlled_owners and e.get("health", 0) > 0
        ]
        # Sort by entity id for deterministic ordering
        own_entities.sort(key=lambda pair: pair[0])

        if eid_bucket >= len(own_entities):
            return [{"action": "noop", "issuer": 1}]

        eid, entity = own_entities[eid_bucket]
        owner = entity.get("owner", 0)

        # Only control P1 in single-player, both in two-player
        if not self._two_player and owner != 1:
            return [{"action": "noop", "issuer": 1}]

        cmd: dict[str, Any] = {"action": cmd_type, "issuer": owner}

        if cmd_type == "gather":
            cmd["worker_id"] = eid
            # Find nearest resource
            best_rid = ""
            best_dist = float("inf")
            for rid, r in self._engine.state.entities.items():
                if r.get("entity_type") == "resource" and r.get("resource_amount", 0) > 0:
                    d = math.hypot(entity["pos_x"] - r["pos_x"], entity["pos_y"] - r["pos_y"])
                    if d < best_dist:
                        best_dist = d
                        best_rid = rid
            cmd["resource_id"] = best_rid
        elif cmd_type == "attack":
            cmd["attacker_id"] = eid
            # Find nearest enemy
            best_tid = ""
            best_dist = float("inf")
            for tid, t in self._engine.state.entities.items():
                if t.get("owner") not in (0, owner) and t.get("health", 0) > 0:
                    d = math.hypot(entity["pos_x"] - t["pos_x"], entity["pos_y"] - t["pos_y"])
                    if d < best_dist:
                        best_dist = d
                        best_tid = tid
            cmd["target_id"] = best_tid
        elif cmd_type == "build":
            cmd["builder_id"] = eid
            # Resolve building_type based on target position / context
            # Use x_bucket,y_bucket to index into available buildings list for the player's race
            race = _get_player_race(self._engine.state, owner)
            race_buildings = _DEFAULT_BUILDING_MAP.get(race, _DEFAULT_BUILDING_MAP["terran"])
            # Map simplified types to race-specific building names
            # Use a simple index: (x_bucket + y_bucket) % len(race_buildings)
            # This gives variety of buildings based on target cell position
            all_race_btypes = list(race_buildings.values()) + PROTOSS_BUILDINGS + TERRAN_BUILDINGS + ZERG_BUILDINGS + SIMPLIFIED_BUILDINGS
            # Deduplicate while preserving order
            seen = set()
            unique_btypes = []
            for bt in all_race_btypes:
                if bt not in seen:
                    seen.add(bt)
                    unique_btypes.append(bt)
            # Index from target grid coords
            bidx = (x_bucket + y_bucket * n_x) % len(unique_btypes)
            cmd["building_type"] = unique_btypes[bidx]
            cmd["pos_x"] = tx
            cmd["pos_y"] = ty
        elif cmd_type == "train":
            cmd["building_id"] = eid
            # Resolve unit_type based on target position / building context
            race = _get_player_race(self._engine.state, owner)
            race_units = _DEFAULT_UNIT_MAP.get(race, _DEFAULT_UNIT_MAP["terran"])
            # Build full list of trainable units for this race
            all_race_utypes = list(race_units.values()) + PROTOSS_UNITS + TERRAN_UNITS + ZERG_UNITS + SIMPLIFIED_UNITS
            seen = set()
            unique_utypes = []
            for ut in all_race_utypes:
                if ut not in seen:
                    seen.add(ut)
                    unique_utypes.append(ut)
            # Index from target grid coords
            uidx = (x_bucket + y_bucket * n_x) % len(unique_utypes)
            cmd["unit_type"] = unique_utypes[uidx]
        elif cmd_type == "noop":
            pass

        return [cmd]

    def _compute_reward(self, prev: GameState | None, curr: GameState, agent_commands: list[dict] | None = None) -> float:
        if prev is None:
            return 0.0

        if self._reward_shaping == "sparse":
            if curr.is_terminal:
                return 1.0 if curr.winner == 1 else (-1.0 if curr.winner == 2 else 0.0)
            return 0.0

        if self._reward_shaping == "shaped":
            reward = 0.0
            # Resource gain reward
            res = curr.resources
            prev_res = prev.resources if prev else {}
            reward += (res.get("p1_mineral", 0) - prev_res.get("p1_mineral", 0)) * 0.001
            reward += (res.get("p1_gas", 0) - prev_res.get("p1_gas", 0)) * 0.001

            # Military advantage
            combat_types = ("worker", "soldier", "scout")
            p1_units = sum(
                1 for e in curr.entities.values()
                if e.get("owner") == 1 and e.get("entity_type") in combat_types
            )
            p2_units = sum(
                1 for e in curr.entities.values()
                if e.get("owner") == 2 and e.get("entity_type") in combat_types
            )
            reward += (p1_units - p2_units) * 0.01

            # Damage dealt
            p2_health_lost = 0.0
            for eid, e in prev.entities.items():
                if e.get("owner") == 2 and eid in curr.entities:
                    lost = e.get("health", 0) - curr.entities[eid].get("health", 0)
                    p2_health_lost += max(0, lost)
            reward += p2_health_lost * 0.005

            # Terminal bonus
            if curr.is_terminal:
                reward += 1.0 if curr.winner == 1 else (-1.0 if curr.winner == 2 else 0.0)

            return reward

        if self._reward_shaping == "dense":
            return compute_dense_reward(
                prev, curr,
                tracker=self._subgoal_tracker,
                config=self._reward_config,
                player_id=1,
                agent_commands=agent_commands,
            )

        return 0.0

    def _build_info(self) -> dict[str, Any]:
        state = self._engine.state
        if state is None:
            return {"tick": 0, "entities": 0, "winner": 0, "action_mask": [False] * len(COMMAND_TYPES)}

        info: dict[str, Any] = {
            "tick": state.tick,
            "entities": len(state.entities),
            "winner": state.winner,
            "is_terminal": state.is_terminal,
            "resources": dict(state.resources),
        }

        # Include subgoal milestone tracking info in dense mode
        if self._reward_shaping == "dense":
            info["subgoals"] = get_subgoal_info(self._subgoal_tracker)

        # ─── Action mask: which COMMAND_TYPES are currently legal ───
        info["action_mask"] = self._compute_action_mask(state)

        return info

    def _compute_action_mask(self, state: GameState) -> list[bool]:
        """Compute which command types are legal for the current player.

        Returns a boolean list of length len(COMMAND_TYPES) where True means the
        corresponding command type has at least one valid target entity.
        """
        n_cmd = len(COMMAND_TYPES)
        mask = [False] * n_cmd

        if state is None or state.is_terminal:
            # Only noop is legal when the game is over
            noop_idx = COMMAND_TYPE_MAP.get("noop", n_cmd - 1)
            mask[noop_idx] = True
            return mask

        # Determine which player(s) we control
        controlled_owners = {1, 2} if self._two_player else {1}

        for eid, e in state.entities.items():
            owner = e.get("owner", 0)
            if owner not in controlled_owners:
                continue
            etype = e.get("entity_type", e.get("building_type", e.get("unit_type", "")))
            if e.get("health", 0) <= 0:
                continue

            # move: any mobile unit (worker, soldier, scout)
            if etype in ("worker", "soldier", "scout"):
                mask[COMMAND_TYPE_MAP["attack"]] = True

            # gather: workers only
            if etype == "worker":
                mask[COMMAND_TYPE_MAP["gather"]] = True
                mask[COMMAND_TYPE_MAP["build"]] = True

            # train: buildings that are completed and not constructing
            if etype in ("building", "base", "barracks", "factory", "starport"):
                if not e.get("is_constructing", False):
                    mask[COMMAND_TYPE_MAP["train"]] = True

        # noop is always legal
        mask[COMMAND_TYPE_MAP["noop"]] = True

        return mask

    def _render_ascii(self) -> None:
        state = self._engine.state
        if state is None:
            print("No game state")
            return

        grid_size = 32
        grid = [["." for _ in range(grid_size)] for _ in range(grid_size)]
        for _eid, e in state.entities.items():
            etype = e.get("entity_type", e.get("building_type", e.get("unit_type", "?")))
            owner = e.get("owner", 0)
            x = int(e.get("pos_x", 0) / MAP_SIZE * grid_size) % grid_size
            y = int(e.get("pos_y", 0) / MAP_SIZE * grid_size) % grid_size

            char = "?"
            if etype == "base":
                char = "B"
            elif etype == "barracks":
                char = "R"
            elif etype == "worker":
                char = "w"
            elif etype == "soldier":
                char = "s"
            elif etype == "scout":
                char = "c"
            elif etype == "resource":
                char = "*"
            elif etype == "building":
                # Protoss / Terran / Zerg buildings — use first letter of building_type
                btype = e.get("building_type", e.get("unit_type", "?"))
                char = btype[0] if btype else "?"
            # Check for Protoss-specific unit types
            utype = e.get("unit_type", "")
            if utype == "Probe":
                char = "p"
            elif utype == "Zealot":
                char = "z"
            elif utype == "Dragoon":
                char = "d"
            elif utype == "Templar":
                char = "t"
            elif utype == "DarkTemplar":
                char = "k"
            elif utype == "Archon":
                char = "a"
            elif utype == "DarkArchon":
                char = "A"
            elif utype == "Reaver":
                char = "v"
            elif utype == "Shuttle":
                char = "h"
            elif utype == "Observer":
                char = "o"
            elif utype == "Arbiter":
                char = "b"
            elif utype == "Carrier":
                char = "C"
            elif utype == "Corsair":
                char = "r"

            if owner == 1:
                char = char.upper()
            elif owner == 2:
                char = char.lower()

            grid[y][x] = char

        print(f"\n  Tick {state.tick}  Winner={state.winner}  Terminal={state.is_terminal}")
        print("  " + "".join("-" for _ in range(grid_size)))
        for row in grid:
            print("  " + "".join(row))
        print("  " + "".join("-" for _ in range(grid_size)))
        p1m = state.resources.get('p1_mineral', 0)
        p1g = state.resources.get('p1_gas', 0)
        p2m = state.resources.get('p2_mineral', 0)
        p2g = state.resources.get('p2_gas', 0)
        print(f"  P1: mineral={p1m} gas={p1g}")
        print(f"  P2: mineral={p2m} gas={p2g}")


# ─── Registration ─────────────────────────────────────────

gym.register(
    id="rts-ai-v0",
    entry_point="simcore.gym_env:RTSSimCoreEnv",
    max_episode_steps=10000,
    kwargs={"opponent_difficulty": "medium"},
)


# ─── Action conversion utilities ─────────────────────────

def discrete_to_md(action_int: int) -> np.ndarray:
    """Convert a Discrete action integer to a MultiDiscrete action array.

    Discrete encoding (new):
        ct_idx = action // (ACTION_DIM_EID * 32)
        eid_bucket = (action % (ACTION_DIM_EID * 32)) // 32
        target_idx = action % 32

    MultiDiscrete: [ct_idx, eid_bucket, x_bucket, y_bucket]
        where x_bucket = target_idx % 8,  y_bucket = target_idx // 8
    """
    n_x = ACTION_DIM_X       # 8
    n_y = ACTION_DIM_Y       # 4
    n_eid = ACTION_DIM_EID   # 4
    n_targets = n_x * n_y    # 32

    ct_idx = action_int // (n_eid * n_targets)
    remainder = action_int % (n_eid * n_targets)
    eid_bucket = remainder // n_targets
    target_idx = remainder % n_targets

    x_bucket = target_idx % n_x
    y_bucket = target_idx // n_x

    return np.array([ct_idx, eid_bucket, x_bucket, y_bucket], dtype=np.int64)


def md_to_discrete(action_md: np.ndarray) -> int:
    """Convert a MultiDiscrete action array to a Discrete action integer.

    MultiDiscrete: [ct_idx, eid_bucket, x_bucket, y_bucket]
        target_idx = y_bucket * 8 + x_bucket

    Discrete encoding (new):
        action = ct_idx * (4 * 32) + eid_bucket * 32 + target_idx
    """
    n_x = ACTION_DIM_X       # 8
    n_y = ACTION_DIM_Y       # 4
    n_eid = ACTION_DIM_EID   # 4
    n_targets = n_x * n_y    # 32

    ct_idx = int(action_md[0])
    eid_bucket = int(action_md[1])
    x_bucket = int(action_md[2])
    y_bucket = int(action_md[3])

    target_idx = y_bucket * n_x + x_bucket

    return ct_idx * (n_eid * n_targets) + eid_bucket * n_targets + target_idx


__all__ = [
    "RTSSimCoreEnv",
    "discrete_to_md",
    "md_to_discrete",
    "ACTION_DIM_X",
    "ACTION_DIM_Y",
    "ACTION_DIM_EID",
]