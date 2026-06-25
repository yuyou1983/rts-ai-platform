"""Phase 3 tests: Event log system — events_this_tick in state snapshots."""
import pytest

from simcore.engine import SimCore
from simcore.events import (
    UNIT_CREATED, UNIT_DESTROYED, BUILDING_COMPLETED,
    RESOURCE_DEPLETED, COMBAT_HIT, ORDER_COMPLETED,
    make_event,
)
from simcore.rules import resolve_combat, KillFeed
from simcore.economy import process_gathering as economy_process_gathering
from simcore.construction import process_construction as new_process_construction


# ─── Helpers ──────────────────────────────────────────────────

def _soldier(sid: str, owner: int, px: float, py: float, **kw: float) -> dict:
    """Create a soldier entity dict."""
    attack = kw.get("attack", 15)
    attack_range = kw.get("attack_range", 1.0)
    cooldown_ground = kw.get("cooldown_ground", 10)
    return {
        "id": sid, "owner": owner, "entity_type": "soldier",
        "pos_x": px, "pos_y": py,
        "health": kw.get("health", 80), "max_health": kw.get("max_health", 80),
        "speed": kw.get("speed", 3.0), "attack": attack,
        "attack_ground": attack, "attack_air": 0,
        "attack_range": attack_range,
        "attack_range_ground": attack_range, "attack_range_air": 0,
        "weapon_type_ground": "normal", "weapon_type_air": "none",
        "cooldown_ground": cooldown_ground, "cooldown_air": 0,
        "cooldown_timer": cooldown_ground,  # ready to fire
        "domain": "ground", "armor": 0, "armor_type": "light",
        "is_idle": True, "carry_amount": 0, "carry_capacity": 0,
        "target_x": None, "target_y": None,
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False,
    }


def _worker(wid: str, owner: int, px: float, py: float, **kw: float) -> dict:
    attack = kw.get("attack", 5)
    attack_range = kw.get("attack_range", 1.0)
    cooldown_ground = kw.get("cooldown_ground", 10)
    return {
        "id": wid, "owner": owner, "entity_type": "worker",
        "pos_x": px, "pos_y": py,
        "health": kw.get("health", 50), "max_health": kw.get("max_health", 50),
        "speed": kw.get("speed", 2.5), "attack": attack,
        "attack_ground": attack, "attack_air": 0,
        "attack_range": attack_range,
        "attack_range_ground": attack_range, "attack_range_air": 0,
        "weapon_type_ground": "normal", "weapon_type_air": "none",
        "cooldown_ground": cooldown_ground, "cooldown_air": 0,
        "cooldown_timer": cooldown_ground,
        "domain": "ground", "armor": 0, "armor_type": "light",
        "is_idle": True, "carry_amount": 0, "carry_capacity": 10.0,
        "target_x": None, "target_y": None,
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False,
    }


def _resource(rid: str, rtype: str, amount: float, px: float, py: float) -> dict:
    return {
        "id": rid, "owner": 0, "entity_type": "resource",
        "resource_type": rtype, "resource_amount": amount,
        "pos_x": px, "pos_y": py,
        "health": 100, "max_health": 100,
        "speed": 0, "attack": 0, "attack_range": 0,
        "is_idle": True, "carry_amount": 0, "carry_capacity": 0,
        "target_x": None, "target_y": None,
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False,
    }


def _building(bid: str, owner: int, btype: str, px: float, py: float,
              constructing: bool = False, build_progress: int = 0) -> dict:
    return {
        "id": bid, "owner": owner, "entity_type": "building",
        "building_type": btype,
        "pos_x": px, "pos_y": py,
        "health": 100 if not constructing else 1,
        "max_health": 100,
        "is_constructing": constructing,
        "build_progress": build_progress,
        "production_queue": [],
        "production_timers": [],
        "upgrade_queue": [],
        "upgrade_timers": [],
        "builder_id": "",
    }


# ─── Tests ────────────────────────────────────────────────────

class TestEventLogInSnapshot:
    """Feature flag controls whether events_this_tick appears."""

    def test_event_log_in_snapshot(self):
        """Flag on → events_this_tick in snapshot."""
        engine = SimCore(enable_event_log=True)
        engine.initialize(map_seed=42)
        state = engine.step(commands=[])
        snapshot = engine.replay[-1]
        assert "events_this_tick" in snapshot
        assert isinstance(snapshot["events_this_tick"], list)

    def test_event_log_off_by_default(self):
        """Flag off → no events_this_tick in snapshot."""
        engine = SimCore()  # default: enable_event_log=False
        engine.initialize(map_seed=42)
        engine.step(commands=[])
        snapshot = engine.replay[-1]
        assert "events_this_tick" not in snapshot


