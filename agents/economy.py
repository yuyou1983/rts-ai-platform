"""RTS Economy Agent — resource gathering, building, and production.

Managed by the Coordinator. Operates within a resource budget.
"""
from __future__ import annotations

import math
from typing import Any

from agentscope_compat import AgentBase, Msg


class EconomyAgent(AgentBase):
    """Economy sub-agent: gather, build, train within budget."""

    def __init__(
        self, name: str = "economy", player_id: int = 1
    ) -> None:
        super().__init__(name=name, player_id=player_id)

    async def reply(self, *args: Any, **kwargs: Any) -> Msg:
        obs_msg: Msg | None = kwargs.get("obs_msg") or (
            args[0] if args else None
        )
        if obs_msg is None:
            return Msg(name=self.name, content="idle", role="assistant",
                       metadata={"commands": []})

        obs = obs_msg.metadata if obs_msg.metadata else {}
        tick = obs.get("tick", 0)
        budget = obs.get("budget", {})
        mineral_budget = budget.get("mineral", 0)
        entities = obs.get("entities", {})

        commands: list[dict] = []
        spent_mineral = 0.0

        # Classify entities
        my_workers: list[tuple[str, dict]] = []
        my_buildings: list[tuple[str, dict]] = []
        resources: list[tuple[str, dict]] = []
        my_base: dict | None = None

        for eid, e in entities.items():
            owner = e.get("owner", -1)
            if owner != self.player_id:
                if owner == 0 and e.get("entity_type") == "resource":
                    resources.append((eid, e))
                continue
            etype = e.get("entity_type", "")
            if etype == "worker":
                my_workers.append((eid, e))
            elif etype == "building":
                my_buildings.append((eid, e))
                if e.get("building_type") == "base" and e.get("health", 0) > 0:
                    my_base = e

        # Priority 1: Assign idle workers to gather
        for wid, w in my_workers:
            if not w.get("is_idle", True):
                continue
            if not resources:
                break
            # Find nearest resource
            best_rid, best_r = min(
                resources,
                key=lambda r: math.hypot(
                    r[1].get("pos_x", 0) - w.get("pos_x", 0),
                    r[1].get("pos_y", 0) - w.get("pos_y", 0),
                ),
            )
            commands.append({
                "action": "gather",
                "worker_id": wid,
                "resource_id": best_rid,
            })

        # Priority 2: Build barracks if none exist (cost: 150 mineral)
        has_barracks = any(
            b.get("building_type") == "barracks"
            for _, b in my_buildings
            if b.get("health", 0) > 0
        )
        if not has_barracks and mineral_budget - spent_mineral >= 150 and my_base:
            builder = my_workers[0] if my_workers else None
            if builder:
                bx = my_base.get("pos_x", 0) + 5
                by = my_base.get("pos_y", 0) + 5
                commands.append({
                    "action": "build",
                    "builder_id": builder[0],
                    "building_type": "barracks",
                    "pos_x": bx,
                    "pos_y": by,
                })
                spent_mineral += 150

        # Priority 3: Train soldiers from barracks (cost: 50 mineral each)
        for bid, b in my_buildings:
            if b.get("building_type") != "barracks":
                continue
            if b.get("health", 0) <= 0:
                continue
            if mineral_budget - spent_mineral >= 50:
                commands.append({
                    "action": "train",
                    "building_id": bid,
                    "unit_type": "soldier",
                })
                spent_mineral += 50

        return Msg(
            name=self.name,
            content=f"tick {tick}: {len(commands)} econ commands",
            role="assistant",
            metadata={"commands": commands, "tick": tick},
        )
