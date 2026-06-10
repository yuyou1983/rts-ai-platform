"""Match recorder — records tick-by-tick game state to JSONL for replay.

Usage:
    recorder = Recorder()
    recorder.start_recording(game_config)
    for tick in game:
        recorder.record_tick(tick, entities, resources, commands, is_terminal)
    recorder.save_replay("replay_123_terran_vs_zerg.jsonl")

Format: one JSON object per line (JSONL).
Each line: {"tick": N, "entities_snapshot": {...}, "commands_this_tick": [...], "is_terminal": bool}
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


_RACE_SHORT = {"terran": "t", "zerg": "z", "protoss": "p"}


class Recorder:
    """Records a game match tick-by-tick for later replay."""

    def __init__(self) -> None:
        self._recording: bool = False
        self._ticks: list[dict] = []
        self._config: dict = {}
        self._start_time: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start_recording(self, game_config: dict) -> None:
        """Begin a new recording session.

        Args:
            game_config: dict with game parameters (seed, max_ticks,
                player_races, etc.). Stored as metadata in the replay header.
        """
        self._recording = True
        self._ticks.clear()
        self._config = dict(game_config)
        self._start_time = time.time()

    def record_tick(
        self,
        tick: int,
        entities: dict,
        resources: dict,
        commands: list[dict] | None = None,
        is_terminal: bool = False,
    ) -> None:
        """Record a single tick snapshot.

        Args:
            tick: current tick number.
            entities: full entity dict from GameState (id → entity_data).
            resources: resources dict {player_id → resource_data}.
            commands: commands issued this tick (human + AI merged).
            is_terminal: whether the game ended this tick.
        """
        if not self._recording:
            return
        self._ticks.append({
            "tick": tick,
            "entities_snapshot": entities,
            "resources": resources,
            "commands_this_tick": commands or [],
            "is_terminal": is_terminal,
        })

    def stop_recording(self) -> None:
        """Stop recording (no more ticks will be accepted)."""
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def tick_count(self) -> int:
        return len(self._ticks)

    # ── Persistence ──────────────────────────────────────────────────────

    def save_replay(self, filepath: str | Path) -> str:
        """Save the recorded ticks to a JSONL file.

        Args:
            filepath: output path. If directory doesn't exist, it's created.

        Returns:
            The absolute path of the saved file.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            # Header line with metadata
            header = {
                "type": "header",
                "config": self._config,
                "duration_seconds": round(time.time() - self._start_time, 2),
                "tick_count": len(self._ticks),
            }
            f.write(json.dumps(header, default=str) + "\n")
            # One line per tick
            for tick_data in self._ticks:
                f.write(json.dumps(tick_data, default=str) + "\n")
        return str(path.resolve())

    @classmethod
    def load_replay(cls, filepath: str | Path) -> tuple[dict, list[dict]]:
        """Load a JSONL replay file.

        Args:
            filepath: path to the .jsonl file.

        Returns:
            (header, ticks) — header is the metadata dict, ticks is the list
            of per-tick snapshot dicts.
        """
        path = Path(filepath)
        header: dict = {}
        ticks: list[dict] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("type") == "header":
                    header = data
                else:
                    ticks.append(data)
        return header, ticks

    @classmethod
    def generate_filename(self, player_races: dict[str, str] | None = None) -> str:
        """Generate a descriptive replay filename.

        Args:
            player_races: optional {"1": "terran", "2": "zerg"} mapping.

        Returns:
            Filename like replay_1717500000_t_vs_z.jsonl
        """
        ts = int(time.time())
        p1 = _RACE_SHORT.get(
            (player_races or {}).get("1", "terran"), "t"
        )
        p2 = _RACE_SHORT.get(
            (player_races or {}).get("2", "terran"), "t"
        )
        return f"replay_{ts}_{p1}_vs_{p2}.jsonl"
