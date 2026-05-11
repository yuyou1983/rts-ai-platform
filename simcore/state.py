"""Immutable game state snapshots for deterministic replay."""
from __future__ import annotations

import math
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
        """Serialize state to a dict suitable for replay storage."""
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
            Each observation contains only entities visible to that player:
            - Own entities: always visible
            - Neutral resources: visible only in 'visible' (2) or 'explored' (1) tiles
            - Enemy entities: visible only in 'visible' (2) tiles
        """
        obs = []
        for pid in (1, 2):
            pid_str = str(pid)
            pf = self.fog_of_war.get(pid_str, {})
            fog_tiles = pf.get("tiles", [])
            fw = pf.get("width", 16)
            fh = pf.get("height", 16)

            visible_entities: dict[str, Any] = {}
            for eid, e in self.entities.items():
                owner = e.get("owner", 0)
                if owner == pid:
                    # Own entities always visible
                    visible_entities[eid] = e
                    continue

                # Map entity position to fog grid
                ex = e.get("pos_x", 0.0)
                ey = e.get("pos_y", 0.0)
                gx = int(ex / 64 * fw) if fw > 0 else 0
                gy = int(ey / 64 * fh) if fh > 0 else 0
                gx = max(0, min(gx, fw - 1))
                gy = max(0, min(gy, fh - 1))
                idx = gy * fw + gx
                fog_state = fog_tiles[idx] if 0 <= idx < len(fog_tiles) else 0

                if owner == 0:
                    # Neutral entities (resources): visible if explored (1) or visible (2)
                    if fog_state >= 1:
                        visible_entities[eid] = e
                else:
                    # Enemy entities: only visible if currently visible (2)
                    if fog_state == 2:
                        visible_entities[eid] = e

            # Own resources always visible
            own_res = {}
            for key, val in self.resources.items():
                if key.startswith(f"p{pid}_"):
                    own_res[key] = val

            obs.append({
                "tick": self.tick,
                "entities": visible_entities,
                "resources": own_res,
                "fog_of_war": pf,  # Include own fog state for rendering
            })
        return obs