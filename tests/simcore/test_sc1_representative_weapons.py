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
            "mechanical_hit_count", "damage_type", "delivery_type",
            "cooldown_ticks", "launch_delay_ticks", "projectile_speed_world_per_tick",
        ]
        for wid, w in weapons.items():
            if wid == "_meta":
                continue
            for field in required:
                assert field in w, f"Weapon '{wid}': missing field '{field}'"

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
        assert w["chain_fractions"] == [1.0, 0.333, 0.111]

    def test_psi_blades_melee(self, weapons):
        w = weapons["protoss_psi_blades"]
        assert w["delivery_type"] == "melee"
        assert w["mechanical_hit_count"] == 2

    def test_psionic_storm_spell(self, weapons):
        w = weapons["protoss_psionic_storm"]
        assert w["delivery_type"] == "area_periodic"
        assert w["spell_tick_count"] == 8


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
        """12 units' armor_type must match SC1 unit size from audited reference."""
        # Map unit_stats keys to reference unit names
        stats_to_ref = {
            "Marine": "Marine", "Firebat": "Firebat", "Vulture": "Vulture",
            "Tank": "Tank", "Zergling": "Zergling", "Hydralisk": "Hydralisk",
            "Mutalisk": "Mutalisk", "Ultralisk": "Ultralisk",
            "Zealot": "Zealot", "Dragoon": "Dragoon",
            "Templar": "HighTemplar", "Reaver": "Reaver",
        }
        for stats_key, ref_name in stats_to_ref.items():
            ref_unit = reference["units"][ref_name]
            expected_armor = ref_unit["unit_size"]
            actual_armor = unit_stats[stats_key]["armor_type"]
            assert actual_armor == expected_armor, (
                f"{stats_key}: armor_type={actual_armor} != {expected_armor} "
                f"(from reference {ref_name})"
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
    """Cross-reference weapons.json values against the audited reference."""

    # Semantic weapon ID → reference unit name
    WEAPON_TO_UNIT = {
        "terran_c10_rifle": "Marine",
        "terran_flame_thrower": "Firebat",
        "terran_fragmentation_grenade": "Vulture",
        "terran_arclite_cannon": "Tank",
        "zerg_claws": "Zergling",
        "zerg_needle_spines": "Hydralisk",
        "zerg_glave_wurm": "Mutalisk",
        "zerg_kaiser_blades": "Ultralisk",
        "protoss_psi_blades": "Zealot",
        "protoss_phase_disruptor": "Dragoon",
        "protoss_psionic_storm": "HighTemplar",
        "protoss_scarab": "Reaver",
    }

    def test_damage_matches_reference(self, weapons, reference):
        """Weapon damage_per_hit must match audited reference."""
        for wid, ref_name in self.WEAPON_TO_UNIT.items():
            ref_unit = reference["units"][ref_name]
            ref_w = ref_unit.get("weapon") or ref_unit.get("spell_weapon") or ref_unit.get("scarab_weapon")
            assert ref_w is not None, f"No weapon data for {ref_name}"
            assert weapons[wid]["damage_per_hit"] == ref_w["damage_amount"], (
                f"{wid}: damage_per_hit={weapons[wid]['damage_per_hit']} != "
                f"reference {ref_w['damage_amount']}"
            )

    def test_damage_type_matches_reference(self, weapons, reference):
        """Weapon damage_type must match audited reference weapon_type."""
        type_map = {
            "normal": "normal", "explosive": "explosive",
            "concussive": "concussive", "independent_spell": "spells",
            "independent": "normal",
        }
        for wid, ref_name in self.WEAPON_TO_UNIT.items():
            ref_unit = reference["units"][ref_name]
            ref_w = ref_unit.get("weapon") or ref_unit.get("spell_weapon") or ref_unit.get("scarab_weapon")
            if ref_w is None:
                continue
            expected = type_map.get(ref_w.get("weapon_type", "normal"), "normal")
            assert weapons[wid]["damage_type"] == expected, (
                f"{wid}: damage_type={weapons[wid]['damage_type']} != reference {expected}"
            )

    def test_source_weapon_dat_id_matches(self, weapons, reference):
        """source_weapon_dat_id must match effective_weapon_dat_id from reference."""
        for wid, ref_name in self.WEAPON_TO_UNIT.items():
            ref_unit = reference["units"][ref_name]
            assert weapons[wid]["source_weapon_dat_id"] == ref_unit["effective_weapon_dat_id"], (
                f"{wid}: source_weapon_dat_id={weapons[wid]['source_weapon_dat_id']} != "
                f"reference {ref_unit['effective_weapon_dat_id']}"
            )

    def test_cooldown_matches_reference(self, weapons, reference):
        """cooldown_ticks must match weapon_cooldown from reference."""
        for wid, ref_name in self.WEAPON_TO_UNIT.items():
            ref_unit = reference["units"][ref_name]
            ref_w = ref_unit.get("weapon") or ref_unit.get("spell_weapon") or ref_unit.get("scarab_weapon")
            if ref_w is None:
                continue
            assert weapons[wid]["cooldown_ticks"] == ref_w["weapon_cooldown"], (
                f"{wid}: cooldown_ticks={weapons[wid]['cooldown_ticks']} != "
                f"reference {ref_w['weapon_cooldown']}"
            )


# ── Tests: Terran combat scenarios (Task 8) ────────────────────────────────


class TestTerranCombatScenarios:
    """Integration tests: 4 Terran units produce correct combat events.

    Each test sets up a realistic combat scenario, calls resolve_combat,
    and asserts on the emitted combat events.
    """

    def _make_entity(
        self,
        uid: str,
        owner: int = 1,
        unit_type: str = "Marine",
        health: float = 100,
        shields: float = 0,
        armor: int = 0,
        armor_type: str = "medium",
        pos: tuple[float, float] = (0.0, 0.0),
        attack_ground: float = 6,
        weapon_type_ground: str = "normal",
        weapon_id_ground: str = "terran_c10_rifle",
        attack_range: float = 4,
        cooldown_ground: int = 6,
        delivery_type: str = "hitscan",
        hit_count: int = 1,
        domain: str = "ground",
    ) -> dict:
        return {
            "id": uid,
            "owner": owner,
            "unit_type": unit_type,
            "entity_type": "soldier" if unit_type != "Vulture" else "scout",
            "health": health,
            "max_health": health,
            "shields": shields,
            "shield": shields,
            "armor": armor,
            "armor_type": armor_type,
            "pos_x": pos[0],
            "pos_y": pos[1],
            "attack_ground": attack_ground,
            "weapon_type_ground": weapon_type_ground,
            "weapon_id_ground": weapon_id_ground,
            "attack_range_ground": attack_range,
            "cooldown_ground": cooldown_ground,
            "cooldown_timer": 99,  # ready to fire
            "delivery_type": delivery_type,
            "hit_count": hit_count,
            "domain": domain,
            "is_idle": False,
            "attack_target_id": "",
        }

    def test_marine_vs_zergling_hitscan(self):
        """Marine → Zergling: hitscan normal, one impact event."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "marine1": self._make_entity(
                "marine1", owner=1, unit_type="Marine",
                attack_ground=6, weapon_type_ground="normal",
                weapon_id_ground="terran_c10_rifle",
                attack_range=4, cooldown_ground=6,
                delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "zerg1": self._make_entity(
                "zerg1", owner=2, unit_type="Zergling",
                health=35, armor=0, armor_type="light",
                pos=(3.0, 0.0),
            ),
        }
        entities["marine1"]["attack_target_id"] = "zerg1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1, "Should emit one attack_started"
        assert len(impacts) == 1, "Should emit one impact_resolved"
        assert attacks[0]["weapon_id"] == "terran_c10_rifle"
        assert impacts[0]["weapon_id"] == "terran_c10_rifle"
        assert impacts[0]["missed"] is False
        # Normal vs light: 100% damage, no armor → 6 damage
        assert impacts[0]["final_damage"] == 6.0
        assert result["zerg1"]["health"] == 29  # 35 - 6 = 29

    def test_firebat_vs_zerglings_splash(self):
        """Firebat → 3 Zerglings: cone splash fractions visible in events."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "bat1": self._make_entity(
                "bat1", owner=1, unit_type="Firebat",
                attack_ground=8, weapon_type_ground="concussive",
                weapon_id_ground="terran_flame_thrower",
                attack_range=2, cooldown_ground=9,
                delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "z1": self._make_entity(
                "z1", owner=2, unit_type="Zergling",
                health=35, armor_type="light",
                pos=(1.5, 0.0),
            ),
            "z2": self._make_entity(
                "z2", owner=2, unit_type="Zergling",
                health=35, armor_type="light",
                pos=(1.0, 0.5),
            ),
            "z3": self._make_entity(
                "z3", owner=2, unit_type="Zergling",
                health=35, armor_type="light",
                pos=(1.5, 1.0),
            ),
        }
        entities["bat1"]["attack_target_id"] = "z1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1, "Should emit one attack_started"
        assert attacks[0]["weapon_id"] == "terran_flame_thrower"

        # Primary target hit + splash hits
        splash_impacts = [e for e in impacts if e.get("is_splash")]
        direct_impacts = [e for e in impacts if not e.get("is_splash")]
        assert len(direct_impacts) >= 1, "Should have at least one direct impact"
        # Firebat has radial splash, so nearby Zerglings should be hit
        assert len(impacts) >= 2, "Should have at least 2 impacts (direct + splash)"

        # All impacts should reference the Firebat weapon
        for imp in impacts:
            assert imp["weapon_id"] == "terran_flame_thrower"

    def test_vulture_vs_zealot_concussive(self):
        """Vulture → Zealot: concussive damage vs light (100% multiplier)."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "vul1": self._make_entity(
                "vul1", owner=1, unit_type="Vulture",
                attack_ground=20, weapon_type_ground="concussive",
                weapon_id_ground="terran_fragmentation_grenade",
                attack_range=5, cooldown_ground=13,
                delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "zeal1": self._make_entity(
                "zeal1", owner=2, unit_type="Zealot",
                health=100, shields=60, armor=1, armor_type="light",
                pos=(4.0, 0.0),
            ),
        }
        entities["vul1"]["attack_target_id"] = "zeal1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "terran_fragmentation_grenade"
        assert len(impacts) == 1
        assert impacts[0]["weapon_id"] == "terran_fragmentation_grenade"
        # Concussive vs light: 100% multiplier
        # Shield absorbs first (no multiplier), remaining → health with multiplier
        # 20 damage, 60 shield → shield absorbs 20, 0 health damage
        assert impacts[0]["shield_damage"] == 20.0
        assert impacts[0]["health_damage"] == 0.0

    def test_tank_vs_dragoon_explosive(self):
        """Tank → Dragoon: explosive damage, heavy impact."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "tank1": self._make_entity(
                "tank1", owner=1, unit_type="SiegeTank",
                attack_ground=40, weapon_type_ground="explosive",
                weapon_id_ground="terran_arclite_cannon",
                attack_range=7, cooldown_ground=9,
                delivery_type="hitscan", hit_count=2,
                pos=(0.0, 0.0),
            ),
            "drag1": self._make_entity(
                "drag1", owner=2, unit_type="Dragoon",
                health=100, shields=80, armor=1, armor_type="heavy",
                pos=(6.0, 0.0),
            ),
        }
        entities["tank1"]["attack_target_id"] = "drag1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "terran_arclite_cannon"
        # Tank hit_count=2: two impacts of 20 each (total 40)
        assert len(impacts) == 2
        for imp in impacts:
            assert imp["weapon_id"] == "terran_arclite_cannon"
        # Explosive vs heavy: 100% multiplier, shield absorbs full per-hit
        # Hit 1: shield 80→60, Hit 2: shield 60→40, 0 health damage
        assert impacts[0]["shield_damage"] == 20.0
        assert impacts[0]["health_damage"] == 0.0
        assert impacts[1]["shield_damage"] == 20.0
        assert impacts[1]["health_damage"] == 0.0


