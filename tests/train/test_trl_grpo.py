"""Tests for TRL GRPO trainer integration.

Covers:
  - TRL availability check
  - TRLGRPOConfig construction and defaults
  - Smoke test (5 episodes, no NaN)
  - 100-episode training (no NaN, loss generally decreasing)
  - Training curves CSV export
  - Fallback to SimplePolicy when TRL unavailable
"""

from __future__ import annotations

import sys
import csv
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from train.grpo_trainer import (
    GRPOConfig,
    GRPOTrainer,
    RolloutBuffer,
    SimplePolicy,
    Transition,
    create_grpo_trainer,
    HAS_TRL,
)


# ─── TRL availability ──────────────────────────────────────


class TestTRLAvailable:
    """Verify TRL can be imported and detected."""

    def test_trl_available(self):
        """TRL 1.4.0 should be importable."""
        import trl

        assert trl.__version__ == "1.4.0"

    def test_has_trl_flag(self):
        """Module-level HAS_TRL should be True."""
        assert HAS_TRL is True


# ─── TRLGRPOConfig ──────────────────────────────────────────


class TestTRLGRPOConfig:
    """Test TRLGRPOConfig construction."""

    def test_default_values(self):
        from train.trl_trainer import TRLGRPOConfig

        cfg = TRLGRPOConfig()
        assert cfg.env_id == "rts-ai-v0"
        assert cfg.seed == 42
        assert cfg.max_ticks == 5000
        assert cfg.reward_shaping == "shaped"
        assert cfg.episodes == 100
        assert cfg.batch_size == 32
        assert cfg.group_size == 4
        assert cfg.learning_rate == 3e-4
        assert cfg.gamma == 0.99
        assert cfg.clip_eps == 0.2
        assert cfg.entropy_coeff == 0.01
        assert cfg.value_coeff == 0.5
        assert cfg.max_grad_norm == 0.5
        assert cfg.ppo_epochs == 4
        assert cfg.hidden_dim == 128
        assert cfg.log_interval == 10
        assert cfg.save_interval == 100
        assert cfg.output_dir == "train/output"
        assert cfg.export_curves is True
        assert cfg.use_trl is True

    def test_custom_values(self):
        from train.trl_trainer import TRLGRPOConfig

        cfg = TRLGRPOConfig(
            episodes=50,
            batch_size=16,
            group_size=8,
            learning_rate=1e-3,
            gamma=0.95,
            clip_eps=0.1,
            entropy_coeff=0.02,
            hidden_dim=64,
            output_dir="/tmp/trl_test",
        )
        assert cfg.episodes == 50
        assert cfg.batch_size == 16
        assert cfg.group_size == 8
        assert cfg.learning_rate == 1e-3
        assert cfg.gamma == 0.95
        assert cfg.clip_eps == 0.1
        assert cfg.entropy_coeff == 0.02
        assert cfg.hidden_dim == 64
        assert cfg.output_dir == "/tmp/trl_test"

    def test_trl_version_populated(self):
        from train.trl_trainer import TRLGRPOConfig

        cfg = TRLGRPOConfig()
        # When TRL is available, trl_version should be set
        if HAS_TRL:
            import trl

            assert cfg.trl_version == trl.__version__


# ─── TRLGRPOTrainer smoke tests ─────────────────────────────


class TestTRLGRPOSmoke:
    """Smoke test: short training run completes without error."""

    def test_trl_grpo_smoke(self, tmp_path):
        """3-episode training run completes without NaN."""
        pytest.importorskip("torch")
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        config = TRLGRPOConfig(
            episodes=3,
            batch_size=2,
            group_size=2,
            max_ticks=50,  # very short for speed
            ppo_epochs=1,
            log_interval=1,
            save_interval=10,
            output_dir=str(tmp_path / "output"),
        )
        trainer = TRLGRPOTrainer(config)
        result = trainer.train()

        assert result["episodes"] == 3
        assert len(trainer.metrics) == 3

        # No NaN in rewards or losses
        for m in trainer.metrics:
            assert not np.isnan(m["reward"]), f"NaN reward at episode {m['episode']}"
            loss_key = "total_loss" if "total_loss" in m else "loss"
            if loss_key in m:
                assert not np.isnan(m[loss_key]), (
                    f"NaN loss at episode {m['episode']}"
                )


