"""Telemetry v2 — metrics, tracing, and replay analytics.

Three components:
1. MetricsCollector  — per-tick counters + histograms (APM, resources, units)
2. ReplayAnalyzer    — post-match analytics (build order, combat efficiency, comebacks)
3. TraceRecorder      — structured event log for debugging and training

All pure Python, no external deps beyond stdlib.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TickMetrics:
    """Snapshot of key indicators at a single tick."""

    tick: int
    player_id: int
    mineral: float = 0.0
    gas: float = 0.0
    workers: int = 0
    soldiers: int = 0
    buildings: int = 0
    idle_workers: int = 0
    apm: float = 0.0  # actions per minute (rolling 60s window)
    army_value: float = 0.0  # soldiers * cost
    economy_value: float = 0.0  # workers + buildings * cost


class MetricsCollector:
    """Collects per-tick metrics for all players during a match.

    Usage::

        mc = MetricsCollector()
        for tick in range(100):
            mc.record(tick, 1, obs_dict)
            mc.record(tick, 2, obs_dict)
        summary = mc.summarize()
    """

    def __init__(self) -> None:
        self._metrics: dict[int, list[TickMetrics]] = defaultdict(list)
        self._actions: dict[int, list[int]] = defaultdict(list)  # tick → action count

    def record(self, tick: int, player_id: int, obs: dict, action_count: int = 0) -> None:
        """Record metrics for one player at one tick."""
        entities = obs.get("entities", {})
        resources = obs.get("resources", {})

        workers = soldiers = buildings = idle_workers = 0
        army_value = 0.0
        eco_value = 0.0

        for e in entities.values():
            if e.get("owner") != player_id:
                continue
            etype = e.get("entity_type", "")
            if etype == "worker":
                workers += 1
                eco_value += 50
                if e.get("is_idle"):
                    idle_workers += 1
            elif etype == "soldier":
                soldiers += 1
                army_value += 50
            elif etype == "building":
                buildings += 1
                eco_value += 100 + e.get("health", 0)

        mineral = resources.get(f"p{player_id}_mineral", 0)
        gas = resources.get(f"p{player_id}_gas", 0)

        # Compute rolling APM (actions per game-minute = 60 ticks at 20tps)
        self._actions[player_id].append(action_count)
        recent_actions = self._actions[player_id][-1200:]  # last 60 game-seconds
        apm = sum(recent_actions) * (1200 / max(len(recent_actions), 1)) / 60

        self._metrics[player_id].append(TickMetrics(
            tick=tick,
            player_id=player_id,
            mineral=mineral,
            gas=gas,
            workers=workers,
            soldiers=soldiers,
            buildings=buildings,
            idle_workers=idle_workers,
            apm=apm,
            army_value=army_value,
            economy_value=eco_value,
        ))

    def get_series(self, player_id: int) -> list[TickMetrics]:
        return self._metrics.get(player_id, [])

    def summarize(self) -> dict[int, dict[str, Any]]:
        """Per-player summary statistics."""
        result: dict[int, dict[str, Any]] = {}
        for pid, series in self._metrics.items():
            if not series:
                continue
            result[pid] = {
                "total_ticks": len(series),
                "peak_army": max(s.soldiers for s in series),
                "peak_workers": max(s.workers for s in series),
                "avg_idle_workers": statistics.mean(s.idle_workers for s in series),
                "avg_apm": statistics.mean(s.apm for s in series),
                "peak_army_value": max(s.army_value for s in series),
                "total_mineral_earned": series[-1].mineral,
                "total_gas_earned": series[-1].gas,
                "final_army_value": series[-1].army_value,
                "final_economy_value": series[-1].economy_value,
            }
        return result


@dataclass
class CombatEvent:
    """A single combat engagement recorded during a match."""

    tick: int
    attacker_id: str
    defender_id: str
    damage: float
    attacker_owner: int
    defender_owner: int


class ReplayAnalyzer:
    """Post-match analytics on replay data.

    Extracts build orders, combat efficiency, economic curves, and comeback metrics.
    """

    def analyze(self, replay: list[dict]) -> dict[str, Any]:
        """Analyze a full replay and return structured insights."""
        if not replay:
            return {"error": "empty replay"}

        build_order = self._extract_build_order(replay)
        economic_curve = self._economic_curve(replay)
        winner = replay[-1].get("winner", 0) if replay else 0

        return {
            "winner": winner,
            "total_ticks": len(replay) - 1,
            "build_order": build_order,
            "economic_curve": economic_curve,
            "comeback": self._detect_comeback(replay),
        }

    @staticmethod
    def _extract_build_order(replay: list[dict]) -> dict[int, list[dict]]:
        """First appearance of each entity type per player."""
        seen: dict[int, dict[str, int]] = defaultdict(dict)
        for snapshot in replay:
            tick = snapshot.get("tick", 0)
            for _eid, e in snapshot.get("entities", {}).items():
                owner = e.get("owner", 0)
                etype = e.get("entity_type", "")
                if etype and etype not in seen[owner]:
                    seen[owner][etype] = tick
        # Convert to sorted build order
        result: dict[int, list[dict]] = {}
        for pid, types in seen.items():
            result[pid] = [
                {"entity_type": etype, "tick": tick}
                for etype, tick in sorted(types.items(), key=lambda x: x[1])
            ]
        return result

    @staticmethod
    def _economic_curve(replay: list[dict]) -> dict[int, list[float]]:
        """Total economic value per player per tick."""
        result: dict[int, list[float]] = defaultdict(list)
        for snapshot in replay:
            value_by_player: dict[int, float] = defaultdict(float)
            for e in snapshot.get("entities", {}).values():
                owner = e.get("owner", 0)
                if owner == 0:
                    continue
                etype = e.get("entity_type", "")
                if etype == "worker" or etype == "soldier":
                    value_by_player[owner] += 50
                elif etype == "building":
                    value_by_player[owner] += 100
            for pid in sorted(value_by_player):
                result[pid].append(value_by_player[pid])
        return dict(result)

    @staticmethod
    def _detect_comeback(replay: list[dict]) -> dict[str, Any]:
        """Detect if a player was behind but won."""
        if len(replay) < 10:
            return {"comeback": False}
        winner = replay[-1].get("winner", 0)
        if winner == 0:
            return {"comeback": False}

        # Check economic value at midpoint
        mid = len(replay) // 2
        mid_value: dict[int, float] = defaultdict(float)
        for e in replay[mid].get("entities", {}).values():
            owner = e.get("owner", 0)
            if owner == 0:
                continue
            etype = e.get("entity_type", "")
            if etype in ("worker", "soldier"):
                mid_value[owner] += 50
            elif etype == "building":
                mid_value[owner] += 100

        if not mid_value:
            return {"comeback": False}

        max_player = max(mid_value, key=mid_value.get)  # type: ignore[arg-type]
        comeback = max_player != winner
        return {
            "comeback": comeback,
            "mid_value": dict(mid_value),
            "winner": winner,
        }


class TraceRecorder:
    """Structured event logger for debugging and training data collection."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def log(
        self,
        event_type: str,
        tick: int,
        player_id: int = 0,
        **details: Any,
    ) -> None:
        self._events.append({
            "event": event_type,
            "tick": tick,
            "player_id": player_id,
            **details,
        })

    def export(self) -> list[dict[str, Any]]:
        return list(self._events)

    def save(self, path: str | Path) -> int:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(self._events, f, indent=2, default=str)
        return len(self._events)

    @classmethod
    def load(cls, path: str | Path) -> TraceRecorder:
        rec = cls()
        with open(path) as f:
            rec._events = json.load(f)
        return rec
