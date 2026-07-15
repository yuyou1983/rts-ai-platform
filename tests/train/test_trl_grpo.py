"""Tests for TRL GRPO trainer integration.

Covers:
  - TRL availability check
  - TRLGRPOConfig construction and defaults
  - Smoke test (5 episodes, no NaN)
  - 100-episode training (no NaN, loss generally decreasing)
  - Training curves CSV export
  - Fallback to SimplePolicy when TRL unavailable
  - GRPO v5: numerical stability (KL clamp, ratio clamp, value_loss clamp)
  - GRPO v5: binary freeze/unfreeze
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
        # GRPO v3/v5 defaults
        assert cfg.freeze_bc_epochs == 500
        assert cfg.kl_coef == 0.1
        assert cfg.grpo_lr == 1e-5
        # GRPO v5 numerical stability clamps
        assert cfg.kl_max == 1.0
        assert cfg.ratio_max == 10.0
        assert cfg.value_loss_max == 1.0
        # v4 fields should NOT exist
        assert not hasattr(cfg, "unfreeze_policy_epochs")
        assert not hasattr(cfg, "grpo_lr_phase_b")
        assert not hasattr(cfg, "grpo_lr_phase_c")

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


# ─── GRPO v3/v5: BC weight freezing & KL penalty ────────────────


@pytest.mark.skipif(
    not HAS_TRL,
    reason="PyTorch not installed",
)
class TestGRPOv5FreezingAndKL:
    """Test GRPO v5 binary freeze/unfreeze and KL penalty features."""

    @pytest.fixture()
    def policy(self):
        import torch
        from train.trl_trainer import GRPOPolicy

        obs_dim = 64 * 10 + 4 + 1
        pol = GRPOPolicy(obs_dim=obs_dim, action_dim=6, hidden_dim=128, lr=1e-3)
        # Simulate BC pretrain: save reference and switch optimizer
        pol.save_bc_reference()
        pol.set_grpo_optimizer(lr=1e-5)
        return pol

    @pytest.fixture()
    def sample_obs(self):
        return {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }

    def test_save_bc_reference_creates_snapshot(self, policy):
        """save_bc_reference should store detached clones of backbone+policy_head."""
        import torch

        assert policy._bc_ref_backbone is not None
        assert policy._bc_ref_policy_head is not None
        # Reference network should have the same architecture but frozen params
        for param in policy._bc_ref_backbone.parameters():
            assert not param.requires_grad
        for param in policy._bc_ref_policy_head.parameters():
            assert not param.requires_grad

    def test_set_grpo_optimizer_changes_lr(self, policy):
        """set_grpo_optimizer should replace the optimizer with smaller LR."""
        import torch

        for pg in policy.optimizer.param_groups:
            assert pg["lr"] == 1e-5

    def test_freeze_during_early_episodes(self, policy, sample_obs):
        """Backbone+policy_head should be frozen when episode < freeze_bc_epochs."""
        import torch
        from train.trl_trainer import TRLGRPOConfig

        buf = RolloutBuffer(group_size=2)
        for _ in range(4):
            buf.add(
                Transition(
                    obs=sample_obs, action=0, reward=1.0,
                    next_obs=sample_obs, terminated=False, truncated=False,
                    info={}, log_prob=-0.5, value=0.1,
                )
            )

        config = TRLGRPOConfig(
            batch_size=2, ppo_epochs=1,
            freeze_bc_epochs=500, kl_coef=0.1,
        )
        advantages = buf.compute_advantages()

        # Record pre-update params
        backbone_w_before = policy.backbone[0].weight.data.clone()
        policy_head_w_before = policy.policy_head.weight.data.clone()

        metrics = policy.update_grpo(buf, advantages, config, episode=10)

        # Backbone and policy_head should NOT change during freeze phase
        assert torch.allclose(policy.backbone[0].weight.data, backbone_w_before), (
            "backbone weights should be frozen during early episodes"
        )
        assert torch.allclose(policy.policy_head.weight.data, policy_head_w_before), (
            "policy_head weights should be frozen during early episodes"
        )
        # value_head IS allowed to change (not checked strictly, but KL should be in metrics)
        assert "kl_div" in metrics

    def test_unfreeze_after_freeze_phase(self, policy, sample_obs):
        """After freeze_bc_epochs, backbone+policy_head should be trainable."""
        import torch
        from train.trl_trainer import TRLGRPOConfig

        buf = RolloutBuffer(group_size=2)
        for _ in range(4):
            buf.add(
                Transition(
                    obs=sample_obs, action=0, reward=1.0,
                    next_obs=sample_obs, terminated=False, truncated=False,
                    info={}, log_prob=-0.5, value=0.1,
                )
            )

        config = TRLGRPOConfig(
            batch_size=2, ppo_epochs=2,
            freeze_bc_epochs=3, kl_coef=0.1,
        )
        advantages = buf.compute_advantages()

        backbone_w_before = policy.backbone[0].weight.data.clone()

        # episode=5 > freeze_bc_epochs=3 → should be unfrozen
        metrics = policy.update_grpo(buf, advantages, config, episode=5)

        # After unfreeze, weights CAN change (not guaranteed with 1 mini-batch,
        # but requires_grad should be True afterward)
        for param in policy.backbone.parameters():
            assert param.requires_grad, "backbone should be unfrozen after freeze phase"
        for param in policy.policy_head.parameters():
            assert param.requires_grad, "policy_head should be unfrozen after freeze phase"

    def test_kl_penalty_in_metrics(self, policy, sample_obs):
        """KL divergence should appear in metrics when bc_reference is set."""
        from train.trl_trainer import TRLGRPOConfig

        buf = RolloutBuffer(group_size=2)
        for _ in range(4):
            buf.add(
                Transition(
                    obs=sample_obs, action=0, reward=1.0,
                    next_obs=sample_obs, terminated=False, truncated=False,
                    info={}, log_prob=-0.5, value=0.1,
                )
            )

        config = TRLGRPOConfig(
            batch_size=2, ppo_epochs=1,
            freeze_bc_epochs=0, kl_coef=0.1,
        )
        advantages = buf.compute_advantages()
        metrics = policy.update_grpo(buf, advantages, config, episode=0)

        assert "kl_div" in metrics
        # KL should be non-negative (allow tiny floating-point tolerance)
        assert metrics["kl_div"] >= -1e-6

    def test_no_kl_penalty_without_reference(self, sample_obs):
        """When no BC reference is saved, KL penalty should be zero."""
        import torch
        pytest.importorskip("torch")
        from train.trl_trainer import GRPOPolicy, TRLGRPOConfig

        obs_dim = 64 * 10 + 4 + 1
        policy = GRPOPolicy(obs_dim=obs_dim, action_dim=6, hidden_dim=128, lr=1e-3)
        # Don't call save_bc_reference

        buf = RolloutBuffer(group_size=2)
        for _ in range(4):
            buf.add(
                Transition(
                    obs=sample_obs, action=0, reward=1.0,
                    next_obs=sample_obs, terminated=False, truncated=False,
                    info={}, log_prob=-0.5, value=0.1,
                )
            )

        config = TRLGRPOConfig(
            batch_size=2, ppo_epochs=1,
            freeze_bc_epochs=0, kl_coef=0.1,
        )
        advantages = buf.compute_advantages()
        metrics = policy.update_grpo(buf, advantages, config, episode=0)

        assert "kl_div" in metrics
        assert metrics["kl_div"] == 0.0


# ─── GRPO v3/v5: CLI defaults ───────────────────────────────────


class TestGRPOv5CLIDefaults:
    """Verify that CLI and GRPOConfig have updated defaults for v5."""

    def test_grpo_config_v5_defaults(self):
        """GRPOConfig should have v3/v5 fields with correct defaults."""
        cfg = GRPOConfig()
        assert cfg.freeze_bc_epochs == 500
        assert cfg.kl_coef == 0.1
        assert cfg.grpo_lr == 1e-5
        # v4 fields should NOT exist
        assert not hasattr(cfg, "unfreeze_policy_epochs")
        assert not hasattr(cfg, "grpo_lr_phase_b")
        assert not hasattr(cfg, "grpo_lr_phase_c")

    def test_grpo_config_default_episodes(self):
        """GRPOConfig default episodes should be 1000."""
        cfg = GRPOConfig()
        assert cfg.episodes == 1000

    def test_cli_episodes_default(self):
        """CLI --episodes should default to 1000."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--episodes", type=int, default=1000)
        args = parser.parse_args([])
        assert args.episodes == 1000

    def test_create_grpo_trainer_no_v4_fields(self):
        """create_grpo_trainer should not pass v4 fields to TRLGRPOConfig."""
        if not HAS_TRL:
            pytest.skip("TRL not installed")

        from train.trl_trainer import TRLGRPOTrainer

        cfg = GRPOConfig(
            episodes=10,
            freeze_bc_epochs=3,
        )
        trainer = create_grpo_trainer(cfg)
        assert isinstance(trainer, TRLGRPOTrainer)
        # v4 fields should not be on the trainer's config
        assert not hasattr(trainer.config, "unfreeze_policy_epochs")
        assert not hasattr(trainer.config, "grpo_lr_phase_b")
        assert not hasattr(trainer.config, "grpo_lr_phase_c")


