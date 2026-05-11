"""Sprint 2 tests: combat micro — target-following, focus fire, priority, KDA."""
import pytest

from simcore.engine import SimCore
from simcore.rules import KillFeed, resolve_combat
from agents.script_ai import ScriptAI


# ─── Helpers ────────────────────────────────────────────────

def _soldier(sid: str, owner: int, px: float, py: float, **kw: float) -> dict:
    """Create a soldier entity dict."""
    return {
        "id": sid, "owner": owner, "entity_type": "soldier",
        "pos_x": px, "pos_y": py,
        "health": kw.get("health", 80), "max_health": kw.get("max_health", 80),
        "speed": kw.get("speed", 3.0), "attack": kw.get("attack", 15),
        "attack_range": kw.get("attack_range", 1.0),
        "is_idle": True, "carry_amount": 0, "carry_capacity": 0,
        "target_x": None, "target_y": None,
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False,
    }


def _worker(wid: str, owner: int, px: float, py: float) -> dict:
    return {
        "id": wid, "owner": owner, "entity_type": "worker",
        "pos_x": px, "pos_y": py,
        "health": 50, "max_health": 50, "speed": 2.5,
        "attack": 5, "attack_range": 1.0,
        "is_idle": True, "carry_amount": 0, "carry_capacity": 10.0,
        "target_x": None, "target_y": None,
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False,
    }


class TestTargetFollowing:
    """Units with attack_target_id chase and update to target's current position."""

    def test_chase_updates_target_position(self):
        """Attacker's target_x/y tracks the target's position each tick."""
        import simcore.rules as R
        e = SimCore()
        e.initialize(map_seed=42)
        # Manually set up a chase scenario
        entities = {
            "s1": {**_soldier("s1", 1, 10.0, 10.0), "attack_target_id": "s2", "is_idle": False},
            "s2": _soldier("s2", 2, 15.0, 10.0),
        }
        result = R.apply_movement(entities, [], 1)
        assert result["s1"]["target_x"] == 15.0  # chasing s2
        assert result["s1"]["target_y"] == 10.0

    def test_dead_target_clears_attack(self):
        """When attack target is removed, attacker becomes idle."""
        import simcore.rules as R
        entities = {
            "s1": {**_soldier("s1", 1, 10.0, 10.0), "attack_target_id": "dead", "is_idle": False},
        }
        # "dead" entity is not in the dict
        result = R.apply_movement(entities, [], 1)
        assert result["s1"]["attack_target_id"] == ""
        assert result["s1"]["is_idle"] is True

    def test_explicit_move_clears_attack(self):
        """Move command clears attack_target_id."""
        import simcore.rules as R
        entities = {
            "s1": {**_soldier("s1", 1, 10.0, 10.0), "attack_target_id": "s2", "is_idle": False},
        }
        result = R.apply_movement(entities, [{"action": "move", "unit_id": "s1", "target_x": 5.0, "target_y": 5.0, "issuer": 1}], 1)
        assert result["s1"]["attack_target_id"] == ""
        assert result["s1"]["target_x"] == 5.0


class TestFocusFire:
    """ScriptAI assigns all soldiers to the weakest enemy."""

    def test_focus_fire_on_weak_target(self):
        """All idle soldiers target the enemy with lowest health fraction."""
        ai = ScriptAI(player_id=1)
        obs = {
            "tick": 100,
            "entities": {
                "s1": _soldier("s1", 1, 10.0, 10.0),
                "s2": _soldier("s2", 1, 10.0, 11.0),
                "e1": _soldier("e1", 2, 10.5, 10.0, health=20),  # weak
                "e2": _soldier("e2", 2, 10.5, 11.0, health=80),  # full
                "base_p1": {"id": "base_p1", "owner": 1, "entity_type": "building",
                            "building_type": "base", "pos_x": 9.6, "pos_y": 9.6,
                            "health": 1500, "max_health": 1500,
                            "is_constructing": False, "production_queue": [],
                            "production_timers": []},
            },
            "resources": {"p1_mineral": 500, "p1_gas": 0},
        }
        result = ai.decide(obs)
        attack_cmds = [c for c in result["commands"] if c.get("action") == "attack"]
        # Both soldiers should target e1 (weakest)
        assert len(attack_cmds) == 2
        targets = {c["target_id"] for c in attack_cmds}
        assert targets == {"e1"}


