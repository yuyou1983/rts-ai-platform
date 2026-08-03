"""Tests for the single authoritative damage resolver in combat_resolution.py.

Task 5 of remediation plan: verify that armor is subtracted BEFORE the size
multiplier (OpenBW order), and that no second formula exists in rules.py.
"""
import pytest

from simcore.combat_resolution import (
    calculate_damage,
    get_damage_multiplier,
    get_armor_type,
    resolve_weapon_impact,
    KillFeed,
)


# ─── Formula order: armor before size multiplier ───────────


class TestDamageFormulaOrder:
    """Verify (damage - armor) * multiplier, NOT damage * multiplier - armor."""

    def test_armor_is_subtracted_before_size_multiplier(self):
        """Correct: (20 - 1 armor) * 0.25 = 4.75.
        Incorrect legacy formula: 20 * 0.25 - 1 = 4.0.
        """
        result = calculate_damage(
            base_damage=20.0,
            weapon_type="concussive",  # 25% vs heavy
            target_armor=1,
            target_armor_type="heavy",
        )
        assert result == pytest.approx(4.75), (
            f"Expected (20-1)*0.25=4.75, got {result}"
        )

    def test_explosive_vs_light_armor_first(self):
        """Correct: (20 - 2 armor) * 0.5 = 9.0.
        Incorrect legacy: 20 * 0.5 - 2 = 8.0.
        """
        result = calculate_damage(
            base_damage=20.0,
            weapon_type="explosive",  # 50% vs light
            target_armor=2,
            target_armor_type="light",
        )
        assert result == pytest.approx(9.0), (
            f"Expected (20-2)*0.5=9.0, got {result}"
        )

    def test_normal_damage_full_after_armor(self):
        """Normal weapon: (20 - 3 armor) * 1.0 = 17.0."""
        result = calculate_damage(
            base_damage=20.0,
            weapon_type="normal",
            target_armor=3,
            target_armor_type="heavy",
        )
        assert result == pytest.approx(17.0)

    def test_minimum_damage_applies_after_armor_and_multiplier(self):
        """If (damage - armor) * mult < min, return min."""
        result = calculate_damage(
            base_damage=1.0,
            weapon_type="concussive",  # 25% vs heavy
            target_armor=3,
            target_armor_type="heavy",
        )
        # (1 - 3) = max(0, -2) = 0; 0 * 0.25 = 0; max(0.5, 0) = 0.5
        assert result == pytest.approx(0.5)

    def test_zero_armor_no_change(self):
        """With 0 armor, both formulas agree — sanity check."""
        result = calculate_damage(
            base_damage=20.0,
            weapon_type="concussive",
            target_armor=0,
            target_armor_type="heavy",
        )
        assert result == pytest.approx(5.0)  # 20 * 0.25 = 5.0


class TestShieldPartialPenetration:
    """Shield absorbs first (no size multiplier), then remaining goes to health."""

    def test_shield_partial_armor_before_multiplier(self):
        """10 shield, 20 base damage, armor 1, multiplier 0.5 (explosive vs light).
        Shield absorbs 10, remaining 10.
        Health: (10 - 1) * 0.5 = 4.5  (correct)
        Legacy:  10 * 0.5 - 1 = 4.0  (wrong)
        """
        entities = {
            "target": {
                "id": "target", "owner": 2, "unit_type": "Marine",
                "pos_x": 0.0, "pos_y": 0.0,
                "health": 100.0, "max_health": 100.0,
                "shields": 10.0, "max_shields": 10.0,
                "armor": 1, "armor_type": "light",
                "entity_type": "soldier", "domain": "ground",
                "attack_target_id": "", "is_idle": True,
            },
        }
        updated, removed = resolve_weapon_impact(
            entities,
            attacker_id="attacker",
            target_id="target",
            weapon_id="test_weapon",
            weapon_type="explosive",  # 50% vs light
            base_damage=20.0,
            tick=1,
            combat_events=None,
        )
        # Shield: 10 - 10 = 0
        assert updated["target"]["shields"] == pytest.approx(0.0)
        # Health: (10 - 1) * 0.5 = 4.5 → 100 - 4.5 = 95.5
        assert updated["target"]["health"] == pytest.approx(95.5), (
            f"Expected (10-1)*0.5=4.5 dmg → 95.5 hp, got {updated['target']['health']}"
        )

    def test_shield_fully_absorbs_no_health_damage(self):
        """If shield absorbs all damage, health is untouched."""
        entities = {
            "target": {
                "id": "target", "owner": 2, "unit_type": "Zealot",
                "pos_x": 0.0, "pos_y": 0.0,
                "health": 100.0, "max_health": 100.0,
                "shields": 60.0, "max_shields": 60.0,
                "armor": 1, "armor_type": "light",
                "entity_type": "soldier", "domain": "ground",
                "attack_target_id": "", "is_idle": True,
            },
        }
        updated, removed = resolve_weapon_impact(
            entities,
            attacker_id="attacker",
            target_id="target",
            weapon_id="test_weapon",
            weapon_type="normal",
            base_damage=10.0,
            tick=1,
            combat_events=None,
        )
        assert updated["target"]["shields"] == pytest.approx(50.0)
        assert updated["target"]["health"] == pytest.approx(100.0)


class TestNoShadowing:
    """Verify rules.py does not shadow combat_resolution functions."""

    def test_rules_imports_calculate_damage_from_combat_resolution(self):
        """rules.calculate_damage must be the same object as combat_resolution's."""
        import simcore.rules as rules
        from simcore import combat_resolution
        assert rules.calculate_damage is combat_resolution.calculate_damage, (
            "rules.py shadows calculate_damage with a local definition"
        )

    def test_rules_imports_get_damage_multiplier_from_combat_resolution(self):
        import simcore.rules as rules
        from simcore import combat_resolution
        assert rules.get_damage_multiplier is combat_resolution.get_damage_multiplier, (
            "rules.py shadows get_damage_multiplier with a local definition"
        )

    def test_rules_imports_get_armor_type_from_combat_resolution(self):
        import simcore.rules as rules
        from simcore import combat_resolution
        assert rules.get_armor_type is combat_resolution.get_armor_type, (
            "rules.py shadows get_armor_type with a local definition"
        )
