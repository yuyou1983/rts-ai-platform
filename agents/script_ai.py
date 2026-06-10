"""Enhanced scripted AI — rule-based RTS opponent with difficulty balancing and 3-race support.

Difficulty levels:
  easy:   slow reaction, no micro, limited production
  medium: moderate reaction, basic micro
  hard:   fast reaction, focus fire, retreat

Race support:
  Terran: CommandCenter→SCV, Barracks→Marine, Factory→Vulture
  Zerg:   Hatchery→Drone/Zergling/Hydralisk (via base simplified train)
  Protoss: Nexus→Probe, Gateway→Zealot/Dragoon (needs Pylon for supply)

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
    """Tactical rule-based RTS AI with difficulty settings and 3-race support."""

    # ─── Production caps per difficulty ─────────────────────────
    _DIFFICULTY_PRESETS = {
        "easy": {
            "max_workers": 8,
            "max_soldiers": 8,
            "max_scouts": 0,
            "rally_size": 6,
            "tick_delay": 5,
            "reaction_delay": 15,
            "micro_enabled": False,
            "scout_enabled": False,
            "build_barracks_tick": 300,
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

    # ─── Race-specific SC1 names ────────────────────────────────
    _RACE_BASE = {"terran": "CommandCenter", "zerg": "Hatchery", "protoss": "Nexus"}
    _RACE_BARRACKS = {"terran": "Barracks", "zerg": "SpawningPool", "protoss": "Gateway"}
    _RACE_SUPPLY = {"terran": "SupplyDepot", "zerg": "Overlord", "protoss": "Pylon"}
    _RACE_WORKER = {"terran": "SCV", "zerg": "Drone", "protoss": "Probe"}
    _RACE_SOLDIER = {"terran": "Marine", "zerg": "Zergling", "protoss": "Zealot"}
    _RACE_SCOUT = {"terran": "Ghost", "zerg": "Hydralisk", "protoss": "Dragoon"}

    # Reverse map: SC1 building name → race
    _BUILDING_RACE: dict[str, str] = {
        "CommandCenter": "terran", "SupplyDepot": "terran", "Refinery": "terran",
        "Barracks": "terran", "Factory": "terran", "Starport": "terran",
        "Hatchery": "zerg", "Lair": "zerg", "Hive": "zerg",
        "Extractor": "zerg", "SpawningPool": "zerg", "HydraliskDen": "zerg",
        "Nexus": "protoss", "Pylon": "protoss", "Assimilator": "protoss",
        "Gateway": "protoss",
    }

    def __init__(self, player_id: int = 2, difficulty: str = "medium",
                 race: str | None = None) -> None:
        self.player_id = player_id
        self.difficulty = difficulty
        self._forced_race = race

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

        # Build costs
        self.BARRACKS_COST = 150
        self.SUPPLY_COST = 100
        self.WORKER_COST = 50
        self.SOLDIER_COST = 100
        self.SCOUT_COST = 75

        # Internal state
        self._rally_point: tuple[float, float] | None = None
        self._attack_issued = False
        self._last_decision_tick = -999
        self._threat_detected_tick = -999
        self._detected_race: str | None = None
        self._supply_built = False

    def _detect_race(self, entities: dict[str, dict]) -> str:
        """Detect own race from buildings."""
        if self._forced_race:
            return self._forced_race
        if self._detected_race:
            return self._detected_race
        for eid, e in entities.items():
            if e.get("owner") == self.player_id and e.get("entity_type") == "building":
                ut = e.get("unit_type", "")
                if ut in self._BUILDING_RACE:
                    self._detected_race = self._BUILDING_RACE[ut]
                    return self._detected_race
        self._detected_race = "terran"
        return "terran"

    def decide(self, obs: dict) -> dict:
        """Generate commands from observation using heuristic rules."""
        commands: list[dict] = []
        tick = obs.get("tick", 0)
        entities = obs.get("entities", {})

        if tick - self._last_decision_tick < self._tick_delay:
            return {"commands": [], "tick": tick}
        self._last_decision_tick = tick

        race = self._detect_race(entities)

        base_name = self._RACE_BASE[race]
        barracks_name = self._RACE_BARRACKS[race]
        supply_name = self._RACE_SUPPLY[race]
        worker_name = self._RACE_WORKER[race]
        soldier_name = self._RACE_SOLDIER[race]
        scout_name = self._RACE_SCOUT[race]

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

        # Find base
        for eid, e in entities.items():
            if e.get("owner") == self.player_id and e.get("entity_type") == "building":
                bt = e.get("building_type", "")
                ut = e.get("unit_type", "")
                if bt == "base" or ut == base_name or ut in ("CommandCenter", "Hatchery", "Nexus"):
                    my_base = e
                    break

        # Categorize
        all_workers: list[tuple[str, dict]] = []
        for eid, e in entities.items():
            owner = e.get("owner", 0)
            etype = e.get("entity_type", "")
            idle = e.get("is_idle", True)

            if owner == self.player_id:
                if etype == "worker":
                    all_workers.append((eid, e))
                    if idle and not e.get("returning_to_base"):
                        if self._micro_enabled:
                            hf = e.get("health", 0) / max(e.get("max_health", 1), 1)
                            if hf < 0.3 and my_base:
                                commands.append({
                                    "action": "move", "unit_id": eid,
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

        # ─── Pre-compute building status (needed for worker reservation) ──
        supply_count = sum(1 for b in my_buildings.values()
                          if b.get("unit_type", "").lower() == supply_name.lower()
                          or b.get("building_type", "").lower() in ("supply_depot", "pylon"))
        has_supply = any(
            (b.get("unit_type", "").lower() == supply_name.lower()
             or b.get("building_type", "").lower() in ("supply_depot", "pylon"))
            and not b.get("is_constructing", False)
            for b in my_buildings.values()
        )
        # Consider supply "met" if at least 1 is complete OR 2 are building
        supply_satisfied = has_supply or supply_count >= 2
        # Limit supply buildings based on army size
        max_supply_buildings = max(3, worker_count // 8 + soldier_count // 6)
        has_barracks = any(
            (b.get("building_type", "").lower() == "barracks"
             or b.get("unit_type", "").lower() == barracks_name.lower())
            and not b.get("is_constructing", False)
            for b in my_buildings.values()
        )
        barracks_building = any(
            (b.get("building_type", "").lower() == "barracks"
             or b.get("unit_type", "").lower() == barracks_name.lower())
            and b.get("is_constructing", False)
            for b in my_buildings.values()
        )

        # Protoss needs Pylon before Gateway
        can_build_barracks = True
        if race == "protoss":
            can_build_barracks = supply_satisfied

        # ─── Rule 1: Idle workers → gather (but keep 1 for building if needed) ─
        mineral_patches = [(eid, e) for eid, e in entities.items()
                           if e.get("entity_type") == "resource"
                           and e.get("resource_type") == "mineral"
                           and e.get("resource_amount", 0) > 0]
        gas_patches = [(eid, e) for eid, e in entities.items()
                       if e.get("entity_type") == "resource"
                       and e.get("resource_type") == "gas"
                       and e.get("resource_amount", 0) > 0]

        # Reserve one worker for building if we need supply or barracks
        need_supply = not supply_satisfied and supply_count < max_supply_buildings and mineral >= self.SUPPLY_COST and tick >= 50
        need_barracks = (not has_barracks and not barracks_building
                         and can_build_barracks
                         and tick >= self._build_barracks_tick
                         and mineral >= self.BARRACKS_COST)
        reserve_worker = int(need_supply or need_barracks)

        workers_to_send = idle_workers[reserve_worker:]

        for wid, worker in workers_to_send:
            if not mineral_patches:
                break
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
                    "action": "gather", "worker_id": wid,
                    "resource_id": pid, "issuer": self.player_id,
                })

        # ─── Rule 2: Combat ─────────────────────────────────────
        enemy_base_x, enemy_base_y = 54.0, 54.0
        if self.player_id == 1:
            enemy_base_x, enemy_base_y = 54.0, 54.0
        else:
            enemy_base_x, enemy_base_y = 10.0, 10.0

        # Find actual enemy base
        for eid, e in enemies:
            if e.get("entity_type") == "building" and (
                e.get("building_type") == "base" or
                e.get("unit_type") in ("CommandCenter", "Hatchery", "Nexus")
            ):
                enemy_base_x = e.get("pos_x", enemy_base_x)
                enemy_base_y = e.get("pos_y", enemy_base_y)
                break

        all_combat = idle_soldiers + idle_scouts

        if all_combat and enemies:
            target_eid, target_e = min(
                enemies,
                key=lambda x: x[1].get("health", 100)
                               / max(x[1].get("max_health", 100), 1)
            )

            base_threat = False
            if my_base:
                base_threat = any(_dist(my_base, e) < 10 for _, e in enemies)
            if base_threat and tick - self._threat_detected_tick < self._reaction_delay:
                base_threat = False
            elif base_threat:
                self._threat_detected_tick = tick

            should_attack = (
                len(all_combat) >= self.RALLY_SIZE
                or base_threat
                or tick > 600
            )

            if should_attack:
                for uid, _ in all_combat:
                    commands.append({
                        "action": "attack", "attacker_id": uid,
                        "target_id": target_eid, "issuer": self.player_id,
                    })
        elif all_combat and tick > 600:
            # Push toward enemy base even without enemies visible
            for uid, _ in all_combat:
                commands.append({
                    "action": "move", "unit_id": uid,
                    "target_x": enemy_base_x,
                    "target_y": enemy_base_y,
                    "issuer": self.player_id,
                })

        # ─── Rule 3: Scouts patrol ──────────────────────────────
        if self._scout_enabled:
            for sid, scout in idle_scouts:
                enemy_quadrant = 0.85 if self.player_id == 1 else 0.15
                map_size = obs.get("map_width", 64)
                tx = map_size * enemy_quadrant
                ty = map_size * enemy_quadrant
                commands.append({
                    "action": "move", "unit_id": sid,
                    "target_x": tx, "target_y": ty,
                    "issuer": self.player_id,
                })

        # ─── Rule 4: Build supply (Protoss Pylon, Terran SupplyDepot, Zerg Overlord) ─
        # supply_satisfied / supply_count / max_supply_buildings already computed above
        # Zerg trains Overlord from Hatchery (not built), so skip for Zerg
        if (race != "zerg" and not supply_satisfied
                and supply_count < max_supply_buildings
                and mineral >= self.SUPPLY_COST and tick >= 50):
            builder = self._pick_builder(idle_workers, all_workers, my_base)
            if builder:
                wid, worker = builder
                bx = (my_base or worker).get("pos_x", 10) + 4
                by = (my_base or worker).get("pos_y", 10) + 1
                commands.append({
                    "action": "build", "builder_id": wid,
                    "building_type": supply_name,
                    "pos_x": bx, "pos_y": by,
                    "issuer": self.player_id,
                })
                mineral -= self.SUPPLY_COST

        # ─── Rule 5: Build barracks (race-aware, needs supply for Protoss) ─
        # has_barracks / barracks_building / can_build_barracks already computed above
        if (not has_barracks and not barracks_building
                and can_build_barracks
                and tick >= self._build_barracks_tick
                and mineral >= self.BARRACKS_COST):
            builder = self._pick_builder(idle_workers, all_workers, my_base)
            if builder:
                wid, worker = builder
                bx = (my_base or worker).get("pos_x", 10) + 3
                by = (my_base or worker).get("pos_y", 10)
                commands.append({
                    "action": "build", "builder_id": wid,
                    "building_type": barracks_name,
                    "pos_x": bx, "pos_y": by,
                    "issuer": self.player_id,
                })
                mineral -= self.BARRACKS_COST

        # ─── Rule 6: Train workers (from base) ──────────────────
        base_building = None
        for b in my_buildings.values():
            bt = b.get("building_type", "")
            ut = b.get("unit_type", "")
            if bt.lower() == "base" or ut.lower() == base_name.lower() or ut in ("CommandCenter", "Hatchery", "Nexus"):
                base_building = b
                break

        completed_barracks = [b for b in my_buildings.values()
                              if (b.get("building_type", "").lower() == "barracks"
                                  or b.get("building_type", "").lower() == barracks_name.lower()
                                  or b.get("unit_type", "").lower() == barracks_name.lower())
                              and not b.get("is_constructing")]

        production_building = base_building or (completed_barracks[0]
                                                if completed_barracks else None)

        if (production_building and mineral >= self.WORKER_COST
                and worker_count < self.MAX_WORKERS):
            commands.append({
                "action": "train",
                "building_id": production_building.get("id", f"base_p{self.player_id}"),
                "unit_type": worker_name,
                "issuer": self.player_id,
            })
            mineral -= self.WORKER_COST

        # ─── Rule 7: Train soldiers (race-aware) ────────────────
        # Zerg: train from Hatchery (base) directly; Terran/Protoss: from barracks
        train_building = None
        if race == "zerg":
            train_building = base_building
        else:
            train_building = completed_barracks[0] if completed_barracks else None

        if (train_building and mineral >= self.SOLDIER_COST
                and worker_count >= 6
                and soldier_count < self.MAX_SOLDIERS):
            commands.append({
                "action": "train",
                "building_id": train_building.get("id", f"base_p{self.player_id}"),
                "unit_type": soldier_name,
                "issuer": self.player_id,
            })
            mineral -= self.SOLDIER_COST

        # ─── Rule 8: Train scouts (race-aware) ───────────────────
        if (self._scout_enabled and train_building
                and mineral >= self.SCOUT_COST
                and worker_count >= 8):
            scout_count = len([e for _, e in my_stuff.items()
                               if e.get("entity_type") == "scout"])
            if scout_count < self.MAX_SCOUTS:
                commands.append({
                    "action": "train",
                    "building_id": train_building.get("id", f"base_p{self.player_id}"),
                    "unit_type": scout_name,
                    "issuer": self.player_id,
                })

        # ─── Rule 9: Zerg — train Overlord for supply ───────────
        if (race == "zerg" and base_building and mineral >= 100
                and tick > 200
                and not self._supply_built):
            # Train Overlord from Hatchery
            commands.append({
                "action": "train",
                "building_id": base_building.get("id", f"base_p{self.player_id}"),
                "unit_type": "Overlord",
                "issuer": self.player_id,
            })
            self._supply_built = True  # Train one for now

        return {"commands": commands, "tick": tick}

    @staticmethod
    def _pick_builder(
        idle_workers: list[tuple[str, dict]],
        all_workers: list[tuple[str, dict]],
        base: dict | None,
    ) -> tuple[str, dict] | None:
        """Pick a builder: prefer idle worker, else closest worker to base."""
        if idle_workers:
            return idle_workers[0]
        if not all_workers or base is None:
            return all_workers[0] if all_workers else None
        # Pick worker closest to base
        return min(all_workers, key=lambda w: _dist(w[1], base))


def _dist(a: dict, b: dict) -> float:
    """Euclidean distance between two entities."""
    dx = a.get("pos_x", 0) - b.get("pos_x", 0)
    dy = a.get("pos_y", 0) - b.get("pos_y", 0)
    return math.sqrt(dx * dx + dy * dy)
