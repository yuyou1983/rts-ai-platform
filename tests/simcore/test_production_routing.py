"""Tests for production routing and supply enforcement (P1-1)."""

import pytest
from simcore.construction import check_train_prerequisites, check_supply


class TestBaseBackdoorSealed:
    """Verify base/command/nexus/hatchery can ONLY train workers, not all units."""

    def _building(self, bt, owner=1):
        return {
            "id": "b1", "owner": owner, "entity_type": "building",
            "building_type": bt,
            "pos_x": 0, "pos_y": 0, "health": 1000,
        }

    # ── Simplified "base" type ──
    def test_base_can_train_worker(self):
        entities = {"b1": self._building("base")}
        assert check_train_prerequisites(entities, 1, "b1", "worker") is True

    def test_base_cannot_train_soldier(self):
        entities = {"b1": self._building("base")}
        assert check_train_prerequisites(entities, 1, "b1", "soldier") is False

    def test_base_cannot_train_scout(self):
        entities = {"b1": self._building("base")}
        assert check_train_prerequisites(entities, 1, "b1", "scout") is False

    # ── Terran CommandCenter ──
    def test_command_center_can_train_scv(self):
        entities = {"b1": self._building("CommandCenter")}
        assert check_train_prerequisites(entities, 1, "b1", "SCV") is True

    @pytest.mark.parametrize("unit", [
        "Marine", "Firebat", "Ghost", "Medic",
        "Vulture", "Tank", "Goliath",
        "Wraith", "Dropship", "Vessel", "BattleCruiser", "Valkyrie",
    ])
    def test_command_center_cannot_train_combat_units(self, unit):
        entities = {"b1": self._building("CommandCenter")}
        assert check_train_prerequisites(entities, 1, "b1", unit) is False

    # ── Protoss Nexus ──
    def test_nexus_can_train_probe(self):
        entities = {"b1": self._building("Nexus")}
        assert check_train_prerequisites(entities, 1, "b1", "Probe") is True

    @pytest.mark.parametrize("unit", [
        "Zealot", "Dragoon", "HighTemplar", "DarkTemplar",
        "Reaver", "Shuttle", "Observer", "Arbiter",
        "Scout", "Carrier", "Corsair", "Archon", "DarkArchon",
    ])
    def test_nexus_cannot_train_combat_units(self, unit):
        entities = {"b1": self._building("Nexus")}
        assert check_train_prerequisites(entities, 1, "b1", unit) is False

    # ── Zerg Hatchery/Lair/Hive ──
    @pytest.mark.parametrize("bt", ["Hatchery", "Lair", "Hive"])
    def test_zerg_base_can_train_drone(self, bt):
        entities = {"b1": self._building(bt)}
        assert check_train_prerequisites(entities, 1, "b1", "Drone") is True

    @pytest.mark.parametrize("bt", ["Hatchery", "Lair", "Hive"])
    def test_zerg_base_can_train_overlord(self, bt):
        entities = {"b1": self._building(bt)}
        assert check_train_prerequisites(entities, 1, "b1", "Overlord") is True

    @pytest.mark.parametrize("bt", ["Hatchery", "Lair", "Hive"])
    @pytest.mark.parametrize("unit", [
        "Zergling", "Hydralisk", "Lurker", "Ultralisk",
        "Queen", "Defiler", "Mutalisk", "Guardian",
        "Devourer", "Scourge", "Broodling", "InfestedTerran",
    ])
    def test_zerg_base_cannot_train_combat_units(self, bt, unit):
        entities = {"b1": self._building(bt)}
        assert check_train_prerequisites(entities, 1, "b1", unit) is False

    # ── Correct routing: production buildings still work ──
    def test_barracks_can_train_marine(self):
        entities = {"b1": self._building("Barracks")}
        assert check_train_prerequisites(entities, 1, "b1", "Marine") is True

    def test_gateway_can_train_zealot(self):
        entities = {"b1": self._building("Gateway")}
        assert check_train_prerequisites(entities, 1, "b1", "Zealot") is True

    def test_factory_can_train_tank(self):
        entities = {"b1": self._building("Factory")}
        assert check_train_prerequisites(entities, 1, "b1", "Tank") is True

    def test_starport_can_train_wraith(self):
        entities = {"b1": self._building("Starport")}
        assert check_train_prerequisites(entities, 1, "b1", "Wraith") is True

    def test_stargate_can_train_carrier(self):
        entities = {"b1": self._building("Stargate")}
        assert check_train_prerequisites(entities, 1, "b1", "Carrier") is True

    def test_robotics_facility_can_train_reaver(self):
        entities = {"b1": self._building("RoboticsFacility")}
        assert check_train_prerequisites(entities, 1, "b1", "Reaver") is True


class TestSupplyEnforcement:
    """Verify supply cap is strictly enforced."""

    def test_training_allowed_when_under_cap(self):
        resources = {"p1_supply_used": 5, "p1_supply_cap": 10}
        assert check_supply(resources, 1, "Marine") is True

    def test_training_blocked_when_at_cap(self):
        resources = {"p1_supply_used": 10, "p1_supply_cap": 10}
        assert check_supply(resources, 1, "Marine") is False

    def test_training_blocked_when_exceeds_cap(self):
        resources = {"p1_supply_used": 9, "p1_supply_cap": 10}
        # Zealot costs 2 supply, 9+2=11 > 10
        assert check_supply(resources, 1, "Zealot") is False

    def test_no_supply_system_allows_training(self):
        resources = {"p1_supply_used": 0, "p1_supply_cap": 0}
        assert check_supply(resources, 1, "Marine") is True

    def test_worker_costs_1_supply(self):
        resources = {"p1_supply_used": 9, "p1_supply_cap": 10}
        # Worker costs 1, 9+1=10 ≤ 10
        assert check_supply(resources, 1, "worker") is True

    def test_overlord_training_allowed_at_cap(self):
        """Overlord costs 0 supply (it IS a supply provider), so always allowed."""
        resources = {"p1_supply_used": 10, "p1_supply_cap": 10}
        assert check_supply(resources, 1, "Overlord") is True

    def test_exact_fit_allowed(self):
        resources = {"p1_supply_used": 8, "p1_supply_cap": 10}
        # Marine costs 2 supply, 8+2=10 ≤ 10
        assert check_supply(resources, 1, "Marine") is True
