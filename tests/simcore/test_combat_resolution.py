"""Tests for simcore.combat_resolution — unified weapon impact resolution.

Tests the SC1 damage matrix rules:
- Shield absorbs first (no size multiplier on shield)
- Explosive vs light: 50% multiplier on health only
- Concussive vs heavy: 25% multiplier on health only
- Minimum damage rule
- Kill and miss event emission
"""
from __future__ import annotations

import pytest
from simcore.combat_resolution import (
    calculate_damage,
    get_armor_type,
    get_damage_multiplier,
    KillFeed,
    resolve_weapon_impact,
)
from simcore.combat_events import IMPACT_RESOLVED, UNIT_DESTROYED


# ─── Fixtures ───────────────────────────────────────────────


def _make_unit(
    uid: str = "u1",
    owner: int = 1,
    health: float = 100,
    shields: float = 0,
    armor: int = 0,
    armor_type: str = "medium",
    pos: tuple[float, float] = (0.0, 0.0),
) -> dict:
    return {
        "id": uid,
        "owner": owner,
        "health": health,
        "max_health": health,
        "shields": shields,
        "shield": shields,
        "armor": armor,
        "armor_type": armor_type,
        "pos_x": pos[0],
        "pos_y": pos[1],
        "entity_type": "soldier",
    }


def _make_attacker(
    uid: str = "a1",
    owner: int = 1,
    pos: tuple[float, float] = (0.0, 0.0),
) -> dict:
    return {
        "id": uid,
        "owner": owner,
        "health": 100,
        "max_health": 100,
        "pos_x": pos[0],
        "pos_y": pos[1],
        "entity_type": "soldier",
    }


# ─── Damage Matrix Tests ────────────────────────────────────


class TestDamageMatrix:
    def test_concussive_vs_light_full(self):
        """Concussive vs light: 100% damage."""
        assert get_damage_multiplier("concussive", "light") == 1.0

    def test_concussive_vs_medium_half(self):
        """Concussive vs medium: 50% damage."""
        assert get_damage_multiplier("concussive", "medium") == 0.5

    def test_concussive_vs_heavy_quarter(self):
        """Concussive vs heavy: 25% damage."""
        assert get_damage_multiplier("concussive", "heavy") == 0.25

    def test_explosive_vs_light_half(self):
        """Explosive vs light: 50% damage."""
        assert get_damage_multiplier("explosive", "light") == 0.5

    def test_explosive_vs_medium_75(self):
        """Explosive vs medium: 75% damage."""
        assert get_damage_multiplier("explosive", "medium") == 0.75

    def test_explosive_vs_heavy_full(self):
        """Explosive vs heavy: 100% damage."""
        assert get_damage_multiplier("explosive", "heavy") == 1.0

    def test_normal_vs_all_full(self):
        """Normal/independent: 100% to all sizes."""
        for at in ("light", "medium", "heavy"):
            assert get_damage_multiplier("normal", at) == 1.0
            assert get_damage_multiplier("independent", at) == 1.0


class TestCalculateDamage:
    def test_no_armor_full_damage(self):
        """Normal damage with 0 armor = full damage."""
        assert calculate_damage(20, "normal", 0, "medium") == 20.0

    def test_armor_reduces(self):
        """Armor subtracts from damage."""
        assert calculate_damage(20, "normal", 3, "medium") == 17.0

    def test_concussive_vs_heavy_with_armor(self):
        """Concussive vs heavy: 25% - armor, min 0.5."""
        dmg = calculate_damage(20, "concussive", 0, "heavy")
        assert dmg == pytest.approx(5.0)  # 20 * 0.25 = 5

    def test_explosive_vs_light_with_armor(self):
        """Explosive vs light: 50% - armor."""
        dmg = calculate_damage(20, "explosive", 0, "light")
        assert dmg == pytest.approx(10.0)  # 20 * 0.5 = 10

    def test_minimum_damage(self):
        """Damage cannot go below minDamage (0.5)."""
        dmg = calculate_damage(1, "concussive", 10, "heavy")
        # 1 * 0.25 - 10 = -9.75, but min is 0.5
        assert dmg == 0.5


# ─── Armor Type Detection ───────────────────────────────────


class TestArmorType:
    def test_explicit_armor_type(self):
        e = _make_unit(armor_type="light")
        assert get_armor_type(e) == "light"

    def test_building_is_heavy(self):
        e = {"entity_type": "building", "health": 100}
        assert get_armor_type(e) == "heavy"

    def test_marine_is_light(self):
        e = {"unit_type": "Marine", "entity_type": "soldier"}
        assert get_armor_type(e) == "light"

    def test_tank_is_heavy(self):
        """SiegeTank has armor_type='heavy' from unit_stats.json."""
        e = {"unit_type": "SiegeTank", "entity_type": "scout", "armor_type": "heavy"}
        assert get_armor_type(e) == "heavy"


# ─── Resolve Weapon Impact: Shield Logic ────────────────────