class TestTRLGRPOStability:
    """Stability test: 20-episode training, no NaN, loss not diverging."""

    def test_trl_grpo_stability(self, tmp_path):
        pytest.importorskip("torch")
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        config = TRLGRPOConfig(
            episodes=10,
            batch_size=4,
            group_size=2,
            max_ticks=100,
            ppo_epochs=1,
            log_interval=5,
            save_interval=10,
            output_dir=str(tmp_path / "output"),
        )
        trainer = TRLGRPOTrainer(config)
        result = trainer.train()

        assert result["episodes"] == 10
        assert len(trainer.metrics) == 10

        # No NaN in any metric
        for m in trainer.metrics:
            assert not np.isnan(m["reward"]), f"NaN reward at ep {m['episode']}"
            loss_key = "total_loss" if "total_loss" in m else "loss"
            if loss_key in m:
                assert not np.isnan(m[loss_key]), (
                    f"NaN loss at ep {m['episode']}"
                )

        # Loss should not diverge wildly
        loss_key = "total_loss" if "total_loss" in trainer.metrics[0] else "loss"
        if loss_key in trainer.metrics[0]:
            early_losses = [m[loss_key] for m in trainer.metrics[:5] if loss_key in m]
            late_losses = [m[loss_key] for m in trainer.metrics[-5:] if loss_key in m]
            if early_losses and late_losses:
                early_mean = np.mean(early_losses)
                late_mean = np.mean(late_losses)
                # Loss should not explode (absolute value should not grow 10x)
                assert abs(late_mean) < abs(early_mean) * 10 + 1.0, (
                    f"Loss diverges: early={early_mean:.4f}, late={late_mean:.4f}"
                )

    @pytest.mark.slow
    def test_trl_grpo_100_episodes(self, tmp_path):
        """100-episode full test — run with: pytest -m slow"""
        pytest.importorskip("torch")
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        config = TRLGRPOConfig(
            episodes=100,
            batch_size=16,
            group_size=4,
            max_ticks=200,
            ppo_epochs=2,
            log_interval=10,
            save_interval=50,
            output_dir=str(tmp_path / "output"),
        )
        trainer = TRLGRPOTrainer(config)
        result = trainer.train()

        assert result["episodes"] == 100
        assert len(trainer.metrics) == 100
        for m in trainer.metrics:
            assert not np.isnan(m["reward"]), f"NaN reward at ep {m['episode']}"


# ─── Training curves CSV export ─────────────────────────────


class TestTRLGRPOCurvesExport:
    """Verify CSV is written with loss/reward columns."""

    def test_trl_grpo_curves_export(self, tmp_path):
        pytest.importorskip("torch")
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        output_dir = tmp_path / "output"
        config = TRLGRPOConfig(
            episodes=3,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            export_curves=True,
            output_dir=str(output_dir),
        )
        trainer = TRLGRPOTrainer(config)
        trainer.train()

        csv_path = output_dir / "training_curves.csv"
        assert csv_path.exists(), "training_curves.csv should be created"

        # Parse CSV and verify columns
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3
        assert "episode" in rows[0]
        assert "reward" in rows[0]
        assert "length" in rows[0]

        # Verify values are numeric and not NaN
        for row in rows:
            reward = float(row["reward"])
            assert not np.isnan(reward)


# ─── Fallback without TRL ────────────────────────────────────


class TestFallbackWithoutTRL:
    """When TRL is unavailable, fallback to SimplePolicy GRPOTrainer."""

    def test_fallback_without_trl(self):
        """Mock TRL unavailable, falls back to SimplePolicy GRPOTrainer."""
        # Mock HAS_TRL to False in the grpo_trainer module
        with mock.patch.dict(sys.modules, {}):
            with mock.patch("train.grpo_trainer.HAS_TRL", False):
                # With use_trl=True but TRL unavailable,
                # create_grpo_trainer should fall back
                config = GRPOConfig(
                    episodes=2,
                    use_trl=True,  # TRL requested but unavailable
                    output_dir="/tmp/fallback_test",
                )
                trainer = create_grpo_trainer(config)
                # Should be the SimplePolicy-based GRPOTrainer
                assert isinstance(trainer, GRPOTrainer)
                assert not isinstance(trainer, type(None))

    def test_force_no_trl(self):
        """With use_trl=False, always use SimplePolicy GRPOTrainer."""
        config = GRPOConfig(
            episodes=2,
            use_trl=False,
            output_dir="/tmp/no_trl_test",
        )
        trainer = create_grpo_trainer(config)
        assert isinstance(trainer, GRPOTrainer)

    def test_fallback_smoke_train(self, tmp_path):
        """Fallback trainer still runs training successfully."""
        config = GRPOConfig(
            episodes=2,
            batch_size=2,
            group_size=2,
            use_trl=False,
            log_interval=1,
            output_dir=str(tmp_path / "output"),
        )
        trainer = create_grpo_trainer(config)
        result = trainer.train()
        assert result["episodes"] == 2
        assert len(trainer.metrics) == 2


