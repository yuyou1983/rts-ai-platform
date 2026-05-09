"""RTS Coordinator Agent — global arbitration via MsgHub.

M1 three-core architecture: Coordinator → Economy + Combat.

The Coordinator:
1. Reads the world observation
2. Assignes strategic priorities (economy vs combat vs scout)
3. Distributes resource budget across sub-agents
4. Collects sub-agent commands and resolves conflicts
"""
from __future__ import annotations

from typing import Any

from agentscope_compat import AgentBase, Msg


class CoordinatorAgent(AgentBase):
    """Top-level coordinator: arbitrates resource budget and priorities."""

    def __init__(
        self,
        name: str = "coordinator",
        player_id: int = 1,
        economy_agent: AgentBase | None = None,
        combat_agent: AgentBase | None = None,
    ) -> None:
        super().__init__(name=name, player_id=player_id)
        self.economy = economy_agent
        self.combat = combat_agent

    async def reply(self, *args: Any, **kwargs: Any) -> Msg:
        """Process world observation → distribute budget → collect commands.

        Returns a Msg with metadata["commands"] = merged command list.
        """
        obs_msg: Msg | None = kwargs.get("obs_msg") or (
            args[0] if args else None
        )
        if obs_msg is None:
            return Msg(
                name=self.name,
                content="no observation",
                role="assistant",
                metadata={"commands": [], "tick": 0},
            )

        obs: dict = obs_msg.metadata if obs_msg.metadata else {}
        tick = obs.get("tick", 0)
        resources = obs.get("resources", {})
        minerals = resources.get(f"p{self.player_id}_mineral", 0)
        gas = resources.get(f"p{self.player_id}_gas", 0)
        entities = obs.get("entities", {})

        # ── Strategy: simple phase-based priority ──
        my_units = [
            e for e in entities.values()
            if e.get("owner") == self.player_id
        ]
        my_soldiers = [u for u in my_units if u.get("entity_type") == "soldier"]
        enemy_count = sum(
            1 for e in entities.values()
            if e.get("owner") not in (0, self.player_id)
            and e.get("health", 0) > 0
        )

        # Budget allocation: 60/40 economy/combat in early game,
        # 30/70 when threatened
        if enemy_count > len(my_soldiers) * 1.5:
            econ_budget, combat_budget = 0.3, 0.7
        else:
            econ_budget, combat_budget = 0.6, 0.4

        # Dispatch to sub-agents
        commands: list[dict] = []

        if self.economy:
            econ_obs = self._make_sub_obs(
                obs, minerals * econ_budget, gas * econ_budget
            )
            econ_msg = Msg(
                name="world", content="economy phase",
                role="user", metadata=econ_obs,
            )
            econ_reply = await self.economy.reply(obs_msg=econ_msg)
            commands.extend(econ_reply.metadata.get("commands", []))

        if self.combat:
            combat_obs = self._make_sub_obs(
                obs, minerals * combat_budget, gas * combat_budget
            )
            combat_msg = Msg(
                name="world", content="combat phase",
                role="user", metadata=combat_obs,
            )
            combat_reply = await self.combat.reply(obs_msg=combat_msg)
            commands.extend(combat_reply.metadata.get("commands", []))

        return Msg(
            name=self.name,
            content=f"tick {tick}: {len(commands)} commands",
            role="assistant",
            metadata={"commands": commands, "tick": tick},
        )

    def _make_sub_obs(
        self, obs: dict, mineral_budget: float, gas_budget: float
    ) -> dict:
        """Create a sub-agent observation with budget constraints."""
        sub = dict(obs)
        sub["budget"] = {
            "mineral": mineral_budget,
            "gas": gas_budget,
        }
        return sub
