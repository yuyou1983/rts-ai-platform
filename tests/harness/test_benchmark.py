"""Tests for benchmark runner and statistics."""


from harness.benchmark import MatchResult, compute_stats, format_report


class TestBenchmarkStats:
    def test_empty_results(self):
        stats = compute_stats([])
        assert stats.total_games == 0
        assert stats.p1_wins == 0
        assert stats.win_rate_p1 == 0.0

    def test_p1_sweep(self):
        results = [
            MatchResult(match_id=f"m{i}", winner=1, ticks=100 * i + 50, tps=5000.0, elapsed=0.01 * i)
            for i in range(10)
        ]
        stats = compute_stats(results)
        assert stats.total_games == 10
        assert stats.p1_wins == 10
        assert stats.p2_wins == 0
        assert stats.win_rate_p1 == 1.0

    def test_mixed_results(self):
        results = [
            MatchResult(match_id="m1", winner=1, ticks=200, tps=4000.0, elapsed=0.05),
            MatchResult(match_id="m2", winner=2, ticks=300, tps=5000.0, elapsed=0.06),
            MatchResult(match_id="m3", winner=0, ticks=5000, tps=3000.0, elapsed=1.6),
            MatchResult(match_id="m4", winner=1, ticks=100, tps=6000.0, elapsed=0.02, error="crash"),
        ]
        stats = compute_stats(results)
        assert stats.total_games == 4
        assert stats.p1_wins == 1  # m1 only (m4 has error)
        assert stats.p2_wins == 1
        assert stats.draws == 1
        assert stats.errors == 1

    def test_tick_stats(self):
        results = [
            MatchResult(match_id="m1", winner=1, ticks=100, tps=1000.0, elapsed=0.1),
            MatchResult(match_id="m2", winner=1, ticks=200, tps=2000.0, elapsed=0.1),
            MatchResult(match_id="m3", winner=1, ticks=300, tps=3000.0, elapsed=0.1),
        ]
        stats = compute_stats(results)
        assert stats.avg_ticks == 200.0
        assert stats.peak_ticks == 300
        assert stats.shortest_ticks == 100
        assert stats.avg_tps == 2000.0


class TestFormatReport:
    def test_report_contains_key_info(self):
        results = [
            MatchResult(match_id="m1", winner=1, ticks=500, tps=5000.0, elapsed=0.1),
            MatchResult(match_id="m2", winner=2, ticks=600, tps=4000.0, elapsed=0.15),
        ]
        stats = compute_stats(results)
        report = format_report(stats, results)
        assert "Total Games:    2" in report
        assert "P1 Wins:        1" in report
        assert "Avg TPS" in report

    def test_report_shows_errors(self):
        results = [
            MatchResult(match_id="m1", winner=1, ticks=100, tps=1000.0, elapsed=0.1),
            MatchResult(match_id="m_err", winner=0, ticks=0, tps=0.0, elapsed=0.0, error="timeout"),
        ]
        stats = compute_stats(results)
        report = format_report(stats, results)
        assert "Errors:         1" in report
        assert "m_err" in report


class TestMatchScheduler:
    def test_round_robin_count(self):
        from harness.pool import MatchScheduler
        scheduler = MatchScheduler()
        count = scheduler.add_round_robin(
            agent_types=["coordinator", "script", "random"],
            maps=[42, 43],
            repeats=2,
        )
        # 3 agents × 2 maps × 2 repeats × (unique pairs including self)
        # Pairs: (coordinator, coordinator), (coordinator, script),
        #         (coordinator, random), (script, script),
        #         (script, random), (random, random) = 6 pairs
        # 6 pairs × 2 maps × 2 repeats = 24
        assert count == 24
        assert scheduler.pending == count
