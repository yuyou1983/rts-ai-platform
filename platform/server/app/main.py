"""Track A — Agent Ops Dashboard API (FastAPI skeleton)."""

import asyncio
import copy
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.mock_data import MOCK_MATCHES, MOCK_TICK
from app.sim_runner import SimRunner

logger = logging.getLogger("dashboard_api")

app = FastAPI(title="RTS AI Platform — Agent Ops API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global SimRunner state ────────────────────────────────────────────────
_sim_runner: SimRunner | None = None


# ── REST endpoints ──────────────────────────────────────────────────────────

@app.get("/api/matches")
def list_matches():
    """Return list of all matches (mock)."""
    return MOCK_MATCHES


@app.get("/api/matches/{match_id}")
def get_match(match_id: str):
    """Return a single match by id (mock)."""
    for m in MOCK_MATCHES:
        if m["id"] == match_id:
            return m
    return {"error": "not found", "match_id": match_id}


@app.post("/api/sim/start")
async def start_sim(
    map_seed: int = 42,
    max_ticks: int = 5000,
    tick_interval_ms: int = 100,
    agent1: str = "RushAI",
    agent2: str = "GreedyGatherer",
):
    """Start a new SimCore live battle. Stops any existing one first."""
    global _sim_runner
    if _sim_runner and _sim_runner.is_running:
        await _sim_runner.stop()

    _sim_runner = SimRunner(
        map_seed=map_seed,
        max_ticks=max_ticks,
        tick_interval_ms=tick_interval_ms,
        agent1_name=agent1,
        agent2_name=agent2,
    )
    await _sim_runner.start()
    return {"status": "running", "map_seed": map_seed, "agents": [agent1, agent2]}


@app.post("/api/sim/stop")
async def stop_sim():
    """Stop the current SimCore battle."""
    global _sim_runner
    if _sim_runner and _sim_runner.is_running:
        await _sim_runner.stop()
        return {"status": "stopped"}
    return {"status": "not_running"}


@app.get("/api/sim/status")
async def sim_status():
    """Return current SimCore battle status."""
    global _sim_runner
    if _sim_runner and _sim_runner.is_running:
        state = _sim_runner._engine.state if _sim_runner._engine else None
        tick = state.tick if state else 0
        return {"status": "running", "tick": tick}
    return {"status": "idle"}


# ── WebSocket endpoints ─────────────────────────────────────────────────────

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """Echo mock tick data every 500ms until client disconnects."""
    await websocket.accept()
    tick = 0
    try:
        while True:
            data = copy.deepcopy(MOCK_TICK)
            data["tick"] = tick
            await websocket.send_text(json.dumps(data))
            tick += 1
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


@app.websocket("/api/sim/ws")
async def ws_sim(websocket: WebSocket):
    """Stream real-time SimCore battle frames to the connected client.

    If no battle is running, the client will wait until one starts.
    The runner broadcasts frames to all connected clients.
    """
    global _sim_runner
    await websocket.accept()
    logger.info("Sim WS client connected")

    if _sim_runner and _sim_runner.is_running:
        _sim_runner.add_client(websocket)

    try:
        while True:
            # Keep the connection alive; listen for client messages
            # (e.g., the client can send "start" to request a new battle)
            msg = await websocket.receive_text()
            data = json.loads(msg) if msg else {}

            if data.get("action") == "start":
                params = data.get("params", {})
                if _sim_runner and _sim_runner.is_running:
                    await _sim_runner.stop()
                _sim_runner = SimRunner(
                    map_seed=params.get("map_seed", 42),
                    max_ticks=params.get("max_ticks", 5000),
                    tick_interval_ms=params.get("tick_interval_ms", 100),
                    agent1_name=params.get("agent1", "RushAI"),
                    agent2_name=params.get("agent2", "GreedyGatherer"),
                )
                await _sim_runner.start()
                _sim_runner.add_client(websocket)

            elif data.get("action") == "stop":
                if _sim_runner and _sim_runner.is_running:
                    await _sim_runner.stop()

    except WebSocketDisconnect:
        logger.info("Sim WS client disconnected")
    except Exception as e:
        logger.error("Sim WS error: %s", e)
    finally:
        if _sim_runner:
            _sim_runner.remove_client(websocket)


# ── Health check ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}
