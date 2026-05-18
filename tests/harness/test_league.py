"""Tests for harness.league — AgentVersion, LeaguePool, ELO, MatchupMode, League."""
from __future__ import annotations

import pytest

from harness.league import (
    AgentType,
    AgentVersion,
    LeaguePool,
    League,
    MatchupConfig,
    MatchupMode,
    MatchupResult,
    VersionStats,
    update_elo,
    _expected_score,
)


# ─── AgentVersion tests ─────────────────────────────────────────────


class TestAgentVersion:
    """Test AgentVersion dataclass."""

    def test_init_basic(self):
        v = AgentVersion(name="script-v1", type=AgentType.SCRIPT)
        assert v.name == "script-v1"
        assert v.type == AgentType.SCRIPT
        assert v.checkpoint_path == ""
        assert v.creation_tick == 0
        assert v.metadata == {}

    def test_init_with_all_fields(self):
        v = AgentVersion(
            name="coord-v2",
            type=AgentType.COORDINATOR,
            checkpoint_path="/models/coord-v2.pt",
            creation_tick=150,
            metadata={"lr": 0.001, "epochs": 10},
        )
        assert v.checkpoint_path == "/models/coord-v2.pt"
        assert v.creation_tick == 150
        assert v.metadata["lr"] == 0.001

    def test_type_coercion_from_string(self):
        v = AgentVersion(name="test", type="script")
        assert v.type == AgentType.SCRIPT

    def test_type_coercion_invalid_raises(self):
        with pytest.raises(ValueError):
            AgentVersion(name="test", type="unknown_type")

    def test_sort_key(self):
        v1 = AgentVersion(name="v1", type=AgentType.SCRIPT, creation_tick=10)
        v2 = AgentVersion(name="v2", type=AgentType.SCRIPT, creation_tick=20)
        assert v1.sort_key < v2.sort_key

    def test_hash_and_equality(self):
        v1 = AgentVersion(name="same", type=AgentType.SCRIPT)
        v2 = AgentVersion(name="same", type=AgentType.COORDINATOR)
        v3 = AgentVersion(name="different", type=AgentType.SCRIPT)
        assert v1 == v2  # equality based on name only
        assert v1 != v3
        assert hash(v1) == hash(v2)

    def test_equality_not_implemented_for_other_types(self):
        v = AgentVersion(name="test", type=AgentType.SCRIPT)
        assert v.__eq__("not_a_version") is NotImplemented


# ─── AgentType tests ────────────────────────────────────────────────


class TestAgentType:
    def test_values(self):
        assert AgentType.SCRIPT.value == "script"
        assert AgentType.COORDINATOR.value == "coordinator"
        assert AgentType.GRPO.value == "grpo"

    def test_from_string(self):
        assert AgentType("script") is AgentType.SCRIPT
        assert AgentType("coordinator") is AgentType.COORDINATOR
        assert AgentType("grpo") is AgentType.GRPO


# ─── VersionStats tests ────────────────────────────────────────────


class TestVersionStats:
    def test_defaults(self):
        s = VersionStats(name="test")
        assert s.elo == 1000.0
        assert s.wins == 0
        assert s.losses == 0
        assert s.draws == 0
        assert s.games_played == 0
        assert s.win_rate == 0.0

    def test_win_rate_calculation(self):
        s = VersionStats(name="test", wins=6, losses=3, draws=1, games_played=10)
        assert s.win_rate == 0.6

    def test_win_rate_zero_games(self):
        s = VersionStats(name="test")
        assert s.win_rate == 0.0

    def test_to_dict(self):
        s = VersionStats(name="v1", elo=1050.0, wins=10, losses=5, draws=2, games_played=17)
        d = s.to_dict()
        assert d["name"] == "v1"
        assert d["elo"] == 1050.0
        assert d["wins"] == 10
        assert d["losses"] == 5
        assert d["draws"] == 2
        assert d["games_played"] == 17
        assert abs(d["win_rate"] - 10 / 17) < 0.01


