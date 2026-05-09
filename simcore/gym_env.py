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
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from simcore.engine import SimCore
from simcore.state import GameState

# ─── Constants ─────────────────────────────────────────────

MAP_SIZE = 64
MAX_ENTITIES = 64
ENTITY_FEATURES = 10  # x, y, health, max_health, speed, attack, range, owner, type_idx, is_idle

UNIT_TYPES = ["worker", "soldier", "scout", "base", "barracks", "resource"]
UNIT_TYPE_MAP = {t: i for i, t in enumerate(UNIT_TYPES)}

COMMAND_TYPES = ["move", "gather", "attack", "build", "train", "noop"]
COMMAND_TYPE_MAP = {t: i for i, t in enumerate(COMMAND_TYPES)}


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
        render_mode: str | None = None,
    ) -> None:
        super().__init__()

        self._seed = seed
        self._max_ticks = max_ticks
        self._two_player = two_player
        self._reward_shaping = reward_shaping
        self.render_mode = render_mode

        self._engine = SimCore(max_ticks=max_ticks)
        self._prev_resources: dict[str, int] = {}

        # Observation: (MAX_ENTITIES, ENTITY_FEATURES) + resource vector
        self.observation_space = spaces.Dict({
            "entities": spaces.Box(
                low=0, high=max(MAP_SIZE, 2000),
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

        # Action: discrete over command_type × unit_idx × target_cell
        # Simplified: 6 command types × 64 max units × 16×16 target grid
        n_cmd = len(COMMAND_TYPES)
        n_units = MAX_ENTITIES
        n_targets = 16 * 16  # 16×16 grid = coarse target mapping
        self._n_actions = n_cmd * n_units * n_targets
        self.action_space = spaces.Discrete(self._n_actions)

    def reset(
        self, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        super().reset(seed=seed)
        actual_seed = seed if seed is not None else self._seed
        self._engine.initialize(map_seed=actual_seed)
        self._prev_resources = dict(self._engine.state.resources) if self._engine.state else {}

        obs = self._state_to_obs(self._engine.state)
        info = self._build_info()
        return obs, info

    def step(
        self, action: int
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        # Decode action
        commands = self._decode_action(action)

        # Add ScriptAI for P2 if single-player
        all_commands = list(commands)
        if not self._two_player and self._engine.state:
            from agents.script_ai import ScriptAI
            ai = ScriptAI(player_id=2)
            obs_p2 = self._engine.state.get_observations()[1]
            ai_result = ai.decide(obs_p2)
            ai_cmds = ai_result.get("commands", []) if isinstance(ai_result, dict) else []
            all_commands.extend(ai_cmds)

        # Step engine
        prev_state = self._engine.state
        new_state = self._engine.step(all_commands)

        obs = self._state_to_obs(new_state)
        reward = self._compute_reward(prev_state, new_state)
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
            entities_arr[i] = [
                e.get("pos_x", 0.0) / MAP_SIZE,
                e.get("pos_y", 0.0) / MAP_SIZE,
                e.get("health", 0.0) / max(e.get("max_health", 1.0), 1.0),
                e.get("max_health", 0.0) / 2000.0,
                e.get("speed", 0.0) / 5.0,
                e.get("attack", 0.0) / 50.0,
                e.get("attack_range", 0.0) / 10.0,
                e.get("owner", 0) / 2.0,
                UNIT_TYPE_MAP.get(etype, 0) / len(UNIT_TYPES),
                float(e.get("is_idle", False)),
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

    def _decode_action(self, action: int) -> list[dict]:
        n_targets = 16 * 16
        n_units = MAX_ENTITIES
        n_cmd = len(COMMAND_TYPES)

        ct_idx = action // (n_units * n_targets)
        remainder = action % (n_units * n_targets)
        unit_idx = remainder // n_targets
        target_idx = remainder % n_targets

        ct_idx = min(ct_idx, n_cmd - 1)
        cmd_type = COMMAND_TYPES[ct_idx]

        # Find actual entity id
        if self._engine.state is None:
            return []
        entity_ids = list(self._engine.state.entities.keys())
        if unit_idx >= len(entity_ids):
            return [{"action": "noop", "issuer": 1}]

        eid = entity_ids[unit_idx]
        entity = self._engine.state.entities[eid]
        owner = entity.get("owner", 0)

        # Only control P1 in single-player, both in two-player
        if not self._two_player and owner != 1:
            return [{"action": "noop", "issuer": 1}]

        tx = (target_idx % 16) * (MAP_SIZE / 16)
        ty = (target_idx // 16) * (MAP_SIZE / 16)

        cmd: dict[str, Any] = {"action": cmd_type, "issuer": owner}

        if cmd_type == "move":
            cmd["unit_id"] = eid
            cmd["target_x"] = tx
            cmd["target_y"] = ty
        elif cmd_type == "gather":
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
            cmd["building_type"] = "barracks"
            cmd["pos_x"] = tx
            cmd["pos_y"] = ty
        elif cmd_type == "train":
            cmd["building_id"] = eid
            cmd["unit_type"] = "soldier"
        elif cmd_type == "noop":
            pass

        return [cmd]

    def _compute_reward(self, prev: GameState | None, curr: GameState) -> float:
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

        return 0.0

    def _build_info(self) -> dict[str, Any]:
        state = self._engine.state
        if state is None:
            return {"tick": 0, "entities": 0, "winner": 0}

        return {
            "tick": state.tick,
            "entities": len(state.entities),
            "winner": state.winner,
            "is_terminal": state.is_terminal,
            "resources": dict(state.resources),
        }

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
)
