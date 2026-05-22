#!/usr/bin/env python3
"""Generate final training comparison report after long runs complete.

Usage:
    PYTHONPATH=. python train/generate_report.py
"""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    base = Path("train/output")

    # Load summaries
    b_sum = json.loads((base / "long_baseline" / "summary.json").read_text()) if (base / "long_baseline" / "summary.json").exists() else {}
    e_sum = json.loads((base / "long_enhanced" / "summary.json").read_text()) if (base / "long_enhanced" / "summary.json").exists() else {}

    if not b_sum or not e_sum:
        print("⚠️  Training runs not yet complete. Waiting for summary.json files.")
        return

    # Load league summary if exists
    league = {}
    if (base / "league" / "league_summary.json").exists():
        league = json.loads((base / "league" / "league_summary.json").read_text())

    # Print comparison
    print("=" * 60)
    print("🏋️  LONG-RANGE TRAINING COMPARISON (200ep × 500tick)")
    print("=" * 60)
    print(f"{'Metric':<25} {'Baseline':>12} {'Enhanced':>12} {'Delta':>12}")
    print("-" * 60)

    metrics = [
        ("Time (s)", "time", "{:.1f}"),
        ("Reward Mean", "reward_mean", "{:.2f}"),
        ("Reward First→Last 20", None, None),
        ("  First 20", "reward_first20", "{:.2f}"),
        ("  Last 20", "reward_last20", "{:.2f}"),
        ("Reward Std", "reward_std", "{:.2f}"),
        ("Loss First 10", "loss_first10", "{:.4f}"),
        ("Loss Last 10", "loss_last10", "{:.4f}"),
    ]

    for label, key, fmt in metrics:
        if key is None:
            continue
        bv = b_sum.get(key, 0)
        ev = e_sum.get(key, 0)
        delta = ev - bv
        if "time" in key:
            pct = f"+{delta/bv*100:.1f}%" if bv else "N/A"
            print(f"{label:<25} {fmt.format(bv):>12} {fmt.format(ev):>12} {pct:>12}")
        else:
            print(f"{label:<25} {fmt.format(bv):>12} {fmt.format(ev):>12} {fmt.format(delta):>12}")

    # Reward improvement
    b_improve = b_sum.get("reward_last20", 0) - b_sum.get("reward_first20", 0)
    e_improve = e_sum.get("reward_last20", 0) - e_sum.get("reward_first20", 0)
    print(f"\n{'Reward Improvement':<25} {b_improve:>12.2f} {e_improve:>12.2f} {e_improve-b_improve:>12.2f}")

    # League results
    if league:
        print("\n" + "=" * 60)
        print("🏆 LEAGUE SELF-PLAY RESULTS")
        print("=" * 60)
        lb = league.get("leaderboard", [])
        print(f"{'Version':<15} {'ELO':>8} {'Games':>8} {'Wins':>8}")
        for e in lb:
            print(f"{e.get('name','?'):<15} {e.get('elo',0):>8.0f} {e.get('games_played',0):>8} {e.get('wins',0):>8}")

        promo = league.get("promotion_log", [])
        promoted = sum(1 for p in promo if p.get("promoted"))
        print(f"\nPromotions: {promoted}/{len(promo)} rounds")

    # Generate HTML
    from train.analyze_curves import load_csv, compute_stats, generate_comparison_html
    b_rows = load_csv(base / "long_baseline" / "training_curves.csv")
    e_rows = load_csv(base / "long_enhanced" / "training_curves.csv")
    b_stats = compute_stats(b_rows)
    e_stats = compute_stats(e_rows)
    generate_comparison_html(b_stats, e_stats, b_rows, e_rows, base / "long_comparison_report.html")
    print(f"\n📊 HTML report: {base / 'long_comparison_report.html'}")


if __name__ == "__main__":
    main()