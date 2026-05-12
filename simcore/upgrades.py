"""Upgrade effects: apply stat modifications based on completed upgrades.

Upgrade groups:
  - Infantry Weapons/Armor (Terran)
  - Vehicle Weapons/Plating (Terran)
  - Ship Weapons/Plating (Terran)
  - Zerg Melee/Missile/Carapace
  - Protoss Ground Weapons/Armor/Shields
  - Protoss Air Weapons/Armor/Shields
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ─── Data Loading ────────────────────────────────────────────

_UPGRADE_DATA: list[dict] | None = None


def _load_upgrade_data() -> list[dict]:
    global _UPGRADE_DATA
    if _UPGRADE_DATA is None:
        path = Path(__file__).resolve().parent.parent / "data" / "upgrades" / "upgrades.json"
        with open(path) as f:
            raw = json.load(f)
        _UPGRADE_DATA = raw.get("upgrades", [])
    return _UPGRADE_DATA


# ─── Upgrade Category Mapping ───────────────────────────────

# Maps upgrade name patterns to (stat, affected_units, bonus_per_level)
_UPGRADE_EFFECTS: list[dict[str, Any]] = [
    # Terran
    {
        "pattern": "Infantry Weapons",
        "stat": "attack",
        "units": ["Marine", "Ghost", "Firebat"],
        "simplified_units": ["soldier", "scout"],
        "bonus": 1,
        "firebat_bonus": 2,  # Firebat gets +2 per level
    },
    {
        "pattern": "Infantry Armor",
        "stat": "armor",
        "units": ["Marine", "Ghost", "Firebat", "Medic"],
        "simplified_units": ["soldier", "scout", "worker"],
        "bonus": 1,
    },
    {
        "pattern": "Vehicle Weapons",
        "stat": "attack",
        "units": ["Vulture", "Tank", "Goliath"],
        "bonus": 1,
    },
    {
        "pattern": "Vehicle Plating",
        "stat": "armor",
        "units": ["Vulture", "Tank", "Goliath"],
        "bonus": 1,
    },
    {
        "pattern": "Ship Weapons",
        "stat": "attack",
        "units": ["Wraith", "BattleCruiser", "Valkyrie"],
        "bonus": 1,
    },
    {
        "pattern": "Ship Plating",
        "stat": "armor",
        "units": ["Wraith", "BattleCruiser", "Valkyrie", "Dropship", "Vessel"],
        "bonus": 1,
    },
    # Zerg
    {
        "pattern": "Melee Attacks",
        "stat": "attack",
        "units": ["Zergling", "Ultralisk", "Broodling", "Drone"],
        "bonus": 1,
        "ultralisk_bonus": 3,
    },
    {
        "pattern": "Missile Attacks",
        "stat": "attack",
        "units": ["Hydralisk", "Mutalisk", "Guardian", "Devourer", "Queen", "SporeColony"],
        "bonus": 1,
    },
    {
        "pattern": "Carapace",
        "stat": "armor",
        "units": ["Zergling", "Hydralisk", "Ultralisk", "Drone", "Overlord",
                   "Mutalisk", "Guardian", "Devourer", "Queen", "Defiler",
                   "Scourge", "Broodling", "Lurker", "InfestedTerran", "Larva"],
        "bonus": 1,
    },
    # Protoss
    {
        "pattern": "Ground Weapons",
        "stat": "attack",
        "units": ["Zealot", "Dragoon", "DarkTemplar", "Reaver", "Archon"],
        "bonus": 1,
        "zealot_bonus": 2,
    },
    {
        "pattern": "Ground Armor",
        "stat": "armor",
        "units": ["Zealot", "Dragoon", "DarkTemplar", "Reaver", "Archon", "Probe"],
        "bonus": 1,
    },
    {
        "pattern": "Plasma Shields",
        "stat": "shield_armor",
        "units": ["Zealot", "Dragoon", "DarkTemplar", "Reaver", "Archon",
                   "Probe", "Scout", "Corsair", "Carrier", "Arbiter",
                   "Observer", "Shuttle", "DarkArchon"],
        "bonus": 1,
    },
    {
        "pattern": "Air Weapons",
        "stat": "attack",
        "units": ["Scout", "Corsair", "Carrier", "Arbiter"],
        "bonus": 1,
    },
    {
        "pattern": "Air Armor",
        "stat": "armor",
        "units": ["Scout", "Corsair", "Carrier", "Arbiter", "Observer", "Shuttle"],
        "bonus": 1,
    },
]


def _get_upgrade_levels(completed_upgrades: list[str]) -> dict[str, int]:
    """Parse completed upgrade names into a dict of {upgrade_base_name: level}."""
    levels: dict[str, int] = {}
    for name in completed_upgrades:
        # Try to extract pattern and level from name like "Infantry Weapons 2"
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            base = parts[0]
            try:
                lvl = int(parts[1])
            except ValueError:
                base = name
                lvl = 1
        else:
            base = name
            lvl = 1
        current = levels.get(base, 0)
        levels[base] = max(current, lvl)
    return levels


def _unit_matches(unit: dict[str, Any], pattern: str) -> bool:
    """Check if a unit matches any of the upgrade effect patterns."""
    utype = unit.get("unit_type", unit.get("entity_type", ""))
    for effect in _UPGRADE_EFFECTS:
        if effect["pattern"] == pattern:
            if utype in effect.get("units", []):
                return True
            if utype in effect.get("simplified_units", []):
                return True
    return False


def apply_upgrade_effects(
    entities: dict[str, Any],
    completed_upgrades: list[str],
) -> dict[str, Any]:
    """Modify unit stats based on completed upgrades.

    Args:
        entities: Current game entities dict.
        completed_upgrades: List of completed upgrade names.

    Returns:
        Updated entities dict with upgrade bonuses applied.
    """
    if not completed_upgrades:
        return entities

    result = dict(entities)
    levels = _get_upgrade_levels(completed_upgrades)

    for eid, e in list(result.items()):
        # Only apply to units (not buildings, resources, effects)
        etype = e.get("entity_type", "")
        if etype not in ("worker", "soldier", "scout", "unit"):
            continue

        updates: dict[str, Any] = {}
        utype = e.get("unit_type", etype)

        for effect in _UPGRADE_EFFECTS:
            pattern = effect["pattern"]
            level = levels.get(pattern, 0)
            if level <= 0:
                continue

            affected = effect.get("units", [])
            simplified = effect.get("simplified_units", [])

            if utype not in affected and etype not in simplified:
                continue

            stat = effect["stat"]
            bonus_per_level = effect.get("bonus", 1)

            # Special cases for specific unit bonuses
            extra = 0
            if utype == "Firebat" and "firebat_bonus" in effect:
                extra = effect["firebat_bonus"] * level - bonus_per_level * level
            elif utype == "Ultralisk" and "ultralisk_bonus" in effect:
                extra = effect["ultralisk_bonus"] * level - bonus_per_level * level
            elif utype == "Zealot" and "zealot_bonus" in effect:
                extra = effect["zealot_bonus"] * level - bonus_per_level * level

            total_bonus = bonus_per_level * level + extra

            if stat == "attack":
                base_attack = e.get("base_attack", e.get("attack", 0))
                updates["attack"] = base_attack + total_bonus
                updates["upgrade_attack_bonus"] = total_bonus
            elif stat == "armor":
                base_armor = e.get("base_armor", e.get("armor", 0))
                updates["armor"] = base_armor + total_bonus
                updates["upgrade_armor_bonus"] = total_bonus
            elif stat == "shield_armor":
                updates["shield_armor_bonus"] = total_bonus

        if updates:
            # Store base stats if not already stored
            if "base_attack" not in e:
                updates["base_attack"] = e.get("attack", 0)
            if "base_armor" not in e:
                updates["base_armor"] = e.get("armor", 0)
            result[eid] = {**e, **updates}

    return result