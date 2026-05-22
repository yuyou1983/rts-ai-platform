"""Tests for SimCore feature-flag wiring through the training pipeline."""
from __future__ import annotations

import gymnasium as gym

import simcore.gym_env  # noqa: F401 — registers rts-ai-v0
from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer


def test_config_flags():
    """TRLGRPOConfig should store SimCore feature flags."""
    cfg = TRLGRPOConfig(
        enable_state_hash=True,
        enable_order_queue=True,
        enable_event_log=True,
        enable_replay_v2=True,
    )
    assert cfg.enable_state_hash is True
    assert cfg.enable_order_queue is True
    assert cfg.enable_event_log is True
    assert cfg.enable_replay_v2 is True

    # Defaults should be False
    cfg_default = TRLGRPOConfig()
    assert cfg_default.enable_state_hash is False
    assert cfg_default.enable_order_queue is False
    assert cfg_default.enable_event_log is False
    assert cfg_default.enable_replay_v2 is False


def test_env_accepts_flags():
    """gym.make should accept feature flags and forward them to RTSSimCoreEnv."""
    env = gym.make(
        "rts-ai-v0",
        seed=42,
        max_ticks=50,
        reward_shaping="shaped",
        enable_state_hash=True,
        enable_order_queue=True,
        enable_event_log=True,
        enable_replay_v2=False,
    )
    try:
        obs, info = env.reset(seed=42)
        assert "entities" in obs
        # Verify flags were stored on the unwrapped env
        unwrapped = env.unwrapped
        assert hasattr(unwrapped, "_enable_state_hash")
        assert unwrapped._enable_state_hash is True
        assert unwrapped._enable_order_queue is True
        assert unwrapped._enable_event_log is True
        assert unwrapped._enable_replay_v2 is False
    finally:
        env.close()


def test_default_env_factory_forwards_flags():
    """_default_env_factory should pass config flags through to gym.make."""
    cfg = TRLGRPOConfig(
        seed=99,
        max_ticks=50,
        reward_shaping="shaped",
        enable_state_hash=True,
        enable_order_queue=True,
        enable_event_log=True,
    )
    trainer = TRLGRPOTrainer(cfg)
    env = trainer._default_env_factory()
    try:
        unwrapped = env.unwrapped
        assert unwrapped._enable_state_hash is True
        assert unwrapped._enable_order_queue is True
        assert unwrapped._enable_event_log is True
        assert unwrapped._enable_replay_v2 is False  # default
    finally:
        env.close()