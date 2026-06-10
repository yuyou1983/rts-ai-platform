"""Test Zerg building morph: Hatchery→Lair→Hive."""
import pytest
from simcore.construction import process_construction
from simcore.mapgen import generate_map
from simcore.state import GameState


def _base_state():
    """Create a minimal state with a Zerg player, Hatchery, Drone, and resources."""
    entities = {
        "h1": {
            "id": "h1",
            "owner": 1,
            "entity_type": "building",
            "building_type": "base",
            "unit_type": "Hatchery",
            "pos_x": 10.0,
            "pos_y": 10.0,
            "health": 1500,
            "max_health": 1500,
            "is_constructing": False,
            "production_queue": [],
            "production_timers": [],
            "upgrade_queue": [],
            "upgrade_timers": [],
        },
        "d1": {
            "id": "d1",
            "owner": 1,
            "entity_type": "worker",
            "unit_type": "Drone",
            "pos_x": 10.5,
            "pos_y": 10.5,
            "health": 40,
            "max_health": 40,
            "is_idle": True,
            "carry_amount": 0,
        },
    }
    resources = {"p1_mineral": 500, "p1_gas": 300, "p2_mineral": 0, "p2_gas": 0}
    return entities, resources


def test_morph_base_starts_transformation():
    """morph_base command on a Hatchery should start morph with timer."""
    entities, resources = _base_state()
    commands = [{
        "action": "morph_building",
        "building_id": "h1",
        "morph_target": "morph_base",
        "issuer": 1,
    }]
    result_entities, result_res = process_construction(
        entities, resources, commands, tick=1, player_races={1: "zerg"}
    )
    building = result_entities["h1"]
    assert building.get("morph_target") == "morph_base"
    assert building.get("morph_json") == "Lair"
    assert building.get("morph_timer", 0) > 0
    # Cost deducted
    assert result_res["p1_mineral"] == 350  # 500 - 150
    assert result_res["p1_gas"] == 200      # 300 - 100


def test_morph_base_transforms_building_on_completion():
    """After morph_timer ticks, building_type should change to morph_base (Lair)."""
    entities, resources = _base_state()
    # Start morph
    entities["h1"]["morph_target"] = "morph_base"
    entities["h1"]["morph_json"] = "Lair"
    entities["h1"]["morph_timer"] = 2
    entities["h1"]["morph_hp_target"] = 1800
    
    # Tick once — still morphing
    result_entities, _ = process_construction(
        entities, resources, [], tick=10, player_races={1: "zerg"}
    )
    assert result_entities["h1"].get("morph_timer") == 1
    assert result_entities["h1"].get("building_type") == "base"  # still Hatchery
    
    # Tick again — morph complete
    result_entities, _ = process_construction(
        result_entities, resources, [], tick=11, player_races={1: "zerg"}
    )
    b = result_entities["h1"]
    assert b["building_type"] == "morph_base"
    assert b["unit_type"] == "Lair"
    assert b["max_health"] == 1800
    assert b.get("morph_target") == ""
    assert b.get("morph_timer") == 0


def test_morph_base2_requires_lair():
    """morph_base2 (Hive) should only work if building_type is morph_base (Lair)."""
    entities, resources = _base_state()
    # Try morph_base2 on Hatchery (should fail)
    commands = [{
        "action": "morph_building",
        "building_id": "h1",
        "morph_target": "morph_base2",
        "issuer": 1,
    }]
    result_entities, result_res = process_construction(
        entities, resources, commands, tick=1, player_races={1: "zerg"}
    )
    assert result_entities["h1"].get("morph_target", "") == ""  # not started
    assert result_res["p1_mineral"] == 500  # no cost deducted
    
    # Now upgrade to Lair first
    entities["h1"]["building_type"] = "morph_base"
    entities["h1"]["unit_type"] = "Lair"
    commands2 = [{
        "action": "morph_building",
        "building_id": "h1",
        "morph_target": "morph_base2",
        "issuer": 1,
    }]
    result_entities2, result_res2 = process_construction(
        entities, resources, commands2, tick=1, player_races={1: "zerg"}
    )
    assert result_entities2["h1"].get("morph_target") == "morph_base2"
    assert result_entities2["h1"].get("morph_json") == "Hive"


def test_morph_insufficient_resources():
    """Morph should not start if player can't afford it."""
    entities, resources = _base_state()
    resources["p1_mineral"] = 10  # can't afford 150
    commands = [{
        "action": "morph_building",
        "building_id": "h1",
        "morph_target": "morph_base",
        "issuer": 1,
    }]
    result_entities, result_res = process_construction(
        entities, resources, commands, tick=1, player_races={1: "zerg"}
    )
    assert result_entities["h1"].get("morph_target", "") == ""
