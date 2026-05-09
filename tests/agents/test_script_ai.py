"""Tests for baseline scripted AI."""
from agents.script_ai import ScriptAI


class TestScriptAI:
    """Test ScriptAI decision-making."""

    def test_returns_commands_key(self):
        """decide() returns a dict with 'commands'."""
        ai = ScriptAI(player_id=1)
        result = ai.decide({"tick": 1, "entities": {}})
        assert "commands" in result

    def test_returns_tick_key(self):
        """decide() returns a dict with 'tick'."""
        ai = ScriptAI(player_id=1)
        result = ai.decide({"tick": 0, "entities": {}})
        assert "tick" in result

    def test_empty_observation(self):
        """Handles empty observation gracefully."""
        ai = ScriptAI(player_id=1)
        result = ai.decide({"tick": 0, "entities": {}})
        assert result["commands"] == []
        assert result["tick"] == 0

    def test_tick_matches_observation(self):
        """Returned tick matches input observation."""
        ai = ScriptAI(player_id=1)
        result = ai.decide({"tick": 42, "entities": {}})
        assert result["tick"] == 42

    def test_gather_idle_workers(self):
        """Idle workers are assigned to gather minerals."""
        ai = ScriptAI(player_id=1)
        obs = {
            "tick": 1,
            "entities": {
                "w1": {
                    "owner": 1, "entity_type": "worker",
                    "is_idle": True, "pos_x": 5, "pos_y": 5,
                },
                "m1": {"owner": 0, "entity_type": "resource", "resource_type": "mineral",
                       "pos_x": 6, "pos_y": 6, "resource_amount": 500},
            },
            "resources": {"p1_mineral": 200},
        }
        result = ai.decide(obs)
        gather_cmds = [c for c in result["commands"] if c.get("action") == "gather"]
        assert len(gather_cmds) > 0
