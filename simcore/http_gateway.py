"""SimCore HTTP gateway — REST/JSON bridge for Godot and web clients.

When ai_player is set in start_game, the step handler automatically
generates AI commands for that player each tick, merging them with
human commands before advancing the simulation.

For Godot (human player), we return ALL entities for rendering.
For AI agents, we use GameState.get_observations() which filters by fog.

Start:  python -m simcore.http_gateway --grpc-port 50051 --http-port 8080
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

from aiohttp import web

from simcore.grpc_client import SimCoreClient
from simcore.state import GameState

from harness.league import League, AgentVersion, AgentType, MatchupResult, update_elo
from harness.pool import MatchConfig, MatchResult, MatchScheduler, SimulationPool

logger = logging.getLogger(__name__)

# Global client — initialized in main()
_client: SimCoreClient | None = None
# AI configuration — set by start_game
_ai_player: int = 0  # 0 = no AI, 1 or 2 = that player is AI-controlled
_ai_agent = None
# Store last full state for AI observation generation
_last_state_dict: dict = {}

# League instance — lazily initialized
_league: League | None = None
# Replay directory — points to harness output
_replay_dir: Path = Path("harness/output/replays")


def _create_ai_agent(player_id: int):
    """Create the appropriate AI agent based on availability."""
    try:
        from agents.coordinator import CoordinatorAgent
        return CoordinatorAgent(player_id=player_id)
    except ImportError:
        from agents.script_ai import ScriptAI
        return ScriptAI(player_id=player_id)


def _state_to_observations(state_dict: dict) -> list[dict]:
    """Convert a raw state dict to per-player observations using GameState."""
    try:
        gs = GameState(
            tick=state_dict.get("tick", 0),
            entities=state_dict.get("entities", {}),
            fog_of_war=state_dict.get("fog_of_war", {}),
            resources=state_dict.get("resources", {}),
            is_terminal=state_dict.get("is_terminal", False),
            winner=state_dict.get("winner", 0),
        )
        return gs.get_observations()
    except Exception:
        return [state_dict, state_dict]


def _godot_state(state_dict: dict) -> dict:
    """Build a Godot-friendly state: all entities visible, fog for rendering only."""
    result = dict(state_dict)
    # Keep fog_of_war for visual rendering
    # But entities are the FULL set (not filtered by fog)
    return result


async def handle_start_game(req: web.Request) -> web.Response:
    global _ai_player, _ai_agent, _last_state_dict
    params = await req.json()
    assert _client
    _ai_player = params.get("ai_player", 0)
    _last_state_dict = {}
    if _ai_player in (1, 2):
        _ai_agent = _create_ai_agent(_ai_player)
        logger.info("AI agent created for P%d: %s", _ai_player, type(_ai_agent).__name__)
    else:
        _ai_agent = None
    result = await _client.start_game(
        seed=params.get("seed", 42),
        max_ticks=params.get("max_ticks", 10000),
        tick_rate=params.get("tick_rate", 10.0),
    )
    _last_state_dict = result
    return web.json_response(_godot_state(result))


async def handle_step(req: web.Request) -> web.Response:
    global _last_state_dict
    params = await req.json()
    assert _client
    commands = list(params.get("commands", []))

    # Auto-inject AI commands for the configured AI player
    if _ai_agent is not None and _ai_player in (1, 2):
        try:
            obs_list = _state_to_observations(_last_state_dict)
            if len(obs_list) >= _ai_player:
                ai_obs = obs_list[_ai_player - 1]
                ai_result = _ai_agent.decide(ai_obs)
                if isinstance(ai_result, dict):
                    ai_cmds = ai_result.get("commands", [])
                else:
                    ai_cmds = list(ai_result) if ai_result else []
                for cmd in ai_cmds:
                    if "issuer" not in cmd:
                        cmd["issuer"] = _ai_player
                commands.extend(ai_cmds)
        except Exception as exc:
            logger.warning("AI command generation failed: %s", exc)

    # Log AI commands
    ai_cmds = [c for c in commands if c.get("issuer") == _ai_player]
    if ai_cmds:
        logger.info("AI P%d commands: %s", _ai_player, 
                    [(c.get("action"), c.get("unit_type", c.get("building_type",""))) for c in ai_cmds[:5]])

    # Debug: log train commands
    train_cmds = [c for c in commands if c.get("action") == "train"]
    if train_cmds:
        logger.info("Sending to gRPC - train commands: %s", train_cmds[:3])
    
    result = await _client.step(commands=commands)
    _last_state_dict = result
    return web.json_response(_godot_state(result))


async def handle_get_state(req: web.Request) -> web.Response:
    assert _client
    result = await _client.get_state()
    return web.json_response(_godot_state(result))


async def handle_health(req: web.Request) -> web.Response:
    assert _client
    result = await _client.health()
    return web.json_response(result)


async def handle_replay(req: web.Request) -> web.Response:
    """GET /api/replay/{match_id} — read replay data.

    Tries to read from harness/output/replays/{match_id}.jsonl first.
    If the file doesn't exist, falls back to the gRPC client's current
    engine replay data.
    """
    match_id = req.match_info["match_id"]
    json_path = _replay_dir / f"{match_id}.json"
    jsonl_path = _replay_dir / f"{match_id}.jsonl"

    ticks: list[dict] = []
    replay_meta: dict = {}

    # Try JSON first (single-file format with ticks array)
    if json_path.is_file():
        with open(json_path) as f:
            data = json.load(f)
        ticks = data.get("ticks", [])
        match_id = data.get("match_id", match_id)
        replay_meta = {"player_races": data.get("player_races", {}),
                        "winner": data.get("winner", 0)}
    # Try JSONL next (one tick per line)
    elif jsonl_path.is_file():
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    else:
        # Fallback: request current replay from the gRPC server
        # The gRPC client doesn't have a dedicated replay method,
        # so we try to get the state which may contain replay snapshots.
        try:
            if _client:
                state = await _client.get_state()
                # The engine stores snapshots in engine._replay; if the
                # state dict includes a "replay" key, use it directly.
                ticks = state.get("replay", [])
        except Exception as exc:
            logger.warning("Failed to fetch replay via gRPC: %s", exc)

    # Normalize tick format for Godot client compatibility
    # Engine raw: resources={"p1_mineral":200,...}, fog={"1":{"tiles":...}}
    # Godot expects: resources={"1":{"minerals":200,...}}, fog same structure
    replay_meta = {}
    for tick in ticks:
        # ── Normalize resources ──
        res: dict = tick.get("resources", {})
        if "p1_mineral" in res:
            p1 = {"minerals": res.pop("p1_mineral", 0), "gas": res.pop("p1_gas", 0),
                   "supply_used": res.pop("p1_supply_used", 0), "supply_cap": res.pop("p1_supply_cap", 0)}
            p2 = {"minerals": res.pop("p2_mineral", 0), "gas": res.pop("p2_gas", 0),
                   "supply_used": res.pop("p2_supply_used", 0), "supply_cap": res.pop("p2_supply_cap", 0)}
            tick["resources"] = {"1": p1, "2": p2}
        # ── Inject map dimensions if missing ──
        if "map_width" not in tick:
            tick["map_width"] = 64
            tick["map_height"] = 64

    # Collect metadata from JSON file if available
    # (replay_meta already populated in the if-branch above)

    return web.json_response({
        "match_id": match_id,
        "ticks": ticks,
        "tick_count": len(ticks),
        **replay_meta,
    })


def _get_league() -> League:
    """Return (and lazily create) the global League instance."""
    global _league
    if _league is None:
        _league = League()
    return _league


async def handle_league_ranking(req: web.Request) -> web.Response:
    """GET /api/league/ranking — return ELO ranking."""
    league = _get_league()
    leaderboard = league.get_leaderboard()
    versions = [s.to_dict() for s in leaderboard]
    return web.json_response({"versions": versions})


async def handle_league_match(req: web.Request) -> web.Response:
    """POST /api/league/match — create and run a League match.

    Request body: {"p1_version": "v1", "p2_version": "v2", "map_seed": 42, "max_ticks": 5000}
    """
    league = _get_league()
    params = await req.json()

    p1_version_name = params.get("p1_version", "script-v1")
    p2_version_name = params.get("p2_version", "script-v1")
    map_seed = params.get("map_seed", 42)
    max_ticks = params.get("max_ticks", 5000)

    # Ensure both versions are registered in the league
    for vname in (p1_version_name, p2_version_name):
        if vname not in league.pool:
            league.register(AgentVersion(
                name=vname,
                type=AgentType.SCRIPT,
                creation_tick=0,
            ))

    config = MatchConfig(
        map_seed=map_seed,
        max_ticks=max_ticks,
        player1_type="script",
        player2_type="script",
    )

    pool = SimulationPool(max_concurrent=1)
    result: MatchResult = await pool.run_match(config)

    # Persist replay to disk
    _replay_dir.mkdir(parents=True, exist_ok=True)
    replay_path = _replay_dir / f"{result.match_id}.jsonl"
    with open(replay_path, "w") as f:
        for tick_snapshot in result.replay:
            f.write(json.dumps(tick_snapshot, default=str) + "\n")

    # Record result in league to update ELO
    try:
        league.record_result(MatchupResult(
            player1=p1_version_name,
            player2=p2_version_name,
            winner=result.winner,
            ticks=result.ticks,
        ))
    except Exception as exc:
        logger.warning("Failed to record league result: %s", exc)

    return web.json_response({
        "match_id": result.match_id,
        "winner": result.winner,
        "ticks": result.ticks,
        "tps": result.tps,
    })


async def handle_league_submit_result(req: web.Request) -> web.Response:
    """POST /api/league/submit_result — submit a match result to update ELO.

    Request body: {"p1_version": "v1", "p2_version": "v2", "winner": 1, "ticks": 1234}
    """
    league = _get_league()
    params = await req.json()

    p1_version_name = params.get("p1_version", "")
    p2_version_name = params.get("p2_version", "")
    winner = params.get("winner", 0)
    ticks = params.get("ticks", 0)

    # Ensure both versions are registered in the league
    for vname in (p1_version_name, p2_version_name):
        if vname not in league.pool:
            league.register(AgentVersion(
                name=vname,
                type=AgentType.SCRIPT,
                creation_tick=0,
            ))

    # Capture ELO before update
    p1_elo_before = league.get_elo(p1_version_name)
    p2_elo_before = league.get_elo(p2_version_name)

    league.record_result(MatchupResult(
        player1=p1_version_name,
        player2=p2_version_name,
        winner=winner,
        ticks=ticks,
    ))

    p1_elo = league.get_elo(p1_version_name)
    p2_elo = league.get_elo(p2_version_name)

    return web.json_response({
        "ok": True,
        "p1_elo": round(p1_elo, 1),
        "p2_elo": round(p2_elo, 1),
    })


def reset_ai_state() -> None:
    """Reset AI configuration globals. Called between tests."""
    global _ai_player, _ai_agent, _last_state_dict, _league
    _ai_player = 0
    _ai_agent = None
    _last_state_dict = {}
    _league = None


async def app_factory(grpc_address: str = "", *, client: SimCoreClient | None = None) -> web.Application:
    global _client
    if client is not None:
        _client = client
    elif grpc_address:
        _client = SimCoreClient(grpc_address)
        await _client.__aenter__()
    else:
        raise ValueError("Either grpc_address or client must be provided")

    app = web.Application()
    app.router.add_post("/api/start_game", handle_start_game)
    app.router.add_post("/api/step", handle_step)
    app.router.add_post("/api/get_state", handle_get_state)
    app.router.add_post("/api/health", handle_health)
    app.router.add_post("/api/replay", handle_replay)

    # New endpoints
    app.router.add_get("/api/replay/{match_id}", handle_replay)
    app.router.add_get("/api/league/ranking", handle_league_ranking)
    app.router.add_post("/api/league/match", handle_league_match)
    app.router.add_post("/api/league/submit_result", handle_league_submit_result)

    # CORS for web clients
    async def _cors(req: web.Request, resp: web.StreamResponse) -> None:
        resp.headers["Access-Control-Allow-Origin"] = "*"

    app.on_response_prepare.append(_cors)

    # Cleanup hook — close the gRPC client on app shutdown
    async def _cleanup(app: web.Application) -> None:
        if _client:
            await _client.__aexit__(None, None, None)

    app.on_shutdown.append(_cleanup)
    return app


async def serve(grpc_port: int = 50051, http_port: int = 8080) -> None:
    grpc_address = f"localhost:{grpc_port}"
    app = await app_factory(grpc_address)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", http_port)
    await site.start()
    logger.info("HTTP gateway started on port %d → gRPC %s", http_port, grpc_address)

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    logger.info("Shutting down HTTP gateway...")
    if _client:
        await _client.__aexit__(None, None, None)
    await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="SimCore HTTP Gateway")
    parser.add_argument("--grpc-port", type=int, default=50051)
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(serve(args.grpc_port, args.http_port))


if __name__ == "__main__":
    main()