"""Terran ScriptAI — ranged turtle, timing push.

Strategy:
- Supply Depot → Barracks → Factory progression
- Mass Marines with range advantage
- Tanks for siege support
- Delay attack to build up a strong force (RALLY_SIZE=6)
- Defend base if threatened
"""
from __future__ import annotations
from agents.race_ai_base import RaceAIBase


class TerranAI(RaceAIBase):
    """Rule-based Terran AI — ranged turtle + timing push."""

    NAME = "TerranAI"
    RACE = "terran"

    BUILD_ORDER = [
        ("SupplyDepot", 2),
        ("Barracks", 2),
        ("Refinery", 1),
        ("Factory", 1),
        ("Academy", 1),
    ]
    MAX_WORKERS = 14
    MAX_BUILDINGS = 12
    ATTACK_DELAY = 300
    RALLY_SIZE = 6

    def decide(self, observation: dict) -> dict:
        cat = self._categorize(observation)
        cmds: list[dict] = []
        tick = observation.get("tick", 0)
        mineral, gas, supply_used, supply_cap = self._get_resources(observation)
        n_workers = self._count_workers(cat)
        has_rax = self._count_building_type(cat, "Barracks") >= 1
        has_fac = self._count_building_type(cat, "Factory") >= 1

        # ── 1. Build ──
        idle_w = cat["idle_workers"]
        n_bldgs = len(cat["my_buildings"])
        if idle_w and n_bldgs < self.MAX_BUILDINGS:
            wid, w = idle_w[0]
            for btype, max_n in self.BUILD_ORDER:
                if self._count_building_type(cat, btype) >= max_n:
                    continue
                cost = {"SupplyDepot": 100, "Barracks": 150, "Refinery": 100,
                        "Factory": 200, "Academy": 150}.get(btype, 150)
                if mineral < cost:
                    continue
                bx = w.get("pos_x", 9.6) + n_bldgs * 2
                by = w.get("pos_y", 9.6) + 1
                cmds.append(self._cmd_build(wid, btype, bx, by))
                mineral -= cost
                break

        # ── 2. Supply at threshold ──
        if supply_cap - supply_used <= 3 and mineral >= 100:
            if idle_w:
                wid, w = idle_w[-1]
                cmds.append(self._cmd_build(wid, "SupplyDepot",
                            w.get("pos_x", 9.6) + 3, w.get("pos_y", 9.6) + 3))

        # ── 3. Gather ──
        build_wid = idle_w[0][0] if idle_w else None
        for wid, w in idle_w:
            if wid != build_wid:
                self._assign_workers_to_minerals(cmds, cat)

        # ── 4. Military — Marines + Tanks ──
        for eid, ent in cat["my_buildings"].items():
            bt = ent.get("building_type", "")
            if bt == "Barracks" and has_rax and mineral >= 50:
                if not self._building_has_queue(cat, eid):
                    cmds.append(self._cmd_train(eid, "Marine"))
                    mineral -= 50
                    continue
            if bt == "Factory" and has_fac and mineral >= 150 and gas >= 50:
                if not self._building_has_queue(cat, eid):
                    cmds.append(self._cmd_train(eid, "Tank"))
                    mineral -= 150
                    gas -= 50
                    continue

        # ── 5. Workers ──
        if n_workers < self.MAX_WORKERS and mineral >= 50:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt in ("base", "CommandCenter") and not self._building_has_queue(cat, eid):
                    cmds.append(self._cmd_train(eid, "SCV"))
                    mineral -= 50
                    break

        # ── 6. Attack — defend if threatened, otherwise timing push ──
        idle_combat = cat["idle_combat"]
        base_threatened = any(
            "base" in eid for eid, _ in cat.get("enemies", [])
        )
        if base_threatened or len(idle_combat) >= self.RALLY_SIZE or tick > self.ATTACK_DELAY:
            self._push_toward_enemy_base(cmds, cat, tick)

        self._retreat_damaged_workers(cmds, cat)
        return {"commands": cmds}