# ── Tests: Zerg combat scenarios (Task 9) ─────────────────────────────────


class TestZergCombatScenarios:
    """Integration tests: 4 Zerg units produce correct combat events."""

    def _make_entity(
        self,
        uid: str,
        owner: int = 1,
        unit_type: str = "Zergling",
        health: float = 100,
        shields: float = 0,
        armor: int = 0,
        armor_type: str = "medium",
        pos: tuple[float, float] = (0.0, 0.0),
        attack_ground: float = 5,
        weapon_type_ground: str = "normal",
        weapon_id_ground: str = "zerg_claws",
        attack_range: float = 1.5,
        cooldown_ground: int = 3,
        delivery_type: str = "melee",
        hit_count: int = 1,
        domain: str = "ground",
    ) -> dict:
        return {
            "id": uid,
            "owner": owner,
            "unit_type": unit_type,
            "entity_type": "soldier" if unit_type not in ("Vulture", "Mutalisk") else "scout",
            "health": health,
            "max_health": health,
            "shields": shields,
            "shield": shields,
            "armor": armor,
            "armor_type": armor_type,
            "pos_x": pos[0],
            "pos_y": pos[1],
            "attack_ground": attack_ground,
            "weapon_type_ground": weapon_type_ground,
            "weapon_id_ground": weapon_id_ground,
            "attack_range_ground": attack_range,
            "cooldown_ground": cooldown_ground,
            "cooldown_timer": 99,
            "delivery_type": delivery_type,
            "hit_count": hit_count,
            "domain": domain,
            "is_idle": False,
            "attack_target_id": "",
        }

    def test_zergling_vs_marine_melee(self):
        """Zergling → Marine: melee normal, one impact."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "zerg1": self._make_entity(
                "zerg1", owner=1, unit_type="Zergling",
                attack_ground=5, weapon_type_ground="normal",
                weapon_id_ground="zerg_claws",
                attack_range=1.5, cooldown_ground=3,
                delivery_type="melee", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "mar1": self._make_entity(
                "mar1", owner=2, unit_type="Marine",
                health=40, armor=0, armor_type="light",
                pos=(1.0, 0.0),
            ),
        }
        entities["zerg1"]["attack_target_id"] = "mar1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "zerg_claws"
        assert len(impacts) == 1
        assert impacts[0]["weapon_id"] == "zerg_claws"
        # Normal vs light: 100%, no armor → 5 damage
        assert impacts[0]["final_damage"] == 5.0
        assert result["mar1"]["health"] == 35  # 40 - 5 = 35

    def test_hydralisk_vs_dragoon_projectile(self):
        """Hydralisk → Dragoon: explosive needle projectile."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "hyd1": self._make_entity(
                "hyd1", owner=1, unit_type="Hydralisk",
                attack_ground=10, weapon_type_ground="explosive",
                weapon_id_ground="zerg_needle_spines",
                attack_range=4, cooldown_ground=6,
                delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "drag1": self._make_entity(
                "drag1", owner=2, unit_type="Dragoon",
                health=100, shields=80, armor=1, armor_type="heavy",
                pos=(3.0, 0.0),
            ),
        }
        entities["hyd1"]["attack_target_id"] = "drag1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "zerg_needle_spines"
        assert len(impacts) == 1
        assert impacts[0]["weapon_id"] == "zerg_needle_spines"
        # Explosive vs heavy: 100% multiplier
        # Shield absorbs full 10, no health damage
        assert impacts[0]["shield_damage"] == 10.0
        assert impacts[0]["health_damage"] == 0.0

    def test_mutalisk_chain_bounce(self):
        """Mutalisk → 3 targets: chain_index 0/1/2 with correct fractions."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "mut1": self._make_entity(
                "mut1", owner=1, unit_type="Mutalisk",
                attack_ground=9, weapon_type_ground="normal",
                weapon_id_ground="zerg_glave_wurm",
                attack_range=3, cooldown_ground=13,
                delivery_type="chain", hit_count=1,
                pos=(0.0, 0.0),
                domain="air",
            ),
            "t1": self._make_entity(
                "t1", owner=2, unit_type="Marine",
                health=40, armor_type="light",
                pos=(2.0, 0.0),
            ),
            "t2": self._make_entity(
                "t2", owner=2, unit_type="Marine",
                health=40, armor_type="light",
                pos=(2.5, 0.5),
            ),
            "t3": self._make_entity(
                "t3", owner=2, unit_type="Marine",
                health=40, armor_type="light",
                pos=(3.0, 1.0),
            ),
        }
        entities["mut1"]["attack_target_id"] = "t1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "zerg_glave_wurm"

        # Chain should produce 3 impacts with chain_index 0, 1, 2
        assert len(impacts) == 3, f"Expected 3 chain impacts, got {len(impacts)}"

        # Chain indices in order
        chain_indices = [e["chain_index"] for e in impacts]
        assert chain_indices == [0, 1, 2], f"Chain indices: {chain_indices}"

        # Chain fractions match weapons.json
        fractions = [round(e["splash_fraction"], 6) for e in impacts]
        assert fractions == [1.0, 0.333, 0.111], f"Fractions: {fractions}"

        # All impacts share the same weapon_id
        for imp in impacts:
            assert imp["weapon_id"] == "zerg_glave_wurm"

        # 3 distinct targets
        target_ids = {e["target_id"] for e in impacts}
        assert len(target_ids) == 3, f"Expected 3 distinct targets, got {target_ids}"

    def test_ultralisk_vs_zealot_melee(self):
        """Ultralisk → Zealot: heavy melee, no projectile."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "ult1": self._make_entity(
                "ult1", owner=1, unit_type="Ultralisk",
                attack_ground=20, weapon_type_ground="normal",
                weapon_id_ground="zerg_kaiser_blades",
                attack_range=1.5, cooldown_ground=6,
                delivery_type="melee", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "zeal1": self._make_entity(
                "zeal1", owner=2, unit_type="Zealot",
                health=100, shields=60, armor=1, armor_type="light",
                pos=(1.0, 0.0),
            ),
        }
        entities["ult1"]["attack_target_id"] = "zeal1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "zerg_kaiser_blades"
        assert len(impacts) == 1
        assert impacts[0]["weapon_id"] == "zerg_kaiser_blades"
        # Normal vs light (Zealot armor_type=light): 100% multiplier on health
        # Shield absorbs full 20, no health damage
        assert impacts[0]["shield_damage"] == 20.0
        assert impacts[0]["health_damage"] == 0.0


