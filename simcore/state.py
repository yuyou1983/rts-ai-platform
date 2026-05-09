"""Immutable game state snapshots for deterministic replay."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GameState:
    """Frozen game state — each tick produces a new snapshot.

    Immutability guarantees: same seed + same command sequence → identical replay.
    """

    tick: int
    entities: dict[str, Any] = field(default_factory=dict)
    fog_of_war: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, int] = field(default_factory=dict)
    is_terminal: bool = False
    winner: int = 0  # 0=none/draw, 1=P1, 2=P2

    def to_snapshot(self) -> dict:
        """Serialize state to a dict suitable for replay storage.

        Returns:
            Dict with all state fields for JSON/msgpack serialization.
        """
        return {
            "tick": self.tick,
            "entities": self.entities,
            "fog_of_war": self.fog_of_war,
            "resources": self.resources,
            "is_terminal": self.is_terminal,
            "winner": self.winner,
        }

    def get_observations(self) -> list[dict]:
        """Generate per-player observations (respecting fog-of-war).

        Returns:
            List of observation dicts, one per player.
        """
        # TODO(#M1): implement fog-of-war filtering per player
        return [
            {
                "tick": self.tick,
                "entities": self.entities,
                "resources": self.resources,
            },
            {
                "tick": self.tick,
                "entities": self.entities,
                "resources": self.resources,
            },
        ]
