"""SimCore runner service — runs a live AI vs AI battle and streams frames via WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

logger = logging.getLogger("sim_runner")


class SimRunner:
    """Manages a live SimCore battle and broadcasts tick state to WebSocket clients.

    Usage:
        runner = SimRunner()
        await runner.start()           # initializes engine & starts game loop
        await runner.add_client(ws)     # register a WebSocket client
        # game loop runs in background, pushing frames to all clients
    """

    def __init__(
        self,
        map_seed: int = 42,
        max_ticks: int = 5000,
        tick_interval_ms: int = 100,
        agent1_name: str = "RushAI",
        agent2_name: str = "GreedyGatherer",
    ):
        self.map_seed = map_seed
        self.max_ticks = max_ticks
        self.tick_interval_ms = tick_interval_ms
        self.agent1_name = agent1_name
        self.agent2_name = agent2_name

        self._engine: Any = None
        self._agents: list[Any] = []
        self._clients: set[Any] = set()  # WebSocket objects
        self._task: asyncio.Task | None = None
        self._running = False

    # ── Public API ───────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize SimCore engine and start the game loop as a background task."""
        from simcore.engine import SimCore
        from simcore.agents import RushAI, GreedyGatherer

        agent_cls_map = {
            "RushAI": RushAI,
            "GreedyGatherer": GreedyGatherer,
        }

        self._engine = SimCore(max_ticks=self.max_ticks)
        self._engine.initialize(map_seed=self.map_seed)

        Agent1 = agent_cls_map.get(self.agent1_name, RushAI)
        Agent2 = agent_cls_map.get(self.agent2_name, GreedyGatherer)

        self._agents = [Agent1(player_id=1), Agent2(player_id=2)]

        self._running = True
        self._task = asyncio.create_task(self._game_loop())
        logger.info("SimRunner started (seed=%d, max_ticks=%d)", self.map_seed, self.max_ticks)

    async def stop(self) -> None:
        """Stop the game loop and close all clients."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Close all connected clients
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        logger.info("SimRunner stopped")

    async def add_client(self, websocket: Any) -> None:
        """Register a WebSocket client to receive tick broadcasts."""
        self._clients.add(websocket)
        # If the engine is already running, send the current state immediately
        if self._engine and self._engine.state:
            await self._send_frame(websocket, self._serialize_state(self._engine.state))

    def remove_client(self, websocket: Any) -> None:
        """Unregister a WebSocket client."""
        self._clients.discard(websocket)

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    # ── Internal ─────────────────────────────────────────────────────────

    def _serialize_state(self, state: Any) -> dict:
        """Convert a GameState to the wire format for the dashboard."""
        entities_out: dict[str, dict] = {}
        for eid, e in state.entities.items():
            # Skip internal meta-entries
            if eid.startswith("__"):
                continue
            entities_out[eid] = {
                "owner": e.get("owner", 0),
                "entity_type": e.get("entity_type", ""),
                "unit_type": e.get("unit_type", ""),
                "building_type": e.get("building_type", ""),
                "x": round(e.get("pos_x", 0.0), 2),
                "y": round(e.get("pos_y", 0.0), 2),
                "health": round(e.get("health", 0), 1),
                "max_health": round(e.get("max_health", 0), 1),
                "shields": round(e.get("shields", 0), 1),
                "max_shields": round(e.get("max_shields", 0), 1),
                "is_constructing": e.get("is_constructing", False),
                "is_idle": e.get("is_idle", True),
                "resource_type": e.get("resource_type", ""),
                "resource_amount": e.get("resource_amount", 0),
            }

        resources_out: dict[str, int] = {}
        for key, val in state.resources.items():
            resources_out[key] = val

        return {
            "tick": state.tick,
            "entities": entities_out,
            "resources": resources_out,
            "is_terminal": state.is_terminal,
            "winner": state.winner,
            "map_width": state.map_width,
            "map_height": state.map_height,
        }

    async def _game_loop(self) -> None:
        """Main game loop: step the engine and broadcast state each tick."""
        try:
            while self._running and self._engine and not self._engine.state.is_terminal:
                # Get agent observations and decisions
                obs = self._engine.get_observations(1), self._engine.get_observations(2)
                commands: list[dict] = []
                for agent, o in zip(self._agents, obs):
                    cmds = agent.decide(o)
                    if cmds:
                        commands.extend(cmds)

                # Step the engine
                state = self._engine.step(commands)

                # Serialize and broadcast
                frame = self._serialize_state(state)
                frame_json = json.dumps(frame)
                await self._broadcast(frame_json)

                # Throttle to desired tick rate
                await asyncio.sleep(self.tick_interval_ms / 1000.0)

            # Game ended — send final frame with terminal flag
            if self._engine and self._engine.state:
                final = self._serialize_state(self._engine.state)
                await self._broadcast(json.dumps(final))
                logger.info("Game ended: tick=%d, winner=%d", final["tick"], final["winner"])

        except asyncio.CancelledError:
            logger.info("Game loop cancelled")
        except Exception as e:
            logger.exception("Game loop error: %s", e)
        finally:
            self._running = False

    async def _broadcast(self, message: str) -> None:
        """Send a message to all connected WebSocket clients."""
        dead: list[Any] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def _send_frame(self, websocket: Any, frame: dict) -> None:
        """Send a single frame dict to one specific WebSocket client."""
        try:
            await websocket.send_text(json.dumps(frame))
        except Exception:
            self._clients.discard(websocket)
