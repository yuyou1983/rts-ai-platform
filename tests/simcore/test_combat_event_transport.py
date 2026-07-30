"""Task 5: Combat event transport tests through gRPC/HTTP/replay pipeline.

Tests that combat events survive the full proto round-trip:
  dict → proto (server) → wire → proto (client) → dict
and that replay snapshots include combat_events.
"""
from __future__ import annotations

import pytest

from simcore.proto_out.proto import state_pb2
from simcore.grpc_server import SimCoreServicer, _EVENT_TYPE_TO_PROTO, _append_combat_events
from simcore.grpc_client import SimCoreClient


# ── Test data ────────────────────────────────────────────────
SAMPLE_EVENT = {
    "event_id": "9:0",
    "tick": 9,
    "event_type": "impact_resolved",
    "attacker_id": "m1",
    "target_id": "z1",
    "weapon_id": "terran_c10_rifle",
    "source_x": 1.0,
    "source_y": 2.0,
    "target_x": 3.0,
    "target_y": 4.0,
    "delivery_type": "hitscan",
    "weapon_type": "normal",
    "armor_type": "light",
    "base_damage": 6.0,
    "final_damage": 6.0,
    "damage_multiplier": 1.0,
    "shield_damage": 0.0,
    "health_damage": 6.0,
    "projectile_id": "",
    "chain_index": 0,
    "is_splash": False,
    "splash_fraction": 1.0,
    "killed": False,
    "missed": False,
    "armor_value": 0.0,
    "shield_armor_value": 0.0,
    "hit_index": 0,
    "hit_count": 1,
}


class TestEventTypeMap:
    """Test the event type string→proto enum mapping."""

    def test_all_types_mapped(self):
        assert _EVENT_TYPE_TO_PROTO["attack_started"] == state_pb2.ATTACK_STARTED
        assert _EVENT_TYPE_TO_PROTO["projectile_spawned"] == state_pb2.PROJECTILE_SPAWNED
        assert _EVENT_TYPE_TO_PROTO["impact_resolved"] == state_pb2.IMPACT_RESOLVED
        assert _EVENT_TYPE_TO_PROTO["unit_destroyed"] == state_pb2.UNIT_DESTROYED
        assert _EVENT_TYPE_TO_PROTO["spell_resolved"] == state_pb2.SPELL_RESOLVED

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown combat event type"):
            _append_combat_events(state_pb2.GameStateSnapshot(), [{"event_type": "bogus"}])


class TestProtoRoundTrip:
    """Test dict → proto → dict round-trip preserves all fields."""

    def test_full_round_trip(self):
        """Server converts dict→proto, client converts proto→dict."""
        # Server side: dict → proto
        proto = state_pb2.GameStateSnapshot()
        _append_combat_events(proto, [SAMPLE_EVENT])
        assert len(proto.combat_events) == 1

        # Client side: proto → dict
        result = SimCoreClient._snapshot_to_dict(proto)
        assert "combat_events" in result
        assert len(result["combat_events"]) == 1

        ev = result["combat_events"][0]
        assert ev["event_id"] == "9:0"
        assert ev["tick"] == 9
        assert ev["event_type"] == "impact_resolved"
        assert ev["attacker_id"] == "m1"
        assert ev["target_id"] == "z1"
        assert ev["weapon_id"] == "terran_c10_rifle"
        assert ev["delivery_type"] == "hitscan"
        assert ev["weapon_type"] == "normal"
        assert ev["armor_type"] == "light"
        assert ev["base_damage"] == 6.0
        assert ev["final_damage"] == 6.0
        assert ev["damage_multiplier"] == 1.0
        assert ev["shield_damage"] == 0.0
        assert ev["health_damage"] == 6.0
        assert ev["chain_index"] == 0
        assert ev["is_splash"] is False
        assert ev["splash_fraction"] == 1.0
        assert ev["killed"] is False
        assert ev["missed"] is False
        assert ev["armor_value"] == 0.0
        assert ev["shield_armor_value"] == 0.0
        assert ev["hit_index"] == 0
        assert ev["hit_count"] == 1

    def test_multiple_events_round_trip(self):
        """Multiple events survive round-trip in order."""
        events = [
            {**SAMPLE_EVENT, "event_id": "5:0", "event_type": "attack_started"},
            {**SAMPLE_EVENT, "event_id": "5:1", "event_type": "impact_resolved", "killed": True},
            {**SAMPLE_EVENT, "event_id": "5:2", "event_type": "unit_destroyed", "weapon_id": ""},
        ]
        proto = state_pb2.GameStateSnapshot()
        _append_combat_events(proto, events)
        result = SimCoreClient._snapshot_to_dict(proto)
        assert len(result["combat_events"]) == 3
        assert result["combat_events"][0]["event_id"] == "5:0"
        assert result["combat_events"][1]["event_id"] == "5:1"
        assert result["combat_events"][2]["event_id"] == "5:2"
        assert result["combat_events"][1]["killed"] is True

    def test_empty_events(self):
        """Snapshot with no combat events works correctly."""
        proto = state_pb2.GameStateSnapshot()
        result = SimCoreClient._snapshot_to_dict(proto)
        assert "combat_events" in result
        assert result["combat_events"] == []


class TestSnapshotDictToProto:
    """Test _snapshot_dict_to_proto forwards combat_events from replay dicts."""

    def test_replay_dict_with_combat_events(self):
        """Replay snapshots with combat_events are converted to proto correctly."""
        snap_dict = {
            "tick": 42,
            "entities": {},
            "combat_events": [SAMPLE_EVENT],
        }
        proto = SimCoreServicer._snapshot_dict_to_proto(snap_dict)
        assert len(proto.combat_events) == 1
        assert proto.combat_events[0].event_id == "9:0"
        assert proto.combat_events[0].weapon_id == "terran_c10_rifle"

    def test_replay_dict_without_combat_events(self):
        """Replay dicts without combat_events don't crash."""
        snap_dict = {"tick": 42, "entities": {}}
        proto = SimCoreServicer._snapshot_dict_to_proto(snap_dict)
        assert len(proto.combat_events) == 0


class TestTickRateDefault:
    """Ensure the 10 TPS contract is maintained."""

    def test_client_start_game_tick_rate_default(self):
        """SimCoreClient.start_game() default tick_rate should be 10.0, not 20.0."""
        import inspect
        sig = inspect.signature(SimCoreClient.start_game)
        tick_rate_param = sig.parameters.get("tick_rate")
        assert tick_rate_param is not None
        assert tick_rate_param.default == 10.0, f"tick_rate default is {tick_rate_param.default}, expected 10.0"
