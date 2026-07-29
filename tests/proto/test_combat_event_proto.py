"""Protobuf schema and round-trip regression for CombatEvent.

Task 3 of the SC1 combat differentiation plan: the GameStateSnapshot must
carry a repeated ``CombatEvent`` field so SimCore can surface authoritative
combat facts (weapon, hit, shield, splash, chain, death) to Godot and replay.
"""

from __future__ import annotations

import pytest

from simcore.proto_out.proto import state_pb2


def _make_impact_event() -> "state_pb2.CombatEvent":
    """Build a canonical IMPACT_RESOLVED event for a Marine vs Zergling hit."""
    return state_pb2.CombatEvent(
        event_id="42:3",
        tick=42,
        event_type=state_pb2.IMPACT_RESOLVED,
        attacker_id="marine_1",
        target_id="zergling_1",
        weapon_id="terran_c10_rifle",
        source_x=10.0,
        source_y=12.0,
        target_x=14.0,
        target_y=12.0,
        delivery_type="hitscan",
        weapon_type="normal",
        armor_type="light",
        base_damage=6.0,
        final_damage=6.0,
        damage_multiplier=1.0,
        health_damage=6.0,
        armor_value=0.0,
        shield_armor_value=0.0,
        hit_index=0,
        hit_count=1,
    )


def test_combat_event_round_trip_preserves_fields():
    """A CombatEvent serialized inside a snapshot survives a round trip."""
    event = _make_impact_event()
    snapshot = state_pb2.GameStateSnapshot(combat_events=[event])
    decoded = state_pb2.GameStateSnapshot.FromString(snapshot.SerializeToString())

    assert decoded.combat_events[0].weapon_id == "terran_c10_rifle"
    assert decoded.combat_events[0].hit_count == 1


def test_combat_event_impact_resolved_enum_value():
    """IMPACT_RESOLVED is a distinct CombatEventType enum value."""
    assert state_pb2.IMPACT_RESOLVED != state_pb2.COMBAT_EVENT_UNSPECIFIED
    assert state_pb2.IMPACT_RESOLVED == 3


def test_all_combat_event_types_exist():
    """All five CombatEventType variants plus UNSPECIFIED are defined."""
    expected = {
        "COMBAT_EVENT_UNSPECIFIED": 0,
        "ATTACK_STARTED": 1,
        "PROJECTILE_SPAWNED": 2,
        "IMPACT_RESOLVED": 3,
        "UNIT_DESTROYED": 4,
        "SPELL_RESOLVED": 5,
    }
    actual = {
        name: value
        for name, value in state_pb2.CombatEventType.items()
        if name in expected
    }
    assert actual == expected


def test_combat_event_full_field_round_trip():
    """Every declared field survives serialization with its set value."""
    event = state_pb2.CombatEvent(
        event_id="7:0",
        tick=7,
        event_type=state_pb2.UNIT_DESTROYED,
        attacker_id="zealot_1",
        target_id="marine_2",
        weapon_id="protoss_psi_blades",
        source_x=1.5,
        source_y=2.5,
        target_x=3.5,
        target_y=4.5,
        delivery_type="melee",
        weapon_type="normal",
        armor_type="medium",
        base_damage=16.0,
        final_damage=16.0,
        damage_multiplier=1.0,
        shield_damage=0.0,
        health_damage=16.0,
        projectile_id="",
        chain_index=0,
        is_splash=False,
        splash_fraction=0.0,
        killed=True,
        missed=False,
        armor_value=1.0,
        shield_armor_value=0.0,
        hit_index=0,
        hit_count=2,
    )
    snapshot = state_pb2.GameStateSnapshot(combat_events=[event])
    decoded = state_pb2.GameStateSnapshot.FromString(snapshot.SerializeToString())
    ev = decoded.combat_events[0]

    assert ev.event_id == "7:0"
    assert ev.tick == 7
    assert ev.event_type == state_pb2.UNIT_DESTROYED
    assert ev.attacker_id == "zealot_1"
    assert ev.target_id == "marine_2"
    assert ev.weapon_id == "protoss_psi_blades"
    assert ev.source_x == pytest.approx(1.5)
    assert ev.source_y == pytest.approx(2.5)
    assert ev.target_x == pytest.approx(3.5)
    assert ev.target_y == pytest.approx(4.5)
    assert ev.delivery_type == "melee"
    assert ev.weapon_type == "normal"
    assert ev.armor_type == "medium"
    assert ev.base_damage == pytest.approx(16.0)
    assert ev.final_damage == pytest.approx(16.0)
    assert ev.damage_multiplier == pytest.approx(1.0)
    assert ev.shield_damage == pytest.approx(0.0)
    assert ev.health_damage == pytest.approx(16.0)
    assert ev.projectile_id == ""
    assert ev.chain_index == 0
    assert ev.is_splash is False
    assert ev.splash_fraction == pytest.approx(0.0)
    assert ev.killed is True
    assert ev.missed is False
    assert ev.armor_value == pytest.approx(1.0)
    assert ev.shield_armor_value == pytest.approx(0.0)
    assert ev.hit_index == 0
    assert ev.hit_count == 2


def test_multiple_combat_events_preserve_order():
    """Repeated events keep their insertion order across serialization."""
    events = [
        state_pb2.CombatEvent(event_id="5:0", tick=5, event_type=state_pb2.ATTACK_STARTED),
        state_pb2.CombatEvent(event_id="5:1", tick=5, event_type=state_pb2.PROJECTILE_SPAWNED),
        state_pb2.CombatEvent(event_id="5:2", tick=5, event_type=state_pb2.IMPACT_RESOLVED),
    ]
    snapshot = state_pb2.GameStateSnapshot(combat_events=events)
    decoded = state_pb2.GameStateSnapshot.FromString(snapshot.SerializeToString())

    assert [e.event_id for e in decoded.combat_events] == ["5:0", "5:1", "5:2"]
    assert [e.event_type for e in decoded.combat_events] == [
        state_pb2.ATTACK_STARTED,
        state_pb2.PROJECTILE_SPAWNED,
        state_pb2.IMPACT_RESOLVED,
    ]


def test_snapshot_without_combat_events_defaults_empty():
    """A snapshot with no combat events round-trips to an empty list."""
    snapshot = state_pb2.GameStateSnapshot(game_tick=1)
    decoded = state_pb2.GameStateSnapshot.FromString(snapshot.SerializeToString())
    assert list(decoded.combat_events) == []
