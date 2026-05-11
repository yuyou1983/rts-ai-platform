#!/usr/bin/env python3
"""E2E test: simulate exact Godot user flows."""
import requests

BASE = "http://localhost:8080/api"


def start_game(seed=42):
    r = requests.post(BASE + "/start_game", json={"seed": seed, "max_ticks": 10000, "ai_player": 2})
    return r.json()


def step(cmds=None):
    r = requests.post(BASE + "/step", json={"commands": cmds or []})
    return r.json()


def test_attack():
    """Simulate: select P1 worker, right-click P2 base."""
    state = start_game(42)
    ents = state["entities"]
    p1w = [k for k, v in ents.items() if v.get("owner") == 1 and v.get("entity_type") == "worker"][0]
    p2b = [k for k, v in ents.items() if v.get("owner") == 2 and v.get("building_type") == "base"][0]
    print(f"[ATTACK] {p1w} → {p2b}")

    state = step([{"action": "attack", "attacker_id": p1w, "target_id": p2b, "issuer": 1}])
    w = state["entities"].get(p1w, {})
    print(f"  attack_target_id={w.get('attack_target_id', 'NOT SET')}")

    for _ in range(500):
        state = step()
        if state.get("is_terminal"):
            break

    b = state["entities"].get(p2b, {})
    hp = b.get("health", 0)
    print(f"  P2 base hp after 500 ticks: {hp:.1f}/1500")
    assert hp < 1500, "No damage dealt!"
    print("  ✓ ATTACK WORKS")


def test_train_worker():
    """Simulate: select P1 base, press T."""
    state = start_game(42)
    ents = state["entities"]
    base = [k for k, v in ents.items() if v.get("owner") == 1 and v.get("building_type") == "base"][0]

    state = step([{"action": "train", "building_id": base, "unit_type": "worker", "issuer": 1}])
    pq = state["entities"].get(base, {}).get("production_queue", [])
    print(f"[TRAIN WORKER] production_queue={pq}")
    assert len(pq) > 0, "Train worker failed!"
    print("  ✓ TRAIN WORKER WORKS")


def test_build_and_train_soldier():
    """Simulate: select worker, B+right-click build barracks, then select barracks, T for soldier."""
    state = start_game(99)
    ents = state["entities"]
    wid = [k for k, v in ents.items() if v.get("owner") == 1 and v.get("entity_type") == "worker"][0]

    # Build barracks
    step([{"action": "build", "builder_id": wid, "building_type": "barracks", "pos_x": 15, "pos_y": 15, "issuer": 1}])

    for _ in range(300):
        state = step()

    barracks = [(k, v) for k, v in state["entities"].items()
                if v.get("owner") == 1 and v.get("building_type") == "barracks"
                and not v.get("is_constructing", True)]
    print(f"[BUILD+TRAIN SOLDIER] barracks ready: {len(barracks)}")
    assert len(barracks) > 0, "Barracks not built!"

    bid = barracks[0][0]
    state = step([{"action": "train", "building_id": bid, "unit_type": "soldier", "issuer": 1}])
    pq = state["entities"].get(bid, {}).get("production_queue", [])
    print(f"  Train soldier: production_queue={pq}")

    for _ in range(100):
        state = step()

    soldiers = [k for k, v in state["entities"].items()
                if v.get("owner") == 1 and v.get("entity_type") == "soldier"]
    print(f"  Soldiers after 100 ticks: {len(soldiers)}")
    assert len(soldiers) > 0, "No soldier spawned!"
    print("  ✓ BUILD+TRAIN SOLDIER WORKS")


if __name__ == "__main__":
    test_train_worker()
    test_attack()
    test_build_and_train_soldier()
    print("\n✓ ALL E2E TESTS PASSED")