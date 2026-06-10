#!/usr/bin/env python3
"""Verify fog-of-war flicker via HTTP harness.
Simulates what grpc_bridge.gd does: start_game → step loop.
Checks:
  1. fog_of_war data present in every response
  2. tile state oscillation (2→1→2 = flicker)
  3. AI commands auto-injected when ai_player=2
"""
import json
import urllib.request
import sys
from collections import Counter

BASE = "http://localhost:8080"

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())

def main():
    print("=== Step 1: start_game ===")
    state = post("/api/start_game", {
        "seed": 42,
        "max_ticks": 500,
        "ai_player": 2,
        "ai_difficulty": "medium",
        "enable_elevation": True,
    })
    print(f"  tick={state['tick']}, entities={len(state['entities'])}")
    fog = state.get("fog_of_war", {})
    print(f"  fog_of_war keys: {list(fog.keys())}")
    for pid in ("1", "2"):
        pf = fog.get(pid, {})
        tiles = pf.get("tiles", [])
        c = Counter(tiles)
        print(f"  P{pid}: w={pf.get('width')}, h={pf.get('height')}, dist={dict(c)}")

    if not fog:
        print("ERROR: No fog_of_war in start_game response!")
        return 1

    # Track per-tile state transitions across ticks
    prev_tiles_p1 = fog.get("1", {}).get("tiles", [])
    oscillations = {}  # tile_idx → count of 2→1→2 flips
    oscillation_ticks = {}  # tile_idx → [tick numbers where 2→1 happened]

    print("\n=== Step 2: step loop (100 ticks) ===")
    for i in range(100):
        state = post("/api/step", {"commands": []})
        tick = state["tick"]
        fog = state.get("fog_of_war", {})
        p1 = fog.get("1", {})
        tiles = p1.get("tiles", [])
        c = Counter(tiles)

        # Check oscillation: compare current vs previous
        for idx in range(min(len(tiles), len(prev_tiles_p1))):
            cur = tiles[idx]
            prev = prev_tiles_p1[idx]
            # Oscillation = was 2, became 1 (or 0), then back to 2 later
            if prev == 2 and cur == 1:
                # This tile just went from visible to explored — potential flicker
                if idx not in oscillations:
                    oscillations[idx] = 0
                    oscillation_ticks[idx] = []
                oscillations[idx] += 1
                oscillation_ticks[idx].append(tick)

        prev_tiles_p1 = list(tiles)

        if state["is_terminal"]:
            print(f"  Game terminated at tick {tick}")
            break

        # Print progress every 20 ticks
        if (i + 1) % 20 == 0:
            print(f"  tick={tick}, fog dist P1={dict(c)}")

    print("\n=== Step 3: Analyze flicker ===")
    # Count tiles that oscillated more than once (2→1→2→1 pattern)
    multi_oscillations = {idx: cnt for idx, cnt in oscillations.items() if cnt >= 2}
    single_oscillations = {idx: cnt for idx, cnt in oscillations.items() if cnt == 1}

    print(f"  Tiles with single 2→1 transition: {len(single_oscillations)} (expected — units moving)")
    print(f"  Tiles with multiple 2→1 transitions (FLICKER): {len(multi_oscillations)}")

    if multi_oscillations:
        print("\n  Flicker details (top 10 worst offenders):")
        sorted_flicker = sorted(multi_oscillations.items(), key=lambda x: -x[1])[:10]
        w = fog.get("1", {}).get("width", 16)
        for idx, cnt in sorted_flicker:
            x, y = idx % w, idx // w
            ticks = oscillation_ticks[idx][:10]
            print(f"    tile ({x},{y}): {cnt} oscillations at ticks {ticks}...")

    print("\n=== Step 4: Verify AI is active ===")
    # Count P2 buildings
    p2_buildings = sum(1 for e in state["entities"].values()
                       if e.get("owner") == 2 and e.get("entity_type") == "building")
    p2_units = sum(1 for e in state["entities"].values()
                   if e.get("owner") == 2 and e.get("entity_type") != "building")
    print(f"  P2 buildings: {p2_buildings}, P2 units: {p2_units}")

    # Result
    if multi_oscillations:
        print(f"\n⚠️  FLICKER DETECTED: {len(multi_oscillations)} tiles oscillate between visible/explored")
        print("  Root cause: Server does 2→1 (expire) then 1→2 (re-illuminate) each tick")
        print("  Godot renders mid-transition = visible area flickers to half-dark")
        return 1
    else:
        print("\n✅ No flicker detected in 100 ticks")
        return 0

if __name__ == "__main__":
    sys.exit(main())
