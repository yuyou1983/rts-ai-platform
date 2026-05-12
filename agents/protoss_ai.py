"""Protoss ScriptAI — rule-based Protoss opponent.

Strategy:
- Pylon FIRST (for pylon power), then 2 Gateways
- Zealot rush, Dragoon after CyberCore
- Limit buildings, focus on army
- Attack with rally groups toward enemy base
"""
from __future__ import annotations
from agents.race_ai_base import RaceAIBase


class ProtossAI(RaceAIBase):
    """Rule-based Protoss AI — rush-oriented."""

    NAME = "ProtossAI"
    RACE = "protoss"

    BUILD_ORDER = [
        ("Pylon", 2),
        ("Gateway", 2),
        ("Assimilator", 1),
        ("CyberneticsCore", 1),
    ]
    MAX_WORKERS = 14
    MAX_BUILDINGS = 8
    ATTACK_DELAY = 80
    RALLY_SIZE = 2

    def decide(self, observation: dict) -> dict:
        cat = self._categorize(observation)
        cmds: list[dict] = []
        tick = observation.get("tick", 0)
        mineral, gas, supply_used, supply_cap = self._get_resources(observation)
        has_pylon = self._count_building_type(cat, "Pylon") >= 1
        has_gate = self._count_building_type(cat, "Gateway") >= 1
        n_workers = self._count_workers(cat)

        # ── 1. Build (cap total buildings) ──
        idle_w = cat["idle_workers"]
        n_bldgs = len(cat["my_buildings"])
        if idle_w and n_bldgs < self.MAX_BUILDINGS:
            wid, w = idle_w[0]
            # Priority: Pylon first if none exist
            if not has_pylon and mineral >= 100:
                cmds.append(self._cmd_build(wid, "Pylon",
                            w.get("pos_x", 54.4) + 2, w.get("pos_y", 54.4) + 2))
            else:
                for btype, max_n in self.BUILD_ORDER:
                    if self._count_building_type(cat, btype) >= max_n:
                        continue
                    cost = {"Pylon": 100, "Gateway": 150, "Assimilator": 100,
                            "CyberneticsCore": 200}.get(btype, 150)
                    if mineral < cost:
                        continue
                    bx = w.get("pos_x", 54.4) + n_bldgs * 2
                    by = w.get("pos_y", 54.4) + 1
                    cmds.append(self._cmd_build(wid, btype, bx, by))
                    break

        # ── 2. Pylon at supply threshold ──
        if supply_cap > 0 and supply_cap - supply_used <= 3 and mineral >= 100:
            if idle_w:
                wid, w = idle_w[-1]
                cmds.append(self._cmd_build(wid, "Pylon",
                            w.get("pos_x", 54.4) + 3, w.get("pos_y", 54.4) + 3))

        # ── 3. Gather ──
        build_wid = idle_w[0][0] if idle_w else None
        for wid, w in idle_w:
            if wid != build_wid:
                self._assign_workers_to_minerals(cmds, cat)

        # ── 4. Military — ZEALOTS FIRST, Dragoon if CyberCore ──
        has_cyber = self._count_building_type(cat, "CyberneticsCore") >= 1
        if has_pylon and has_gate:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt != "Gateway":
                    continue
                if self._building_has_queue(cat, eid):
                    continue
                if mineral >= 100:
                    cmds.append(self._cmd_train(eid, "Zealot"))
                    mineral -= 100
                    continue
                if has_cyber and mineral >= 125 and gas >= 50:
                    cmds.append(self._cmd_train(eid, "Dragoon"))
                    mineral -= 125
                    gas -= 50
                    continue

        # ── 5. Workers from Nexus when no gate yet ──
        if n_workers < self.MAX_WORKERS and mineral >= 50 and not has_gate:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt in ("base", "Nexus") and not self._building_has_queue(cat, eid):
                    cmds.append(self._cmd_train(eid, "Probe"))
                    mineral -= 50
                    break

        # ── 6. Attack — aggressive ──
        idle_combat = cat["idle_combat"]
        if len(idle_combat) >= self.RALLY_SIZE or tick > self.ATTACK_DELAY:
            self._push_toward_enemy_base(cmds, cat, tick)

        self._retreat_damaged_workers(cmds, cat)
        return {"commands": cmds}