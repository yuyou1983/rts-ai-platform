"""RTS Combat Agent — thin AgentBase wrapper around sub_agents.CombatAgent.

Kept for backward compatibility. The real logic lives in agents.sub_agents.
"""
from __future__ import annotations

from typing import Any

from agents.sub_agents import CombatAgent as _CombatCore
from agentscope_compat import AgentBase, Msg


class CombatAgent(AgentBase):
    """AgentBase-compatible wrapper for the combat sub-agent."""

    def __init__(self, name: str = "combat", player_id: int = 1) -> None:
        super().__init__(name=name, player_id=player_id)
        self._core = _CombatCore(player_id=player_id)

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
            content=f"tick {tick}: {len(commands)} combat commands",
            role="assistant",
            metadata={"commands": commands, "tick": tick},
        )