"""P4-2: Rule-based AI baseline tests.

Validates that:
  - PassiveAI does nothing
  - GreedyGatherer gathers minerals and trains workers
  - RushAI builds military and attacks
  - Two agents can run a full game via SimCore.run()
  - ReplayV2 captures the match
"""
import pytest
from simcore.engine import SimCore
from simcore.agents import PassiveAI, GreedyGatherer, RushAI


class TestPassiveAI:
    def test_returns_empty(self):
        ai = PassiveAI()
        obs = {"entities": {}, "resources": {}}
        assert ai.decide(obs) == []

    def test_run_with_two_passive(self):
        """Two PassiveAIs → game reaches max_ticks with no changes."""
        engine = SimCore(max_ticks=100)
        state = engine.run([PassiveAI(), PassiveAI()])
        assert state.is_terminal  # max_ticks reached
        # Both bases alive
        bases = [e for e in state.entities.values()
                 if e.get("entity_type") == "building" and e.get("building_type") == "base"]
        assert len(bases) == 2
        assert all(b.get("health", 0) > 0 for b in bases)


class TestGreedyGatherer:
    def test_sends_idle_workers(self):
        ai = GreedyGatherer(player_id=1)
        obs = {
            "entities": {
                "w1": {"id": "w1", "owner": 1, "entity_type": "worker",
                       "is_idle": True, "pos_x": 10, "pos_y": 10},
                "m1": {"id": "m1", "entity_type": "resource",
                       "resource_type": "mineral", "resource_amount": 500,
                       "pos_x": 12, "pos_y": 10},
                "base_p1": {"id": "base_p1", "owner": 1, "entity_type": "building",
                            "building_type": "base", "unit_type": "CommandCenter",
                            "pos_x": 10, "pos_y": 10, "is_constructing": False},
            },
            "resources": {"p1_mineral": 200, "p1_gas": 0,
                          "p1_supply_used": 6, "p1_supply_cap": 10,
                          "p2_mineral": 200, "p2_gas": 0},
        }
        cmds = ai.decide(obs)
        gather_cmds = [c for c in cmds if c["action"] == "gather"]
        assert len(gather_cmds) == 1
        assert gather_cmds[0]["unit_id"] == "w1"
        assert gather_cmds[0]["resource_id"] == "m1"

    def test_trains_worker_when_affordable(self):
        ai = GreedyGatherer(player_id=1)
        obs = {
            "entities": {
                "base_p1": {"id": "base_p1", "owner": 1, "entity_type": "building",
                            "building_type": "base", "unit_type": "CommandCenter",
                            "pos_x": 10, "pos_y": 10, "is_constructing": False},
            },
            "resources": {"p1_mineral": 300, "p1_gas": 0,
                          "p1_supply_used": 6, "p1_supply_cap": 20,
                          "p2_mineral": 200, "p2_gas": 0},
        }
        cmds = ai.decide(obs)
        train_cmds = [c for c in cmds if c["action"] == "train"]
        assert len(train_cmds) == 1
        assert train_cmds[0]["unit_type"] == "SCV"

    def test_gathers_over_200_ticks(self):
        """Run 200 ticks with GreedyGatherer vs PassiveAI — minerals increase."""
        engine = SimCore(max_ticks=300, enable_replay_v2=True)
        engine.initialize(map_seed=42, config={"player_races": {1: "terran", 2: "terran"}})
        agents = [GreedyGatherer(player_id=1), PassiveAI()]
        start_mineral = engine.state.resources["p1_mineral"]
        for _ in range(200):
            obs = engine.state.get_observations()
            cmds = [a.decide(o) for a, o in zip(agents, obs)]
            engine.step(cmds[0] + cmds[1])
        end_mineral = engine.state.resources["p1_mineral"]
        assert end_mineral > start_mineral


