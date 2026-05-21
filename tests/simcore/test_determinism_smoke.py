"""Deterministic replay smoke tests for SimCore.

Verifies the core invariant: same seed + same command sequence → identical replay.
"""
from __future__ import annotations

import pytest

from simcore.engine import SimCore

try:
    from agents.script_ai import ScriptAI

    _HAS_SCRIPT_AI = True
except ImportError:
    _HAS_SCRIPT_AI = False


MAX_TICKS = 200


def _run_with_script_ai(seed: int) -> list[dict]:
    """Run a game for MAX_TICKS with ScriptAI for both players, return replay."""
    ai1 = ScriptAI(player_id=1)
    ai2 = ScriptAI(player_id=2)
    engine = SimCore(max_ticks=MAX_TICKS)
    engine.initialize(map_seed=seed)
    for _ in range(MAX_TICKS):
        if engine.state.is_terminal:
            break
        obs = engine.state.get_observations()
        cmds1 = ai1.decide(obs[0]).get("commands", [])
        cmds2 = ai2.decide(obs[1]).get("commands", [])
        engine.step(cmds1 + cmds2)
    return engine.replay


def _run_with_empty_commands(seed: int) -> list[dict]:
    """Run a game for MAX_TICKS with no AI commands, return replay."""
    engine = SimCore(max_ticks=MAX_TICKS)
    engine.initialize(map_seed=seed)
    for _ in range(MAX_TICKS):
        if engine.state.is_terminal:
            break
        engine.step(commands=[])
    return engine.replay


def test_same_seed_same_commands_same_replay():
    """Same seed + same ScriptAI decisions must produce identical replay snapshots."""
    if not _HAS_SCRIPT_AI:
        pytest.skip("ScriptAI not available")

    replay_a = _run_with_script_ai(seed=42)
    replay_b = _run_with_script_ai(seed=42)

    assert len(replay_a) == len(replay_b), (
        f"Replay lengths differ: {len(replay_a)} vs {len(replay_b)}"
    )
    for tick, (snap_a, snap_b) in enumerate(zip(replay_a, replay_b)):
        assert snap_a == snap_b, f"Divergence at tick {tick}"


def test_different_seed_different_replay():
    """Different seeds must produce different initial snapshots."""
    engine_a = SimCore()
    engine_a.initialize(map_seed=42)
    snap_a = engine_a.state.to_snapshot()

    engine_b = SimCore()
    engine_b.initialize(map_seed=99)
    snap_b = engine_b.state.to_snapshot()

    assert snap_a != snap_b, "Different seeds produced identical initial state"


def test_same_seed_empty_commands_same_replay():
    """Same seed + empty commands must produce identical replay snapshots."""
    replay_a = _run_with_empty_commands(seed=42)
    replay_b = _run_with_empty_commands(seed=42)

    assert len(replay_a) == len(replay_b), (
        f"Replay lengths differ: {len(replay_a)} vs {len(replay_b)}"
    )
    for tick, (snap_a, snap_b) in enumerate(zip(replay_a, replay_b)):
        assert snap_a == snap_b, f"Divergence at tick {tick}"