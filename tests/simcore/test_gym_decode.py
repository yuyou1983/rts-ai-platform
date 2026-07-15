"""Unit tests for RTSSimCoreEnv._decode_action.

Covers:
  (1) gather — correct target coordinates decoded (was "move", now removed)
  (2) gather — auto-finds nearest resource
  (3) attack — auto-finds nearest enemy
  (4) build  — barracks at target coordinates
  (5) train  — soldier in specified building
  (6) noop   — no-op command
  (7) eid_bucket out of range → noop
"""
from __future__ import annotations

import math

import pytest

from simcore.gym_env import RTSSimCoreEnv, COMMAND_TYPES, COMMAND_TYPE_MAP, MAP_SIZE, MAX_ENTITIES, ACTION_DIM_X, ACTION_DIM_Y, ACTION_DIM_EID
from simcore.state import GameState

# ─── Helpers ──────────────────────────────────────────────

N_TARGETS = ACTION_DIM_X * ACTION_DIM_Y  # 8*4 = 32
N_CMD = len(COMMAND_TYPES)  # 6


def _encode_action(ct_idx: int, eid_bucket: int, tx: int, ty: int) -> int:
    """Encode discrete action from command-type index, entity bucket, and target coordinates.

    tx and ty are world coordinates. They are quantised to x_bucket / y_bucket
    for the encoding, then decoded back inside _decode_action.
    """
    x_bucket = int(tx) // (MAP_SIZE // ACTION_DIM_X)   # 0..7
    y_bucket = int(ty) // (MAP_SIZE // ACTION_DIM_Y)   # 0..3
    target_idx = y_bucket * ACTION_DIM_X + x_bucket
    return ct_idx * (ACTION_DIM_EID * N_TARGETS) + eid_bucket * N_TARGETS + target_idx


def _make_env(**kwargs):
    """Create a minimal RTSSimCoreEnv with a mocked engine state."""
    env = RTSSimCoreEnv(seed=0, **kwargs)
    # State is a read-only property backed by _state; we set _state directly.
    return env


def _set_state(env: RTSSimCoreEnv, state: GameState) -> None:
    """Inject a GameState into the env's engine for testing _decode_action."""
    env._engine._state = state


# ─── Tests ───────────────────────────────────────────────


class TestDecodeGatherCoords:
    """(1) gather command decodes correct target coordinates (replaces old move test)."""

    def test_gather_decodes_target_coordinates(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 50,
            "max_health": 50,
        }
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        # ct_idx=0 is now "gather" (was "move")
        action = _encode_action(ct_idx=0, eid_bucket=0, tx=8, ty=16)
        cmds = env._decode_action(action)

        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd["action"] == "gather"
        assert cmd["worker_id"] == "w1"
        assert cmd["issuer"] == 1


