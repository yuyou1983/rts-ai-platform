"""Tests for Replay V2 dual-track system."""
import json
import tempfile
from pathlib import Path

import pytest

from simcore.engine import SimCore
from simcore.replay import ReplayV2


class TestReplayV2RecordsCommands:
    """V2 replay records commands per tick."""

    def test_replay_v2_records_commands(self):
        """Engine with enable_replay_v2=True records commands."""
        engine = SimCore(enable_replay_v2=True)
        engine.initialize(map_seed=42)
        cmds = [{"unit_id": "worker_1", "action": "gather"}]
        engine.step(cmds)
        assert engine.replay_v2 is not None
        assert len(engine.replay_v2.commands) == 1
        assert engine.replay_v2.commands[0]["tick"] == 1
        assert engine.replay_v2.commands[0]["commands"] == cmds


class TestReplayV2OffByDefault:
    """V2 replay is off by default."""

    def test_replay_v2_off_by_default(self):
        """Default engine has replay_v2 property as None."""
        engine = SimCore()
        engine.initialize(map_seed=42)
        assert engine.replay_v2 is None


class TestReplayV2Keyframes:
    """V2 replay records periodic keyframes."""

    def test_replay_v2_keyframes(self):
        """Keyframes are recorded every keyframe_interval ticks."""
        interval = 100
        engine = SimCore(enable_replay_v2=True, enable_state_hash=True)
        engine.initialize(map_seed=42)
        engine.replay_v2.keyframe_interval = interval
        for i in range(250):
            engine.step(commands=[])
        # Keyframes expected at ticks 100, 200
        assert 100 in engine.replay_v2.keyframes
        assert 200 in engine.replay_v2.keyframes
        # 250 is not a multiple of 100
        assert 250 not in engine.replay_v2.keyframes


class TestReplayV2Hashes:
    """V2 replay records state hashes when hash is enabled."""

    def test_replay_v2_hashes(self):
        """With enable_state_hash + enable_replay_v2, hashes are recorded."""
        engine = SimCore(enable_replay_v2=True, enable_state_hash=True)
        engine.initialize(map_seed=42)
        for _ in range(5):
            engine.step(commands=[])
        assert len(engine.replay_v2.hashes) == 5
        # All hashes should be non-zero
        for tick, h in engine.replay_v2.hashes.items():
            assert isinstance(h, int)
            assert h != 0


class TestReplayV2Serialization:
    """Round-trip serialization of ReplayV2."""

    def test_replay_v2_serialization(self):
        """to_dict → from_dict round-trip preserves data."""
        r = ReplayV2(seed=99, map_width=32, map_height=32, config={"difficulty": "hard"})
        r.record_tick(1, [{"action": "move"}])
        r.record_keyframe(100, {"tick": 100, "entities": {}})
        r.record_hash(1, 12345)
        d = r.to_dict()
        r2 = ReplayV2.from_dict(d)
        assert r2.seed == 99
        assert r2.map_width == 32
        assert r2.config == {"difficulty": "hard"}
        assert len(r2.commands) == 1
        assert 100 in r2.keyframes
        assert r2.hashes[1] == 12345


class TestReplayV2SaveLoad:
    """File save/load round-trip."""

    def test_replay_v2_save_load(self, tmp_path):
        """Save to file, load back, data matches."""
        r = ReplayV2(seed=42, config={"foo": "bar"})
        r.record_tick(1, [{"action": "gather"}])
        r.record_hash(1, 9999)
        path = tmp_path / "test_replay.json"
        r.save(path)
        r2 = ReplayV2.load(path)
        assert r2.seed == 42
        assert r2.config == {"foo": "bar"}
        assert len(r2.commands) == 1
        assert r2.hashes[1] == 9999


class TestReplayV2SmallerThanV1:
    """V2 replay should be smaller than V1 for the same game."""

    def test_replay_v2_smaller_than_v1(self):
        """Compare JSON size of V1 replay vs V2 replay for same game."""
        engine = SimCore(enable_replay_v2=True, enable_state_hash=True)
        engine.initialize(map_seed=42)
        for _ in range(50):
            engine.step(commands=[])
        v1_json = json.dumps(engine.replay, indent=2)
        v2_json = json.dumps(engine.replay_v2.to_dict(), indent=2)
        assert len(v2_json) < len(v1_json), (
            f"V2 ({len(v2_json)}) should be smaller than V1 ({len(v1_json)})"
        )


class TestReplayV2ReexecuteMatchesLive:
    """Re-executed V2 replay hashes match live execution."""

    def test_replay_v2_reexecute_matches_live(self):
        """Run live game, reexecute V2, verify hashes match."""
        engine = SimCore(enable_replay_v2=True, enable_state_hash=True)
        engine.initialize(map_seed=42)
        for _ in range(20):
            engine.step(commands=[])
        # Collect live hashes
        live_hashes = list(engine.replay_v2.hashes.values())
        # Re-execute
        reexec_hashes = ReplayV2.reexecute(engine.replay_v2)
        assert live_hashes == reexec_hashes, (
            f"Live hashes {live_hashes[:5]}... != reexec {reexec_hashes[:5]}..."
        )


class TestReplayV1Unaffected:
    """V1 replay still works when V2 is enabled."""

    def test_replay_v1_unaffected(self):
        """V1 replay is still recorded when V2 is enabled."""
        engine = SimCore(enable_replay_v2=True, enable_state_hash=True)
        engine.initialize(map_seed=42)
        for _ in range(5):
            engine.step(commands=[])
        # V1 replay should have 1 (init) + 5 (steps) = 6 entries
        assert len(engine.replay) == 6
        # V2 should also be present
        assert engine.replay_v2 is not None
        assert len(engine.replay_v2.commands) == 5