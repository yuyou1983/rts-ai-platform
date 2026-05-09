"""Harness Layer — match scheduling + concurrent simulation pool.

Architecture:
  MatchScheduler  — creates match configurations, queues matches
  SimulationPool  — runs N matches concurrently via asyncio
  MatchResult      — per-match outcome + telemetry

This layer sits above SimCore and is engine-agnostic. It communicates
with SimCore through the AgentScope game loop (which uses SimCore internally)
or through the gRPC client for remote/multi-process setups.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agents.game_loop import AgentScopeGameLoop

logger = logging.getLogger(__name__)


@dataclass
class MatchConfig:
    """Configuration for a single match."""

    match_id: str = ""
    map_seed: int = 42
    max_ticks: int = 10000
    player1_type: str = "coordinator"  # coordinator | script | random
    player2_type: str = "script"

    def __post_init__(self) -> None:
        if not self.match_id:
            import shortuuid

            self.match_id = shortuuid.uuid()


@dataclass
class MatchResult:
    """Outcome of a single match."""

    match_id: str
    winner: int = 0
    ticks: int = 0
    elapsed: float = 0.0
    tps: float = 0.0
    replay: list[dict] = field(default_factory=list)
    error: str | None = None


class MatchScheduler:
    """Generates and queues match configurations.

    Supports:
    - Round-robin: every agent pair plays N times
    - Seeded bracket: seeded tournament with fixed seeds
    - Custom: user-supplied configs
    """

    def __init__(self) -> None:
        self._queue: list[MatchConfig] = []

    def add_round_robin(
        self,
        agent_types: list[str],
        maps: list[int],
        repeats: int = 1,
        max_ticks: int = 10000,
    ) -> int:
        """Add round-robin matches: each pair × each map × repeats."""
        count = 0
        for i, a1 in enumerate(agent_types):
            for a2 in agent_types[i:]:
                for seed in maps:
                    for r in range(repeats):
                        self._queue.append(
                            MatchConfig(
                                map_seed=seed + r,
                                max_ticks=max_ticks,
                                player1_type=a1,
                                player2_type=a2,
                            )
                        )
                        count += 1
        return count

    def add_seeded_bracket(
        self, agent_types: list[str], seeds: list[int], max_ticks: int = 10000
    ) -> int:
        """Add a single-elimination bracket (pairwise matchups)."""
        count = 0
        for i in range(0, len(agent_types), 2):
            if i + 1 < len(agent_types):
                for seed in seeds:
                    self._queue.append(
                        MatchConfig(
                            map_seed=seed,
                            max_ticks=max_ticks,
                            player1_type=agent_types[i],
                            player2_type=agent_types[i + 1],
                        )
                    )
                    count += 1
        return count

    def add_custom(self, configs: list[MatchConfig]) -> int:
        """Add user-supplied match configurations."""
        self._queue.extend(configs)
        return len(configs)

    @property
    def pending(self) -> int:
        return len(self._queue)

    def pop(self) -> MatchConfig | None:
        return self._queue.pop(0) if self._queue else None


class SimulationPool:
    """Runs matches concurrently with bounded parallelism.

    Usage::

        pool = SimulationPool(max_concurrent=4)
        results = await pool.run_all(scheduler)
    """

    def __init__(self, max_concurrent: int = 4) -> None:
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: list[MatchResult] = []
        self._completed = 0
        self._failed = 0

    async def run_match(self, config: MatchConfig) -> MatchResult:
        """Run a single match under the semaphore."""
        async with self._semaphore:
            try:
                loop = AgentScopeGameLoop(
                    map_seed=config.map_seed, max_ticks=config.max_ticks
                )
                t0 = time.monotonic()
                outcome = await loop.run()
                elapsed = time.monotonic() - t0
                result = MatchResult(
                    match_id=config.match_id,
                    winner=outcome["winner"],
                    ticks=outcome["ticks"],
                    elapsed=elapsed,
                    tps=outcome["tps"],
                    replay=outcome["replay"],
                )
                self._completed += 1
                logger.info(
                    "Match %s done: winner=%d ticks=%d tps=%.0f",
                    config.match_id,
                    result.winner,
                    result.ticks,
                    result.tps,
                )
            except Exception as exc:
                self._failed += 1
                result = MatchResult(
                    match_id=config.match_id, error=str(exc)
                )
                logger.error("Match %s failed: %s", config.match_id, exc)
        self._results.append(result)
        return result

    async def run_all(self, scheduler: MatchScheduler) -> list[MatchResult]:
        """Drain the scheduler and run all matches concurrently."""
        tasks: list[asyncio.Task[MatchResult]] = []
        while config := scheduler.pop():
            tasks.append(asyncio.create_task(self.run_match(config)))
        if tasks:
            await asyncio.gather(*tasks)
        return list(self._results)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "completed": self._completed,
            "failed": self._failed,
            "total": len(self._results),
        }
