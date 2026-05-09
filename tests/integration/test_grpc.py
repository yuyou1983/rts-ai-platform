"""Integration tests for gRPC server + client (auto-step mode).

Uses real gRPC client/server via subprocess to avoid event loop conflicts.
"""
import subprocess
import sys
import time

import pytest

from simcore.grpc_client import SimCoreClient


def _find_free_port() -> int:
    """Find a free TCP port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def grpc_server_port():
    """Start a real gRPC server on a free port, yield the port, then kill it."""
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "simcore.grpc_server",
         "--port", str(port), "--tick-rate", "20"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)  # Wait for server to start
    yield port
    proc.terminate()
    proc.wait(timeout=5)


class TestGrpcIntegration:
    """Integration tests with a real gRPC server subprocess."""

    @pytest.mark.asyncio
    async def test_start_and_step(self, grpc_server_port):
        """Start game, step once, verify tick advances."""
        async with SimCoreClient(f"localhost:{grpc_server_port}") as client:
            s = await client.start_game(seed=42, max_ticks=100)
            assert s["tick"] == 0
            assert not s["is_terminal"]

            s = await client.step(commands=[])
            assert s["tick"] == 1

            s = await client.step(commands=[])
            assert s["tick"] == 2

    @pytest.mark.asyncio
    async def test_health(self, grpc_server_port):
        """Health check should report healthy."""
        async with SimCoreClient(f"localhost:{grpc_server_port}") as client:
            h = await client.health()
            assert h["healthy"] is True
            assert h["status"] == "idle"

    @pytest.mark.asyncio
    async def test_building_type_in_state(self, grpc_server_port):
        """building_type and unit_type should be present in entity dict."""
        async with SimCoreClient(f"localhost:{grpc_server_port}") as client:
            s = await client.start_game(seed=42, max_ticks=100)
            for _eid, e in s["entities"].items():
                assert "building_type" in e
                assert "unit_type" in e

    @pytest.mark.asyncio
    async def test_command_submission(self, grpc_server_port):
        """Submit a move command and verify it doesn't crash."""
        async with SimCoreClient(f"localhost:{grpc_server_port}") as client:
            s = await client.start_game(seed=42, max_ticks=100)
            unit_id = ""
            for eid, e in s["entities"].items():
                if e.get("entity_type") == "unit":
                    unit_id = eid
                    break
            if unit_id:
                s2 = await client.step(commands=[{
                    "action": "move",
                    "issuer": 1,
                    "unit_id": unit_id,
                    "target_x": 10.0,
                    "target_y": 10.0,
                }])
                assert s2["tick"] == 1
