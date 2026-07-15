"""Greedy Gatherer AI — all workers gather, builds supply when blocked, trains workers up to 10."""
from __future__ import annotations


class GreedyGatherer:
    """Sends all idle workers to the nearest mineral patch.
    Builds supply depots/overlords/pylons when supply blocked.
    Trains workers up to 10 if affordable.

    Strategy:
      1. Find idle workers → send to nearest mineral
      2. If supply cap ≤ supply used → build supply building
      3. If workers < 10 and minerals ≥ 50 → train worker from base
    """

    def __init__(self, player_id: int = 1):
        self.player_id = player_id
        self._supply_building = {
            "terran": "SupplyDepot",
            "zerg": "Overlord",
            "protoss": "Pylon",
        }
        self._worker_name = {
            "terran": "SCV",
            "zerg": "Drone",
            "protoss": "Probe",
        }

    def decide(self, obs: dict) -> list[dict]:
        cmds: list[dict] = []
        entities = obs.get("entities", {})
        resources = obs.get("resources", {})
        pid = self.player_id
        minerals = resources.get(f"p{pid}_mineral", 0)

        # Determine race from base
        race = "terran"
        my_base = None
        for e in entities.values():
            if (e.get("owner") == pid
                    and e.get("entity_type") == "building"
                    and e.get("building_type") == "base"):
                my_base = e
                ut = e.get("unit_type", "CommandCenter")
                if "Hatchery" in ut or "Lair" in ut or "Hive" in ut:
                    race = "zerg"
                elif "Nexus" in ut:
                    race = "protoss"
                break

        # Supply check
        supply_used = resources.get(f"p{pid}_supply_used", 0)
        supply_cap = resources.get(f"p{pid}_supply_cap", 0)

        # 1. Idle workers → gather nearest mineral
        mineral_patches = [
            (eid, e) for eid, e in entities.items()
            if e.get("entity_type") == "resource"
            and e.get("resource_type") == "mineral"
            and e.get("resource_amount", 0) > 0
        ]
        idle_workers = [
            (eid, e) for eid, e in entities.items()
            if e.get("owner") == pid
            and e.get("entity_type") == "worker"
            and e.get("is_idle", True)
        ]

        for wid, w in idle_workers:
            if not mineral_patches:
                break
            best_mid = min(
                mineral_patches,
                key=lambda m: abs(m[1].get("pos_x", 0) - w.get("pos_x", 0))
                             + abs(m[1].get("pos_y", 0) - w.get("pos_y", 0))
            )[0]
            cmds.append({
                "action": "gather",
                "issuer": pid,
                "unit_id": wid,
                "resource_id": best_mid,
            })

        # Track which worker IDs already have commands this tick
        assigned_ids = {c["unit_id"] for c in cmds if "unit_id" in c}

        # 2. Supply blocked → build supply
        if supply_cap > 0 and supply_used >= supply_cap - 1 and minerals >= 100:
            supply_type = self._supply_building.get(race, "SupplyDepot")
            if race in ("terran", "protoss"):
                workers = [
                    (eid, e) for eid, e in entities.items()
                    if e.get("owner") == pid and e.get("entity_type") == "worker"
                ]
                if workers:
                    # Pick the first worker that does NOT already have a command
                    builder = None
                    for wid, w in workers:
                        if wid not in assigned_ids:
                            builder = (wid, w)
                            break
                    # If all workers are assigned, override one worker's gather with build
                    if builder is None:
                        builder = workers[0]
                        cmds = [c for c in cmds
                                if c.get("unit_id") != builder[0]]
                    wid, w = builder
                    assigned_ids.add(wid)
                    bx = w.get("pos_x", 0) + 3
                    by = w.get("pos_y", 0) + 3
                    cmds.append({
                        "action": "build",
                        "issuer": pid,
                        "unit_id": wid,
                        "building_type": supply_type,
                        "target_x": bx,
                        "target_y": by,
                    })
            elif race == "zerg":
                if my_base:
                    cmds.append({
                        "action": "train",
                        "issuer": pid,
                        "building_id": my_base.get("id", ""),
                        "unit_type": "Overlord",
                    })

        # 3. Train workers if needed (up to 10)
        worker_count = len([
            e for e in entities.values()
            if e.get("owner") == pid and e.get("entity_type") == "worker"
        ])
        if worker_count < 10 and minerals >= 50 and supply_used < supply_cap:
            if my_base:
                worker_name = self._worker_name.get(race, "SCV")
                cmds.append({
                    "action": "train",
                    "issuer": pid,
                    "building_id": my_base.get("id", ""),
                    "unit_type": worker_name,
                })

        return cmds
