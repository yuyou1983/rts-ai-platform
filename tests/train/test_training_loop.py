"""Tests for T3+T4: Training closed loop — RolloutWorker integration,
League registration, and PromotionGate evaluation.

Covers:
  - train_with_worker smoke (3 episodes, no NaN)
  - train_and_register: train → register with League → League has version
  - promotion_flow: train → register → PromotionGate evaluates (mocked games)
  - worker_vs_sequential: worker and sequential produce similar buffer sizes
"""

from __future__ import annotations

import sys
from typing import Any
from unittest import mock

import numpy as np
import pytest

from train.grpo_trainer import RolloutBuffer, SimplePolicy, Transition

try:
    from train.trl_trainer import HAS_TORCH, TRLGRPOConfig, TRLGRPOTrainer
except ImportError:
    HAS_TORCH = False
    TRLGRPOConfig = None  # type: ignore[assignment,misc]
    TRLGRPOTrainer = None  # type: ignore[assignment,misc]

try:
    from harness.league import AgentType, AgentVersion, League
except ImportError:
    League = None  # type: ignore[assignment,misc]
    AgentVersion = None  # type: ignore[assignment,misc]
    AgentType = None  # type: ignore[assignment,misc]

try:
    from harness.promotion import PromotionConfig, PromotionResult, PromotionGate
except ImportError:
    PromotionGate = None  # type: ignore[assignment,misc]
    PromotionConfig = None  # type: ignore[assignment,misc]


# ─── Mock Environment (module-level for pickle) ────────────────


class _SimpleSpace:
    """Minimal action_space stand-in with .n attribute."""

    def __init__(self, n: int):
        self.n = n


class _ShapeSpace:
    def __init__(self, shape):
        self.shape = shape


class _SimpleObsSpace:
    """Minimal observation_space stand-in with .spaces dict."""

    def __init__(self):
        self.spaces = {
            "entities": _ShapeSpace((64, 10)),
            "resources": _ShapeSpace((4,)),
            "tick": _ShapeSpace((1,)),
        }

    def __getitem__(self, key: str):
        return self.spaces[key]


class MockEnv:
    """Minimal Gymnasium-like env: constant obs, done after `ep_length` steps."""

    def __init__(self, ep_length: int = 3, n_actions: int = 6):
        self.ep_length = ep_length
        self.n_actions = n_actions
        self._step = 0
        self.action_space = _SimpleSpace(n_actions)
        self.observation_space = _SimpleObsSpace()

    def reset(self, seed: int | None = None, **kwargs):
        self._step = 0
        obs = self._make_obs()
        info: dict[str, Any] = {}
        return obs, info

    def step(self, action: int):
        self._step += 1
        obs = self._make_obs()
        reward = 1.0
        terminated = self._step >= self.ep_length
        truncated = False
        info: dict[str, Any] = {"winner": 1 if terminated else 0}
        return obs, reward, terminated, truncated, info

    def close(self):
        pass

    @staticmethod
    def _make_obs() -> dict[str, np.ndarray]:
        return {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }


def _make_mock_env() -> MockEnv:
    """Pickleable env factory."""
    return MockEnv(ep_length=3, n_actions=6)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def short_config(tmp_path):
    """Minimal config for fast tests."""
    if TRLGRPOConfig is None:
        pytest.skip("TRLGRPOConfig not available")
    return TRLGRPOConfig(
        episodes=3,
        batch_size=2,
        group_size=2,
        max_ticks=50,
        ppo_epochs=1,
        log_interval=1,
        save_interval=100,
        output_dir=str(tmp_path / "output"),
        use_worker=False,
    )


