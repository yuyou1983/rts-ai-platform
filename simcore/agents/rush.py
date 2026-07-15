"""Rush AI — trains military units and attacks enemy base once army reaches threshold."""
from __future__ import annotations

from simcore.agents.greedy import GreedyGatherer


class RushAI:
    """Trains military units and attacks the enemy base.

    Strategy:
      1. Gather with idle workers (delegates to GreedyGatherer)
      2. Build a barracks/gateway/spawning pool
      3. Train military units from that building
      4. When army ≥ attack_threshold, attack-move to enemy start location
         (uses initial spawn knowledge, not fog-dependent vision)
    """

    _MIL_BUILDING = {"terran": "Barracks", "zerg": "SpawningPool", "protoss": "Gateway"}
    _MIL_UNIT = {"terran": "Marine", "zerg": "Zergling", "protoss": "Zealot"}

    def __init__(self, player_id: int = 1, attack_threshold: int = 4):
        self.player_id = player_id
        self.attack_threshold = attack_threshold
        self._gatherer = GreedyGatherer(player_id)
        self._enemy_base_pos: tuple[float, float] | None = None

    def _find_enemy_base_pos(self, entities: dict, pid: int) -> tuple[float, float] | None:
        """Try to find enemy base from visible entities. Returns None if not in vision."""
        for eid, e in entities.items():
            if (e.get("owner", 0) not in (0, pid)
                    and e.get("entity_type") == "building"
                    and e.get("building_type") == "base"):
                return (e.get("pos_x", 0.0), e.get("pos_y", 0.0))
        return None

    def decide(self, obs: dict) -> list[dict]:
        cmds: list[dict] = []
        entities = obs.get("entities", {})
        resources = obs.get("resources", {})
        pid = self.player_id
        minerals = resources.get(f"p{pid}_mineral", 0)
        supply_used = resources.get(f"p{pid}_supply_used", 0)
        supply_cap = resources.get(f"p{pid}_supply_cap", 0)

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

        # Infer enemy base position: if we can see it, update. Otherwise use last known.
        visible_enemy_pos = self._find_enemy_base_pos(entities, pid)
        if visible_enemy_pos is not None:
            self._enemy_base_pos = visible_enemy_pos
        elif self._enemy_base_pos is None:
            # First tick: infer from map symmetry — enemy base is diagonally opposite
            if my_base is not None:
                # Default map is 64x64, enemy base at opposite corner
                map_w = obs.get("map_width", 64) or 64
                map_h = obs.get("map_height", 64) or 64
                bx = my_base.get("pos_x", 0.0)
                by = my_base.get("pos_y", 0.0)
                self._enemy_base_pos = (map_w - bx, map_h - by)

        mil_building = self._MIL_BUILDING.get(race, "Barracks")
        mil_unit = self._MIL_UNIT.get(race, "Marine")

        # Check if we have the military building (completed)
        has_mil_building = any(
            e.get("owner") == pid
            and e.get("entity_type") == "building"
            and e.get("unit_type", "").lower() == mil_building.lower()
            and not e.get("is_constructing", False)
            for e in entities.values()
        )

        # Build military building if missing — pick builder FIRST
        builder_id: str | None = None
        if not has_mil_building and minerals >= 150:
            workers = [
                (eid, e) for eid, e in entities.items()
                if e.get("owner") == pid and e.get("entity_type") == "worker"
            ]
            if workers and my_base:
                wid, w = workers[0]
                builder_id = wid
                bx = my_base.get("pos_x", 0) + 5
                by = my_base.get("pos_y", 0) + 5
                cmds.append({
                    "action": "build",
                    "issuer": pid,
                    "unit_id": wid,
                    "building_type": mil_building,
                    "target_x": bx,
                    "target_y": by,
                })

        # Reuse gather logic for workers, but filter out the builder
        gather_cmds = self._gatherer.decide(obs)
        if builder_id is not None:
            gather_cmds = [c for c in gather_cmds
                           if c.get("unit_id") != builder_id]

        # Train military units
        if has_mil_building and minerals >= 50 and supply_used < supply_cap:
            mil_bldg = None
            for eid, e in entities.items():
                if (e.get("owner") == pid
                    and e.get("entity_type") == "building"
                    and e.get("unit_type", "").lower() == mil_building.lower()
                    and not e.get("is_constructing", False)):
                    mil_bldg = e
                    break
            if mil_bldg:
                cmds.append({
                    "action": "train",
                    "issuer": pid,
                    "building_id": mil_bldg.get("id", ""),
                    "unit_type": mil_unit,
                })

        # Count military units (soldiers and scouts that we own)
        army = [
            (eid, e) for eid, e in entities.items()
            if e.get("owner") == pid
            and e.get("entity_type") in ("soldier", "scout")
        ]

        # Attack if army size ≥ threshold — keep issuing orders every tick
        if len(army) >= self.attack_threshold:
            target_pos = self._enemy_base_pos
            if target_pos is not None:
                for uid, u in army:
                    # Try targeted attack if enemy base visible
                    enemy_base_id = None
                    for eid, e in entities.items():
                        if (e.get("owner", 0) not in (0, pid)
                                and e.get("entity_type") == "building"
                                and e.get("building_type") == "base"):
                            enemy_base_id = eid
                            break
                    if enemy_base_id:
                        cmds.append({
                            "action": "attack",
                            "issuer": pid,
                            "attacker_id": uid,
                            "unit_id": uid,
                            "target_id": enemy_base_id,
                        })
                    else:
                        # Move toward enemy base (will attack once in vision)
                        cmds.append({
                            "action": "move",
                            "issuer": pid,
                            "unit_id": uid,
                            "target_x": target_pos[0],
                            "target_y": target_pos[1],
                        })

        return gather_cmds + cmds
