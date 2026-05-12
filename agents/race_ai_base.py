"""Base class for race-specific ScriptAIs.

Provides shared helpers: entity categorization, resource tracking,
distance calculations, and common decision patterns.
"""
from __future__ import annotations

import math
from typing import Any


def _dist(a: dict, b: dict) -> float:
    """Euclidean distance between two entity dicts."""
    dx = a.get("pos_x", 0) - b.get("pos_x", 0)
    dy = a.get("pos_y", 0) - b.get("pos_y", 0)
    return math.sqrt(dx * dx + dy * dy)


def _nearest(entities: list[tuple[str, dict]], ref: dict) -> tuple[str, dict] | None:
    """Return (eid, entity) of the nearest entity in the list."""
    best = None
    best_d = float("inf")
    for eid, e in entities:
        d = _dist(ref, e)
        if d < best_d:
            best_d = d
            best = (eid, e)
    return best


# Worker entity types (covers both simplified and JSON-based naming)
_WORKER_TYPES = {"worker", "SCV", "Drone", "Probe", "Overlord"}
# Combat unit entity types
_COMBAT_TYPES = {
    "soldier", "scout", "unit",
    "Marine", "Firebat", "Ghost", "Medic", "Vulture", "Tank", "Goliath",
    "Wraith", "Vessel", "BattleCruiser", "Valkyrie",
    "Zergling", "Hydralisk", "Lurker", "Ultralisk",
    "Queen", "Defiler", "Mutalisk", "Guardian", "Devourer", "Scourge",
    "Zealot", "Dragoon", "Templar", "HighTemplar", "DarkTemplar",
    "Archon", "DarkArchon", "Reaver",
    "Arbiter", "Scout_unit", "Carrier", "Corsair",
}
# Supply provider types
_SUPPLY_BUILDING_TYPES = {"SupplyDepot", "supply_depot", "Pylon", "pylon"}
# Base building types
_BASE_BUILDING_TYPES = {"base", "CommandCenter", "Nexus", "Hatchery", "Lair", "Hive"}
# Barracks types
_BARRACKS_TYPES = {"barracks", "Barracks", "Gateway"}


