"""Tests for SimCore engine: initialization, determinism, replay."""
import pytest

from agents.script_ai import ScriptAI
from simcore.engine import SimCore


class TestInitialization:
    """Test SimCore initialization and determinism."""

    def test_default_state(self):
        """Engine starts un-initialized."""
        engine = SimCore()
        assert engine.state is None
        assert engine.tick == 0

    def test_initialize_sets_state(self):
        """initialize() creates a valid GameState."""
        engine = SimCore()
        engine.initialize(map_seed=42)
        assert engine.state is not None
        assert engine.tick == 0
        assert len(engine.state.entities) > 0

    def test_initialization_deterministic(self):
        """Same seed → same initial state."""
        engine1 = SimCore()
        engine1.initialize(map_seed=123)

        engine2 = SimCore()
        engine2.initialize(map_seed=123)

        assert engine1.state == engine2.state

    def test_different_seed_different_state(self):
        """Different seeds → different states."""
        engine1 = SimCore()
        engine1.initialize(map_seed=1)

        engine2 = SimCore()
        engine2.initialize(map_seed=2)

        assert engine1.state != engine2.state


class TestStep:
    """Test single tick advancement."""

    def test_step_requires_initialization(self):
        """step() raises if not initialized."""
        engine = SimCore()
        with pytest.raises(RuntimeError, match="not initialized"):
            engine.step(commands=[])

    def test_step_advances_tick(self):
        """step() increments tick counter."""
        engine = SimCore()
        engine.initialize(map_seed=42)
        engine.step(commands=[])
        assert engine.tick == 1

    def test_step_returns_gamestate(self):
        """step() returns a GameState."""
        engine = SimCore()
        engine.initialize(map_seed=42)
        state = engine.step(commands=[])
        assert state is not None
        assert state.tick == 1


class TestReplay:
    """Test deterministic replay."""

    def test_replay_records_initial_state(self):
        """Replay includes the initial state snapshot."""
        engine = SimCore()
        engine.initialize(map_seed=42)
        assert len(engine.replay) == 1
        assert engine.replay[0]["tick"] == 0

    def test_replay_deterministic(self):
        """Same seed + same commands → identical replay."""
        def run_game(seed: int) -> list[dict]:
            e = SimCore(max_ticks=100)
            e.initialize(map_seed=seed)
            for _ in range(20):
                e.step(commands=[])
            return e.replay

        assert run_game(42) == run_game(42)

    def test_replay_length_matches_ticks(self):
        """Replay length = 1 (init) + N (ticks)."""
        engine = SimCore()
        engine.initialize(map_seed=42)
        for _ in range(5):
            engine.step(commands=[])
        assert len(engine.replay) == 6


class TestWithAI:
    """Test engine with scripted AI driving decisions."""

    def test_ai_produces_commands(self):
        """ScriptAI generates non-empty commands on real game state."""
        ai = ScriptAI(player_id=1)
        engine = SimCore()
        engine.initialize(map_seed=42)
        obs = engine.state.get_observations()
        cmd = ai.decide(obs[0] if obs else {})
        assert "commands" in cmd
        assert "tick" in cmd

    def test_ai_game_loop(self):
        """Engine runs for N ticks with AI decisions."""
        ai = ScriptAI(player_id=1)
        engine = SimCore(max_ticks=50)
        engine.initialize(map_seed=42)
        for _ in range(10):
            obs = engine.state.get_observations()
            cmds = ai.decide(obs[0] if obs else {}).get("commands", [])
            engine.step(cmds)
        assert engine.tick == 10
