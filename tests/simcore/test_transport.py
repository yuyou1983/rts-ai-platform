"""Tests for P3-2: Transport system — load/unload Dropship, Shuttle, Overlord, Bunker."""
import math
import pytest
from simcore.transport import process_transport

T = 32.0  # _MAP_TILE_SIZE


def _transport(unit_type="Dropship", eid="tr1", owner=1, x=100, y=100, hp=150,
               abilities=None, loaded=None, cargo_capacity=None):
    e = {
        "id": eid, "entity_id": eid, "owner": owner,
        "entity_type": "unit", "unit_type": unit_type,
        "pos_x": x, "pos_y": y, "health": hp, "max_health": hp,
        "is_transport": True,
        "loaded_units": loaded or [],
        "cargo_used": len(loaded or []),
        "attack_ground": 0, "attack_air": 0,
        "domain": "air",
        "base_speed": 4.0, "buffs": [],
        "is_idle": True, "attack_target_id": "",
    }
    if abilities is not None:
        e["abilities"] = abilities
    if cargo_capacity is not None:
        e["cargo_capacity"] = cargo_capacity
    return e


def _passenger(eid="p1", owner=1, x=110, y=100, hp=40, unit_type="Marine",
               domain="ground", supply_cost=1):
    return {
        "id": eid, "entity_id": eid, "owner": owner,
        "entity_type": "unit", "unit_type": unit_type,
        "pos_x": x, "pos_y": y, "health": hp, "max_health": hp,
        "domain": domain, "supply_cost": supply_cost,
        "attack_ground": 6, "attack_air": 6,
        "attack_range_ground": 128, "weapon_type_ground": "normal",
        "cooldown_ground": 8, "cooldown_timer": 0,
        "armor": 0, "armor_type": "small",
        "shields": 0, "max_shields": 0,
        "base_speed": 3.0, "buffs": [],
        "is_idle": True, "attack_target_id": "",
    }


