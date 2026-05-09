"""Batch benchmark runner — 100-game tournament with statistics.

Usage:
    python -m harness.benchmark --games 100 --concurrent 4 --seeds 42-141

Runs N games headlessly through SimCore, collects match results,
and produces a JSON report + console summary.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.pool import MatchResult, MatchScheduler, SimulationPool

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkStats:
    """Aggregate statistics from a batch of matches."""

    total_games: int = 0
    p1_wins: int = 0
    p2_wins: int = 0
    draws: int = 0
    errors: int = 0
    avg_ticks: float = 0.0
    avg_tps: float = 0.0
    avg_elapsed: float = 0.0
    win_rate_p1: float = 0.0
    win_rate_p2: float = 0.0
    peak_ticks: int = 0
    shortest_ticks: int = 0


def compute_stats(results: list[MatchResult]) -> BenchmarkStats:
    """Compute aggregate statistics from match results."""
    valid = [r for r in results if r.error is None]
    errored = [r for r in results if r.error is not None]

    stats = BenchmarkStats()
    stats.total_games = len(results)
    stats.errors = len(errored)
    stats.p1_wins = sum(1 for r in valid if r.winner == 1)
    stats.p2_wins = sum(1 for r in valid if r.winner == 2)
    stats.draws = sum(1 for r in valid if r.winner == 0)

    if valid:
        ticks_list = [r.ticks for r in valid]
        tps_list = [r.tps for r in valid]
        elapsed_list = [r.elapsed for r in valid]
        stats.avg_ticks = sum(ticks_list) / len(ticks_list)
        stats.avg_tps = sum(tps_list) / len(tps_list)
        stats.avg_elapsed = sum(elapsed_list) / len(elapsed_list)
        stats.peak_ticks = max(ticks_list)
        stats.shortest_ticks = min(ticks_list)

    total_valid = len(valid)
    if total_valid > 0:
        stats.win_rate_p1 = stats.p1_wins / total_valid
        stats.win_rate_p2 = stats.p2_wins / total_valid

    return stats


def format_report(stats: BenchmarkStats, results: list[MatchResult]) -> str:
    """Format a human-readable benchmark report."""
    lines = [
        "=" * 60,
        "  RTS AI Platform — Benchmark Report",
        "=" * 60,
        "",
        f"  Total Games:    {stats.total_games}",
        f"  P1 Wins:        {stats.p1_wins} ({stats.win_rate_p1:.1%})",
        f"  P2 Wins:        {stats.p2_wins} ({stats.win_rate_p2:.1%})",
        f"  Draws:          {stats.draws}",
        f"  Errors:         {stats.errors}",
        "",
        f"  Avg Ticks:      {stats.avg_ticks:.0f}",
        f"  Avg TPS:        {stats.avg_tps:.0f}",
        f"  Avg Elapsed:    {stats.avg_elapsed:.2f}s",
        f"  Peak Ticks:     {stats.peak_ticks}",
        f"  Shortest:       {stats.shortest_ticks} ticks",
        "",
        "=" * 60,
    ]

    # Show first 5 error details if any
    errored = [r for r in results if r.error is not None]
    if errored:
        lines.append("  Failed matches (first 5):")
        for r in errored[:5]:
            lines.append(f"    {r.match_id}: {r.error}")
        lines.append("")

    return "\n".join(lines)


async def run_benchmark(
    games: int = 100,
    concurrent: int = 4,
    seed_start: int = 42,
    p1_type: str = "coordinator",
    p2_type: str = "script",
    max_ticks: int = 10000,
    output_dir: str = "harness/output",
) -> dict[str, Any]:
    """Run a batch benchmark and return results + stats."""
    scheduler = MatchScheduler()

    seeds = list(range(seed_start, seed_start + games))
    agent_types = [p1_type, p2_type]

    count = scheduler.add_round_robin(
        agent_types=agent_types,
        maps=seeds,
        repeats=1,
        max_ticks=max_ticks,
    )
    logger.info("Queued %d matches", count)

    pool = SimulationPool(max_concurrent=concurrent)
    t0 = time.monotonic()
    results = await pool.run_all(scheduler)
    wall_time = time.monotonic() - t0

    stats = compute_stats(results)

    # Save outputs
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Full results JSON
    results_data = [
        {
            "match_id": r.match_id,
            "winner": r.winner,
            "ticks": r.ticks,
            "elapsed": r.elapsed,
            "tps": r.tps,
            "error": r.error,
        }
        for r in results
    ]
    with open(out_path / "benchmark_results.json", "w") as f:
        json.dump(results_data, f, indent=2)

    # Stats JSON
    with open(out_path / "benchmark_stats.json", "w") as f:
        json.dump(vars(stats), f, indent=2)

    # Human report
    report = format_report(stats, results)
    with open(out_path / "benchmark_report.txt", "w") as f:
        f.write(report)

    print(report)
    logger.info(
        "Benchmark complete: %d games in %.1fs (wall), avg TPS=%.0f",
        games, wall_time, stats.avg_tps,
    )

    return {"stats": vars(stats), "wall_time": wall_time}


def main() -> None:
    parser = argparse.ArgumentParser(description="RTS AI Benchmark Runner")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--concurrent", type=int, default=4)
    parser.add_argument("--seed-start", type=int, default=42)
    parser.add_argument("--p1", default="coordinator")
    parser.add_argument("--p2", default="script")
    parser.add_argument("--max-ticks", type=int, default=10000)
    parser.add_argument("--output-dir", default="harness/output")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    asyncio.run(
        run_benchmark(
            games=args.games,
            concurrent=args.concurrent,
            seed_start=args.seed_start,
            p1_type=args.p1,
            p2_type=args.p2,
            max_ticks=args.max_ticks,
            output_dir=args.output_dir,
        )
    )


if __name__ == "__main__":
    main()