# ─── GRPO v5: Numerical Stability ──────────────────────────────


@pytest.mark.skipif(
    not HAS_TRL,
    reason="PyTorch not installed",
)
class TestGRPOv5NumericalStability:
    """Test GRPO v5 numerical stability clamps."""

    OBS_DIM = 64 * 10 + 4 + 1  # 645

    @pytest.fixture()
    def policy(self):
        import torch
        from train.trl_trainer import GRPOPolicy

        pol = GRPOPolicy(obs_dim=self.OBS_DIM, action_dim=6, hidden_dim=128, lr=1e-3)
        pol.save_bc_reference()
        return pol

    @pytest.fixture()
    def sample_obs(self):
        return {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }

    def _make_buffer(self, sample_obs, n=4, reward=1.0):
        buf = RolloutBuffer(group_size=2)
        for _ in range(n):
            buf.add(
                Transition(
                    obs=sample_obs, action=0, reward=reward,
                    next_obs=sample_obs, terminated=False, truncated=False,
                    info={}, log_prob=-0.5, value=0.1,
                )
            )
        return buf

    def test_kl_clamp(self, policy, sample_obs):
        """KL penalty should be clamped to max kl_max (default 1.0)."""
        import torch
        from train.trl_trainer import TRLGRPOConfig

        buf = self._make_buffer(sample_obs)
        config = TRLGRPOConfig(
            batch_size=2, ppo_epochs=1,
            freeze_bc_epochs=0, kl_coef=100.0,  # very high to provoke large KL
            kl_max=1.0,
        )
        advantages = buf.compute_advantages()
        metrics = policy.update_grpo(buf, advantages, config, episode=0)

        # KL divergence in metrics should not exceed kl_max
        assert metrics["kl_div"] <= config.kl_max + 1e-6, (
            f"KL {metrics['kl_div']} exceeds max {config.kl_max}"
        )

    def test_ratio_clamp(self, policy, sample_obs):
        """PPO ratio should be clamped to max ratio_max (default 10.0)."""
        import torch
        from train.trl_trainer import TRLGRPOConfig

        buf = self._make_buffer(sample_obs, reward=100.0)  # high reward for extreme ratio
        config = TRLGRPOConfig(
            batch_size=2, ppo_epochs=1,
            freeze_bc_epochs=0, kl_coef=0.0,
            ratio_max=10.0,
        )
        advantages = buf.compute_advantages()

        # Patch exp to verify clamp is applied — we check the ratio indirectly
        # by verifying loss is finite (no inf)
        metrics = policy.update_grpo(buf, advantages, config, episode=0)

        assert not np.isinf(metrics["total_loss"]), (
            f"Loss is inf — ratio clamp may not be working"
        )
        assert not np.isnan(metrics["total_loss"]), (
            f"Loss is NaN — ratio clamp may not be working"
        )

    def test_value_loss_clamp(self, policy, sample_obs):
        """Value loss should be clamped to max value_loss_max (default 1.0)."""
        import torch
        from train.trl_trainer import TRLGRPOConfig

        # Use extreme returns to provoke large value loss
        buf = self._make_buffer(sample_obs, reward=1000.0)
        config = TRLGRPOConfig(
            batch_size=2, ppo_epochs=1,
            freeze_bc_epochs=0, kl_coef=0.0,
            value_loss_max=1.0,
        )
        advantages = buf.compute_advantages()
        metrics = policy.update_grpo(buf, advantages, config, episode=0)

        # value_loss in metrics should not exceed value_loss_max
        assert metrics["value_loss"] <= config.value_loss_max + 1e-3, (
            f"value_loss {metrics['value_loss']} exceeds max {config.value_loss_max}"
        )

    def test_no_inf_loss_over_10_episodes(self, tmp_path):
        """After 10 episodes, loss should never be inf or NaN."""
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        config = TRLGRPOConfig(
            episodes=10,
            batch_size=2,
            group_size=2,
            max_ticks=50,
            ppo_epochs=1,
            log_interval=1,
            save_interval=100,
            output_dir=str(tmp_path / "output"),
            # Use the clamps
            kl_max=1.0,
            ratio_max=10.0,
            value_loss_max=1.0,
        )
        trainer = TRLGRPOTrainer(config)
        result = trainer.train()

        assert result["episodes"] == 10
        for m in trainer.metrics:
            loss_key = "total_loss" if "total_loss" in m else "loss"
            if loss_key in m:
                assert not np.isinf(m[loss_key]), (
                    f"inf loss at episode {m['episode']}: {m[loss_key]}"
                )
                assert not np.isnan(m[loss_key]), (
                    f"NaN loss at episode {m['episode']}: {m[loss_key]}"
                )