# ─── MatchupMode tests ─────────────────────────────────────────────


class TestMatchupMode:
    def test_values(self):
        assert MatchupMode.MIRROR.value == "mirror"
        assert MatchupMode.NEW_VS_OLD.value == "new_vs_old"
        assert MatchupMode.CROSS_TYPE.value == "cross_type"

    def test_from_string(self):
        assert MatchupMode("mirror") is MatchupMode.MIRROR
        assert MatchupMode("new_vs_old") is MatchupMode.NEW_VS_OLD
        assert MatchupMode("cross_type") is MatchupMode.CROSS_TYPE

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            MatchupMode("invalid")


# ─── MatchupConfig tests ───────────────────────────────────────────


class TestMatchupConfig:
    def test_defaults(self):
        cfg = MatchupConfig()
        assert cfg.mode == MatchupMode.NEW_VS_OLD
        assert cfg.games_per_pair == 5
        assert cfg.max_ticks == 10000
        assert cfg.mirror_enabled is True

    def test_custom_mode(self):
        cfg = MatchupConfig(mode=MatchupMode.MIRROR)
        assert cfg.mode == MatchupMode.MIRROR

    def test_mode_coercion_from_string(self):
        cfg = MatchupConfig(mode="cross_type")
        assert cfg.mode == MatchupMode.CROSS_TYPE


# ─── MatchupResult tests ───────────────────────────────────────────


class TestMatchupResult:
    def test_init(self):
        r = MatchupResult(player1="a", player2="b", winner=1)
        assert r.player1 == "a"
        assert r.player2 == "b"
        assert r.winner == 1
        assert r.mode == MatchupMode.MIRROR

    def test_mode_coercion_from_string(self):
        r = MatchupResult(player1="a", player2="b", winner=0, mode="new_vs_old")
        assert r.mode == MatchupMode.NEW_VS_OLD


# ─── ELO rating tests ──────────────────────────────────────────────


class TestExpectedScore:
    def test_equal_ratings(self):
        ea = _expected_score(1000.0, 1000.0)
        assert abs(ea - 0.5) < 1e-9

    def test_higher_rating_favored(self):
        ea = _expected_score(1200.0, 1000.0)
        assert ea > 0.5

    def test_lower_rating_underdog(self):
        ea = _expected_score(800.0, 1000.0)
        assert ea < 0.5

    def test_symmetry(self):
        ea = _expected_score(1200.0, 1000.0)
        eb = _expected_score(1000.0, 1200.0)
        assert abs(ea + eb - 1.0) < 1e-9


