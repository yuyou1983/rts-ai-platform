"""Integration tests for gRPC server + client."""
import asyncio

import pytest

from simcore.grpc_client import SimCoreClient
from simcore.grpc_server import SimCoreServicer


@pytest.fixture
def servicer():
    return SimCoreServicer()


class TestServerUnit:
    """Test server logic without network."""

    def test_servicer_init(self, servicer):
        assert servicer.engine is not None

    def test_state_to_snapshot(self, servicer):
        from simcore.engine import SimCore

        e = SimCore()
        e.initialize(map_seed=42)
        snap = servicer._state_to_snapshot(e.state)
        assert snap.game_tick == 0
        assert len(snap.entities) > 0


class TestClientServerIntegration:
    """Full client-server integration via in-process channel."""

    def test_start_and_step(self):
        """Start game and step through gRPC."""
        from concurrent import futures

        import grpc

        async def _test():
            # Start in-process server
            server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=2))
            from simcore.proto_out.proto import service_pb2_grpc
            service_pb2_grpc.add_SimCoreServiceServicer_to_server(
                SimCoreServicer(), server
            )
            port = server.add_insecure_port("[::]:0")
            await server.start()

            try:
                async with SimCoreClient(f"localhost:{port}") as client:
                    state = await client.start_game(seed=42)
                    assert state["tick"] == 0
                    assert len(state["entities"]) > 0

                    # Step a few ticks
                    for i in range(5):
                        state = await client.step(commands=[])
                        assert state["tick"] == i + 1

                    # Get state
                    state2 = await client.get_state()
                    assert state2["tick"] == 5

                    # Health
                    health = await client.health()
                    assert health["healthy"] is True
            finally:
                await server.stop(grace=0)

        asyncio.run(_test())

    def test_step_with_commands(self):
        """Send actual commands through gRPC."""
        from concurrent import futures

        import grpc

        async def _test():
            server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=2))
            from simcore.proto_out.proto import service_pb2_grpc
            service_pb2_grpc.add_SimCoreServiceServicer_to_server(
                SimCoreServicer(), server
            )
            port = server.add_insecure_port("[::]:0")
            await server.start()

            try:
                async with SimCoreClient(f"localhost:{port}") as client:
                    await client.start_game(seed=42)
                    # Send a move command
                    state = await client.step(commands=[{
                        "action": "move",
                        "unit_id": "worker_p1_0",
                        "target_x": 10.0,
                        "target_y": 10.0,
                        "issuer": 1,
                    }])
                    assert state["tick"] == 1
            finally:
                await server.stop(grace=0)

        asyncio.run(_test())
