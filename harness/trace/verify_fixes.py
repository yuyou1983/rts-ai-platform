#!/usr/bin/env python3
"""Functional verification of RTS-AI HTTP train command fixes."""

import json
import requests
import time
import os

BASE = "http://localhost:8080/api"
REPORT_PATH = "/Users/yuyou/code/rts-ai-platform/harness/trace/verification-report.json"

def start_game(ai_player=2):
    r = requests.post(f"{BASE}/start_game", json={"ai_player": ai_player})
    assert r.status_code == 200, f"start_game failed: {r.status_code} {r.text[:200]}"
    return r.json()

def step_game(commands=None, num_steps=1):
    if commands is None:
        commands = []
    r = requests.post(f"{BASE}/step", json={"commands": commands})
    assert r.status_code == 200, f"step failed: {r.status_code} {r.text[:200]}"
    return r.json()

def run_scenario1():
    """AI Produces Combat Units via HTTP - 300 steps, check P2 marines."""
    print("=== Scenario 1: AI Produces Combat Units via HTTP ===")
    state = start_game(ai_player=2)
    print(f"  start_game: tick={state['tick']}, entities={len(state['entities'])}")
    
    # Run 300 steps
    for i in range(300):
        state = step_game(commands=[])
        if (i+1) % 50 == 0:
            print(f"  step {i+1}/300: tick={state['tick']}, entities={len(state['entities'])}")
    
    # Count P2 soldiers (Marines) - entity_type can be "soldier" or "unit", unit_type is "Marine"
    p2_marines = []
    p2_soldiers = []  # any combat unit (entity_type == "soldier")
    p2_all_units = []
    for eid, ent in state["entities"].items():
        if ent["owner"] == 2 and ent["entity_type"] in ("unit", "soldier", "worker"):
            p2_all_units.append(ent)
            if ent["entity_type"] == "soldier":
                p2_soldiers.append(ent)
                if ent.get("unit_type", "") == "Marine":
                    p2_marines.append(ent)
    
    marine_count = len(p2_marines)
    soldier_count = len(p2_soldiers)
    all_p2_unit_count = len(p2_all_units)
    print(f"  P2 total units: {all_p2_unit_count}, P2 soldiers: {soldier_count}, P2 Marines: {marine_count}")
    
    # Also check for any combat unit types
    unit_types = set(ent.get("unit_type", "") for ent in p2_all_units)
    print(f"  P2 unit types: {unit_types}")
    
    passed = marine_count >= 1
    assertion = "marine_count >= 1"
    print(f"  RESULT: {'PASS' if passed else 'FAIL'} ({assertion}: actual={marine_count})")
    
    return {
        "name": "AI Produces Combat Units via HTTP",
        "status": "pass" if passed else "fail",
        "evidence": {
            "request": "POST /api/step",
            "response_status": 200,
            "marine_count": marine_count,
            "soldier_count": soldier_count,
            "p2_total_units": all_p2_unit_count,
            "p2_unit_types": list(unit_types),
            "assertion": assertion,
            "steps_run": 300,
            "final_tick": state["tick"]
        }
    }

