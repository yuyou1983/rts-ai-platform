"""Task 2: Semantic weapons catalog tests for SC1 representative units.

Verifies that weapons.json and unit_stats.json contain correct
weapon IDs, damage types, delivery types, and combat stats for
all 12 representative units, cross-referenced against the
Task 1A sc1_representative_reference.json.
"""
import json
from pathlib import Path

import pytest

# ── Paths ──────────────────────────────────────────────────────────────────
WEAPONS_PATH = Path(__file__).parent.parent.parent / "data" / "combat" / "weapons.json"
UNIT_STATS_PATH = Path(__file__).parent.parent.parent / "simcore" / "data" / "unit_stats.json"
REF_PATH = Path(__file__).parent.parent.parent / "data" / "combat" / "sc1_representative_reference.json"


# ── Expected weapon IDs per canonical unit ─────────────────────────────────
EXPECTED_WEAPONS = {
    "Marine": "terran_c10_rifle",
    "Firebat": "terran_flame_thrower",
    "Vulture": "terran_fragmentation_grenade",
    "Tank": "terran_arclite_cannon",
    "Zergling": "zerg_claws",
    "Hydralisk": "zerg_needle_spines",
    "Mutalisk": "zerg_glave_wurm",
    "Ultralisk": "zerg_kaiser_blades",
    "Zealot": "protoss_psi_blades",
    "Dragoon": "protoss_phase_disruptor",
    "Templar": "protoss_psionic_storm",
    "Reaver": "protoss_scarab",
}

VALID_DELIVERY = {"melee", "hitscan", "projectile", "chain", "area_periodic", "tracking"}
VALID_DAMAGE_TYPES = {"normal", "explosive", "concussive", "spells"}

# Unit name → unit_stats.json key mapping
UNIT_STATS_KEYS = {
    "Marine": "Marine",
    "Firebat": "Firebat",
    "Vulture": "Vulture",
    "Tank": "Tank",
    "Zergling": "Zergling",
    "Hydralisk": "Hydralisk",
    "Mutalisk": "Mutalisk",
    "Ultralisk": "Ultralisk",
    "Zealot": "Zealot",
    "Dragoon": "Dragoon",
    "Templar": "Templar",
    "Reaver": "Reaver",
}