class TestShieldResolution:
    def test_shield_absorbs_all_no_health_damage(self):
        """20 damage vs 30 shield: only shield takes damage, no health loss."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=100, shields=30, armor_type="light"),
        }
        events: list[dict] = []
        kf = KillFeed()

        entities, removed = resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            base_damage=20,
            tick=5,
            combat_events=events,
            kill_feed=kf,
        )

        target = entities["t1"]
        assert target["shields"] == 10  # 30 - 20 = 10
        assert target["health"] == 100  # no health damage
        assert not removed  # not killed

        # Check event
        impact = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impact) == 1
        assert impact[0]["shield_damage"] == 20.0
        assert impact[0]["health_damage"] == 0.0
        assert impact[0]["final_damage"] == 20.0

    def test_shield_partial_penetration(self):
        """20 explosive vs 10 shield, 0 armor, light unit.
        Shield absorbs 10, remaining 10 → health with 50% (explosive vs light) = 5.
        """
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=100, shields=10, armor=0, armor_type="light"),
        }
        events: list[dict] = []

        entities, removed = resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_arclite_cannon",
            weapon_type="explosive",
            base_damage=20,
            tick=5,
            combat_events=events,
        )

        target = entities["t1"]
        assert target["shields"] == 0  # shield fully depleted
        assert target["health"] == 95  # 100 - 5 = 95

        impact = events[0]
        assert impact["shield_damage"] == 10.0
        assert impact["health_damage"] == 5.0
        assert impact["final_damage"] == 15.0

    def test_shield_no_size_multiplier(self):
        """20 explosive vs 30 shield light unit.
        Shield takes full 20 (no size multiplier), not 10 (50%).
        """
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=100, shields=30, armor=0, armor_type="light"),
        }
        events: list[dict] = []

        entities, _ = resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_arclite_cannon",
            weapon_type="explosive",
            base_damage=20,
            tick=5,
            combat_events=events,
        )

        target = entities["t1"]
        assert target["shields"] == 10  # 30 - 20 = 10 (full, not 50%)
        assert target["health"] == 100  # no penetration

    def test_concussive_vs_heavy_shield(self):
        """20 concussive vs 10 shield, 0 armor, heavy unit.
        Shield absorbs 10, remaining 10 → health with 25% (concussive vs heavy) = 2.5.
        """
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=100, shields=10, armor=0, armor_type="heavy"),
        }
        events: list[dict] = []

        entities, _ = resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_fragmentation_grenade",
            weapon_type="concussive",
            base_damage=20,
            tick=5,
            combat_events=events,
        )

        target = entities["t1"]
        assert target["shields"] == 0  # shield fully depleted
        assert target["health"] == pytest.approx(97.5)  # 100 - 2.5 = 97.5

        impact = events[0]
        assert impact["shield_damage"] == 10.0
        assert impact["health_damage"] == 2.5


# ─── Resolve Weapon Impact: Kill & Miss ────────────────────


class TestKillAndMiss:
    def test_kill_emits_unit_destroyed(self):
        """Lethal damage emits both impact_resolved and unit_destroyed."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=10, shields=0, armor_type="medium"),
        }
        events: list[dict] = []

        entities, removed = resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            base_damage=20,
            tick=5,
            combat_events=events,
        )

        assert "t1" in removed
        impact_events = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        death_events = [e for e in events if e["event_type"] == UNIT_DESTROYED]
        assert len(impact_events) == 1
        assert len(death_events) == 1
        assert impact_events[0]["killed"] is True

    def test_miss_emits_zero_damage(self):
        """Miss produces impact_resolved with missed=True and 0 damage."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=100, armor_type="medium"),
        }
        events: list[dict] = []

        entities, removed = resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            base_damage=20,
            tick=5,
            combat_events=events,
            missed=True,
        )

        assert not removed  # no kill on miss
        target = entities["t1"]
        assert target["health"] == 100  # no damage

        impact = events[0]
        assert impact["missed"] is True
        assert impact["final_damage"] == 0.0

    def test_kill_feed_tracked(self):
        """KillFeed tracks damage and kills."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=10, armor_type="medium"),
        }
        events: list[dict] = []
        kf = KillFeed()

        resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            base_damage=20,
            tick=5,
            combat_events=events,
            kill_feed=kf,
        )

        assert kf.kills[1] == 1
        assert kf.deaths[2] == 1
        assert kf.damage_dealt[1] > 0

    def test_final_damage_truncated_by_health(self):
        """final_damage = actual shield + actual health damage, not theoretical."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_unit("t1", owner=2, health=5, shields=0, armor_type="medium"),
        }
        events: list[dict] = []

        entities, _ = resolve_weapon_impact(
            entities,
            attacker_id="a1",
            target_id="t1",
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            base_damage=100,  # way more than target's 5 HP
            tick=5,
            combat_events=events,
        )

        impact = events[0]
        assert impact["health_damage"] == 5.0  # truncated to actual HP
        assert impact["final_damage"] == 5.0