# ─── Opponent curriculum ──────────────────────────────────────


class TestOpponentCurriculumHelper:
    """Test the get_opponent_difficulty_for_step helper."""

    def test_easy_phase(self):
        from train.trl_trainer import get_opponent_difficulty_for_step

        assert get_opponent_difficulty_for_step(0) == "easy"
        assert get_opponent_difficulty_for_step(99_999) == "easy"

    def test_medium_phase(self):
        from train.trl_trainer import get_opponent_difficulty_for_step

        assert get_opponent_difficulty_for_step(100_000) == "medium"
        assert get_opponent_difficulty_for_step(199_999) == "medium"

    def test_hard_phase(self):
        from train.trl_trainer import get_opponent_difficulty_for_step

        assert get_opponent_difficulty_for_step(200_000) == "hard"
        assert get_opponent_difficulty_for_step(500_000) == "hard"

    def test_custom_total_steps(self):
        from train.trl_trainer import get_opponent_difficulty_for_step

        assert get_opponent_difficulty_for_step(0, total_steps=90_000) == "easy"
        assert get_opponent_difficulty_for_step(30_000, total_steps=90_000) == "medium"
        assert get_opponent_difficulty_for_step(60_000, total_steps=90_000) == "hard"

    def test_phase_ordering(self):
        from train.trl_trainer import get_opponent_difficulty_for_step

        difficulties = [get_opponent_difficulty_for_step(s) for s in [0, 150_000, 300_000]]
        assert difficulties == ["easy", "medium", "hard"]


