#!/usr/bin/env python3
"""Terran vs Zerg simulation — 3 games headless."""
from __future__ import annotations
import time, sys
sys.path.insert(0, ".")

from simcore.engine import SimCore
from agents.script_ai import ScriptAI


def run_tvz(game_id: int, seed: int, max_ticks: int = 5000):
    engine = SimCore(max_ticks=max_ticks, tick_rate=10.0)
    engine.initialize(map_seed=seed, config={
        "map_size": 64,
        "max_ticks": max_ticks,
        "player_races": {1: "terran", 2: "zerg"},
    })
    engine._player_races = {1: "terran", 2: "zerg"}

    ai1 = ScriptAI(player_id=1)
    ai2 = ScriptAI(player_id=2)
    tick = 0

    t0 = time.monotonic()
    while tick < max_ticks and not engine.state.is_terminal:
        obs = engine.state.get_observations()
        obs1 = obs[0] if obs else {}
        obs2 = obs[1] if len(obs) > 1 else {}

        result1 = ai1.decide(obs1)
        result2 = ai2.decide(obs2)

        cmds1 = result1.get("commands", []) if isinstance(result1, dict) else []
        cmds2 = result2.get("commands", []) if isinstance(result2, dict) else []

        for cmd in cmds1:
            cmd["issuer"] = 1
        for cmd in cmds2:
            cmd["issuer"] = 2

        engine.step(cmds1 + cmds2)
        tick += 1

    elapsed = time.monotonic() - t0
    tps = tick / max(elapsed, 1e-9)

    # ── 统计 ──
    ents = engine.state.entities
    p1_units = sum(1 for e in ents.values()
                   if e.get("owner") == 1 and e.get("entity_type") != "building")
    p2_units = sum(1 for e in ents.values()
                   if e.get("owner") == 2 and e.get("entity_type") != "building")
    p1_bldg = sum(1 for e in ents.values()
                  if e.get("owner") == 1 and e.get("entity_type") == "building")
    p2_bldg = sum(1 for e in ents.values()
                  if e.get("owner") == 2 and e.get("entity_type") == "building")

    res = engine.state.resources
    p1_min = res.get("p1_mineral", 0)
    p2_min = res.get("p2_mineral", 0)

    winner = engine.state.winner
    winner_str = {0: "⏳ Draw (max ticks)", 1: "🏆 Terran WIN", 2: "🏆 Zerg WIN"}.get(winner, f"P{winner}")

    return {
        "game": game_id, "seed": seed,
        "winner": winner_str, "winner_id": winner,
        "ticks": tick, "tps": round(tps, 1), "elapsed": round(elapsed, 2),
        "terran": {"units": p1_units, "buildings": p1_bldg, "mineral": int(p1_min)},
        "zerg":   {"units": p2_units, "buildings": p2_bldg, "mineral": int(p2_min)},
    }


if __name__ == "__main__":
    configs = [(1, 42), (2, 77), (3, 123)]

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       ⚔️  TERRAN vs ZERG — Headless Battle Sim        ║")
    print("╚══════════════════════════════════════════════════════════╝")

    results = []
    for gid, seed in configs:
        r = run_tvz(gid, seed, max_ticks=5000)
        results.append(r)

        t = r["terran"]
        z = r["zerg"]
        print(f"\n┌─── Game {r['game']} (seed={r['seed']}) ────────────────────┐")
        print(f"│  Result:  {r['winner']}")
        print(f"│  Ticks:   {r['ticks']}  |  TPS: {r['tps']}  |  {r['elapsed']}s")
        print(f"│")
        print(f"│  🏰 Terran  {t['units']:3d} units  {t['buildings']:2d} bldgs  {t['mineral']:5d} min")
        print(f"│  🪺 Zerg    {z['units']:3d} units  {z['buildings']:2d} bldgs  {z['mineral']:5d} min")
        print(f"└──────────────────────────────────────────────┘")

    # ── 汇总 ──
    tw = sum(1 for r in results if r["winner_id"] == 1)
    zw = sum(1 for r in results if r["winner_id"] == 2)
    dr = sum(1 for r in results if r["winner_id"] == 0)
    avg_t = sum(r["ticks"] for r in results) / len(results)
    avg_s = sum(r["tps"] for r in results) / len(results)

    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"║  📊 TOTAL:  Terran {tw} — Zerg {zw} — Draw {dr}             ║")
    print(f"║  Avg ticks: {avg_t:.0f}  |  Avg TPS: {avg_s:.1f}                   ║")
    print(f"╚══════════════════════════════════════════════════════════╝")
    print()