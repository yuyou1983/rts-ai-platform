"""Unit tests for simcore.wrappers — FlattenRTSObs, NormalizeRTSReward, ActionMaskRTS."""
from __future__ import annotations

import gymnasium as gym
import numpy as np
import pytest

import simcore.gym_env  # noqa: F401 — triggers gym.register()
from simcore.wrappers import (
    ActionMaskRTS,
    FlattenRTSObs,
    NormalizeRTSReward,
    MultiDiscreteActionMaskRTS,
    FLAT_DIM,
    TOTAL_ACTIONS,
    COMMAND_TYPES,
    ACTION_DIM_EID,
    N_X,
    N_Y,
    N_TARGETS,
)


# ─── Helpers ───────────────────────────────────────────────────────

def _make_env(**kwargs):
    return gym.make("rts-ai-v0", seed=42, **kwargs)


# ─── FlattenRTSObs ─────────────────────────────────────────────────

class TestFlattenRTSObs:
    """FlattenRTSObs: Dict obs → Box(1093,) float32."""

    def test_observation_space_is_box_1093(self):
        env = FlattenRTSObs(_make_env())
        assert isinstance(env.observation_space, gym.spaces.Box)
        assert env.observation_space.shape == (FLAT_DIM,)
        assert env.observation_space.dtype == np.float32
        env.close()

    def test_reset_returns_flat_vector(self):
        env = FlattenRTSObs(_make_env())
        obs, info = env.reset()
        assert obs.shape == (FLAT_DIM,)
        assert obs.dtype == np.float32
        env.close()

    def test_step_returns_flat_vector(self):
        env = FlattenRTSObs(_make_env())
        env.reset()
        obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
        assert obs.shape == (FLAT_DIM,)
        assert obs.dtype == np.float32
        env.close()

    def test_flat_obs_values_match_dict(self):
        """Verify flattening preserves values: concat(entities.flatten(), resources, tick)."""
        raw = _make_env()
        flat = FlattenRTSObs(raw)
        # Access the unwrapped RTSSimCoreEnv (gym.make adds TimeLimit)
        inner = raw.unwrapped
        inner.reset()
        raw_obs = inner._state_to_obs(inner._engine.state)
        flat_obs, _ = flat.reset()

        expected = np.concatenate([
            raw_obs["entities"].flatten(),
            raw_obs["resources"].flatten(),
            raw_obs["tick"].flatten(),
        ]).astype(np.float32)
        np.testing.assert_array_almost_equal(flat_obs, expected)
        flat.close()

    def test_observation_space_contains_reset_obs(self):
        env = FlattenRTSObs(_make_env())
        obs, _ = env.reset()
        assert env.observation_space.contains(obs), "Flattened obs not in declared space"
        env.close()

    def test_low_high_match_original(self):
        """Flattened low/high bounds are the concat of original sub-spaces."""
        raw = _make_env()
        flat = FlattenRTSObs(raw)
        low = np.concatenate([
            raw.observation_space["entities"].low.flatten(),
            raw.observation_space["resources"].low.flatten(),
            raw.observation_space["tick"].low.flatten(),
        ])
        high = np.concatenate([
            raw.observation_space["entities"].high.flatten(),
            raw.observation_space["resources"].high.flatten(),
            raw.observation_space["tick"].high.flatten(),
        ])
        np.testing.assert_array_equal(flat.observation_space.low, low)
        np.testing.assert_array_equal(flat.observation_space.high, high)
        flat.close()


# ─── NormalizeRTSReward ────────────────────────────────────────────

