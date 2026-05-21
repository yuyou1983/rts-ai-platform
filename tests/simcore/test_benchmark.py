"""SimCore Performance Benchmark — Baseline Reference for Future Phases.

This module records baseline tick-throughput numbers for the headless SimCore
engine running empty (no-command) steps. The generous time thresholds are
intentionally loose — they serve as regression safety nets, not strict
performance targets. If a future phase introduces changes that push execution
time beyond these bounds, the failing test signals a potential performance
regression worth investigating.

Thresholds:
  • 1 000 empty ticks  < 3.0 s   (≈ 3 ms / tick)
  • 10 000 empty ticks < 30.0 s  (≈ 3 ms / tick)

These baselines were recorded on a typical development machine. CI runners
may be slower, so thresholds may need upward adjustment if false failures
appear in CI.
"""
from __future__ import annotations

import time

from simcore.engine import SimCore


class TestPerformanceBenchmark:
    """Tick-throughput regression tests for SimCore."""

    def test_1k_ticks_performance(self) -> None:
        """Run 1 000 empty ticks and assert total wall-clock time < 3.0 s."""
        engine = SimCore()
        engine.initialize(map_seed=42)

        start = time.time()
        for _ in range(1_000):
            engine.step(commands=[])
        elapsed = time.time() - start

        print(f"\n[benchmark] 1k ticks: {elapsed:.3f}s  ({elapsed / 1_000 * 1_000:.2f} ms/tick)")
        assert elapsed < 3.0, f"1k empty ticks took {elapsed:.3f}s (threshold 3.0s)"

    def test_10k_ticks_performance(self) -> None:
        """Run 10 000 empty ticks and assert total wall-clock time < 30.0 s."""
        engine = SimCore()
        engine.initialize(map_seed=42)

        start = time.time()
        for _ in range(10_000):
            engine.step(commands=[])
        elapsed = time.time() - start

        print(f"\n[benchmark] 10k ticks: {elapsed:.3f}s  ({elapsed / 10_000 * 1_000:.2f} ms/tick)")
        assert elapsed < 30.0, f"10k empty ticks took {elapsed:.3f}s (threshold 30.0s)"