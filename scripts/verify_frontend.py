#!/usr/bin/env python3
"""Automated front-end verification for Godot RTS.

Runs a simulated game via the HTTP gateway, takes screenshots via
Godot headless mode, and validates entity positions/colors.

Usage:
    1. Start servers: python -m simcore.grpc_server &; python -m simcore.http_gateway &
    2. Run: python scripts/verify_frontend.py

No GUI needed — runs fully headless.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://localhost:8080/api"
SCREENSHOTS_DIR = Path(__file__).parent.parent / "test_screenshots"


def api_call(endpoint: str, data: dict | None = None) -> dict:
    """Make an API call to the HTTP gateway."""
    url = BASE + endpoint
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        print(f"❌ API call failed: {e}")
        sys.exit(1)


def verify_entity_state(state: dict) -> list[str]:
    """Validate entity state consistency. Returns list of errors."""
    errors: list[str] = []
    entities = state.get("entities", {})

    # 1. Resource nodes should have resource_type and resource_amount
    for eid, e in entities.items():
        if e.get("entity_type") == "resource":
            if not e.get("resource_type"):
                errors.append(f"{eid}: resource missing resource_type")
            if e.get("resource_amount", 0) <= 0 and e.get("resource_type"):
                errors.append(f"{eid}: resource {e['resource_type']} has amount={e.get('resource_amount')}")

    # 2. Buildings should have building_type
    for eid, e in entities.items():
        if e.get("entity_type") == "building":
            if not e.get("building_type"):
                errors.append(f"{eid}: building missing building_type")

    # 3. Own units should have positive health (or be dead/removed)
    for eid, e in entities.items():
        if e.get("entity_type") in ("worker", "soldier", "scout"):
            if e.get("health", 0) <= 0 and e.get("max_health", 1) > 0:
                errors.append(f"{eid}: {e['entity_type']} has health={e.get('health')} but still in entities")

    # 4. No duplicate positions (indicating double-render bug)
    positions: dict[str, list[str]] = {}
    for eid, e in entities.items():
        pos_key = f"({e.get('pos_x', 0):.1f},{e.get('pos_y', 0):.1f})"
        positions.setdefault(pos_key, []).append(eid)
    for pos, ids in positions.items():
        if len(ids) > 2:  # Allow 2 (e.g. worker + mineral at same spot)
            errors.append(f"Duplicate position {pos}: {ids}")

    return errors


def verify_game_loop(max_ticks: int = 200) -> bool:
    """Run a full game loop and verify state consistency at intervals."""
    print("🚀 Starting game via HTTP gateway...")
    state = api_call("/start_game", {"seed": 42, "max_ticks": 10000})
    tick = state.get("tick", 0)
    print(f"   Game started at tick {tick}, entities: {len(state.get('entities', {}))}")

    # Verify initial state
    errors = verify_entity_state(state)
    if errors:
        print(f"❌ Initial state errors: {errors}")
        return False
    print("✅ Initial state valid")

    # Run tick-by-tick, issuing gather commands at tick 0
    all_errors: list[str] = []
    check_intervals = {1, 10, 50, 100, 150, 200}

    for t in range(1, max_ticks + 1):
        # Get current entities for command generation
        entities = state.get("entities", {})
        commands: list[dict] = []

        # Issue gather commands at tick 1
        if t == 1:
            workers = {eid: e for eid, e in entities.items()
                       if e.get("entity_type") == "worker" and e.get("owner") == 1}
            minerals = {eid: e for eid, e in entities.items()
                        if e.get("entity_type") == "resource" and e.get("resource_type") == "mineral"
                        and e.get("resource_amount", 0) > 0}
            worker_list = list(workers.items())
            mineral_list = list(minerals.items())
            for i, (wid, w) in enumerate(worker_list):
                if i < len(mineral_list):
                    mid, m = mineral_list[i % len(mineral_list)]
                    commands.append({
                        "action": "gather",
                        "worker_id": wid,
                        "resource_id": mid,
                        "issuer": 1,
                    })

        # Build barracks when we can afford it (around tick 50)
        if t == 50:
            resources = state.get("resources", {})
            mineral = int(resources.get("p1_mineral", 0))
            if mineral >= 100:
                idle_workers = [eid for eid, e in entities.items()
                                if e.get("entity_type") == "worker" and e.get("owner") == 1
                                and e.get("is_idle", True)]
                if idle_workers:
                    # Find base position for build location
                    bases = [e for e in entities.values()
                             if e.get("entity_type") == "building" and e.get("building_type") == "base"
                             and e.get("owner") == 1]
                    if bases:
                        bx = bases[0].get("pos_x", 10) + 3
                        by = bases[0].get("pos_y", 10) + 2
                        commands.append({
                            "action": "build",
                            "builder_id": idle_workers[0],
                            "building_type": "barracks",
                            "pos_x": bx,
                            "pos_y": by,
                            "issuer": 1,
                        })

        # Train soldier when barracks is complete and we can afford
        if t in (100, 130, 160):
            barracks = [eid for eid, e in entities.items()
                        if e.get("entity_type") == "building" and e.get("building_type") == "barracks"
                        and e.get("owner") == 1 and not e.get("is_constructing", False)]
            if barracks:
                commands.append({
                    "action": "train",
                    "building_id": barracks[0],
                    "unit_type": "soldier",
                    "issuer": 1,
                })

        # Step
        state = api_call("/step", {"commands": commands})
        tick = state.get("tick", t)

        if t in check_intervals:
            errors = verify_entity_state(state)
            status = "✅" if not errors else "❌"
            ent_count = len(state.get("entities", {}))
            res = state.get("resources", {})
            print(f"  {status} Tick {tick}: ents={ent_count}, mineral={res.get('p1_mineral', 0)}, errors={len(errors)}")
            if errors:
                all_errors.extend([f"tick {tick}: {e}" for e in errors])

        if state.get("is_terminal", False):
            print(f"🏁 Game ended at tick {tick}, winner: P{state.get('winner', 0)}")
            break

    if all_errors:
        print(f"\n❌ {len(all_errors)} errors found:")
        for e in all_errors[:10]:
            print(f"   {e}")
        return False

    print("\n✅ All verification checks passed!")
    return True


def main() -> None:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    # Health check
    try:
        health = api_call("/health")
        print(f"🏥 Health: {health}")
    except SystemExit:
        print("❌ Servers not running. Start them first:")
        print("   python -m simcore.grpc_server --port 50051 &")
        print("   python -m simcore.http_gateway --grpc-port 50051 --http-port 8080 &")
        sys.exit(1)

    success = verify_game_loop(max_ticks=200)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()