#!/usr/bin/env python3
"""Combat simulation: pit unit compositions against each other head-to-head.

Usage:
    python scripts/combat_sim.py
    python scripts/combat_sim.py --matchups Marine:Zergling Tank:Hydralisk
    python scripts/combat_sim.py --count 10  # 10 of each unit per side
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simcore.engine import SimCore
from simcore.rules import resolve_combat


# ─── Unit catalog (name → stats) ──────────────────────────────────────────
UNIT_CATALOG: dict[str, dict] = {
    # Terran
    "SCV":        {"health": 60,  "max_health": 60,  "speed": 2.5, "attack": 5,  "attack_range": 1.5, "armor": 0, "armor_type": "medium"},
    "Marine":     {"health": 40,  "max_health": 40,  "speed": 3.0, "attack": 6,  "attack_range": 5.0, "armor": 0, "armor_type": "small"},
    "Firebat":    {"health": 50,  "max_health": 50,  "speed": 3.0, "attack": 16, "attack_range": 1.5, "armor": 1, "armor_type": "medium"},
    "Ghost":      {"health": 45,  "max_health": 45,  "speed": 3.0, "attack": 10, "attack_range": 8.0, "armor": 0, "armor_type": "small"},
    "Medic":      {"health": 60,  "max_health": 60,  "speed": 3.0, "attack": 0,  "attack_range": 0,   "armor": 1, "armor_type": "small"},
    "Vulture":    {"health": 80,  "max_health": 80,  "speed": 5.0, "attack": 20, "attack_range": 5.0, "armor": 0, "armor_type": "medium"},
    "Tank":       {"health": 150, "max_health": 150, "speed": 2.5, "attack": 30, "attack_range": 10.0,"armor": 1, "armor_type": "large"},
    "Goliath":    {"health": 125, "max_health": 125, "speed": 3.0, "attack": 12, "attack_range": 7.0, "armor": 1, "armor_type": "large"},
    "Wraith":     {"health": 120, "max_health": 120, "speed": 5.0, "attack": 8,  "attack_range": 6.0, "armor": 0, "armor_type": "large"},
    "BattleCruiser":{"health":500,"max_health":500,  "speed": 2.0, "attack": 25, "attack_range": 6.0, "armor": 3, "armor_type": "large"},
    # Zerg
    "Drone":      {"health": 40,  "max_health": 40,  "speed": 2.5, "attack": 5,  "attack_range": 1.5, "armor": 0, "armor_type": "medium"},
    "Zergling":   {"health": 40,  "max_health": 40,  "speed": 4.0, "attack": 7,  "attack_range": 1.5, "armor": 0, "armor_type": "small"},
    "Hydralisk":  {"health": 80,  "max_health": 80,  "speed": 3.0, "attack": 15, "attack_range": 6.0, "armor": 0, "armor_type": "medium"},
    "Lurker":     {"health": 125, "max_health": 125, "speed": 2.5, "attack": 20, "attack_range": 8.0, "armor": 1, "armor_type": "large"},
    "Ultralisk":  {"health": 400, "max_health": 400, "speed": 2.5, "attack": 40, "attack_range": 1.5, "armor": 2, "armor_type": "large"},
    "Mutalisk":   {"health": 120, "max_health": 120, "speed": 5.0, "attack": 9,  "attack_range": 3.0, "armor": 0, "armor_type": "small"},
    "Queen":      {"health": 120, "max_health": 120, "speed": 5.0, "attack": 0,  "attack_range": 0,   "armor": 0, "armor_type": "medium"},
    "Defiler":    {"health": 80,  "max_health": 80,  "speed": 3.0, "attack": 0,  "attack_range": 0,   "armor": 1, "armor_type": "medium"},
    "Scourge":    {"health": 25,  "max_health": 25,  "speed": 7.0, "attack":110, "attack_range": 1.0, "armor": 0, "armor_type": "small"},
}


def spawn_units(side: int, unit_name: str, count: int, start_x: float, start_y: float, spacing: float = 2.0) -> dict:
    """Spawn a squad of units on one side of the arena."""
    stats = UNIT_CATALOG[unit_name]
    entities = {}
    for i in range(count):
        row = i // 5
        col = i % 5
        eid = f"{unit_name}_{side}_{i}"
        etype = "worker" if unit_name in ("SCV", "Drone", "Probe") else "soldier"
        if stats["attack_range"] >= 5.0 and unit_name not in ("SCV", "Drone", "Marine"):
            etype = "scout"
        entities[eid] = {
            "id": eid,
            "owner": side,
            "entity_type": etype,
            "unit_type": unit_name,
            "pos_x": start_x + col * spacing,
            "pos_y": start_y + row * spacing,
            "is_idle": True,
            "attack_target_id": "",
            "weapon_type": "normal",
            **stats,
        }
    return entities


def run_combat_sim(p1_unit: str, p2_unit: str, count: int = 5, max_ticks: int = 300) -> dict:
    """Run a single combat sim between two unit types. Returns result dict."""
    # Spawn P1 on left, P2 on right
    entities = {}
    entities.update(spawn_units(1, p1_unit, count, start_x=10.0, start_y=10.0))
    entities.update(spawn_units(2, p2_unit, count, start_x=40.0, start_y=10.0))

    # Issue attack commands: every unit targets nearest enemy
    commands = []
    p1_ids = [eid for eid in entities if entities[eid]["owner"] == 1]
    p2_ids = [eid for eid in entities if entities[eid]["owner"] == 2]

    for eid in p1_ids:
        # Find nearest P2 unit
        e = entities[eid]
        nearest = min(p2_ids, key=lambda tid: math.hypot(
            e["pos_x"] - entities[tid]["pos_x"],
            e["pos_y"] - entities[tid]["pos_y"],
        ))
        commands.append({"action": "attack", "attacker_id": eid, "target_id": nearest, "issuer": 1})

    for eid in p2_ids:
        e = entities[eid]
        nearest = min(p1_ids, key=lambda tid: math.hypot(
            e["pos_x"] - entities[tid]["pos_x"],
            e["pos_y"] - entities[tid]["pos_y"],
        ))
        commands.append({"action": "attack", "attacker_id": eid, "target_id": nearest, "issuer": 2})

    resources = {"p1_mineral": 0, "p2_mineral": 0, "p1_gas": 0, "p2_gas": 0}
    kill_log: list[str] = []

    tick = 0
    while tick < max_ticks:
        entities, resources = resolve_combat(entities, resources, commands, tick)

        # Check for dead and log
        dead = [eid for eid, e in entities.items() if e.get("health", 0) <= 0]
        for eid in dead:
            kill_log.append(f"  T{tick:3d}: {eid} destroyed")

        # Move surviving units toward their targets
        for eid, e in list(entities.items()):
            if e.get("health", 0) <= 0:
                continue
            tid = e.get("attack_target_id", "")
            if tid and tid in entities and entities[tid].get("health", 0) > 0:
                target = entities[tid]
                dx = target["pos_x"] - e["pos_x"]
                dy = target["pos_y"] - e["pos_y"]
                dist = math.hypot(dx, dy)
                if dist > e.get("attack_range", 6.0):
                    speed = e.get("speed", 3.0)
                    step = min(speed, dist)
                    entities[eid] = {**e,
                        "pos_x": e["pos_x"] + dx / dist * step,
                        "pos_y": e["pos_y"] + dy / dist * step,
                    }
            elif not tid or (tid in entities and entities[tid].get("health", 0) <= 0):
                # Retarget
                enemies = [x for x in entities
                           if entities[x].get("owner") != e["owner"]
                           and entities[x].get("owner", 0) != 0
                           and entities[x].get("health", 0) > 0
                           and entities[x].get("entity_type") != "resource"]
                if enemies:
                    nearest = min(enemies, key=lambda x: math.hypot(
                        e["pos_x"] - entities[x]["pos_x"],
                        e["pos_y"] - entities[x]["pos_y"],
                    ))
                    commands.append({"action": "attack", "attacker_id": eid, "target_id": nearest, "issuer": e["owner"]})
                    entities[eid] = {**e, "attack_target_id": nearest, "is_idle": False}

        # Remove dead
        entities = {eid: e for eid, e in entities.items() if e.get("health", 0) > 0}

        # Check victory
        p1_alive = any(e["owner"] == 1 for e in entities.values())
        p2_alive = any(e["owner"] == 2 for e in entities.values())

        if not p1_alive and not p2_alive:
            return {"winner": "draw", "ticks": tick, "p1_unit": p1_unit, "p2_unit": p2_unit,
                    "p1_remaining": 0, "p2_remaining": 0, "kills": kill_log}
        elif not p1_alive:
            p2_left = sum(1 for e in entities.values() if e["owner"] == 2)
            return {"winner": 2, "ticks": tick, "p1_unit": p1_unit, "p2_unit": p2_unit,
                    "p1_remaining": 0, "p2_remaining": p2_left, "kills": kill_log}
        elif not p2_alive:
            p1_left = sum(1 for e in entities.values() if e["owner"] == 1)
            return {"winner": 1, "ticks": tick, "p1_unit": p1_unit, "p2_unit": p2_unit,
                    "p1_remaining": p1_left, "p2_remaining": 0, "kills": kill_log}

        tick += 1

    # Timeout — count remaining HP
    p1_hp = sum(e["health"] for e in entities.values() if e["owner"] == 1)
    p2_hp = sum(e["health"] for e in entities.values() if e["owner"] == 2)
    p1_left = sum(1 for e in entities.values() if e["owner"] == 1)
    p2_left = sum(1 for e in entities.values() if e["owner"] == 2)
    if p1_hp > p2_hp:
        winner = 1
    elif p2_hp > p1_hp:
        winner = 2
    else:
        winner = "draw"
    return {"winner": winner, "ticks": tick, "p1_unit": p1_unit, "p2_unit": p2_unit,
            "p1_remaining": p1_left, "p2_remaining": p2_left, "kills": kill_log}


# ─── Default matchup table ────────────────────────────────────────────────
DEFAULT_MATCHUPS = [
    ("Marine",        "Zergling"),
    ("Marine",        "Hydralisk"),
    ("Firebat",       "Zergling"),
    ("Firebat",       "Hydralisk"),
    ("Tank",          "Hydralisk"),
    ("Tank",          "Ultralisk"),
    ("Goliath",       "Mutalisk"),
    ("Vulture",       "Hydralisk"),
    ("BattleCruiser", "Ultralisk"),
    ("BattleCruiser", "Mutalisk"),
    ("Ghost",         "Hydralisk"),
    ("Marine",        "Mutalisk"),
    ("Ultralisk",     "Goliath"),
    ("Ultralisk",     "Tank"),
]


def print_banner():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          ⚔️  RTS-AI 兵种对战模拟器  ⚔️                        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def print_result(r: dict, verbose: bool = False):
    w = r["winner"]
    if w == 1:
        wstr = f"🏆 P1 {r['p1_unit']} WIN"
    elif w == 2:
        wstr = f"🏆 P2 {r['p2_unit']} WIN"
    else:
        wstr = "🤝 DRAW"

    print(f"  {r['p1_unit']:>15s}  vs  {r['p2_unit']:<15s}  │  {wstr}  │  T={r['ticks']:3d}  │  "
          f"剩余 P1:{r['p1_remaining']}  P2:{r['p2_remaining']}")

    if verbose and r["kills"]:
        for k in r["kills"][:20]:
            print(k)
        if len(r["kills"]) > 20:
            print(f"  ... 还有 {len(r['kills'])-20} 条击杀记录")


def main():
    parser = argparse.ArgumentParser(description="RTS-AI 兵种对战模拟")
    parser.add_argument("--matchups", nargs="+", help="对战组合 P1:P2 (如 Marine:Zergling)")
    parser.add_argument("--count", type=int, default=5, help="每方兵种数量 (默认5)")
    parser.add_argument("--max-ticks", type=int, default=300, help="最大tick数 (默认300)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细击杀日志")
    args = parser.parse_args()

    if args.matchups:
        matchups = []
        for m in args.matchups:
            parts = m.split(":")
            if len(parts) == 2 and parts[0] in UNIT_CATALOG and parts[1] in UNIT_CATALOG:
                matchups.append((parts[0], parts[1]))
            else:
                print(f"⚠️  无效对战: {m}  (可用兵种: {', '.join(UNIT_CATALOG.keys())})")
                sys.exit(1)
    else:
        matchups = DEFAULT_MATCHUPS

    print_banner()
    print(f"  每方数量: {args.count}   最大回合: {args.max_ticks}")
    print(f"  对战场次: {len(matchups)}")
    print()
    print("  ┌─────────────────────────────────────────────────────────────────────────────┐")

    p1_wins = 0
    p2_wins = 0
    draws = 0

    for p1, p2 in matchups:
        r = run_combat_sim(p1, p2, count=args.count, max_ticks=args.max_ticks)
        print_result(r, verbose=args.verbose)
        if r["winner"] == 1:
            p1_wins += 1
        elif r["winner"] == 2:
            p2_wins += 1
        else:
            draws += 1

    print("  └─────────────────────────────────────────────────────────────────────────────┘")
    print()
    print(f"  📊 总战绩: P1胜 {p1_wins}  │  P2胜 {p2_wins}  │  平局 {draws}")
    print()


if __name__ == "__main__":
    main()