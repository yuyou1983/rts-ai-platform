"""Zerg ScriptAI — rule-based Zerg opponent.

Strategy:
- SpawningPool first, then mass Zerglings
- Drone only until pool is up
- Overlord at supply thresholds
- Attack with rally groups toward enemy base
"""
from __future__ import annotations
from agents.race_ai_base import RaceAIBase


class ZergAI(RaceAIBase):
    """Rule-based Zerg AI — rush-oriented."""

    NAME = "ZergAI"
    RACE = "zerg"

    BUILD_ORDER = [
        ("SpawningPool", 1),
        ("Extractor", 1),
    ]
    MAX_WORKERS = 14
    ATTACK_DELAY = 80
    RALLY_SIZE = 3
    TRAIN_BUILDINGS = {"base", "Hatchery", "Lair", "Hive"}

    def decide(self, observation: dict) -> dict:
        cat = self._categorize(observation)
        cmds: list[dict] = []
        tick = observation.get("tick", 0)
        mineral, gas, supply_used, supply_cap = self._get_resources(observation)
        has_pool = self._count_building_type(cat, "SpawningPool") >= 1
        n_workers = self._count_workers(cat)

        # ── 1. Build (minimal: SpawningPool + Extractor) ──
        idle_w = cat["idle_workers"]
        if idle_w and n_workers > 1:
            wid, w = idle_w[0]
            for btype, max_n in self.BUILD_ORDER:
                if self._count_building_type(cat, btype) >= max_n:
                    continue
                cost = {"SpawningPool": 200, "Extractor": 50}.get(btype, 150)
                if mineral < cost:
                    continue
                bx = w.get("pos_x", 9.6) + self._count_building_type(cat, btype) * 2
                by = w.get("pos_y", 9.6) + 1
                cmds.append(self._cmd_build(wid, btype, bx, by))
                break

        # ── 2. Gather ──
        build_wid = idle_w[0][0] if idle_w else None
        for wid, w in idle_w:
            if wid != build_wid:
                self._assign_workers_to_minerals(cmds, cat)

        # ── 3. Overlord when supply tight ──
        if supply_cap > 0 and supply_cap - supply_used <= 2 and mineral >= 100:
            bid = self._find_any_barracks(cat)
            if bid:
                cmds.append(self._cmd_train(bid, "Overlord"))

        # ── 4. Military — ALWAYS prioritize Zerglings ──
        if has_pool:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt not in self.TRAIN_BUILDINGS:
                    continue
                if self._building_has_queue(cat, eid):
                    continue
                if mineral >= 50:
                    cmds.append(self._cmd_train(eid, "Zergling"))
                    mineral -= 50

        # ── 5. Workers only before pool ──
        if n_workers < self.MAX_WORKERS and mineral >= 50 and not has_pool:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt in self.TRAIN_BUILDINGS and not self._building_has_queue(cat, eid):
                    cmds.append(self._cmd_train(eid, "Drone"))
                    mineral -= 50
                    break

        # ── 6. Attack — aggressive ──
        idle_combat = cat["idle_combat"]
        if len(idle_combat) >= self.RALLY_SIZE or tick > self.ATTACK_DELAY:
            self._push_toward_enemy_base(cmds, cat, tick)

        self._retreat_damaged_workers(cmds, cat)
        return {"commands": cmds}