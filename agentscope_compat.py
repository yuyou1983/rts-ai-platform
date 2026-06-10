"""agentscope_compat — minimal compatibility shim for AgentScope interfaces.

This module provides the AgentBase / Msg / MsgHub abstractions used by
the multi-agent architecture (Coordinator, Economy, Combat, Scout, etc.)
without requiring a hard dependency on the `agentscope` package.

When `agentscope` is installed, all symbols are re-exported directly.
Otherwise, lightweight local implementations are provided so that
the agent code remains importable and testable.

To use the real agentscope, install the optional dependency:
    pip install 'rts-ai-platform[agents]'
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try real agentscope first; fall back to local implementations.
# ---------------------------------------------------------------------------
try:
    from agentscope import AgentBase, Msg, MsgHub  # type: ignore[import-untyped]
    logger.debug("agentscope available — using upstream AgentBase/Msg/MsgHub")
except ImportError:
    logger.debug("agentscope not installed — using local compat shim")

    # ---- Msg -----------------------------------------------------------
    @dataclass
    class Msg:  # type: ignore[no-redef]
        """Lightweight message object compatible with agentscope.Msg."""

        name: str = ""
        content: Any = None
        role: str = "assistant"
        metadata: dict[str, Any] = field(default_factory=dict)

        def __str__(self) -> str:
            return f"Msg(name={self.name!r}, role={self.role!r})"

    # ---- AgentBase -----------------------------------------------------
    class AgentBase:  # type: ignore[no-redef]
        """Minimal AgentScope-compatible agent base class."""

        name: str

        def __init__(self, name: str = "agent", **_kwargs: Any) -> None:
            self.name = name

        def reply(self, x: Msg | list[Msg] | None = None) -> Msg:
            """Process an incoming message and return a reply."""
            raise NotImplementedError(
                f"{self.__class__.__name__}.reply() not implemented"
            )

        async def reply_async(self, x: Msg | list[Msg] | None = None) -> Msg:
            """Async variant of reply — default wraps the sync version."""
            return self.reply(x)

    # ---- MsgHub --------------------------------------------------------
    class MsgHub:  # type: ignore[no-redef]
        """Minimal message-hub for broadcasting Msg to participants.

        Supports both sync and async context-manager usage:
            async with MsgHub(participants=[a, b], announcement=Msg(...)):
                ...
        """

        def __init__(
            self,
            participants: list[AgentBase] | None = None,
            announcement: Msg | None = None,
        ) -> None:
            self._participants = participants or []
            self._announcement = announcement

        async def broadcast(self, msg: Msg | str) -> None:
            """Send *msg* to every participant's ``observe`` method."""
            if isinstance(msg, str):
                msg = Msg(name="hub", content=msg)
            for agent in self._participants:
                observe_fn = getattr(agent, "observe", None)
                if observe_fn and callable(observe_fn):
                    if asyncio.iscoroutinefunction(observe_fn):
                        await observe_fn(msg)
                    else:
                        observe_fn(msg)

        # -- async context manager ---------------------------------------
        async def __aenter__(self) -> MsgHub:
            if self._announcement:
                await self.broadcast(self._announcement)
            return self

        async def __aexit__(self, *exc: Any) -> None:
            pass

        # -- sync context manager (thin wrapper) -------------------------
        def __enter__(self) -> MsgHub:
            if self._announcement:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.broadcast(self._announcement))
                except RuntimeError:
                    asyncio.run(self.broadcast(self._announcement))
            return self

        def __exit__(self, *exc: Any) -> None:
            pass


__all__ = ["AgentBase", "Msg", "MsgHub"]
