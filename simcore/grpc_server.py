"""SimCore gRPC server — production-ready, backed by AgentScope game loop.

Start with:  python -m simcore.grpc_server --port 50051
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from concurrent import futures

import grpc

from simcore.engine import SimCore
from simcore.proto_out.proto import service_pb2, service_pb2_grpc, state_pb2

logger = logging.getLogger(__name__)


class SimCoreServicer(service_pb2_grpc.SimCoreServiceServicer):
    """gRPC service implementation backed by SimCore engine."""

    def __init__(self) -> None:
        self.engine = SimCore()
        self._lock = asyncio.Lock()

    async def StartGame(self, request, context):
        """Start a new game from config."""
        async with self._lock:
            config = request.config
            self.engine.initialize(
                map_seed=config.map_seed or 42,
                config={
                    "map_size": config.map_width or 64,
                    "max_ticks": config.max_ticks or 10000,
                    "tick_rate": config.tick_rate or 20.0,
                },
            )
        return self._state_to_snapshot(self.engine.state)

    async def Step(self, request, context):
        """Process one tick with commands."""
        commands: list[dict] = []
        for cmd in request.commands:
            payload = cmd.WhichOneof("payload") or "stop"
            cmd_dict: dict[str, object] = {"action": payload, "issuer": cmd.issuer}
            if payload == "move" and cmd.move:
                cmd_dict.update({
                    "unit_id": cmd.move.unit_id,
                    "target_x": cmd.move.target_x,
                    "target_y": cmd.move.target_y,
                })
            elif payload == "attack" and cmd.attack:
                cmd_dict.update({
                    "attacker_id": cmd.attack.attacker_id,
                    "target_id": cmd.attack.target_id,
                })
            elif payload == "gather" and cmd.gather:
                cmd_dict.update({
                    "worker_id": cmd.gather.worker_id,
                    "resource_id": cmd.gather.resource_id,
                })
            elif payload == "build" and cmd.build:
                cmd_dict.update({
                    "builder_id": cmd.build.builder_id,
                    "building_type": cmd.build.building_type,
                    "pos_x": cmd.build.pos_x,
                    "pos_y": cmd.build.pos_y,
                })
            elif payload == "train" and cmd.train:
                cmd_dict.update({
                    "building_id": cmd.train.building_id,
                    "unit_type": cmd.train.unit_type,
                })
            commands.append(cmd_dict)

        async with self._lock:
            state = self.engine.step(commands)
        return self._state_to_snapshot(state)

    async def GetState(self, request, context):
        """Return current game state."""
        if self.engine.state is None:
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
            context.set_details("Game not started")
            return state_pb2.GameStateSnapshot()
        return self._state_to_snapshot(self.engine.state)

    async def GetReplay(self, request, context):
        """Stream replay snapshots from a given tick."""
        from_tick = request.from_tick or 0
        async with self._lock:
            replay = list(self.engine.replay)
        for snapshot in replay[from_tick:]:
            yield self._snapshot_dict_to_proto(snapshot)

    async def Health(self, request, context):
        """Health check."""
        return service_pb2.HealthResponse(
            healthy=True,
            game_tick=self.engine.tick,
            status="running" if self.engine.state and not self.engine.state.is_terminal else "idle",
        )

    # ─── Conversion helpers ────────────────────────────────────

    @staticmethod
    def _state_to_snapshot(state) -> state_pb2.GameStateSnapshot:
        """Convert GameState to protobuf snapshot."""
        if state is None:
            return state_pb2.GameStateSnapshot()
        snap = state_pb2.GameStateSnapshot(
            game_tick=state.tick,
            is_terminal=state.is_terminal,
            winner=state.winner,
        )
        for eid, e in state.entities.items():
            entity = state_pb2.EntityState(
                id=eid,
                owner=e.get("owner", 0),
                entity_type=e.get("entity_type", ""),
                pos_x=e.get("pos_x", 0.0),
                pos_y=e.get("pos_y", 0.0),
                health=e.get("health", 0),
                max_health=e.get("max_health", 0),
                is_idle=e.get("is_idle", True),
            )
            if "speed" in e:
                entity.speed = e["speed"]
            if "attack" in e:
                entity.attack = e["attack"]
            if "attack_range" in e:
                entity.attack_range = e["attack_range"]
            snap.entities.append(entity)
        for key, val in state.resources.items():
            snap.resources[key] = val
        return snap

    @staticmethod
    def _snapshot_dict_to_proto(snap: dict) -> state_pb2.GameStateSnapshot:
        """Convert a replay dict to protobuf."""
        proto = state_pb2.GameStateSnapshot(
            game_tick=snap.get("tick", 0),
            is_terminal=snap.get("is_terminal", False),
            winner=snap.get("winner", 0),
        )
        for eid, e in snap.get("entities", {}).items():
            proto.entities.append(state_pb2.EntityState(
                id=eid,
                owner=e.get("owner", 0),
                entity_type=e.get("entity_type", ""),
                pos_x=e.get("pos_x", 0.0),
                pos_y=e.get("pos_y", 0.0),
                health=e.get("health", 0),
                is_idle=e.get("is_idle", True),
            ))
        return proto


async def serve(port: int = 50051) -> None:
    """Start the gRPC server."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=4))
    service_pb2_grpc.add_SimCoreServiceServicer_to_server(
        SimCoreServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info("SimCore gRPC server started on port %d", port)
    await server.wait_for_termination()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="SimCore gRPC Server")
    parser.add_argument("--port", type=int, default=50051, help="gRPC port")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    asyncio.run(serve(args.port))


if __name__ == "__main__":
    main()