class RaceAIBase:
    """Common functionality for all race AIs."""

    MAX_WORKERS = 16
    RALLY_SIZE = 4
    RETREAT_HP_FRAC = 0.3

    def __init__(self, player_id: int = 1) -> None:
        self.player_id = player_id
        self._rally_point: tuple[float, float] | None = None

    # ─── Entity type checking helpers ──────────────────────────
    @staticmethod
    def _is_worker(e: dict) -> bool:
        etype = e.get("entity_type", "")
        utype = e.get("unit_type", "")
        return etype in _WORKER_TYPES or utype in _WORKER_TYPES

    @staticmethod
    def _is_combat(e: dict) -> bool:
        etype = e.get("entity_type", "")
        utype = e.get("unit_type", "")
        return etype in _COMBAT_TYPES or utype in _COMBAT_TYPES

    @staticmethod
    def _is_building(e: dict) -> bool:
        return e.get("entity_type", "") == "building"

    @staticmethod
    def _is_resource(e: dict) -> bool:
        return e.get("entity_type", "") == "resource"

    # ─── Observation parsing ──────────────────────────────────
    def _categorize(self, obs: dict) -> dict:
        """Split entities into useful buckets."""
        entities = obs.get("entities", {})
        out: dict[str, Any] = {
            "idle_workers": [],
            "gathering_workers": [],
            "all_workers": [],
            "combat_units": [],
            "idle_combat": [],
            "my_buildings": {},
            "my_base": None,
            "enemies": [],
            "resources_mineral": [],
            "resources_gas": [],
        }

        # Find base first
        for eid, e in entities.items():
            if e.get("owner") == self.player_id and self._is_building(e):
                bt = e.get("building_type", "")
                if bt in _BASE_BUILDING_TYPES and e.get("health", 0) > 0:
                    out["my_base"] = e
                    break

        for eid, e in entities.items():
            owner = e.get("owner", 0)
            idle = e.get("is_idle", True)

            if owner == self.player_id:
                if self._is_worker(e):
                    out["all_workers"].append((eid, e))
                    if idle and not e.get("returning_to_base"):
                        health_frac = e.get("health", 0) / max(e.get("max_health", 1), 1)
                        if health_frac < self.RETREAT_HP_FRAC and out["my_base"]:
                            # Don't add to idle_workers; they'll retreat elsewhere
                            continue
                        out["idle_workers"].append((eid, e))
                    elif not idle and e.get("carry_amount", 0) > 0:
                        out["gathering_workers"].append((eid, e))
                elif self._is_combat(e):
                    out["combat_units"].append((eid, e))
                    if idle:
                        out["idle_combat"].append((eid, e))
                elif self._is_building(e):
                    out["my_buildings"][eid] = e
            elif owner == 0:
                if self._is_resource(e):
                    if e.get("resource_type") == "mineral" and e.get("resource_amount", 0) > 0:
                        out["resources_mineral"].append((eid, e))
                    elif e.get("resource_type") == "gas" and e.get("resource_amount", 0) > 0:
                        out["resources_gas"].append((eid, e))
            elif owner != 0 and e.get("health", 0) > 0:
                out["enemies"].append((eid, e))

        return out

    def _get_resources(self, obs: dict) -> tuple[int, int, int, int]:
        """Return (mineral, gas, supply_used, supply_cap)."""
        resources = obs.get("resources", {})
        if isinstance(resources, dict):
            mineral = resources.get(f"p{self.player_id}_mineral", 0)
            gas = resources.get(f"p{self.player_id}_gas", 0)
            supply_used = resources.get(f"p{self.player_id}_supply_used", 0)
            supply_cap = resources.get(f"p{self.player_id}_supply_cap", 0)
            return mineral, gas, supply_used, supply_cap
        return 0, 0, 0, 0

    # ─── Command builders ─────────────────────────────────────
    def _cmd_gather(self, worker_id: str, resource_id: str) -> dict:
        return {
            "action": "gather",
            "worker_id": worker_id,
            "resource_id": resource_id,
            "issuer": self.player_id,
        }

    def _cmd_move(self, unit_id: str, tx: float, ty: float) -> dict:
        return {
            "action": "move",
            "unit_id": unit_id,
            "target_x": tx,
            "target_y": ty,
            "issuer": self.player_id,
        }

    def _cmd_attack(self, attacker_id: str, target_id: str) -> dict:
        return {
            "action": "attack",
            "attacker_id": attacker_id,
            "target_id": target_id,
            "issuer": self.player_id,
        }

    def _cmd_build(self, builder_id: str, btype: str, px: float, py: float) -> dict:
        return {
            "action": "build",
            "builder_id": builder_id,
            "building_type": btype,
            "pos_x": px,
            "pos_y": py,
            "issuer": self.player_id,
        }

    def _cmd_train(self, building_id: str, utype: str) -> dict:
        return {
            "action": "train",
            "building_id": building_id,
            "unit_type": utype,
            "issuer": self.player_id,
        }

    def _cmd_spell(self, caster_id: str, spell: str, *,
                   target_id: str = "", target_x: float = 0, target_y: float = 0) -> dict:
        cmd: dict[str, Any] = {
            "action": "spell",
            "caster_id": caster_id,
            "spell": spell,
            "issuer": self.player_id,
        }
        if target_id:
            cmd["target_id"] = target_id
        if target_x or target_y:
            cmd["target_x"] = target_x
            cmd["target_y"] = target_y
        return cmd

    # ─── Shared tactics ───────────────────────────────────────
    def _assign_workers_to_minerals(self, commands: list, cat: dict) -> None:
        """Send idle workers to nearest mineral patch."""
        for wid, worker in cat["idle_workers"]:
            if not cat["resources_mineral"]:
                break
            target = _nearest(cat["resources_mineral"], worker)
            if target:
                rid, _ = target
                commands.append(self._cmd_gather(wid, rid))

    def _assign_workers_to_gas(self, commands: list, cat: dict, max_gas: int = 3) -> None:
        """Assign idle workers to gas if refinery exists and needed."""
        gas_gatherers = sum(
            1 for _, w in cat["gathering_workers"]
            if w.get("carry_type", "mineral") == "gas"
        )
        if gas_gatherers >= max_gas:
            return
        # Check for refinery/extractor/assimilator
        has_gas_building = any(
            b.get("building_type") in ("refinery", "Refinery", "Extractor", "Assimilator")
            for b in cat["my_buildings"].values()
        )
        if not has_gas_building:
            return
        remaining = max_gas - gas_gatherers
        for wid, worker in cat["idle_workers"]:
            if remaining <= 0:
                break
            if not cat["resources_gas"]:
                break
            target = _nearest(cat["resources_gas"], worker)
            if target:
                rid, _ = target
                commands.append(self._cmd_gather(wid, rid))
                remaining -= 1

    def _focus_fire(self, commands: list, cat: dict) -> None:
        """All idle combat units attack the weakest visible enemy."""
        if not cat["idle_combat"] or not cat["enemies"]:
            return

        target_eid, target_e = min(
            cat["enemies"],
            key=lambda x: x[1].get("health", 100) / max(x[1].get("max_health", 100), 1),
        )
        for uid, _ in cat["idle_combat"]:
            commands.append(self._cmd_attack(uid, target_eid))

    def _push_toward_enemy_base(self, commands: list, cat: dict, tick: int) -> None:
        """Move idle combat units toward the enemy base area."""
        if not cat["idle_combat"]:
            return
        ex, ey = self._enemy_base_position(cat)
        for uid, _ in cat["idle_combat"]:
            commands.append(self._cmd_move(uid, ex, ey))

    def _retreat_damaged_workers(self, commands: list, cat: dict) -> None:
        """Move workers with low HP back to base."""
        base = cat["my_base"]
        if not base:
            return
        for wid, worker in cat["idle_workers"]:
            hp_frac = worker.get("health", 0) / max(worker.get("max_health", 1), 1)
            if hp_frac < self.RETREAT_HP_FRAC:
                commands.append(self._cmd_move(wid, base["pos_x"], base["pos_y"]))

    def _base_position(self, cat: dict) -> tuple[float, float]:
        base = cat["my_base"]
        if base:
            return base.get("pos_x", 10.0), base.get("pos_y", 10.0)
        return 10.0, 10.0

    def _enemy_base_position(self, cat: dict) -> tuple[float, float]:
        for eid, e in cat["enemies"]:
            if e.get("entity_type") == "building" and e.get("building_type") in _BASE_BUILDING_TYPES:
                return e.get("pos_x", 54.0), e.get("pos_y", 54.0)
        return (54.0, 54.0) if self.player_id == 1 else (10.0, 10.0)

    def _count_my_type(self, obs: dict, etype: str) -> int:
        entities = obs.get("entities", {})
        return sum(
            1 for e in entities.values()
            if e.get("owner") == self.player_id and e.get("entity_type") == etype
        )

    def _count_workers(self, cat: dict) -> int:
        """Count all owned workers (simplified and JSON-named)."""
        return len(cat["all_workers"])

    def _count_building_type(self, cat: dict, btype: str) -> int:
        return sum(
            1 for b in cat["my_buildings"].values()
            if b.get("building_type") == btype and not b.get("is_constructing", False)
        )

    def _find_building_id(self, cat: dict, btype: str) -> str | None:
   # Try exact match first, then case-insensitive
        for eid, b in cat["my_buildings"].items():
            if b.get("building_type") == btype and not b.get("is_constructing", False):
                return eid
        # Case-insensitive fallback
        for eid, b in cat["my_buildings"].items():
            if b.get("building_type", "").lower() == btype.lower() and not b.get("is_constructing", False):
                return eid
        return None

    def _is_building_constructing(self, cat: dict, btype: str) -> bool:
        return any(
            b.get("building_type", "").lower() == btype.lower() and b.get("is_constructing", False)
            for b in cat["my_buildings"].values()
        )

    def _find_any_barracks(self, cat: dict) -> str | None:
        """Find any production building (barracks or gateway)."""
        for bt in _BARRACKS_TYPES:
            bid = self._find_building_id(cat, bt)
            if bid:
                return bid
        return None

    def _building_has_queue(self, cat: dict, building_id: str) -> bool:
        """Check if a building already has something in its production queue."""
        b = cat["my_buildings"].get(building_id, {})
        queue = b.get("production_queue", [])
        return len(queue) > 0