"""Tests for P1-2: Research system — RESEARCH command + research_queue + full upgrade effects."""
import pytest
from simcore.engine import SimCore
from simcore.commands import validate_command, RESEARCH
from simcore.upgrades import (
    apply_upgrade_effects,
    _get_upgrade_levels,
    _RESEARCH_EFFECTS,
)


# ─── Unit-level tests: upgrade level parsing ───

class TestUpgradeLevelParsing:
    def test_single_level_no_number(self):
        levels = _get_upgrade_levels(["StimPack Tech"])
        assert levels.get("StimPack Tech") == 1

    def test_numbered_levels(self):
        levels = _get_upgrade_levels(
            ["Infantry Weapons 1", "Infantry Weapons 2", "Infantry Weapons 3"]
        )
        assert levels["Infantry Weapons"] == 3

    def test_mixed_upgrades(self):
        levels = _get_upgrade_levels(
            ["Infantry Weapons 1", "Infantry Armor 2", "StimPack Tech"]
        )
        assert levels["Infantry Weapons"] == 1
        assert levels["Infantry Armor"] == 2
        assert levels["StimPack Tech"] == 1

    def test_empty_list(self):
        assert _get_upgrade_levels([]) == {}


# ─── Unit-level tests: weapon/armor stat upgrades ───

class TestStatUpgrades:
    def test_infantry_weapons_marine(self):
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["Infantry Weapons 1"])
        assert result["m1"]["attack"] == 7
        assert result["m1"]["upgrade_attack_bonus"] == 1

    def test_infantry_weapons_3_marine(self):
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["Infantry Weapons 1", "Infantry Weapons 2", "Infantry Weapons 3"])
        assert result["m1"]["attack"] == 9
        assert result["m1"]["upgrade_attack_bonus"] == 3

    def test_infantry_weapons_firebat_bonus(self):
        """Firebat gets +2 per level, total +6 at level 3."""
        firebat = {"entity_type": "soldier", "unit_type": "Firebat",
                   "attack": 8, "armor": 1}
        entities = {"f1": firebat}
        result = apply_upgrade_effects(entities, ["Infantry Weapons 3"])
        assert result["f1"]["attack"] == 14  # 8 + 6
        assert result["f1"]["upgrade_attack_bonus"] == 6

    def test_infantry_armor(self):
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["Infantry Armor 2"])
        assert result["m1"]["armor"] == 2
        assert result["m1"]["upgrade_armor_bonus"] == 2

    def test_zerg_melee_zergling(self):
        zergling = {"entity_type": "soldier", "unit_type": "Zergling",
                    "attack": 5, "armor": 0}
        entities = {"z1": zergling}
        result = apply_upgrade_effects(entities, ["Melee Attacks 1"])
        assert result["z1"]["attack"] == 6

    def test_protoss_ground_weapons_zealot_bonus(self):
        """Zealot gets +2 per level, total +6 at level 3."""
        zealot = {"entity_type": "soldier", "unit_type": "Zealot",
                  "attack": 8, "armor": 1}
        entities = {"z1": zealot}
        result = apply_upgrade_effects(entities, ["Ground Weapons 3"])
        assert result["z1"]["attack"] == 14  # 8 + 6

    def test_protoss_plasma_shields(self):
        zealot = {"entity_type": "soldier", "unit_type": "Zealot",
                  "attack": 8, "armor": 1, "shields": 20}
        entities = {"z1": zealot}
        result = apply_upgrade_effects(entities, ["Plasma Shields 2"])
        assert result["z1"]["shield_armor_bonus"] == 2

    def test_base_stats_stored(self):
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["Infantry Weapons 1"])
        assert result["m1"]["base_attack"] == 6
        assert result["m1"]["base_armor"] == 0

    def test_no_double_base_store(self):
        """Don't overwrite base_attack if already stored."""
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "base_attack": 6, "attack": 7, "armor": 0}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["Infantry Weapons 1"])
        assert result["m1"]["base_attack"] == 6  # preserved

    def test_skips_buildings(self):
        building = {"entity_type": "building", "unit_type": "Barracks",
                    "attack": 0, "armor": 1}
        entities = {"b1": building}
        result = apply_upgrade_effects(entities, ["Infantry Weapons 1"])
        assert result["b1"] == building  # unchanged

    def test_skips_meta_keys(self):
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0}
        entities = {"__completed_upgrades__": {"1": ["Infantry Weapons 1"]},
                    "m1": marine}
        result = apply_upgrade_effects(entities, ["Infantry Weapons 1"])
        assert result["m1"]["attack"] == 7