class TestUpdateElo:
    def test_winner_a(self):
        a = VersionStats(name="a", elo=1000.0)
        b = VersionStats(name="b", elo=1000.0)
        update_elo(a, b, winner=1)
        assert a.elo > 1000.0
        assert b.elo < 1000.0
        assert a.wins == 1
        assert b.losses == 1
        assert a.games_played == 1
        assert b.games_played == 1

    def test_winner_b(self):
        a = VersionStats(name="a", elo=1000.0)
        b = VersionStats(name="b", elo=1000.0)
        update_elo(a, b, winner=2)
        assert a.elo < 1000.0
        assert b.elo > 1000.0
        assert a.losses == 1
        assert b.wins == 1

    def test_draw(self):
        a = VersionStats(name="a", elo=1000.0)
        b = VersionStats(name="b", elo=1000.0)
        update_elo(a, b, winner=0)
        assert a.elo == 1000.0
        assert b.elo == 1000.0
        assert a.draws == 1
        assert b.draws == 1

    def test_draw_with_different_ratings(self):
        """A draw between unequal players pulls both toward 1000."""
        a = VersionStats(name="a", elo=1200.0)
        b = VersionStats(name="b", elo=800.0)
        update_elo(a, b, winner=0)
        # A loses some ELO, B gains some on draw
        assert a.elo < 1200.0
        assert b.elo > 800.0

    def test_elo_conservatism_with_large_gap(self):
        """Upset: a much lower rated player wins → big ELO swing."""
        a = VersionStats(name="a", elo=800.0)
        b = VersionStats(name="b", elo=1200.0)
        update_elo(a, b, winner=1)
        # a gains more than usual since b was heavily favored
        gain_a = a.elo - 800.0
        loss_b = 1200.0 - b.elo
        assert gain_a > 16  # more than half the default k-factor
        assert abs(gain_a - loss_b) < 1e-9  # conservation

    def test_custom_k_factor(self):
        a = VersionStats(name="a", elo=1000.0)
        b = VersionStats(name="b", elo=1000.0)
        update_elo(a, b, winner=1, k_factor=64.0)
        # With equal ratings, expected=0.5, winner gets k*(1-0.5)=32
        assert abs(a.elo - 1032.0) < 1e-9
        assert abs(b.elo - 968.0) < 1e-9

    def test_multiple_games_accumulate(self):
        a = VersionStats(name="a", elo=1000.0)
        b = VersionStats(name="b", elo=1000.0)
        update_elo(a, b, winner=1)
        update_elo(a, b, winner=1)
        update_elo(a, b, winner=2)
        assert a.games_played == 3
        assert b.games_played == 3
        assert a.wins == 2
        assert a.losses == 1
        assert b.wins == 1
        assert b.losses == 2
        # a should be above 1000 after 2 wins and 1 loss from equal start
        assert a.elo > 1000.0


# ─── LeaguePool tests ──────────────────────────────────────────────


class TestLeaguePool:
    def _make_version(self, name: str, type_: AgentType = AgentType.SCRIPT, tick: int = 0):
        return AgentVersion(name=name, type=type_, creation_tick=tick)

    def test_add_version(self):
        pool = LeaguePool()
        v = self._make_version("v1", AgentType.SCRIPT, 10)
        pool.add_version(v)
        assert len(pool) == 1
        assert "v1" in pool

    def test_add_duplicate_raises(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("v1"))
        with pytest.raises(ValueError, match="already exists"):
            pool.add_version(self._make_version("v1"))

    def test_remove_version(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("v1"))
        removed = pool.remove_version("v1")
        assert removed.name == "v1"
        assert len(pool) == 0

    def test_remove_nonexistent_raises(self):
        pool = LeaguePool()
        with pytest.raises(KeyError, match="not found"):
            pool.remove_version("nonexistent")

    def test_get_all_versions_sorted(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("v3", tick=30))
        pool.add_version(self._make_version("v1", tick=10))
        pool.add_version(self._make_version("v2", tick=20))
        all_v = pool.get_all_versions()
        assert [v.name for v in all_v] == ["v1", "v2", "v3"]

    def test_get_latest(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("v1", tick=10))
        pool.add_version(self._make_version("v2", tick=20))
        latest = pool.get_latest()
        assert latest is not None
        assert latest.name == "v2"

    def test_get_latest_empty_pool(self):
        pool = LeaguePool()
        assert pool.get_latest() is None

    def test_get_by_name(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("v1"))
        v = pool.get_by_name("v1")
        assert v is not None
        assert v.name == "v1"

    def test_get_by_name_not_found(self):
        pool = LeaguePool()
        assert pool.get_by_name("nonexistent") is None

    def test_get_by_type(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("s1", AgentType.SCRIPT, 10))
        pool.add_version(self._make_version("c1", AgentType.COORDINATOR, 20))
        pool.add_version(self._make_version("s2", AgentType.SCRIPT, 30))
        scripts = pool.get_by_type(AgentType.SCRIPT)
        assert len(scripts) == 2
        assert all(v.type == AgentType.SCRIPT for v in scripts)

    def test_get_by_type_string(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("s1", AgentType.SCRIPT, 10))
        scripts = pool.get_by_type("script")
        assert len(scripts) == 1

    def test_get_by_type_empty(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("c1", AgentType.COORDINATOR, 10))
        scripts = pool.get_by_type(AgentType.SCRIPT)
        assert scripts == []

    def test_len(self):
        pool = LeaguePool()
        assert len(pool) == 0
        pool.add_version(self._make_version("v1"))
        assert len(pool) == 1

    def test_contains(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("v1"))
        assert "v1" in pool
        assert "v2" not in pool

    def test_iter(self):
        pool = LeaguePool()
        pool.add_version(self._make_version("v2", tick=20))
        pool.add_version(self._make_version("v1", tick=10))
        names = [v.name for v in pool]
        assert names == ["v1", "v2"]


