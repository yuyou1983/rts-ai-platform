"""Tests for train/rollout_worker.py — RolloutWorker with mock env."""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest

from train.grpo_trainer import Transition
from train.rollout_worker import RolloutWorker

try:
    from train.trl_trainer import HAS_TORCH as _HAS_TORCH
except ImportError:
    _HAS_TORCH = False


# ─── Mock Environment (module-level for pickle) ───────────────


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
        info: dict[str, Any] = {}
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


# ─── Module-level callables (must be pickle-able) ────────────


def _make_mock_env() -> MockEnv:
    """Pickleable env factory — returns a MockEnv with ep_length=3."""
    return MockEnv(ep_length=3, n_actions=6)


def _constant_policy(obs: dict[str, Any]) -> int:
    """Pickleable policy that always returns action 0."""
    return 0


# ─── Fixtures ─────────────────────────────────────────────────


@pytest.fixture()
def worker():
    """Return a RolloutWorker with mock env and constant policy."""
    return RolloutWorker(
        num_workers=2,
        env_factory=_make_mock_env,
        policy=_constant_policy,
        max_steps=100,
    )


# ─── RolloutWorker initialization ─────────────────────────────


class TestRolloutWorkerInit:
    def test_default_attributes(self, worker):
        assert worker.num_workers == 2
        assert worker.max_steps == 100
        assert worker._episodes_completed == 0
        assert worker._total_steps == 0

    def test_custom_num_workers(self):
        w = RolloutWorker(
            num_workers=8,
            env_factory=_make_mock_env,
            policy=_constant_policy,
        )
        assert w.num_workers == 8


# ─── collect_episode ──────────────────────────────────────────


class TestCollectEpisode:
    def test_returns_list_of_transitions(self, worker):
        transitions = asyncio.run(worker.collect_episode(seed=42))
        assert isinstance(transitions, list)
        assert len(transitions) > 0
        for t in transitions:
            assert isinstance(t, Transition)

    def test_episode_length_matches_env(self, worker):
        """With MockEnv(ep_length=3), we expect 3 transitions."""
        transitions = asyncio.run(worker.collect_episode(seed=1))
        assert len(transitions) == 3

    def test_episode_records_correct_actions(self):
        """Policy always returns action=0; all transitions should have action=0."""
        w = RolloutWorker(
            num_workers=1,
            env_factory=_make_mock_env,
            policy=_constant_policy,
            max_steps=100,
        )
        transitions = asyncio.run(w.collect_episode(seed=10))
        for t in transitions:
            assert t.action == 0

    def test_episode_reward(self, worker):
        """Each step gives reward=1.0; total should be 3.0 for 3 steps."""
        transitions = asyncio.run(worker.collect_episode(seed=7))
        total_reward = sum(t.reward for t in transitions)
        assert total_reward == pytest.approx(3.0)

    def test_updates_stats(self, worker):
        """collect_episode should update internal episode/step counters."""
        assert worker._episodes_completed == 0
        assert worker._total_steps == 0
        asyncio.run(worker.collect_episode(seed=1))
        assert worker._episodes_completed == 1
        assert worker._total_steps == 3


# ─── collect_batch ─────────────────────────────────────────────


class TestCollectBatch:
    def test_returns_correct_number_of_episodes(self, worker):
        episodes = asyncio.run(worker.collect_batch(n_episodes=4, base_seed=0))
        assert len(episodes) == 4

    def test_each_episode_is_nonempty(self, worker):
        episodes = asyncio.run(worker.collect_batch(n_episodes=3, base_seed=0))
        for ep in episodes:
            assert len(ep) > 0

    def test_deterministic_ordering(self, worker):
        """Episodes returned by collect_batch should be in index order."""
        episodes = asyncio.run(worker.collect_batch(n_episodes=5, base_seed=42))
        assert len(episodes) == 5
        for ep in episodes:
            assert len(ep) == 3


# ─── run (synchronous entry point) ────────────────────────────