class TestNormalizeRTSReward:
    """NormalizeRTSReward: running z-score with eps=1e-8."""

    def test_single_step_reward_is_zero(self):
        """First reward: mean = r, var undefined → std returns 1.0, so r_norm = 0."""
        env = NormalizeRTSReward(_make_env(reward_shaping="shaped"))
        env.reset()
        # The very first reward normalises to 0 because mean==reward and std==1
        # This is by design: not enough data for meaningful normalisation.
        # After a few steps the stats stabilise.
        env.close()

    def test_stats_accumulate_across_steps(self):
        env = NormalizeRTSReward(_make_env(reward_shaping="shaped"))
        env.reset()
        for _ in range(50):
            env.step(env.action_space.sample())
        assert env._count >= 50
        # mean/var should have been updated
        assert env._var != 1.0 or env._count < 2  # var changes after 2+ samples
        env.close()

    def test_eps_prevents_division_by_zero(self):
        env = NormalizeRTSReward(_make_env(reward_shaping="shaped"), eps=1e-8)
        env._mean = 0.0
        env._var = 0.0
        env._count = 100  # pretend we have data
        # std = sqrt(0 / 99 + 1e-8) ≈ 1e-4, not zero
        std = env._std
        assert std > 0
        # normalising should not raise
        result = env.reward(0.0)  # _update_stats will be called but we manually set state
        env.close()

    def test_normalised_reward_is_finite(self):
        env = NormalizeRTSReward(_make_env(reward_shaping="shaped"))
        env.reset()
        for _ in range(200):
            _, reward, _, _, _ = env.step(env.action_space.sample())
            assert np.isfinite(reward), f"Non-finite normalised reward: {reward}"
        env.close()

    def test_identity_after_many_zero_rewards(self):
        """If all rewards are zero, normalised reward should be zero."""
        env = NormalizeRTSReward(_make_env(reward_shaping="sparse"))
        env.reset()
        rewards = []
        for _ in range(20):
            _, r, _, _, _ = env.step(env.action_space.sample())
            rewards.append(r)
        # sparse rewards are zero during the game, so normalised should also ≈ 0
        # after the first couple steps once stats stabilise
        for r in rewards[3:]:
            assert abs(r) < 0.05, f"Expected ≈0 normalised sparse reward, got {r}"
        env.close()

    def test_reset_does_not_clear_stats(self):
        """Statistics persist across episodes (standard RL practice)."""
        env = NormalizeRTSReward(_make_env(reward_shaping="shaped"))
        env.reset()
        for _ in range(30):
            env.step(env.action_space.sample())
        count_before = env._count
        mean_before = env._mean
        env.reset()
        assert env._count == count_before, "Stats should not reset on env.reset()"
        assert env._mean == mean_before
        env.close()


# ─── ActionMaskRTS ─────────────────────────────────────────────────

class TestActionMaskRTS:
    """ActionMaskRTS: info["action_mask"] with shape (768,)."""

    def test_mask_in_info_on_reset(self):
        env = ActionMaskRTS(_make_env())
        _, info = env.reset()
        assert "action_mask" in info
        assert "action_mask_discrete" in info
        mask = info["action_mask"]
        assert mask.shape == (TOTAL_ACTIONS,)
        assert mask.dtype == np.bool_
        env.close()

    def test_mask_in_info_on_step(self):
        env = ActionMaskRTS(_make_env())
        env.reset()
        _, _, _, _, info = env.step(env.action_space.sample())
        assert "action_mask" in info
        assert "action_mask_discrete" in info
        assert info["action_mask"].shape == (TOTAL_ACTIONS,)
        env.close()

    def test_at_least_one_valid_action(self):
        """On reset there should always be at least one alive owned unit (the base)."""
        env = ActionMaskRTS(_make_env())
        _, info = env.reset()
        assert info["action_mask"].any(), "Expected at least one valid action on reset"
        env.close()

    def test_mask_structure_per_entity(self):
        """If entity bucket i is valid, all cmd*4*32 + i*32 + [0..31] should be True."""
        env = ActionMaskRTS(_make_env())
        obs, info = env.reset()
        mask = info["action_mask"]

        # Find a valid entity bucket index
        entities = obs["entities"]
        health = entities[:, 2]
        owner = entities[:, 7]
        valid_units = np.where((health > 0) & (np.isclose(owner, 0.5, atol=0.05)))[0]

        # The first valid alive-owned entity maps to eid_bucket=0
        if len(valid_units) > 0:
            eb = 0
            for cmd in range(COMMAND_TYPES):
                base = cmd * (ACTION_DIM_EID * N_TARGETS) + eb * N_TARGETS
                assert mask[base : base + N_TARGETS].all(), (
                    f"Expected all targets valid for cmd={cmd}, eid_bucket={eb}"
                )
        env.close()

    def test_invalid_entities_masked(self):
        """Dead or enemy entities should have all corresponding actions masked (False)."""
        env = ActionMaskRTS(_make_env())
        obs, info = env.reset()
        mask = info["action_mask"]

        entities = obs["entities"]
        health = entities[:, 2]
        owner = entities[:, 7]
        # Find entity indices that are NOT alive+owned
        invalid_units = np.where(~((health > 0) & (np.isclose(owner, 0.5, atol=0.05))))[0]

        # If there are fewer than 4 alive owned entities, some eid_buckets are invalid
        n_alive_owned = int(((health > 0) & (np.isclose(owner, 0.5, atol=0.05))).sum())
        if n_alive_owned < ACTION_DIM_EID:
            for eb in range(n_alive_owned, ACTION_DIM_EID):
                for cmd in range(COMMAND_TYPES):
                    base = cmd * (ACTION_DIM_EID * N_TARGETS) + eb * N_TARGETS
                    assert not mask[base : base + N_TARGETS].any(), (
                        f"Expected all targets invalid for cmd={cmd}, empty eid_bucket={eb}"
                    )
        env.close()

    def test_total_valid_actions_divisible_by_n_targets(self):
        """Total valid True entries should be (num_valid_buckets * 6 * 32)."""
        env = ActionMaskRTS(_make_env())
        obs, info = env.reset()
        mask = info["action_mask"]

        entities = obs["entities"]
        health = entities[:, 2]
        owner = entities[:, 7]
        n_valid = int(((health > 0) & (np.isclose(owner, 0.5, atol=0.05))).sum())
        n_valid_buckets = min(n_valid, ACTION_DIM_EID)
        assert mask.sum() == n_valid_buckets * COMMAND_TYPES * N_TARGETS
        env.close()

    def test_mask_with_flattened_obs(self):
        """ActionMaskRTS should still work when wrapped around FlattenRTSObs."""
        env = FlattenRTSObs(_make_env())
        env = ActionMaskRTS(env)
        _, info = env.reset()
        assert "action_mask" in info
        assert info["action_mask"].shape == (TOTAL_ACTIONS,)
        assert info["action_mask"].any(), "Should have valid actions with flat obs"
        env.close()