# ─── League integration tests ───────────────────────────────────────


class TestLeagueRegister:
    """Test League.register / deregister / get_stats / get_elo."""

    def test_register_and_stats_initialized(self):
        league = League()
        v = AgentVersion(name="v1", type=AgentType.SCRIPT, creation_tick=10)
        league.register(v)
        stats = league.get_stats("v1")
        assert stats.elo == 1000.0
        assert stats.games_played == 0

    def test_register_duplicate_raises(self):
        league = League()
        league.register(AgentVersion(name="v1", type=AgentType.SCRIPT))
        with pytest.raises(ValueError):
            league.register(AgentVersion(name="v1", type=AgentType.COORDINATOR))

    def test_deregister(self):
        league = League()
        league.register(AgentVersion(name="v1", type=AgentType.SCRIPT))
        removed = league.deregister("v1")
        assert removed.name == "v1"
        assert len(league.pool) == 0

    def test_get_stats_unknown_raises(self):
        league = League()
        with pytest.raises(KeyError):
            league.get_stats("unknown")

    def test_get_elo_unknown_returns_zero(self):
        league = League()
        assert league.get_elo("unknown") == 0.0

    def test_get_leaderboard(self):
        league = League()
        league.register(AgentVersion(name="v1", type=AgentType.SCRIPT))
        league.register(AgentVersion(name="v2", type=AgentType.SCRIPT))
        # Manipulate ELO directly
        league._stats["v1"].elo = 1100.0
        league._stats["v2"].elo = 1050.0
        board = league.get_leaderboard()
        assert board[0].name == "v1"
        assert board[1].name == "v2"


class TestLeagueRecordResult:
    """Test League.record_result and ELO updates."""

    def _make_league_with_two(self) -> League:
        league = League()
        league.register(AgentVersion(name="v1", type=AgentType.SCRIPT, creation_tick=10))
        league.register(AgentVersion(name="v2", type=AgentType.SCRIPT, creation_tick=20))
        return league

    def test_record_winner_1(self):
        league = self._make_league_with_two()
        league.record_result(MatchupResult(player1="v1", player2="v2", winner=1))
        assert league.get_elo("v1") > 1000.0
        assert league.get_elo("v2") < 1000.0
        assert league.total_games == 1

    def test_record_winner_2(self):
        league = self._make_league_with_two()
        league.record_result(MatchupResult(player1="v1", player2="v2", winner=2))
        assert league.get_elo("v1") < 1000.0
        assert league.get_elo("v2") > 1000.0

    def test_record_draw(self):
        league = self._make_league_with_two()
        league.record_result(MatchupResult(player1="v1", player2="v2", winner=0))
        assert league.get_elo("v1") == 1000.0
        assert league.get_elo("v2") == 1000.0

    def test_record_results_batch(self):
        league = self._make_league_with_two()
        results = [
            MatchupResult(player1="v1", player2="v2", winner=1),
            MatchupResult(player1="v1", player2="v2", winner=1),
            MatchupResult(player1="v1", player2="v2", winner=2),
        ]
        league.record_results(results)
        assert league.total_games == 3
        assert league.get_stats("v1").wins == 2
        assert league.get_stats("v1").losses == 1

    def test_record_result_unknown_player_raises(self):
        league = self._make_league_with_two()
        with pytest.raises(KeyError, match="No stats"):
            league.record_result(
                MatchupResult(player1="v1", player2="unknown", winner=1)
            )

    def test_history_tracking(self):
        league = self._make_league_with_two()
        r = MatchupResult(player1="v1", player2="v2", winner=1)
        league.record_result(r)
        assert len(league.history) == 1
        assert league.history[0] == r


