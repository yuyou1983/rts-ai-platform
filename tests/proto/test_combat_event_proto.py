"""Contract tests for CombatEvent field completeness (Task 8).

Every combat event must carry enough visual context for Godot to render
without looking up entity state:

  - source_owner / target_owner (player ids for color/faction)
  - source_x / source_y (attacker position for muzzle effect)
  - target_x / target_y (impact position for hit effect)
  - weapon_id (semantic weapon for VFX selection)
  - delivery_type (melee/hitscan/projectile/chain/area_periodic/tracking)

unit_destroyed events must NOT be bare 3-field dicts — they need positions
and owners so death VFX can play at the right location.
"""

import pytest
from simcore.rules import resolve_combat
from simcore.combat_resolution import resolve_weapon_impact
from simcore.combat_events import (
    IMPACT_RESOLVED,
    UNIT_DESTROYED,
    ATTACK_STARTED,
    PROJECTILE_SPAWNED,
)


# ── Helpers ──────────────────────────────────────────────────

def _marine(uid, owner=1, x=0.0, y=0.0, health=40, target_id="z1"):
    return {
        "id": uid, "owner": owner, "entity_type": "unit",
        "unit_type": "Marine", "health": health, "max_health": 40,
        "pos_x": x, "pos_y": y, "attack": 6, "attack_range": 4.0,
        "weapon_id_ground": "terran_c10_rifle",
        "weapon_id_air": "terran_c10_rifle",
        "armor_type": "light", "armor": 0,
        "cooldown_timer": 99, "cooldown_ground": 15, "cooldown_air": 15,
        "attack_target_id": target_id,
        "is_idle": False, "mp": 0, "energy": 0, "buffs": [],
    }


def _zealot(uid, owner=2, x=5.0, y=0.0, health=100, shields=60):
    return {
        "id": uid, "owner": owner, "entity_type": "unit",
        "unit_type": "Zealot", "health": health, "max_health": 100,
        "shields": shields, "max_shields": 60,
        "pos_x": x, "pos_y": y, "attack": 8, "attack_range": 1.0,
        "weapon_id_ground": "protoss_psi_blades",
        "weapon_id_air": "",
        "armor_type": "medium", "armor": 1,
        "cooldown_timer": 0, "attack_target_id": "",
        "is_idle": True, "mp": 0, "energy": 0, "buffs": [],
    }


# ── Impact events carry owner context ────────────────────────

class TestImpactEventContext:
    def test_impact_has_source_owner(self):
        """IMPACT_RESOLVED events must include source_owner."""
        entities = {
            "m1": _marine("m1", owner=1, x=0, y=0),
            "z1": _zealot("z1", owner=2, x=3, y=0, health=100, shields=0),
        }
        events = []
        resolve_combat(entities, {}, [], tick=1, combat_events=events)
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert impacts, "No impact events emitted"
        for imp in impacts:
            assert imp["source_owner"] == 1, f"source_owner missing on {imp['event_id']}"
            assert imp["target_owner"] == 2, f"target_owner missing on {imp['event_id']}"

    def test_impact_has_positions(self):
        """IMPACT_RESOLVED events must have non-zero source/target positions."""
        entities = {
            "m1": _marine("m1", owner=1, x=2.0, y=3.0),
            "z1": _zealot("z1", owner=2, x=5.0, y=3.0, health=100, shields=0),
        }
        events = []
        resolve_combat(entities, {}, [], tick=1, combat_events=events)
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert impacts
        for imp in impacts:
            assert (imp["source_x"], imp["source_y"]) == (2.0, 3.0)
            assert (imp["target_x"], imp["target_y"]) == (5.0, 3.0)


# ── Death events carry visual context ────────────────────────

class TestDeathEventContext:
    def test_death_event_has_visual_context(self):
        """unit_destroyed events must carry source_owner, target_owner, and position."""
        entities = {
            "m1": _marine("m1", owner=1, x=0, y=0),
            "z1": _zealot("z1", owner=2, x=3, y=0, health=1, shields=0),  # will die
        }
        events = []
        resolve_combat(entities, {}, [], tick=1, combat_events=events)
        deaths = [e for e in events if e["event_type"] == UNIT_DESTROYED]
        assert deaths, "No unit_destroyed events emitted"
        death = deaths[0]
        assert death["source_owner"] == 1, "Death event missing source_owner"
        assert death["target_owner"] == 2, "Death event missing target_owner"
        assert (death.get("target_x", 0.0), death.get("target_y", 0.0)) != (0.0, 0.0), \
            "Death event target position must be non-zero"

    def test_death_event_has_target_position(self):
        """unit_destroyed events must have target_x/target_y matching the dead unit."""
        entities = {
            "m1": _marine("m1", owner=1, x=4.0, y=8.0),
            "z1": _zealot("z1", owner=2, x=7.0, y=8.0, health=1, shields=0),
        }
        events = []
        resolve_combat(entities, {}, [], tick=1, combat_events=events)
        deaths = [e for e in events if e["event_type"] == UNIT_DESTROYED]
        assert deaths
        death = deaths[0]
        assert death["target_x"] == 7.0
        assert death["target_y"] == 8.0


# ── Proto round-trip ─────────────────────────────────────────

class TestProtoRoundTrip:
    def test_proto_has_owner_fields(self):
        """The generated proto must have source_owner and target_owner fields."""
        from simcore.proto_out.proto import state_pb2
        e = state_pb2.CombatEvent()
        field_names = {f.name for f in e.DESCRIPTOR.fields}
        assert "source_owner" in field_names
        assert "target_owner" in field_names

    def test_proto_round_trip_owner_fields(self):
        """Set and read source_owner/target_owner via proto."""
        from simcore.proto_out.proto import state_pb2
        e = state_pb2.CombatEvent()
        e.source_owner = 1
        e.target_owner = 2
        e.event_type = state_pb2.IMPACT_RESOLVED
        e.weapon_id = "terran_c10_rifle"
        assert e.source_owner == 1
        assert e.target_owner == 2
