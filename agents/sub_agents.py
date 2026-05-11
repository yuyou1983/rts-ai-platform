"""Economy Agent — manages workers, building, and resource collection.

Responsibilities:
- Assign idle workers to nearest mineral/gas patch
- Build barracks when affordable
- Train workers up to cap
- Re-assign workers after deposit
"""
from __future__ import annotations

import math
from typing import Any


class EconomyAgent:
    """Pure-economy decision maker. Takes budget-limited observation, returns economy commands."""

    MAX_WORKERS = 14
    BARRACKS_COST = 100
    WORKER_COST = 50

    def __init__(self, player_id: int = 1) -> None:
        self.player_id = player_id

    def decide(self, obs: dict) -> list[dict]:
        """Generate economy commands from observation."""
        commands: list[dict] = []
        entities = obs.get("entities", {})
        budget = obs.get("budget", {})
        mineral_budget = budget.get("mineral", float("inf"))
        gas_budget = budget.get("gas", float("inf"))

        # Find my base
        my_base = None
        idle_workers: list[tuple[str, dict]] = []
        my_workers: list[dict] = []
        my_buildings: dict[str, dict] = {}

        for eid, e in entities.items():
            if e.get("owner") != self.player_id:
                continue
            if e.get("entity_type") == "building" and e.get("building_type") == "base":
                my_base = e
                my_buildings[eid] = e
            elif e.get("entity_type") == "building":
                my_buildings[eid] = e
            elif e.get("entity_type") == "worker":
                my_workers.append(e)
                if e.get("is_idle", True) and not e.get("returning_to_base"):
                    idle_workers.append((eid, e))

        worker_count = len(my_workers)

        # Resource patches
        mineral_patches = [(eid, e) for eid, e in entities.items()
                           if e.get("entity_type") == "resource"
                           and e.get("resource_type") == "mineral"
                           and e.get("resource_amount", 0) > 0]
        gas_patches = [(eid, e) for eid, e in entities.items()
                       if e.get("entity_type") == "resource"
                       and e.get("resource_type") == "gas"
                       and e.get("resource_amount", 0) > 0]

        # Assign idle workers to nearest resource
        for wid, worker in idle_workers:
            if not mineral_patches:
                break
            # Prefer gas if we have enough miners on minerals
            gas_miners = sum(1 for w in my_workers
                           if not w.get("is_idle", True) and w.get("carry_amount", 0) > 0
                           and entities.get(w.get("attack_target_id", ""), {}).get("resource_type") == "gas")
            patches = gas_patches if (worker_count > 8 and gas_patches and gas_miners < 2) else mineral_patches

            best_patch = None
            best_dist = float("inf")
            for pid, patch in patches:
                d = _dist(worker, patch)
                if d < best_dist:
                    best_dist = d
                    best_patch = (pid, patch)

            if best_patch:
                pid, _ = best_patch
                commands.append({
                    "action": "gather",
                    "worker_id": wid,
                    "resource_id": pid,
                    "issuer": self.player_id,
                })

        # Build barracks if none
        has_barracks = any(b.get("building_type") == "barracks" and not b.get("is_constructing", False)
                         for b in my_buildings.values())
        barracks_building = any(b.get("building_type") == "barracks" and b.get("is_constructing", False)
                              for b in my_buildings.values())

        if not has_barracks and not barracks_building and mineral_budget >= self.BARRACKS_COST and idle_workers:
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
            mineral_budget -= self.BARRACKS_COST

        # Train workers (skip if we still need to build barracks)
        completed_barracks = [b for b in my_buildings.values()
                              if b.get("building_type") == "barracks" and not b.get("is_constructing")]
        need_barracks = not has_barracks and not barracks_building
        production_building = my_base or (completed_barracks[0] if completed_barracks else None)

        if not need_barracks and production_building and mineral_budget >= self.WORKER_COST and worker_count < self.MAX_WORKERS:
            commands.append({
                "action": "train",
                "building_id": production_building.get("id", f"base_p{self.player_id}"),
                "unit_type": "worker",
                "issuer": self.player_id,
            })
            mineral_budget -= self.WORKER_COST

        return commands