class TestRun:
    def test_run_returns_correct_count(self, worker):
        episodes = worker.run(n_episodes=5, base_seed=0)
        assert len(episodes) == 5

    def test_run_resets_stats(self, worker):
        """run() should reset per-run counters at the start."""
        worker.run(n_episodes=2, base_seed=0)
        assert worker._episodes_completed == 2
        assert worker._total_steps == 6  # 2 episodes × 3 steps

    def test_run_with_different_batch_sizes(self):
        w = RolloutWorker(
            num_workers=1,
            env_factory=_make_mock_env,
            policy=_constant_policy,
            max_steps=100,
        )
        for n in [1, 3, 7]:
            episodes = w.run(n_episodes=n, base_seed=0)
            assert len(episodes) == n

    def test_run_episode_contents(self, worker):
        episodes = worker.run(n_episodes=2, base_seed=42)
        for ep in episodes:
            for t in ep:
                assert isinstance(t, Transition)
                assert isinstance(t.action, int)
                assert isinstance(t.reward, float)


# ─── SharedRolloutBuffer integration ──────────────────────────


class TestWorkerWithSharedBuffer:
    def test_collects_into_shared_buffer(self):
        from train.shared_buffer import SharedRolloutBuffer

        shared_buf = SharedRolloutBuffer(group_size=4, max_transitions=1000)
        w = RolloutWorker(
            num_workers=2,
            env_factory=_make_mock_env,
            policy=_constant_policy,
            max_steps=100,
            shared_buffer=shared_buf,
        )
        episodes = w.run(n_episodes=4, base_seed=0)
        # Transitions should have been added to shared buffer
        total_transitions = sum(len(ep) for ep in episodes)
        assert len(shared_buf) == total_transitions
        assert total_transitions == 12  # 4 episodes × 3 steps

    def test_shared_buffer_preserves_content(self):
        from train.shared_buffer import SharedRolloutBuffer

        shared_buf = SharedRolloutBuffer(group_size=2, max_transitions=1000)
        w = RolloutWorker(
            num_workers=1,
            env_factory=_make_mock_env,
            policy=_constant_policy,
            max_steps=100,
            shared_buffer=shared_buf,
        )
        w.run(n_episodes=2, base_seed=0)
        transitions = shared_buf.get_transitions()
        assert len(transitions) == 6  # 2 episodes × 3 steps
        for t in transitions:
            assert isinstance(t, Transition)


# ─── GRPO Policy (torch-only) ────────────────────────────────


class TestWorkerGRPOPolicy:
    @pytest.mark.skipif(
        not _HAS_TORCH, reason="PyTorch not available"
    )
    def test_grpo_policy_runs(self):
        """RolloutWorker with policy_type='grpo' should collect episodes."""
        w = RolloutWorker(
            num_workers=2,
            env_factory=_make_mock_env,
            max_steps=100,
            policy_type="grpo",
        )
        episodes = w.run(n_episodes=2, base_seed=0)
        assert len(episodes) == 2
        for ep in episodes:
            assert len(ep) > 0

    @pytest.mark.skipif(
        _HAS_TORCH, reason="Test only valid without PyTorch"
    )
    def test_grpo_policy_fails_without_torch(self):
        """Without PyTorch, policy_type='grpo' should raise RuntimeError."""
        w = RolloutWorker(
            num_workers=1,
            env_factory=_make_mock_env,
            max_steps=100,
            policy_type="grpo",
        )
        with pytest.raises(RuntimeError, match="PyTorch not available"):
            w.run(n_episodes=1, base_seed=0)


# ─── Throughput measurement ──────────────────────────────────


class TestWorkerThroughput:
    def test_games_per_hour(self):
        """4 workers, 8 episodes should yield a measurable games/hr rate > 100."""
        w = RolloutWorker(
            num_workers=4,
            env_factory=_make_mock_env,
            policy=_constant_policy,
            max_steps=100,
        )
        w.run(n_episodes=8, base_seed=0)
        # MockEnv episodes are very fast; expect high throughput
        assert w.games_per_hour > 100

    def test_games_per_hour_zero_before_run(self):
        w = RolloutWorker(
            num_workers=1,
            env_factory=_make_mock_env,
            policy=_constant_policy,
            max_steps=100,
        )
        assert w.games_per_hour == 0.0