class TestLoad:
    def test_load_single_unit(self):
        tr = _transport(eid="tr1", x=100, y=100)
        p1 = _passenger(eid="p1", x=110, y=100)
        ents = {"tr1": tr, "p1": p1}
        cmds = [{"action": "load", "transport_id": "tr1", "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 1
        assert result["tr1"]["loaded_units"][0]["id"] == "p1"
        assert "p1" not in result  # removed from map

    def test_load_multiple_units(self):
        tr = _transport(eid="tr1")
        p1 = _passenger(eid="p1", x=110, y=100)
        p2 = _passenger(eid="p2", x=120, y=100)
        ents = {"tr1": tr, "p1": p1, "p2": p2}
        cmds = [{"action": "load", "transport_id": "tr1", "unit_ids": ["p1", "p2"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 2
        assert "p1" not in result
        assert "p2" not in result

    def test_load_respects_capacity(self):
        tr = _transport(eid="tr1", cargo_capacity=1)
        p1 = _passenger(eid="p1")
        p2 = _passenger(eid="p2", x=120, y=100)
        ents = {"tr1": tr, "p1": p1, "p2": p2}
        cmds = [{"action": "load", "transport_id": "tr1", "unit_ids": ["p1", "p2"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 1
        assert "p2" in result  # couldn't load, still on map

    def test_load_enemy_unit_rejected(self):
        tr = _transport(eid="tr1", owner=1)
        p1 = _passenger(eid="p1", owner=2)  # enemy
        ents = {"tr1": tr, "p1": p1}
        cmds = [{"action": "load", "transport_id": "tr1", "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 0
        assert "p1" in result

    def test_load_flying_unit_rejected(self):
        tr = _transport(eid="tr1")
        p1 = _passenger(eid="p1", domain="air")  # flying
        ents = {"tr1": tr, "p1": p1}
        cmds = [{"action": "load", "transport_id": "tr1", "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 0
        assert "p1" in result

    def test_load_out_of_range_rejected(self):
        tr = _transport(eid="tr1", x=0, y=0)
        p1 = _passenger(eid="p1", x=200, y=200)  # way too far
        ents = {"tr1": tr, "p1": p1}
        cmds = [{"action": "load", "transport_id": "tr1", "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 0
        assert "p1" in result

    def test_load_stasis_unit_rejected(self):
        tr = _transport(eid="tr1")
        p1 = _passenger(eid="p1")
        p1["stasis"] = True
        ents = {"tr1": tr, "p1": p1}
        cmds = [{"action": "load", "transport_id": "tr1", "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 0

    def test_overlord_without_ventral_sacs_rejected(self):
        tr = _transport(unit_type="Overlord", eid="ov1", abilities=["detector"])
        p1 = _passenger(eid="p1")
        ents = {"ov1": tr, "p1": p1}
        cmds = [{"action": "load", "transport_id": "ov1", "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["ov1"]["loaded_units"]) == 0

    def test_overlord_with_ventral_sacs_accepted(self):
        tr = _transport(unit_type="Overlord", eid="ov1",
                        abilities=["detector", "transport"])
        p1 = _passenger(eid="p1")
        ents = {"ov1": tr, "p1": p1}
        cmds = [{"action": "load", "transport_id": "ov1", "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["ov1"]["loaded_units"]) == 1
        assert "p1" not in result


class TestUnload:
    def test_unload_all(self):
        loaded = [{"id": "p1", "unit_type": "Marine", "owner": 1,
                   "health": 40, "max_health": 40, "shields": 0, "max_shields": 0,
                   "attack_ground": 6, "attack_air": 6,
                   "attack_range_ground": 128, "weapon_type_ground": "normal",
                   "cooldown_ground": 8, "armor": 0, "armor_type": "small",
                   "supply_cost": 1, "domain": "ground"}]
        tr = _transport(eid="tr1", x=300, y=300, loaded=loaded)
        ents = {"tr1": tr}
        cmds = [{"action": "unload", "transport_id": "tr1",
                 "target_x": 300, "target_y": 300}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 0
        assert "p1" in result
        assert result["p1"]["pos_x"] == 300
        assert result["p1"]["pos_y"] == 300
        assert result["p1"]["health"] == 40

    def test_unload_specific_units(self):
        loaded = [
            {"id": "p1", "unit_type": "Marine", "owner": 1,
             "health": 40, "max_health": 40, "shields": 0, "max_shields": 0,
             "attack_ground": 6, "attack_air": 6,
             "attack_range_ground": 128, "weapon_type_ground": "normal",
             "cooldown_ground": 8, "armor": 0, "armor_type": "small",
             "supply_cost": 1, "domain": "ground"},
            {"id": "p2", "unit_type": "Firebat", "owner": 1,
             "health": 50, "max_health": 50, "shields": 0, "max_shields": 0,
             "attack_ground": 8, "attack_air": 0,
             "attack_range_ground": 32, "weapon_type_ground": "concussive",
             "cooldown_ground": 10, "armor": 1, "armor_type": "medium",
             "supply_cost": 1, "domain": "ground"},
        ]
        tr = _transport(eid="tr1", x=200, y=200, loaded=loaded)
        ents = {"tr1": tr}
        cmds = [{"action": "unload", "transport_id": "tr1",
                 "target_x": 200, "target_y": 200, "unit_ids": ["p1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["tr1"]["loaded_units"]) == 1
        assert result["tr1"]["loaded_units"][0]["id"] == "p2"
        assert "p1" in result
        assert "p2" not in result  # p2 still in cargo

    def test_unload_preserves_health(self):
        """Passenger damaged while in transport; unloaded with correct HP."""
        loaded = [{"id": "p1", "unit_type": "Marine", "owner": 1,
                   "health": 15, "max_health": 40, "shields": 0, "max_shields": 0,
                   "attack_ground": 6, "attack_air": 6,
                   "attack_range_ground": 128, "weapon_type_ground": "normal",
                   "cooldown_ground": 8, "armor": 0, "armor_type": "small",
                   "supply_cost": 1, "domain": "ground"}]
        tr = _transport(eid="tr1", x=100, y=100, loaded=loaded)
        ents = {"tr1": tr}
        cmds = [{"action": "unload", "transport_id": "tr1",
                 "target_x": 100, "target_y": 100}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["p1"]["health"] == 15


class TestTransportDeath:
    def test_transport_death_kills_passengers(self):
        loaded = [{"id": "p1", "unit_type": "Marine", "owner": 1,
                   "health": 40, "max_health": 40, "shields": 0, "max_shields": 0,
                   "attack_ground": 6, "attack_air": 6,
                   "attack_range_ground": 128, "weapon_type_ground": "normal",
                   "cooldown_ground": 8, "armor": 0, "armor_type": "small",
                   "supply_cost": 1, "domain": "ground"}]
        tr = _transport(eid="tr1", hp=0, loaded=loaded)
        ents = {"tr1": tr}
        # No commands, but transport is dead
        result, _ = process_transport(ents, {"p1_mineral": 5000}, [], tick=1)
        assert "tr1" not in result  # dead transport removed


class TestBunker:
    def test_bunker_load_infantry(self):
        bunker = {
            "id": "bk1", "entity_id": "bk1", "owner": 1,
            "entity_type": "building", "unit_type": "Bunker",
            "pos_x": 100, "pos_y": 100, "health": 350, "max_health": 350,
            "is_transport": True,
            "loaded_units": [], "cargo_used": 0,
        }
        marine = _passenger(eid="m1", unit_type="Marine")
        ents = {"bk1": bunker, "m1": marine}
        cmds = [{"action": "load", "transport_id": "bk1", "unit_ids": ["m1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["bk1"]["loaded_units"]) == 1
        assert "m1" not in result

    def test_bunker_rejects_siege_tank(self):
        bunker = {
            "id": "bk1", "entity_id": "bk1", "owner": 1,
            "entity_type": "building", "unit_type": "Bunker",
            "pos_x": 100, "pos_y": 100, "health": 350, "max_health": 350,
            "is_transport": True,
            "loaded_units": [], "cargo_used": 0,
        }
        tank = _passenger(eid="t1", unit_type="SiegeTank")
        ents = {"bk1": bunker, "t1": tank}
        cmds = [{"action": "load", "transport_id": "bk1", "unit_ids": ["t1"]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["bk1"]["loaded_units"]) == 0
        assert "t1" in result

    def test_bunker_capacity_4(self):
        bunker = {
            "id": "bk1", "entity_id": "bk1", "owner": 1,
            "entity_type": "building", "unit_type": "Bunker",
            "pos_x": 100, "pos_y": 100, "health": 350, "max_health": 350,
            "is_transport": True,
            "loaded_units": [], "cargo_used": 0,
        }
        marines = {f"m{i}": _passenger(eid=f"m{i}", x=100 + i * 5, y=100)
                   for i in range(5)}
        ents = {"bk1": bunker, **marines}
        cmds = [{"action": "load", "transport_id": "bk1",
                 "unit_ids": [f"m{i}" for i in range(5)]}]
        result, _ = process_transport(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert len(result["bk1"]["loaded_units"]) == 4
        assert "m4" in result  # 5th rejected
