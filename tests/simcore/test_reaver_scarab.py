"""Tests for P3-4: Reaver Scarab ammunition system."""
import math
import pytest
from simcore.construction import process_construction
from simcore.rules import resolve_combat

T = 32.0


def _reaver(eid="r1", owner=1, pos_x=100, pos_y=100, scarab_count=5, scarab_capacity=10,
            attack_ground=100, attack_air=0, cooldown_ground=22, cooldown_air=0,
            attack_range_ground=256, hp=100, energy=0) -> dict:
    return {
        "id": eid, "owner": owner,
        "entity_type": "soldier", "unit_type": "Reaver",
        "pos_x": pos_x, "pos_y": pos_y,
        "health": hp, "max_health": hp,
        "energy": energy, "max_energy": 200, "is_spellcaster": True,
        "armor": 0, "domain": "ground",
        "attack_ground": attack_ground, "attack_air": attack_air,
        "cooldown_ground": cooldown_ground, "cooldown_air": cooldown_air,
        "attack_range_ground": attack_range_ground, "attack_range_air": 0,
        "cooldown_timer": cooldown_ground,  # ready to fire on first tick
        "base_speed": 2.0,
        "is_idle": False, "attack_target_id": "",
        "target_x": None, "target_y": None,
        "returning_to_base": False, "deposit_pending": False,
        "scarab_count": scarab_count, "scarab_capacity": scarab_capacity,
        "scarab_building": False, "scarab_timer": 0,
        "is_flying": False, "is_transport": False,
        "loaded_units": [], "cargo_capacity": 0, "cargo_used": 0,
        "stasis": False, "morphing": False,
    }


def _target(eid="t1", owner=2, pos_x=200, pos_y=100, hp=200) -> dict:
    return {
        "id": eid, "owner": owner,
        "entity_type": "soldier", "unit_type": "Marine",
        "pos_x": pos_x, "pos_y": pos_y,
        "health": hp, "max_health": hp,
        "armor": 0, "domain": "ground",
        "attack_ground": 6, "attack_air": 0,
        "cooldown_ground": 15, "cooldown_air": 0,
        "attack_range_ground": 128, "attack_range_air": 0,
        "cooldown_timer": 0,
        "base_speed": 3.0,
        "is_idle": True, "attack_target_id": "",
        "target_x": None, "target_y": None,
        "returning_to_base": False, "deposit_pending": False,
        "scarab_count": 0, "scarab_capacity": 0,
        "scarab_building": False, "scarab_timer": 0,
        "is_flying": False, "is_transport": False,
        "loaded_units": [], "cargo_capacity": 0, "cargo_used": 0,
        "stasis": False, "morphing": False,
    }


class TestScarabConsumption:
    def test_scarab_decremented_on_fire(self):
        """Reaver fires and scarab_count decrements."""
        r = _reaver(scarab_count=5)
        r["attack_target_id"] = "t1"
        t = _target(hp=200)
        ents = {"r1": r, "t1": t}
        res = {"p1_mineral": 1000, "p2_mineral": 1000}
        result, _ = resolve_combat(ents, res, [], 1)
        assert result["r1"]["scarab_count"] == 4

    def test_no_scarab_no_fire(self):
        """Reaver with 0 scarabs cannot attack."""
        r = _reaver(scarab_count=0)
        r["attack_target_id"] = "t1"
        t = _target(hp=200)
        ents = {"r1": r, "t1": t}
        res = {"p1_mineral": 1000, "p2_mineral": 1000}
        result, _ = resolve_combat(ents, res, [], 1)
        # Target should not take damage from Reaver (Marine might still fire back)
        assert result["t1"]["health"] == 200 or result["t1"]["health"] == 200 - 6
        # Scarab count stays 0
        assert result["r1"]["scarab_count"] == 0

    def test_last_scarab_fires(self):
        """Reaver with 1 scarab fires, drops to 0."""
        r = _reaver(scarab_count=1)
        r["attack_target_id"] = "t1"
        t = _target(hp=200)
        ents = {"r1": r, "t1": t}
        res = {"p1_mineral": 1000, "p2_mineral": 1000}
        result, _ = resolve_combat(ents, res, [], 1)
        assert result["r1"]["scarab_count"] == 0