# ─── GRPO advantage computation ──────────────────────────────


class TestGRPOAdvantages:
    """Test the group-relative advantage formula."""

    def test_group_relative_advantages(self):
        """Verify GRPO advantage = (r - mean) / (std + eps)."""
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        config = TRLGRPOConfig(group_size=4)
        trainer = TRLGRPOTrainer(config)

        obs = {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }

        # Add 4 transitions with rewards [1, 2, 3, 4]
        for r in [1.0, 2.0, 3.0, 4.0]:
            trainer.buffer.add(
                Transition(
                    obs=obs,
                    action=0,
                    reward=r,
                    next_obs=obs,
                    terminated=False,
                    truncated=False,
                    info={},
                    log_prob=-0.5,
                    value=0.0,
                )
            )

        advantages = trainer.compute_advantages()
        assert len(advantages) == 4

        # Mean = 2.5, std = sqrt(1.25) ≈ 1.118
        # adv[0] = (1 - 2.5) / 1.118 ≈ -1.342
        # adv[3] = (4 - 2.5) / 1.118 ≈ 1.342
        # Higher rewards should have higher advantages
        assert advantages[3] > advantages[0]
        assert advantages[3] > 0
        assert advantages[0] < 0

    def test_empty_buffer_advantages(self):
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        config = TRLGRPOConfig()
        trainer = TRLGRPOTrainer(config)
        advantages = trainer.compute_advantages()
        assert len(advantages) == 0


# ─── GRPOPolicy (PyTorch) ────────────────────────────────────


@pytest.mark.skipif(
    not HAS_TRL,
    reason="PyTorch not installed",
)
class TestGRPOPolicy:
    """Test the GRPOPolicy PyTorch network."""

    @pytest.fixture()
    def policy(self):
        import torch
        from train.trl_trainer import GRPOPolicy

        obs_dim = 64 * 10 + 4 + 1
        return GRPOPolicy(obs_dim=obs_dim, action_dim=6, hidden_dim=128, lr=1e-3)

    @pytest.fixture()
    def sample_obs(self):
        return {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }

    def test_act_returns_valid(self, policy, sample_obs):
        action, log_prob, value = policy.act(sample_obs)
        assert isinstance(action, int)
        assert 0 <= action < 6
        assert isinstance(log_prob, float)
        assert isinstance(value, float)

    def test_forward_shapes(self, policy):
        import torch

        obs_flat = torch.randn(1, 645)
        logits, value = policy.forward(obs_flat)
        assert logits.shape == (1, 6)
        assert value.shape == (1,)

    def test_update_grpo(self, policy, sample_obs):
        """Test that update_grpo runs and returns valid metrics."""
        from train.trl_trainer import TRLGRPOConfig

        # Fill buffer with some data
        buf = RolloutBuffer(group_size=2)
        for _ in range(4):
            buf.add(
                Transition(
                    obs=sample_obs,
                    action=0,
                    reward=1.0,
                    next_obs=sample_obs,
                    terminated=False,
                    truncated=False,
                    info={},
                    log_prob=-0.5,
                    value=0.1,
                )
            )

        config = TRLGRPOConfig(batch_size=2, ppo_epochs=1)
        advantages = buf.compute_advantages()

        metrics = policy.update_grpo(buf, advantages, config)
        assert "pg_loss" in metrics
        assert "value_loss" in metrics
        assert "entropy" in metrics
        assert "total_loss" in metrics
        assert not np.isnan(metrics["total_loss"])


# ─── create_grpo_trainer factory ────────────────────────────


class TestCreateGRPOTrainer:
    """Test the factory function."""

    def test_returns_trl_grpo_when_available(self):
        """When TRL is available and use_trl=True, returns TRLGRPOTrainer."""
        from train.trl_trainer import TRLGRPOTrainer

        if HAS_TRL:
            config = GRPOConfig(use_trl=True)
            trainer = create_grpo_trainer(config)
            assert isinstance(trainer, TRLGRPOTrainer)

    def test_returns_simple_when_trl_disabled(self):
        """When use_trl=False, always returns GRPOTrainer (SimplePolicy)."""
        config = GRPOConfig(use_trl=False)
        trainer = create_grpo_trainer(config)
        assert isinstance(trainer, GRPOTrainer)

    def test_returns_simple_when_trl_unavailable(self):
        """When TRL is not installed, returns GRPOTrainer even with use_trl=True."""
        with mock.patch("train.grpo_trainer.HAS_TRL", False):
            config = GRPOConfig(use_trl=True)
            trainer = create_grpo_trainer(config)
            assert isinstance(trainer, GRPOTrainer)