"""MsgHub — compatible with AgentScope's message hub (blackboard broadcast).

Enhanced: supports both sync and async context managers.
Auto-broadcast fires when any participant calls reply() inside the hub.

Usage::

    hub = MsgHub(participants=[coord, econ, combat], announcement=obs_msg)
    with hub:                    # sync
        ...
    async with hub:             # async
        ...
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from agentscope_compat._agent_base import AgentBase
from agentscope_compat._msg import Msg


class MsgHub:
    """A message hub that auto-broadcasts messages among participants."""

    def __init__(
        self,
        participants: Sequence[AgentBase],
        announcement: Msg | list[Msg] | None = None,
        enable_auto_broadcast: bool = True,
        name: str | None = None,
    ) -> None:
        self.participants = list(participants)
        self.announcement = announcement
        self.enable_auto_broadcast = enable_auto_broadcast
        self.name = name or f"hub_{id(self)}"
        self._active = False
        self._history: list[Msg] = []
        self._pending_announce: list[Msg] = []

    @property
    def active(self) -> bool:
        return self._active

    def _open(self) -> MsgHub:
        """Activate hub and broadcast announcement to all participants."""
        self._active = True
        if self.announcement is not None:
            msgs = self.announcement if isinstance(self.announcement, list) else [self.announcement]
            for m in msgs:
                self._history.append(m)
            # Don't broadcast here — callers (sync/async) will handle it
            self._pending_announce = msgs
        return self

    async def _announce_async(self) -> None:
        """Broadcast pending announcement asynchronously."""
        if not self._pending_announce:
            return
        for m in self._pending_announce:
            for agent in self.participants:
                await agent.observe(m)
        self._pending_announce = []

    def _announce_sync(self) -> None:
        """Broadcast pending announcement synchronously."""
        if not self._pending_announce:
            return
        for m in self._pending_announce:
            self._broadcast_sync(m)
        self._pending_announce = []

    def _close(self) -> None:
        """Deactivate hub."""
        self._active = False

    def _broadcast_sync(self, msg: Msg) -> None:
        """Broadcast a message to all participants synchronously."""
        self._history.append(msg)
        for agent in self.participants:
            # observe is always async in AgentBase — run it properly
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # Already inside an event loop — use nest_asyncio or thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(asyncio.run, agent.observe(msg)).result()
            else:
                asyncio.run(agent.observe(msg))

    def broadcast(self, msg: Msg) -> None:
        """Broadcast a message to all participants (sync)."""
        self._broadcast_sync(msg)

    async def broadcast_async(self, msg: Msg) -> None:
        """Broadcast a message to all participants (async)."""
        self._history.append(msg)
        for agent in self.participants:
            await agent.observe(msg)

    def auto_broadcast(self, msg: Msg) -> None:
        """Broadcast if auto_broadcast is enabled and hub is active."""
        if self.enable_auto_broadcast and self._active:
            self._broadcast_sync(msg)

    @property
    def history(self) -> list[Msg]:
        """Read-only access to broadcast history."""
        return list(self._history)

    # Sync context manager
    def __enter__(self) -> MsgHub:
        self._open()
        self._announce_sync()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._close()

    # Async context manager
    async def __aenter__(self) -> MsgHub:
        self._open()
        await self._announce_async()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self._close()