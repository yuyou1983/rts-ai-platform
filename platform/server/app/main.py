"""Track A — Agent Ops Dashboard API (FastAPI skeleton)."""

import asyncio
import copy
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.mock_data import MOCK_MATCHES, MOCK_TICK

app = FastAPI(title="RTS AI Platform — Agent Ops API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ── WebSocket endpoint ─────────────────────────────────────────────────────

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


# ── Health check ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}
