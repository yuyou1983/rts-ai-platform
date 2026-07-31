"""Task 13: End-to-end combat visual event tests.

Verifies that ``resolve_combat`` emits well-formed, ordered, unique, and
deterministic combat events across all three races.

Coverage:
    1. E2E combat event pipeline (Marine vs Zergling) — attack_started +
       impact_resolved present, weapon_id preserved, damage fields correct,
       event_ids unique, events ordered.
    2. Determinism — the same matchup run in two separate subprocesses with
       different ``PYTHONHASHSEED`` values (1 and 999) produces byte-identical
       serialized combat events (same types, order, damage, IDs, targets).
    3. Multi-unit determinism — a 6 Mutalisk vs 10 Marine matchup run in two
       subprocesses with different ``PYTHONHASHSEED`` produces identical chain
       bounce target selection.
    4. Event completeness — one matchup per race (Terran/Zerg/Protoss) emits
       impact_resolved events with every expected field present and non-null.

Determinism tests use ``subprocess.run`` so that ``PYTHONHASHSEED`` (which is
fixed at interpreter startup and cannot be changed mid-process) can be
controlled per run.  This avoids in-process hash-seed contamination.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from simcore.combat_events import ATTACK_STARTED, IMPACT_RESOLVED
from simcore.rules import resolve_combat

# Tests in this directory exercise combat via subprocesses; group them with the
# rest of the integration bucket.  Running the file by path still runs them
# regardless of the marker.
pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Fields every impact_resolved event must carry (from combat_resolution /
# rules emit paths).  Used by the completeness test.
EXPECTED_IMPACT_FIELDS = (
    "event_id", "tick", "event_type",
    "attacker_id", "target_id", "weapon_id",
    "source_x", "source_y", "target_x", "target_y",
    "delivery_type", "weapon_type", "armor_type",
    "base_damage", "final_damage", "damage_multiplier",
    "shield_damage", "health_damage",
    "chain_index", "is_splash", "splash_fraction",
    "killed", "missed", "armor_value", "shield_armor_value",
    "hit_index", "hit_count",
)


# ─── Entity builder (in-process) ────────────────────────────────────────────

def make_entity(
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
    """Build a minimal combat-capable entity dict (mirrors unit_stats shape)."""
    entity_type = "soldier"
    if unit_type in ("Vulture", "Mutalisk"):
        entity_type = "scout"
    return {
        "id": uid,
        "owner": owner,
        "unit_type": unit_type,
        "entity_type": entity_type,
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
        "cooldown_timer": 99,  # ready to fire this tick
        "delivery_type": delivery_type,
        "hit_count": hit_count,
        "domain": domain,
        "is_idle": False,
        "attack_target_id": "",
    }


# ─── Subprocess determinism harness ─────────────────────────────────────────
#
# Embedded script run via ``python -c`` with ``cwd=PROJECT_ROOT`` so that
# ``import simcore`` resolves (sys.path[0] is the cwd).  It builds a matchup,
# runs ``resolve_combat``, and prints the combat events as sorted JSON.

_COMBAT_SCRIPT = """\
import json
import sys
from simcore.rules import resolve_combat


def mk(uid, owner=1, unit_type='Marine', health=100, shields=0, armor=0,
       armor_type='medium', pos=(0.0, 0.0), attack_ground=6,
       weapon_type_ground='normal', weapon_id_ground='terran_c10_rifle',
       attack_range=4, cooldown_ground=6, delivery_type='hitscan',
       hit_count=1, domain='ground'):
    et = 'soldier'
    if unit_type in ('Vulture', 'Mutalisk'):
        et = 'scout'
    return {
        'id': uid, 'owner': owner, 'unit_type': unit_type,
        'entity_type': et, 'health': health, 'max_health': health,
        'shields': shields, 'shield': shields, 'armor': armor,
        'armor_type': armor_type, 'pos_x': pos[0], 'pos_y': pos[1],
        'attack_ground': attack_ground,
        'weapon_type_ground': weapon_type_ground,
        'weapon_id_ground': weapon_id_ground,
        'attack_range_ground': attack_range,
        'cooldown_ground': cooldown_ground, 'cooldown_timer': 99,
        'delivery_type': delivery_type, 'hit_count': hit_count,
        'domain': domain, 'is_idle': False, 'attack_target_id': '',
    }


