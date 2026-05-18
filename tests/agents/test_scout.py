"""Tests for ScoutAgent — AgentBase wrapper around sub_agents.ScoutAgent."""
import asyncio

import pytest

from agents.scout import ScoutAgent
from agentscope_compat import Msg


class TestScoutAgentInit:
    """Test ScoutAgent initialization."""

    def test_default_name_and_player_id(self):
        agent = ScoutAgent()
        assert agent.name == "scout"
        assert agent.player_id == 1

    def test_custom_name_and_player_id(self):
        agent = ScoutAgent(name="my_scout", player_id=2)
        assert agent.name == "my_scout"
        assert agent.player_id == 2

    def test_core_initialized(self):
        agent = ScoutAgent(player_id=1)
        assert agent._core is not None
        assert agent._core.player_id == 1


class TestScoutAgentReplyWithObs:
    """Test ScoutAgent.reply when given an observation message."""

    def _make_obs_msg(self, tick: int = 5) -> Msg:
        """Build a minimal observation Msg that ScoutAgent can process."""
        return Msg(
            name="simcore",
            content="obs",
            role="user",
            metadata={
                "tick": tick,
                "entities": {
                    "scout_1": {
                        "owner": 1,
                        "entity_type": "scout",
                        "is_idle": True,
                        "pos_x": 10,
                        "pos_y": 10,
                        "health": 60,
                        "max_health": 60,
                    },
                    "base_p1": {
                        "owner": 1,
                        "entity_type": "building",
                        "building_type": "base",
                        "pos_x": 9.6,
                        "pos_y": 9.6,
                        "health": 1500,
                    },
                },
                "fog_of_war": {
                    "tiles": [0] * 256,  # 16x16 all unexplored
                    "width": 16,
                    "height": 16,
                },
            },
        )

    def test_reply_returns_msg(self):
        agent = ScoutAgent(player_id=1)
        obs_msg = self._make_obs_msg()
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert isinstance(result, Msg)

    def test_reply_name_is_agent_name(self):
        agent = ScoutAgent(name="scout", player_id=1)
        obs_msg = self._make_obs_msg()
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert result.name == "scout"

    def test_reply_role_is_assistant(self):
        agent = ScoutAgent(player_id=1)
        obs_msg = self._make_obs_msg()
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert result.role == "assistant"

    def test_reply_metadata_has_commands(self):
        agent = ScoutAgent(player_id=1)
        obs_msg = self._make_obs_msg()
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert "commands" in result.metadata
        assert isinstance(result.metadata["commands"], list)

    def test_reply_metadata_has_tick(self):
        agent = ScoutAgent(player_id=1)
        obs_msg = self._make_obs_msg(tick=7)
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert result.metadata["tick"] == 7

    def test_reply_content_mentions_command_count(self):
        agent = ScoutAgent(player_id=1)
        obs_msg = self._make_obs_msg(tick=10)
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        # Content format: "tick {tick}: {n} scout commands"
        assert "scout commands" in result.content
        assert "tick 10" in result.content

    def test_scout_commands_are_move_or_retreat(self):
        """All scout commands should be 'move' (patrol/retreat)."""
        agent = ScoutAgent(player_id=1)
        obs_msg = self._make_obs_msg()
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        for cmd in result.metadata["commands"]:
            assert cmd["action"] == "move"

    def test_command_format_has_required_keys(self):
        """Each move command must include unit_id, target_x, target_y, issuer."""
        agent = ScoutAgent(player_id=1)
        obs_msg = self._make_obs_msg()
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        for cmd in result.metadata["commands"]:
            assert "action" in cmd
            assert "unit_id" in cmd
            assert "target_x" in cmd
            assert "target_y" in cmd
            assert "issuer" in cmd

    def test_damaged_scout_retreats(self):
        """A scout below retreat threshold should move toward base."""
        obs_msg = Msg(
            name="simcore",
            content="obs",
            role="user",
            metadata={
                "tick": 3,
                "entities": {
                    "scout_1": {
                        "owner": 1,
                        "entity_type": "scout",
                        "is_idle": True,
                        "pos_x": 20,
                        "pos_y": 20,
                        "health": 20,
                        "max_health": 60,
                    },
                    "base_p1": {
                        "owner": 1,
                        "entity_type": "building",
                        "building_type": "base",
                        "pos_x": 9.6,
                        "pos_y": 9.6,
                        "health": 1500,
                    },
                },
                "fog_of_war": {},
            },
        )
        agent = ScoutAgent(player_id=1)
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        # Retreat move: target should be near base coordinates
        retreat_cmds = [
            c for c in result.metadata["commands"]
            if abs(c["target_x"] - 9.6) < 1 and abs(c["target_y"] - 9.6) < 1
        ]
        assert len(retreat_cmds) > 0


class TestScoutAgentReplyIdle:
    """Test ScoutAgent.reply when no observation is given (idle)."""

    def test_idle_without_obs_msg(self):
        agent = ScoutAgent(name="scout", player_id=1)
        result = asyncio.run(agent.reply())
        assert isinstance(result, Msg)
        assert result.content == "idle"
        assert result.role == "assistant"
        assert result.name == "scout"

    def test_idle_metadata_empty_commands(self):
        agent = ScoutAgent(player_id=1)
        result = asyncio.run(agent.reply())
        assert result.metadata == {"commands": []}

    def test_idle_with_kwargs_none(self):
        """Passing obs_msg=None explicitly should also result in idle."""
        agent = ScoutAgent(player_id=1)
        result = asyncio.run(agent.reply(obs_msg=None))
        assert result.content == "idle"
        assert result.metadata["commands"] == []

    def test_idle_with_empty_args(self):
        """Calling reply() with no args at all."""
        agent = ScoutAgent(player_id=1)
        result = asyncio.run(agent.reply())
        assert result.content == "idle"


class TestScoutAgentMetadata:
    """Test metadata correctness across scenarios."""

    def test_metadata_is_dict(self):
        agent = ScoutAgent(player_id=1)
        obs_msg = Msg(
            name="simcore", content="obs", role="user",
            metadata={"tick": 1, "entities": {}, "fog_of_war": {}},
        )
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert isinstance(result.metadata, dict)

    def test_no_scouts_no_commands(self):
        """If observation has no scout units, commands should be empty."""
        obs_msg = Msg(
            name="simcore", content="obs", role="user",
            metadata={
                "tick": 2,
                "entities": {
                    "w1": {"owner": 1, "entity_type": "worker", "is_idle": True,
                           "pos_x": 5, "pos_y": 5},
                },
                "fog_of_war": {},
            },
        )
        agent = ScoutAgent(player_id=1)
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert result.metadata["commands"] == []

    def test_other_player_scouts_ignored(self):
        """Scouts owned by other players should not generate commands."""
        obs_msg = Msg(
            name="simcore", content="obs", role="user",
            metadata={
                "tick": 3,
                "entities": {
                    "scout_e1": {
                        "owner": 2, "entity_type":"scout", "is_idle": True,
                        "pos_x": 50, "pos_y": 50, "health": 60, "max_health": 60,
                    },
                },
                "fog_of_war": {},
            },
        )
        agent = ScoutAgent(player_id=1)
        result = asyncio.run(agent.reply(obs_msg=obs_msg))
        assert result.metadata["commands"] == []