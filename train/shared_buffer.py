"""Shared RolloutBuffer — thread-safe buffer for concurrent rollout collection."""
from __future__ import annotations

import threading
import numpy as np
from typing import Any
from train.grpo_trainer import Transition, RolloutBuffer


class SharedRolloutBuffer:
    """Thread-safe wrapper around RolloutBuffer for concurrent collection.

    Multiple worker threads/processes can add transitions concurrently.
    Uses a lock to serialize additions. When full, compute_advantages()
    can be called from the main training thread.
    """

    def __init__(self, group_size: int = 4, max_transitions: int = 10000) -> None:
        self._buffer = RolloutBuffer(group_size=group_size)
        self._lock = threading.Lock()
        self._max_transitions = max_transitions

    def add(self, t: Transition) -> None:
        with self._lock:
            if len(self._buffer) < self._max_transitions:
                self._buffer.add(t)

    def add_batch(self, transitions: list[Transition]) -> int:
        """Add a batch of transitions. Returns count actually added."""
        with self._lock:
            space = self._max_transitions - len(self._buffer)
            count = min(len(transitions), space)
            for t in transitions[:count]:
                self._buffer.add(t)
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def is_full(self) -> bool:
        with self._lock:
            return len(self._buffer) >= self._max_transitions

    def compute_advantages(self) -> np.ndarray:
        with self._lock:
            return self._buffer.compute_advantages()

    def get_transitions(self) -> list[Transition]:
        with self._lock:
            return list(self._buffer.transitions)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    @property
    def group_size(self) -> int:
        return self._buffer.group_size