class TestRushAI:
    def test_issues_build_command(self):
        ai = RushAI(player_id=1)
        obs = {
            "entities": {
                "base_p1": {"id": "base_p1", "owner": 1, "entity_type": "building",
                            "building_type": "base", "unit_type": "CommandCenter",
                            "pos_x": 10, "pos_y": 10, "is_constructing": False},
                "w0": {"id": "w0", "owner": 1, "entity_type": "worker",
                       "is_idle": True, "pos_x": 10, "pos_y": 12},
                "m0": {"id": "m0", "entity_type": "resource",
                       "resource_type": "mineral", "resource_amount": 500,
                       "pos_x": 12, "pos_y": 10},
            },
            "resources": {"p1_mineral": 500, "p1_gas": 0,
                          "p1_supply_used": 6, "p1_supply_cap": 20,
                          "p2_mineral": 200, "p2_gas": 0},
        }
        cmds = ai.decide(obs)
        build_cmds = [c for c in cmds if c["action"] == "build"]
        assert len(build_cmds) >= 1
        assert build_cmds[0]["building_type"] == "Barracks"

    def test_run_rush_vs_passive(self):
        """RushAI vs PassiveAI over 600 ticks — RushAI should deal damage or destroy base."""
        engine = SimCore(max_ticks=700, enable_replay_v2=True)
        engine.initialize(map_seed=42, config={"player_races": {1: "terran", 2: "terran"}})
        agents = [RushAI(player_id=1, attack_threshold=2), PassiveAI()]
        for _ in range(600):
            obs = engine.state.get_observations()
            cmds = [a.decide(o) for a, o in zip(agents, obs)]
            engine.step(cmds[0] + cmds[1])
        # P2 base should have taken damage (or be destroyed)
        p2_base = engine.state.entities.get("base_p2", {})
        if p2_base:
            assert p2_base.get("health", 1500) < 1500, "RushAI failed to damage P2 base in 600 ticks"


class TestAgentVsAgent:
    def test_gatherer_mirror_300_ticks(self):
        """Two GreedyGatherers run for 300 ticks — both should have minerals."""
        engine = SimCore(max_ticks=400)
        engine.initialize(map_seed=42, config={"player_races": {1: "terran", 2: "zerg"}})
        agents = [GreedyGatherer(player_id=1), GreedyGatherer(player_id=2)]
        for _ in range(300):
            obs = engine.state.get_observations()
            cmds = [a.decide(o) for a, o in zip(agents, obs)]
            engine.step(cmds[0] + cmds[1])
        assert engine.state.resources["p1_mineral"] > 200
        assert engine.state.resources["p2_mineral"] > 200

    def test_rush_vs_gatherer(self):
        """RushAI vs GreedyGatherer — RushAI should have military units."""
        engine = SimCore(max_ticks=400)
        engine.initialize(map_seed=42, config={"player_races": {1: "terran", 2: "terran"}})
        agents = [RushAI(player_id=1, attack_threshold=2), GreedyGatherer(player_id=2)]
        for _ in range(300):
            obs = engine.state.get_observations()
            cmds = [a.decide(o) for a, o in zip(agents, obs)]
            engine.step(cmds[0] + cmds[1])
        # P1 should have at least some military units
        p1_mil = [e for e in engine.state.entities.values()
                  if e.get("owner") == 1 and e.get("entity_type") in ("soldier", "scout")]
        assert len(p1_mil) >= 1

    def test_replay_v2_full_match(self):
        """Full match with ReplayV2 — verify it records correctly."""
        engine = SimCore(max_ticks=100, enable_replay_v2=True)
        engine.initialize(map_seed=42, config={"player_races": {1: "terran", 2: "terran"}})
        agents = [GreedyGatherer(player_id=1), PassiveAI()]
        for _ in range(80):
            obs = engine.state.get_observations()
            cmds = [a.decide(o) for a, o in zip(agents, obs)]
            engine.step(cmds[0] + cmds[1])
        rp = engine.replay_v2
        assert rp is not None
        assert len(rp.commands) == 80
