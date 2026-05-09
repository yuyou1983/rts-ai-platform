"""MsgHub — compatible with AgentScope's message hub (blackboard broadcast)."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ._agent_base import AgentBase
from ._msg import Msg


class MsgHub:
    """A message hub that auto-broadcasts replies among participants.

    Usage::

        async with MsgHub(participants=[coord, econ, combat],
                          announcement=obs_msg) as hub:
            await coord()
            await econ()
            await combat()
    """

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

    async def __aenter__(self) -> MsgHub:
        self._active = True
        # Broadcast announcement to all participants
        if self.announcement is not None:
            for agent in self.participants:
                await agent.observe(self.announcement)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self._active = False

    async def broadcast(self, msg: Msg) -> None:
        """Manually broadcast a message to all participants."""
        for agent in self.participants:
            await agent.observe(msg)