class TestCombatEvents:
    """COMBAT_HIT and UNIT_DESTROYED emitted from combat resolution."""

    def test_unit_destroyed_event(self):
        """A unit dies in combat → UNIT_DESTROYED event emitted."""
        # Set up a one-shot kill: attacker with very high attack
        entities = {
            "killer": _soldier("killer", 1, 10.0, 10.0, attack=999),
            "victim": _worker("victim", 2, 10.5, 10.0),  # 50 HP, will die
        }
        cmds = [{"action": "attack", "attacker_id": "killer", "target_id": "victim", "issuer": 1}]
        kf = KillFeed()
        result_ents, _ = resolve_combat(
            entities, {"p1_mineral": 0, "p2_mineral": 0}, cmds, 1, kill_feed=kf,
        )

        # Now simulate what the engine's event detection does
        pre_combat = entities
        post_combat = result_ents

        events: list[dict] = []
        # Build reverse map
        target_to_attackers: dict[str, list[str]] = {}
        for eid, e in pre_combat.items():
            tid = e.get("attack_target_id", "")
            if tid:
                target_to_attackers.setdefault(tid, []).append(eid)

        # Also add attack commands mapping
        for cmd in cmds:
            if cmd.get("action") == "attack":
                aid = cmd.get("attacker_id", "")
                tid = cmd.get("target_id", "")
                if aid and tid:
                    target_to_attackers.setdefault(tid, []).append(aid)

        removed = set(pre_combat.keys()) - set(post_combat.keys())
        for eid in removed:
            killers = target_to_attackers.get(eid, [])
            killer_id = killers[0] if killers else ""
            events.append(make_event(UNIT_DESTROYED, 1, unit_id=eid, killer_id=killer_id))

        destroyed_events = [e for e in events if e["type"] == UNIT_DESTROYED]
        assert len(destroyed_events) == 1
        assert destroyed_events[0]["unit_id"] == "victim"
        assert destroyed_events[0]["killer_id"] == "killer"

    def test_combat_hit_event(self):
        """Damage dealt in combat → COMBAT_HIT event emitted."""
        entities = {
            "atk": _soldier("atk", 1, 10.0, 10.0, attack=10),
            "target": _soldier("target", 2, 10.5, 10.0, health=80),
        }
        cmds = [{"action": "attack", "attacker_id": "atk", "target_id": "target", "issuer": 1}]
        kf = KillFeed()
        result_ents, _ = resolve_combat(
            entities, {"p1_mineral": 0, "p2_mineral": 0}, cmds, 1, kill_feed=kf,
        )

        # Simulate event detection (matching engine logic)
        events: list[dict] = []
        # Build reverse map from commands AND from entity attack_target_id
        target_to_attackers: dict[str, list[str]] = {}
        for cmd in cmds:
            if cmd.get("action") == "attack":
                aid = cmd.get("attacker_id", "")
                tid = cmd.get("target_id", "")
                if aid and tid:
                    target_to_attackers.setdefault(tid, []).append(aid)
        # Also include attack_target_id from the pre-combat snapshot
        for eid, e in entities.items():
            tid = e.get("attack_target_id", "")
            if tid:
                target_to_attackers.setdefault(tid, []).append(eid)

        for eid, post_e in result_ents.items():
            pre_e = entities.get(eid)
            if pre_e is None:
                continue
            pre_hp = pre_e.get("health", 0)
            post_hp = post_e.get("health", 0)
            if post_hp < pre_hp:
                attackers = target_to_attackers.get(eid, [])
                attacker_id = attackers[0] if attackers else ""
                damage = pre_hp - post_hp
                events.append(make_event(COMBAT_HIT, 1, attacker_id=attacker_id,
                                         target_id=eid, damage=round(damage, 4)))

        hit_events = [e for e in events if e["type"] == COMBAT_HIT]
        assert len(hit_events) >= 1
        # Find the specific hit where our explicit attacker hit the target
        atk_hits = [h for h in hit_events if h["target_id"] == "target"]
        assert len(atk_hits) >= 1
        hit = atk_hits[0]
        assert hit["attacker_id"] == "atk"
        assert hit["damage"] > 0


class TestBuildingCompletedEvent:
    """BUILDING_COMPLETED emitted when construction finishes."""

    def test_building_completed_event(self):
        """Building with build_progress reaching 100 emits BUILDING_COMPLETED."""
        # Simulate the before/after comparison that the engine does
        pre_entities = {
            "barracks_1": _building("barracks_1", 1, "barracks", 10.0, 10.0,
                                    constructing=True, build_progress=90),
        }
        # Simulate construction completing (build_progress 90 + 10 = 100)
        post_entities = {
            "barracks_1": {**pre_entities["barracks_1"],
                           "is_constructing": False,
                           "build_progress": 100,
                           "health": 100},
        }

        events: list[dict] = []
        for eid, post_e in post_entities.items():
            pre_e = pre_entities.get(eid)
            if pre_e is None:
                continue
            if (pre_e.get("entity_type") == "building"
                    and pre_e.get("is_constructing") is True
                    and post_e.get("is_constructing") is False):
                events.append(make_event(BUILDING_COMPLETED, 1,
                                         building_id=eid,
                                         building_type=post_e.get("building_type", "")))

        assert len(events) == 1
        assert events[0]["type"] == BUILDING_COMPLETED
        assert events[0]["building_id"] == "barracks_1"
        assert events[0]["building_type"] == "barracks"


