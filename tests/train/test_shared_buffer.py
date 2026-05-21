"""Tests for train/shared_buffer.py — SharedRolloutBuffer thread-safety and behaviour."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np
import pytest

from train.grpo_trainer import Transition
from train.shared_buffer import SharedRolloutBuffer


# ─── Helpers ──────────────────────────────────────────────────


def _make_transition(reward: float = 1.0) -> Transition:
    """Create a minimal Transition for testing."""
    return Transition(
        obs={
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        },
        action=0,
        reward=reward,
        next_obs={
            "entities": np.zeros((64, 10), dtype=np.float32),
            "resources": np.zeros(4, dtype=np.float32),
            "tick": np.zeros(1, dtype=np.float32),
        },
        terminated=False,
        truncated=False,
        info={},
    )


# ─── Test cases ──────────────────────────────────────────────


class TestSharedBufferAdd:
    def test_single_add(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        t = _make_transition()
        buf.add(t)
        assert len(buf) == 1

    def test_concurrent_adds(self):
        """Multiple threads adding transitions concurrently."""
        buf = SharedRolloutBuffer(group_size=2, max_transitions=1000)
        n_threads = 8
        adds_per_thread = 50
        barrier = threading.Barrier(n_threads)

        def _worker():
            barrier.wait()
            for _ in range(adds_per_thread):
                buf.add(_make_transition())

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(buf) == n_threads * adds_per_thread


class TestSharedBufferMax:
    def test_respects_max_transitions(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=5)
        for i in range(10):
            buf.add(_make_transition())
        assert len(buf) == 5

    def test_is_full_after_max(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=3)
        for _ in range(3):
            buf.add(_make_transition())
        assert buf.is_full()

    def test_not_full_before_max(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=10)
        buf.add(_make_transition())
        assert not buf.is_full()


class TestSharedBufferComputeAdvantages:
    def test_returns_correct_shape(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        for i in range(4):
            buf.add(_make_transition(reward=float(i)))
        advantages = buf.compute_advantages()
        assert advantages.shape == (4,)

    def test_advantages_values(self):
        """With group_size=2 and 4 transitions, groups are [0,1] and [2,3]."""
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        rewards = [1.0, 3.0, 5.0, 9.0]
        for r in rewards:
            buf.add(_make_transition(reward=r))
        advantages = buf.compute_advantages()
        # Group 1: [1.0, 3.0] → mean=2, std=1 → adv = [-1, 1]
        # Group 2: [5.0, 9.0] → mean=7, std=2 → adv = [-1, 1]
        np.testing.assert_allclose(advantages[:2], [-1.0, 1.0], atol=1e-6)
        np.testing.assert_allclose(advantages[2:], [-1.0, 1.0], atol=1e-6)


class TestSharedBufferClear:
    def test_clear_empties_buffer(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        for _ in range(5):
            buf.add(_make_transition())
        assert len(buf) == 5
        buf.clear()
        assert len(buf) == 0

    def test_clear_resets_is_full(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=2)
        buf.add(_make_transition())
        buf.add(_make_transition())
        assert buf.is_full()
        buf.clear()
        assert not buf.is_full()


class TestSharedBufferIsFull:
    def test_is_full_true(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=2)
        buf.add(_make_transition())
        buf.add(_make_transition())
        assert buf.is_full()

    def test_is_full_false(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=10)
        buf.add(_make_transition())
        assert not buf.is_full()


class TestSharedBufferAddBatch:
    def test_batch_addition(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        transitions = [_make_transition() for _ in range(10)]
        added = buf.add_batch(transitions)
        assert added == 10
        assert len(buf) == 10

    def test_batch_respects_max(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=5)
        transitions = [_make_transition() for _ in range(10)]
        added = buf.add_batch(transitions)
        assert added == 5
        assert len(buf) == 5

    def test_batch_returns_count(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        transitions = [_make_transition() for _ in range(3)]
        added = buf.add_batch(transitions)
        assert added == 3


class TestSharedBufferGetTransitions:
    def test_get_transitions_returns_copy(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        buf.add(_make_transition())
        ts = buf.get_transitions()
        assert len(ts) == 1
        # Modifying returned list does not affect buffer
        ts.clear()
        assert len(buf) == 1

    def test_get_transitions_content(self):
        buf = SharedRolloutBuffer(group_size=2, max_transitions=100)
        t = _make_transition(reward=42.0)
        buf.add(t)
        ts = buf.get_transitions()
        assert ts[0].reward == 42.0