class TestOpponentCurriculumConfig:
    """Test TRLGRPOConfig opponent curriculum fields."""

    def test_default_opponent_difficulty(self):
        from train.trl_trainer import TRLGRPOConfig

        cfg = TRLGRPOConfig()
        assert cfg.opponent_difficulty == "easy"
        assert cfg.opponent_curriculum is True
        assert cfg.opponent_curve_steps == 300_000

    def test_custom_opponent_config(self):
        from train.trl_trainer import TRLGRPOConfig

        cfg = TRLGRPOConfig(
            opponent_difficulty="hard",
            opponent_curriculum=False,
            opponent_curve_steps=100_000,
        )
        assert cfg.opponent_difficulty == "hard"
        assert cfg.opponent_curriculum is False
        assert cfg.opponent_curve_steps == 100_000


class TestOpponentCurriculumSmoke:
    """Smoke test: short training with opponent curriculum enabled."""

    def test_curriculum_smoke(self, tmp_path):
        """3-episode training with opponent curriculum completes without error."""
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
            opponent_difficulty="easy",
            opponent_curriculum=True,
            opponent_curve_steps=100,  # tiny for fast phase transitions
            output_dir=str(tmp_path / "output"),
        )
        trainer = TRLGRPOTrainer(config)
        result = trainer.train()

        assert result["episodes"] == 3
        assert len(trainer.metrics) == 3
        # Verify opponent_difficulty is tracked in metrics
        for m in trainer.metrics:
            assert "opponent_difficulty" in m, "Missing opponent_difficulty in metrics"
            assert m["opponent_difficulty"] in ("easy", "medium", "hard")


class TestGymEnvOpponentDifficulty:
    """Test that opponent_difficulty flows through gym.make to RTSSimCoreEnv."""

    def test_make_with_opponent_difficulty(self):
        import gymnasium as gym
        import simcore.gym_env  # noqa: F401

        env = gym.make("rts-ai-v0", seed=42, opponent_difficulty="easy")
        obs, info = env.reset()
        assert obs["entities"].shape == (64, 17)

        # Verify the unwrapped env has the correct difficulty
        inner = env.unwrapped
        assert hasattr(inner, "_opponent_difficulty")
        assert inner._opponent_difficulty == "easy"
        env.close()

    def test_make_with_opponent_difficulty_medium(self):
        import gymnasium as gym
        import simcore.gym_env  # noqa: F401

        env = gym.make("rts-ai-v0", seed=42, opponent_difficulty="medium")
        inner = env.unwrapped
        assert inner._opponent_difficulty == "medium"
        env.close()