# ── Tests: Protoss combat scenarios (Task 10) ────────────────────────────


class TestProtossCombatScenarios:
    """Integration tests: 4 Protoss units produce correct combat events."""

    def _make_entity(
        self,
        uid: str,
        owner: int = 1,
        unit_type: str = "Zealot",
        health: float = 100,
        shields: float = 0,
        armor: int = 0,
        armor_type: str = "medium",
        pos: tuple[float, float] = (0.0, 0.0),
        attack_ground: float = 16,
        weapon_type_ground: str = "normal",
        weapon_id_ground: str = "protoss_psi_blades",
        attack_range: float = 1.5,
        cooldown_ground: int = 9,
        delivery_type: str = "melee",
        hit_count: int = 1,
        domain: str = "ground",
    ) -> dict:
        return {
            "id": uid,
            "owner": owner,
            "unit_type": unit_type,
            "entity_type": "soldier",
            "health": health,
            "max_health": health,
            "shields": shields,
            "shield": shields,
            "armor": armor,
            "armor_type": armor_type,
            "pos_x": pos[0],
            "pos_y": pos[1],
            "attack_ground": attack_ground,
            "weapon_type_ground": weapon_type_ground,
            "weapon_id_ground": weapon_id_ground,
            "attack_range_ground": attack_range,
            "cooldown_ground": cooldown_ground,
            "cooldown_timer": 99,
            "delivery_type": delivery_type,
            "hit_count": hit_count,
            "domain": domain,
            "is_idle": False,
            "attack_target_id": "",
        }

    def test_zealot_double_hit(self):
        """Zealot → Marine: hit_count=2, two impact events in one cycle."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "zeal1": self._make_entity(
                "zeal1", owner=1, unit_type="Zealot",
                attack_ground=16, weapon_type_ground="normal",
                weapon_id_ground="protoss_psi_blades",
                attack_range=1.5, cooldown_ground=9,
                delivery_type="melee", hit_count=2,
                pos=(0.0, 0.0),
            ),
            "mar1": self._make_entity(
                "mar1", owner=2, unit_type="Marine",
                health=40, armor=0, armor_type="light",
                pos=(1.0, 0.0),
            ),
        }
        entities["zeal1"]["attack_target_id"] = "mar1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "protoss_psi_blades"
        # Zealot hits twice per attack cycle
        assert len(impacts) == 2, f"Expected 2 impacts (hit_count=2), got {len(impacts)}"
        # Each hit does 8 damage (total 16)
        for imp in impacts:
            assert imp["weapon_id"] == "protoss_psi_blades"
            assert imp["hit_index"] in (0, 1)
        # Total damage = 16 (8 per hit, normal vs light = 100%, no armor)
        total_dmg = sum(e["health_damage"] + e["shield_damage"] for e in impacts)
        assert total_dmg == 16.0, f"Total damage {total_dmg} != 16"

    def test_dragoon_vs_shielded_target(self):
        """Dragoon → Dragoon: explosive phase orb, shield/health split."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "drag1": self._make_entity(
                "drag1", owner=1, unit_type="Dragoon",
                attack_ground=20, weapon_type_ground="explosive",
                weapon_id_ground="protoss_phase_disruptor",
                attack_range=4, cooldown_ground=13,
                delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "drag2": self._make_entity(
                "drag2", owner=2, unit_type="Dragoon",
                health=100, shields=15, armor=1, armor_type="heavy",
                pos=(3.0, 0.0),
            ),
        }
        entities["drag1"]["attack_target_id"] = "drag2"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "protoss_phase_disruptor"
        assert len(impacts) == 1
        # Shield absorbs 15, remaining 5 goes to health
        # Explosive vs heavy: 100% multiplier, armor 1 → 5*1.0 - 1 = 4
        assert impacts[0]["shield_damage"] == 15.0
        assert impacts[0]["health_damage"] == 4.0

    def test_reaver_splash_damage(self):
        """Reaver → clustered Marines: scarab with splash."""
        from simcore.rules import resolve_combat
        from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED

        entities = {
            "reaver1": {**self._make_entity(
                "reaver1", owner=1, unit_type="Reaver",
                attack_ground=20, weapon_type_ground="normal",
                weapon_id_ground="protoss_scarab",
                attack_range=8, cooldown_ground=9,
                delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ), "scarab_count": 5},
            "m1": self._make_entity(
                "m1", owner=2, unit_type="Marine",
                health=40, armor=0, armor_type="light",
                pos=(7.0, 0.0),
            ),
            "m2": self._make_entity(
                "m2", owner=2, unit_type="Marine",
                health=40, armor=0, armor_type="light",
                pos=(7.0, 1.0),
            ),
            "m3": self._make_entity(
                "m3", owner=2, unit_type="Marine",
                health=40, armor=0, armor_type="light",
                pos=(8.0, 0.5),
            ),
        }
        entities["reaver1"]["attack_target_id"] = "m1"

        combat_events: list[dict] = []
        result, _ = resolve_combat(
            entities, {}, [], tick=1,
            combat_events=combat_events,
        )

        attacks = [e for e in combat_events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in combat_events if e["event_type"] == IMPACT_RESOLVED]

        assert len(attacks) == 1
        assert attacks[0]["weapon_id"] == "protoss_scarab"
        # Primary hit + at least one splash
        assert len(impacts) >= 2, f"Expected splash impacts, got {len(impacts)}"
        # Primary impact
        primary = [e for e in impacts if not e.get("is_splash")]
        assert len(primary) >= 1
        # Splash impacts
        splash = [e for e in impacts if e.get("is_splash")]
        assert len(splash) >= 1
        # All impacts use scarab weapon
        for imp in impacts:
            assert imp["weapon_id"] == "protoss_scarab"
