"""RTS Coordinator Agent — global arbitration with sub-agent dispatch.

Architecture:
  Coordinator
  ├── EconomyAgent  (workers, building, resource collection)
  ├── CombatAgent   (soldiers, attack orders, unit production)
  └── ScoutAgent    (reconnaissance patrol)

The Coordinator:
1. Reads the world observation
2. Computes strategic phase and budget split
3. Dispatches to sub-agents with budget-limited observations
4. Merges and deduplicates commands
5. Broadcasts summary via MsgHub (if active)
"""
from __future__ import annotations

import math
from typing import Any

from agents.sub_agents import EconomyAgent, CombatAgent, ScoutAgent
from agentscope_compat import AgentBase, Msg


class CoordinatorAgent(AgentBase):
    """Top-level coordinator: arbitrates resource budget and priorities."""

    def __init__(
        self,
        name: str = "coordinator",
        player_id: int = 1,
    ) -> None:
        super().__init__(name=name, player_id=player_id)
        self.economy = EconomyAgent(player_id=player_id)
        self.combat = CombatAgent(player_id=player_id)
        self.scout = ScoutAgent(player_id=player_id)
        self._hub = None  # Optional MsgHub for inter-agent broadcast

    def attach_hub(self, hub: Any) -> None:
        """Attach a MsgHub for broadcasting state summaries."""
        self._hub = hub

    def decide(self, obs: dict) -> dict:
        """Synchronous entry point: observation → merged commands.

        This is the primary interface called by SimCore's game loop.
        """
        tick = obs.get("tick", 0)
        entities = obs.get("entities", {})
        resources = obs.get("resources", {})

        mineral_key = f"p{self.player_id}_mineral"
        gas_key = f"p{self.player_id}_gas"
        mineral = resources.get(mineral_key, 0) if isinstance(resources, dict) else 0
        gas = resources.get(gas_key, 0) if isinstance(resources, dict) else 0

        # ── Phase & budget allocation ──
        my_soldiers = sum(
            1 for e in entities.values()
            if e.get("owner") == self.player_id and e.get("entity_type") == "soldier"
        )
        enemy_combat = sum(
            1 for e in entities.values()
            if e.get("owner") not in (0, self.player_id)
            and e.get("health", 0) > 0
            and e.get("entity_type") in ("soldier", "scout")
        )
        my_base = _find_my_base(entities, self.player_id)
        base_threat = any(
            _dist(my_base or {"pos_x": 0, "pos_y": 0}, e) < 12
            for e in entities.values()
            if e.get("owner") not in (0, self.player_id) and e.get("health", 0) > 0
        )

        # Budget split: economy vs combat
        if base_threat or enemy_combat > my_soldiers * 1.5:
            econ_frac, combat_frac = 0.3, 0.7
        elif my_soldiers >= 8:
            econ_frac, combat_frac = 0.4, 0.6
        else:
            econ_frac, combat_frac = 0.6, 0.4

        # ── Dispatch to sub-agents ──
        econ_obs = _with_budget(obs, mineral * econ_frac, gas * econ_frac)
        combat_obs = _with_budget(obs, mineral * combat_frac, gas * combat_frac)

        econ_cmds = self.economy.decide(econ_obs)
        combat_cmds = self.combat.decide(combat_obs)
        scout_cmds = self.scout.decide(obs)  # scouts have no budget

        # ── Merge & deduplicate ──
        all_cmds = econ_cmds + combat_cmds + scout_cmds
        merged = _dedup_commands(all_cmds)

        # ── Broadcast to hub (if attached) ──
        if self._hub is not None:
            summary = Msg(
                name=self.name,
                content=f"tick {tick}: {len(merged)} commands "
                        f"(econ={len(econ_cmds)} combat={len(combat_cmds)} scout={len(scout_cmds)})",
                role="assistant",
                metadata={"commands": merged, "tick": tick,
                          "phase": "threat" if base_threat else "normal",
                          "budget_split": {"econ": econ_frac, "combat": combat_frac}},
            )
            # Sync wrapper for async broadcast
            import asyncio
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._hub.broadcast(summary))

        return {"commands": merged, "tick": tick}

    async def reply(self, *args: Any, **kwargs: Any) -> Msg:
        """Async interface for AgentScope compatibility."""
        obs_msg: Msg | None = kwargs.get("obs_msg") or (args[0] if args else None)
        if obs_msg is None:
            return Msg(name=self.name, content="no obs", role="assistant",
                       metadata={"commands": [], "tick": 0})
        obs = obs_msg.metadata if obs_msg.metadata else {}
        result = self.decide(obs)
        return Msg(name=self.name, content=f"tick {result['tick']}", role="assistant",
                   metadata=result)


# ─── Helpers ────────────────────────────────────────────────

def _with_budget(obs: dict, mineral: float, gas: float) -> dict:
    """Create a sub-agent observation with budget constraints."""
    sub = dict(obs)
    sub["budget"] = {"mineral": mineral, "gas": gas}
    return sub


def _dedup_commands(cmds: list[dict]) -> list[dict]:
    """Remove duplicate commands for the same unit."""
    seen_units: set[str] = set()
    result: list[dict] = []
    for cmd in cmds:
        action = cmd.get("action", "")
        # Build command: dedup by builder_id + "build" to avoid clash with gather
        if action == "build":
            uid = cmd.get("builder_id") or cmd.get("worker_id") or ""
            key = f"build_{uid}" if uid else ""
        else:
            uid = (
                cmd.get("unit_id") or cmd.get("worker_id") or cmd.get("attacker_id")
                or cmd.get("builder_id") or cmd.get("entity_id")
            )
            key = uid or ""

        if key and key in seen_units:
            continue
        if key:
            seen_units.add(key)
        # Also dedup train commands per building
        bid = cmd.get("building_id")
        if action == "train" and bid:
            train_key = f"train_{bid}_{cmd.get('unit_type')}"
            if train_key in seen_units:
                continue
            seen_units.add(train_key)
        result.append(cmd)
    return result


def _find_my_base(entities: dict, player_id: int) -> dict | None:
    for eid, e in entities.items():
        if (e.get("owner") == player_id
                and e.get("building_type") == "base"
                and e.get("health", 0) > 0):
            return e
    return None


def _dist(a: dict, b: dict) -> float:
    dx = a.get("pos_x", 0) - b.get("pos_x", 0)
    dy = a.get("pos_y", 0) - b.get("pos_y", 0)
    return math.sqrt(dx * dx + dy * dy)