"""Test that gas workers loop: gather → return → deposit → gather again."""
import pytest
from simcore.economy import process_gathering
from simcore.mapgen import generate_map


def _make_worker(uid, px, py, owner=1, carry=0, carry_type="mineral",
                 gather_target="", idle=True, returning=False,
                 deposit=False, target_x=None, target_y=None):
    return {
        "id": uid, "entity_type": "worker", "owner": owner,
        "pos_x": px, "pos_y": py,
        "carry_amount": carry, "carry_type": carry_type,
        "carry_capacity": 10.0,
        "gather_target_id": gather_target,
        "is_idle": idle, "returning_to_base": returning,
        "deposit_pending": deposit,
        "target_x": target_x, "target_y": target_y,
        "health": 50, "max_health": 50,
    }


def _make_base(uid, px, py, owner=1):
    return {
        "id": uid, "entity_type": "building", "owner": owner,
        "building_type": "base", "pos_x": px, "pos_y": py,
        "health": 1000, "max_health": 1000,
    }


def _make_geyser(uid, px, py, amount=5000):
    return {
        "id": uid, "entity_type": "resource", "resource_type": "gas",
        "pos_x": px, "pos_y": py, "resource_amount": amount,
    }


def _make_refinery(uid, px, py, owner=1, geyser_id=""):
    return {
        "id": uid, "entity_type": "building", "owner": owner,
        "building_type": "Refinery", "pos_x": px, "pos_y": py,
        "health": 750, "max_health": 750,
        "built_on_geyser": geyser_id,
    }


def test_gas_worker_loops_after_deposit():
    """Worker gathers gas, returns, deposits, then goes BACK to gas."""
    base = _make_base("base1", 5.0, 5.0, owner=1)
    geyser = _make_geyser("g1", 10.0, 5.0, amount=5000)
    refinery = _make_refinery("ref1", 10.0, 5.0, owner=1, geyser_id="g1")
    # Worker just arrived at base with full gas load, deposit pending
    worker = _make_worker("w1", 5.0, 5.0, owner=1,
                          carry=10.0, carry_type="gas",
                          gather_target="g1",
                          idle=False, returning=False, deposit=True)

    entities = {e["id"]: e for e in [base, geyser, refinery, worker]}
    resources = {"p1_mineral": 100, "p1_gas": 0}

    ents, res = process_gathering(entities, resources, [], tick=0)

    w = ents["w1"]
    # Deposit should clear carry and credit gas
    assert res["p1_gas"] == 10, f"Expected 10 gas, got {res['p1_gas']}"
    assert w["carry_amount"] == 0
    # Worker should NOT be idle — should be heading back to gas
    assert w["is_idle"] is False, "Worker should auto-return to gas node"
    assert w["gather_target_id"] == "g1", "Worker should remember gas target"
    assert w["target_x"] == 10.0 and w["target_y"] == 5.0, \
        f"Worker target should be geyser pos, got ({w['target_x']}, {w['target_y']})"


def test_gas_worker_full_cycle():
    """Simulate several ticks: gather → full → return → deposit → back."""
    base = _make_base("base1", 5.0, 5.0, owner=1)
    geyser = _make_geyser("g1", 10.0, 5.0, amount=5000)
    refinery = _make_refinery("ref1", 10.0, 5.0, owner=1, geyser_id="g1")
    # Worker at geyser, empty carry
    worker = _make_worker("w1", 10.0, 5.0, owner=1,
                          carry=0.0, carry_type="mineral",
                          gather_target="g1",
                          idle=False, returning=False, deposit=False)

    entities = {e["id"]: e for e in [base, geyser, refinery, worker]}
    resources = {"p1_mineral": 100, "p1_gas": 0}

    # Tick 1-2: worker gathers gas (rate=4/tick, capacity=10)
    for _ in range(2):
        entities, resources = process_gathering(entities, resources, [], tick=0)
    w = entities["w1"]
    assert w["carry_amount"] == 8.0, f"After 2 ticks should carry 8, got {w['carry_amount']}"
    assert w["carry_type"] == "gas"

    # Tick 3: carry hits 10 → returning_to_base
    entities, resources = process_gathering(entities, resources, [], tick=0)
    w = entities["w1"]
    assert w["carry_amount"] == 10.0
    assert w["returning_to_base"] is True, "Worker should start returning"

    # Simulate arrival at base: teleport worker to base
    w["pos_x"] = 5.0
    w["pos_y"] = 5.0
    entities["w1"] = w
    entities, resources = process_gathering(entities, resources, [], tick=0)
    w = entities["w1"]
    # deposit_pending now
    assert w.get("deposit_pending") is True

    # Process deposit
    entities, resources = process_gathering(entities, resources, [], tick=0)
    w = entities["w1"]
    assert resources["p1_gas"] == 10, f"Should have 10 gas deposited, got {resources['p1_gas']}"
    # Worker should auto-return to geyser
    assert w["is_idle"] is False, "Worker should auto-return to gas, not idle"
    assert w["gather_target_id"] == "g1"


def test_mineral_worker_also_loops():
    """Mineral workers should also loop after deposit."""
    base = _make_base("base1", 5.0, 5.0, owner=1)
    mineral = {
        "id": "m1", "entity_type": "resource", "resource_type": "mineral",
        "pos_x": 10.0, "pos_y": 5.0, "resource_amount": 5000,
    }
    worker = _make_worker("w1", 5.0, 5.0, owner=1,
                          carry=10.0, carry_type="mineral",
                          gather_target="m1",
                          idle=False, returning=False, deposit=True)

    entities = {e["id"]: e for e in [base, mineral, worker]}
    resources = {"p1_mineral": 50, "p1_gas": 0}

    ents, res = process_gathering(entities, resources, [], tick=0)
    w = ents["w1"]
    assert res["p1_mineral"] == 60
    assert w["is_idle"] is False, "Mineral worker should auto-return too"
    assert w["gather_target_id"] == "m1"


def test_worker_idle_when_resource_exhausted():
    """Worker becomes truly idle if the resource node is gone."""
    base = _make_base("base1", 5.0, 5.0, owner=1)
    # No geyser in entities — it was depleted and removed
    worker = _make_worker("w1", 5.0, 5.0, owner=1,
                          carry=10.0, carry_type="gas",
                          gather_target="g1",
                          idle=False, returning=False, deposit=True)

    entities = {e["id"]: e for e in [base, worker]}
    resources = {"p1_mineral": 100, "p1_gas": 0}

    ents, res = process_gathering(entities, resources, [], tick=0)
    w = ents["w1"]
    assert res["p1_gas"] == 10
    assert w["is_idle"] is True, "Worker should be idle when resource gone"
    assert w["gather_target_id"] == "", "Target should be cleared"
