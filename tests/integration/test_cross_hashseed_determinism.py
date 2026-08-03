"""Cross-hashseed determinism tests (Task 10 Step 3-4).

Validates that combat resolution produces identical results regardless of
PYTHONHASHSEED.  The old code used Python's built-in ``hash()`` which is
seeded per-process — ``deterministic_percent_roll`` replaces it with
BLAKE2s for stable, reproducible rolls.
"""

import json
import subprocess
import sys

import pytest

from simcore.rules import deterministic_percent_roll


# ── Unit test: deterministic_percent_roll is stable ──────────

class TestDeterministicRoll:
    def test_same_inputs_same_output(self):
        assert deterministic_percent_roll(1, "m1") == deterministic_percent_roll(1, "m1")

    def test_different_inputs_different_output(self):
        # Extremely unlikely to collide for these inputs
        assert deterministic_percent_roll(1, "m1") != deterministic_percent_roll(2, "m1")

    def test_output_in_range(self):
        for i in range(100):
            r = deterministic_percent_roll(i, f"unit_{i}")
            assert 0 <= r < 100

    def test_no_builtin_hash_in_combat_path(self):
        """rules.py must not use built-in hash() for combat rolls."""
        import simcore.rules as rules_mod
        import inspect
        source = inspect.getsource(rules_mod)
        # Allow hash in comments/docstrings by checking actual code lines
        for line in source.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
                continue
            # Check for hash() calls that aren't hashlib or deterministic_percent_roll
            if 'hash(' in line and 'hashlib' not in line and 'deterministic' not in line:
                pytest.fail(f"Built-in hash() found in rules.py: {line.strip()}")


# ── Integration: cross-process determinism ───────────────────

_COMBAT_SCRIPT = """\
import json, sys
from simcore.rules import resolve_combat

def mk(uid, owner, x, y, hp, unit_type='Marine', weapon='terran_c10_rifle'):
    return {
        'id': uid, 'owner': owner, 'entity_type': 'unit',
        'unit_type': unit_type, 'health': hp, 'max_health': hp,
        'pos_x': x, 'pos_y': y, 'attack': 6, 'attack_range': 4.0,
        'weapon_id_ground': weapon, 'weapon_id_air': weapon,
        'armor_type': 'light', 'armor': 0,
        'cooldown_timer': 99, 'cooldown_ground': 15, 'cooldown_air': 15,
        'attack_target_id': 'z1' if owner == 1 else '',
        'is_idle': False if owner == 1 else True,
        'mp': 0, 'energy': 0, 'buffs': [],
        'shields': 0, 'max_shields': 0,
    }

entities = {
    'm1': mk('m1', 1, 0.0, 0.0, 40),
    'z1': mk('z1', 2, 3.0, 0.0, 100, 'Zergling', 'zerg_spines'),
}
entities['z1']['attack_target_id'] = ''

events = []
result, _ = resolve_combat(entities, {}, [], tick=1, combat_events=events)

# Output: events + final state
out = {
    'events': sorted(events, key=lambda e: e.get('event_id', '')),
    'm1_hp': result['m1']['health'],
    'z1_hp': result['z1']['health'],
}
print(json.dumps(out, sort_keys=True))
"""


class TestCrossHashseedDeterminism:
    @pytest.mark.parametrize("seed1,seed2", [(1, 999), (0, 42), (7, 314)])
    def test_combat_identical_across_hashseeds(self, seed1, seed2):
        """Combat resolution must produce identical results across PYTHONHASHSEED values."""
        env1 = {**dict(__import__('os').environ), 'PYTHONHASHSEED': str(seed1)}
        env2 = {**dict(__import__('os').environ), 'PYTHONHASHSEED': str(seed2)}

        r1 = subprocess.run(
            [sys.executable, "-c", _COMBAT_SCRIPT],
            capture_output=True, text=True, cwd=".",
            env=env1,
        )
        r2 = subprocess.run(
            [sys.executable, "-c", _COMBAT_SCRIPT],
            capture_output=True, text=True, cwd=".",
            env=env2,
        )

        assert r1.returncode == 0, f"Process 1 failed: {r1.stderr}"
        assert r2.returncode == 0, f"Process 2 failed: {r2.stderr}"

        out1 = json.loads(r1.stdout)
        out2 = json.loads(r2.stdout)

        assert out1 == out2, (
            f"Combat results differ across PYTHONHASHSEED={seed1} vs {seed2}:\n"
            f"seed {seed1}: {json.dumps(out1, indent=2)}\n"
            f"seed {seed2}: {json.dumps(out2, indent=2)}"
        )