class TestDecodeGather:
    """(2) gather command auto-finds nearest resource."""

    def test_gather_finds_nearest_resource(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 20.0,
            "pos_y": 20.0,
            "health": 50,
            "max_health": 50,
        }
        far_resource = {
            "entity_type": "resource",
            "owner": 0,
            "pos_x": 50.0,
            "pos_y": 50.0,
            "resource_amount": 100,
            "health": 100,
        }
        near_resource = {
            "entity_type": "resource",
            "owner": 0,
            "pos_x": 22.0,
            "pos_y": 21.0,
            "resource_amount": 200,
            "health": 100,
        }
        # Order matters: entity_ids = list(state.entities.keys()) => ["w1", "r_far", "r_near"]
        state = GameState(
            tick=0,
            entities={"w1": worker, "r_far": far_resource, "r_near": near_resource},
        )
        _set_state(env, state)

        action = _encode_action(ct_idx=0, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd["action"] == "gather"
        assert cmd["worker_id"] == "w1"
        # Should pick the nearer resource
        assert cmd["resource_id"] == "r_near"

    def test_gather_no_resources_returns_empty_resource_id(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 20.0,
            "pos_y": 20.0,
            "health": 50,
            "max_health": 50,
        }
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        action = _encode_action(ct_idx=0, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["action"] == "gather"
        # No resource found → resource_id is empty string
        assert cmd["resource_id"] == ""

    def test_gather_ignores_depleted_resources(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 20.0,
            "pos_y": 20.0,
            "health": 50,
            "max_health": 50,
        }
        depleted = {
            "entity_type": "resource",
            "owner": 0,
            "pos_x": 21.0,
            "pos_y": 21.0,
            "resource_amount": 0,
            "health": 0,
        }
        active = {
            "entity_type": "resource",
            "owner": 0,
            "pos_x": 40.0,
            "pos_y": 40.0,
            "resource_amount": 50,
            "health": 50,
        }
        state = GameState(
            tick=0, entities={"w1": worker, "r_dead": depleted, "r_alive": active}
        )
        _set_state(env, state)

        action = _encode_action(ct_idx=0, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["resource_id"] == "r_alive"


class TestDecodeAttack:
    """(3) attack command auto-finds nearest enemy."""

    def test_attack_finds_nearest_enemy(self):
        env = _make_env()

        soldier = {
            "entity_type": "soldier",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 80,
            "max_health": 80,
        }
        enemy_far = {
            "entity_type": "soldier",
            "owner": 2,
            "pos_x": 50.0,
            "pos_y": 50.0,
            "health": 60,
            "max_health": 60,
        }
        enemy_near = {
            "entity_type": "worker",
            "owner": 2,
            "pos_x": 12.0,
            "pos_y": 11.0,
            "health": 30,
            "max_health": 30,
        }
        state = GameState(
            tick=0,
            entities={"s1": soldier, "e_far": enemy_far, "e_near": enemy_near},
        )
        _set_state(env, state)

        action = _encode_action(ct_idx=1, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["action"] == "attack"
        assert cmd["attacker_id"] == "s1"
        assert cmd["target_id"] == "e_near"

    def test_attack_ignores_dead_enemies(self):
        env = _make_env()

        soldier = {
            "entity_type": "soldier",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 80,
            "max_health": 80,
        }
        dead_enemy = {
            "entity_type": "soldier",
            "owner": 2,
            "pos_x": 11.0,
            "pos_y": 11.0,
            "health": 0,
            "max_health": 60,
        }
        alive_enemy = {
            "entity_type": "soldier",
            "owner": 2,
            "pos_x": 50.0,
            "pos_y": 50.0,
            "health": 60,
            "max_health": 60,
        }
        state = GameState(
            tick=0,
            entities={"s1": soldier, "e_dead": dead_enemy, "e_alive": alive_enemy},
        )
        _set_state(env, state)

        action = _encode_action(ct_idx=1, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["target_id"] == "e_alive"

    def test_attack_no_enemies_returns_empty_target_id(self):
        env = _make_env()

        soldier = {
            "entity_type": "soldier",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 80,
            "max_health": 80,
        }
        state = GameState(tick=0, entities={"s1": soldier})
        _set_state(env, state)

        action = _encode_action(ct_idx=1, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["action"] == "attack"
        assert cmd["target_id"] == ""


class TestDecodeBuild:
    """(4) build command selects building_type based on race and target grid."""

    def test_build_resolves_building_type_at_target(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 16.0,
            "pos_y": 16.0,
            "health": 50,
            "max_health": 50,
        }
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        # Target cell (tx=32, ty=32) → x_bucket=2, y_bucket=1 (new 4×2 grid)
        action = _encode_action(ct_idx=2, eid_bucket=0, tx=32, ty=32)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["action"] == "build"
        assert cmd["builder_id"] == "w1"
        # building_type is now dynamically resolved from race + target grid index
        assert isinstance(cmd["building_type"], str)
        assert len(cmd["building_type"]) > 0
        assert cmd["pos_x"] == 32.0
        assert cmd["pos_y"] == 32.0
        assert cmd["issuer"] == 1


class TestDecodeTrain:
    """(5) train command resolves unit_type based on race and building context."""

    def test_train_resolves_unit_type_in_building(self):
        env = _make_env()

        barracks = {
            "entity_type": "barracks",
            "owner": 1,
            "pos_x": 30.0,
            "pos_y": 30.0,
            "health": 500,
            "max_health": 500,
        }
        state = GameState(tick=0, entities={"b1": barracks})
        _set_state(env, state)

        action = _encode_action(ct_idx=3, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["action"] == "train"
        assert cmd["building_id"] == "b1"
        # unit_type is now dynamically resolved from race + target grid index
        assert isinstance(cmd["unit_type"], str)
        assert len(cmd["unit_type"]) > 0
        assert cmd["issuer"] == 1


class TestDecodeNoop:
    """(6) noop command — no operation."""

    def test_noop_command(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 50,
            "max_health": 50,
        }
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        # ct_idx → "noop"
        action = _encode_action(ct_idx=COMMAND_TYPE_MAP["noop"], eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd["action"] == "noop"
        assert cmd["issuer"] == 1
        # noop has no additional keys
        assert "unit_id" not in cmd
        assert "target_x" not in cmd


class TestDecodeEidBucketOutOfRange:
    """(7) eid_bucket out of range returns noop."""

    def test_eid_bucket_exceeds_owned_entity_count_returns_noop(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 50,
            "max_health": 50,
        }
        # Only 1 alive owned entity, so eid_bucket >= 1 is out of range
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        # eid_bucket=1 (out of range with only 1 entity), any command type (gather)
        action = _encode_action(ct_idx=0, eid_bucket=3, tx=8, ty=8)
        cmds = env._decode_action(action)

        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd["action"] == "noop"
        assert cmd["issuer"] == 1

    def test_eid_bucket_at_boundary_returns_noop(self):
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 50,
            "max_health": 50,
        }
        # 1 alive owned entity → valid eid_bucket is 0; eid_bucket=1 is out of range
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        action = _encode_action(ct_idx=0, eid_bucket=1, tx=8, ty=8)
        cmds = env._decode_action(action)

        assert cmds[0]["action"] == "noop"


class TestDecodeEdgeCases:
    """Additional edge cases for _decode_action."""

    def test_null_state_returns_empty_list(self):
        env = _make_env()
        env._engine._state = None

        action = _encode_action(ct_idx=0, eid_bucket=0, tx=0, ty=0)
        cmds = env._decode_action(action)

        assert cmds == []

    def test_non_p1_unit_in_single_player_returns_noop(self):
        env = _make_env()

        enemy = {
            "entity_type": "soldier",
            "owner": 2,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 80,
            "max_health": 80,
        }
        state = GameState(tick=0, entities={"e1": enemy})
        _set_state(env, state)

        # Try to move enemy unit (owner=2) in single-player mode
        # With no owned P1 entities, eid_bucket=0 is out of range → noop
        action = _encode_action(ct_idx=0, eid_bucket=0, tx=8, ty=8)
        cmds = env._decode_action(action)

        assert cmds[0]["action"] == "noop"
        assert cmds[0]["issuer"] == 1

    def test_p2_unit_in_two_player_mode_is_controlled(self):
        env = _make_env(two_player=True)

        enemy = {
            "entity_type": "soldier",
            "owner": 2,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 80,
            "max_health": 80,
        }
        state = GameState(tick=0, entities={"e1": enemy})
        _set_state(env, state)

        # Try to control enemy unit (owner=2) in two-player mode
        # ct_idx=0 is now "gather"
        action = _encode_action(ct_idx=0, eid_bucket=0, tx=8, ty=8)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["action"] == "gather"
        assert cmd["worker_id"] == "e1"
        assert cmd["issuer"] == 2

    def test_ct_idx_clamped_to_noop(self):
        """ct_idx >= n_cmd is clamped to n_cmd-1 (noop)."""
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 50,
            "max_health": 50,
        }
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        # Use a ct_idx way beyond the valid range
        # The encoding formula: action = ct_idx * (ACTION_DIM_EID * N_TARGETS) + ...
        # ct_idx=100 → clamped to last index (noop)
        action = 100 * (ACTION_DIM_EID * N_TARGETS) + 0 * N_TARGETS + 0
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["action"] == "noop"

    def test_target_cell_resolution(self):
        """Verify that different x_bucket/y_bucket values map to correct world coords."""
        env = _make_env()

        worker = {
            "entity_type": "worker",
            "owner": 1,
            "pos_x": 0.0,
            "pos_y": 0.0,
            "health": 50,
            "max_health": 50,
        }
        state = GameState(tick=0, entities={"w1": worker})
        _set_state(env, state)

        # x_bucket=2 → tx=32, y_bucket=1 → ty=32 (new 4×2 grid)
        action = _encode_action(ct_idx=2, eid_bucket=0, tx=32, ty=32)
        cmds = env._decode_action(action)

        cmd = cmds[0]
        assert cmd["pos_x"] == 32.0
        assert cmd["pos_y"] == 32.0


# ─── Gym + RushAI Integration ───────────────────────────

class TestGymAgentIntegration:
    """Verify Gym env works end-to-end with rule-based AI opponents."""

    def test_single_player_200_steps_no_crash(self):
        """Random P1 + RushAI P2, 200 steps, no exception."""
        from simcore.agents.rush import RushAI

        def factory(*, player_id):
            return RushAI(player_id=player_id, attack_threshold=2)

        env = RTSSimCoreEnv(seed=7, two_player=False, agent_factory=factory, max_ticks=5000)
        obs, info = env.reset()
        for _ in range(200):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            assert obs["entities"].shape == (64, 17)
            assert obs["resources"].shape == (4,)
            assert isinstance(reward, float)
            assert isinstance(terminated, bool)
            assert isinstance(truncated, bool)
            if terminated or truncated:
                break
        env.close()

    def test_two_player_200_steps_no_crash(self):
        """Two-player mode, both random actions, 200 steps."""
        env = RTSSimCoreEnv(seed=7, two_player=True, max_ticks=5000)
        obs, info = env.reset()
        for _ in range(200):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        env.close()

    def test_shaped_reward_nonzero(self):
        """Shaped reward should be nonzero after enough steps."""
        from simcore.agents.rush import RushAI

        def factory(*, player_id):
            return RushAI(player_id=player_id, attack_threshold=2)

        env = RTSSimCoreEnv(
            seed=7, two_player=False, agent_factory=factory,
            reward_shaping="shaped", max_ticks=5000,
        )
        obs, info = env.reset()
        total_reward = 0.0
        for _ in range(300):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            if terminated or truncated:
                break
        # Shaped reward should have accumulated something
        assert total_reward != 0.0, "Shaped reward remained zero after 300 steps"
        env.close()

    def test_terminal_info_has_winner(self):
        """When game terminates, info should contain winner info."""
        from simcore.agents.rush import RushAI

        def factory(*, player_id):
            return RushAI(player_id=player_id, attack_threshold=2)

        env = RTSSimCoreEnv(seed=7, two_player=False, agent_factory=factory, max_ticks=8000)
        obs, info = env.reset()
        for _ in range(8000):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated:
                assert "winner" in info, "terminated=True but no winner in info"
                assert info["winner"] in (0, 1, 2), f"Invalid winner value: {info['winner']}"
                break
            if truncated:
                break
        env.close()

    def test_reset_clears_state(self):
        """After reset, tick should go back to 0."""
        from simcore.agents.rush import RushAI

        def factory(*, player_id):
            return RushAI(player_id=player_id, attack_threshold=2)

        env = RTSSimCoreEnv(seed=7, two_player=False, agent_factory=factory)
        obs, info = env.reset()
        assert info["tick"] == 0
        # Run 50 steps
        for _ in range(50):
            env.step(env.action_space.sample())
        # Reset and verify tick=0
        obs2, info2 = env.reset()
        assert info2["tick"] == 0
        env.close()
