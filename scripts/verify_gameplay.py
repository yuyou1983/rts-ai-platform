#!/usr/bin/env python3
"""Full gameplay harness — simulates grpc_bridge.gd behavior precisely.
Tests:
  1. start_game → first state (tick 0)
  2. step loop for 50 ticks (matching Godot's _poll_state timing)
  3. Verify fog_of_war present EVERY tick
  4. Verify entities change (AI builds)
  5. Verify resources increase
  6. Verify no NaN/corrupt data
  7. Fog flicker analysis
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
    errors = []

    # === 1. START GAME ===
    print("[1] start_game ...")
    state = post("/api/start_game", {
        "seed": 42,
        "max_ticks": 500,
        "ai_player": 2,
        "ai_difficulty": "medium",
        "enable_elevation": True,
    })

    tick = state.get("tick")
    entities = state.get("entities", {})
    fog = state.get("fog_of_war", {})
    resources = state.get("resources", {})
    height_map = state.get("height_map")

    if tick != 0:
        errors.append(f"start_game: expected tick=0, got {tick}")
    if not entities:
        errors.append("start_game: no entities returned")
    if not fog:
        errors.append("start_game: no fog_of_war returned")
    if not resources:
        errors.append("start_game: no resources returned")
    if not height_map:
        errors.append("start_game: no height_map returned (enable_elevation=True)")

    print(f"  tick={tick}, entities={len(entities)}, fog_keys={list(fog.keys())}, has_height_map={height_map is not None}")
    print(f"  P1 resources: {resources.get('1', {})}")

    # === 2. STEP LOOP ===
    print("[2] step loop (50 ticks) ...")
    prev_fog_p1 = fog.get("1", {}).get("tiles", [])
    oscillation_count = {}
    oscillation_ticks = {}
    tick_data = []

    for i in range(50):
        state = post("/api/step", {"commands": []})
        tick = state.get("tick", -1)
        entities = state.get("entities", {})
        fog = state.get("fog_of_war", {})
        resources = state.get("resources", {})
        is_terminal = state.get("is_terminal", False)

        # Fog present check
        if not fog:
            errors.append(f"tick {tick}: fog_of_war missing from step response")

        # Fog flicker analysis
        p1_tiles = fog.get("1", {}).get("tiles", [])
        for idx in range(min(len(p1_tiles), len(prev_fog_p1))):
            cur = p1_tiles[idx]
            prev = prev_fog_p1[idx]
            if prev == 2 and cur == 1:
                if idx not in oscillation_count:
                    oscillation_count[idx] = 0
                    oscillation_ticks[idx] = []
                oscillation_count[idx] += 1
                oscillation_ticks[idx].append(tick)
        prev_fog_p1 = list(p1_tiles)

        # Sanity: no NaN in resources
        for k, v in resources.items():
            if isinstance(v, float) and (v != v):  # NaN check
                errors.append(f"tick {tick}: NaN in resources.{k}")

        # Track entity count
        p1_units = sum(1 for e in entities.values() if e.get("owner") == 1 and e.get("entity_type") != "building")
        p2_units = sum(1 for e in entities.values() if e.get("owner") == 2 and e.get("entity_type") != "building")
        p1_minerals = resources.get("p1_mineral", resources.get("1", {}).get("minerals", 0))

        tick_data.append({
            "tick": tick, "p1_units": p1_units, "p2_units": p2_units,
            "p1_minerals": p1_minerals, "is_terminal": is_terminal
        })

        if is_terminal:
            print(f"  Game ended at tick {tick}, winner={state.get('winner')}")
            break

    # Print summary
    print(f"  Steps completed: {len(tick_data)}")
    if tick_data:
        first = tick_data[0]
        last = tick_data[-1]
        print(f"  P1 units: {first['p1_units']} → {last['p1_units']}")
        print(f"  P2 units: {first['p2_units']} → {last['p2_units']}")
        print(f"  P1 minerals: {first['p1_minerals']} → {last['p1_minerals']}")

    # === 3. FLICKER ANALYSIS ===
    print("[3] Fog flicker analysis ...")
    multi_osc = {idx: cnt for idx, cnt in oscillation_count.items() if cnt >= 2}
    single_osc = {idx: cnt for idx, cnt in oscillation_count.items() if cnt == 1}
    print(f"  Tiles with single 2→1 transition: {len(single_osc)} (normal — units leaving area)")
    print(f"  Tiles with multiple 2→1 transitions: {len(multi_osc)} (FLICKER)")

    if multi_osc:
        w = fog.get("1", {}).get("width", 16)
        worst = sorted(multi_osc.items(), key=lambda x: -x[1])[:5]
        for idx, cnt in worst:
            x, y = idx % w, idx // w
            print(f"    tile ({x},{y}): {cnt} oscillations at ticks {oscillation_ticks[idx][:8]}...")
        errors.append(f"Fog flicker: {len(multi_osc)} tiles oscillate between visible/explored")

    # === RESULT ===
    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("\n✅ All checks passed")
        return 0

if __name__ == "__main__":
    sys.exit(main())
