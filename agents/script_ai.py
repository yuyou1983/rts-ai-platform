"""Baseline scripted AI — deterministic rule-based opponent for RL training.

Implements AgentInterface protocol: decide(obs) → cmd dict.

Heuristic priority (per tick):
1. If idle workers → assign to nearest mineral patch
2. If idle military → attack nearest enemy
3. If mineral >= 100 and no barracks → build barracks
4. If mineral >= 50 and barracks exists → train worker (up to 12)
5. If mineral >= 100 and workers >= 8 → train soldier
6. If base under attack → pull workers back
"""
from __future__ import annotations

import math


class ScriptAI:
    """Rule-based RTS AI. No LLM, no learning — pure heuristics.

    Usage:
        ai = ScriptAI(player_id=1)
        cmd = ai.decide(observation_dict)
    """

    MAX_WORKERS = 12
    MAX_SOLDIERS = 20
    BARRACKS_COST = 100
    WORKER_COST = 50
    SOLDIER_COST = 100

    def __init__(self, player_id: int = 1) -> None:
        self.player_id = player_id
        self._barracks_built = False

    def decide(self, obs: dict) -> dict:
        """Generate commands from observation using heuristic rules.

        Args:
            obs: Observation dict from GameState.get_observations().

        Returns:
            Command dict with 'commands' list and 'tick'.
        """
        commands: list[dict] = []
        tick = obs.get("tick", 0)
        entities = obs.get("entities", {})
        my_stuff = {k: v for k, v in entities.items() if v.get("owner") == self.player_id}

        # Categorize entities
        idle_workers = []
        idle_military = []
        my_buildings = {}
        my_base = None
        enemies = []

        for eid, e in entities.items():
            owner = e.get("owner")
            etype = e.get("entity_type", "")
            idle = e.get("is_idle", True)

            if owner == self.player_id:
                if etype == "worker" and idle:
                    idle_workers.append((eid, e))
                elif etype in ("soldier", "scout") and idle:
                    idle_military.append((eid, e))
                elif etype == "building":
                    my_buildings[eid] = e
                    if e.get("building_type") == "base":
                        my_base = e
            elif owner != 0 and e.get("health", 0) > 0:
                enemies.append((eid, e))

        # Resources
        mineral_key = f"p{self.player_id}_mineral"
        resources = obs.get("resources", {})
        mineral = resources.get(mineral_key, 0) if isinstance(resources, dict) else 0
        worker_count = len([e for _, e in my_stuff.items() if e.get("entity_type") == "worker"])

        # ─── Rule 1: Idle workers → gather nearest mineral ─────────
        mineral_patches = [(eid, e) for eid, e in entities.items()
                          if e.get("entity_type") == "resource"
                          and e.get("resource_type") == "mineral"
                          and e.get("resource_amount", 0) > 0]

        for wid, worker in idle_workers:
            if not mineral_patches:
                break
            # Find nearest mineral
            best_patch = None
            best_dist = float("inf")
            for pid, patch in mineral_patches:
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

        # ─── Rule 2: Idle military → attack nearest enemy ──────────
        for uid, unit in idle_military:
            if not enemies:
                # No enemies visible → move toward center
                commands.append({
                    "action": "move",
                    "unit_id": uid,
                    "target_x": 32.0,
                    "target_y": 32.0,
                    "issuer": self.player_id,
                })
                continue

            best_enemy = None
            best_dist = float("inf")
            for eid, enemy in enemies:
                d = _dist(unit, enemy)
                if d < best_dist:
                    best_dist = d
                    best_enemy = (eid, enemy)

            if best_enemy:
                eid, enemy = best_enemy
                commands.append({
                    "action": "attack",
                    "attacker_id": uid,
                    "target_id": eid,
                    "issuer": self.player_id,
                })

        # ─── Rule 3: Build barracks if affordable and none exist ───
        has_barracks = any(b.get("building_type") == "barracks" for b in my_buildings.values())
        if not has_barracks and mineral >= self.BARRACKS_COST and idle_workers:
            wid, worker = idle_workers[0]
            commands.append({
                "action": "build",
                "builder_id": wid,
                "building_type": "barracks",
                "pos_x": worker.get("pos_x", 10) + 3,
                "pos_y": worker.get("pos_y", 10),
                "issuer": self.player_id,
            })
            mineral -= self.BARRACKS_COST

        # ─── Rule 4: Train workers if affordable and under cap ─────
        barracks = [b for b in my_buildings.values() if b.get("building_type") == "barracks"]
        base = my_base
        production_building = base or (barracks[0] if barracks else None)

        if production_building and mineral >= self.WORKER_COST and worker_count < self.MAX_WORKERS:
            commands.append({
                "action": "train",
                "building_id": production_building.get("id", "base_p1"),
                "unit_type": "worker",
                "issuer": self.player_id,
            })
            mineral -= self.WORKER_COST

        # ─── Rule 5: Train soldiers if workers sufficient ───────────
        if (barracks and mineral >= self.SOLDIER_COST
                and worker_count >= 8
                and production_building):
            soldier_count = len([e for _, e in my_stuff.items()
                               if e.get("entity_type") == "soldier"])
            if soldier_count < self.MAX_SOLDIERS:
                commands.append({
                    "action": "train",
                    "building_id": barracks[0].get("id", "barracks_0"),
                    "unit_type": "soldier",
                    "issuer": self.player_id,
                })

        return {"commands": commands, "tick": tick}


def _dist(a: dict, b: dict) -> float:
    """Euclidean distance between two entities."""
    dx = a.get("pos_x", 0) - b.get("pos_x", 0)
    dy = a.get("pos_y", 0) - b.get("pos_y", 0)
    return math.sqrt(dx * dx + dy * dy)