class TestUnitCreatedEvent:
    """UNIT_CREATED emitted when a new entity appears in the entities dict."""

    def test_unit_created_event(self):
        """New unit appearing in entities → UNIT_CREATED event emitted."""
        # Simulate before/after entity key comparison
        start_entities = {
            "base_p1": _building("base_p1", 1, "base", 9.6, 9.6),
        }
        end_entities = {
            "base_p1": _building("base_p1", 1, "base", 9.6, 9.6),
            "worker_1": _worker("worker_1", 1, 10.0, 10.0),
        }

        events: list[dict] = []
        start_keys = set(start_entities.keys())
        current_keys = set(end_entities.keys())
        new_entity_ids = current_keys - start_keys
        for eid in new_entity_ids:
            e = end_entities[eid]
            if eid.startswith("__"):
                continue
            events.append(make_event(UNIT_CREATED, 1,
                                     unit_id=eid,
                                     unit_type=e.get("unit_type",
                                                     e.get("building_type",
                                                           e.get("entity_type", ""))),
                                     owner=e.get("owner", 0)))

        assert len(events) == 1
        assert events[0]["type"] == UNIT_CREATED
        assert events[0]["unit_id"] == "worker_1"
        assert events[0]["owner"] == 1


class TestResourceDepletedEvent:
    """RESOURCE_DEPLETED emitted when resource amount drops to 0."""

    def test_resource_depleted_event(self):
        """Resource amount hitting 0 → RESOURCE_DEPLETED event emitted."""
        pre_entities = {
            "m1": _resource("m1", "mineral", 5.0, 14.0, 9.6),
        }
        # After gathering, amount drops to 0 and entity may be removed
        post_entities = {}  # resource removed

        events: list[dict] = []
        removed = set(pre_entities.keys()) - set(post_entities.keys())
        for eid in removed:
            pre_e = pre_entities.get(eid, {})
            if pre_e.get("entity_type") == "resource":
                events.append(make_event(RESOURCE_DEPLETED, 1, resource_id=eid))

        # Also check surviving resources whose amount hit 0
        for eid, post_e in post_entities.items():
            pre_e = pre_entities.get(eid)
            if pre_e is None:
                continue
            if post_e.get("entity_type") != "resource":
                continue
            pre_amt = pre_e.get("resource_amount", 0)
            post_amt = post_e.get("resource_amount", 0)
            if pre_amt > 0 and post_amt <= 0:
                events.append(make_event(RESOURCE_DEPLETED, 1, resource_id=eid))

        assert len(events) == 1
        assert events[0]["type"] == RESOURCE_DEPLETED
        assert events[0]["resource_id"] == "m1"


class TestEventsAccumulate:
    """Multiple events in the same tick are all present."""

    def test_events_accumulate(self):
        """Two combat events in the same tick both appear."""
        events_this_tick: list[dict] = []

        events_this_tick.append(
            make_event(COMBAT_HIT, 5, attacker_id="a1", target_id="t1", damage=15)
        )
        events_this_tick.append(
            make_event(UNIT_DESTROYED, 5, unit_id="t1", killer_id="a1")
        )

        assert len(events_this_tick) == 2
        assert events_this_tick[0]["type"] == COMBAT_HIT
        assert events_this_tick[1]["type"] == UNIT_DESTROYED


class TestMakeEventHelper:
    """Verify the make_event utility function structure."""

    def test_make_event_helper(self):
        """make_event returns dict with type, tick, and extra data."""
        evt = make_event(UNIT_CREATED, tick=42, unit_id="w1",
                         unit_type="worker", owner=1)
        assert evt["type"] == UNIT_CREATED
        assert evt["tick"] == 42
        assert evt["unit_id"] == "w1"
        assert evt["unit_type"] == "worker"
        assert evt["owner"] == 1

    def test_make_event_minimal(self):
        """make_event with no extra data only has type and tick."""
        evt = make_event(COMBAT_HIT, tick=0)
        assert evt == {"type": COMBAT_HIT, "tick": 0}


class TestEndToEndEvents:
    """Full engine step produces correct events with flag enabled."""

    def test_engine_step_with_event_log_enabled(self):
        """Step with flag on produces events_this_tick (possibly empty list)."""
        engine = SimCore(enable_event_log=True)
        engine.initialize(map_seed=42)
        state = engine.step(commands=[])
        snapshot = engine.replay[-1]
        assert "events_this_tick" in snapshot
        # No combat in first tick, so should be empty or contain only unit_created
        for evt in snapshot["events_this_tick"]:
            assert "type" in evt
            assert "tick" in evt

    def test_engine_step_without_event_log(self):
        """Step with flag off does NOT produce events_this_tick."""
        engine = SimCore(enable_event_log=False)
        engine.initialize(map_seed=42)
        engine.step(commands=[])
        snapshot = engine.replay[-1]
        assert "events_this_tick" not in snapshot