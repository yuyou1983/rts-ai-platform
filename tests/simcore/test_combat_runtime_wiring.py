"""Tests for production unit construction preserving semantic combat bindings.

Task 4 of remediation plan: verify that _build_unit_entity() keeps weapon_id_ground,
armor_type, and spell_weapon_id from unit_stats.json — no manual field injection.
"""
import pytest
from pathlib import Path

from simcore.construction import _build_unit_entity


@pytest.mark.parametrize(
    ("unit_type", "weapon_id", "armor_type"),
    [
        ("Marine", "terran_c10_rifle", "light"),
        ("Vulture", "terran_fragmentation_grenade", "medium"),
        ("Tank", "terran_arclite_cannon", "heavy"),
        ("Firebat", "terran_flame_thrower", "light"),
        ("Zergling", "zerg_claws", "light"),
        ("Hydralisk", "zerg_needle_spines", "medium"),
        ("Ultralisk", "zerg_kaiser_blades", "heavy"),
        ("Mutalisk", "zerg_glave_wurm", "light"),
        ("Zealot", "protoss_psi_blades", "light"),
        ("Dragoon", "protoss_phase_disruptor", "heavy"),
        ("Reaver", "protoss_scarab", "heavy"),
    ],
)
def test_production_entity_keeps_combat_binding(unit_type, weapon_id, armor_type):
    """Production entities must carry semantic weapon_id and armor_type."""
    entity = _build_unit_entity("u1", unit_type, 1, "soldier", 0.0, 0.0)
    assert entity["weapon_id_ground"] == weapon_id, (
        f"{unit_type}: weapon_id_ground={entity.get('weapon_id_ground')} != {weapon_id}"
    )
    assert entity["armor_type"] == armor_type, (
        f"{unit_type}: armor_type={entity.get('armor_type')} != {armor_type}"
    )


def test_templar_keeps_spell_binding():
    """High Templar has null ground weapon and spell_weapon_id."""
    entity = _build_unit_entity("t1", "Templar", 1, "soldier", 0.0, 0.0)
    assert entity["weapon_id_ground"] is None
    assert entity["spell_weapon_id"] == "protoss_psionic_storm"


def test_marine_emits_semantic_weapon_id():
    """Production Marine attack must emit semantic weapon_id, not 'marine'."""
    from simcore.rules import resolve_combat
    from simcore.combat_events import IMPACT_RESOLVED

    attacker = _build_unit_entity("m", "Marine", 1, "soldier", 0.0, 0.0)
    target = _build_unit_entity("z", "Zergling", 2, "soldier", 1.0, 0.0)
    attacker["attack_target_id"] = "z"
    attacker["cooldown_timer"] = 999  # ready to fire
    events: list[dict] = []
    resolve_combat({"m": attacker, "z": target}, {}, [], 1, combat_events=events)
    # Only check the Marine's impacts — the Zergling auto-attacks back
    # with its own weapon_id, which is correct behaviour, not a bug.
    weapon_ids = {
        e.get("weapon_id") for e in events
        if e.get("event_type") == IMPACT_RESOLVED and e.get("attacker_id") == "m"
    }
    assert weapon_ids == {"terran_c10_rifle"}, (
        f"Expected {{'terran_c10_rifle'}}, got {weapon_ids}"
    )


def test_vulture_launch_does_not_damage_until_arrival():
    """Task 6: Vulture projectile must not deal damage on launch tick.

    A projectile entity should be created, and the target's HP/shield
    must be unchanged until process_projectiles() delivers the hit.
    """
    from simcore.rules import resolve_combat
    from simcore.combat_events import IMPACT_RESOLVED, PROJECTILE_SPAWNED

    attacker = _build_unit_entity("v", "Vulture", 1, "scout", 0.0, 0.0)
    target = _build_unit_entity("z", "Zealot", 2, "soldier", 4.0, 0.0)
    attacker["attack_target_id"] = "z"
    attacker["cooldown_timer"] = 999  # ready to fire
    before_hp = target["health"]
    before_shield = target["shields"]
    events: list[dict] = []
    launched, _ = resolve_combat({"v": attacker, "z": target}, {}, [], 1,
                                 combat_events=events)
    # Target must not be damaged on launch tick
    assert launched["z"]["health"] == before_hp, (
        f"HP changed on launch tick: {before_hp} -> {launched['z']['health']}"
    )
    assert launched["z"]["shields"] == before_shield, (
        f"Shield changed on launch tick: {before_shield} -> {launched['z']['shields']}"
    )
    # A projectile_spawned event must be emitted
    spawn_events = [e for e in events if e.get("event_type") == PROJECTILE_SPAWNED]
    assert len(spawn_events) >= 1, "No projectile_spawned event emitted"
    # No impact_resolved yet — damage comes later when projectile arrives
    impact_events = [e for e in events if e.get("event_type") == IMPACT_RESOLVED
                     and e.get("attacker_id") == "v"]
    assert len(impact_events) == 0, f"Damage applied on launch tick: {impact_events}"
    # A projectile entity must exist in the returned entities
    projectiles = [e for e in launched.values()
                   if e.get("projectile_type") or e.get("entity_type") == "projectile"]
    assert len(projectiles) >= 1, "No projectile entity created"


def test_ultralisk_melee_does_not_create_projectile():
    """Task 6: Melee weapons (Ultralisk) must not create projectile entities."""
    from simcore.rules import resolve_combat
    from simcore.combat_events import PROJECTILE_SPAWNED

    attacker = _build_unit_entity("u", "Ultralisk", 1, "soldier", 0.0, 0.0)
    target = _build_unit_entity("m", "Marine", 2, "soldier", 1.0, 0.0)
    attacker["attack_target_id"] = "m"
    attacker["cooldown_timer"] = 999
    events: list[dict] = []
    result, _ = resolve_combat({"u": attacker, "m": target}, {}, [], 1,
                              combat_events=events)
    # No projectile_spawned event for melee
    spawn_events = [e for e in events if e.get("event_type") == PROJECTILE_SPAWNED]
    assert len(spawn_events) == 0, f"Melee created projectile: {spawn_events}"
    # No projectile entities
    projectiles = [e for e in result.values()
                   if e.get("projectile_type") or e.get("entity_type") == "projectile"]
    assert len(projectiles) == 0, f"Melee created projectile entity: {projectiles}"
