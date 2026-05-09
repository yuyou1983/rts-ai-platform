"""SimCore HTTP gateway — REST/JSON bridge for Godot and web clients.

Runs alongside the gRPC server on a different port.
All responses are JSON, making it trivial for Godot's HTTPRequest node.

Start:  python -m simcore.http_gateway --grpc-port 50051 --http-port 8080
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from aiohttp import web

from simcore.grpc_client import SimCoreClient

logger = logging.getLogger(__name__)

# Global client — initialized in main()
_client: SimCoreClient | None = None


async def handle_start_game(req: web.Request) -> web.Response:
    params = await req.json()
    assert _client
    result = await _client.start_game(
        seed=params.get("seed", 42),
        max_ticks=params.get("max_ticks", 10000),
        tick_rate=params.get("tick_rate", 20.0),
    )
    return web.json_response(result)


async def handle_step(req: web.Request) -> web.Response:
    params = await req.json()
    assert _client
    result = await _client.step(commands=params.get("commands", []))
    return web.json_response(result)


async def handle_get_state(req: web.Request) -> web.Response:
    assert _client
    result = await _client.get_state()
    return web.json_response(result)


async def handle_health(req: web.Request) -> web.Response:
    assert _client
    result = await _client.health()
    return web.json_response(result)


async def handle_replay(req: web.Request) -> web.Response:
    # Replay is server-streaming — collect all snapshots into array
    # This is a simplified version for Godot (no actual streaming)
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