scenario = sys.argv[1] if len(sys.argv) > 1 else 'simple'

if scenario == 'simple':
    entities = {
        'marine1': mk('marine1', owner=1, unit_type='Marine',
                      attack_ground=6, weapon_type_ground='normal',
                      weapon_id_ground='terran_c10_rifle', attack_range=4,
                      cooldown_ground=6, delivery_type='hitscan',
                      hit_count=1, pos=(0.0, 0.0)),
        'zerg1': mk('zerg1', owner=2, unit_type='Zergling', health=35,
                    armor=0, armor_type='light', pos=(3.0, 0.0)),
    }
    entities['marine1']['attack_target_id'] = 'zerg1'
elif scenario == 'multi':
    entities = {}
    for i in range(6):
        entities['mut%d' % i] = mk(
            'mut%d' % i, owner=1, unit_type='Mutalisk', health=120,
            armor_type='medium', attack_ground=9,
            weapon_type_ground='normal',
            weapon_id_ground='zerg_glave_wurm', attack_range=3,
            cooldown_ground=13, delivery_type='chain', hit_count=1,
            pos=(0.0, float(i)), domain='air')
    for j in range(10):
        entities['mar%d' % j] = mk(
            'mar%d' % j, owner=2, unit_type='Marine', health=40,
            armor=0, armor_type='light', pos=(2.0, float(j)))
    for i in range(6):
        entities['mut%d' % i]['attack_target_id'] = 'mar%d' % i
else:
    raise SystemExit('unknown scenario: %s' % scenario)