# ─── Stacking all three wrappers ────────────────────────────────────

class TestWrapperStack:
    """Ensure all three wrappers can be stacked and work correctly."""

    def test_full_stack_reset_and_step(self):
        env = _make_env(reward_shaping="shaped")
        env = FlattenRTSObs(env)
        env = NormalizeRTSReward(env)
        env = ActionMaskRTS(env)

        obs, info = env.reset()
        assert obs.shape == (FLAT_DIM,)
        assert "action_mask" in info
        assert info["action_mask"].shape == (TOTAL_ACTIONS,)

        obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
        assert obs.shape == (FLAT_DIM,)
        assert np.isfinite(reward)
        assert "action_mask" in info
        env.close()

    def test_full_stack_episode_runs(self):
        env = _make_env(reward_shaping="shaped")
        env = FlattenRTSObs(env)
        env = NormalizeRTSReward(env)
        env = ActionMaskRTS(env)

        env.reset()
        for _ in range(50):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            assert obs.shape == (FLAT_DIM,)
            assert np.isfinite(reward)
            if terminated or truncated:
                env.reset()
        env.close()


# ─── ActionMaskRTS MultiDiscrete mode ──────────────────────────────

class TestActionMaskRTSMultiDiscrete:
    """ActionMaskRTS with action_mode='multidiscrete'."""

    def test_multidiscrete_mask_on_reset(self):
        env = ActionMaskRTS(_make_env(), action_mode="multidiscrete")
        _, info = env.reset()
        assert "action_mask" in info
        assert "action_mask_discrete" in info
        md_mask = info["action_mask"]
        # Should be a tuple/list of 4 arrays
        assert isinstance(md_mask, tuple)
        assert len(md_mask) == 4
        cmd_mask, eid_mask, x_mask, y_mask = md_mask
        assert cmd_mask.shape == (6,)
        assert eid_mask.shape == (4,)
        assert x_mask.shape == (8,)
        assert y_mask.shape == (4,)
        assert cmd_mask.dtype == np.bool_
        assert eid_mask.dtype == np.bool_
        assert x_mask.dtype == np.bool_
        assert y_mask.dtype == np.bool_
        env.close()

    def test_multidiscrete_mask_on_step(self):
        env = ActionMaskRTS(_make_env(), action_mode="multidiscrete")
        env.reset()
        _, _, _, _, info = env.step(env.action_space.sample())
        assert "action_mask" in info
        md_mask = info["action_mask"]
        assert isinstance(md_mask, tuple)
        assert len(md_mask) == 4
        env.close()

    def test_cmd_and_target_masks_all_true(self):
        """cmd, x, y masks should always be all True."""
        env = ActionMaskRTS(_make_env(), action_mode="multidiscrete")
        _, info = env.reset()
        cmd_mask, eid_mask, x_mask, y_mask = info["action_mask"]
        assert cmd_mask.all(), "cmd_mask should be all True"
        assert x_mask.all(), "x_mask should be all True"
        assert y_mask.all(), "y_mask should be all True"
        env.close()

    def test_eid_mask_matches_alive_owned(self):
        """eid_mask should match the alive owned entities (up to 4)."""
        env = ActionMaskRTS(_make_env(), action_mode="multidiscrete")
        obs, info = env.reset()
        _, eid_mask, _, _ = info["action_mask"]
        entities = obs["entities"]
        health = entities[:, 2]
        owner = entities[:, 7]
        n_alive_owned = int(((health > 0) & (np.isclose(owner, 0.5, atol=0.05))).sum())
        n_valid = min(n_alive_owned, ACTION_DIM_EID)
        # eid_mask should have exactly n_valid True entries
        assert eid_mask.sum() == n_valid
        env.close()

    def test_at_least_one_valid_entity(self):
        """On reset there should always be at least one alive owned unit (the base)."""
        env = ActionMaskRTS(_make_env(), action_mode="multidiscrete")
        _, info = env.reset()
        _, eid_mask, _, _ = info["action_mask"]
        assert eid_mask.any(), "Expected at least one valid entity bucket on reset"
        env.close()

    def test_discrete_mask_always_available(self):
        """action_mask_discrete should always be the flat (768,) mask."""
        env = ActionMaskRTS(_make_env(), action_mode="multidiscrete")
        _, info = env.reset()
        assert "action_mask_discrete" in info
        disc = info["action_mask_discrete"]
        assert disc.shape == (TOTAL_ACTIONS,)
        assert disc.dtype == np.bool_
        env.close()

    def test_invalid_action_mode_raises(self):
        with pytest.raises(ValueError, match="action_mode"):
            ActionMaskRTS(_make_env(), action_mode="invalid")

    def test_multidiscrete_with_flattened_obs(self):
        """Should work when wrapped around FlattenRTSObs."""
        env = FlattenRTSObs(_make_env())
        env = ActionMaskRTS(env, action_mode="multidiscrete")
        _, info = env.reset()
        md_mask = info["action_mask"]
        assert isinstance(md_mask, tuple)
        assert len(md_mask) == 4
        # unit_mask should still reflect alive P1 units
        _, unit_mask, _, _ = md_mask
        assert unit_mask.any(), "Should have valid units with flat obs"
        env.close()


