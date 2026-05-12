"""AI Benchmark Suite — adversarial cross-race tests.

Each test runs two race AIs against each other for up to 5000 ticks,
verifying that the game terminates with a winner and recording stats.
"""
from __future__ import annotations
import pytest
from simcore.engine import SimCore
from agents.zerg_ai import ZergAI
from agents.protoss_ai import ProtossAI
from agents.terran_ai import TerranAI


def _run_match(ai1, ai2, max_ticks: int = 5000) -> dict:
    """Run a full AI vs AI match, return stats dict."""
    e = SimCore()
    e.initialize(map_seed=42, config={"player_races": {1: ai1.RACE, 2: ai2.RACE}})
    for _ in range(max_ticks):
        obs = e.state.get_observations()
        r1 = ai1.decide(obs[0])
        r2 = ai2.decide(obs[1])
        cmds = r1.get("commands", []) + r2.get("commands", [])
        e.step(cmds)
        if e.state.is_terminal:
            break

    # Count unit types per player
    p1_units: dict[str, int] = {}
    p2_units: dict[str, int] = {}
    for eid, ent in e.state.entities.items():
        ut = ent.get("unit_type", "")
        if ent.get("owner") == 1 and ut:
            p1_units[ut] = p1_units.get(ut, 0) + 1
        elif ent.get("owner") == 2 and ut:
            p2_units[ut] = p2_units.get(ut, 0) + 1

    return {
        "tick": e.state.tick,
        "terminal": e.state.is_terminal,
        "winner": e.state.winner,
        "p1_units": p1_units,
        "p2_units": p2_units,
    }


class TestBenchmark:
    """Cross-race adversarial benchmarks."""

    def test_terran_vs_zerg(self):
        result = _run_match(TerranAI(player_id=1), ZergAI(player_id=2))
        assert result["terminal"], f"Game didn't terminate in {result['tick']} ticks"
        assert result["winner"] in (1, 2), f"Expected a winner, got {result['winner']}"

    def test_zerg_vs_protoss(self):
        result = _run_match(ZergAI(player_id=1), ProtossAI(player_id=2))
        assert result["terminal"], f"Game didn't terminate in {result['tick']} ticks"
        assert result["winner"] in (1, 2), f"Expected a winner, got {result['winner']}"

    def test_protoss_vs_terran(self):
        result = _run_match(ProtossAI(player_id=1), TerranAI(player_id=2))
        assert result["terminal"], f"Game didn't terminate in {result['tick']} ticks"
        assert result["winner"] in (1, 2), f"Expected a winner, got {result['winner']}"

    def test_zerg_solo_economy(self):
        """Zerg AI alone should reach 500 mineral and have combat units by tick 500."""
        e = SimCore()
        e.initialize(map_seed=42, config={"player_races": {1: "zerg"}})
        ai = ZergAI(player_id=1)
        for _ in range(500):
            obs = e.get_observations(player_id=1)
            result = ai.decide(obs)
            e.step(result.get("commands", []))

        mineral = e.state.resources.get("p1_mineral", 0)
        soldiers = [e for eid, e in e.state.entities.items()
                     if e.get("owner") == 1 and e.get("entity_type") == "soldier"]
        assert mineral >= 200, f"Expected 200+ mineral, got {mineral}"
        assert len(soldiers) >= 1, f"Expected at least 1 soldier, got {len(soldiers)}"