class TestLeagueGenerateMatchups:
    """Test League.generate_matchups across all three modes."""

    def _make_league(self) -> League:
        league = League()
        league.register(AgentVersion(name="s1", type=AgentType.SCRIPT, creation_tick=10))
        league.register(AgentVersion(name="s2", type=AgentType.SCRIPT, creation_tick=20))
        league.register(AgentVersion(name="c1", type=AgentType.COORDINATOR, creation_tick=30))
        return league

    def test_mirror_mode(self):
        league = self._make_league()
        matchups = league.generate_matchups(MatchupConfig(mode=MatchupMode.MIRROR, games_per_pair=2))
        # 3 versions × 2 games = 6
        assert len(matchups) == 6
        assert all(m["mode"] == "mirror" for m in matchups)
        # Each matchup: p1_version == p2_version
        assert all(m["player1_version"] == m["player2_version"] for m in matchups)

    def test_mirror_disabled(self):
        league = self._make_league()
        cfg = MatchupConfig(mode=MatchupMode.MIRROR, mirror_enabled=False)
        matchups = league.generate_matchups(cfg)
        assert matchups == []

    def test_new_vs_old_mode(self):
        league = self._make_league()
        matchups = league.generate_matchups(
            MatchupConfig(mode=MatchupMode.NEW_VS_OLD, games_per_pair=3)
        )
        # s1 has no predecessor → skip
        # s2 has predecessor s1 → 3 games
        # c1 has no predecessor of same type → skip
        # Total: 3 matchups
        assert len(matchups) == 3
        assert all(m["mode"] == "new_vs_old" for m in matchups)

    def test_new_vs_old_picks_best_predecessor(self):
        """When a version has multiple predecessors, it plays the best by ELO."""
        league = League()
        league.register(AgentVersion(name="s1", type=AgentType.SCRIPT, creation_tick=10))
        league.register(AgentVersion(name="s2", type=AgentType.SCRIPT, creation_tick=20))
        league.register(AgentVersion(name="s3", type=AgentType.SCRIPT, creation_tick=30))
        # s2 beats s1, so s2 ELO > s1 ELO
        league.record_result(MatchupResult(player1="s2", player2="s1", winner=1))
        matchups = league.generate_matchups(
            MatchupConfig(mode=MatchupMode.NEW_VS_OLD, games_per_pair=1)
        )
        # s1 has no predecessor → skip
        # s2 has predecessor s1 → 1 game
        # s3 has predecessors s1, s2; best by ELO is s2 → 1 game
        assert len(matchups) == 2
        s3_matchup = [m for m in matchups if m["player1_version"] == "s3"][0]
        assert s3_matchup["player2_version"] == "s2"

    def test_cross_type_mode(self):
        league = self._make_league()
        matchups = league.generate_matchups(
            MatchupConfig(mode=MatchupMode.CROSS_TYPE, games_per_pair=2)
        )
        # Cross-type pairs (different type): (s1,c1), (s2,c1) = 2 pairs × 2 games = 4
        assert len(matchups) == 4
        assert all(m["mode"] == "cross_type" for m in matchups)
        # Ensure no same-type matchups
        for m in matchups:
            assert m["player1_type"] != m["player2_type"]

    def test_default_config(self):
        league = self._make_league()
        matchups = league.generate_matchups()  # default: NEW_VS_OLD
        assert len(matchups) > 0


