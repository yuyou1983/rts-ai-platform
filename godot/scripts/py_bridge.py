#!/usr/bin/env python3
"""Bridge script called by Godot's GrpcBridge to talk to SimCore gRPC server.

Usage (called by Godot OS.execute):
    python3 py_bridge.py localhost:50051 start_game '{"seed": 42}'
    python3 py_bridge.py localhost:50051 step '{"commands": []}'
    python3 py_bridge.py localhost:50051 get_state '{}'
    python3 py_bridge.py localhost:50051 health '{}'

Outputs a single JSON line to stdout.
"""
from __future__ import annotations

import asyncio
import json
import sys

# Add project root to path so simcore imports work
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from simcore.grpc_client import SimCoreClient


async def main() -> None:
    address = sys.argv[1]
    method = sys.argv[2]
    params = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

    async with SimCoreClient(address) as client:
        if method == "start_game":
            result = await client.start_game(
                seed=params.get("seed", 42),
                max_ticks=params.get("max_ticks", 10000),
                tick_rate=params.get("tick_rate", 20.0),
            )
        elif method == "step":
            result = await client.step(commands=params.get("commands", []))
        elif method == "get_state":
            result = await client.get_state()
        elif method == "health":
            result = await client.health()
        else:
            result = {"error": f"unknown method: {method}"}

    print(json.dumps(result, default=str))


if __name__ == "__main__":
    asyncio.run(main())
