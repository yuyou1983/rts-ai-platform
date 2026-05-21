"""Deterministic replay recorder and player."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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


@dataclass
class ReplayV2:
    """Compact replay: seed + command sequence + periodic keyframes.

    V1 (full snapshot) stays the default for Godot.
    V2 is for training/replay analysis.
    State hash validates V2 replay determinism.
    """

    seed: int
    map_width: int = 64
    map_height: int = 64
    config: dict = field(default_factory=dict)
    commands: list[dict] = field(default_factory=list)  # [{"tick": N, "commands": [...]}]
    keyframes: dict[int, dict] = field(default_factory=dict)  # tick → snapshot
    hashes: dict[int, int] = field(default_factory=dict)  # tick → state_hash
    keyframe_interval: int = 100

    def record_tick(self, tick: int, cmds: list[dict]) -> None:
        self.commands.append({"tick": tick, "commands": cmds})

    def record_keyframe(self, tick: int, snapshot: dict) -> None:
        self.keyframes[tick] = snapshot

    def record_hash(self, tick: int, state_hash: int) -> None:
        self.hashes[tick] = state_hash

    def to_dict(self) -> dict:
        return {
            "version": 2, "seed": self.seed,
            "map_width": self.map_width, "map_height": self.map_height,
            "config": self.config,
            "commands": self.commands,
            "keyframes": {str(k): v for k, v in self.keyframes.items()},
            "hashes": {str(k): v for k, v in self.hashes.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReplayV2:
        return cls(
            seed=data["seed"], map_width=data.get("map_width", 64),
            map_height=data.get("map_height", 64), config=data.get("config", {}),
            commands=data.get("commands", []),
            keyframes={int(k): v for k, v in data.get("keyframes", {}).items()},
            hashes={int(k): v for k, v in data.get("hashes", {}).items()},
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> ReplayV2:
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def reexecute(cls, replay_v2: ReplayV2) -> list[int]:
        """Re-execute V2 replay, return per-tick hashes for verification."""
        from simcore.engine import SimCore
        engine = SimCore(enable_state_hash=True, enable_event_log=False, enable_order_queue=False)
        engine.initialize(map_seed=replay_v2.seed, config=replay_v2.config)
        result_hashes: list[int] = []
        for cmd_record in replay_v2.commands:
            engine.step(cmd_record.get("commands", []))
            snapshot = engine.replay[-1]
            result_hashes.append(snapshot.get("state_hash", 0))
        return result_hashes
