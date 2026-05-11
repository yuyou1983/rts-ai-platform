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
import logging
import signal

from aiohttp import web

from simcore.grpc_client import SimCoreClient
from simcore.state import GameState

logger = logging.getLogger(__name__)

# Global client — initialized in main()
_client: SimCoreClient | None = None
# AI configuration — set by start_game
_ai_player: int = 0  # 0 = no AI, 1 or 2 = that player is AI-controlled
_ai_agent = None
# Store last full state for AI observation generation
_last_state_dict: dict = {}


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
        tick_rate=params.get("tick_rate", 20.0),
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
    return web.json_response({"error": "replay not supported via HTTP", "replay": []})


async def app_factory(grpc_address: str) -> web.Application:
    global _client
    _client = SimCoreClient(grpc_address)
    await _client.__aenter__()

    app = web.Application()
    app.router.add_post("/api/start_game", handle_start_game)
    app.router.add_post("/api/step", handle_step)
    app.router.add_post("/api/get_state", handle_get_state)
    app.router.add_post("/api/health", handle_health)
    app.router.add_post("/api/replay", handle_replay)

    # CORS for web clients
    async def _cors(req: web.Request, resp: web.StreamResponse) -> None:
        resp.headers["Access-Control-Allow-Origin"] = "*"

    app.on_response_prepare.append(_cors)
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