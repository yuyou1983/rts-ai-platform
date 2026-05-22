"""Training curve analysis and visualization.

Reads training_curves.csv from baseline and enhanced runs,
produces comparison plots as HTML (no matplotlib dependency).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def load_csv(path: Path) -> list[dict[str, Any]]:
    """Load training_curves.csv into list of dicts."""
    if not path.exists():
        return []
    with open(path) as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def compute_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics from CSV rows."""
    if not rows:
        return {"episodes": 0}
    import numpy as np
    rewards = [float(r["reward"]) for r in rows]
    losses = [float(r.get("total_loss", 0)) for r in rows]
    lengths = [float(r.get("length", 0)) for r in rows]
    return {
        "episodes": len(rows),
        "reward_mean": float(np.mean(rewards)),
        "reward_std": float(np.std(rewards)),
        "reward_first20": float(np.mean(rewards[:20])),
        "reward_last20": float(np.mean(rewards[-20:])),
        "loss_first10": float(np.mean(losses[:10])),
        "loss_last10": float(np.mean(losses[-10:])),
        "avg_length": float(np.mean(lengths)),
    }


def generate_comparison_html(
    baseline_stats: dict[str, Any],
    enhanced_stats: dict[str, Any],
    baseline_rows: list[dict[str, Any]],
    enhanced_rows: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Generate an HTML comparison report with inline SVG charts."""
    import numpy as np

    def smooth(data: list[float], window: int = 10) -> list[float]:
        if len(data) < window:
            return data
        return [float(np.mean(data[max(0, i - window):i + 1])) for i in range(len(data))]

    def svg_line(data: list[float], width: int = 700, height: int = 250,
                 color: str = "#4fc3f7", label: str = "") -> str:
        if not data:
            return f'<p><em>{label}: no data</em></p>'
        mn, mx = min(data), max(data)
        rng = mx - mn if mx != mn else 1.0
        pts = []
        for i, v in enumerate(data):
            x = int(i / max(len(data) - 1, 1) * (width - 40)) + 20
            y = int(height - 20 - (v - mn) / rng * (height - 40))
            pts.append(f"{x},{y}")
        poly = " ".join(pts)
        return (
            f'<svg width="{width}" height="{height}" '
            f'style="background:#1a1a2e;border-radius:8px;margin:8px 0">'
            f'<text x="20" y="18" fill="#aaa" font-size="12">{label}</text>'
            f'<text x="20" y="{height-5}" fill="#666" font-size="10">ep=0</text>'
            f'<text x="{width-60}" y="{height-5}" fill="#666" font-size="10">ep={len(data)-1}</text>'
            f'<text x="{width-100}" y="18" fill="#888" font-size="10">min={mn:.2f} max={mx:.2f}</text>'
            f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.5"/>'
            f'</svg>'
        )

    # Extract series
    b_rewards = [float(r["reward"]) for r in baseline_rows]
    e_rewards = [float(r["reward"]) for r in enhanced_rows]
    b_losses = [float(r.get("total_loss", 0)) for r in baseline_rows]
    e_losses = [float(r.get("total_loss", 0)) for r in enhanced_rows]

    # Smoothing
    b_rewards_s = smooth(b_rewards, 15)
    e_rewards_s = smooth(e_rewards, 15)
    b_losses_s = smooth(b_losses, 15)
    e_losses_s = smooth(e_losses, 15)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Training Comparison</title>
<style>
  body {{ background:#0d0d1a; color:#e0e0e0; font-family:system-ui,sans-serif; padding:20px; }}
  h1 {{ color:#4fc3f7; }} h2 {{ color:#81c784; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; max-width:1500px; }}
  .card {{ background:#1a1a2e; border-radius:12px; padding:16px; }}
  .stat {{ display:inline-block; background:#252545; padding:8px 14px; margin:4px; border-radius:6px; }}
  .stat .label {{ color:#888; font-size:11px; }} .stat .value {{ color:#4fc3f7; font-size:18px; font-weight:600; }}
  .better {{ color:#81c784; }} .worse {{ color:#ef5350; }}
  table {{ border-collapse:collapse; width:100%; }} th,td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #252545; }}
  th {{ color:#4fc3f7; }} td {{ color:#ccc; }}
</style></head><body>
<h1>🏋️ Training Comparison Report</h1>

<div class="grid">
  <div class="card">
    <h2>📊 Baseline (flags OFF)</h2>
    <div class="stat"><span class="label">Episodes</span><br><span class="value">{baseline_stats.get('episodes',0)}</span></div>
    <div class="stat"><span class="label">Reward Mean</span><br><span class="value">{baseline_stats.get('reward_mean',0):.2f}</span></div>
    <div class="stat"><span class="label">Reward First→Last 20</span><br><span class="value">{baseline_stats.get('reward_first20',0):.2f} → {baseline_stats.get('reward_last20',0):.2f}</span></div>
    <div class="stat"><span class="label">Loss First→Last 10</span><br><span class="value">{baseline_stats.get('loss_first10',0):.4f} → {baseline_stats.get('loss_last10',0):.4f}</span></div>
    <div class="stat"><span class="label">Avg Length</span><br><span class="value">{baseline_stats.get('avg_length',0):.0f}</span></div>
  </div>
  <div class="card">
    <h2>🚀 Enhanced (flags ON)</h2>
    <div class="stat"><span class="label">Episodes</span><br><span class="value">{enhanced_stats.get('episodes',0)}</span></div>
    <div class="stat"><span class="label">Reward Mean</span><br><span class="value">{enhanced_stats.get('reward_mean',0):.2f}</span></div>
    <div class="stat"><span class="label">Reward First→Last 20</span><br><span class="value">{enhanced_stats.get('reward_first20',0):.2f} → {enhanced_stats.get('reward_last20',0):.2f}</span></div>
    <div class="stat"><span class="label">Loss First→Last 10</span><br><span class="value">{enhanced_stats.get('loss_first10',0):.4f} → {enhanced_stats.get('loss_last10',0):.4f}</span></div>
    <div class="stat"><span class="label">Avg Length</span><br><span class="value">{enhanced_stats.get('avg_length',0):.0f}</span></div>
  </div>
</div>

<h2>📈 Reward Curves (smoothed, window=15)</h2>
<div class="grid">
  <div class="card">{svg_line(b_rewards_s, color="#4fc3f7", label="Baseline Reward")}</div>
  <div class="card">{svg_line(e_rewards_s, color="#81c784", label="Enhanced Reward")}</div>
</div>

<h2>📉 Loss Curves (smoothed, window=15)</h2>
<div class="grid">
  <div class="card">{svg_line(b_losses_s, color="#ffa726", label="Baseline Loss")}</div>
  <div class="card">{svg_line(e_losses_s, color="#ef5350", label="Enhanced Loss")}</div>
</div>

<h2>📋 Head-to-Head Comparison</h2>
<table>
<tr><th>Metric</th><th>Baseline</th><th>Enhanced</th><th>Δ</th></tr>
<tr><td>Reward Last 20</td><td>{baseline_stats.get('reward_last20',0):.2f}</td>
    <td>{enhanced_stats.get('reward_last20',0):.2f}</td>
    <td class="{'better' if enhanced_stats.get('reward_last20',0) > baseline_stats.get('reward_last20',0) else 'worse'}">
    {enhanced_stats.get('reward_last20',0) - baseline_stats.get('reward_last20',0):+.2f}</td></tr>
<tr><td>Loss Last 10</td><td>{baseline_stats.get('loss_last10',0):.4f}</td>
    <td>{enhanced_stats.get('loss_last10',0):.4f}</td>
    <td class="{'better' if abs(enhanced_stats.get('loss_last10',0)) > abs(baseline_stats.get('loss_last10',0)) else 'worse'}">
    {enhanced_stats.get('loss_last10',0) - baseline_stats.get('loss_last10',0):+.4f}</td></tr>
<tr><td>Reward Std</td><td>{baseline_stats.get('reward_std',0):.2f}</td>
    <td>{enhanced_stats.get('reward_std',0):.2f}</td>
    <td class="{'better' if enhanced_stats.get('reward_std',0) < baseline_stats.get('reward_std',0) else 'worse'}">
    {enhanced_stats.get('reward_std',0) - baseline_stats.get('reward_std',0):+.2f}</td></tr>
</table>

</body></html>"""

    output_path.write_text(html)
    print(f"Report saved to {output_path}")


def analyze(output_base: str = "train/output") -> None:
    """Analyze and generate comparison report."""
    base = Path(output_base)
    b_rows = load_csv(base / "long_baseline" / "training_curves.csv")
    e_rows = load_csv(base / "long_enhanced" / "training_curves.csv")
    # Also try new directory names
    if not b_rows:
        b_rows = load_csv(base / "long_baseline" / "training_curves.csv")
    if not e_rows:
        e_rows = load_csv(base / "long_enhanced" / "training_curves.csv")
    b_stats = compute_stats(b_rows)
    e_stats = compute_stats(e_rows)
    generate_comparison_html(b_stats, e_stats, b_rows, e_rows, base / "comparison_report.html")

    # Also save stats JSON
    combined = {"baseline": b_stats, "enhanced": e_stats}
    (base / "long_comparison_stats.json").write_text(json.dumps(combined, indent=2))
    print(f"Stats: {json.dumps(combined, indent=2)}")


if __name__ == "__main__":
    analyze()