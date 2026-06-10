#!/usr/bin/env python3
"""平衡性模拟 — 10局三族 round-robin 对战。

用法: PYTHONPATH=. python3 scripts/balance_sim_10.py

种族组合: TvT×2, TvZ×2, TvP×2, ZvZ×1, ZvP×2, PvP×1 = 10局
AI: ScriptAI(medium) vs ScriptAI(medium)
输出: 胜率表 + 资源/兵力/时长统计 → harness/output/balance_sim_10.json
"""
from __future__ import annotations
import sys, json, time
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simcore.engine import SimCore
from agents.script_ai import ScriptAI

# ─── 配置 ───────────────────────────────────────────────────────────────────────
MATCHUPS = [
    ("terran", "terran"),
    ("terran", "zerg"),
    ("terran", "protoss"),
    ("zerg", "zerg"),
    ("zerg", "protoss"),
    ("protoss", "protoss"),
]
MAX_TICKS = 3000
SEED_BASE = 42
DIFFICULTY = "hard"  # hard 更积极攻击，更容易出胜负


def run_one(race1: str, race2: str, seed: int) -> dict:
    engine = SimCore()
    engine.initialize(map_seed=seed)

    # 手动覆盖种族（engine.initialize 默认 terran/terran）
    # 通过重新初始化状态中的 race 实现
    # 若 engine 支持 player_races config 则用 config
    try:
        engine.initialize(map_seed=seed, config={"player_races": {1: race1, 2: race2}, "max_ticks": MAX_TICKS})
    except TypeError:
        engine.initialize(map_seed=seed)
        engine._max_ticks = MAX_TICKS

    ai1 = ScriptAI(player_id=1, difficulty=DIFFICULTY)
    ai2 = ScriptAI(player_id=2, difficulty=DIFFICULTY)

    t0 = time.time()
    tick = 0
    while tick < MAX_TICKS and not engine._state.is_terminal:
        obs = engine._state.get_observations()
        cmd1 = ai1.decide(obs[0]).get("commands", [])
        cmd2 = ai2.decide(obs[1]).get("commands", [])
        engine.step(cmd1 + cmd2)
        tick += 1

    elapsed = time.time() - t0
    state = engine._state

    # 统计实体
    ents = state.entities
    p1_units = [e for e in ents.values() if e.get("owner") == 1 and e.get("entity_type") != "building"]
    p2_units = [e for e in ents.values() if e.get("owner") == 2 and e.get("entity_type") != "building"]
    p1_blds = [e for e in ents.values() if e.get("owner") == 1 and e.get("entity_type") == "building"]
    p2_blds = [e for e in ents.values() if e.get("owner") == 2 and e.get("entity_type") == "building"]

    base_types = ("CommandCenter", "Hatchery", "Nexus")
    p1_base = any(b.get("unit_type") in base_types for b in p1_blds)
    p2_base = any(b.get("unit_type") in base_types for b in p2_blds)

    winner = state.winner if state.winner else 0
    if not winner:
        if p1_base and not p2_base:
            winner = 1
        elif p2_base and not p1_base:
            winner = 2

    res = state.resources if hasattr(state, "resources") else {}
    return {
        "matchup": f"{race1[0].upper()}v{race2[0].upper()}",
        "race1": race1, "race2": race2,
        "seed": seed,
        "ticks": tick,
        "time_s": round(elapsed, 2),
        "winner": winner,
        "p1_units": len(p1_units), "p2_units": len(p2_units),
        "p1_buildings": len(p1_blds), "p2_buildings": len(p2_blds),
        "p1_mineral": res.get("p1_mineral", 0), "p2_mineral": res.get("p2_mineral", 0),
        "p1_gas": res.get("p1_gas", 0), "p2_gas": res.get("p2_gas", 0),
    }


def main():
    print("=" * 60)
    print("  RTS-AI 平衡性模拟 — 10局")
    print(f"  AI: ScriptAI({DIFFICULTY}) vs ScriptAI({DIFFICULTY})")
    print(f"  Max ticks: {MAX_TICKS}")
    print("=" * 60)

    results = []
    idx = 0
    games_per_mu = {0: 2, 1: 2, 2: 2, 3: 1, 4: 2, 5: 1}  # 共10局

    for mu_i, (r1, r2) in enumerate(MATCHUPS):
        n_games = games_per_mu.get(mu_i, 1)
        for g in range(n_games):
            seed = SEED_BASE + idx * 7
            idx += 1
            mu = f"{r1[0].upper()}v{r2[0].upper()}"
            print(f"\n[{idx}/10] {mu}  seed={seed} ...", end=" ", flush=True)
            r = run_one(r1, r2, seed)
            results.append(r)
            w = f"P{r['winner']}" if r["winner"] else "DRAW"
            print(f"→ {w}  ticks={r['ticks']}  {r['time_s']}s  U:{r['p1_units']}/{r['p2_units']}  B:{r['p1_buildings']}/{r['p2_buildings']}")

    # ─── 统计 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  结果汇总")
    print("=" * 60)

    mu_stats: dict[str, dict] = defaultdict(lambda: {"p1": 0, "p2": 0, "draw": 0, "n": 0, "ticks": 0})
    for r in results:
        s = mu_stats[r["matchup"]]
        s["n"] += 1
        s["ticks"] += r["ticks"]
        if r["winner"] == 1:
            s["p1"] += 1
        elif r["winner"] == 2:
            s["p2"] += 1
        else:
            s["draw"] += 1

    print(f"\n{'MU':<6} {'P1胜':>5} {'P2胜':>5} {'平':>4} {'总':>3} {'AvgTick':>8}")
    print("-" * 38)
    for mu in sorted(mu_stats):
        s = mu_stats[mu]
        avg = s["ticks"] // max(s["n"], 1)
        print(f"{mu:<6} {s['p1']:>5} {s['p2']:>5} {s['draw']:>4} {s['n']:>3} {avg:>8}")

    # 种族胜率
    race_w: dict[str, int] = defaultdict(int)
    race_t: dict[str, int] = defaultdict(int)
    for r in results:
        race_t[r["race1"]] += 1
        race_t[r["race2"]] += 1
        if r["winner"] == 1:
            race_w[r["race1"]] += 1
        elif r["winner"] == 2:
            race_w[r["race2"]] += 1

    print(f"\n{'种族':<10} {'胜':>4} {'出场':>5} {'胜率':>7}")
    print("-" * 30)
    for race in ("terran", "zerg", "protoss"):
        w = race_w[race]
        t = race_t[race]
        wr = f"{w/t*100:.0f}%" if t else "—"
        print(f"{race:<10} {w:>4} {t:>5} {wr:>7}")

    # 明细
    print(f"\n{'#':<3} {'MU':<6} {'Seed':<5} {'Win':<6} {'Ticks':<7} {'s':<6} {'P1U':<5} {'P2U':<5} {'P1B':<5} {'P2B':<5} {'P1M':<6} {'P2M':<6}")
    print("-" * 70)
    for i, r in enumerate(results, 1):
        w = f"P{r['winner']}" if r["winner"] else "DRAW"
        print(f"{i:<3} {r['matchup']:<6} {r['seed']:<5} {w:<6} {r['ticks']:<7} {r['time_s']:<6.1f} {r['p1_units']:<5} {r['p2_units']:<5} {r['p1_buildings']:<5} {r['p2_buildings']:<5} {r['p1_mineral']:<6} {r['p2_mineral']:<6}")

    # 存 JSON
    out = ROOT / "harness" / "output" / "balance_sim_10.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"summary": {k: dict(v) for k, v in mu_stats.items()}, "games": results}, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