# ─── test_train_with_worker_smoke ───────────────────────────────


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestTrainWithWorker:
    """Smoke-test training with the RolloutWorker."""

    def test_train_with_worker_smoke(self, tmp_path):
        """3 episodes with worker, no NaN."""
        from train.rollout_worker import RolloutWorker

        config = TRLGRPOConfig(
            episodes=3,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "output"),
            use_worker=True,
        )
        trainer = TRLGRPOTrainer(
            config,
            env_factory=_make_mock_env,
        )

        # Create a worker manually to control params
        worker = RolloutWorker(
            num_workers=2,
            env_factory=_make_mock_env,
            max_steps=50,
            policy_type="grpo",
        )
        result = trainer.train_with_worker(worker=worker)

        assert result["episodes"] == 3
        assert result["total_time"] > 0
        assert result["games_per_hour"] >= 0

        # No NaN in metrics
        for m in trainer.metrics:
            assert not np.isnan(m["reward"]), f"NaN reward at ep {m['episode']}"
            loss_key = "total_loss" if "total_loss" in m else "loss"
            if loss_key in m:
                assert not np.isnan(m[loss_key]), (
                    f"NaN loss at ep {m['episode']}"
                )

    def test_worker_vs_sequential_buffer_size(self, tmp_path):
        """Worker and sequential produce same number of episodes for same config."""
        config_seq = TRLGRPOConfig(
            episodes=4,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "seq_output"),
            use_worker=False,
        )
        trainer_seq = TRLGRPOTrainer(config_seq, env_factory=_make_mock_env)
        result_seq = trainer_seq.train()

        config_w = TRLGRPOConfig(
            episodes=4,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "worker_output"),
            use_worker=True,
        )
        from train.rollout_worker import RolloutWorker

        worker = RolloutWorker(
            num_workers=2,
            env_factory=_make_mock_env,
            max_steps=50,
            policy_type="grpo",
        )
        trainer_w = TRLGRPOTrainer(config_w, env_factory=_make_mock_env)
        result_w = trainer_w.train_with_worker(worker=worker)

        # Both should produce same number of episodes
        assert result_seq["episodes"] == result_w["episodes"]


# ─── test_train_and_register ────────────────────────────────────


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestTrainAndRegister:
    """Train → register with League → League has version."""

    def test_train_and_register(self, tmp_path):
        """Train 5 eps → register with League → League has the version."""
        config = TRLGRPOConfig(
            episodes=5,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "output"),
            use_worker=False,
        )
        trainer = TRLGRPOTrainer(config, env_factory=_make_mock_env)

        league = League()

        result = trainer.train_and_promote(
            league=league,
            version_name="grpo-test-v0",
        )

        # The new version should be registered in the league
        assert "grpo-test-v0" in league.pool
        version = league.pool.get_by_name("grpo-test-v0")
        assert version is not None
        assert version.type == AgentType.GRPO

        # Since there's no champion, it should be auto-promoted
        assert result["promoted"] is True
        assert result["version"] == "grpo-test-v0"
        assert "No champion exists" in result["reason"]

    def test_train_and_register_with_existing_champion(self, tmp_path):
        """When League already has a champion, promotion evaluation runs."""
        config = TRLGRPOConfig(
            episodes=3,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "output"),
            use_worker=False,
        )
        trainer = TRLGRPOTrainer(config, env_factory=_make_mock_env)

        league = League()
        champion = AgentVersion(
            "script-champion-v1", AgentType.SCRIPT, creation_tick=0
        )
        league.register(champion)

        # Mock the PromotionGate.evaluate_sync to avoid running actual games
        mock_result = PromotionResult(
            promoted=False,
            challenger="grpo-challenger",
            champion="script-champion-v1",
            games_played=20,
            wins=8,
            losses=12,
            draws=0,
            win_rate=0.40,
            ci_lower=0.22,
            ci_upper=0.60,
            passed=False,
            reason="Promotion FAILED: win_rate=0.400, CI=[0.220, 0.600] < threshold=0.500",
        )

        with mock.patch.object(
            PromotionGate, "evaluate_sync", return_value=mock_result
        ):
            result = trainer.train_and_promote(
                league=league,
                version_name="grpo-challenger",
            )

        # The challenger should be registered in the league BEFORE rollback
        # After rollback, PromotionGate.deregisters the challenger
        # So the challenger is no longer in the pool
        assert result["promoted"] is False
        assert result["version"] == "grpo-challenger"
        assert result["games_played"] == 20
        # Champion should still be in the league
        assert "script-champion-v1" in league.pool