class TestBuildScarab:
    def test_build_scarab_deducts_mineral(self):
        """build_scarab command costs 15 minerals."""
        r = _reaver(scarab_count=3, scarab_capacity=10)
        ents = {"r1": r}
        res = {"p1_mineral": 100, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        cmds = [{"action": "build_scarab", "unit_id": "r1"}]
        result_ents, result_res = process_construction(ents, res, cmds, 1)
        assert result_res["p1_mineral"] == 85

    def test_build_scarab_sets_building_flag(self):
        r = _reaver(scarab_count=3, scarab_capacity=10)
        ents = {"r1": r}
        res = {"p1_mineral": 100, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        cmds = [{"action": "build_scarab", "unit_id": "r1"}]
        result_ents, _ = process_construction(ents, res, cmds, 1)
        assert result_ents["r1"]["scarab_building"] is True
        # Timer decremented in same tick by Section 5b
        assert result_ents["r1"]["scarab_timer"] == 69

    def test_build_scarab_rejected_if_full(self):
        """Cannot build scarab when at capacity."""
        r = _reaver(scarab_count=10, scarab_capacity=10)
        ents = {"r1": r}
        res = {"p1_mineral": 100, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        cmds = [{"action": "build_scarab", "unit_id": "r1"}]
        result_ents, result_res = process_construction(ents, res, cmds, 1)
        assert result_res["p1_mineral"] == 100  # not deducted
        assert result_ents["r1"].get("scarab_building", False) is False

    def test_build_scarab_rejected_if_already_building(self):
        """Cannot queue two scarabs simultaneously."""
        r = _reaver(scarab_count=5, scarab_capacity=10)
        r["scarab_building"] = True
        r["scarab_timer"] = 50
        ents = {"r1": r}
        res = {"p1_mineral": 100, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        cmds = [{"action": "build_scarab", "unit_id": "r1"}]
        result_ents, result_res = process_construction(ents, res, cmds, 1)
        assert result_res["p1_mineral"] == 100  # not deducted

    def test_build_scarab_rejected_insufficient_mineral(self):
        r = _reaver(scarab_count=5, scarab_capacity=10)
        ents = {"r1": r}
        res = {"p1_mineral": 10, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        cmds = [{"action": "build_scarab", "unit_id": "r1"}]
        result_ents, result_res = process_construction(ents, res, cmds, 1)
        assert result_res["p1_mineral"] == 10
        assert result_ents["r1"].get("scarab_building", False) is False

    def test_scarab_timer_completes(self):
        """After 70 ticks, scarab count increments."""
        r = _reaver(scarab_count=5, scarab_capacity=10)
        r["scarab_building"] = True
        r["scarab_timer"] = 1
        ents = {"r1": r}
        res = {"p1_mineral": 100, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        result_ents, _ = process_construction(ents, res, [], 1)
        assert result_ents["r1"]["scarab_count"] == 6
        assert result_ents["r1"]["scarab_building"] is False

    def test_scarab_timer_in_progress(self):
        """Mid-build, timer decrements but count doesn't change."""
        r = _reaver(scarab_count=5, scarab_capacity=10)
        r["scarab_building"] = True
        r["scarab_timer"] = 30
        ents = {"r1": r}
        res = {"p1_mineral": 100, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        result_ents, _ = process_construction(ents, res, [], 1)
        assert result_ents["r1"]["scarab_count"] == 5
        assert result_ents["r1"]["scarab_timer"] == 29
        assert result_ents["r1"]["scarab_building"] is True

    def test_non_reaver_rejected(self):
        """build_scarab on a non-Reaver unit does nothing."""
        m = _target(eid="m1", owner=1, hp=50)
        m["unit_type"] = "Marine"
        ents = {"m1": m}
        res = {"p1_mineral": 100, "p1_gas": 0, "p2_mineral": 100, "p2_gas": 0}
        cmds = [{"action": "build_scarab", "unit_id": "m1"}]
        result_ents, result_res = process_construction(ents, res, cmds, 1)
        assert result_res["p1_mineral"] == 100
