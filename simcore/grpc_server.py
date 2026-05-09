"""SimCore gRPC server — production-ready, backed by SimCore engine.

Supports two modes:
  1. Manual step:  client calls Step() each tick
  2. Auto step:    server runs its own tick loop, client polls GetState()

Start with:  python -m simcore.grpc_server --port 50051
Auto step:    python -m simcore.grpc_server --port 50051 --auto-step --tick-rate 20
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from concurrent import futures

import grpc

from agents.script_ai import ScriptAI
from simcore.engine import SimCore
from simcore.proto_out.proto import service_pb2, service_pb2_grpc, state_pb2

logger = logging.getLogger(__name__)


class SimCoreServicer(service_pb2_grpc.SimCoreServiceServicer):
    """gRPC service implementation backed by SimCore engine."""

    def __init__(self, auto_step: bool = False, tick_rate: float = 20.0) -> None:
        self.engine = SimCore()
        self._lock = asyncio.Lock()
        self._auto_step = auto_step
        self._tick_rate = tick_rate
        self._ai_agents: dict[int, ScriptAI] = {}
        self._auto_task: asyncio.Task | None = None

    async def StartGame(self, request, context):
        """Start a new game from config."""
        async with self._lock:
            config = request.config
            map_seed = config.map_seed or 42
            max_ticks = config.max_ticks or 10000
            tick_rate = config.tick_rate or self._tick_rate

            self.engine = SimCore(max_ticks=max_ticks, tick_rate=tick_rate)
            self.engine.initialize(
                map_seed=map_seed,
                config={"map_size": config.map_width or 64, "max_ticks": max_ticks},
            )

            # Create AI agents for all players
            self._ai_agents = {1: ScriptAI(player_id=1), 2: ScriptAI(player_id=2)}

            # Start auto-step loop if enabled
            if self._auto_step and self._auto_task is None:
                self._auto_task = asyncio.create_task(self._auto_step_loop())

        snapshot = self._state_to_snapshot(self.engine.state)
        logger.info("Game started: seed=%d, max_ticks=%d, auto_step=%s",
                     map_seed, max_ticks, self._auto_step)
        return snapshot

    async def Step(self, request, context):
        """Process one tick with commands."""
        commands = self._parse_commands(request)
        async with self._lock:
            # If auto-step is enabled, AI commands are already applied in the loop.
            # Here we just apply any player-submitted commands on top.
            state = self.engine.step(commands)

        if state.is_terminal and self._auto_task:
            self._auto_task.cancel()
            self._auto_task = None

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

    # ─── Auto-step loop ──────────────────────────────────────

    async def _auto_step_loop(self) -> None:
        """Background task: advance ticks at tick_rate, driven by AI agents."""
        interval = 1.0 / self._tick_rate if self._tick_rate > 0 else 0.05
        logger.info("Auto-step loop started (interval=%.3fs)", interval)
        try:
            while self.engine.state and not self.engine.state.is_terminal:
                async with self._lock:
                    obs = self.engine.state.get_observations()
                    all_commands: list[dict] = []
                    for pid, ai in self._ai_agents.items():
                        idx = pid - 1
                        if idx < len(obs):
                            all_commands.extend(ai.decide(obs[idx]))
                    self.engine.step(all_commands)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Auto-step loop cancelled")
        except Exception:
            logger.exception("Auto-step loop error")

    # ─── Command parsing ──────────────────────────────────────

    @staticmethod
    def _parse_commands(request) -> list[dict]:
        """Convert protobuf CommandBatch to list of dicts."""
        commands: list[dict] = []
        for cmd in request.commands:
            payload = cmd.WhichOneof("payload") or "stop"
            cmd_dict: dict = {"action": payload, "issuer": cmd.issuer}
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
        return commands

    # ─── Conversion helpers ──────────────────────────────────

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
            if "building_type" in e:
                entity.building_type = e.get("building_type", "")
            if "unit_type" in e:
                entity.unit_type = e.get("unit_type", "")
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


async def serve(port: int = 50051, auto_step: bool = False,
                tick_rate: float = 20.0) -> None:
    """Start the gRPC server with graceful shutdown."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=4))
    servicer = SimCoreServicer(auto_step=auto_step, tick_rate=tick_rate)
    service_pb2_grpc.add_SimCoreServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info("SimCore gRPC server started on port %d (auto_step=%s)", port, auto_step)

    # Graceful shutdown on SIGINT/SIGTERM
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    logger.info("Shutting down...")
    await server.stop(grace=5)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="SimCore gRPC Server")
    parser.add_argument("--port", type=int, default=50051, help="gRPC port")
    parser.add_argument("--auto-step", action="store_true",
                        help="Server auto-advances ticks via AI")
    parser.add_argument("--tick-rate", type=float, default=20.0,
                        help="Ticks per second (auto-step mode)")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(serve(args.port, args.auto_step, args.tick_rate))


if __name__ == "__main__":
    main()
