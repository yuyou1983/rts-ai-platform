"""Tests for train/rl_trainer.py — RLTrainerConfig, RTSPolicy, and RLTrainer."""

from __future__ import annotations

import numpy as np
import pytest

from train.grpo_trainer import RolloutBuffer, SimplePolicy, Transition
from train.rl_trainer import HAS_TORCH, RLTrainer, RLTrainerConfig


# ─── RLTrainerConfig ──────────────────────────────────────────


class TestRLTrainerConfig:
    """Test RLTrainerConfig defaults and custom values."""

    def test_default_values(self):
        cfg = RLTrainerConfig()
        assert cfg.env_id == "rts-ai-v0"
        assert cfg.seed == 42
        assert cfg.max_ticks == 5000
        assert cfg.reward_shaping == "shaped"
        assert cfg.episodes == 100
        assert cfg.batch_size == 32
        assert cfg.learning_rate == 3e-4
        assert cfg.gamma == 0.99
        assert cfg.gae_lambda == 0.95
        assert cfg.clip_ratio == 0.2
        assert cfg.entropy_coeff == 0.01
        assert cfg.value_coeff == 0.5
        assert cfg.max_grad_norm == 0.5
        assert cfg.ppo_epochs == 4
        assert cfg.hidden_dim == 128
        assert cfg.log_interval == 10
        assert cfg.save_interval == 100
        assert cfg.output_dir == "train/output"

    def test_custom_values(self):
        cfg = RLTrainerConfig(
            env_id="custom-v1",
            seed=123,
            episodes=50,
            batch_size=16,
            learning_rate=1e-3,
            gamma=0.9,
            gae_lambda=0.8,
            clip_ratio=0.1,
            ppo_epochs=2,
            hidden_dim=64,
            output_dir="/tmp/rl_test",
        )
        assert cfg.env_id == "custom-v1"
        assert cfg.seed == 123
        assert cfg.episodes == 50
        assert cfg.batch_size == 16
        assert cfg.learning_rate == 1e-3
        assert cfg.gamma == 0.9
        assert cfg.gae_lambda == 0.8
        assert cfg.clip_ratio == 0.1
        assert cfg.ppo_epochs == 2
        assert cfg.hidden_dim == 64
        assert cfg.output_dir == "/tmp/rl_test"


# ─── RTSPolicy (PyTorch) ─────────────────────────────────────


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
class TestRTSPolicy:
    """Test the PyTorch RTSPolicy network."""

    @pytest.fixture()
    def policy(self):
        torch = pytest.importorskip("torch")
        from train.rl_trainer import RTSPolicy

        obs_dim = 64 * 10 + 4 + 1  # entities(64*10) + resources(4) + tick(1)
        return RTSPolicy(obs_dim=obs_dim, action_dim=6, hidden_dim=128, lr=1e-3)

    @pytest.fixture()
    def sample_obs(self):
        return {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }

    def test_forward_output_shapes(self, policy, sample_obs):
        torch = pytest.importorskip("torch")

        obs_flat = torch.from_numpy(
            np.concatenate([
                sample_obs["entities"].flatten(),
                sample_obs["resources"].flatten(),
                sample_obs["tick"].flatten(),
            ]).astype(np.float32)
        ).unsqueeze(0)

        logits, value = policy.forward(obs_flat)
        assert logits.shape == (1, 6), f"Expected logits shape (1, 6), got {logits.shape}"
        assert value.shape == (1,), f"Expected value shape (1,), got {value.shape}"

    def test_act_returns_tuple(self, policy, sample_obs):
        action, log_prob, value = policy.act(sample_obs)
        assert isinstance(action, int)
        assert 0 <= action < 6, f"Action {action} out of range [0, 6)"
        assert isinstance(log_prob, float)
        assert isinstance(value, float)

    def test_act_different_obs_shapes(self, policy):
        """RTSPolicy should handle various obs shapes as long as flatten matches obs_dim."""
        obs = {
            "entities": np.random.randn(64, 10).astype(np.float32),
            "resources": np.random.randn(4).astype(np.float32),
            "tick": np.array([5.0], dtype=np.float32),
        }
        action, log_prob, value = policy.act(obs)
        assert isinstance(action, int)


# ─── RLTrainer ────────────────────────────────────────────────


class TestRLTrainer:
    """Test RLTrainer initialization and compute_advantages."""

    def test_init_default_config(self):
        trainer = RLTrainer()
        assert trainer.config.episodes == 100
        assert trainer.config.batch_size == 32
        assert len(trainer.metrics) == 0

    def test_init_custom_config(self):
        cfg = RLTrainerConfig(episodes=10, batch_size=8)
        trainer = RLTrainer(config=cfg)
        assert trainer.config.episodes == 10
        assert trainer.config.batch_size == 8

    def test_init_with_external_policy(self):
        """RLTrainer accepts an external policy (SimplePolicy as mock)."""
        policy = SimplePolicy(n_actions=6)
        trainer = RLTrainer(policy=policy)
        assert trainer._external_policy is policy

    def test_init_with_env_factory(self):
        """RLTrainer accepts a custom env_factory."""
        called = False

        def factory():
            nonlocal called
            called = True
            raise RuntimeError("mock env")

        trainer = RLTrainer(env_factory=factory)
        assert trainer.env_factory is factory

    def test_compute_advantages_empty_buffer(self):
        trainer = RLTrainer()
        buf = RolloutBuffer(group_size=4)
        adv = trainer.compute_advantages(buf)
        assert adv.shape == (0,)

    def test_compute_advantages_shape(self):
        """compute_advantages should return array with same length as buffer."""
        cfg = RLTrainerConfig(gamma=0.99, gae_lambda=0.95)
        trainer = RLTrainer(config=cfg)
        buf = RolloutBuffer(group_size=4)

        obs = {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }
        for i in range(5):
            buf.add(Transition(
                obs=obs,
                action=0,
                reward=float(i),
                next_obs=obs,
                terminated=(i == 4),
                truncated=False,
                info={},
                log_prob=-0.5,
                value=float(i) * 0.1,
            ))

        adv = trainer.compute_advantages(buf)
        assert adv.shape == (5,), f"Expected shape (5,), got {adv.shape}"
        assert adv.dtype == np.float32

    def test_compute_advantages_with_dones(self):
        """Advantages should reset at episode boundaries (terminated/truncated)."""
        cfg = RLTrainerConfig(gamma=0.99, gae_lambda=0.95)
        trainer = RLTrainer(config=cfg)
        buf = RolloutBuffer(group_size=4)

        obs = {
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        }

        # Two short episodes: [terminated=True at idx 1, truncated=True at idx 3]
        for i in range(4):
            buf.add(Transition(
                obs=obs,
                action=0,
                reward=1.0,
                next_obs=obs,
                terminated=(i == 1),
                truncated=(i == 3),
                info={},
                log_prob=-0.5,
                value=0.0,
            ))

        adv = trainer.compute_advantages(buf)
        assert adv.shape == (4,)
        # Non-zero advantages expected since reward=1.0 and value=0.0
        assert not np.allclose(adv, 0.0)