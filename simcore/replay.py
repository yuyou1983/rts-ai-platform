"""Deterministic replay recorder and player."""
from __future__ import annotations

import json
from pathlib import Path


class ReplayRecorder:
    """Records game state snapshots for later replay.

    Each snapshot is a dict from GameState.to_snapshot().
    The replay is fully deterministic: same seed + commands → same trace.
    """

    def __init__(self) -> None:
        self._snapshots: list[dict] = []

    def record(self, snapshot: dict) -> None:
        """Record a state snapshot.

        Args:
            snapshot: GameState.to_snapshot() output.
        """
        self._snapshots.append(snapshot)

    def save(self, path: str | Path) -> None:
        """Save replay to a JSON file.

        Args:
            path: Output file path.
        """
        Path(path).write_text(json.dumps(self._snapshots, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> ReplayRecorder:
        """Load a replay from a JSON file.

        Args:
            path: Input file path.

        Returns:
            ReplayRecorder with loaded snapshots.
        """
        recorder = cls()
        data = json.loads(Path(path).read_text())
        recorder._snapshots = data
        return recorder

    @property
    def snapshots(self) -> list[dict]:
        """All recorded snapshots."""
        return list(self._snapshots)

    @property
    def length(self) -> int:
        """Number of recorded snapshots."""
        return len(self._snapshots)
