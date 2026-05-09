"""Tests for GRPO trainer and ReactAdapter."""

import numpy as np

from agents.react_adapter import ReactGameAgent, _dist_sq
from train.grpo_trainer import (
    GRPOConfig,
    GRPOTrainer,
    RolloutBuffer,
    SimplePolicy,
    Transition,
)


class TestRolloutBuffer:
    def test_add_and_len(self):
        buf = RolloutBuffer(group_size=4)
        assert len(buf) == 0
        t = Transition(
            obs={"entities": np.zeros((64, 10)), "resources": np.zeros(4), "tick": np.zeros(1)},
            action=0, reward=1.0,
            next_obs={"entities": np.zeros((64, 10)), "resources": np.zeros(4), "tick": np.zeros(1)},
            terminated=False, truncated=False,
        )
        buf.add(t)
        assert len(buf) == 1

    def test_compute_advantages(self):
        buf = RolloutBuffer(group_size=4)
        for r in [1.0, 2.0, 3.0, 4.0]:
            buf.add(Transition(
                obs={"entities": np.zeros((64, 10)), "resources": np.zeros(4), "tick": np.zeros(1)},
                action=0, reward=r,
                next_obs={"entities": np.zeros((64, 10)), "resources": np.zeros(4), "tick": np.zeros(1)},
                terminated=False, truncated=False,
            ))
        adv = buf.compute_advantages()
        assert len(adv) == 4
        # Higher rewards should have positive advantages
        assert adv[3] > adv[0]


class TestSimplePolicy:
    def test_act_returns_valid(self):
        policy = SimplePolicy(n_actions=100, lr=0.01)
        obs = {"entities": np.zeros((64, 10)), "resources": np.zeros(4), "tick": np.zeros(1)}
        action, log_prob, value = policy.act(obs)
        assert 0 <= action < 100
        assert isinstance(log_prob, float)
        assert isinstance(value, float)

    def test_update_modifies_preferences(self):
        policy = SimplePolicy(n_actions=10, lr=0.1)
        prefs_before = policy._preferences.copy()
        policy.update(np.array([0, 1, 2]), np.array([1.0, -1.0, 0.5]))
        assert not np.array_equal(prefs_before, policy._preferences)


class TestReactGameAgent:
    def test_decide_returns_dict(self):
        agent = ReactGameAgent(player_id=1)
        obs = {
            "tick": 0,
            "entities": {
                "base_p1": {"owner": 1, "entity_type": "building", "building_type": "base", "pos_x": 10, "pos_y": 10, "health": 1500, "max_health": 1500, "is_idle": True},
                "worker_0": {"owner": 1, "entity_type": "worker", "pos_x": 11, "pos_y": 10, "health": 50, "max_health": 50, "is_idle": True, "speed": 2.0, "attack": 5, "attack_range": 1.0, "carry_amount": 0, "carry_capacity": 10},
                "mineral_0": {"owner": 0, "entity_type": "resource", "resource_type": "mineral", "resource_amount": 500, "pos_x": 14, "pos_y": 10, "health": 0, "max_health": 0, "is_idle": True},
            },
            "resources": {"p1_mineral": 0, "p1_gas": 0},
        }
        result = agent.decide(obs)
        assert "commands" in result
        assert "tick" in result
        assert isinstance(result["commands"], list)

    def test_build_prompt_contains_key_info(self):
        agent = ReactGameAgent(player_id=1)
        obs = {"tick": 5, "entities": {"base_p1": {"owner": 1, "entity_type": "building", "building_type": "base", "pos_x": 10, "pos_y": 10, "health": 1500, "max_health": 1500, "is_idle": True}}, "resources": {"p1_mineral": 100}}
        prompt = agent._build_prompt(obs)
        assert "Tick 5" in prompt
        assert "Player 1" in prompt

    def test_parse_action_json(self):
        agent = ReactGameAgent(player_id=1)
        text = 'Here is my plan: {"commands": [{"action": "move", "unit_id": "w1", "target_x": 10, "target_y": 20}]}'
        cmds = agent.parse_action(text)
        assert len(cmds) == 1
        assert cmds[0]["action"] == "move"

    def test_parse_action_text(self):
        agent = ReactGameAgent(player_id=1)
        text = "move worker_1 to 15 25"
        cmds = agent.parse_action(text)
        assert len(cmds) >= 1
        assert cmds[0]["action"] == "move"

    def test_dist_sq(self):
        a = {"pos_x": 0, "pos_y": 0}
        b = {"pos_x": 3, "pos_y": 4}
        assert _dist_sq(a, b) == 25.0


class TestGRPOTrainerSmoke:
    """Smoke test: 2-episode training run."""

    def test_smoke_train(self, tmp_path):
        config = GRPOConfig(
            episodes=2,
            batch_size=2,
            group_size=2,
            log_interval=1,
            save_interval=1,
            output_dir=str(tmp_path / "output"),
        )
        trainer = GRPOTrainer(config)
        result = trainer.train()
        assert result["episodes"] == 2
        assert len(trainer.metrics) == 2
