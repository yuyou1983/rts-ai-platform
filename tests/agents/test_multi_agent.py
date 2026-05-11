"""Tests for M1 multi-agent architecture."""
import asyncio

from agents.combat import CombatAgent
from agents.coordinator import CoordinatorAgent
from agents.economy import EconomyAgent
from agents.game_loop import run_sync
from agentscope_compat import AgentBase, Msg, MsgHub


class TestCompatLayer:
    """Verify AgentScope compat layer works."""

    def test_msg_creation(self):
        msg = Msg(name="test", content="hello", role="user")
        assert msg.name == "test"
        assert msg.content == "hello"
        assert msg.role == "user"
        assert msg.id  # auto-generated

    def test_msg_metadata(self):
        msg = Msg(name="obs", content="world", role="user",
                  metadata={"tick": 5, "minerals": 300})
        assert msg.metadata["tick"] == 5
        assert msg.metadata["minerals"] == 300

    def test_agent_base_interface(self):
        class DummyAgent(AgentBase):
            async def reply(self, *args, **kwargs):
                return Msg(name=self.name, content="ok", role="assistant")

        agent = DummyAgent(name="dummy", player_id=1)
        assert agent.name == "dummy"
        assert agent.player_id == 1

    def test_msghub_broadcast(self):
        """MsgHub should broadcast announcement to all participants (async)."""
        class SpyAgent(AgentBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.observed = []

            async def observe(self, msg):
                self.observed.append(msg)

            async def reply(self, *args, **kwargs):
                return Msg(name=self.name, content="ack", role="assistant")

        agents = [SpyAgent(name="a1"), SpyAgent(name="a2")]
        announcement = Msg(name="world", content="obs", role="user",
                          metadata={"tick": 0})

        async def _test():
            async with MsgHub(participants=agents, announcement=announcement):
                pass
            assert len(agents[0].observed) == 1
            assert len(agents[1].observed) == 1

        asyncio.run(_test())

    def test_msghub_sync_context(self):
        """MsgHub should also work as sync context manager."""
        class SpyAgent(AgentBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.observed = []

            async def observe(self, msg):
                self.observed.append(msg)

            async def reply(self, *args, **kwargs):
                return Msg(name=self.name, content="ack", role="assistant")

        agents = [SpyAgent(name="a1"), SpyAgent(name="a2")]
        announcement = Msg(name="world", content="obs", role="user",
                          metadata={"tick": 0})

        with MsgHub(participants=agents, announcement=announcement):
            pass
        assert len(agents[0].observed) == 1
        assert len(agents[1].observed) == 1


class TestEconomyAgent:
    """Test economy sub-agent decisions."""

    def test_idle_workers_gather(self):
        econ = EconomyAgent(player_id=1)
        obs = Msg(
            name="simcore", content="obs", role="user",
            metadata={
                "tick": 1,
                "budget": {"mineral": 500, "gas": 0},
                "entities": {
                    "w1": {"owner": 1, "entity_type": "worker",
                           "is_idle": True, "pos_x": 10, "pos_y": 10},
                    "m1": {"owner": 0, "entity_type": "resource",
                           "resource_type": "mineral",
                           "pos_x": 12, "pos_y": 10, "resource_amount": 500},
                    "base_p1": {"owner": 1, "entity_type": "building",
                               "building_type": "base", "pos_x": 9.6, "pos_y": 9.6,
                               "health": 1500},
                },
            },
        )
        reply = asyncio.run(econ.reply(obs_msg=obs))
        gather_cmds = [c for c in reply.metadata["commands"]
                       if c.get("action") == "gather"]
        assert len(gather_cmds) > 0


class TestCombatAgent:
    """Test combat sub-agent decisions."""

    def test_attack_nearby_enemy(self):
        combat = CombatAgent(player_id=1)
        obs = Msg(
            name="simcore", content="obs", role="user",
            metadata={
                "tick": 5,
                "budget": {"mineral": 500, "gas": 0},
                "entities": {
                    "s1": {"owner": 1, "entity_type": "soldier",
                           "is_idle": True, "pos_x": 20, "pos_y": 20,
                           "attack_range": 3.0, "attack": 15,
                           "health": 80, "max_health": 80},
                    "e1": {"owner": 2, "entity_type": "soldier",
                           "pos_x": 21, "pos_y": 20, "health": 50,
                           "max_health": 80},
                },
            },
        )
        reply = asyncio.run(combat.reply(obs_msg=obs))
        atk_cmds = [c for c in reply.metadata["commands"]
                    if c.get("action") == "attack"]
        assert len(atk_cmds) > 0


class TestCoordinatorAgent:
    """Test coordinator orchestrates sub-agents."""

    def test_coordinator_dispatches(self):
        coord = CoordinatorAgent(player_id=1)
        obs = Msg(
            name="simcore", content="obs", role="user",
            metadata={
                "tick": 10,
                "resources": {"p1_mineral": 300, "p1_gas": 0},
                "entities": {
                    "w1": {"owner": 1, "entity_type": "worker",
                           "is_idle": True, "pos_x": 5, "pos_y": 5},
                    "m1": {"owner": 0, "entity_type": "resource",
                           "resource_type": "mineral",
                           "pos_x": 6, "pos_y": 5, "resource_amount": 500},
                    "base_p1": {"owner": 1, "entity_type": "building",
                               "building_type": "base", "pos_x": 4.6, "pos_y": 4.6,
                               "health": 1500},
                    "s1": {"owner": 1, "entity_type": "soldier",
                           "is_idle": True, "pos_x": 15, "pos_y": 15,
                           "attack_range": 3.0, "attack": 15,
                           "health": 80, "max_health": 80},
                    "e1": {"owner": 2, "entity_type": "soldier",
                           "pos_x": 16, "pos_y": 15, "health": 50,
                           "max_health": 80},
                },
            },
        )
        reply = asyncio.run(coord.reply(obs_msg=obs))
        commands = reply.metadata.get("commands", [])
        # Should have both economy and combat commands
        assert len(commands) > 0


class TestGameLoop:
    """Integration: full multi-agent game loop."""

    def test_50_tick_game(self):
        result = run_sync(map_seed=42, max_ticks=100)
        # Game loop runs max_ticks iterations, but stops early if terminal
        assert result["ticks"] >= 50
        assert result["tps"] > 100
        assert len(result["replay"]) == result["ticks"] + 1  # init + ticks

    def test_determinism(self):
        r1 = run_sync(map_seed=42, max_ticks=100)
        r2 = run_sync(map_seed=42, max_ticks=100)
        assert r1["replay"] == r2["replay"]

    def test_performance(self):
        result = run_sync(map_seed=42, max_ticks=500)
        assert result["tps"] > 50, f"Too slow: {result['tps']:.0f} tps"