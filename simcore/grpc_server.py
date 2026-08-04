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
import concurrent.futures
from typing import Any, Callable

import grpc

from simcore.engine import SimCore
from simcore.proto_out.proto import service_pb2, service_pb2_grpc, state_pb2

logger = logging.getLogger(__name__)

# Type alias: agent_factory(player_id) -> agent with .decide(obs)
AgentFactory = Callable[[int], Any]

# ─── SC1 combat differentiation: event-type string → proto enum ───
# Combat events emitted by the engine carry a lowercase ``event_type``
# string (e.g. "attack_started"); the proto enum uses the same names
# uppercased.  This map bridges the two representations.
_EVENT_TYPE_TO_PROTO = {
    "attack_started": state_pb2.ATTACK_STARTED,
    "projectile_spawned": state_pb2.PROJECTILE_SPAWNED,
    "impact_resolved": state_pb2.IMPACT_RESOLVED,
    "unit_destroyed": state_pb2.UNIT_DESTROYED,
    "spell_resolved": state_pb2.SPELL_RESOLVED,
}


def _append_combat_events(proto_snapshot, events: list[dict]) -> None:
    """Append combat event dicts onto a GameStateSnapshot proto.

    ``events`` is the list-of-dicts shape produced by the engine's
    ``resolve_combat`` (and surfaced via ``engine.combat_events_this_tick``).
    Unknown ``event_type`` values raise ValueError to surface schema drift
    early rather than silently dropping events.
    """
    for event in events:
        event_type = event["event_type"]
        if event_type not in _EVENT_TYPE_TO_PROTO:
            raise ValueError(f"Unknown combat event type: {event_type}")
        ce = proto_snapshot.combat_events.add()
        ce.event_id = event.get("event_id", "")
        ce.tick = int(event.get("tick", 0))
        ce.event_type = _EVENT_TYPE_TO_PROTO[event_type]
        ce.attacker_id = event.get("attacker_id", "")
        ce.target_id = event.get("target_id", "")
        ce.weapon_id = event.get("weapon_id", "")
        ce.source_x = float(event.get("source_x", 0.0))
        ce.source_y = float(event.get("source_y", 0.0))
        ce.target_x = float(event.get("target_x", 0.0))
        ce.target_y = float(event.get("target_y", 0.0))
        ce.delivery_type = event.get("delivery_type", "")
        ce.weapon_type = event.get("weapon_type", "")
        ce.armor_type = event.get("armor_type", "")
        ce.base_damage = float(event.get("base_damage", 0.0))
        ce.final_damage = float(event.get("final_damage", 0.0))
        ce.damage_multiplier = float(event.get("damage_multiplier", 0.0))
        ce.shield_damage = float(event.get("shield_damage", 0.0))
        ce.health_damage = float(event.get("health_damage", 0.0))
        ce.projectile_id = event.get("projectile_id", "")
        ce.chain_index = int(event.get("chain_index", 0))
        ce.is_splash = bool(event.get("is_splash", False))
        ce.splash_fraction = float(event.get("splash_fraction", 1.0))
        ce.killed = bool(event.get("killed", False))
        ce.missed = bool(event.get("missed", False))
        ce.armor_value = float(event.get("armor_value", 0.0))
        ce.shield_armor_value = float(event.get("shield_armor_value", 0.0))
        ce.hit_index = int(event.get("hit_index", 0))
        ce.hit_count = int(event.get("hit_count", 1))
        ce.source_owner = int(event.get("source_owner", 0))
        ce.target_owner = int(event.get("target_owner", 0))


