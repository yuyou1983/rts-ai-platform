"""Integration tests: projectile → resolve_weapon_impact → combat events.

Verifies that process_projectiles now routes damage through the unified
resolve_weapon_impact path, producing proper combat events with shield,
armor, and size multiplier handling.
"""
from __future__ import annotations

import pytest
from simcore.projectile import create_projectile, process_projectiles
from simcore.combat_events import IMPACT_RESOLVED, UNIT_DESTROYED
from simcore.combat_resolution import KillFeed


def _make_target(
    uid: str = "t1",
    owner: int = 2,
    health: float = 100,
    shields: float = 0,
    armor: int = 0,
    armor_type: str = "medium",
    pos: tuple[float, float] = (10.0, 0.0),
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


class TestProjectileDamageResolution:
    """Projectile hits must go through resolve_weapon_impact."""

    def test_bullet_hits_emits_impact_event(self):
        """Instant bullet hit produces an impact_resolved combat event."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_target(health=100, armor_type="medium"),
        }
        proj = create_projectile(
            owner="a1",
            target_id="t1",
            pos_x=0.0, pos_y=0.0,
            speed=100,
            damage=20,
            damage_type="normal",
            projectile_type="bullet",
            tick=1, seq=1,
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            attacker_id="a1",
        )
        entities[proj["id"]] = proj

        events: list[dict] = []
        kf = KillFeed()

        result = process_projectiles(entities, 1, combat_events=events, kill_feed=kf)

        # Target should have taken 20 damage
        assert result["t1"]["health"] == 80

        # Should emit exactly one impact_resolved event
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impacts) == 1
        assert impacts[0]["final_damage"] == 20.0
        assert impacts[0]["missed"] is False
        assert impacts[0]["weapon_id"] == "terran_c10_rifle"

    def test_projectile_shield_absorption(self):
        """Projectile damage hits shield first, then health."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_target(health=100, shields=30, armor_type="light"),
        }
        proj = create_projectile(
            owner="a1",
            target_id="t1",
            pos_x=0.0, pos_y=0.0,
            speed=100,
            damage=20,
            damage_type="normal",
            projectile_type="bullet",
            tick=1, seq=1,
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            attacker_id="a1",
        )
        entities[proj["id"]] = proj

        events: list[dict] = []
        result = process_projectiles(entities, 1, combat_events=events)

        target = result["t1"]
        assert target["shields"] == 10  # 30 - 20 = 10
        assert target["health"] == 100   # no health damage

        impact = events[0]
        assert impact["shield_damage"] == 20.0
        assert impact["health_damage"] == 0.0

    def test_projectile_explosive_vs_light(self):
        """Explosive projectile vs light: 50% multiplier on health portion."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_target(health=100, shields=10, armor=0, armor_type="light"),
        }
        proj = create_projectile(
            owner="a1",
            target_id="t1",
            pos_x=0.0, pos_y=0.0,
            speed=100,
            damage=20,
            damage_type="explosive",
            projectile_type="bullet",
            tick=1, seq=1,
            weapon_id="terran_arclite_cannon",
            weapon_type="explosive",
            attacker_id="a1",
        )
        entities[proj["id"]] = proj

        events: list[dict] = []
        result = process_projectiles(entities, 1, combat_events=events)

        target = result["t1"]
        assert target["shields"] == 0   # shield depleted
        assert target["health"] == 95   # 100 - (10 * 0.5) = 95

    def test_projectile_kill_emits_unit_destroyed(self):
        """Lethal projectile hit emits both impact_resolved and unit_destroyed."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_target(health=10, armor_type="medium"),
        }
        proj = create_projectile(
            owner="a1",
            target_id="t1",
            pos_x=0.0, pos_y=0.0,
            speed=100,
            damage=20,
            damage_type="normal",
            projectile_type="bullet",
            tick=1, seq=1,
            weapon_id="terran_c10_rifle",
            weapon_type="normal",
            attacker_id="a1",
        )
        entities[proj["id"]] = proj

        events: list[dict] = []
        kf = KillFeed()

        result = process_projectiles(entities, 1, combat_events=events, kill_feed=kf)

        # Target should be removed
        assert "t1" not in result

        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        deaths = [e for e in events if e["event_type"] == UNIT_DESTROYED]
        assert len(impacts) == 1
        assert len(deaths) == 1
        assert impacts[0]["killed"] is True
        assert kf.kills[1] == 1

    def test_tracking_projectile_delayed_hit(self):
        """Non-instant projectile travels then hits on a subsequent tick."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_target(health=100, pos=(9.0, 0.0), armor_type="medium"),
        }
        proj = create_projectile(
            owner="a1",
            target_id="t1",
            pos_x=0.0, pos_y=0.0,
            speed=3.0,
            damage=20,
            damage_type="normal",
            projectile_type="missile",
            tick=1, seq=1,
            weapon_id="terran_goliath_missiles",
            weapon_type="normal",
            attacker_id="a1",
        )
        entities[proj["id"]] = proj

        all_events: list[dict] = []

        # Run ticks until the missile hits (should take ~4 ticks at speed 3)
        result = entities
        for t in range(1, 10):
            tick_events: list[dict] = []
            result = process_projectiles(result, t, combat_events=tick_events)
            all_events.extend(tick_events)
            if "t1" not in result:
                break

        # Target should be hit by now
        impacts = [e for e in all_events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impacts) >= 1
        assert impacts[0]["final_damage"] == 20.0

    def test_deterministic_projectile_id(self):
        """Projectile IDs are deterministic: proj_{tick}_{seq}."""
        proj1 = create_projectile(
            "a1", "t1", 0, 0, 10, 20, "normal",
            tick=5, seq=1,
        )
        proj2 = create_projectile(
            "a1", "t2", 0, 0, 10, 20, "normal",
            tick=5, seq=2,
        )
        proj3 = create_projectile(
            "a1", "t3", 0, 0, 10, 20, "normal",
            tick=6, seq=1,
        )
        assert proj1["id"] == "proj_5_1"
        assert proj2["id"] == "proj_5_2"
        assert proj3["id"] == "proj_6_1"

    def test_projectile_no_target_self_destructs(self):
        """Projectile with missing target self-destructs after timeout."""
        entities = {
            "a1": _make_attacker(),
            "t1": _make_target(health=100, pos=(100.0, 0.0)),
        }
        proj = create_projectile(
            owner="a1",
            target_id="t1",
            pos_x=0.0, pos_y=0.0,
            speed=1.0,
            damage=20,
            damage_type="normal",
            projectile_type="missile",
            tick=1, seq=1,
        )
        entities[proj["id"]] = proj

        # Remove target
        del entities["t1"]

        events: list[dict] = []
        result = process_projectiles(entities, 1, combat_events=events)

        # No impact events — target was gone
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impacts) == 0

        # Projectile should be removed
        proj_ids = [eid for eid in result if eid.startswith("proj_")]
        assert len(proj_ids) == 0
