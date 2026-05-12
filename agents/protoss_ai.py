"""Protoss ScriptAI — minimal buildings, max army.

Strategy:
- Single Pylon → 1 Gateway → ZEALOTS
- Only build what's needed for production
- Never build more than 2 Pylons unless supply blocked
- Attack early with 2 Zealots
"""
from __future__ import annotations
from agents.race_ai_base import RaceAIBase


class ProtossAI(RaceAIBase):
    """Rule-based Protoss AI — minimal infrastructure, max army."""

    NAME = "ProtossAI"
    RACE = "protoss"

    MAX_WORKERS = 10
    MAX_BUILDINGS = 5
    ATTACK_DELAY = 100
    RALLY_SIZE = 2

    def decide(self, observation: dict) -> dict:
        cat = self._categorize(observation)
        cmds: list[dict] = []
        tick = observation.get("tick", 0)
        mineral, gas, supply_used, supply_cap = self._get_resources(observation)
        n_pylons = self._count_building_type(cat, "Pylon")
        n_gates = self._count_building_type(cat, "Gateway")
        n_workers = self._count_workers(cat)
        has_pylon = n_pylons >= 1
        has_gate = n_gates >= 1

        # ── 1. Build (STRICTLY minimal) ──
        idle_w = cat["idle_workers"]
        n_bldgs = len(cat["my_buildings"])
        if idle_w and n_bldgs < self.MAX_BUILDINGS and n_workers > 1:
            wid, w = idle_w[0]
            # Priority 1: First Pylon if none
            if not has_pylon and mineral >= 100:
                cmds.append(self._cmd_build(wid, "Pylon",
                            w.get("pos_x", 54.4) + 2, w.get("pos_y", 54.4) + 2))
                mineral -= 100
            # Priority 2: First Gateway if have Pylon but no Gate
            elif has_pylon and n_gates < 1 and mineral >= 150:
                cmds.append(self._cmd_build(wid, "Gateway",
                            w.get("pos_x", 54.4) + 4, w.get("pos_y", 54.4) + 1))
                mineral -= 150
            # Priority 3: Supply Pylon only if truly blocked
            elif has_pylon and supply_cap - supply_used <= 2 and mineral >= 100 and n_pylons < 3:
                cmds.append(self._cmd_build(wid, "Pylon",
                            w.get("pos_x", 54.4) + n_pylons * 2, w.get("pos_y", 54.4) + 2))
                mineral -= 100

        # ── 2. Gather ──
        build_wid = idle_w[0][0] if idle_w else None
        for wid, w in idle_w:
            if wid != build_wid:
                self._assign_workers_to_minerals(cmds, cat)

        # ── 3. Military — ZEALOTS nonstop ──
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

        # ── 4. Workers from Nexus — only if we're short ──
        if n_workers < self.MAX_WORKERS and mineral >= 50:
            for eid, ent in cat["my_buildings"].items():
                bt = ent.get("building_type", "")
                if bt in ("base", "Nexus") and not self._building_has_queue(cat, eid):
                    cmds.append(self._cmd_train(eid, "Probe"))
                    mineral -= 50
                    break

        # ── 5. Attack — early timing ──
        idle_combat = cat["idle_combat"]
        if len(idle_combat) >= self.RALLY_SIZE or tick > self.ATTACK_DELAY:
            self._push_toward_enemy_base(cmds, cat, tick)

        self._retreat_damaged_workers(cmds, cat)
        return {"commands": cmds}