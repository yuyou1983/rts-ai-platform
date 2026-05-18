"""Tests for harness.scheduler — AgentVersion, MatchMode, LeagueScheduler."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.scheduler import (
    AgentVersion,
    LeagueScheduler,
    MatchMode,
    VersionStats,
    LeagueStats,
    _generate_focused,
    _generate_random_sample,
    _generate_round_robin,
)
from harness.pool import MatchConfig, MatchResult


# ─── AgentVersion tests ─────────────────────────────────────────────


class TestAgentVersion:
    """Test AgentVersion dataclass and key property."""

    def test_init(self):
        v = AgentVersion(agent_type="coordinator", version="v0.3")
        assert v.agent_type == "coordinator"
        assert v.version == "v0.3"
        assert v.registered_at == 0.0
        assert v.metadata == {}

    def test_key_property(self):
        v = AgentVersion(agent_type="coordinator", version="v0.3")
        assert v.key == "coordinator@v0.3"

    def test_key_with_different_types(self):
        v1 = AgentVersion(agent_type="script", version="v1.0")
        v2 = AgentVersion(agent_type="coordinator", version="v1.0")
        assert v1.key == "script@v1.0"
        assert v2.key == "coordinator@v1.0"
        assert v1.key != v2.key

    def test_hash_and_equality(self):
        v1 = AgentVersion(agent_type="coordinator", version="v0.3")
        v2 = AgentVersion(agent_type="coordinator", version="v0.3")
        v3 = AgentVersion(agent_type="coordinator", version="v0.4")
        assert v1 == v2
        assert v1 != v3
        assert hash(v1) == hash(v2)

    def test_equality_not_implemented_for_other_types(self):
        v = AgentVersion(agent_type="coordinator", version="v0.3")
        assert v.__eq__("not_a_version") is NotImplemented

    def test_metadata_default(self):
        v = AgentVersion(agent_type="coordinator", version="v0.3", metadata={"lr": 0.001})
        assert v.metadata == {"lr": 0.001}

    def test_registered_at(self):
        v = AgentVersion(agent_type="coordinator", version="v0.3", registered_at=100.0)
        assert v.registered_at == 100.0


# ─── MatchMode tests ─────────────────────────────────────────────────


class TestMatchMode:
    """Test MatchMode enum values."""

    def test_round_robin(self):
        assert MatchMode.ROUND_ROBIN.value == "round_robin"

    def test_random_sample(self):
        assert MatchMode.RANDOM_SAMPLE.value == "random_sample"

    def test_focused(self):
        assert MatchMode.FOCUSED.value == "focused"

    def test_from_string(self):
        assert MatchMode("round_robin") is MatchMode.ROUND_ROBIN
        assert MatchMode("random_sample") is MatchMode.RANDOM_SAMPLE
        assert MatchMode("focused") is MatchMode.FOCUSED

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            MatchMode("invalid_mode")

    def test_enum_members_count(self):
        assert len(MatchMode) == 3


# ─── Round-robin generator tests ─────────────────────────────────────


class TestGenerateRoundRobin:
    """Test _generate_round_robin directly."""

    def _make_versions(self, n: int) -> list[AgentVersion]:
        return [
            AgentVersion(agent_type=f"type{i}", version=f"v{i}", registered_at=float(i))
            for i in range(n)
        ]

    def test_two_versions(self):
        versions = self._make_versions(2)
        configs = _generate_round_robin(versions, maps=[42], repeats=1, max_ticks=5000)
        # permutations of 2 = 2 ordered pairs: (0,1), (1,0) × 1 map × 1 repeat = 2
        assert len(configs) == 2
        assert all(isinstance(c, MatchConfig) for c in configs)

    def test_three_versions(self):
        versions = self._make_versions(3)
        configs = _generate_round_robin(versions, maps=[42], repeats=1, max_ticks=5000)
        # permutations of 3 = 6 × 1 map × 1 repeat = 6
        assert len(configs) == 6

    def test_multiple_maps(self):
        versions = self._make_versions(2)
        configs = _generate_round_robin(versions, maps=[42, 99], repeats=1, max_ticks=5000)
        # 2 permutations × 2 maps × 1 repeat = 4
        assert len(configs) == 4

    def test_multiple_repeats(self):
        versions = self._make_versions(2)
        configs = _generate_round_robin(versions, maps=[42], repeats=3, max_ticks=5000)
        # 2 permutations × 1 map × 3 repeats = 6
        assert len(configs) == 6

    def test_empty_versions(self):
        configs = _generate_round_robin([], maps=[42], repeats=1, max_ticks=5000)
        assert configs == []

    def test_single_version(self):
        configs = _generate_round_robin(
            [AgentVersion(agent_type="a", version="v1")],
            maps=[42],
            repeats=1,
            max_ticks=5000,
        )
        # permutations of 1 = 0 ordered pairs
        assert configs == []

    def test_max_ticks_propagated(self):
        versions = self._make_versions(2)
        configs = _generate_round_robin(versions, maps=[42], repeats=1, max_ticks=9999)
        assert all(c.max_ticks == 9999 for c in configs)


# ─── Random sample generator tests ────────────────────────────────────


class TestGenerateRandomSample:
    """Test _generate_random_sample directly."""

    def _make_versions(self, n: int) -> list[AgentVersion]:
        return [
            AgentVersion(agent_type=f"type{i}", version=f"v{i}", registered_at=float(i))
            for i in range(n)
        ]

    def test_sample_smaller_than_full(self):
        import random
        versions = self._make_versions(4)
        rng = random.Random(42)
        configs = _generate_random_sample(
            versions, maps=[42, 99], repeats=1, max_ticks=5000, sample_count=5, rng=rng,
        )
        assert len(configs) == 5

    def test_sample_exceeds_full_returns_all(self):
        import random
        versions = self._make_versions(2)
        rng = random.Random(42)
        configs = _generate_random_sample(
            versions, maps=[42], repeats=1, max_ticks=5000, sample_count=999, rng=rng,
        )
        # full set is 2 permutations × 1 map × 1 repeat = 2
        assert len(configs) == 2

    def test_empty_versions(self):
        import random
        rng = random.Random(42)
        configs = _generate_random_sample(
            [], maps=[42], repeats=1, max_ticks=5000, sample_count=5, rng=rng,
        )
        assert configs == []


# ─── Focused generator tests ─────────────────────────────────────────


class TestGenerateFocused:
    """Test _generate_focused directly."""

    def test_empty_versions(self):
        configs = _generate_focused([], maps=[42], repeats=1, max_ticks=5000, focus_count=3)
        assert configs == []

    def test_all_newest_round_robin(self):
        """When focus_count >= len(versions), it's a full round-robin among all."""
        versions = [
            AgentVersion(agent_type="a", version="v1", registered_at=1.0),
            AgentVersion(agent_type="a", version="v2", registered_at=2.0),
        ]
        configs = _generate_focused(versions, maps=[42], repeats=1, max_ticks=5000, focus_count=3)
        # All are "newest" → round-robin among 2 = 2 permutations × 1 map × 1 repeat = 2
        assert len(configs) == 2

    def test_older_vs_newest(self):
        """Older versions play each newest version in both directions."""
        versions = [
            AgentVersion(agent_type="a", version="v1", registered_at=1.0),
            AgentVersion(agent_type="a", version="v2", registered_at=2.0),
            AgentVersion(agent_type="a", version="v3", registered_at=3.0),
        ]
        configs = _generate_focused(versions, maps=[42], repeats=1, max_ticks=5000, focus_count=1)
        # newest = [v3], older = [v1, v2]
        # round-robin among newest: 0 permutations (only 1 version)
        # each older vs each newest: 2 older × 1 newest × 1 map × 1 repeat × 2 directions = 4
        assert len(configs) == 4

    def test_multiple_maps_repeats(self):
        versions = [
            AgentVersion(agent_type="a", version="v1", registered_at=1.0),
            AgentVersion(agent_type="a", version="v2", registered_at=2.0),
            AgentVersion(agent_type="a", version="v3", registered_at=3.0),
        ]
        configs = _generate_focused(
            versions, maps=[42, 99], repeats=2, max_ticks=5000, focus_count=1,
        )
        # round-robin among newest (v3): 0
        # 2 older × 1 newest × 2 maps × 2 repeats × 2 directions = 16
        assert len(configs) == 16


