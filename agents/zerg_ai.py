"""Zerg ScriptAI — early rush + swarm reinforcements.

Strategy:
- 9-pool speed: SpawningPool immediately, then Drones
- Mass Zerglings — overwhelm before enemy can mass
- 2nd Hatchery for extra Larva after first wave
- Hydralisk Den for ranged support mid-game
- Attack early (RALLY_SIZE=3), reinforce continuously
"""
from __future__ import annotations
from agents.race_ai_base import RaceAIBase


class ZergAI(RaceAIBase):
    """Rule-based Zerg AI — early rush + swarm."""

    NAME = "ZergAI"
    RACE = "zerg"

    BUILD_ORDER = [
        ("SpawningPool", 1),
        ("Hatchery", 2),
        ("HydraliskDen", 1),
        ("Extractor", 1),
    ]
    MAX_WORKERS = 16
    ATTACK_DELAY = 100
    RALLY_SIZE = 3
    TRAIN_BUILDINGS = {"base", "Hatchery", "Lair", "Hive"}

    def decide(self, observation: dict) -> dict:
        cat = self._categorize(observation)
        cmds: list[dict] = []
        tick = observation.get("tick", 0)
        mineral, gas, supply_used, supply_cap = self._get_resources(observation)
        has_pool = (self._count_building_type(cat, "SpawningPool") >= 1
                    or self._is_building_constructing(cat, "SpawningPool"))
        n_workers = self._count_workers(cat)

        # ── 1. Build (Pool IMMEDIATELY, then economy) ──
        idle_w = cat["idle_workers"]
        if idle_w and n_workers > 1:
            wid, w = idle_w[0]
            for btype, max_n in self.BUILD_ORDER:
                if self._count_building_type(cat, btype) >= max_n:
                    continue
                # Delay 2nd Hatch and HydraDen until we have economy
                if btype in ("Hatchery", "HydraliskDen") and n_workers < 8:
                    continue
                if btype == "Extractor" and n_workers < 10:
                    continue
                cost = {"SpawningPool": 200, "Hatchery": 300,
                        "HydraliskDen": 100, "Extractor": 50}.get(btype, 150)
                if mineral < cost:
                    continue
                bx = w.get("pos_x", 9.6) + self._count_building_type(cat, btype) * 3
                by = w.get("pos_y", 9.6) + 1
                cmds.append(self._cmd_build(wid, btype, bx, by))
                mineral -= cost
                break

        # ── 2. Gather ──
        build_wid = idle_w[0][0] if idle_w else None
        for wid, w in idle_w:
            if wid != build_wid:
                self._assign_workers_to_minerals(cmds, cat)

        # ── 3. Overlord at supply thresholds ──
        if supply_cap > 0 and supply_cap - supply_used <= 4 and mineral >= 100:
            bid = self._find_any_barracks(cat)
            if bid:
                cmds.append(self._cmd_train(bid, "Overlord"))

        # ── 4. Military — ALWAYS Zerglings if pool exists ──
        has_hydra = self._count_building_type(cat, "HydraliskDen") >= 1
        if has_pool:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt not in self.TRAIN_BUILDINGS:
                    continue
                if self._building_has_queue(cat, eid):
                    continue
                # Hydralisks for ranged support (need HydraDen + gas)
                if has_hydra and mineral >= 75 and gas >= 25:
                    cmds.append(self._cmd_train(eid, "Hydralisk"))
                    mineral -= 75
                    gas -= 25
                    continue
                if mineral >= 50:
                    cmds.append(self._cmd_train(eid, "Zergling"))
                    mineral -= 50

        # ── 5. Workers — Drones alongside military once pool is up ──
        if n_workers < self.MAX_WORKERS and mineral >= 50:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt in self.TRAIN_BUILDINGS and not self._building_has_queue(cat, eid):
                    cmds.append(self._cmd_train(eid, "Drone"))
                    mineral -= 50
                    break

        # ── 6. Attack — aggressive, small groups ──
        idle_combat = cat["idle_combat"]
        if len(idle_combat) >= self.RALLY_SIZE or tick > self.ATTACK_DELAY:
            self._push_toward_enemy_base(cmds, cat, tick)

        self._retreat_damaged_workers(cmds, cat)
        return {"commands": cmds}