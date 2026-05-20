"""Runtime auto-stepper — drives the simulation loop with AI agents.

Moved from simcore/grpc_server.py so that simcore (L1) no longer
imports from agents (L2).  The RuntimeAutoStepper owns the dict of
AI agents and advances ticks at a configured rate.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class RuntimeAutoStepper:
    """Background task that advances ticks driven by AI agents.

    Parameters
    ----------
    engine:
        A SimCore engine instance (must expose ``state``, ``step()``,
        and ``state.get_observations()``).
    agent_factory:
        Callable ``(player_id: int) -> Any`` that returns an AI agent
        with a ``decide(obs)`` interface.
    tick_rate:
        Target ticks per second.
    """

    def __init__(
        self,
        engine: Any,
        agent_factory: Callable[[int], Any],
        tick_rate: float = 10.0,
    ) -> None:
        self.engine = engine
        self._agent_factory = agent_factory
        self._tick_rate = tick_rate
        self._ai_agents: dict[int, Any] = {}
        self._auto_task: asyncio.Task | None = None

    # ─── Public API ──────────────────────────────────────────

    def create_agents(self, player_ids: list[int] | None = None) -> None:
        """Create AI agents for the given player ids (default: [1, 2])."""
        if player_ids is None:
            player_ids = [1, 2]
        self._ai_agents = {
            pid: self._agent_factory(pid) for pid in player_ids
        }
        logger.info(
            "Auto-step agents created: %s",
            {pid: type(a).__name__ for pid, a in self._ai_agents.items()},
        )

    def start(self) -> None:
        """Start the background auto-step loop (idempotent)."""
        if self._auto_task is None:
            self._auto_task = asyncio.create_task(self._auto_step_loop())

    def cancel(self) -> None:
        """Cancel the running auto-step task, if any."""
        if self._auto_task is not None:
            self._auto_task.cancel()
            self._auto_task = None

    # ─── Loop ───────────────────────────────────────────────

    async def _auto_step_loop(self) -> None:
        """Background coroutine: advance ticks at *tick_rate*, driven by AI."""
        interval = 1.0 / self._tick_rate if self._tick_rate > 0 else 0.05
        logger.info("Auto-step loop started (interval=%.3fs)", interval)
        try:
            while self.engine.state and not self.engine.state.is_terminal:
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