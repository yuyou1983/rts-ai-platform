"""League Self-Play Training — Analysis utilities.

Reads league_summary.json, generates ELO progression and win-rate charts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_league_summary(path: Path) -> dict[str, Any]:
    """Load a league_summary.json file."""
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def generate_league_html(summary: dict[str, Any], output_path: Path) -> None:
    """Generate HTML visualization of league training results."""
    import numpy as np

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
            f'<text x="20" y="{height-5}" fill="#666" font-size="10">round=0</text>'
            f'<text x="{width-80}" y="{height-5}" fill="#666" font-size="10">round={len(data)-1}</text>'
            f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>'
            f'</svg>'
        )

    rounds = summary.get("round_metrics", [])
    elos = [r.get("elo", 1000) for r in rounds]
    win_rates = [r.get("win_rate", 0) for r in rounds]
    promotions = summary.get("promotion_log", [])
    leaderboard = summary.get("leaderboard", [])

    # Promotion markers
    promo_rounds = [p.get("round", 0) for p in promotions if p.get("promoted")]

    # Leaderboard table
    lb_rows = ""
    for entry in leaderboard:
        lb_rows += (
            f'<tr><td>{entry.get("name","?")}</td>'
            f'<td>{entry.get("elo",0):.0f}</td>'
            f'<td>{entry.get("games_played",0)}</td>'
            f'<td>{entry.get("wins",0)}</td></tr>'
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>League Training Report</title>
<style>
  body {{ background:#0d0d1a; color:#e0e0e0; font-family:system-ui,sans-serif; padding:20px; }}
  h1 {{ color:#4fc3f7; }} h2 {{ color:#81c784; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; max-width:1500px; }}
  .card {{ background:#1a1a2e; border-radius:12px; padding:16px; }}
  table {{ border-collapse:collapse; width:100%; }}
  th,td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #252545; }}
  th {{ color:#4fc3f7; }} td {{ color:#ccc; }}
  .stat {{ display:inline-block; background:#252545; padding:8px 14px; margin:4px; border-radius:6px; }}
  .stat .label {{ color:#888; font-size:11px; }}
  .stat .value {{ color:#4fc3f7; font-size:18px; font-weight:600; }}
</style></head><body>
<h1>🏆 League Self-Play Training Report</h1>

<div class="grid">
  <div class="card">
    <h2>📈 ELO Progression</h2>
    {svg_line(elos, color="#4fc3f7", label="ELO per Round")}
  </div>
  <div class="card">
    <h2>🎯 Win Rate per Round</h2>
    {svg_line(win_rates, color="#81c784", label="Win Rate")}
  </div>
</div>

<h2>🏅 Leaderboard</h2>
<div class="card">
<table>
<tr><th>Version</th><th>ELO</th><th>Games</th><th>Wins</th></tr>
{lb_rows}
</table>
</div>

<h2>📋 Promotion Log</h2>
<div class="card">
<table>
<tr><th>Round</th><th>Version</th><th>Promoted</th><th>Win Rate</th><th>ELO</th></tr>
{''.join(f'<tr><td>{p.get("round",0)}</td><td>{p.get("version","?")}</td><td>{"✅" if p.get("promoted") else "❌"}</td><td>{p.get("win_rate",0):.2f}</td><td>{p.get("elo",0):.0f}</td></tr>' for p in promotions)}
</table>
</div>

</body></html>"""

    output_path.write_text(html)
    print(f"League report saved to {output_path}")


if __name__ == "__main__":
    base = Path("train/output/league")
    summary = load_league_summary(base / "league_summary.json")
    if summary:
        generate_league_html(summary, base / "league_report.html")
    else:
        print("No league_summary.json found")