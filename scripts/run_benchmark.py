#!/usr/bin/env python3
"""Quick benchmark runner — 50 games script vs script."""
import asyncio
import time
import json
from pathlib import Path

from harness.pool import MatchScheduler, SimulationPool
from harness.benchmark import compute_stats, format_report


async def main():
    scheduler = MatchScheduler()
    seeds = list(range(42, 92))  # 50 games

    count = scheduler.add_round_robin(
        agent_types=["script", "script"],
        maps=seeds,
        repeats=1,
        max_ticks=5000,
    )
    print(f"Queued {count} matches")

    pool = SimulationPool(max_concurrent=4)
    t0 = time.monotonic()
    results = await pool.run_all(scheduler)
    wall = time.monotonic() - t0

    stats = compute_stats(results)

    out = Path("harness/output")
    out.mkdir(parents=True, exist_ok=True)

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
    with open(out / "benchmark_results.json", "w") as f:
        json.dump(results_data, f, indent=2)
    with open(out / "benchmark_stats.json", "w") as f:
        json.dump(vars(stats), f, indent=2)

    report = format_report(stats, results)
    with open(out / "benchmark_report.txt", "w") as f:
        f.write(report)

    print(report)
    print(f"Wall time: {wall:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())