class TestLeagueSummaryAndLeaderboard:
    """Test League.summary() and format_leaderboard()."""

    def test_empty_league(self):
        league = League()
        assert "no versions" in league.format_leaderboard().lower()

    def test_non_empty_leaderboard(self):
        league = League()
        league.register(AgentVersion(name="v1", type=AgentType.SCRIPT))
        text = league.format_leaderboard()
        assert "v1" in text

    def test_summary_dict(self):
        league = League()
        league.register(AgentVersion(name="v1", type=AgentType.SCRIPT))
        s = league.summary()
        assert s["versions"] == 1
        assert s["total_games"] == 0
        assert "leaderboard" in s


class TestLeagueIntegration:
    """Full integration: register → generate matchups → record results → verify ELO."""

    def test_full_new_vs_old_cycle(self):
        league = League()
        v1 = AgentVersion(name="script-v1", type=AgentType.SCRIPT, creation_tick=0)
        v2 = AgentVersion(name="script-v2", type=AgentType.SCRIPT, creation_tick=100)
        v3 = AgentVersion(name="coord-v1", type=AgentType.COORDINATOR, creation_tick=200)

        league.register(v1)
        league.register(v2)
        league.register(v3)

        # Generate new-vs-old matchups
        matchups = league.generate_matchups(
            MatchupConfig(mode=MatchupMode.NEW_VS_OLD, games_per_pair=5)
        )
        # script-v2 vs script-v1 (best predecessor) → 5 games
        # coord-v1 has no predecessor of same type → skip
        assert len(matchups) == 5
        assert all(m["player1_version"] == "script-v2" for m in matchups)
        assert all(m["player2_version"] == "script-v1" for m in matchups)

        # Simulate v2 winning all 5
        for _ in range(5):
            league.record_result(
                MatchupResult(player1="script-v2", player2="script-v1", winner=1)
            )

        # v2 should have higher ELO than v1
        assert league.get_elo("script-v2") > league.get_elo("script-v1")
        assert league.get_stats("script-v2").wins == 5
        assert league.get_stats("script-v1").losses == 5

    def test_full_mirror_cycle(self):
        league = League()
        league.register(AgentVersion(name="v1", type=AgentType.SCRIPT, creation_tick=0))
        league.register(AgentVersion(name="v2", type=AgentType.COORDINATOR, creation_tick=100))

        matchups = league.generate_matchups(
            MatchupConfig(mode=MatchupMode.MIRROR, games_per_pair=3)
        )
        assert len(matchups) == 6  # 2 versions × 3 games

        # Record draws for all mirror matches
        for m in matchups:
            league.record_result(
                MatchupResult(player1=m["player1_version"], player2=m["player2_version"], winner=0)
            )

        # All draws from equal starting ELO → still 1000
        assert league.get_elo("v1") == 1000.0
        assert league.get_elo("v2") == 1000.0
        assert league.total_games == 6

    def test_full_cross_type_cycle(self):
        league = League()
        league.register(AgentVersion(name="s1", type=AgentType.SCRIPT, creation_tick=0))
        league.register(AgentVersion(name="c1", type=AgentType.COORDINATOR, creation_tick=100))
        league.register(AgentVersion(name="g1", type=AgentType.GRPO, creation_tick=200))

        matchups = league.generate_matchups(
            MatchupConfig(mode=MatchupMode.CROSS_TYPE, games_per_pair=2)
        )
        # Cross-type pairs: (s1,c1), (s1,g1), (c1,g1) = 3 pairs × 2 = 6
        assert len(matchups) == 6

        # Script always wins
        for m in matchups:
            if m["player1_version"] == "s1":
                league.record_result(
                    MatchupResult(player1="s1", player2=m["player2_version"], winner=1)
                )
            elif m["player2_version"] == "s1":
                league.record_result(
                    MatchupResult(player1=m["player1_version"], player2="s1", winner=2)
                )
            else:
                # c1 vs g1 — draw
                league.record_result(
                    MatchupResult(player1=m["player1_version"], player2=m["player2_version"], winner=0)
                )

        # s1 should have highest ELO
        board = league.get_leaderboard()
        assert board[0].name == "s1"
        assert league.total_games == 6