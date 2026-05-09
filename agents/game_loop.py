"""AgentScope game loop — bridges SimCore engine with multi-agent framework.

This is the central runtime for M1:
1. SimCore produces observations per tick
2. Observations are wrapped as Msg and broadcast via MsgHub
3. Coordinator arbitrates, delegates to Economy/Combat
4. Commands are collected and fed back to SimCore
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from agents.combat import CombatAgent
from agents.coordinator import CoordinatorAgent
from agents.economy import EconomyAgent
from agentscope_compat import AgentBase, Msg, MsgHub
from simcore.engine import SimCore


class AgentScopeGameLoop:
    """Full game loop: SimCore ↔ MsgHub ↔ multi-agent.

    Usage::

        loop = AgentScopeGameLoop(player1_agents=..., player2_agents=...)
        result = await loop.run()
    """

    def __init__(
        self,
        player1_agents: dict[str, AgentBase] | None = None,
        player2_agents: dict[str, AgentBase] | None = None,
        map_seed: int = 42,
        max_ticks: int = 10000,
        tick_rate: float = 20.0,
    ) -> None:
        self.map_seed = map_seed
        self.max_ticks = max_ticks
        self.tick_rate = tick_rate

        # Build agent teams
        self.p1 = player1_agents or self._build_team(player_id=1)
        self.p2 = player2_agents or self._build_team(player_id=2)

        self.engine = SimCore(max_ticks=max_ticks)
        self._tick = 0
        self._elapsed = 0.0

    @staticmethod
    def _build_team(player_id: int) -> dict[str, AgentBase]:
        """Create default M1 three-core team."""
        econ = EconomyAgent(player_id=player_id)
        combat = CombatAgent(player_id=player_id)
        coord = CoordinatorAgent(
            player_id=player_id,
            economy_agent=econ,
            combat_agent=combat,
        )
        return {"coordinator": coord, "economy": econ, "combat": combat}

    async def run(self) -> dict[str, Any]:
        """Execute the full game and return result dict."""
        self.engine.initialize(map_seed=self.map_seed)
        t0 = time.monotonic()

        while self._tick < self.max_ticks and not self.engine.state.is_terminal:
            await self._tick_loop()
            self._tick += 1

        self._elapsed = time.monotonic() - t0

        return {
            "winner": self.engine.state.winner,
            "ticks": self._tick,
            "elapsed": self._elapsed,
            "tps": self._tick / max(self._elapsed, 1e-9),
            "replay": self.engine.replay,
        }

    async def _tick_loop(self) -> None:
        """Single tick: observe → agents decide → step engine."""
        obs = self.engine.state.get_observations()

        # Player 1 commands via MsgHub
        p1_commands = await self._agent_decide(
            obs_player=obs[0] if obs else {},
            team=self.p1,
            player_id=1,
        )

        # Player 2 commands via MsgHub
        p2_commands = await self._agent_decide(
            obs_player=obs[1] if len(obs) > 1 else {},
            team=self.p2,
            player_id=2,
        )

        # Step SimCore
        self.engine.step(p1_commands + p2_commands)

    async def _agent_decide(
        self,
        obs_player: dict,
        team: dict[str, AgentBase],
        player_id: int,
    ) -> list[dict]:
        """Run one team's agents through MsgHub and collect commands."""
        coord = team["coordinator"]
        obs_msg = Msg(
            name="simcore",
            content=f"tick {self._tick} observation for player {player_id}",
            role="user",
            metadata=obs_player,
        )

        # MsgHub broadcast: coordinator + sub-agents share observation
        participants = list(team.values())
        async with MsgHub(
            participants=participants,
            announcement=obs_msg,
        ):
            reply = await coord.reply(obs_msg=obs_msg)

        return reply.metadata.get("commands", [])

    @property
    def tick(self) -> int:
        return self._tick


def run_sync(
    map_seed: int = 42,
    max_ticks: int = 10000,
) -> dict[str, Any]:
    """Convenience: run a full game synchronously."""
    loop = AgentScopeGameLoop(map_seed=map_seed, max_ticks=max_ticks)
    return asyncio.run(loop.run())
