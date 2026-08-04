#!/usr/bin/env python3
"""Generate SC1 combat fixtures for Godot Test Mode (Task 9 Step 2).

Uses the production SimCore engine to create deterministic combat event
sequences.  Godot Test Mode consumes these fixtures instead of running
its own (now-removed) damage formula.

Usage:
    python3 scripts/generate_sc1_combat_fixtures.py --write   # write fixtures
    python3 scripts/generate_sc1_combat_fixtures.py --check   # verify freshness
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simcore.engine import SimCore
from simcore.construction import _build_unit_entity
from simcore.state import GameState

OUTPUT_PATH = ROOT / "godot" / "resources" / "test" / "sc1_combat_presets.json"

GENERATOR_VERSION = 1

# ── Preset definitions ───────────────────────────────────────

PRESETS = [
    {
        "id": "marine_vs_zergling",
        "attacker": "Marine",
        "targets": ["Zergling"],
        "setup": [
            {"unit_type": "Marine", "owner": 1, "pos": (4.0, 4.0), "target": "Zergling"},
            {"unit_type": "Zergling", "owner": 2, "pos": (7.0, 4.0)},
        ],
        "ticks": 20,
    },
    {
        "id": "firebat_vs_zergling",
        "attacker": "Firebat",
        "targets": ["Zergling"],
        "setup": [
            {"unit_type": "Firebat", "owner": 1, "pos": (4.0, 4.0), "target": "Zergling"},
            {"unit_type": "Zergling", "owner": 2, "pos": (6.0, 4.0)},
        ],
        "ticks": 20,
    },
    {
        "id": "vulture_vs_zealot",
        "attacker": "Vulture",
        "targets": ["Zealot"],
        "setup": [
            {"unit_type": "Vulture", "owner": 1, "pos": (4.0, 4.0), "target": "Zealot"},
            {"unit_type": "Zealot", "owner": 2, "pos": (8.0, 4.0)},
        ],
        "ticks": 20,
    },
    {
        "id": "tank_vs_dragoon",
        "attacker": "Tank",
        "targets": ["Dragoon"],
        "setup": [
            {"unit_type": "Tank", "owner": 1, "pos": (4.0, 4.0), "target": "Dragoon"},
            {"unit_type": "Dragoon", "owner": 2, "pos": (9.0, 4.0)},
        ],
        "ticks": 25,
    },
    {
        "id": "hydralisk_vs_dragoon",
        "attacker": "Hydralisk",
        "targets": ["Dragoon"],
        "setup": [
            {"unit_type": "Hydralisk", "owner": 1, "pos": (4.0, 4.0), "target": "Dragoon"},
            {"unit_type": "Dragoon", "owner": 2, "pos": (8.0, 4.0)},
        ],
        "ticks": 25,
    },
    {
        "id": "mutalisk_vs_marine",
        "attacker": "Mutalisk",
        "targets": ["Marine"],
        "setup": [
            {"unit_type": "Mutalisk", "owner": 1, "pos": (4.0, 4.0), "target": "Marine"},
            {"unit_type": "Marine", "owner": 2, "pos": (7.0, 4.0)},
            {"unit_type": "Marine", "owner": 2, "pos": (8.0, 4.0)},
            {"unit_type": "Marine", "owner": 2, "pos": (7.5, 5.0)},
        ],
        "ticks": 25,
    },
    {
        "id": "zealot_vs_marine",
        "attacker": "Zealot",
        "targets": ["Marine"],
        "setup": [
            {"unit_type": "Zealot", "owner": 1, "pos": (4.0, 4.0), "target": "Marine"},
            {"unit_type": "Marine", "owner": 2, "pos": (5.0, 4.0)},
        ],
        "ticks": 20,
    },
    {
        "id": "dragoon_vs_ultralisk",
        "attacker": "Dragoon",
        "targets": ["Ultralisk"],
        "setup": [
            {"unit_type": "Dragoon", "owner": 1, "pos": (4.0, 4.0), "target": "Ultralisk"},
            {"unit_type": "Ultralisk", "owner": 2, "pos": (8.0, 4.0)},
        ],
        "ticks": 30,
    },
    {
        "id": "storm_vs_marine_group",
        "attacker": "High Templar",
        "targets": ["Marine"],
        "setup": [
            {"unit_type": "HighTemplar", "owner": 1, "pos": (4.0, 4.0),
             "spell": "psionicstorm", "target_pos": (7.0, 4.0)},
            {"unit_type": "Marine", "owner": 2, "pos": (7.0, 4.0)},
            {"unit_type": "Marine", "owner": 2, "pos": (7.5, 4.0)},
            {"unit_type": "Marine", "owner": 2, "pos": (7.0, 4.5)},
        ],
        "ticks": 15,
    },
    {
        "id": "reaver_vs_zergling_group",
        "attacker": "Reaver",
        "targets": ["Zergling"],
        "setup": [
            {"unit_type": "Reaver", "owner": 1, "pos": (4.0, 4.0), "target": "Zergling"},
            {"unit_type": "Zergling", "owner": 2, "pos": (9.0, 4.0)},
            {"unit_type": "Zergling", "owner": 2, "pos": (9.5, 4.0)},
            {"unit_type": "Zergling", "owner": 2, "pos": (9.0, 4.5)},
        ],
        "ticks": 25,
    },
]


def _build_entity(spec: dict, eid: str) -> dict:
    """Build a production unit entity using _build_unit_entity."""
    unit_type = spec["unit_type"]
    owner = spec["owner"]
    pos = spec["pos"]
    # Map unit_type to simplified_etype
    if unit_type in ("Vulture", "Mutalisk", "Wraith", "Scout"):
        etype = "scout"
    else:
        etype = "soldier"
    entity = _build_unit_entity(eid, unit_type, owner, etype, pos[0], pos[1])
    # Set cooldown high so first tick fires immediately
    entity["cooldown_timer"] = 99
    entity["cooldown_ground"] = 15
    entity["cooldown_air"] = 15
    # Spellcasters need is_spellcaster=True and energy for spells
    if "spell" in spec:
        entity["is_spellcaster"] = True
        entity["energy"] = 75
        entity["mp"] = 75
    if "target" in spec:
        entity["attack_target_id"] = spec["target"]
    else:
        entity["is_idle"] = True
    return entity


def _run_preset(preset: dict) -> dict:
    """Run one preset through SimCore and collect combat events."""
    engine = SimCore()
    engine.initialize(map_seed=42, config={"player_races": {1: "protoss", 2: "zerg"}})

    # Build entities directly (bypassing full economy)
    entities = {}
    # Add base buildings so check_terminal doesn't end the game
    entities["base_p1"] = {
        "id": "base_p1", "owner": 1, "entity_type": "building",
        "building_type": "base", "pos_x": 20.0, "pos_y": 20.0,
        "health": 1500, "max_health": 1500, "shields": 0,
        "is_constructing": False,
    }
    entities["base_p2"] = {
        "id": "base_p2", "owner": 2, "entity_type": "building",
        "building_type": "base", "pos_x": 40.0, "pos_y": 40.0,
        "health": 1500, "max_health": 1500, "shields": 0,
        "is_constructing": False,
    }
    eid_counter = 0
    entity_id_map = {}

    for spec in preset["setup"]:
        eid_counter += 1
        eid = f"u{eid_counter}"
        entity_id_map[(spec["unit_type"], spec["owner"], spec["pos"])] = eid
        # Map target references
        if "target" in spec:
            # Find target entity
            for t_spec in preset["setup"]:
                if t_spec["unit_type"] == spec["target"].split("_")[0] or t_spec.get("id") == spec["target"]:
                    pass  # target will be resolved below
        entities[eid] = _build_entity(spec, eid)

    # Resolve target references
    for spec in preset["setup"]:
        eid_counter2 = 0
        for s2 in preset["setup"]:
            eid_counter2 += 1
            if s2 is spec:
                break
        eid = f"u{eid_counter2}"
        if "target" in spec:
            # Find the target by matching unit_type
            target_type = spec["target"]
            t_counter = 0
            for s2 in preset["setup"]:
                t_counter += 1
                if s2["unit_type"] == target_type and s2["owner"] != spec["owner"]:
                    entities[eid]["attack_target_id"] = f"u{t_counter}"
                    entities[eid]["is_idle"] = False
                    break

    # Build commands (attack or spell)
    commands = []
    for spec in preset["setup"]:
        eid_counter2 = 0
        for s2 in preset["setup"]:
            eid_counter2 += 1
            if s2 is spec:
                break
        eid = f"u{eid_counter2}"

        if "spell" in spec:
            commands.append({
                "action": "spell",
                "unit_id": eid,
                "caster_id": eid,
                "spell": spec["spell"],
                "target_x": spec["target_pos"][0],
                "target_y": spec["target_pos"][1],
                "issuer": spec["owner"],
            })
        elif "target" in spec:
            commands.append({
                "action": "attack",
                "attacker_id": eid,
                "target_id": entities[eid]["attack_target_id"],
                "issuer": spec["owner"],
                "unit_id": eid,
            })

    # Inject custom entities into engine state (bypassing full economy)
    state = engine._state
    races = {}
    for spec in preset["setup"]:
        r = "terran"
        if spec["unit_type"] in ("Zealot", "Dragoon", "HighTemplar", "Reaver", "Scout", "Corsair", "Arbiter", "Carrier"):
            r = "protoss"
        elif spec["unit_type"] in ("Zergling", "Hydralisk", "Mutalisk", "Ultralisk", "Defiler", "Queen", "Scourge", "Overlord"):
            r = "zerg"
        races[spec["owner"]] = r
    # Fallback: ensure both players have a race
    races.setdefault(1, "terran")
    races.setdefault(2, "zerg")
    engine._state = GameState(
        tick=state.tick, entities=entities, fog_of_war=state.fog_of_war,
        resources={"p1_mineral": 5000, "p2_mineral": 5000, "p1_supply": 100, "p2_supply": 100},
        is_terminal=False, winner=0, height_map=state.height_map,
        map_width=state.map_width, map_height=state.map_height,
        player_races=races, elevation_grid=state.elevation_grid,
    )
    engine._replay = [engine._state.to_snapshot()]

    # Run ticks
    all_events = []
    # First tick with commands
    state = engine.step(commands)
    all_events.extend(engine.combat_events_this_tick)

    # Subsequent ticks with no commands (let projectiles/spells advance)
    for _ in range(preset["ticks"] - 1):
        state = engine.step([])
        all_events.extend(engine.combat_events_this_tick)

    # Collect final state
    final_entities = {}
    for eid, e in state.entities.items():
        if e.get("entity_type") in ("unit", "building"):
            final_entities[eid] = {
                "id": eid,
                "unit_type": e.get("unit_type", ""),
                "owner": e.get("owner", 0),
                "health": round(e.get("health", 0), 2),
                "shields": round(e.get("shields", 0), 2),
                "pos_x": e.get("pos_x", 0),
                "pos_y": e.get("pos_y", 0),
            }

    return {
        "id": preset["id"],
        "attacker": preset["attacker"],
        "targets": preset["targets"],
        "initial_entities": [
            {
                "id": f"u{i+1}",
                "unit_type": s["unit_type"],
                "owner": s["owner"],
                "pos_x": s["pos"][0],
                "pos_y": s["pos"][1],
            }
            for i, s in enumerate(preset["setup"])
        ],
        "commands": commands,
        "ticks": preset["ticks"],
        "combat_events": all_events,
        "final_entities": final_entities,
    }


def _compute_source_hash() -> str:
    """Hash key source files to detect drift."""
    files = [
        "simcore/rules.py",
        "simcore/combat_resolution.py",
        "simcore/combat_catalog.py",
        "simcore/projectile.py",
        "simcore/spells.py",
        "simcore/engine.py",
        "data/combat/weapons.json",
        "simcore/data/unit_stats.json",
    ]
    h = hashlib.sha256()
    for fpath in files:
        p = ROOT / fpath
        if p.exists():
            h.update(p.read_bytes())
            h.update(b"\x00")
    return h.hexdigest()


def generate_fixtures() -> dict:
    """Generate all combat fixtures."""
    presets = []
    for preset_def in PRESETS:
        try:
            result = _run_preset(preset_def)
            presets.append(result)
        except Exception as e:
            presets.append({
                "id": preset_def["id"],
                "error": str(e),
                "attacker": preset_def["attacker"],
                "targets": preset_def["targets"],
            })

    return {
        "meta": {
            "source_reference_sha256": _compute_source_hash(),
            "generator_version": GENERATOR_VERSION,
        },
        "presets": presets,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate SC1 combat fixtures")
    parser.add_argument("--write", action="store_true", help="Write fixtures to file")
    parser.add_argument("--check", action="store_true", help="Verify fixture freshness")
    args = parser.parse_args()

    if not args.write and not args.check:
        parser.print_help()
        return 1

    fixtures = generate_fixtures()

    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w") as f:
            json.dump(fixtures, f, indent=2, sort_keys=True)
        print(f"Written: {OUTPUT_PATH}")
        print(f"Presets: {len(fixtures['presets'])}")
        print(f"Source hash: {fixtures['meta']['source_reference_sha256'][:16]}...")

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"ERROR: {OUTPUT_PATH} does not exist. Run --write first.")
            return 1
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
        # Regenerate and compare
        fresh = generate_fixtures()
        if json.dumps(existing, sort_keys=True) != json.dumps(fresh, sort_keys=True):
            print("STALE: Fixtures are out of date. Run --write to regenerate.")
            # Show what changed
            if existing.get("meta", {}).get("source_reference_sha256") != fresh.get("meta", {}).get("source_reference_sha256"):
                print(f"  Source hash changed: {existing.get('meta', {}).get('source_reference_sha256', '?')[:16]} → {fresh.get('meta', {}).get('source_reference_sha256', '?')[:16]}")
            return 1
        else:
            print("FRESH: Fixtures are up to date.")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
