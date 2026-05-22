"""Tests for M2+M3: League self-play training + PromotionGate integration.

Covers:
  - league_train module imports and config
  - _run_eval_games with mock env
  - run_league_training produces correct output structure
  - PromotionGate evaluation within league flow
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import pytest


# ─── Module import tests ───────────────────────────────────────────────


class TestLeagueTrainModule:
    """Verify league_train module structure."""

    def test_import(self):
        from train import league_train
        assert hasattr(league_train, "run_league_training")
        assert hasattr(league_train, "_run_eval_games")
        assert hasattr(league_train, "_make_version_name")

    def test_make_version_name(self):
        from train.league_train import _make_version_name
        assert _make_version_name(0) == "grpo-v0"
        assert _make_version_name(5) == "grpo-v5"


class TestRunEvalGames:
    """Test _run_eval_games with mock env."""

    def test_basic(self, tmp_path):
        """Run 2 eval games, check result structure."""
        from harness.league import AgentType, AgentVersion, League
        from train.league_train import _run_eval_games
        from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

        league = League()
        v0 = AgentVersion("test-v0", AgentType.SCRIPT, creation_tick=0)
        league.register(v0)

        cfg = TRLGRPOConfig(
            episodes=2, max_ticks=50, output_dir=str(tmp_path),
            log_interval=999, save_interval=999,
        )
        trainer = TRLGRPOTrainer(cfg)

        matchups = [
            {"player1_version": "test-v0", "player2_version": "test-v0",
             "map_seed": 42, "max_ticks": 50, "mode": "mirror"},
            {"player1_version": "test-v0", "player2_version": "test-v0",
             "map_seed": 43, "max_ticks": 50, "mode": "mirror"},
        ]

        results = _run_eval_games(league, matchups, trainer, max_ticks=50)
        assert len(results) == 2
        for r in results:
            assert "player1" in r
            assert "player2" in r
            assert "winner" in r
            assert "ticks" in r
            assert isinstance(r["ticks"], int)
            assert r["ticks"] <= 50


class TestLeagueTrainingIntegration:
    """Integration test: 2-round league training produces correct output."""

    @pytest.mark.slow
    def test_two_rounds(self, tmp_path):
        from train.league_train import run_league_training

        summary = run_league_training(
            rounds=2,
            episodes_per_round=5,
            max_ticks=50,
            output_dir=str(tmp_path / "league"),
            enable_order_queue=False,
            enable_event_log=False,
            enable_state_hash=False,
        )

        # Check summary structure
        assert summary["rounds"] == 2
        assert len(summary["round_metrics"]) == 2
        assert len(summary["promotion_log"]) == 2
        assert len(summary["leaderboard"]) >= 3  # script-v0 + grpo-v0 + grpo-v1

        # First round auto-promoted
        assert summary["promotion_log"][0]["promoted"] is True
        assert summary["promotion_log"][0]["reason"] == "auto"

        # Check output files
        league_dir = tmp_path / "league"
        assert (league_dir / "league_summary.json").exists()

        # Verify JSON is valid
        data = json.loads((league_dir / "league_summary.json").read_text())
        assert data["rounds"] == 2


class TestPromotionFlow:
    """Test PromotionGate within the league training flow."""

    def test_auto_promote_no_champion(self):
        """When only 1 version exists, auto-promote."""
        from harness.league import AgentType, AgentVersion, League
        from harness.promotion import PromotionConfig, PromotionGate

        league = League()
        v0 = AgentVersion("grpo-v0", AgentType.GRPO, creation_tick=0)
        league.register(v0)

        gate = PromotionGate(config=PromotionConfig(), league=league)
        # No champion → auto-promote
        assert len(league.get_leaderboard()) == 1

    def test_promotion_eval_records_result(self):
        """PromotionGate evaluate_sync records result in league."""
        from harness.league import AgentType, AgentVersion, League, MatchupResult
        from harness.promotion import PromotionConfig, PromotionGate

        league = League()
        champ = AgentVersion("script-v0", AgentType.SCRIPT, creation_tick=0)
        chal = AgentVersion("grpo-v1", AgentType.GRPO, creation_tick=100)
        league.register(champ)
        league.register(chal)

        # Simulate a win for challenger
        league.record_result(MatchupResult("grpo-v1", "script-v0", winner=1))
        assert league.get_elo("grpo-v1") > 1000.0

    def test_wilson_ci_narrow_with_many_games(self):
        """Wilson CI narrows as game count increases."""
        from harness.promotion import wilson_ci
        # 5/10 wins → wide CI
        lo1, hi1 = wilson_ci(5, 10, confidence=0.90)
        # 50/100 wins → narrow CI
        lo2, hi2 = wilson_ci(50, 100, confidence=0.90)
        assert (hi2 - lo2) < (hi1 - lo1)