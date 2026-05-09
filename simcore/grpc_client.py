"""SimCore gRPC client — for Godot bridge and batch simulation."""
from __future__ import annotations

import logging
from typing import Any

import grpc

from simcore.proto_out.proto import cmd_pb2, service_pb2, service_pb2_grpc, state_pb2

logger = logging.getLogger(__name__)


class SimCoreClient:
    """Async gRPC client for SimCore service.

    Usage::

        async with SimCoreClient("localhost:50051") as client:
            state = await client.start_game(seed=42)
            for _ in range(100):
                state = await client.step(commands=[...])
    """

    def __init__(self, address: str = "localhost:50051") -> None:
        self.address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub: service_pb2_grpc.SimCoreServiceStub | None = None

    async def __aenter__(self) -> SimCoreClient:
        self._channel = grpc.aio.insecure_channel(self.address)
        self._stub = service_pb2_grpc.SimCoreServiceStub(self._channel)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._channel:
            await self._channel.close()
        self._channel = None
        self._stub = None

    async def start_game(
        self, seed: int = 42, max_ticks: int = 10000, tick_rate: float = 20.0
    ) -> dict:
        """Start a new game, return state dict."""
        assert self._stub
        config = state_pb2.GameConfig(
            map_seed=seed, map_width=64, max_ticks=max_ticks, tick_rate=tick_rate
        )
        request = service_pb2.StartGameRequest(config=config)
        snapshot = await self._stub.StartGame(request)
        return self._snapshot_to_dict(snapshot)

    async def step(self, commands: list[dict] | None = None) -> dict:
        """Submit commands and advance one tick."""
        assert self._stub
        batch = cmd_pb2.CommandBatch()
        if commands:
            for c in commands:
                cmd = cmd_pb2.Command(issuer=c.get("issuer", 0))
                action = c.get("action", "stop")
                if action == "move":
                    cmd.move.unit_id = c.get("unit_id", "")
                    cmd.move.target_x = c.get("target_x", 0.0)
                    cmd.move.target_y = c.get("target_y", 0.0)
                elif action == "attack":
                    cmd.attack.attacker_id = c.get("attacker_id", "")
                    cmd.attack.target_id = c.get("target_id", "")
                elif action == "gather":
                    cmd.gather.worker_id = c.get("worker_id", "")
                    cmd.gather.resource_id = c.get("resource_id", "")
                elif action == "build":
                    cmd.build.builder_id = c.get("builder_id", "")
                    cmd.build.building_type = c.get("building_type", "")
                    cmd.build.pos_x = c.get("pos_x", 0.0)
                    cmd.build.pos_y = c.get("pos_y", 0.0)
                elif action == "train":
                    cmd.train.building_id = c.get("building_id", "")
                    cmd.train.unit_type = c.get("unit_type", "")
                batch.commands.append(cmd)
        snapshot = await self._stub.Step(batch)
        return self._snapshot_to_dict(snapshot)

    async def get_state(self) -> dict:
        """Get current game state."""
        assert self._stub
        snapshot = await self._stub.GetState(service_pb2.GetStateRequest())
        return self._snapshot_to_dict(snapshot)

    async def health(self) -> dict:
        """Health check."""
        assert self._stub
        resp = await self._stub.Health(service_pb2.HealthRequest())
        return {
            "healthy": resp.healthy,
            "game_tick": resp.game_tick,
            "status": resp.status,
        }

    # ─── Conversion ────────────────────────────────────────────

    @staticmethod
    def _snapshot_to_dict(snapshot) -> dict:
        """Convert protobuf snapshot to plain dict."""
        entities = {}
        for e in snapshot.entities:
            entities[e.id] = {
                "owner": e.owner,
                "entity_type": e.entity_type,
                "pos_x": e.pos_x,
                "pos_y": e.pos_y,
                "health": e.health,
                "max_health": e.max_health,
                "speed": e.speed,
                "attack": e.attack,
                "attack_range": e.attack_range,
                "is_idle": e.is_idle,
            }
        return {
            "tick": snapshot.game_tick,
            "is_terminal": snapshot.is_terminal,
            "winner": snapshot.winner,
            "entities": entities,
            "resources": dict(snapshot.resources),
        }
