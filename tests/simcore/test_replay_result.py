"""Tests for replay result integrity: winner consistency, keyframe recovery, corruption detection.

1. test_replay_rush_vs_passive_match_result
   — RushAI vs PassiveAI runs to terminal state, replay is saved/loaded/reexecuted,
     and the winner from the reexecuted engine matches the original.

2. test_keyframe_state_recoverable
   — From a keyframe tick's snapshot we can read the entity count and confirm
     at least one entity has non-zero health.

3. test_replay_detects_corruption
   — Tampering with a command in the replay causes reexecution hashes to diverge
     from the original live hashes.
"""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import pytest

from simcore.agents import PassiveAI, RushAI
from simcore.engine import SimCore
from simcore.replay import ReplayV2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_rush_vs_passive(max_ticks: int = 2000) -> SimCore:
    """Run RushAI (P1) vs PassiveAI (P2) until terminal or max_ticks."""
    engine = SimCore(
        max_ticks=max_ticks,
        enable_replay_v2=True,
        enable_state_hash=True,
    )
    engine.initialize(
        map_seed=42,
        config={"player_races": {1: "terran", 2: "terran"}},
    )
    agents = [RushAI(player_id=1, attack_threshold=2), PassiveAI()]
    while engine.tick < max_ticks and not engine.state.is_terminal:
        obs = engine.state.get_observations()
        cmds = [a.decide(o) for a, o in zip(agents, obs)]
        engine.step(cmds[0] + cmds[1])
    return engine


# ---------------------------------------------------------------------------
# Test 1: winner consistency after save/load + reexecute
# ---------------------------------------------------------------------------

class TestReplayRushVsPassiveMatchResult:
    def test_replay_rush_vs_passive_match_result(self, tmp_path: Path):
        """RushAI vs PassiveAI → terminal; save+load+reexecute yields same winner."""
        engine = _run_rush_vs_passive(max_ticks=2000)
        assert engine.state.is_terminal, "Game did not reach terminal state within max_ticks"

        original_winner = engine.state.winner
        assert original_winner in (1, 2), f"Unexpected winner: {original_winner}"

        # Save ReplayV2 to disk
        replay_path = tmp_path / "rush_vs_passive.json"
        engine.replay_v2.save(replay_path)

        # Load it back
        loaded: ReplayV2 = ReplayV2.load(replay_path)
        assert loaded.winner == original_winner, (
            f"Loaded replay winner {loaded.winner} != original {original_winner}"
        )

        # Reexecute and extract the winner from the reexecuted engine
        reexec_engine = SimCore(
            enable_state_hash=True,
            enable_event_log=False,
            enable_order_queue=False,
        )
        reexec_engine.initialize(map_seed=loaded.seed, config=loaded.config)
        for cmd_record in loaded.commands:
            reexec_engine.step(cmd_record.get("commands", []))

        reexec_winner = reexec_engine.state.winner
        assert reexec_winner == original_winner, (
            f"Reexecuted winner {reexec_winner} != original {original_winner}"
        )


# ---------------------------------------------------------------------------
# Test 2: keyframe state recoverable
# ---------------------------------------------------------------------------

class TestKeyframeStateRecoverable:
    def test_keyframe_state_recoverable(self, tmp_path: Path):
        """Keyframe snapshots contain entities with non-zero health."""
        engine = SimCore(
            max_ticks=500,
            enable_replay_v2=True,
            enable_state_hash=True,
        )
        engine.initialize(
            map_seed=42,
            config={"player_races": {1: "terran", 2: "terran"}},
        )
        agents = [RushAI(player_id=1, attack_threshold=2), PassiveAI()]

        # Run enough ticks to guarantee at least one keyframe (interval=100)
        for _ in range(250):
            obs = engine.state.get_observations()
            cmds = [a.decide(o) for a, o in zip(agents, obs)]
            engine.step(cmds[0] + cmds[1])

        rp: ReplayV2 = engine.replay_v2
        assert len(rp.keyframes) > 0, "No keyframes recorded"

        # Pick the first keyframe tick
        keyframe_tick = sorted(rp.keyframes.keys())[0]
        snapshot = rp.keyframes[keyframe_tick]

        entities = snapshot.get("entities", {})
        # Filter out meta-entries (keys starting with "__")
        real_entities = {
            eid: e for eid, e in entities.items()
            if not eid.startswith("__")
        }
        assert len(real_entities) > 0, (
            f"Keyframe at tick {keyframe_tick} has no real entities"
        )

        # At least one entity must have non-zero health
        non_zero_health = [
            e for e in real_entities.values()
            if e.get("health", 0) > 0
        ]
        assert len(non_zero_health) > 0, (
            f"No entity with health > 0 in keyframe at tick {keyframe_tick}"
        )


# ---------------------------------------------------------------------------
# Test 3: corruption detection via hash mismatch
# ---------------------------------------------------------------------------

class TestReplayDetectsCorruption:
    def test_replay_detects_corruption(self, tmp_path: Path):
        """Modifying a command in the replay causes reexecute hashes to differ."""
        engine = SimCore(
            max_ticks=500,
            enable_replay_v2=True,
            enable_state_hash=True,
        )
        engine.initialize(
            map_seed=42,
            config={"player_races": {1: "terran", 2: "terran"}},
        )
        agents = [RushAI(player_id=1, attack_threshold=2), PassiveAI()]

        # Run enough ticks to have a meaningful command history
        for _ in range(150):
            obs = engine.state.get_observations()
            cmds = [a.decide(o) for a, o in zip(agents, obs)]
            engine.step(cmds[0] + cmds[1])

        rp: ReplayV2 = engine.replay_v2
        original_hashes = list(rp.hashes.values())

        # Deep-copy the replay and tamper with commands at a mid-game tick
        corrupted = copy.deepcopy(rp)
        # Find the first tick that has non-empty commands and wipe them all.
        # Removing previously valid commands forces a different game trajectory,
        # which MUST cause state hashes to diverge from the original.
        tampered = False
        for i, cmd_rec in enumerate(corrupted.commands):
            if cmd_rec.get("commands"):
                corrupted.commands[i]["commands"] = []
                tampered = True
                break

        assert tampered, "No tick with non-empty commands found to corrupt"

        # Reexecute the corrupted replay
        reexec_hashes = ReplayV2.reexecute(corrupted)

        # Hashes should NOT all match — at least one must differ
        mismatches = sum(
            1 for a, b in zip(original_hashes, reexec_hashes) if a != b
        )
        assert mismatches > 0, (
            "Corrupted replay produced identical hashes — corruption not detected"
        )
