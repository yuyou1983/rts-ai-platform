"""Training dashboard — live HTML visualization for GRPO training.

Serves a single-page dashboard at http://localhost:8765 showing:
  - Loss curve (per episode)
  - Win rate (rolling window)
  - Average reward
  - APM (actions per minute)
  - Episode length

Data source: reads metrics JSON from train/output/final_metrics.json or
an active training session writing to the same file.

Usage:
    python -m train.dashboard --port 8765 --data-dir train/output
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>RTS AI — Training Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .header { background: #161b22; padding: 16px 24px; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 16px; }
  .header h1 { font-size: 20px; color: #58a6ff; }
  .header .status { font-size: 13px; color: #8b949e; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .card h3 { font-size: 14px; color: #8b949e; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
  .card .value { font-size: 32px; font-weight: 700; color: #58a6ff; }
  .card .sub { font-size: 12px; color: #8b949e; margin-top: 4px; }
  canvas { width: 100%; height: 200px; }
  .full { grid-column: 1 / -1; }
  .sparkline { position: relative; height: 60px; margin-top: 8px; }
</style>
</head>
<body>
<div class="header">
  <h1>RTS AI Training Dashboard</h1>
  <span class="status" id="status">Connecting...</span>
</div>
<div class="grid">
  <div class="card"><h3>Episodes</h3><div class="value" id="episodes">0</div><div class="sub">total completed</div></div>
  <div class="card"><h3>Win Rate</h3><div class="value" id="winrate">—</div><div class="sub">last 100 episodes</div></div>
  <div class="card"><h3>Avg Reward</h3><div class="value" id="avg_reward">—</div><div class="sub">last 100 episodes</div></div>
  <div class="card"><h3>APM</h3><div class="value" id="apm">—</div><div class="sub">actions per minute</div></div>
  <div class="card full"><h3>Loss Curve</h3><canvas id="loss_canvas" height="200"></canvas></div>
  <div class="card full"><h3>Reward Curve</h3><canvas id="reward_canvas" height="200"></canvas></div>
</div>
<script>
const POLL_MS = 2000;
let metrics = [];
let pollTimer;

async function poll() {
  try {
    const res = await fetch('/api/metrics');
    if (res.ok) metrics = await res.json();
  } catch(e) {}
  render();
}

function drawLine(canvasId, data, key, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth * 2;
  const h = canvas.height = canvas.offsetHeight * 2;
  ctx.clearRect(0, 0, w, h);

  if (data.length < 2) return;
  const vals = data.map(d => d[key] || 0);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const range = maxV - minV || 1;

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < vals.length; i++) {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((vals[i] - minV) / range) * (h - 20) - 10;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Axis labels
  ctx.fillStyle = '#8b949e';
  ctx.font = '20px sans-serif';
  ctx.fillText(maxV.toFixed(2), 8, 24);
  ctx.fillText(minV.toFixed(2), 8, h - 4);
}

function render() {
  if (!metrics.length) return;
  const last = metrics[metrics.length - 1];
  const n = metrics.length;

  document.getElementById('episodes').textContent = n;

  // Win rate
  const recent = metrics.slice(-100);
  const wins = recent.filter(m => m.winner === 1).length;
  document.getElementById('winrate').textContent = (wins / recent.length * 100).toFixed(1) + '%';

  // Avg reward
  const avgR = recent.reduce((s, m) => s + m.reward, 0) / recent.length;
  document.getElementById('avg_reward').textContent = avgR.toFixed(2);

  // APM
  document.getElementById('apm').textContent = last.fps ? (last.fps * 60).toFixed(0) : '—';

  // Charts
  drawLine('loss_canvas', metrics, 'loss', '#f0883e');
  drawLine('reward_canvas', metrics, 'reward', '#58a6ff');

  document.getElementById('status').textContent = 'Last update: ' + new Date().toLocaleTimeString();
}

pollTimer = setInterval(poll, POLL_MS);
poll();
</script>
</body>
</html>"""


async def handle_index(request: object) -> object:
    from aiohttp import web
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def handle_metrics(request: object) -> object:
    from aiohttp import web
    data_path = request.app["data_path"]
    metrics = []
    if data_path.exists():
        try:
            with open(data_path) as f:
                metrics = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return web.json_response(metrics)


async def serve(port: int = 8765, data_dir: str = "train/output") -> None:
    from aiohttp import web

    app = web.Application()
    data_path = Path(data_dir) / "final_metrics.json"
    app["data_path"] = data_path

    app.router.add_get("/", handle_index)
    app.router.add_get("/api/metrics", handle_metrics)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Dashboard running at http://localhost:%d", port)

    stop_event = asyncio.Event()

    import signal

    def _signal_handler() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="Training Dashboard")
    parser.add_argument("--port", type=int,default=8765)
    parser.add_argument("--data-dir", default="train/output")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(serve(args.port, args.data_dir))


if __name__ == "__main__":
    main()
