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
