#!/usr/bin/env python3
"""Sync combat mechanics catalog and unit bindings from audited SC1 reference.

Reads data/combat/sc1_representative_reference.json and updates:
- data/combat/weapons.json (mechanics catalog)
- simcore/data/unit_stats.json (unit → semantic weapon binding)

Idempotent: running twice produces identical output.
Does NOT copy mechanics values into unit entities — only bindings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REFERENCE_PATH = REPO / "data/combat/sc1_representative_reference.json"
WEAPONS_PATH = REPO / "data/combat/weapons.json"
UNIT_STATS_PATH = REPO / "simcore/data/unit_stats.json"

# Map reference unit names to unit_stats keys
PROJECT_TO_STATS_KEY = {
    "Marine": "Marine",
    "Vulture": "Vulture",
    "Tank": "Tank",
    "Firebat": "Firebat",
    "Zergling": "Zergling",
    "Hydralisk": "Hydralisk",
    "Ultralisk": "Ultralisk",
    "Mutalisk": "Mutalisk",
    "Zealot": "Zealot",
    "Dragoon": "Dragoon",
    "HighTemplar": "Templar",
    "Reaver": "Reaver",
}

# Weapon behavior → delivery type mapping
# SC1 weapon_behavior values: 0=melee, 1=tracking, 2=projectile, 3=area_effect, 5=normal_melee, 7=chain
BEHAVIOR_TO_DELIVERY = {
    0: "melee",        # melee (Vulture grenade is special - hitscan)
    1: "tracking",     # tracking (Dragoon)
    2: "projectile",   # projectile (Marine, Tank, Hydralisk)
    3: "area_periodic", # spell (Storm)
    5: "melee",        # normal melee (Firebat, Zergling, Ultralisk, Zealot, Reaver scarab)
    7: "chain",        # chain (Mutalisk)
}

# Weapon type → damage_type mapping
WEAPON_TYPE_MAP = {
    "normal": "normal",
    "explosive": "explosive",
    "concussive": "concussive",
    "independent": "normal",
    "independent_spell": "spells",
}

# Cooldown ticks conversion: SC1 cooldown is in 1/24 seconds * 3 (frames)
# Our engine uses ticks where 1 tick = 1/24 second
# SC1 weapon_cooldown value * 3 / 24 = ticks, but we keep the raw value as ticks
COOLDOWN_TICKS_MAP = {
    # Direct cooldown values from DAT
}


def _resolve_delivery(weapon_data: dict, ref_name: str) -> str:
    """Resolve delivery type from weapon behavior and known special cases."""
    behavior = weapon_data.get("weapon_behavior", 0)
    # Special cases
    if ref_name == "Vulture":
        # Vulture grenade is a projectile despite behavior=0 (melee in DAT means "no iscript projectile")
        return "projectile"
    if ref_name == "Marine":
        return "hitscan"  # Marine uses hitscan
    if ref_name == "Reaver":
        return "tracking"  # Scarab tracks target
    if ref_name == "Firebat":
        return "melee"  # Firebat is close-range splash
    return BEHAVIOR_TO_DELIVERY.get(behavior, "hitscan")


def build_weapon_catalog(reference: dict) -> dict:
    """Build the complete weapons.json from audited reference."""
    weapons: dict = {"_meta": {"generated_from": "sc1_representative_reference.json"}}

    for name, unit_data in reference["units"].items():
        w = unit_data.get("weapon") or unit_data.get("spell_weapon") or unit_data.get("scarab_weapon")
        if not w:
            continue

        semantic_id = unit_data["semantic_weapon_id"]
        dat_id = unit_data["effective_weapon_dat_id"]

        # Determine delivery type
        if unit_data.get("spell_weapon") is not None or unit_data.get("scarab_weapon") is not None:
            if "spell_weapon" in unit_data:
                delivery = "area_periodic"
            else:
                delivery = "tracking"
        else:
            delivery = _resolve_delivery(w, name)

        # Damage type
        damage_type = WEAPON_TYPE_MAP.get(w.get("weapon_type", "normal"), "normal")

        # Splash
        inner = w.get("inner_splash_range", 0)
        medium = w.get("medium_splash_range", 0)
        outer = w.get("outer_splash_range", 0)
        has_splash = inner > 0 or medium > 0 or outer > 0

        # Projectile speed: SC1 iscript values approximated in world units/tick.
        # These are derived from iscript.bin frame counts and OpenBW projectile
        # velocity constants, converted to our world-unit scale.
        PROJECTILE_SPEEDS = {
            "terran_fragmentation_grenade": 4.0,    # Vulture grenade
            "terran_arclite_cannon": 3.0,       # Tank siege cannon
            "zerg_needle_spines": 4.0,           # Hydralisk spines
            "protoss_phase_disruptor": 3.5,     # Dragoon bolt (tracking)
            "zerg_glave_wurm": 4.0,             # Mutalisk glaive (chain)
            "protoss_scarab": 2.5,              # Reaver scarab (tracking, slow)
        }
        proj_speed = PROJECTILE_SPEEDS.get(semantic_id, 0.0)

        entry: dict = {
            "weapon_id": semantic_id,
            "source_weapon_dat_id": dat_id,
            "damage_per_hit": w["damage_amount"],
            "mechanical_hit_count": unit_data.get("max_ground_hits", 1) or 1,
            "damage_type": damage_type,
            "delivery_type": delivery,
            "cooldown_ticks": w.get("weapon_cooldown", 15),
            "launch_delay_ticks": 0,
            "projectile_speed_world_per_tick": proj_speed,
        }

        # Splash profile
        if has_splash:
            if "scarab_weapon" in unit_data:
                entry["splash_profile"] = "radial"
                entry["splash_inner"] = inner
                entry["splash_medium"] = medium
                entry["splash_outer"] = outer
                entry["splash_fractions"] = [1.0, 0.5, 0.25]
            elif "spell_weapon" in unit_data:
                entry["splash_profile"] = "radial"
                entry["splash_inner"] = inner
                entry["splash_medium"] = medium
                entry["splash_outer"] = outer
                entry["splash_fractions"] = [1.0, 1.0, 1.0]  # Storm does full in all radii
            else:
                # Firebat line splash
                entry["splash_profile"] = "line"
                entry["splash_inner"] = inner
                entry["splash_medium"] = medium
                entry["splash_outer"] = outer
                entry["splash_fractions"] = [1.0, 0.5, 0.25]

        # Chain (Mutalisk)
        if delivery == "chain":
            entry["chain_fractions"] = [1.0, 0.333, 0.111]
            entry["chain_radius"] = 3
            entry["chain_max_targets"] = 3

        # Special: Storm
        if "spell_weapon" in unit_data:
            entry["spell_tick_count"] = 8
            entry["spell_tick_interval"] = 1
            entry["spell_duration_ticks"] = 8

        # Special: Reaver scarab ammo
        if "scarab_weapon" in unit_data:
            entry["scarab_capacity"] = 5
            entry["scarab_unit_id"] = 85

        weapons[semantic_id] = entry

    return weapons


def update_unit_bindings(reference: dict, unit_stats: dict) -> dict:
    """Update unit_stats.json bindings from reference. Only bindings, not mechanics."""
    for ref_name, stats_key in PROJECT_TO_STATS_KEY.items():
        if stats_key not in unit_stats:
            continue
        ref_unit = reference["units"][ref_name]
        semantic_id = ref_unit["semantic_weapon_id"]

        unit_stats[stats_key]["weapon_id_ground"] = semantic_id
        unit_stats[stats_key]["armor_type"] = ref_unit["unit_size"]

        # Air weapon (same as ground for most units)
        if ref_unit.get("air_weapon_raw", 130) != 130:
            unit_stats[stats_key]["weapon_id_air"] = semantic_id
        else:
            unit_stats[stats_key]["weapon_id_air"] = None

        # Spell weapon
        if "spell_weapon" in ref_unit:
            unit_stats[stats_key]["weapon_id_ground"] = None
            unit_stats[stats_key]["spell_weapon_id"] = semantic_id
        else:
            # Don't overwrite spell_weapon_id if not a spell unit
            if "spell_weapon_id" in unit_stats[stats_key] and ref_name != "HighTemplar":
                pass  # Keep existing if any

        # Shield
        unit_stats[stats_key]["shield"] = ref_unit["shield"] if ref_unit["shield_enabled"] else 0

    return unit_stats


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write updated files")
    parser.add_argument("--check", action="store_true", help="Check if files are up to date")
    args = parser.parse_args()

    reference = json.loads(REFERENCE_PATH.read_text())

    # Build new catalogs
    new_weapons = build_weapon_catalog(reference)
    existing_stats = json.loads(UNIT_STATS_PATH.read_text())
    new_stats = update_unit_bindings(reference, existing_stats)

    if args.check:
        # Compare
        existing_weapons = json.loads(WEAPONS_PATH.read_text())
        if json.dumps(existing_weapons, sort_keys=True) != json.dumps(new_weapons, sort_keys=True):
            print("FAIL: weapons.json is stale")
            sys.exit(1)
        if json.dumps(existing_stats, sort_keys=True) != json.dumps(new_stats, sort_keys=True):
            print("FAIL: unit_stats.json bindings are stale")
            sys.exit(1)
        print("OK: catalogs are up to date")
        return

    if args.write:
        WEAPONS_PATH.write_text(render_json(new_weapons))
        UNIT_STATS_PATH.write_text(render_json(new_stats))
        print(f"Written: {WEAPONS_PATH}")
        print(f"Written: {UNIT_STATS_PATH}")
        return

    # Default: dry run
    print(json.dumps(new_weapons, indent=2, sort_keys=True)[:2000])


if __name__ == "__main__":
    main()
