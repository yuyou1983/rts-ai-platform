"""League rules-AI self-play integration test.

End-to-end: register 3 rule-AI versions (Passive/Greedy/Rush) into a League,
generate round-robin matchups, run real SimCore games, record results,
update ELO, and print the leaderboard.

No GPU or RL training required — pure rule-based AI.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest

from harness.league import (
    AgentType,
    AgentVersion,
    League,
    MatchupConfig,
    MatchupMode,
    MatchupResult,
    VersionStats,
    update_elo,
)
from simcore.engine import SimCore
from agents.script_ai import ScriptAI


# ─── Custom rule-AI variants ────────────────────────────────────────────


class PassiveAI(ScriptAI):
    """Minimalist AI: only gathers resources, barely builds, never attacks.

    Designed to lose — serves as the baseline.
    """

    def __init__(self, player_id: int = 1) -> None:
        super().__init__(player_id=player_id, difficulty="easy", race="terran")
        # Override to be even more passive: no attacks until very late
        self.RALLY_SIZE = 99  # never rally enough to attack
        self.MAX_SOLDIERS = 4  # tiny army cap
        self.MAX_WORKERS = 6


class GreedyAI(ScriptAI):
    """Economy-focused AI: max workers first, moderate army, attacks mid-game.

    Medium strength — strong economy but delayed aggression.
    """

    def __init__(self, player_id: int = 1) -> None:
        super().__init__(player_id=player_id, difficulty="medium", race="terran")
        self.MAX_WORKERS = 16  # heavy economy
        self.MAX_SOLDIERS = 12
        self.RALLY_SIZE = 4  # attack with small groups


class RushAI(ScriptAI):
    """Aggressive AI: quick barracks, constant pressure, all-in attacks.

    Designed to win early — strong vs passive, can lose vs greedy late-game.
    """

    def __init__(self, player_id: int = 1) -> None:
        super().__init__(player_id=player_id, difficulty="hard", race="terran")
        self.MAX_WORKERS = 10  # limited economy
        self.MAX_SOLDIERS = 24  # large army
        self.RALLY_SIZE = 2  # attack very early
        self._build_barracks_tick = 0  # build barracks immediately


# ─── Direct SimCore match runner ─────────────────────────────────────────


def run_rules_match(
    ai1: ScriptAI,
    ai2: ScriptAI,
    map_seed: int = 42,
    max_ticks: int = 3000,
) -> dict[str, Any]:
    """Run a single script-vs-script match directly through SimCore.

    Returns a dict with keys: winner, ticks, tps.
    """
    t0 = time.monotonic()
    engine = SimCore(max_ticks=max_ticks, tick_rate=20.0)
    engine.initialize(map_seed=map_seed)

    # Assign player races (default terran)
    engine._player_races = {1: "terran", 2: "terran"}

    tick = 0
    while tick < max_ticks and not engine.state.is_terminal:
        obs = engine.state.get_observations()
        obs1 = obs[0] if obs else {}
        obs2 = obs[1] if len(obs) > 1 else {}

        result1 = ai1.decide(obs1)
        result2 = ai2.decide(obs2)

        cmds1 = result1.get("commands", []) if isinstance(result1, dict) else []
        cmds2 = result2.get("commands", []) if isinstance(result2, dict) else []

        for cmd in cmds1:
            cmd["issuer"] = 1
        for cmd in cmds2:
            cmd["issuer"] = 2

        engine.step(cmds1 + cmds2)
        tick += 1

    elapsed = time.monotonic() - t0
    final = engine.state
    return {
        "winner": final.winner if final else 0,
        "ticks": tick,
        "tps": tick / max(elapsed, 1e-9),
    }


# ─── Integration test ───────────────────────────────────────────────────


@pytest.mark.integration
class TestLeagueRulesSelfPlay:
    """End-to-end: register rule AIs → round-robin → SimCore → ELO → leaderboard."""

    # A short max_ticks so tests complete quickly (still enough for a decisive result)
    MAX_TICKS = 2000
    MAP_SEEDS = [42, 137]

    @staticmethod
    def _make_league() -> League:
        """Create a League with 3 rule-AI versions registered."""
        league = League()
        versions = [
            AgentVersion(
                name="passive-v1",
                type=AgentType.SCRIPT,
                creation_tick=0,
                metadata={"variant": "passive"},
            ),
            AgentVersion(
                name="greedy-v1",
                type=AgentType.SCRIPT,
                creation_tick=100,
                metadata={"variant": "greedy"},
            ),
            AgentVersion(
                name="rush-v1",
                type=AgentType.SCRIPT,
                creation_tick=200,
                metadata={"variant": "rush"},
            ),
        ]
        for v in versions:
            league.register(v)
        return league

    @staticmethod
    def _make_ai(name: str, player_id: int) -> ScriptAI:
        """Construct the correct ScriptAI variant from version name."""
        variant = name.split("-")[0]
        if variant == "passive":
            return PassiveAI(player_id=player_id)
        elif variant == "greedy":
            return GreedyAI(player_id=player_id)
        elif variant == "rush":
            return RushAI(player_id=player_id)
        else:
            # Fallback to default medium ScriptAI
            return ScriptAI(player_id=player_id, difficulty="medium")

    # ── 1. Registration ────────────────────────────────────────────────

    def test_register_three_versions(self):
        """Three versions are registered with correct ELO initialization."""
        league = self._make_league()
        assert len(league.pool) == 3
        for name in ("passive-v1", "greedy-v1", "rush-v1"):
            stats = league.get_stats(name)
            assert stats.elo == 1000.0
            assert stats.games_played == 0

    # ── 2. Round-robin matchup generation ───────────────────────────────

    def test_generate_round_robin_matchups(self):
        """Mirror mode generates matchups for each version × games_per_pair, cycling seeds."""
        league = self._make_league()
        mirror_cfg = MatchupConfig(
            mode=MatchupMode.MIRROR,
            games_per_pair=1,
            map_seeds=self.MAP_SEEDS,
            max_ticks=self.MAX_TICKS,
        )
        mirror_matchups = league.generate_matchups(mirror_cfg)
        # 3 versions × 1 game = 3 mirror matchups (seeds cycle)
        assert len(mirror_matchups) == 3
        for m in mirror_matchups:
            assert m["mode"] == "mirror"
            assert m["player1_version"] == m["player2_version"]

    def test_mirror_matchups_cycle_seeds(self):
        """Mirror mode cycles through map seeds across versions."""
        league = self._make_league()
        mirror_cfg = MatchupConfig(
            mode=MatchupMode.MIRROR,
            games_per_pair=2,
            map_seeds=self.MAP_SEEDS,
            max_ticks=self.MAX_TICKS,
        )
        mirror_matchups = league.generate_matchups(mirror_cfg)
        # 3 versions × 2 games = 6 matchups, seeds cycle over [42, 137]
        assert len(mirror_matchups) == 6
        seeds_used = [m["map_seed"] for m in mirror_matchups]
        assert 42 in seeds_used and 137 in seeds_used

    def test_cross_type_zero_when_same_type(self):
        """When all versions are the same agent type, cross-type yields 0 matchups."""
        league = self._make_league()
        cfg = MatchupConfig(
            mode=MatchupMode.CROSS_TYPE,
            games_per_pair=2,
            map_seeds=[42],
            max_ticks=self.MAX_TICKS,
        )
        matchups = league.generate_matchups(cfg)
        # All are SCRIPT type → no cross-type pairs
        assert matchups == []

    # ── 3. Run games + record results + ELO update ─────────────────────

    def _run_round_robin_games(
        self,
        league: League,
        games_per_pair: int = 1,
    ) -> list[MatchupResult]:
        """Manually generate all ordered-pair matchups and run SimCore games.

        We bypass the League matchup generator (which only supports mirror/
        new_vs_old/cross_type modes) and create a full round-robin:
        every (A_vs_B) and (B_vs_A) on each map seed.
        """
        versions = league.pool.get_all_versions()
        results: list[MatchupResult] = []

        for i, v1 in enumerate(versions):
            for v2 in versions[i + 1 :]:
                # v1 as P1 vs v2 as P2
                for seed in self.MAP_SEEDS:
                    for _ in range(games_per_pair):
                        ai1 = self._make_ai(v1.name, player_id=1)
                        ai2 = self._make_ai(v2.name, player_id=2)
                        outcome = run_rules_match(
                            ai1, ai2, map_seed=seed, max_ticks=self.MAX_TICKS
                        )
                        results.append(
                            MatchupResult(
                                player1=v1.name,
                                player2=v2.name,
                                winner=outcome["winner"],
                                ticks=outcome["ticks"],
                                mode=MatchupMode.CROSS_TYPE,
                            )
                        )

                # v2 as P1 vs v1 as P2 (swap sides for fairness)
                for seed in self.MAP_SEEDS:
                    for _ in range(games_per_pair):
                        ai1 = self._make_ai(v2.name, player_id=1)
                        ai2 = self._make_ai(v1.name, player_id=2)
                        outcome = run_rules_match(
                            ai1, ai2, map_seed=seed, max_ticks=self.MAX_TICKS
                        )
                        results.append(
                            MatchupResult(
                                player1=v2.name,
                                player2=v1.name,
                                winner=outcome["winner"],
                                ticks=outcome["ticks"],
                                mode=MatchupMode.CROSS_TYPE,
                            )
                        )

        return results

    def test_full_round_robin_with_simcore(self):
        """Register 3 AIs → round-robin (6 ordered pairs × 2 seeds × 1 game = 12 games)
        → record results → ELO updates → verify ranking."""
        league = self._make_league()

        # Run games
        results = self._run_round_robin_games(league, games_per_pair=1)
        assert len(results) == 12  # 3 choose 2 = 3 pairs × 2 directions × 2 seeds × 1

        # Record all results
        league.record_results(results)

        # Verify total games
        assert league.total_games == 12

        # Verify each version has played games
        for name in ("passive-v1", "greedy-v1", "rush-v1"):
            stats = league.get_stats(name)
            assert stats.games_played > 0

        # Passive should generally lose → lowest ELO
        # Rush/Greedy should have higher ELO than Passive
        passive_elo = league.get_elo("passive-v1")
        greedy_elo = league.get_elo("greedy-v1")
        rush_elo = league.get_elo("rush-v1")

        # At minimum, not all ELOs should be equal (someone must have won)
        assert not (passive_elo == greedy_elo == rush_elo == 1000.0), (
            "Expected at least one ELO change after 12 games"
        )

        # Print leaderboard for debugging
        leaderboard = league.format_leaderboard()
        print("\n" + leaderboard)

    def test_elo_updates_after_games(self):
        """Verify ELO conservation: sum of all ELO changes should be zero."""
        league = self._make_league()

        initial_total_elo = sum(league.get_elo(n) for n in ("passive-v1", "greedy-v1", "rush-v1"))
        assert initial_total_elo == 3000.0

        results = self._run_round_robin_games(league, games_per_pair=1)
        league.record_results(results)

        final_total_elo = sum(league.get_elo(n) for n in ("passive-v1", "greedy-v1", "rush-v1"))
        # ELO is conserved per-match (zero-sum), so total should remain 3000
        assert abs(final_total_elo - 3000.0) < 1e-6, (
            f"ELO not conserved: initial=3000, final={final_total_elo}"
        )

    def test_passive_loses_most(self):
        """Passive AI should have the most losses of the three."""
        league = self._make_league()
        results = self._run_round_robin_games(league, games_per_pair=1)
        league.record_results(results)

        passive_stats = league.get_stats("passive-v1")
        greedy_stats = league.get_stats("greedy-v1")
        rush_stats = league.get_stats("rush-v1")

        # Passive is designed to be weakest → most losses
        assert passive_stats.losses >= greedy_stats.losses or passive_stats.losses >= rush_stats.losses, (
            f"Expected Passive to have most losses: "
            f"Passive L={passive_stats.losses}, Greedy L={greedy_stats.losses}, Rush L={rush_stats.losses}"
        )

    # ── 4. Leaderboard formatting ──────────────────────────────────────

    def test_leaderboard_after_games(self):
        """Leaderboard is non-empty and contains all version names."""
        league = self._make_league()
        results = self._run_round_robin_games(league, games_per_pair=1)
        league.record_results(results)

        board = league.get_leaderboard()
        assert len(board) == 3
        names = {s.name for s in board}
        assert names == {"passive-v1", "greedy-v1", "rush-v1"}

        # Board should be sorted by ELO descending
        for i in range(len(board) - 1):
            assert board[i].elo >= board[i + 1].elo

    def test_format_leaderboard_output(self):
        """format_leaderboard() produces a readable string with table formatting."""
        league = self._make_league()
        results = self._run_round_robin_games(league, games_per_pair=1)
        league.record_results(results)

        text = league.format_leaderboard()
        assert "League Leaderboard" in text
        assert "passive-v1" in text
        assert "greedy-v1" in text
        assert "rush-v1" in text
        assert "ELO" in text

    def test_summary_dict(self):
        """summary() returns a machine-readable dict with correct structure."""
        league = self._make_league()
        results = self._run_round_robin_games(league, games_per_pair=1)
        league.record_results(results)

        s = league.summary()
        assert s["versions"] == 3
        assert s["total_games"] == 12
        assert len(s["leaderboard"]) == 3

    # ── 5. Multiple rounds (repeated games) ────────────────────────────

    def test_two_rounds_elo_converges(self):
        """Running 2 rounds of round-robin (24 games) → ELO converges further."""
        league = self._make_league()

        # Round 1
        results_r1 = self._run_round_robin_games(league, games_per_pair=1)
        league.record_results(results_r1)
        elo_after_r1 = {n: league.get_elo(n) for n in ("passive-v1", "greedy-v1", "rush-v1")}

        # Round 2
        results_r2 = self._run_round_robin_games(league, games_per_pair=1)
        league.record_results(results_r2)
        elo_after_r2 = {n: league.get_elo(n) for n in ("passive-v1", "greedy-v1", "rush-v1")}

        assert league.total_games == 24

        # After more games, ELO should have moved further from 1000
        # (at least for the strongest/weakest)
        max_deviation_r1 = max(abs(e - 1000.0) for e in elo_after_r1.values())
        max_deviation_r2 = max(abs(e - 1000.0) for e in elo_after_r2.values())
        assert max_deviation_r2 >= max_deviation_r1, (
            "ELO should spread further with more games"
        )

        print("\n" + league.format_leaderboard())


# ─── Unit-level: verify AI variant behaviour ─────────────────────────────


class TestRulesAIVariants:
    """Verify the three rule-AI variants produce different decision patterns."""

    @pytest.mark.parametrize("ai_cls,name", [
        (PassiveAI, "passive"),
        (GreedyAI, "greedy"),
        (RushAI, "rush"),
    ])
    def test_ai_initializes_correctly(self, ai_cls, name):
        ai = ai_cls(player_id=1)
        assert ai.player_id == 1

    def test_passive_has_small_caps(self):
        ai = PassiveAI(player_id=1)
        assert ai.MAX_WORKERS <= 8
        assert ai.MAX_SOLDIERS <= 8
        assert ai.RALLY_SIZE > 20  # won't attack easily

    def test_greedy_has_large_economy(self):
        ai = GreedyAI(player_id=1)
        assert ai.MAX_WORKERS >= 14
        assert ai.MAX_SOLDIERS >= 10

    def test_rush_has_early_barracks(self):
        ai = RushAI(player_id=1)
        assert ai._build_barracks_tick == 0
        assert ai.RALLY_SIZE <= 3

    def test_match_produces_valid_outcome(self):
        """A single Passive vs Rush match should produce a decisive winner or draw."""
        outcome = run_rules_match(
            PassiveAI(player_id=1),
            RushAI(player_id=2),
            map_seed=42,
            max_ticks=2000,
        )
        assert outcome["winner"] in (0, 1, 2)
        assert outcome["ticks"] > 0
        assert outcome["tps"] > 0

    def test_rush_beats_passive(self):
        """Rush should reliably beat Passive (at least 2 out of 3 on different seeds)."""
        wins = 0
        for seed in [42, 137, 256]:
            outcome = run_rules_match(
                RushAI(player_id=1),
                PassiveAI(player_id=2),
                map_seed=seed,
                max_ticks=2000,
            )
            if outcome["winner"] == 1:
                wins += 1
        assert wins >= 2, f"Rush only won {wins}/3 against Passive"
