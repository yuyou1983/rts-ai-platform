"""Tests for SB3 PPO integration — wrapper, training, and evaluation.

Three test classes:
  1. TestWrapperCreation — verify the wrapper layer creates a valid env.
  2. TestSB3PPOLearn — verify PPO can learn for 1 step without crashing.
  3. TestSB3EvalScript — verify the eval script entry point is runnable.

All SB3-dependent tests are *skipped* when stable-baselines3 is not
installed, so the suite still passes in minimal CI environments.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

# ─── Optional SB3 import ─────────────────────────────────────

try:
    import gymnasium as gym
    from stable_baselines3 import PPO

    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False
    gym = None  # type: ignore[assignment]
    PPO = None  # type: ignore[assignment, misc]


# ─── Helpers ────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # ~/code/rts-ai-platform


def _make_wrapped_env(seed: int = 42, max_ticks: int = 200):
    """Create an rts-ai-v0 env wrapped with FlattenRTSObs."""
    import gymnasium as gym  # type: ignore[no-redef]

    import simcore.gym_env  # noqa: F401 — register
    from simcore.wrappers import FlattenRTSObs

    env = gym.make(
        "rts-ai-v0",
        seed=seed,
        max_ticks=max_ticks,
        reward_shaping="shaped",
    )
    env = FlattenRTSObs(env)
    return env


# ─── 1. TestWrapperCreation ─────────────────────────────────


@pytest.mark.skipif(not HAS_SB3, reason="stable-baselines3 not installed")
class TestWrapperCreation:
    """Verify the wrapper layer can create a gym env compatible with SB3."""

    def test_make_env_and_reset(self):
        """Wrapped env resets and returns a flat Box observation."""
        env = _make_wrapped_env()
        obs, info = env.reset(seed=42)
        assert isinstance(obs, np.ndarray), f"Expected ndarray, got {type(obs)}"
        assert obs.shape[0] >= 645, f"Expected shape >= (645,), got {obs.shape}"
        assert obs.dtype == np.float32
        env.close()

    def test_step_returns_valid_tuple(self):
        """Stepping the wrapped env returns the standard 5-tuple."""
        env = _make_wrapped_env()
        obs, _ = env.reset(seed=0)
        action = env.action_space.sample()
        obs2, reward, terminated, truncated, info = env.step(action)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)
        env.close()

    def test_observation_space_is_box(self):
        """FlattenRTSObs converts the Dict space to a single Box."""
        env = _make_wrapped_env()
        assert isinstance(env.observation_space, gym.spaces.Box)
        assert env.observation_space.shape[0] >= 645
        env.close()

    def test_action_space_is_discrete(self):
        """Action space remains Discrete after wrapping."""
        env = _make_wrapped_env()
        assert isinstance(env.action_space, gym.spaces.Discrete)
        env.close()


# ─── 2. TestSB3PPOLearn ──────────────────────────────────────


@pytest.mark.skipif(not HAS_SB3, reason="stable-baselines3 not installed")
class TestSB3PPOLearn:
    """Verify that sb3 PPO can learn 1 step without crashing."""

    def test_ppo_learn_one_step(self):
        """Create PPO with MlpPolicy and call learn(n_steps=64).

        This is the minimal "smoke test" — we just need it to not crash.
        """
        env = _make_wrapped_env()
        model = PPO(
            "MlpPolicy",
            env,
            verbose=0,
            seed=42,
            n_steps=64,
            batch_size=32,
            n_epochs=1,
        )
        model.learn(total_timesteps=64)
        env.close()

    def test_ppo_predict_after_learn(self):
        """After learning, model.predict() returns valid actions."""
        env = _make_wrapped_env()
        model = PPO(
            "MlpPolicy",
            env,
            verbose=0,
            seed=42,
            n_steps=64,
            batch_size=32,
            n_epochs=1,
        )
        model.learn(total_timesteps=64)

        obs, _ = env.reset(seed=7)
        action, _ = model.predict(obs, deterministic=True)
        assert env.action_space.contains(int(action)), (
            f"Action {action} not in action space"
        )
        env.close()


# ─── 3. TestSB3EvalScript ────────────────────────────────────


@pytest.mark.skipif(not HAS_SB3, reason="stable-baselines3 not installed")
class TestSB3EvalScript:
    """Verify the eval script is runnable end-to-end (quick mode)."""

    def test_eval_script_runs(self, tmp_path):
        """Run sb3_eval.py with --episodes 1 --quick-train-steps 64.

        The script should quick-train (since no model file exists) and
        evaluate one episode, exiting with code 0.
        """
        model_path = tmp_path / "sb3_ppo.zip"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "train.sb3_eval",
                "--model-path",
                str(model_path),
                "--episodes",
                "1",
                "--quick-train-steps",
                "64",
                "--max-ticks",
                "200",
                "--log-level",
                "WARNING",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Eval script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # The quick-trained model should have been saved
        assert model_path.exists(), f"Model file not saved at {model_path}"

    def test_eval_script_with_existing_model(self, tmp_path):
        """Run eval when model file already exists — should skip training."""
        # First: quick-train a model
        model_path = tmp_path / "sb3_ppo.zip"
        env = _make_wrapped_env()
        model = PPO(
            "MlpPolicy",
            env,
            verbose=0,
            seed=42,
            n_steps=64,
            batch_size=32,
            n_epochs=1,
        )
        model.learn(total_timesteps=64)
        model.save(str(model_path))
        env.close()

        # Second: run eval on it
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "train.sb3_eval",
                "--model-path",
                str(model_path),
                "--episodes",
                "1",
                "--max-ticks",
                "200",
                "--log-level",
                "WARNING",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Eval script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_eval_report_json_created(self, tmp_path):
        """Eval should write a .eval.json report alongside the model."""
        model_path = tmp_path / "sb3_ppo.zip"
        report_path = tmp_path / "sb3_ppo.eval.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "train.sb3_eval",
                "--model-path",
                str(model_path),
                "--episodes",
                "2",
                "--quick-train-steps",
                "64",
                "--max-ticks",
                "200",
                "--log-level",
                "WARNING",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
            timeout=120,
        )
        assert result.returncode == 0

        import json

        assert report_path.exists(), f"Report JSON not found at {report_path}"
        with open(report_path) as f:
            data = json.load(f)
        assert "win_rate" in data
        assert "mean_reward" in data
        assert "mean_apm" in data
        assert "episodes" in data
        assert data["episodes"] == 2


# ─── 4. Non-SB3 tests (always run) ───────────────────────────


class TestEvalHelpers:
    """Test helper functions that don't require SB3."""

    def test_compute_apm_basic(self):
        from train.sb3_eval import _compute_apm

        # 1440 steps over 1440 ticks → 1440 APM (1 action per tick at 24tps)
        assert _compute_apm(1440, 1440) == 1440.0

    def test_compute_apm_zero_ticks(self):
        from train.sb3_eval import _compute_apm

        assert _compute_apm(10, 0) == 0.0

    def test_compute_apm_formula(self):
        from train.sb3_eval import _compute_apm

        steps = 100
        ticks = 500
        expected = steps * 1440.0 / ticks
        assert abs(_compute_apm(steps, ticks) - expected) < 1e-6

    def test_eval_config_defaults(self):
        from train.sb3_eval import EvalConfig

        cfg = EvalConfig()
        assert cfg.episodes == 10
        assert cfg.seed == 42
        assert cfg.max_ticks == 10000
        assert cfg.deterministic is True
        assert cfg.quick_train_steps == 1024

    def test_eval_result_summary(self):
        from train.sb3_eval import EvalResult

        result = EvalResult(
            episodes=10,
            wins=4,
            episode_rewards=[1.0, 2.0, 3.0, 4.0, -1.0, -2.0, 0.0, 1.0, 2.0, 3.0],
            episode_lengths=[100, 200, 150, 180, 90, 110, 200, 160, 140, 170],
            episode_apms=[30.0, 40.0, 35.0, 38.0, 25.0, 28.0, 50.0, 42.0, 33.0, 36.0],
        )
        summary = result.summary()
        assert summary["episodes"] == 10
        assert abs(summary["win_rate"] - 0.4) < 1e-9
        assert abs(summary["mean_reward"] - 1.3) < 1e-9
        assert abs(summary["mean_apm"] - 35.7) < 0.1