# Units that can attack air
AIR_ATTACKERS = {"Marine", "Hydralisk", "Mutalisk", "Dragoon", "Templar"}


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def weapons():
    with open(WEAPONS_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def unit_stats():
    with open(UNIT_STATS_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def reference():
    with open(REF_PATH) as f:
        return json.load(f)


# ── Tests: weapons.json structure ──────────────────────────────────────────
class TestWeaponsCatalog:
    def test_weapons_file_exists(self):
        assert WEAPONS_PATH.exists(), f"weapons.json not found at {WEAPONS_PATH}"

    def test_all_12_weapons_present(self, weapons):
        for unit_name, weapon_id in EXPECTED_WEAPONS.items():
            assert weapon_id in weapons, f"Missing weapon '{weapon_id}' for {unit_name}"

    def test_all_delivery_types_valid(self, weapons):
        for wid, w in weapons.items():
            if wid == "_meta":
                continue
            assert w["delivery_type"] in VALID_DELIVERY, (
                f"Weapon {wid}: invalid delivery_type '{w['delivery_type']}'"
            )

    def test_all_damage_types_valid(self, weapons):
        for wid, w in weapons.items():
            if wid == "_meta":
                continue
            assert w["damage_type"] in VALID_DAMAGE_TYPES, (
                f"Weapon {wid}: invalid damage_type '{w['damage_type']}'"
            )

    def test_required_fields_present(self, weapons):
        required = [
            "weapon_id", "source_weapon_dat_id", "damage_per_hit",
            "hit_count", "total_base_damage", "damage_type", "delivery_type",
            "can_target_ground", "can_target_air", "cooldown_ticks",
            "launch_delay_ticks", "projectile_speed_world_per_tick",
            "max_lifetime_ticks", "splash_profile", "chain_fractions",
            "chain_radius_world",
        ]
        for wid, w in weapons.items():
            if wid == "_meta":
                continue
            for field in required:
                assert field in w, f"Weapon '{wid}': missing field '{field}'"

    def test_total_damage_consistency(self, weapons):
        """total_base_damage == damage_per_hit * hit_count"""
        for wid, w in weapons.items():
            if wid == "_meta":
                continue
            expected = w["damage_per_hit"] * w["hit_count"]
            assert w["total_base_damage"] == expected, (
                f"Weapon {wid}: total_base_damage={w['total_base_damage']} "
                f"!= {w['damage_per_hit']}×{w['hit_count']}={expected}"
            )

    def test_melee_hitscan_zero_projectile_speed(self, weapons):
        for wid, w in weapons.items():
            if wid == "_meta":
                continue
            if w["delivery_type"] in ("melee", "hitscan", "area_periodic"):
                assert w["projectile_speed_world_per_tick"] == 0, (
                    f"Weapon {wid}: delivery={w['delivery_type']} but "
                    f"projectile_speed={w['projectile_speed_world_per_tick']}"
                )

    def test_mutalisk_chain_fractions(self, weapons):
        w = weapons["zerg_glave_wurm"]
        assert w["delivery_type"] == "chain"
        assert w["chain_fractions"] == [1.0, 0.333333, 0.111111]
        assert w["splash_profile"] == "none"

    def test_psi_blades_melee(self, weapons):
        w = weapons["protoss_psi_blades"]
        assert w["delivery_type"] == "melee"
        assert w["chain_fractions"] == []
        assert w["splash_profile"] == "none"

    def test_psionic_storm_has_techdata_id(self, weapons):
        w = weapons["protoss_psionic_storm"]
        assert "source_techdata_id" in w, "Psionic Storm missing source_techdata_id"


# ── Tests: unit_stats.json weapon IDs ──────────────────────────────────────
class TestUnitStatsWeapons:
    def test_unit_stats_file_exists(self):
        assert UNIT_STATS_PATH.exists()

    def test_all_12_units_have_weapon_ids(self, unit_stats):
        for unit_name, expected_wid in EXPECTED_WEAPONS.items():
            key = UNIT_STATS_KEYS[unit_name]
            assert key in unit_stats, f"Unit '{key}' not in unit_stats.json"

            u = unit_stats[key]
            if unit_name == "Templar":
                # Templar uses spell_weapon_id
                assert u.get("spell_weapon_id") == expected_wid, (
                    f"{unit_name}: spell_weapon_id={u.get('spell_weapon_id')} "
                    f"!= {expected_wid}"
                )
            else:
                assert u.get("weapon_id_ground") == expected_wid, (
                    f"{unit_name}: weapon_id_ground={u.get('weapon_id_ground')} "
                    f"!= {expected_wid}"
                )

    def test_air_attackers_have_weapon_id_air(self, unit_stats):
        for unit_name in AIR_ATTACKERS:
            if unit_name == "Templar":
                continue  # Templar uses spell, not air weapon
            key = UNIT_STATS_KEYS[unit_name]
            u = unit_stats[key]
            assert u.get("weapon_id_air") is not None, (
                f"{unit_name} should have weapon_id_air"
            )

    def test_non_air_attackers_have_no_weapon_id_air(self, unit_stats):
        non_air = set(EXPECTED_WEAPONS.keys()) - AIR_ATTACKERS
        for unit_name in non_air:
            key = UNIT_STATS_KEYS[unit_name]
            u = unit_stats[key]
            air = u.get("weapon_id_air")
            assert air is None, (
                f"{unit_name} should NOT have weapon_id_air (got {air})"
            )

    def test_armor_type_matches_reference(self, unit_stats, reference):
        """12 units' armor_type must match SC1 unit size mapping."""
        size_to_armor = {"small": "light", "medium": "medium", "large": "heavy"}

        # Map unit names to reference keys
        ref_unit_map = {
            "Marine": ("terran", "marine"),
            "Firebat": ("terran", "firebat"),
            "Vulture": ("terran", "vulture"),
            "Tank": ("terran", "siege_tank"),
            "Zergling": ("zerg", "zergling"),
            "Hydralisk": ("zerg", "hydralisk"),
            "Mutalisk": ("zerg", "mutalisk"),
            "Ultralisk": ("zerg", "ultralisk"),
            "Zealot": ("protoss", "zealot"),
            "Dragoon": ("protoss", "dragoon"),
            "Templar": ("protoss", "high_templar"),
            "Reaver": ("protoss", "reaver"),
        }

        for unit_name, (race, key) in ref_unit_map.items():
            ref_unit = reference["units"][race][key]
            expected_armor = size_to_armor[ref_unit["unit_size"]]
            stats_key = UNIT_STATS_KEYS[unit_name]
            actual_armor = unit_stats[stats_key]["armor_type"]
            assert actual_armor == expected_armor, (
                f"{unit_name}: armor_type={actual_armor} != {expected_armor} "
                f"(unit_size={ref_unit['unit_size']})"
            )

    def test_engine_tps_matches_simcore(self, unit_stats):
        """_meta.engine_tps should be SimCore.tick_rate (10)."""
        assert unit_stats["_meta"]["engine_tps"] == 10, (
            f"engine_tps={unit_stats['_meta']['engine_tps']} != 10"
        )

    def test_cooldown_formula_correct(self, unit_stats):
        """_meta.cooldown_formula should use round(sc1_frames * sim_tick_rate / 23.81)."""
        formula = unit_stats["_meta"].get("cooldown_formula", "")
        assert "23.81" in formula, f"cooldown_formula missing 23.81: {formula}"
        assert "round" in formula, f"cooldown_formula missing round(): {formula}"


# ── Tests: cross-reference weapons vs reference ────────────────────────────
class TestCrossReference:
    def test_damage_matches_reference(self, weapons, reference):
        """Weapon damage values must match Task 1A reference."""
        ref_weapon_map = {
            "terran_c10_rifle": (0, 6, 1),
            "terran_flame_thrower": (25, 8, 1),
            "terran_fragmentation_grenade": (4, 20, 1),
            "terran_arclite_cannon": (10, 20, 2),
            "zerg_claws": (35, 5, 1),
            "zerg_needle_spines": (38, 10, 1),
            "zerg_glave_wurm": (48, 9, 1),
            "zerg_kaiser_blades": (39, 20, 1),
            "protoss_psi_blades": (64, 8, 2),
            "protoss_phase_disruptor": (66, 20, 1),
            "protoss_scarab": (81, 20, 1),
        }

        for wid, (dat_id, dmg, factor) in ref_weapon_map.items():
            w = weapons[wid]
            ref_w = reference["weapons"][str(dat_id)]
            assert w["damage_per_hit"] == ref_w["damage_amount"], (
                f"{wid}: damage_per_hit={w['damage_per_hit']} != "
                f"reference {ref_w['damage_amount']}"
            )
            # hit_count: Zealot special case (factor=1 in dat, but 2 in wiki)
            if wid == "protoss_psi_blades":
                assert w["hit_count"] == 2
            else:
                assert w["hit_count"] == ref_w["damage_factor"], (
                    f"{wid}: hit_count={w['hit_count']} != "
                    f"reference factor={ref_w['damage_factor']}"
                )

    def test_cooldown_matches_reference(self, weapons, reference):
        """Weapon cooldown frames must match Task 1A reference."""
        ref_cooldown_map = {
            "terran_c10_rifle": 0,
            "terran_flame_thrower": 25,
            "terran_fragmentation_grenade": 4,
            "terran_arclite_cannon": 10,
            "zerg_claws": 35,
            "zerg_needle_spines": 38,
            "zerg_glave_wurm": 48,
            "zerg_kaiser_blades": 39,
            "protoss_psi_blades": 64,
            "protoss_phase_disruptor": 66,
            "protoss_scarab": 81,
        }

        for wid, dat_id in ref_cooldown_map.items():
            w = weapons[wid]
            ref_w = reference["weapons"][str(dat_id)]
            assert w["sc1_cooldown_frames"] == ref_w["weapon_cooldown"], (
                f"{wid}: sc1_cooldown_frames={w['sc1_cooldown_frames']} != "
                f"reference {ref_w['weapon_cooldown']}"
            )

    def test_damage_type_matches_reference(self, weapons, reference):
        """Weapon damage types must match Task 1A reference."""
        type_map = {
            0: "normal", 1: "explosive", 2: "concussive", 3: "normal",
        }
        ref_type_map = {
            "terran_c10_rifle": 0,
            "terran_flame_thrower": 25,
            "terran_fragmentation_grenade": 4,
            "terran_arclite_cannon": 10,
            "zerg_claws": 35,
            "zerg_needle_spines": 38,
            "zerg_glave_wurm": 48,
            "zerg_kaiser_blades": 39,
            "protoss_psi_blades": 64,
            "protoss_phase_disruptor": 66,
            "protoss_scarab": 81,
        }

        type_names = {0: "independent", 1: "explosive", 2: "concussive", 3: "normal"}
        for wid, dat_id in ref_type_map.items():
            w = weapons[wid]
            ref_w = reference["weapons"][str(dat_id)]
            expected_type = type_names.get(ref_w["weapon_type_raw"], "unknown")
            assert w["damage_type"] == expected_type, (
                f"{wid}: damage_type={w['damage_type']} != "
                f"reference {expected_type}"
            )
