"""Enhanced scripted AI — rule-based RTS opponent with difficulty balancing.

Difficulty levels:
  easy:   slow reaction, no micro, limited production
  medium: moderate reaction, basic micro
  hard:   fast reaction, focus fire, retreat  (original behavior)

Key balance levers:
  - tick_delay: AI only decides every N ticks (APM throttle)
  - production_cap: limits on workers/soldiers/scouts
  - rally_size: minimum group before attacking
  - reaction_delay: ticks before reacting to threats
  - micro_enabled: focus fire, retreat, etc.
"""
from __future__ import annotations

import math
from typing import Any


class ScriptAI:
    """Tactical rule-based RTS AI with difficulty settings."""

    # ─── Production caps per difficulty ─────────────────────────
    _DIFFICULTY_PRESETS = {
        "easy": {
            "max_workers": 8,
            "max_soldiers": 8,
            "max_scouts": 0,
            "rally_size": 6,        # need 6 soldiers before pushing
            "tick_delay": 5,       # decide only every 5 ticks
            "reaction_delay": 15,  # ticks before reacting to base threat
            "micro_enabled": False,
            "scout_enabled": False,
            "build_barracks_tick": 300,  # don't build barracks until tick 300
        },
        "medium": {
            "max_workers": 12,
            "max_soldiers": 14,
            "max_scouts": 2,
            "rally_size": 4,
            "tick_delay": 2,
            "reaction_delay": 5,
            "micro_enabled": True,
            "scout_enabled": True,
            "build_barracks_tick": 100,
        },
        "hard": {
            "max_workers": 14,
            "max_soldiers": 20,
            "max_scouts": 4,
            "rally_size": 2,
            "tick_delay": 1,
            "reaction_delay": 0,
            "micro_enabled": True,
            "scout_enabled": True,
            "build_barracks_tick": 0,
        },
    }

    def __init__(self, player_id: int = 2, difficulty: str = "medium") -> None:
        self.player_id = player_id
        self.difficulty = difficulty

        preset = self._DIFFICULTY_PRESETS.get(difficulty,
                                               self._DIFFICULTY_PRESETS["medium"])
        self.MAX_WORKERS = preset["max_workers"]
        self.MAX_SOLDIERS = preset["max_soldiers"]
        self.MAX_SCOUTS = preset["max_scouts"]
        self.RALLY_SIZE = preset["rally_size"]
        self._tick_delay = preset["tick_delay"]
        self._reaction_delay = preset["reaction_delay"]
        self._micro_enabled = preset["micro_enabled"]
        self._scout_enabled = preset["scout_enabled"]
        self._build_barracks_tick = preset["build_barracks_tick"]

        self.BARRACKS_COST = 150
        self.WORKER_COST = 50
        self.SOLDIER_COST = 100
        self.SCOUT_COST = 75

        # Internal state
        self._rally_point: tuple[float, float] | None = None
        self._attack_issued = False
        self._last_decision_tick = -999
        self._threat_detected_tick = -999

    def decide(self, obs: dict) -> dict:
        """Generate commands from observation using heuristic rules."""
        commands: list[dict] = []
        tick = obs.get("tick", 0)
        entities = obs.get("entities", {})

        # ─── APM throttle: skip ticks ────────────────────────────
        if tick - self._last_decision_tick < self._tick_delay:
            return {"commands": [], "tick": tick}
        self._last_decision_tick = tick

        my_stuff = {k: v for k, v in entities.items()
                    if v.get("owner") == self.player_id}

        # Categorize entities
        idle_workers: list[tuple[str, dict]] = []
        gathering_workers: list[tuple[str, dict]] = []
        idle_soldiers: list[tuple[str, dict]] = []
        idle_scouts: list[tuple[str, dict]] = []
        my_buildings: dict[str, dict] = {}
        my_base: dict | None = None
        enemies: list[tuple[str, dict]] = []

        # Find my base
        my_base = None
        for eid, e in entities.items():
            if (e.get("owner") == self.player_id
                    and e.get("entity_type") == "building"
                    and e.get("building_type") == "base"):
                my_base = e
                break

        # Categorize
        for eid, e in entities.items():
            owner = e.get("owner", 0)
            etype = e.get("entity_type", "")
            idle = e.get("is_idle", True)

            if owner == self.player_id:
                if etype == "worker":
                    if idle and not e.get("returning_to_base"):
                        # Retreat damaged workers (micro only)
                        if self._micro_enabled:
                            health_frac = (e.get("health", 0)
                                           / max(e.get("max_health", 1), 1))
                            if health_frac < 0.3 and my_base:
                                commands.append({
                                    "action": "move",
                                    "unit_id": eid,
                                    "target_x": my_base["pos_x"],
                                    "target_y": my_base["pos_y"],
                                    "issuer": self.player_id,
                                })
                                continue
                        idle_workers.append((eid, e))
                    elif not idle and e.get("carry_amount", 0) > 0:
                        gathering_workers.append((eid, e))
                elif etype == "soldier" and idle:
                    idle_soldiers.append((eid, e))
                elif etype == "scout" and idle:
                    idle_scouts.append((eid, e))
                elif etype == "building":
                    my_buildings[eid] = e
            elif owner != 0 and e.get("health", 0) > 0:
                enemies.append((eid, e))

        # Resources
        mineral_key = f"p{self.player_id}_mineral"
        gas_key = f"p{self.player_id}_gas"
        resources = obs.get("resources", {})
        mineral = resources.get(mineral_key, 0) if isinstance(resources, dict) else 0
        gas = resources.get(gas_key, 0) if isinstance(resources, dict) else 0
        worker_count = len([e for _, e in my_stuff.items()
                           if e.get("entity_type") == "worker"])
        soldier_count = len([e for _, e in my_stuff.items()
                            if e.get("entity_type") == "soldier"])

        # ─── Rule 1: Idle workers → gather ──────────────────────
        mineral_patches = [(eid, e) for eid, e in entities.items()
                           if e.get("entity_type") == "resource"
                           and e.get("resource_type") == "mineral"
                           and e.get("resource_amount", 0) > 0]
        gas_patches = [(eid, e) for eid, e in entities.items()
                       if e.get("entity_type") == "resource"
                       and e.get("resource_type") == "gas"
                       and e.get("resource_amount", 0) > 0]

        for wid, worker in idle_workers:
            if not mineral_patches:
                break
            # Assign gas workers after 8 miners (micro only)
            if (self._micro_enabled and worker_count > 8
                    and gas_patches
                    and len([1 for _, gw in gathering_workers
                             if entities.get(gw.get("attack_target_id", ""),
                                             {}).get("resource_type") == "gas"]) < 2):
                patches = gas_patches
            else:
                patches = mineral_patches

            best_patch = None
            best_dist = float("inf")
            for pid, patch in patches:
                d = _dist(worker, patch)
                if d < best_dist:
                    best_dist = d
                    best_patch = (pid, patch)

            if best_patch:
                pid, patch = best_patch
                commands.append({
                    "action": "gather",
                    "worker_id": wid,
                    "resource_id": pid,
                    "issuer": self.player_id,
                })

        # ─── Rule 2: Combat — focus fire or push ─────────────────
        enemy_base_x, enemy_base_y = 54.0, 54.0
        if self.player_id == 1:
            enemy_base_x, enemy_base_y = 54.0, 54.0
        else:
            enemy_base_x, enemy_base_y = 10.0, 10.0

        if idle_soldiers and enemies:
            # Focus fire: target weakest enemy
            target_eid, target_e = min(
                enemies,
                key=lambda x: x[1].get("health", 100)
                               / max(x[1].get("max_health", 100), 1)
            )

            # Base threat detection (with reaction delay)
            base_threat = False
            if my_base:
                base_threat = any(
                    _dist(my_base, e) < 10 for _, e in enemies
                )
            if base_threat and tick - self._threat_detected_tick < self._reaction_delay:
                base_threat = False  # not reacting yet
            elif base_threat:
                self._threat_detected_tick = tick

            # Attack condition: enough soldiers OR base threatened OR late game
            should_attack = (
                len(idle_soldiers) >= self.RALLY_SIZE
                or base_threat
                or tick > 800
            )

            if should_attack:
                for uid, _ in idle_soldiers:
                    commands.append({
                        "action": "attack",
                        "attacker_id": uid,
                        "target_id": target_eid,
                        "issuer": self.player_id,
                    })

        elif idle_soldiers and tick > 800:
            for uid, _ in idle_soldiers:
                commands.append({
                    "action": "move",
                    "unit_id": uid,
                    "target_x": enemy_base_x,
                    "target_y": enemy_base_y,
                    "issuer": self.player_id,
                })

        # ─── Rule 3: Scouts patrol (if enabled) ─────────────────
        if self._scout_enabled:
            for sid, scout in idle_scouts:
                enemy_quadrant = 0.85 if self.player_id == 1 else 0.15
                tx = 64 * enemy_quadrant
                ty = 64 * enemy_quadrant
                commands.append({
                    "action": "move",
                    "unit_id": sid,
                    "target_x": tx,
                    "target_y": ty,
                    "issuer": self.player_id,
                })

        # ─── Rule 4: Build barracks (with tick gate) ─────────────
        has_barracks = any(b.get("building_type") == "barracks"
                           and not b.get("is_constructing", False)
                           for b in my_buildings.values())
        barracks_building = any(b.get("building_type") == "barracks"
                                and b.get("is_constructing", False)
                                for b in my_buildings.values())

        if (not has_barracks and not barracks_building
                and tick >= self._build_barracks_tick
                and mineral >= self.BARRACKS_COST and idle_workers):
            wid, worker = idle_workers[0]
            bx = (my_base or worker).get("pos_x", 10) + 3
            by = (my_base or worker).get("pos_y", 10)
            commands.append({
                "action": "build",
                "builder_id": wid,
                "building_type": "barracks",
                "pos_x": bx,
                "pos_y": by,
                "issuer": self.player_id,
            })
            mineral -= self.BARRACKS_COST

        # ─── Rule 5: Train workers ──────────────────────────────
        completed_barracks = [b for b in my_buildings.values()
                              if b.get("building_type") == "barracks"
                              and not b.get("is_constructing")]
        production_building = (my_base
                               or (completed_barracks[0]
                                   if completed_barracks else None))

        if (production_building and mineral >= self.WORKER_COST
                and worker_count < self.MAX_WORKERS):
            commands.append({
                "action": "train",
                "building_id": production_building.get(
                    "id", f"base_p{self.player_id}"),
                "unit_type": "worker",
                "issuer": self.player_id,
            })
            mineral -= self.WORKER_COST

        # ─── Rule 6: Train soldiers ─────────────────────────────
        if (completed_barracks and mineral >= self.SOLDIER_COST
                and worker_count >= 8
                and soldier_count < self.MAX_SOLDIERS):
            commands.append({
                "action": "train",
                "building_id": completed_barracks[0].get("id", "barracks_0"),
                "unit_type": "Marine",
                "issuer": self.player_id,
            })
            mineral -= self.SOLDIER_COST

        # ─── Rule 7: Train scouts (if enabled) ──────────────────
        if (self._scout_enabled and completed_barracks
                and mineral >= self.SCOUT_COST
                and worker_count >= 10):
            scout_count = len([e for _, e in my_stuff.items()
                               if e.get("entity_type") == "scout"])
            if scout_count < self.MAX_SCOUTS:
                commands.append({
                    "action": "train",
                    "building_id": completed_barracks[0].get("id", "barracks_0"),
                    "unit_type": "scout",
                    "issuer": self.player_id,
                })

        return {"commands": commands, "tick": tick}


def _dist(a: dict, b: dict) -> float:
    """Euclidean distance between two entities."""
    dx = a.get("pos_x", 0) - b.get("pos_x", 0)
    dy = a.get("pos_y", 0) - b.get("pos_y", 0)
    return math.sqrt(dx * dx + dy * dy)