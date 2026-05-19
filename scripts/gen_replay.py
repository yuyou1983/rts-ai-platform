
import sys, json, time
sys.path.insert(0, ".")
from simcore.engine import SimCore
from agents.script_ai import ScriptAI

def generate_tvz_replay(match_id, seed, max_ticks=5000):
    engine = SimCore(max_ticks=max_ticks, tick_rate=10.0)
    engine.initialize(map_seed=seed, config={
        "map_size": 64, "max_ticks": max_ticks,
        "player_races": {1: "terran", 2: "zerg"},
    })
    engine._player_races = {1: "terran", 2: "zerg"}

    ai1 = ScriptAI(player_id=1)
    ai2 = ScriptAI(player_id=2)
    tick = 0

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

    # Build compact replay
    replay = engine.replay
    # Compress: only keep every 5th tick for smooth 4x playback
    # but keep first 10 and last 20 ticks at full resolution
    ticks = []
    for i, snap in enumerate(replay):
        if i < 10 or i > len(replay) - 20 or i % 5 == 0:
            ticks.append(snap)

    return {
        "match_id": match_id,
        "seed": seed,
        "winner": engine.state.winner,
        "total_ticks": len(replay),
        "tick_count": len(ticks),
        "player_races": {"1": "terran", "2": "zerg"},
        "ticks": ticks,
    }

if __name__ == "__main__":
    print("Generating Terran vs Zerg replay (seed=42)...", flush=True)
    data = generate_tvz_replay("tvz-seed42", seed=42, max_ticks=5000)

    from pathlib import Path
    out = Path("harness/output/replays")
    out.mkdir(parents=True, exist_ok=True)

    # Save as single JSON (not JSONL, since we need the ticks array)
    with open(out / "tvz-seed42.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))

    print(f"  Winner: P{data['winner']} ({'Terran' if data['winner']==1 else 'Zerg' if data['winner']==2 else 'Draw'})")
    print(f"  Total ticks: {data['total_ticks']}, Compressed: {data['tick_count']}")
    print(f"  Saved to {out}/tvz-seed42.json")