class TestAutoAttackPriority:
    """Auto-attack picks targets by priority score, not just distance."""

    def test_prefers_low_health_over_nearby(self):
        """Low-health enemy gets priority over a closer full-health one."""
        import simcore.rules as R
        # Use attack=15 so e_weak survives with 5hp (not one-shot)
        entities = {
            "s1": _soldier("s1", 1, 10.0, 10.0, attack=5, attack_range=3.0),
            "e_weak": _soldier("e_weak", 2, 11.0, 10.0, health=10, max_health=80),
            "e_full": _soldier("e_full", 2, 10.5, 10.0, health=80, max_health=80),
        }
        result_ents, _ = R.resolve_combat(entities, {"p1_mineral": 0, "p2_mineral": 0}, [], 1)
        # e_weak should have taken damage (preferred target due to low health)
        assert result_ents["e_weak"]["health"] < 10


class TestKillFeed:
    """KDA tracking works correctly."""

    def test_kill_tracked(self):
        kf = KillFeed()
        kf.record_kill(1, 2)
        kf.record_kill(1, 2)
        assert kf.kills == {1: 2, 2: 0}
        assert kf.deaths == {1: 0, 2: 2}

    def test_damage_tracked(self):
        kf = KillFeed()
        kf.record_damage(1, 15.0)
        kf.record_damage(1, 10.0)
        assert kf.damage_dealt[1] == 25.0

    def test_to_dict(self):
        kf = KillFeed()
        kf.record_kill(1, 2)
        kf.record_damage(2, 5.0)
        d = kf.to_dict()
        assert "kills" in d and "deaths" in d and "damage_dealt" in d

    def test_combat_records_kill(self):
        """resolve_combat records kills in the KillFeed."""
        import simcore.rules as R
        kf = KillFeed()
        entities = {
            "s1": _soldier("s1", 1, 10.0, 10.0),
            "w1": _worker("w1", 2, 10.5, 10.0),  # will die from one hit (50hp - 15 = 35, still alive)
        }
        cmds = [{"action": "attack", "attacker_id": "s1", "target_id": "w1", "issuer": 1}]
        result, _ = R.resolve_combat(entities, {"p1_mineral": 0, "p2_mineral": 0}, cmds, 1, kill_feed=kf)
        # w1 took 15 damage but didn't die
        assert kf.damage_dealt[1] == 15.0
        assert kf.kills[1] == 0

    def test_combat_records_kill_on_death(self):
        """Kill is recorded when health drops to 0."""
        import simcore.rules as R
        kf = KillFeed()
        entities = {
            "s1": _soldier("s1", 1, 10.0, 10.0, attack=999),
            "w1": _worker("w1", 2, 10.5, 10.0),  # will die
        }
        cmds = [{"action": "attack", "attacker_id": "s1", "target_id": "w1", "issuer": 1}]
        result, _ = R.resolve_combat(entities, {"p1_mineral": 0, "p2_mineral": 0}, cmds, 1, kill_feed=kf)
        assert kf.kills[1] == 1
        assert kf.deaths[2] == 1
        assert "w1" not in result  # removed


class TestWorkerRetreat:
    """Damaged workers retreat to base."""

    def test_damaged_worker_flees(self):
        """Worker below health threshold gets a move-to-base command."""
        ai = ScriptAI(player_id=1)
        obs = {
            "tick": 50,
            "entities": {
                "w1": {**_worker("w1", 1, 10.0, 10.0), "health": 10},  # 10/50 = 0.2 < 0.3
                "base_p1": {"id": "base_p1", "owner": 1, "entity_type": "building",
                            "building_type": "base", "pos_x": 9.6, "pos_y": 9.6,
                            "health": 1500, "max_health": 1500,
                            "is_constructing": False, "production_queue": [],
                            "production_timers": []},
                # Need at least one resource so gather doesn't crash
                "m1": {"id": "m1", "owner": 0, "entity_type": "resource",
                       "resource_type": "mineral", "pos_x": 14.0, "pos_y": 9.6,
                       "resource_amount": 1500},
            },
            "resources": {"p1_mineral": 500, "p1_gas": 0},
        }
        result = ai.decide(obs)
        move_cmds = [c for c in result["commands"] if c.get("action") == "move"]
        assert len(move_cmds) == 1
        # Should move toward base
        assert move_cmds[0]["target_x"] == 9.6


class TestEndToEndCombat:
    """Full game with enhanced AI still terminates and is deterministic."""

    def test_game_terminates(self):
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
        assert e._state.is_terminal

    def test_deterministic(self):
        def run(seed: int) -> dict:
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
            return {"tick": e._state.tick, "winner": e._state.winner}

        assert run(42) == run(42)