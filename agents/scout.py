"""RTS Scout Agent — thin AgentBase wrapper around sub_agents.ScoutAgent.

Kept for backward compatibility. The real logic lives in agents.sub_agents.
"""
from __future__ import annotations

from typing import Any

from agents.sub_agents import ScoutAgent as _ScoutCore
from agentscope_compat import AgentBase, Msg


class ScoutAgent(AgentBase):
    """AgentBase-compatible wrapper for the scout sub-agent."""

    def __init__(self, name: str = "scout", player_id: int = 1) -> None:
        super().__init__(name=name, player_id=player_id)
        self._core = _ScoutCore(player_id=player_id)

    async def reply(self, *args: Any, **kwargs: Any) -> Msg:
        obs_msg: Msg | None = kwargs.get("obs_msg") or (args[0] if args else None)
        if obs_msg is None:
            return Msg(name=self.name, content="idle", role="assistant",
                       metadata={"commands": []})

        obs = obs_msg.metadata if obs_msg.metadata else {}
        commands = self._core.decide(obs)
        tick = obs.get("tick", 0)
        return Msg(
            name=self.name,
            content=f"tick {tick}: {len(commands)} scout commands",
            role="assistant",
            metadata={"commands": commands, "tick": tick},
        )