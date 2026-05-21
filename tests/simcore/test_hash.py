"""Tests for state hashing: FNV-1a, GameState.state_hash, engine integration."""
import pytest

from simcore.hash import fnv1a_64
from simcore.state import GameState
from simcore.engine import SimCore


# ---------------------------------------------------------------------------
# FNV-1a 64-bit unit tests
# ---------------------------------------------------------------------------

class TestFNV1a:
    """FNV-1a 64-bit hash function tests."""

    def test_fnv1a_known_empty(self):
        """FNV-1a 64-bit of empty bytes equals the offset basis."""
        assert fnv1a_64(b"") == 0xCBF29CE484222325

    def test_fnv1a_deterministic(self):
        """Same input always produces the same output."""
        data = b"hello world"
        assert fnv1a_64(data) == fnv1a_64(data)

    def test_fnv1a_different(self):
        """Different inputs produce different outputs."""
        assert fnv1a_64(b"foo") != fnv1a_64(b"bar")

    def test_fnv1a_returns_int(self):
        """fnv1a_64 returns an int."""
        result = fnv1a_64(b"test")
        assert isinstance(result, int)

    def test_fnv1a_64_bit_range(self):
        """Result fits in 64 bits (unsigned)."""
        result = fnv1a_64(b"anything")
        assert 0 <= result < 2**64


# ---------------------------------------------------------------------------
# GameState.state_hash() tests
# ---------------------------------------------------------------------------

class TestStateHash:
    """GameState.state_hash() tests."""

    def test_state_hash_deterministic(self):
        """Same GameState always produces the same hash."""
        state = GameState(
            tick=5,
            entities={"unit_1": {"hp": 100, "pos_x": 1.0, "pos_y": 2.0}},
            fog_of_war={},
            resources={"p1_minerals": 500},
            is_terminal=False,
            winner=0,
        )
        assert state.state_hash() == state.state_hash()

    def test_state_hash_changes(self):
        """Different entity HP produces different hash."""
        state_a = GameState(
            tick=1,
            entities={"unit_1": {"hp": 100}},
            fog_of_war={},
            resources={},
            is_terminal=False,
            winner=0,
        )
        state_b = GameState(
            tick=1,
            entities={"unit_1": {"hp": 99}},
            fog_of_war={},
            resources={},
            is_terminal=False,
            winner=0,
        )
        assert state_a.state_hash() != state_b.state_hash()

    def test_state_hash_float_normalization(self):
        """1.0 and 1.000000000001 should hash the same after 4-decimal rounding."""
        state_a = GameState(
            tick=1,
            entities={"unit_1": {"pos_x": 1.0}},
            fog_of_war={},
            resources={},
            is_terminal=False,
            winner=0,
        )
        state_b = GameState(
            tick=1,
            entities={"unit_1": {"pos_x": 1.000000000001}},
            fog_of_war={},
            resources={},
            is_terminal=False,
            winner=0,
        )
        assert state_a.state_hash() == state_b.state_hash()

    def test_state_hash_returns_int(self):
        """state_hash() returns an int."""
        state = GameState(tick=0)
        result = state.state_hash()
        assert isinstance(result, int)

    def test_state_hash_different_tick(self):
        """Different ticks produce different hashes."""
        state0 = GameState(tick=0)
        state1 = GameState(tick=1)
        assert state0.state_hash() != state1.state_hash()

    def test_state_hash_nested_floats(self):
        """Float normalization works on deeply nested values."""
        state_a = GameState(
            tick=1,
            entities={"u1": {"pos": {"x": 3.14159, "y": 2.71828}}},
            fog_of_war={},
            resources={},
            is_terminal=False,
            winner=0,
        )
        state_b = GameState(
            tick=1,
            entities={"u1": {"pos": {"x": 3.1416, "y": 2.7183}}},
            fog_of_war={},
            resources={},
            is_terminal=False,
            winner=0,
        )
        assert state_a.state_hash() == state_b.state_hash()


# ---------------------------------------------------------------------------
# Engine integration tests
# ---------------------------------------------------------------------------

class TestEngineHash:
    """SimCore enable_state_hash integration tests."""

    def test_engine_hash_with_flag_on(self):
        """When enable_state_hash=True, snapshots include state_hash."""
        engine = SimCore(enable_state_hash=True, max_ticks=100)
        engine.initialize(map_seed=42)
        engine.step(commands=[])
        # Initial snapshot + one step = 2 entries
        assert len(engine.replay) == 2
        for snapshot in engine.replay:
            assert "state_hash" in snapshot
            assert isinstance(snapshot["state_hash"], int)

    def test_engine_hash_off_by_default(self):
        """Default SimCore does NOT include state_hash in snapshots."""
        engine = SimCore()
        engine.initialize(map_seed=42)
        engine.step(commands=[])
        for snapshot in engine.replay:
            assert "state_hash" not in snapshot

    def test_engine_hash_flag_explicit_false(self):
        """Explicitly setting enable_state_hash=False omits state_hash."""
        engine = SimCore(enable_state_hash=False)
        engine.initialize(map_seed=42)
        engine.step(commands=[])
        for snapshot in engine.replay:
            assert "state_hash" not in snapshot

    def test_multi_run_hash_consistency(self):
        """Running same game 3x produces identical state hashes every tick."""
        def run_game() -> list[dict]:
            e = SimCore(enable_state_hash=True, max_ticks=50)
            e.initialize(map_seed=99)
            for _ in range(10):
                e.step(commands=[])
            return e.replay

        runs = [run_game() for _ in range(3)]
        # All runs should have the same length
        lengths = [len(r) for r in runs]
        assert lengths[0] == lengths[1] == lengths[2]
        # All state hashes should match across runs at every tick
        for tick_idx in range(lengths[0]):
            hashes = [run[tick_idx].get("state_hash") for run in runs]
            assert hashes[0] == hashes[1] == hashes[2], (
                f"Hash mismatch at tick {tick_idx}: {hashes}"
            )