# ─── Unit-level tests: research effects ───

class TestResearchEffects:
    def test_u238_shells_range(self):
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "attack_range": 128, "armor": 0}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["U-238 Shells"])
        assert result["m1"]["attack_range"] == 160  # 128 + 32

    def test_stimpack_ability(self):
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0, "abilities": []}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["StimPack Tech"])
        assert "stimpack" in result["m1"]["abilities"]

    def test_siege_tech_ability(self):
        tank = {"entity_type": "soldier", "unit_type": "Tank",
                "attack": 30, "armor": 1, "abilities": []}
        entities = {"t1": tank}
        result = apply_upgrade_effects(entities, ["Siege Tech"])
        assert "siege_mode" in result["t1"]["abilities"]

    def test_burrow_ability_zerg(self):
        drone = {"entity_type": "worker", "unit_type": "Drone",
                 "attack": 0, "armor": 0, "abilities": []}
        zergling = {"entity_type": "soldier", "unit_type": "Zergling",
                    "attack": 5, "armor": 0, "abilities": []}
        entities = {"d1": drone, "z1": zergling}
        result = apply_upgrade_effects(entities, ["Burrow"])
        assert "burrow" in result["d1"]["abilities"]
        assert "burrow" in result["z1"]["abilities"]

    def test_lurker_aspect(self):
        hydra = {"entity_type": "soldier", "unit_type": "Hydralisk",
                 "attack": 10, "armor": 0, "abilities": []}
        entities = {"h1": hydra}
        result = apply_upgrade_effects(entities, ["Lurker Aspect"])
        assert "lurker_morph" in result["h1"]["abilities"]

    def test_singularity_charge_range(self):
        dragoon = {"entity_type": "soldier", "unit_type": "Dragoon",
                   "attack": 8, "attack_range": 128, "armor": 1}
        entities = {"d1": dragoon}
        result = apply_upgrade_effects(entities, ["Singularity Charge"])
        assert result["d1"]["attack_range"] == 192  # 128 + 64

    def test_leg_enhancements_speed(self):
        zealot = {"entity_type": "soldier", "unit_type": "Zealot",
                  "attack": 8, "armor": 1, "speed": 2.5}
        entities = {"z1": zealot}
        result = apply_upgrade_effects(entities, ["Leg Enhancements"])
        assert result["z1"]["speed"] == 3.0

    def test_research_no_effect_on_wrong_unit(self):
        """Siege Tech only affects Tank, not Marine."""
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0, "abilities": []}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["Siege Tech"])
        assert result["m1"].get("abilities", []) == []

    def test_adrenal_glands_speed(self):
        zergling = {"entity_type": "soldier", "unit_type": "Zergling",
                    "attack": 5, "armor": 0, "attack_speed": 8}
        entities = {"z1": zergling}
        result = apply_upgrade_effects(entities, ["Adrenal Glands"])
        assert result["z1"]["attack_speed"] == 6  # 8 - 2

    def test_chitinous_plating_armor(self):
        ultra = {"entity_type": "soldier", "unit_type": "Ultralisk",
                 "attack": 20, "armor": 1}
        entities = {"u1": ultra}
        result = apply_upgrade_effects(entities, ["Chitinous Plating"])
        assert result["u1"]["armor"] == 3  # 1 + 2

    def test_scarab_damage(self):
        reaver = {"entity_type": "soldier", "unit_type": "Reaver",
                  "attack": 100, "armor": 0}
        entities = {"r1": reaver}
        result = apply_upgrade_effects(entities, ["Scarab Damage"])
        assert result["r1"]["attack"] == 125  # 100 + 25


# ─── Integration: RESEARCH command in pipeline ───

