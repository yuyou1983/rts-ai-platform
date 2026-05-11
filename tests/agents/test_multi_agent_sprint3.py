"""Sprint 3 tests: multi-agent architecture — Coordinator, sub-agents, MsgHub."""
import pytest

from agents.coordinator import CoordinatorAgent, _dedup_commands, _with_budget, _find_my_base
from agents.sub_agents import EconomyAgent, CombatAgent, ScoutAgent
from agentscope_compat import AgentBase, Msg, MsgHub


# ─── Helpers ────────────────────────────────────────────

def _soldier(sid: str, owner: int, px: float, py: float, **kw: float) -> dict:
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


def _base(bid: str, owner: int, px: float, py: float) -> dict:
    return {
        "id": bid, "owner": owner, "entity_type": "building",
        "building_type": "base", "pos_x": px, "pos_y": py,
        "health": 1500, "max_health": 1500,
        "is_constructing": False, "production_queue": [],
        "production_timers": [],
    }


def _barracks(bid: str, owner: int, px: float, py: float, constructing=False) -> dict:
    return {
        "id": bid, "owner": owner, "entity_type": "building",
        "building_type": "barracks", "pos_x": px, "pos_y": py,
        "health": 100, "max_health": 100,
        "is_constructing": constructing, "build_progress": 0 if constructing else 100,
        "production_queue": [], "production_timers": [],
    }


def _mineral(mid: str, px: float, py: float, amount=1500) -> dict:
    return {
        "id": mid, "owner": 0, "entity_type": "resource",
        "resource_type": "mineral", "pos_x": px, "pos_y": py,
        "resource_amount": amount,
    }


def _make_obs(tick=0, mineral=200, entities=None):
    return {
        "tick": tick,
        "resources": {"p1_mineral": mineral, "p1_gas": 0},
        "entities": entities or {},
    }


class TestEconomyAgent:
    """Economy sub-agent produces correct commands."""

    def test_gather_when_idle(self):
        econ = EconomyAgent(player_id=1)
        obs = _make_obs(entities={
            "w1": _worker("w1", 1, 10, 10),
            "m1": _mineral("m1", 12, 10),
            "b1": _base("b1", 1, 9.6, 9.6),
        })
        obs["budget"] = {"mineral": 500, "gas": 0}
        cmds = econ.decide(obs)
        assert any(c["action"] == "gather" for c in cmds)

    def test_build_barracks_when_affordable(self):
        econ = EconomyAgent(player_id=1)
        obs = _make_obs(mineral=200, entities={
            "w1": _worker("w1", 1, 10, 10),
            "m1": _mineral("m1", 12, 10),
            "b1": _base("b1", 1, 9.6, 9.6),
        })
        obs["budget"] = {"mineral": 200, "gas": 0}
        cmds = econ.decide(obs)
        assert any(c["action"] == "build" for c in cmds)

    def test_no_train_without_barracks(self):
        econ = EconomyAgent(player_id=1)
        obs = _make_obs(mineral=500, entities={
            "w1": _worker("w1", 1, 10, 10),
            "m1": _mineral("m1", 12, 10),
            "b1": _base("b1", 1, 9.6, 9.6),
        })
        obs["budget"] = {"mineral": 500, "gas": 0}
        cmds = econ.decide(obs)
        # Should build barracks first, not train workers
        train_cmds = [c for c in cmds if c["action"] == "train" and c.get("unit_type") == "worker"]
        assert len(train_cmds) == 0, "Should not train workers before barracks"


class TestCombatAgent:
    """Combat sub-agent produces attack commands."""

    def test_attack_weakest_enemy(self):
        combat = CombatAgent(player_id=1)
        obs = _make_obs(entities={
            "s1": _soldier("s1", 1, 10, 10),
            "s2": _soldier("s2", 1, 10, 11),
            "e1": _soldier("e1", 2, 10.5, 10, health=20),
            "e2": _soldier("e2", 2, 10.5, 11, health=80),
        })
        obs["budget"] = {"mineral": 500, "gas": 0}
        cmds = combat.decide(obs)
        atk_cmds = [c for c in cmds if c["action"] == "attack"]
        # Should target e1 (weakest)
        targets = {c["target_id"] for c in atk_cmds}
        assert "e1" in targets


class TestCoordinatorIntegration:
    """Coordinator dispatches to sub-agents and merges correctly."""

    def test_coordinator_produces_commands(self):
        coord = CoordinatorAgent(player_id=1)
        obs = _make_obs(mineral=300, entities={
            "w1": _worker("w1", 1, 10, 10),
            "w2": _worker("w2", 1, 11, 10),
            "m1": _mineral("m1", 12, 10),
            "b1": _base("b1", 1, 9.6, 9.6),
            "s1": _soldier("s1", 1, 20, 20),
            "e1": _soldier("e1", 2, 20.5, 20, health=30),
        })
        result = coord.decide(obs)
        assert len(result["commands"]) > 0

    def test_coordinator_deterministic(self):
        coord1 = CoordinatorAgent(player_id=1)
        coord2 = CoordinatorAgent(player_id=1)
        obs = _make_obs(mineral=300, entities={
            "w1": _worker("w1", 1, 10, 10),
            "m1": _mineral("m1", 12, 10),
            "b1": _base("b1", 1, 9.6, 9.6),
        })
        r1 = coord1.decide(obs)
        r2 = coord2.decide(obs)
        assert r1["commands"] == r2["commands"]


class TestDedupCommands:
    """_dedup_commands handles edge cases correctly."""

    def test_build_not_deduped_with_gather(self):
        """Build and gather for same worker should both survive dedup."""
        cmds = [
            {"action": "gather", "worker_id": "w1", "resource_id": "m1"},
            {"action": "build", "builder_id": "w1", "building_type": "barracks", "pos_x": 5, "pos_y": 5},
        ]
        result = _dedup_commands(cmds)
        actions = [c["action"] for c in result]
        assert "gather" in actions
        assert "build" in actions

    def test_duplicate_gather_deduped(self):
        cmds = [
            {"action": "gather", "worker_id": "w1", "resource_id": "m1"},
            {"action": "gather", "worker_id": "w1", "resource_id": "m2"},
        ]
        result = _dedup_commands(cmds)
        gather_cmds = [c for c in result if c["action"] == "gather"]
        assert len(gather_cmds) == 1

    def test_train_deduped_per_building(self):
        cmds = [
            {"action": "train", "building_id": "b1", "unit_type": "soldier"},
            {"action": "train", "building_id": "b1", "unit_type": "soldier"},
        ]
        result = _dedup_commands(cmds)
        train_cmds = [c for c in result if c["action"] == "train"]
        assert len(train_cmds) == 1


class TestBudgetAllocation:
    """_with_budget correctly limits resources."""

    def test_budget_split(self):
        obs = {"tick": 0, "resources": {"p1_mineral": 100, "p1_gas": 50}, "entities": {}}
        sub = _with_budget(obs, 60, 30)
        assert sub["budget"] == {"mineral": 60, "gas": 30}


class TestFindMyBase:
    """_find_my_base returns correct base entity."""

    def test_finds_own_base(self):
        entities = {
            "b1": _base("b1", 1, 9.6, 9.6),
            "b2": _base("b2", 2, 54, 54),
        }
        result = _find_my_base(entities, 1)
        assert result is not None
        assert result["id"] == "b1"

    def test_returns_none_when_dead(self):
        entities = {
            "b1": {**_base("b1", 1, 9.6, 9.6), "health": 0},
        }
        assert _find_my_base(entities, 1) is None