# ─── LeagueScheduler tests ──────────────────────────────────────────


class TestLeagueSchedulerRegister:
    """Test LeagueScheduler register / unregister / versions."""

    def test_register_single(self):
        ls = LeagueScheduler()
        v = ls.register("coordinator", "v0.3")
        assert v.key == "coordinator@v0.3"
        assert ls.versions == [v]
        assert ls.version_keys == ["coordinator@v0.3"]

    def test_register_multiple(self):
        ls = LeagueScheduler()
        v1 = ls.register("coordinator", "v0.3")
        v2 = ls.register("coordinator", "v0.4")
        v3 = ls.register("script", "v1.0")
        assert len(ls.versions) == 3
        assert ls.version_keys == [
            "coordinator@v0.3",
            "coordinator@v0.4",
            "script@v1.0",
        ]

    def test_register_duplicate_preserves_timestamp(self):
        ls = LeagueScheduler()
        v1 = ls.register("coordinator", "v0.3")
        original_ts = v1.registered_at
        v2 = ls.register("coordinator", "v0.3", metadata={"extra": True})
        assert v2.registered_at == original_ts
        assert v2.metadata.get("extra") is True

    def test_unregister_existing(self):
        ls = LeagueScheduler()
        ls.register("coordinator", "v0.3")
        ls.register("coordinator", "v0.4")
        result = ls.unregister("coordinator", "v0.3")
        assert result is True
        assert ls.version_keys == ["coordinator@v0.4"]

    def test_unregister_nonexistent(self):
        ls = LeagueScheduler()
        result = ls.unregister("coordinator", "v0.3")
        assert result is False

    def test_versions_property_after_unregister(self):
        ls = LeagueScheduler()
        ls.register("coordinator", "v0.3")
        ls.register("script", "v1.0")
        ls.unregister("coordinator", "v0.3")
        assert len(ls.versions) == 1
        assert ls.versions[0].agent_type == "script"


