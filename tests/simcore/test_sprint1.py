"""Sprint 1 integration tests: economy loop, combat, construction, production."""
import pytest

from simcore.engine import SimCore
from agents.script_ai import ScriptAI


class TestEconomyLoop:
    """Workers gather, return to base, and deposit resources."""

    def test_worker_gathers_and_returns(self):
        """Single worker: gather → carry full → return → deposit."""
        e = SimCore()
        e.initialize(map_seed=42)
        # Run 50 ticks with P1 only
        ai = ScriptAI(player_id=1)
        for _ in range(50):
            obs = e._state.get_observations()
            cmds = ai.decide(obs[0]).get("commands", [])
            e.step(cmds)

        # P1 should have earned minerals from worker deposits
        assert e._state.resources.get("p1_mineral", 0) > 0

    def test_resource_nodes_not_destroyed_by_combat(self):
        """Resource nodes survive combat phase (they have no health)."""
        e = SimCore()
        e.initialize(map_seed=42)
        ai1 = ScriptAI(player_id=1)
        ai2 = ScriptAI(player_id=2)
        for _ in range(5):
            obs = e._state.get_observations()
            c1 = ai1.decide(obs[0]).get("commands", [])
            c2 = ai2.decide(obs[1]).get("commands", [])
            e.step(c1 + c2)

        minerals = sum(
            1 for ent in e._state.entities.values()
            if ent.get("entity_type") == "resource"
            and ent.get("resource_type") == "mineral"
        )
        assert minerals > 0, "Resource nodes should not be destroyed by combat"

    def test_worker_carry_grows_then_resets(self):
        """Worker carry_amount increases while gathering, resets after deposit."""
        e = SimCore()
        e.initialize(map_seed=42)
        ai = ScriptAI(player_id=1)
        carry_values: list[float] = []

        for _ in range(20):
            obs = e._state.get_observations()
            cmds = ai.decide(obs[0]).get("commands", [])
            e.step(cmds)
            w = e._state.entities.get("worker_p1_0", {})
            carry_values.append(w.get("carry_amount", 0))

        # carry should go up and then come back down at least once
        max_carry = max(carry_values)
        assert max_carry > 0, "Worker should have carried resources at some point"
        # After deposit, carry should be 0 at least once after the peak
        peak_idx = carry_values.index(max_carry)
        post_peak = carry_values[peak_idx + 1 :]
        assert any(v == 0 for v in post_peak), "Carry should reset after deposit"


class TestCombat:
    """Attack commands work and units die."""

    def test_attack_reduces_health(self):
        """Explicit attack command damages the target."""
        e = SimCore()
        e.initialize(map_seed=42)
        # Place two soldiers adjacent manually
        e._state = e._state.__class__(
            tick=0,
            entities={
                "s1": {"id": "s1", "owner": 1, "entity_type": "soldier",
                       "pos_x": 10.0, "pos_y": 10.0, "health": 80, "max_health": 80,
                       "speed": 3.0, "attack": 15, "attack_range": 1.0,
                       "is_idle": True, "carry_amount": 0, "carry_capacity": 0,
                       "target_x": None, "target_y": None,
                       "returning_to_base": False, "attack_target_id": "",
                       "deposit_pending": False},
                "s2": {"id": "s2", "owner": 2, "entity_type": "soldier",
                       "pos_x": 10.5, "pos_y": 10.0, "health": 80, "max_health": 80,
                       "speed": 3.0, "attack": 15, "attack_range": 1.0,
                       "is_idle": True, "carry_amount": 0, "carry_capacity": 0,
                       "target_x": None, "target_y": None,
                       "returning_to_base": False, "attack_target_id": "",
                       "deposit_pending": False},
            },
            fog_of_war={"tiles": [], "width": 0, "height": 0},
            resources={"p1_mineral": 200, "p1_gas": 0, "p2_mineral": 200, "p2_gas": 0},
        )
        e.step([{"action": "attack", "attacker_id": "s1", "target_id": "s2", "issuer": 1}])
        target = e._state.entities.get("s2")
        assert target is not None
        assert target["health"] < 80, "Target should have taken damage"

    def test_neutral_not_auto_attacked(self):
        """Neutral entities (owner=0) are not auto-attacked."""
        e = SimCore()
        e.initialize(map_seed=42)
        ai1 = ScriptAI(player_id=1)
        ai2 = ScriptAI(player_id=2)
        for _ in range(10):
            obs = e._state.get_observations()
            c1 = ai1.decide(obs[0]).get("commands", [])
            c2 = ai2.decide(obs[1]).get("commands", [])
            e.step(c1 + c2)

        resources = sum(
            1 for ent in e._state.entities.values()
            if ent.get("entity_type") == "resource"
        )
        assert resources > 0, "Neutral resources should not be auto-attacked"


class TestConstruction:
    """Building construction progresses and completes."""

    def test_barracks_completes(self):
        """Barracks starts at progress=0 and reaches 100."""
        e = SimCore()
        e.initialize(map_seed=42)
        ai = ScriptAI(player_id=1)
        for _ in range(15):
            obs = e._state.get_observations()
            cmds = ai.decide(obs[0]).get("commands", [])
            e.step(cmds)

        barracks = [
            ent for ent in e._state.entities.values()
            if ent.get("building_type") == "barracks" and ent.get("owner") == 1
        ]
        assert len(barracks) >= 1
        completed = [b for b in barracks if not b.get("is_constructing", False)]
        assert len(completed) >= 1, "At least one barracks should be completed"


class TestProduction:
    """Training units works with production timers."""

    def test_soldier_spawns_from_barracks(self):
        """After barracks + sufficient minerals, soldiers are produced."""
        e = SimCore()
        e.initialize(map_seed=42)
        ai = ScriptAI(player_id=1)
        # Run long enough for eco → barracks → soldiers
        for _ in range(200):
            obs = e._state.get_observations()
            cmds = ai.decide(obs[0]).get("commands", [])
            e.step(cmds)

        soldiers = [
            ent for ent in e._state.entities.values()
            if ent.get("entity_type") == "soldier" and ent.get("owner") == 1
        ]
        assert len(soldiers) >= 1, "At least one soldier should be trained"


class TestEndToEnd:
    """Full game loop: ScriptAI vs ScriptAI."""

    def test_game_terminates(self):
        """AI vs AI game terminates within 5000 ticks."""
        e = SimCore()
        e.initialize(map_seed=42)
        ai1 = ScriptAI(player_id=1)
        ai2 = ScriptAI(player_id=2)
        for _ in range(5000):
            obs = e._state.get_observations()
            c1 = ai1.decide(obs[0]).get("commands", [])
            c2 = ai2.decide(obs[1]).get("commands", [])
            e.step(c1 + c2)
            if e._state.is_terminal:
                break
        assert e._state.is_terminal, "Game should terminate within 5000 ticks"

    def test_deterministic_replay(self):
        """Same seed + same AI produces same result."""
        def run_game(seed: int) -> dict:
            e = SimCore()
            e.initialize(map_seed=seed)
            ai1 = ScriptAI(player_id=1)
            ai2 = ScriptAI(player_id=2)
            for _ in range(2000):
                obs = e._state.get_observations()
                c1 = ai1.decide(obs[0]).get("commands", [])
                c2 = ai2.decide(obs[1]).get("commands", [])
                e.step(c1 + c2)
                if e._state.is_terminal:
                    break
            return {
                "tick": e._state.tick,
                "winner": e._state.winner,
                "ents": len(e._state.entities),
            }

        r1 = run_game(42)
        r2 = run_game(42)
        assert r1 == r2, "Same seed should produce identical game"