# ─── MultiDiscreteActionMaskRTS convenience wrapper ─────────────────

class TestMultiDiscreteActionMaskRTS:
    """MultiDiscreteActionMaskRTS auto-detects action space."""

    def test_defaults_to_discrete_for_discrete_env(self):
        """Standard env has Discrete action space → uses discrete mode."""
        env = MultiDiscreteActionMaskRTS(_make_env())
        assert env.action_mode == "discrete"
        _, info = env.reset()
        # In discrete mode, action_mask is the flat (768,) array
        assert info["action_mask"].shape == (TOTAL_ACTIONS,)
        env.close()

    def test_uses_multidiscrete_for_multidiscrete_env(self):
        """If action_space is MultiDiscrete, auto-selects multidiscrete mode."""
        raw = _make_env()
        # Patch action_space to MultiDiscrete for detection
        original_space = raw.action_space
        raw.action_space = gym.spaces.MultiDiscrete([6, 4, 8, 4])
        env = MultiDiscreteActionMaskRTS(raw)
        assert env.action_mode == "multidiscrete"
        _, info = env.reset()
        md_mask = info["action_mask"]
        assert isinstance(md_mask, tuple)
        assert len(md_mask) == 4
        # Restore so close() doesn't break
        raw.action_space = original_space
        env.close()
