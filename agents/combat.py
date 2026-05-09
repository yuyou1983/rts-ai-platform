"""RTS Combat Agent — unit micro, attack priority, defense.

Managed by the Coordinator. Receives combat-budget resources.
"""
from __future__ import annotations

import math
from typing import Any

from agentscope_compat import AgentBase, Msg


class CombatAgent(AgentBase):
    """Combat sub-agent: attack, defend, scout within budget."""

    def __init__(
        self, name: str = "combat", player_id: int = 1
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
        entities = obs.get("entities", {})

        commands: list[dict] = []

        # Classify
        my_combat: list[tuple[str, dict]] = []
        enemies: list[tuple[str, dict]] = []

        for eid, e in entities.items():
            owner = e.get("owner", -1)
            etype = e.get("entity_type", "")
            if owner == self.player_id:
                if etype in ("soldier", "scout"):
                    my_combat.append((eid, e))
                if etype == "building" and e.get("building_type") == "base":
                    pass  # TODO(#M1): base defense logic
            elif owner != 0 and e.get("health", 0) > 0:
                enemies.append((eid, e))

        # No enemies → idle or scout
        if not enemies:
            # Send scouts to explore
            for sid, s in my_combat:
                if s.get("entity_type") == "scout" and s.get("is_idle"):
                    # Move towards map center-ish
                    cx, cy = 32, 32  # assume 64x64 map
                    commands.append({
                        "action": "move",
                        "unit_id": sid,
                        "target_x": cx + (hash(sid) % 20 - 10),
                        "target_y": cy + (hash(sid) % 20 - 10),
                    })
            return Msg(
                name=self.name,
                content=f"tick {tick}: no enemies, {len(commands)} scout cmds",
                role="assistant",
                metadata={"commands": commands, "tick": tick},
            )

        # Assign each combat unit to nearest enemy
        for uid, u in my_combat:
            if not u.get("is_idle", True):
                continue
            # Find nearest enemy
            best_eid, best_enemy = min(
                enemies,
                key=lambda e: math.hypot(
                    e[1].get("pos_x", 0) - u.get("pos_x", 0),
                    e[1].get("pos_y", 0) - u.get("pos_y", 0),
                ),
            )
            dist = math.hypot(
                best_enemy.get("pos_x", 0) - u.get("pos_x", 0),
                best_enemy.get("pos_y", 0) - u.get("pos_y", 0),
            )
            attack_range = u.get("attack_range", 1.5)
            if dist <= attack_range:
                commands.append({
                    "action": "attack",
                    "attacker_id": uid,
                    "target_id": best_eid,
                })
            else:
                commands.append({
                    "action": "move",
                    "unit_id": uid,
                    "target_x": best_enemy.get("pos_x", 0),
                    "target_y": best_enemy.get("pos_y", 0),
                })

        return Msg(
            name=self.name,
            content=f"tick {tick}: {len(commands)} combat commands",
            role="assistant",
            metadata={"commands": commands, "tick": tick},
        )