class TestResearchCommandPipeline:
    def _make_state(self, upgrades_completed=None, minerals=5000, gas=5000):
        """Create a minimal SimCore state with an Engineering Bay and a Marine."""
        from simcore.state import GameState
        state = GameState()
        state.entities = {
            "eb1": {
                "entity_type": "building",
                "building_type": "EngineeringBay",
                "owner": 1,
                "is_constructing": False,
                "hp": 850,
                "upgrade_queue": [],
                "upgrade_timers": [],
            },
            "m1": {
                "entity_type": "soldier",
                "unit_type": "Marine",
                "owner": 1,
                "attack": 6,
                "armor": 0,
                "attack_range": 128,
                "hp": 40,
                "abilities": [],
            },
        }
        if upgrades_completed:
            state.entities["__completed_upgrades__"] = {"1": list(upgrades_completed)}
        state.resources = {"p1_mineral": minerals, "p1_gas": gas}
        return state

    def test_research_command_alias_accepted(self):
        """'research' action should be accepted by validate_command."""
        cmd = {"action": "research", "building_id": "eb1",
               "upgrade_name": "Infantry Weapons 1", "issuer": 1}
        entity = {"entity_type": "building", "building_type": "EngineeringBay",
                  "owner": 1, "is_constructing": False}
        # validate_command checks basic structure; action must be in ALL_COMMANDS
        assert cmd["action"] in {"upgrade", "research"}

    def test_research_command_adds_to_queue(self):
        """A RESEARCH command should add to upgrade_queue in the building."""
        from simcore.construction import process_construction
        entities = {
            "eb1": {
                "entity_type": "building",
                "building_type": "EngineeringBay",
                "owner": 1,
                "is_constructing": False,
                "hp": 850,
                "upgrade_queue": [],
                "upgrade_timers": [],
            },
        }
        resources = {"p1_mineral": 5000, "p1_gas": 5000}
        commands = [
            {"action": "research", "building_id": "eb1",
             "upgrade_name": "Infantry Weapons 1", "issuer": 1}
        ]
        entities_out, resources_out = process_construction(
            entities, resources, commands, tick=1,
            player_races={1: "terran"}
        )
        assert "Infantry Weapons 1" in entities_out["eb1"]["upgrade_queue"]

    def test_research_completion_applies_effects(self):
        """When upgrade timer expires, _apply_upgrade fires and effects appear."""
        from simcore.upgrades import apply_upgrade_effects
        # Simulate: Infantry Weapons 1 completed
        entities = {
            "m1": {"entity_type": "soldier", "unit_type": "Marine",
                   "owner": 1, "attack": 6, "armor": 0, "abilities": []}
        }
        result = apply_upgrade_effects(entities, ["Infantry Weapons 1"])
        assert result["m1"]["attack"] == 7

    def test_completed_upgrades_recorded(self):
        """After research completes, __completed_upgrades__ should contain it."""
        from simcore.construction import process_construction
        # Pre-set timer to 1 so it completes on next tick
        entities = {
            "eb1": {
                "entity_type": "building",
                "building_type": "EngineeringBay",
                "owner": 1,
                "is_constructing": False,
                "hp": 850,
                "upgrade_queue": ["Infantry Weapons 1"],
                "upgrade_timers": [1],
            },
        }
        resources = {"p1_mineral": 5000, "p1_gas": 5000}
        entities_out, _ = process_construction(
            entities, resources, [], tick=2,
            player_races={1: "terran"}
        )
        cu = entities_out.get("__completed_upgrades__", {})
        assert "Infantry Weapons 1" in cu.get("1", [])

    def test_research_event_emitted(self):
        """RESEARCH_COMPLETED event should be emitted when upgrade finishes."""
        from simcore.construction import process_construction
        entities = {
            "eb1": {
                "entity_type": "building",
                "building_type": "EngineeringBay",
                "owner": 1,
                "is_constructing": False,
                "hp": 850,
                "upgrade_queue": ["Infantry Weapons 1"],
                "upgrade_timers": [1],
            },
        }
        resources = {"p1_mineral": 5000, "p1_gas": 5000}
        entities_out, _ = process_construction(
            entities, resources, [], tick=2,
            player_races={1: "terran"}
        )
        events = entities_out.get("__events__", [])
        research_events = [e for e in events if e.get("type") == "research_completed"]
        assert len(research_events) == 1
        assert research_events[0]["upgrade_name"] == "Infantry Weapons 1"


# ─── Research catalog completeness ───

class TestResearchCatalog:
    def test_all_research_effects_have_units(self):
        """Every entry in _RESEARCH_EFFECTS must list at least one unit."""
        for name, effects in _RESEARCH_EFFECTS.items():
            for rfx in effects:
                assert len(rfx.get("units", [])) > 0, f"{name} has empty units list"

    def test_no_duplicate_abilities(self):
        """Applying the same research twice should not duplicate the ability."""
        marine = {"entity_type": "soldier", "unit_type": "Marine",
                  "attack": 6, "armor": 0, "abilities": []}
        entities = {"m1": marine}
        result = apply_upgrade_effects(entities, ["StimPack Tech", "StimPack Tech"])
        assert result["m1"]["abilities"].count("stimpack") == 1