def run_scenario2_and_3():
    """Scenario 2: Production Queue Bounded (<=5), Scenario 3: Entity IDs in dict."""
    print("\n=== Scenario 2: Production Queue is Bounded ===")
    state = start_game(ai_player=2)
    print(f"  start_game: tick={state['tick']}")
    
    # Run 100 steps
    for i in range(100):
        state = step_game(commands=[])
    print(f"  After 100 steps: tick={state['tick']}, entities={len(state['entities'])}")
    
    # --- Scenario 2: Check production queues ---
    max_queue_len = 0
    queue_details = []
    for eid, ent in state["entities"].items():
        if ent["owner"] == 2 and ent["entity_type"] == "building":
            q = ent.get("production_queue", [])
            qlen = len(q)
            max_queue_len = max(max_queue_len, qlen)
            if qlen > 0:
                queue_details.append({"entity_id": eid, "queue_len": qlen, "queue": q})
    
    queue_bounded = max_queue_len <= 5
    print(f"  Max P2 building production queue length: {max_queue_len}")
    print(f"  Buildings with non-empty queues: {len(queue_details)}")
    for d in queue_details[:5]:
        print(f"    {d['entity_id']}: queue_len={d['queue_len']}, queue={d['queue']}")
    
    assertion = "production_queue length <= 5"
    print(f"  RESULT: {'PASS' if queue_bounded else 'FAIL'} ({assertion}: actual max={max_queue_len})")
    
    scenario2 = {
        "name": "Production Queue is Bounded",
        "status": "pass" if queue_bounded else "fail",
        "evidence": {
            "request": "POST /api/step",
            "response_status": 200,
            "max_queue_length": max_queue_len,
            "buildings_with_queue": len(queue_details),
            "assertion": assertion,
            "steps_run": 100
        }
    }
    
    # --- Scenario 3: Entity IDs inside entity dict ---
    print("\n=== Scenario 3: Entity IDs are present in observation ===")
    p2_buildings = [ent for eid, ent in state["entities"].items() 
                     if ent["owner"] == 2 and ent["entity_type"] == "building"]
    
    buildings_with_id = sum(1 for ent in p2_buildings if "id" in ent and ent["id"])
    buildings_total = len(p2_buildings)
    
    # Show sample
    if p2_buildings:
        sample = p2_buildings[0]
        print(f"  Sample P2 building keys: {list(sample.keys())}")
        print(f"  Sample 'id' field: {sample.get('id', 'MISSING')}")
    
    id_present = buildings_with_id == buildings_total and buildings_total > 0
    assertion3 = "P2 buildings have 'id' field inside entity dict"
    print(f"  P2 buildings with 'id': {buildings_with_id}/{buildings_total}")
    print(f"  RESULT: {'PASS' if id_present else 'FAIL'} ({assertion3})")
    
    scenario3 = {
        "name": "Entity IDs are present in observation",
        "status": "pass" if id_present else "fail",
        "evidence": {
            "request": "POST /api/step",
            "response_status": 200,
            "p2_buildings_total": buildings_total,
            "p2_buildings_with_id_field": buildings_with_id,
            "sample_entity_keys": list(p2_buildings[0].keys()) if p2_buildings else [],
            "sample_id_value": p2_buildings[0].get("id", "MISSING") if p2_buildings else "N/A",
            "assertion": assertion3
        }
    }
    
    return scenario2, scenario3

def main():
    print("Starting functional verification of RTS-AI HTTP train command fixes...\n")
    
    # Check server is reachable
    try:
        r = requests.post(f"{BASE}/start_game", json={"ai_player": 2})
        server_up = r.status_code == 200
        print(f"Server health: {'UP' if server_up else 'DOWN'} (status={r.status_code})")
    except Exception as e:
        print(f"Server health: DOWN ({e})")
        server_up = False
    
    if not server_up:
        report = {
            "overall_status": "fail",
            "server": {"started": False},
            "task_specific_scenarios": [],
            "summary": {"task_specific_total": 3, "task_specific_passed": 0, "pass_rate": 0.0}
        }
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to {REPORT_PATH}")
        return
    
    scenarios = []
    
    # Scenario 1
    try:
        s1 = run_scenario1()
        scenarios.append(s1)
    except Exception as e:
        print(f"  ERROR: {e}")
        scenarios.append({
            "name": "AI Produces Combat Units via HTTP",
            "status": "fail",
            "evidence": {"error": str(e)}
        })
    
    # Scenarios 2 & 3
    try:
        s2, s3 = run_scenario2_and_3()
        scenarios.append(s2)
        scenarios.append(s3)
    except Exception as e:
        print(f"  ERROR: {e}")
        scenarios.append({
            "name": "Production Queue is Bounded",
            "status": "fail",
            "evidence": {"error": str(e)}
        })
        scenarios.append({
            "name": "Entity IDs are present in observation",
            "status": "fail",
            "evidence": {"error": str(e)}
        })
    
    passed = sum(1 for s in scenarios if s["status"] == "pass")
    total = len(scenarios)
    
    if passed == total:
        overall = "pass"
    elif passed > 0:
        overall = "partial"
    else:
        overall = "fail"
    
    report = {
        "overall_status": overall,
        "server": {"started": True},
        "task_specific_scenarios": scenarios,
        "summary": {
            "task_specific_total": total,
            "task_specific_passed": passed,
            "pass_rate": round(passed / total, 2) if total > 0 else 0.0
        }
    }
    
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"OVERALL: {overall.upper()}")
    print(f"Passed: {passed}/{total}")
    print(f"Report: {REPORT_PATH}")

if __name__ == "__main__":
    main()