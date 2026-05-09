"""Tests for Telemetry v2 — MetricsCollector, ReplayAnalyzer, TraceRecorder."""
import tempfile
from pathlib import Path

from harness.telemetry import (
    MetricsCollector,
    ReplayAnalyzer,
    TraceRecorder,
)


def _make_replay(ticks: int = 50, winner: int = 1) -> list[dict]:
    """Generate a synthetic replay for testing."""
    replay = []
    for t in range(ticks + 1):
        entities = {
            "w1": {"owner": 1, "entity_type": "worker", "is_idle": t < 5, "health": 50},
            "s1": {"owner": 1, "entity_type": "soldier", "health": 80},
            "b1": {"owner": 1, "entity_type": "building", "building_type": "base", "health": 500},
            "e1": {"owner": 2, "entity_type": "soldier", "health": max(0, 80 - t * 2)},
        }
        if t > 10:
            entities["b2"] = {
                "owner": 1, "entity_type": "building",
                "building_type": "barracks", "health": 300,
            }
        replay.append({
            "tick": t,
            "entities": entities,
            "resources": {"p1_mineral": 100 + t * 5, "p1_gas": 10 + t},
            "winner": winner if t == ticks else 0,
            "is_terminal": t == ticks,
        })
    return replay


class TestMetricsCollector:
    def test_record_and_summarize(self):
        mc = MetricsCollector()
        for t in range(100):
            obs = {
                "entities": {
                    "w1": {"owner": 1, "entity_type": "worker", "is_idle": t < 10},
                    "s1": {"owner": 1, "entity_type": "soldier", "health": 80},
                },
                "resources": {"p1_mineral": 100 + t * 3},
            }
            mc.record(t, 1, obs, action_count=2 if t % 5 == 0 else 0)
        summary = mc.summarize()
        assert 1 in summary
        assert summary[1]["peak_workers"] == 1
        assert summary[1]["peak_army"] == 1
        assert summary[1]["avg_apm"] >= 0


class TestReplayAnalyzer:
    def test_analyze_basic(self):
        replay = _make_replay(50, winner=1)
        ra = ReplayAnalyzer()
        result = ra.analyze(replay)
        assert result["winner"] == 1
        assert result["total_ticks"] == 50
        assert 1 in result["build_order"]
        assert "economic_curve" in result

    def test_build_order(self):
        replay = _make_replay(50)
        ra = ReplayAnalyzer()
        bo = ra._extract_build_order(replay)
        # Player 1 should have worker (tick 0), soldier (tick 0), building (tick 0)
        # and barracks (tick 11)
        p1_types = [b["entity_type"] for b in bo.get(1, [])]
        assert "worker" in p1_types
        assert "building" in p1_types

    def test_comeback_detection(self):
        # Winner = 2, but player 1 is ahead at midpoint → comeback
        replay = _make_replay(100, winner=2)
        ra = ReplayAnalyzer()
        result = ra.analyze(replay)
        # In our synthetic replay, player 1 has more stuff at midpoint
        assert "comeback" in result


class TestTraceRecorder:
    def test_log_and_export(self):
        tr = TraceRecorder()
        tr.log("attack", tick=5, player_id=1, attacker="s1", target="e1")
        tr.log("gather", tick=6, player_id=1, worker="w1", resource="m1")
        events = tr.export()
        assert len(events) == 2
        assert events[0]["event"] == "attack"

    def test_save_and_load(self):
        tr = TraceRecorder()
        tr.log("test_event", tick=0, detail="hello")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.json"
            n = tr.save(path)
            assert n == 1
            loaded = TraceRecorder.load(path)
            assert len(loaded.export()) == 1
            assert loaded.export()[0]["detail"] == "hello"
