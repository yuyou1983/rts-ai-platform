"""Tests for Harness layer — MatchScheduler + SimulationPool."""
import asyncio

from harness.pool import MatchConfig, MatchScheduler, SimulationPool


class TestMatchScheduler:
    def test_round_robin(self):
        s = MatchScheduler()
        n = s.add_round_robin(
            agent_types=["coordinator", "script", "random"],
            maps=[42, 99],
            repeats=2,
        )
        # pairs: (coord,coord), (coord,script), (coord,random),
        #        (script,script), (script,random), (random,random) = 6
        # × 2 maps × 2 repeats = 24
        assert n == 24
        assert s.pending == 24

    def test_seeded_bracket(self):
        s = MatchScheduler()
        n = s.add_seeded_bracket(
            agent_types=["coordinator", "script", "random", "zerg"],
            seeds=[42],
        )
        # pairs: (coord,script), (random,zerg) × 1 seed = 2
        assert n == 2
        assert s.pending == 2

    def test_custom(self):
        s = MatchScheduler()
        n = s.add_custom([
            MatchConfig(map_seed=1, max_ticks=100),
            MatchConfig(map_seed=2, max_ticks=200),
        ])
        assert n == 2

    def test_pop(self):
        s = MatchScheduler()
        s.add_custom([MatchConfig(map_seed=42)])
        cfg = s.pop()
        assert cfg is not None
        assert cfg.map_seed == 42
        assert s.pop() is None


class TestSimulationPool:
    def test_single_match(self):
        scheduler = MatchScheduler()
        scheduler.add_custom([MatchConfig(map_seed=42, max_ticks=100)])

        pool = SimulationPool(max_concurrent=1)
        results = asyncio.run(pool.run_all(scheduler))
        assert len(results) == 1
        assert results[0].ticks >= 0
        assert results[0].error is None

    def test_concurrent_matches(self):
        scheduler = MatchScheduler()
        scheduler.add_custom([
            MatchConfig(map_seed=10 + i, max_ticks=100)
            for i in range(4)
        ])

        pool = SimulationPool(max_concurrent=2)
        results = asyncio.run(pool.run_all(scheduler))
        assert len(results) == 4
        assert pool.stats["completed"] == 4
        assert pool.stats["failed"] == 0

    def test_round_robin_tournament(self):
        scheduler = MatchScheduler()
        scheduler.add_round_robin(
            agent_types=["coordinator", "script"],
            maps=[42],
            repeats=1,
            max_ticks=100,
        )
        # pairs: (coord,coord), (coord,script), (script,script) = 3 × 1 map × 1 = 3
        assert scheduler.pending == 3

        pool = SimulationPool(max_concurrent=2)
        results = asyncio.run(pool.run_all(scheduler))
        assert len(results) == 3
        assert pool.stats["completed"] == 3