# ─── test_promotion_flow ────────────────────────────────────────


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestPromotionFlow:
    """End-to-end: train → register → PromotionGate evaluates (mocked)."""

    def test_promotion_flow_promoted(self, tmp_path):
        """When the gate passes, version is promoted."""
        config = TRLGRPOConfig(
            episodes=3,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "output"),
            use_worker=False,
        )
        trainer = TRLGRPOTrainer(config, env_factory=_make_mock_env)

        league = League()
        champion = AgentVersion("champ-v1", AgentType.SCRIPT, creation_tick=0)
        league.register(champion)

        # Mock a successful promotion result
        mock_result = PromotionResult(
            promoted=True,
            challenger="grpo-promoted-v1",
            champion="champ-v1",
            games_played=30,
            wins=20,
            losses=8,
            draws=2,
            win_rate=0.667,
            ci_lower=0.51,
            ci_upper=0.80,
            passed=True,
            reason="Promotion PASSED: win_rate=0.667, CI=[0.510, 0.800] ≥ threshold=0.500",
        )

        with mock.patch.object(
            PromotionGate, "evaluate_sync", return_value=mock_result
        ):
            result = trainer.train_and_promote(
                league=league,
                version_name="grpo-promoted-v1",
            )

        assert result["promoted"] is True
        assert result["win_rate"] == pytest.approx(0.667)
        assert result["version"] == "grpo-promoted-v1"

    def test_promotion_flow_rejected(self, tmp_path):
        """When the gate fails, version is rolled back."""
        config = TRLGRPOConfig(
            episodes=3,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "output"),
            use_worker=False,
        )
        trainer = TRLGRPOTrainer(config, env_factory=_make_mock_env)

        league = League()
        champion = AgentVersion("champ-v2", AgentType.SCRIPT, creation_tick=0)
        league.register(champion)

        mock_result = PromotionResult(
            promoted=False,
            challenger="grpo-rejected-v1",
            champion="champ-v2",
            games_played=25,
            wins=8,
            losses=15,
            draws=2,
            win_rate=0.32,
            ci_lower=0.17,
            ci_upper=0.51,
            passed=False,
            reason="Promotion FAILED",
        )

        with mock.patch.object(
            PromotionGate, "evaluate_sync", return_value=mock_result
        ):
            result = trainer.train_and_promote(
                league=league,
                version_name="grpo-rejected-v1",
            )

        assert result["promoted"] is False
        assert result["version"] == "grpo-rejected-v1"
        # Champion should still be in the league
        assert "champ-v2" in league.pool


# ─── Config flag ────────────────────────────────────────────────


class TestUseWorkerFlag:
    """Verify use_worker config flag works."""

    def test_default_is_false(self):
        cfg = TRLGRPOConfig()
        assert cfg.use_worker is False

    def test_can_set_true(self):
        cfg = TRLGRPOConfig(use_worker=True)
        assert cfg.use_worker is True

    def test_train_and_promote_respects_flag(self, tmp_path):
        """When use_worker=False, train() is used; when True, train_with_worker()."""
        config = TRLGRPOConfig(
            episodes=2,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            output_dir=str(tmp_path / "output"),
            use_worker=False,
        )
        trainer = TRLGRPOTrainer(config, env_factory=_make_mock_env)

        # Patch both methods to track which is called
        with mock.patch.object(
            trainer, "train", return_value={"total_time": 0.1, "episodes": 2}
        ) as mock_train, mock.patch.object(
            trainer, "train_with_worker", return_value={"total_time": 0.1, "episodes": 2}
        ) as mock_worker:
            league = League()
            trainer.train_and_promote(league=league, version_name="test-v0")
            mock_train.assert_called_once()
            mock_worker.assert_not_called()

        # Now with use_worker=True
        config2 = TRLGRPOConfig(
            episodes=2,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            output_dir=str(tmp_path / "output2"),
            use_worker=True,
        )
        trainer2 = TRLGRPOTrainer(config2, env_factory=_make_mock_env)

        with mock.patch.object(
            trainer2, "train", return_value={"total_time": 0.1, "episodes": 2}
        ), mock.patch.object(
            trainer2, "train_with_worker", return_value={"total_time": 0.1, "episodes": 2}
        ) as mock_worker2:
            league2 = League()
            trainer2.train_and_promote(league=league2, version_name="test-v1")
            mock_worker2.assert_called_once()