events = []
resolve_combat(entities, {}, [], tick=1, combat_events=events)
print(json.dumps(events, sort_keys=True))
"""


def _run_combat_subprocess(scenario: str, hashseed: str) -> tuple[list[dict], str]:
    """Run a combat scenario in a fresh subprocess with a fixed PYTHONHASHSEED.

    Returns ``(parsed_events, raw_json_string)``.  The raw string is returned so
    callers can assert byte-identical output across seeds (the strongest
    determinism proof); the parsed list supports per-field assertions.
    """
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    proc = subprocess.run(
        [sys.executable, "-c", _COMBAT_SCRIPT, scenario],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"subprocess (PYTHONHASHSEED={hashseed}, scenario={scenario}) "
        f"exited {proc.returncode}:\n{proc.stderr}"
    )
    raw = proc.stdout.strip()
    assert raw, (
        f"subprocess (PYTHONHASHSEED={hashseed}, scenario={scenario}) "
        f"produced no stdout:\n{proc.stderr}"
    )
    return json.loads(raw), raw


# ─── 1. E2E combat event pipeline ────────────────────────────────────────────


class TestE2ECombatEvents:
    """Marine vs Zergling: full attack_started → impact_resolved pipeline."""

    def test_marine_vs_zergling_event_pipeline(self):
        entities = {
            "marine1": make_entity(
                "marine1", owner=1, unit_type="Marine",
                attack_ground=6, weapon_type_ground="normal",
                weapon_id_ground="terran_c10_rifle", attack_range=4,
                cooldown_ground=6, delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "zerg1": make_entity(
                "zerg1", owner=2, unit_type="Zergling", health=35, armor=0,
                armor_type="light", pos=(3.0, 0.0),
            ),
        }
        entities["marine1"]["attack_target_id"] = "zerg1"

        events: list[dict] = []
        result, _ = resolve_combat(entities, {}, [], tick=1, combat_events=events)

        attacks = [e for e in events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]

        # attack_started + impact_resolved both present
        assert len(attacks) == 1, f"expected 1 attack_started, got {len(attacks)}"
        assert len(impacts) == 1, f"expected 1 impact_resolved, got {len(impacts)}"

        # weapon_id preserved on both events
        assert attacks[0]["weapon_id"] == "terran_c10_rifle"
        assert impacts[0]["weapon_id"] == "terran_c10_rifle"

        # damage fields correct (normal vs light, no armor → 6 dmg, no shield)
        imp = impacts[0]
        assert imp["base_damage"] == 6.0
        assert imp["final_damage"] == 6.0
        assert imp["shield_damage"] == 0.0
        assert imp["health_damage"] == 6.0
        assert imp["damage_multiplier"] == 1.0  # normal vs light = 100%

        # event_id unique (no duplicate IDs)
        event_ids = [e["event_id"] for e in events]
        assert len(event_ids) == len(set(event_ids)), (
            f"duplicate event_ids: {event_ids}"
        )

        # events ordered: attack_started before impact_resolved
        type_order = [e["event_type"] for e in events]
        assert type_order == [ATTACK_STARTED, IMPACT_RESOLVED], (
            f"event order wrong: {type_order}"
        )
        assert events.index(attacks[0]) < events.index(impacts[0])

        # sanity: damage was actually applied
        assert result["zerg1"]["health"] == 29.0  # 35 - 6


# ─── 2 & 3. Determinism via subprocess (PYTHONHASHSEED isolation) ─────────────


class TestCombatEventDeterminism:
    """Combat events must be identical regardless of PYTHONHASHSEED.

    PYTHONHASHSEED randomizes str/bytes hashing (and thus set iteration order)
    at interpreter startup and cannot be changed mid-process, so each seed is
    exercised in its own subprocess.
    """

    def test_simple_matchup_deterministic_across_hashseeds(self):
        """Marine vs Zergling: two subprocesses (seed 1 vs 999) match exactly."""
        events_a, raw_a = _run_combat_subprocess("simple", "1")
        events_b, raw_b = _run_combat_subprocess("simple", "999")

        # Byte-identical serialized output — strongest determinism proof.
        assert raw_a == raw_b

        # Both runs produced real combat events.
        assert len(events_a) >= 2
        assert ATTACK_STARTED in [e["event_type"] for e in events_a]

        # Same event types in the same order.
        types_a = [e["event_type"] for e in events_a]
        types_b = [e["event_type"] for e in events_b]
        assert types_a == types_b

        # Same event IDs (and unique within each run).
        ids_a = [e["event_id"] for e in events_a]
        ids_b = [e["event_id"] for e in events_b]
        assert ids_a == ids_b
        assert len(ids_a) == len(set(ids_a))

        # Same target selection.
        targets_a = [e["target_id"] for e in events_a]
        targets_b = [e["target_id"] for e in events_b]
        assert targets_a == targets_b

        # Same damage values on impact events.
        def _dmg(ev: list[dict]) -> list[tuple]:
            return [
                (e["base_damage"], e["final_damage"],
                 e["shield_damage"], e["health_damage"])
                for e in ev if e["event_type"] == IMPACT_RESOLVED
            ]
        assert _dmg(events_a) == _dmg(events_b)

    def test_multi_unit_chain_bounce_deterministic(self):
        """6 Mutalisk vs 10 Marine: chain bounce targets are seed-independent."""
        events_a, raw_a = _run_combat_subprocess("multi", "1")
        events_b, raw_b = _run_combat_subprocess("multi", "999")

        # Byte-identical serialized output.
        assert raw_a == raw_b

        impacts_a = [e for e in events_a if e["event_type"] == IMPACT_RESOLVED]
        impacts_b = [e for e in events_b if e["event_type"] == IMPACT_RESOLVED]

        # 6 Mutalisks × 3 chain impacts (chain_index 0,1,2) = 18 impacts.
        assert len(impacts_a) == 18, f"expected 18 impacts, got {len(impacts_a)}"
        assert len(impacts_b) == 18

        # Chain bounce target selection is deterministic.
        assert [e["target_id"] for e in impacts_a] == [
            e["target_id"] for e in impacts_b
        ]
        # Chain indices and fractions are deterministic.
        assert [e["chain_index"] for e in impacts_a] == [
            e["chain_index"] for e in impacts_b
        ]
        assert [e["splash_fraction"] for e in impacts_a] == [
            e["splash_fraction"] for e in impacts_b
        ]

        # 6 attacks (one per Mutalisk) — also deterministic + unique IDs.
        attacks_a = [e for e in events_a if e["event_type"] == ATTACK_STARTED]
        assert len(attacks_a) == 6
        all_ids_a = [e["event_id"] for e in events_a]
        assert len(all_ids_a) == len(set(all_ids_a))

        # Full event-list equality as a final guarantee.
        assert events_a == events_b


# ─── 4. Event completeness across all three races ────────────────────────────


def _build_race_matchup(race: str) -> dict:
    """One matchup per race with that race as the attacker.

    Terran and Zerg attackers hit shielded Protoss targets (exercising
    shield_damage); the Protoss attacker uses a multi-hit melee weapon
    (exercising hit_index/hit_count and health_damage).
    """
    if race == "Terran":
        entities = {
            "m1": make_entity(
                "m1", owner=1, unit_type="Marine",
                attack_ground=6, weapon_type_ground="normal",
                weapon_id_ground="terran_c10_rifle", attack_range=4,
                cooldown_ground=6, delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "z1": make_entity(
                "z1", owner=2, unit_type="Zealot", health=100, shields=60,
                armor=1, armor_type="light", pos=(3.0, 0.0),
            ),
        }
        entities["m1"]["attack_target_id"] = "z1"
        return entities

    if race == "Zerg":
        entities = {
            "h1": make_entity(
                "h1", owner=1, unit_type="Hydralisk",
                attack_ground=10, weapon_type_ground="explosive",
                weapon_id_ground="zerg_needle_spines", attack_range=4,
                cooldown_ground=6, delivery_type="hitscan", hit_count=1,
                pos=(0.0, 0.0),
            ),
            "d1": make_entity(
                "d1", owner=2, unit_type="Dragoon", health=100, shields=80,
                armor=1, armor_type="heavy", pos=(3.0, 0.0),
            ),
        }
        entities["h1"]["attack_target_id"] = "d1"
        return entities

    # Protoss: Zealot (hit_count=2) vs Marine
    entities = {
        "z1": make_entity(
            "z1", owner=1, unit_type="Zealot",
            attack_ground=16, weapon_type_ground="normal",
            weapon_id_ground="protoss_psi_blades", attack_range=1.5,
            cooldown_ground=9, delivery_type="melee", hit_count=2,
            pos=(0.0, 0.0),
        ),
        "m1": make_entity(
            "m1", owner=2, unit_type="Marine", health=40, armor=0,
            armor_type="light", pos=(1.0, 0.0),
        ),
    }
    entities["z1"]["attack_target_id"] = "m1"
    return entities


@pytest.mark.parametrize("race", ["Terran", "Zerg", "Protoss"])
class TestEventCompleteness:
    """Each race's matchup must emit impact_resolved events with all fields."""

    def test_impact_events_have_all_fields_non_null(self, race: str):
        entities = _build_race_matchup(race)
        events: list[dict] = []
        resolve_combat(entities, {}, [], tick=1, combat_events=events)

        attacks = [e for e in events if e["event_type"] == ATTACK_STARTED]
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]

        assert attacks, f"{race}: no attack_started event emitted"
        assert impacts, f"{race}: no impact_resolved event emitted"

        # Every impact_resolved event has all expected fields, none None.
        for imp in impacts:
            for field in EXPECTED_IMPACT_FIELDS:
                assert field in imp, (
                    f"{race}: impact event missing field {field!r}: {imp}"
                )
                assert imp[field] is not None, (
                    f"{race}: impact field {field!r} is None: {imp}"
                )

        # Every attack_started event carries its core fields, none None.
        attack_fields = (
            "event_id", "tick", "event_type", "attacker_id", "target_id",
            "weapon_id", "weapon_type", "armor_type", "base_damage",
            "hit_count",
        )
        for atk in attacks:
            for field in attack_fields:
                assert field in atk, (
                    f"{race}: attack event missing field {field!r}: {atk}"
                )
                assert atk[field] is not None, (
                    f"{race}: attack field {field!r} is None: {atk}"
                )

        # event_ids are unique across the whole event stream.
        all_ids = [e["event_id"] for e in events]
        assert len(all_ids) == len(set(all_ids)), (
            f"{race}: duplicate event_ids: {all_ids}"
        )

        # Damage is actually being dealt: base_damage > 0 and final >= 0.
        for imp in impacts:
            assert imp["base_damage"] > 0, f"{race}: non-positive base_damage"
            assert imp["final_damage"] >= 0, f"{race}: negative final_damage"

        # weapon_id is preserved from attack_started → impact_resolved.
        attack_wid = {atk["weapon_id"] for atk in attacks}
        impact_wid = {imp["weapon_id"] for imp in impacts}
        assert impact_wid <= attack_wid, (
            f"{race}: impact weapon_ids {impact_wid} not in attack "
            f"weapon_ids {attack_wid}"
        )