class CombatAgent:
    """Pure-combat decision maker. Takes budget-limited observation, returns combat commands."""

    RALLY_SIZE = 2
    SOLDIER_COST = 100
    SCOUT_COST = 75
    MAX_SOLDIERS = 20
    MAX_SCOUTS = 4

    def __init__(self, player_id: int = 1) -> None:
        self.player_id = player_id

    def decide(self, obs: dict) -> list[dict]:
        """Generate combat commands from observation."""
        commands: list[dict] = []
        entities = obs.get("entities", {})
        budget = obs.get("budget", {})
        mineral_budget = budget.get("mineral", float("inf"))

        idle_soldiers: list[tuple[str, dict]] = []
        idle_scouts: list[tuple[str, dict]] = []
        enemies: list[tuple[str, dict]] = []
        my_buildings: dict[str, dict] = {}
        my_base: dict | None = None

        for eid, e in entities.items():
            owner = e.get("owner", 0)
            if owner == self.player_id:
                if e.get("entity_type") == "soldier" and e.get("is_idle", True):
                    idle_soldiers.append((eid, e))
                elif e.get("entity_type") == "scout" and e.get("is_idle", True):
                    idle_scouts.append((eid, e))
                elif e.get("entity_type") == "building":
                    my_buildings[eid] = e
                    if e.get("building_type") == "base":
                        my_base = e
            elif owner != 0 and e.get("health", 0) > 0:
                enemies.append((eid, e))

        soldier_count = sum(1 for e in entities.values()
                          if e.get("owner") == self.player_id and e.get("entity_type") == "soldier")
        scout_count = sum(1 for e in entities.values()
                        if e.get("owner") == self.player_id and e.get("entity_type") == "scout")

        # Focus fire on weakest enemy
        if idle_soldiers and enemies:
            target_eid, target_e = min(
                enemies,
                key=lambda x: x[1].get("health", 100) / max(x[1].get("max_health", 100), 1)
            )
            base_threat = any(
                _dist(my_base or {"pos_x": 0, "pos_y": 0}, e) < 10
                for _, e in enemies
            ) if my_base else False

            if len(idle_soldiers) >= self.RALLY_SIZE or base_threat or len(idle_soldiers) >= len(enemies):
                for uid, _ in idle_soldiers:
                    commands.append({
                        "action": "attack",
                        "attacker_id": uid,
                        "target_id": target_eid,
                        "issuer": self.player_id,
                    })

        # Scout patrol
        for sid, scout in idle_scouts:
            enemy_quadrant = 0.85 if self.player_id == 1 else 0.15
            commands.append({
                "action": "move",
                "unit_id": sid,
                "target_x": 64 * enemy_quadrant,
                "target_y": 64 * enemy_quadrant,
                "issuer": self.player_id,
            })

        # Train soldiers
        completed_barracks = [b for b in my_buildings.values()
                              if b.get("building_type") == "barracks" and not b.get("is_constructing")]
        if completed_barracks and mineral_budget >= self.SOLDIER_COST:
            if soldier_count < self.MAX_SOLDIERS:
                commands.append({
                    "action": "train",
                    "building_id": completed_barracks[0].get("id", "barracks_0"),
                    "unit_type": "soldier",
                    "issuer": self.player_id,
                })
                mineral_budget -= self.SOLDIER_COST

        # Train scouts
        if completed_barracks and mineral_budget >= self.SCOUT_COST:
            if scout_count < self.MAX_SCOUTS:
                commands.append({
                    "action": "train",
                    "building_id": completed_barracks[0].get("id", "barracks_0"),
                    "unit_type": "scout",
                    "issuer": self.player_id,
                })

        return commands


class ScoutAgent:
    """Smart scout agent — patrols unexplored areas based on fog coverage."""

    PATROL_POINTS = 8  # number of patrol waypoints around the map
    RETREAT_HEALTH_FRAC = 0.4

    def __init__(self, player_id: int = 1) -> None:
        self.player_id = player_id
        self._patrol_index: dict[str, int] = {}  # per-scout patrol cycle

    def decide(self, obs: dict) -> list[dict]:
        entities = obs.get("entities", {})
        fog = obs.get("fog_of_war", {})
        commands: list[dict] = []
        map_size = 64.0

        # Generate patrol waypoints in unexplored areas
        waypoints = self._unexplored_waypoints(fog, map_size)

        for eid, e in entities.items():
            if e.get("owner") != self.player_id:
                continue
            if e.get("entity_type") != "scout":
                continue

            # Retreat if damaged
            health_frac = e.get("health", 0) / max(e.get("max_health", 1), 1)
            if health_frac < self.RETREAT_HEALTH_FRAC and e.get("is_idle", True):
                base = self._find_my_base(entities)
                if base:
                    commands.append({
                        "action": "move",
                        "unit_id": eid,
                        "target_x": base.get("pos_x", 10),
                        "target_y": base.get("pos_y", 10),
                        "issuer": self.player_id,
                    })
                continue

            if not e.get("is_idle", True):
                continue

            # Pick next unexplored waypoint
            idx = self._patrol_index.get(eid, 0)
            if waypoints:
                wp = waypoints[idx % len(waypoints)]
                commands.append({
                    "action": "move",
                    "unit_id": eid,
                    "target_x": wp[0],
                    "target_y": wp[1],
                    "issuer": self.player_id,
                })
                self._patrol_index[eid] = idx + 1

        return commands

    def _unexplored_waypoints(self, fog: dict, map_size: float) -> list[tuple[float, float]]:
        """Generate waypoints in unexplored fog regions."""
        pf = fog if "tiles" in fog else fog.get(str(self.player_id), {})
        tiles = pf.get("tiles", [])
        fw = pf.get("width", 16)
        fh = pf.get("height", 16)
        if not tiles or fw == 0 or fh == 0:
            # Fallback: default patrol points
            return [(map_size * f, map_size * f)
                    for f in [0.25, 0.5, 0.75, 0.85]]

        # Find clusters of unexplored tiles and generate waypoints
        unexplored: list[tuple[int, int]] = []
        step = max(1, fw // 8)  # sample every few tiles
        for gy in range(0, fh, step):
            for gx in range(0, fw, step):
                idx = gy * fw + gx
                if idx < len(tiles) and tiles[idx] == 0:
                    unexplored.append((gx, gy))

        if not unexplored:
            # All explored — patrol enemy quadrant
            eq = 0.85 if self.player_id == 1 else 0.15
            return [(map_size * eq, map_size * eq)]

        # Convert fog-grid coords to world coords and pick up to 8
        waypoints: list[tuple[float, float]] = []
        for gx, gy in unexplored[:self.PATROL_POINTS]:
            wx = (gx + 0.5) / fw * map_size
            wy = (gy + 0.5) / fh * map_size
            waypoints.append((wx, wy))
        return waypoints

    def _find_my_base(self, entities: dict) -> dict | None:
        for eid, e in entities.items():
            if (e.get("owner") == self.player_id
                    and e.get("entity_type") == "building"
                    and e.get("building_type") == "base"
                    and e.get("health", 0) > 0):
                return e
        return None


def _dist(a: dict, b: dict) -> float:
    dx = a.get("pos_x", 0) - b.get("pos_x", 0)
    dy = a.get("pos_y", 0) - b.get("pos_y", 0)
    return math.sqrt(dx * dx + dy * dy)