class TestLeagueSchedulerGenerateSchedule:
    """Test LeagueScheduler.generate_schedule across all three modes."""

    def _make_scheduler(self) -> LeagueScheduler:
        ls = LeagueScheduler(maps=[42, 99], max_ticks=5000, seed=42)
        ls.register("coordinator", "v0.3")
        ls.register("coordinator", "v0.4")
        ls.register("script", "v1.0")
        return ls

    def test_round_robin_mode(self):
        ls = self._make_scheduler()
        configs = ls.generate_schedule(mode="round_robin", repeats=1)
        # 3 versions → permutations(3,2) = 6 × 2 maps × 1 repeat = 12
        assert len(configs) == 12
        assert all(isinstance(c, MatchConfig) for c in configs)

    def test_round_robin_enum_mode(self):
        ls = self._make_scheduler()
        configs = ls.generate_schedule(mode=MatchMode.ROUND_ROBIN, repeats=1)
        assert len(configs) == 12

    def test_random_sample_mode(self):
        ls = self._make_scheduler()
        configs = ls.generate_schedule(mode="random_sample", repeats=1, sample_count=5)
        assert len(configs) == 5

    def test_random_sample_returns_all_if_small(self):
        ls = self._make_scheduler()
        configs = ls.generate_schedule(mode="random_sample", repeats=1, sample_count=999)
        assert len(configs) == 12  # same as round_robin total

    def test_focused_mode(self):
        ls = self._make_scheduler()
        configs = ls.generate_schedule(mode="focused", repeats=1, focus_count=1)
        assert len(configs) > 0
        assert all(isinstance(c, MatchConfig) for c in configs)

    def test_insufficient_versions_returns_empty(self):
        ls = LeagueScheduler()
        ls.register("coordinator", "v0.3")
        configs = ls.generate_schedule(mode="round_robin")
        assert configs == []

    def test_no_versions_returns_empty(self):
        ls = LeagueScheduler()
        configs = ls.generate_schedule(mode="round_robin")
        assert configs == []

    def test_invalid_mode_raises(self):
        ls = self._make_scheduler()
        with pytest.raises(ValueError):
            ls.generate_schedule(mode="nonexistent_mode")

    def test_repeats_multiplies_configs(self):
        ls = self._make_scheduler()
        configs_r1 = ls.generate_schedule(mode="round_robin", repeats=1)
        configs_r2 = ls.generate_schedule(mode="round_robin", repeats=2)
        assert len(configs_r2) == len(configs_r1) * 2


class TestLeagueSchedulerRunWithMock:
    """Test LeagueScheduler.run() with mocked SimulationPool to avoid real matches."""

    def _make_scheduler(self) -> LeagueScheduler:
        ls = LeagueScheduler(maps=[42], max_ticks=500, seed=42)
        ls.register("coordinator", "v0.3")
        ls.register("script", "v1.0")
        return ls

    @pytest.mark.asyncio
    async def test_run_round_robin_mock(self):
        ls = self._make_scheduler()
        mock_result = MatchResult(
            match_id="mock1", winner=1, ticks=500, elapsed=1.0, tps=500.0,
        )

        with patch("harness.scheduler.SimulationPool") as MockPool, \
             patch("harness.scheduler.MatchScheduler") as MockMatchScheduler:
            mock_pool_instance = MagicMock()
            mock_pool_instance.run_all = AsyncMock(return_value=[mock_result])
            MockPool.return_value = mock_pool_instance

            results = await ls.run(mode="round_robin", repeats=1)

            assert len(results) == 1
            assert results[0].winner == 1
            MockPool.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_empty_schedule(self):
        """If <2 versions, run should return empty list without error."""
        ls = LeagueScheduler()
        ls.register("coordinator", "v0.3")
        results = await ls.run(mode="round_robin")
        assert results == []
        assert ls.stats is not None
        assert ls.stats.total_matches == 0


class TestLeagueSchedulerSummary:
    """Test LeagueScheduler.summary() and to_dict()."""

    def test_summary_before_run(self):
        ls = LeagueScheduler()
        assert ls.summary() == "No league has been run yet."

    def test_to_dict_before_run(self):
        ls = LeagueScheduler()
        d = ls.to_dict()
        assert d == {"status": "not_run"}