class SimCoreServicer(service_pb2_grpc.SimCoreServiceServicer):
    """gRPC service implementation backed by SimCore engine."""

    def __init__(
        self,
        auto_step: bool = False,
        tick_rate: float = 10.0,
        agent_factory: AgentFactory | None = None,
    ) -> None:
        self.engine = SimCore()
        self._lock = asyncio.Lock()
        self._auto_step = auto_step
        self._tick_rate = tick_rate
        # AI agent support — injected by the runtime layer
        self._agent_factory = agent_factory
        self._ai_agents: dict[int, Any] = {}
        self._auto_task: asyncio.Task | None = None

    async def StartGame(self, request, context):
        """Start a new game from config."""
        async with self._lock:
            config = request.config
            map_seed = config.map_seed or 42
            max_ticks = config.max_ticks or 10000
            tick_rate = config.tick_rate or self._tick_rate

            # Parse player_races from game_mode JSON field
            player_races = {1: "terran", 2: "terran"}
            if config.game_mode:
                import json
                try:
                    mode_data = json.loads(config.game_mode)
                    raw_races = mode_data.get("player_races", {})
                    for pid_str, race in raw_races.items():
                        player_races[int(pid_str)] = race
                except (json.JSONDecodeError, ValueError):
                    pass

            self.engine = SimCore(max_ticks=max_ticks, tick_rate=tick_rate)
            # Phase D: pass enable_elevation from config
            enable_elev = config.enable_elevation
            self.engine.initialize(
                map_seed=map_seed,
                config={
                    "map_size": config.map_width or 64,
                    "max_ticks": max_ticks,
                    "enable_elevation": enable_elev,
                    "player_races": player_races,
                },
            )

            # Create AI agents if a factory was injected
            if self._agent_factory is not None:
                self._ai_agents = {
                    1: self._agent_factory(1),
                    2: self._agent_factory(2),
                }

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

        # SC1 combat differentiation: surface this tick's combat events so
        # the gRPC/HTTP/replay pipeline can drive Godot visuals.  GetState
        # and StartGame intentionally omit combat_events (avoid stale replay).
        return self._state_to_snapshot(state, combat_events=self.engine.combat_events_this_tick)

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
                            result = ai.decide(obs[idx])
                            # Support both dict and list return shapes
                            if isinstance(result, dict):
                                all_commands.extend(result.get("commands", []))
                            else:
                                all_commands.extend(list(result) if result else [])
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
    def _state_to_snapshot(state, combat_events: list[dict] | None = None) -> state_pb2.GameStateSnapshot:
        """Convert GameState to protobuf snapshot.

        Args:
            state: GameState to serialize.
            combat_events: Optional list of combat event dicts (from
                ``engine.combat_events_this_tick``).  When provided, the
                events are appended to ``snap.combat_events``.  StartGame
                and GetState callers pass ``None`` (the default) so the
                snapshot carries no combat events — only Step() injects the
                current tick's authoritative combat facts.
        """
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
                owner=int(e.get("owner", 0)),
                entity_type=e.get("entity_type", ""),
                pos_x=e.get("pos_x", 0.0),
                pos_y=e.get("pos_y", 0.0),
                health=int(e.get("health", 0)),
                max_health=int(e.get("max_health", 0)),
                is_idle=e.get("is_idle", True),
            )
            # Optional fields — only set when present to avoid proto3 zero-vs-absent confusion
            if "speed" in e:
                entity.speed = e["speed"]
            if "attack" in e:
                entity.attack = e["attack"]
            if "attack_range" in e:
                entity.attack_range = e["attack_range"]
            if "carry_amount" in e:
                entity.carry_amount = e["carry_amount"]
            if "building_type" in e:
                entity.building_type = e["building_type"]
            if "is_constructing" in e:
                entity.is_constructing = e["is_constructing"]
            if "unit_type" in e:
                entity.unit_type = e["unit_type"]
            if "resource_type" in e:
                entity.resource_type = e["resource_type"]
            if "resource_amount" in e:
                entity.resource_amount = e["resource_amount"]
            # Movement / attack targeting state
            if e.get("attack_target_id"):
                entity.attack_target_id = e["attack_target_id"]
            if e.get("target_x") is not None:
                entity.target_x = float(e["target_x"])
            if e.get("target_y") is not None:
                entity.target_y = float(e["target_y"])
            # production_queue
            if "production_queue" in e and isinstance(e["production_queue"], list):
                for item in e["production_queue"]:
                    entity.production_queue.append(str(item))
            # production_timers (parallel to production_queue)
            if "production_timers" in e and isinstance(e["production_timers"], list):
                for t in e["production_timers"]:
                    entity.production_timers.append(int(t))
            snap.entities.append(entity)
        for key, val in state.resources.items():
            snap.resources[key] = int(val)
        # Fog-of-war per player
        fog = state.fog_of_war if hasattr(state, "fog_of_war") else {}
        for pid, field_name in [("1", "fog_p1"), ("2", "fog_p2")]:
            pf = fog.get(pid, fog) if isinstance(fog, dict) else {}
            tiles = list(pf.get("tiles", []))
            w = pf.get("width", 0)
            h = pf.get("height", 0)
            grid = state_pb2.FogGrid(tiles=tiles, width=w, height=h)
            snap.fog_p1.CopyFrom(grid) if field_name == "fog_p1" else snap.fog_p2.CopyFrom(grid)
        # Phase D: height_map
        if hasattr(state, "height_map") and state.height_map is not None:
            for row_vals in state.height_map:
                row = state_pb2.HeightRow(values=row_vals)
                snap.height_map.append(row)
        # Fill GameConfig so Godot gets map dimensions
        snap.config.map_seed = 0
        snap.config.map_width = state.map_width if hasattr(state, "map_width") else 64
        snap.config.map_height = state.map_height if hasattr(state, "map_height") else 64
        snap.config.max_ticks = 0
        snap.config.tick_rate = 0.0
        # Player races — propagate so Godot can do race-aware visual lookup
        if hasattr(state, "player_races") and isinstance(state.player_races, dict):
            for pid, race in state.player_races.items():
                snap.config.player_races[str(pid)] = race
        # ── SC1 combat differentiation: authoritative combat events ──
        if combat_events:
            _append_combat_events(snap, combat_events)
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
            ent = state_pb2.EntityState(
                id=eid,
                owner=int(e.get("owner", 0)),
                entity_type=e.get("entity_type", ""),
                pos_x=e.get("pos_x", 0.0),
                pos_y=e.get("pos_y", 0.0),
                health=int(e.get("health", 0)),
                max_health=int(e.get("max_health", 0)),
                is_idle=e.get("is_idle", True),
                building_type=e.get("building_type", ""),
                resource_type=e.get("resource_type", ""),
                resource_amount=e.get("resource_amount", 0.0),
            )
            # production_queue + production_timers
            pq = e.get("production_queue", [])
            if isinstance(pq, list):
                for item in pq:
                    ent.production_queue.append(str(item))
            pt = e.get("production_timers", [])
            if isinstance(pt, list):
                for t in pt:
                    ent.production_timers.append(int(t))
            proto.entities.append(ent)
        # Phase D: height_map from replay dict
        hm = snap.get("height_map")
        if hm and isinstance(hm, list):
            for row_vals in hm:
                row = state_pb2.HeightRow(values=row_vals)
                proto.height_map.append(row)
        # Fill GameConfig from replay dict
        proto.config.map_width = snap.get("map_width", 64)
        proto.config.map_height = snap.get("map_height", 64)
        # ── SC1 combat differentiation: replay combat events ──
        # Replay snapshots store combat_events as a list of dicts (same
        # shape as engine.combat_events_this_tick); forward them so V1
        # replays streamed via GetReplay carry authoritative combat facts.
        _append_combat_events(proto, snap.get("combat_events", []))
        return proto


async def serve(port: int = 50051, auto_step: bool = False,
                tick_rate: float = 10.0,
                agent_factory: AgentFactory | None = None) -> None:
    """Start the gRPC server with graceful shutdown."""
    server = grpc.aio.server(concurrent.futures.ThreadPoolExecutor(max_workers=4))
    servicer = SimCoreServicer(
        auto_step=auto_step,
        tick_rate=tick_rate,
        agent_factory=agent_factory,
    )
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
    parser.add_argument("--tick-rate", type=float, default=10.0,
                        help="Ticks per second (auto-step mode)")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Load agent factory dynamically to avoid L1→L2 import violation.
    # runtime.agent_factory is L2; simcore must not statically import it.
    agent_factory = None
    if args.auto_step:
        import importlib
        _mod = importlib.import_module("runtime.agent_factory")
        agent_factory = _mod.create_ai_agent

    asyncio.run(serve(args.port, args.auto_step, args.tick_rate, agent_factory))


if __name__ == "__main__":
    main()