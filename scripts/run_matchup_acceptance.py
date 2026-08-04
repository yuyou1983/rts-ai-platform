#!/usr/bin/env python3
"""Task 11 Step 3: 10 matchup automated acceptance test.

Runs 10 SC1 representative matchups through the production SimCore engine,
recording combat identity, attack actions, projectiles, hit feedback, and
counter results. Outputs a structured QA log.

Usage:
    python3 scripts/run_matchup_acceptance.py
"""
from __future__ import annotations

import json
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simcore.engine import SimCore
from simcore.construction import _build_unit_entity

MATCHUPS = [
    {"id": "marine_vs_zergling", "name": "8 Marine vs 12 Zergling",
     "p1": [("Marine", 8)], "p2": [("Zergling", 12)]},
    {"id": "firebat_vs_zergling", "name": "6 Firebat vs 16 Zergling",
     "p1": [("Firebat", 6)], "p2": [("Zergling", 16)]},
    {"id": "vulture_vs_zealot", "name": "4 Vulture vs 8 Zealot",
     "p1": [("Vulture", 4)], "p2": [("Zealot", 8)]},
    {"id": "tank_vs_dragoon", "name": "3 Tank vs 6 Dragoon",
     "p1": [("Tank", 3)], "p2": [("Dragoon", 6)]},
    {"id": "hydra_vs_dragoon", "name": "8 Hydralisk vs 6 Dragoon",
     "p1": [("Hydralisk", 8)], "p2": [("Dragoon", 6)]},
    {"id": "mutalisk_vs_marine", "name": "6 Mutalisk vs 10 Marine",
     "p1": [("Mutalisk", 6)], "p2": [("Marine", 10)]},
    {"id": "zealot_vs_marine", "name": "8 Zealot vs 12 Marine",
     "p1": [("Zealot", 8)], "p2": [("Marine", 12)]},
    {"id": "dragoon_vs_ultralisk", "name": "6 Dragoon vs 3 Ultralisk",
     "p1": [("Dragoon", 6)], "p2": [("Ultralisk", 3)]},
    {"id": "storm_vs_marine", "name": "2 High Templar Storm vs Marine group",
     "p1": [("HighTemplar", 2)], "p2": [("Marine", 10)],
     "spell": "psionic_storm"},
    {"id": "reaver_vs_zergling", "name": "3 Reaver vs Zergling group",
     "p1": [("Reaver", 3)], "p2": [("Zergling", 15)]},
]


def _spawn_units(state, units_spec, owner, x_offset):
    """Place units in a grid pattern."""
    random.seed(42)
    eid_counter = 0
    for unit_type, count in units_spec:
        for _ in range(count):
            eid = f"p{owner}u{eid_counter}"
            col = eid_counter % 5
            row = eid_counter // 5
            x = x_offset + col * 1.5
            y = 10.0 + row * 2.0
            e = _build_unit_entity(eid, unit_type, owner, "soldier", x, y)
            e["is_idle"] = True
            e["attack_ground"] = 1
            e["cooldown_timer"] = 99
            # High Templar needs spellcaster stats
            if unit_type == "HighTemplar":
                e["is_spellcaster"] = True
                e["energy"] = 75
                e["mp"] = 75
            state.entities[eid] = e
            eid_counter += 1


def _add_bases(state):
    for owner in (1, 2):
        bid = f"base_p{owner}"
        state.entities[bid] = {
            "id": bid, "owner": owner, "entity_type": "building",
            "building_type": "base", "pos_x": float(1 if owner == 1 else 53),
            "pos_y": 30.0, "health": 1500, "max_health": 1500,
            "shield": 0, "max_shield": 0, "is_idle": True,
            "attack_ground": 0, "cooldown_timer": 0,
        }


def run_matchup(matchup, max_ticks=200):
    """Run one matchup, return result dict."""
    engine = SimCore()
    engine.initialize(map_seed=42)
    state = engine._state
    _add_bases(state)

    _spawn_units(state, matchup["p1"], 1, 8.0)
    _spawn_units(state, matchup["p2"], 2, 14.0)

    total_events = 0
    event_types = set()
    weapon_ids = set()
    p1_deaths = 0
    p2_deaths = 0

    for tick in range(1, max_ticks + 1):
        engine.step([])
        events = engine.combat_events_this_tick
        total_events += len(events)

        for ev in events:
            et = ev.get("event_type", "")
            event_types.add(et)
            wid = ev.get("weapon_id", "")
            if wid:
                weapon_ids.add(wid)
            if et == "unit_destroyed":
                tid = ev.get("target_id", "")
                if tid.startswith("p1"):
                    p1_deaths += 1
                elif tid.startswith("p2"):
                    p2_deaths += 1

        if engine._state.is_terminal:
            break

    p1_alive = sum(1 for e in state.entities.values()
                   if e.get("owner") == 1 and e.get("entity_type") == "soldier"
                   and e.get("health", 0) > 0)
    p2_alive = sum(1 for e in state.entities.values()
                   if e.get("owner") == 2 and e.get("entity_type") == "soldier"
                   and e.get("health", 0) > 0)

    # Score: identity(1-5), attack action(1-5), projectile(1-5), hit feedback(1-5), readability(1-5)
    # Automated scoring: check if events contain expected types
    has_attack = "attack_started" in event_types
    has_impact = "impact_resolved" in event_types
    has_destroyed = "unit_destroyed" in event_types

    identity_score = 5 if weapon_ids else 1
    attack_score = 5 if has_attack else 1
    projectile_score = 5 if has_impact else 1
    hit_score = 5 if has_impact else 1
    # Readability is a visual metric — cannot be assessed headless.
    # Mark as PENDING (not scored) for human evaluation in Godot Test Mode.
    readability_score = None  # PENDING human eval

    automated_scores = [identity_score, attack_score, projectile_score, hit_score]
    all_pass = all(s >= 4 for s in automated_scores)

    return {
        "id": matchup["id"],
        "name": matchup["name"],
        "ticks": tick,
        "total_events": total_events,
        "event_types": sorted(event_types),
        "weapon_ids": sorted(weapon_ids),
        "p1_deaths": p1_deaths,
        "p2_deaths": p2_deaths,
        "p1_alive": p1_alive,
        "p2_alive": p2_alive,
        "scores": {
            "identity": identity_score,
            "attack_action": attack_score,
            "projectile": projectile_score,
            "hit_feedback": hit_score,
            "readability": readability_score,
        },
        "gate": "PASS" if all_pass else "CONCERNS",
    }


def main():
    results = []
    for m in MATCHUPS:
        print(f"Running: {m['name']}...", end=" ", flush=True)
        r = run_matchup(m)
        results.append(r)
        print(f"{r['gate']} ({r['total_events']} events, "
              f"P1:{r['p1_alive']}alive/{r['p1_deaths']}dead, "
              f"P2:{r['p2_alive']}alive/{r['p2_deaths']}dead)")

    print("\n=== Matchup Acceptance Summary ===")
    all_pass = True
    for r in results:
        scores = r["scores"]
        print(f"  {r['name']}: {r['gate']} "
              f"(id:{scores['identity']} atk:{scores['attack_action']} "
              f"proj:{scores['projectile']} hit:{scores['hit_feedback']} "
              f"read:{scores['readability']})")
        if r["gate"] != "PASS":
            all_pass = False

    gate = "G7 PASS" if all_pass else "G7 CONCERNS"
    print(f"\nFinal Gate: {gate}")

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "reports",
                            "matchup_acceptance_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"gate": gate, "results": results}, f, indent=2)
    print(f"Results saved to: {out_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
