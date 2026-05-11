"""Tests for Gymnasium environment wrapper."""
import gymnasium as gym
import numpy as np

# Trigger gym.register() call
import simcore.gym_env  # noqa: F401


class TestGymEnvBasics:
    """Core Gym API compliance tests."""

    def test_make_and_reset(self):
        env = gym.make("rts-ai-v0", seed=42)
        obs, info = env.reset()
        assert "entities" in obs
        assert "resources" in obs
        assert "tick" in obs
        assert obs["entities"].shape == (64, 10)
        assert obs["resources"].shape == (4,)
        env.close()

    def test_step_returns_valid_tuple(self):
        env = gym.make("rts-ai-v0", seed=42)
        env.reset()
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert "tick" in info
        env.close()

    def test_action_space_sample(self):
        env = gym.make("rts-ai-v0", seed=42)
        action = env.action_space.sample()
        assert env.action_space.contains(action)
        env.close()

    def test_observation_space_contains(self):
        env = gym.make("rts-ai-v0", seed=42)
        obs, _ = env.reset()
        assert env.observation_space.contains(obs)
        env.close()

    def test_deterministic_reset(self):
        env = gym.make("rts-ai-v0", seed=42)
        obs1, _ = env.reset(seed=42)
        obs2, _ = env.reset(seed=42)
        np.testing.assert_array_equal(obs1["entities"], obs2["entities"])
        env.close()


class TestRewardShaping:
    """Reward function variants."""

    def test_sparse_reward_zero_during_game(self):
        env = gym.make("rts-ai-v0", seed=42, reward_shaping="sparse")
        env.reset()
        for _ in range(10):
            _, reward, _, _, _ = env.step(env.action_space.sample())
            assert reward == 0.0
        env.close()

    def test_shaped_reward_nonzero(self):
        env = gym.make("rts-ai-v0", seed=42, reward_shaping="shaped")
        env.reset()
        rewards = []
        # 300 steps ensures ScriptAI P2 builds units and gathers resources,
        # triggering non-zero shaped reward for P1. 100 steps was flaky.
        for _ in range(300):
            _, reward, _, _, _ = env.step(env.action_space.sample())
            rewards.append(reward)
        assert any(abs(r) > 0 for r in rewards), f"All rewards zero in 300 steps: {rewards[:15]}"
        env.close()


class TestASCIIRender:
    """ASCII render mode smoke test."""

    def test_ascii_render_no_crash(self, capsys):
        env = gym.make("rts-ai-v0", seed=42, render_mode="ascii")
        env.reset()
        env.step(env.action_space.sample())
        env.render()
        captured = capsys.readouterr()
        assert "Tick" in captured.out
        env.close()


class TestTwoPlayerMode:
    """Two-player (self-play) mode."""

    def test_two_player_init(self):
        env = gym.make("rts-ai-v0", seed=42, two_player=True)
        obs, info = env.reset()
        assert obs["entities"].shape == (64, 10)
        env.close()
