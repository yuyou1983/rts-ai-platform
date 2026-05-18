"""Tests for harness.promotion — PromotionGate, Wilson CI, PromotionConfig."""
from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.promotion import (
    PromotionConfig,
    PromotionGate,
    PromotionResult,
    wilson_ci,
    _z_for_confidence,
)
from harness.pool import MatchResult


# ─── Wilson CI tests ─────────────────────────────────────────────────

class TestWilsonCI:
    """Validate the pure-math Wilson score interval."""

    def test_all_wins(self):
        lo, hi = wilson_ci(100, 100, 0.95)
        assert lo > 0.9
        assert hi >= 0.999

    def test_all_losses(self):
        lo, hi = wilson_ci(0, 100, 0.95)
        assert lo == 0.0
        assert hi < 0.1

    def test_fifty_fifty(self):
        lo, hi = wilson_ci(50, 100, 0.95)
        assert 0.35 < lo < 0.5
        assert 0.5 < hi < 0.65

    def test_small_n(self):
        lo, hi = wilson_ci(1, 2, 0.95)
        assert 0.0 < lo < 0.5
        assert 0.5 < hi < 1.0

    def test_zero_n_raises(self):
        with pytest.raises(ValueError, match="n must be > 0"):
            wilson_ci(0, 0, 0.95)

    def test_symmetry(self):
        """CI for k/n should be mirror of CI for (n-k)/n when p=0.5."""
        lo1, hi1 = wilson_ci(30, 100, 0.95)
        lo2, hi2 = wilson_ci(70, 100, 0.95)
        # Mirror around 0.5
        assert abs(lo1 - (1 - hi2)) < 0.02
        assert abs(hi1 - (1 - lo2)) < 0.02

    def test_increasing_confidence_widens_interval(self):
        lo_90, hi_90 = wilson_ci(55, 100, 0.90)
        lo_99, hi_99 = wilson_ci(55, 100, 0.99)
        assert lo_99 < lo_90
        assert hi_99 > hi_90

    def test_known_value(self):
        """Cross-check against a known Wilson interval (n=100, k=55, conf=0.95).

        Expected approximate: [0.452, 0.643] per standard tables.
        """
        lo, hi = wilson_ci(55, 100, 0.95)
        assert abs(lo - 0.452) < 0.02
        assert abs(hi - 0.643) < 0.02


class TestZForConfidence:
    """Validate the z-value approximation."""

    def test_95_percent(self):
        z = _z_for_confidence(0.95)
        assert abs(z - 1.96) < 0.02

    def test_99_percent(self):
        z = _z_for_confidence(0.99)
        assert abs(z - 2.576) < 0.05

    def test_80_percent(self):
        z = _z_for_confidence(0.80)
        assert abs(z - 1.282) < 0.03

    def test_monotonic(self):
        """Higher confidence → higher z."""
        assert _z_for_confidence(0.90) < _z_for_confidence(0.95) < _z_for_confidence(0.99)


# ─── PromotionConfig tests ──────────────────────────────────────────

class TestPromotionConfig:
    def test_defaults(self):
        cfg = PromotionConfig()
        assert cfg.min_games == 100
        assert cfg.win_threshold == 0.55
        assert cfg.confidence == 0.95

    def test_custom(self):
        cfg = PromotionConfig(min_games=200, win_threshold=0.60, confidence=0.99)
        assert cfg.min_games == 200

    def test_invalid_threshold_zero(self):
        with pytest.raises(ValueError, match="win_threshold"):
            PromotionConfig(win_threshold=0.0)

    def test_invalid_threshold_one(self):
        with pytest.raises(ValueError, match="win_threshold"):
            PromotionConfig(win_threshold=1.0)

    def test_invalid_confidence(self):
        with pytest.raises(ValueError, match="confidence"):
            PromotionConfig(confidence=1.5)

    def test_invalid_min_games(self):
        with pytest.raises(ValueError, match="min_games"):
            PromotionConfig(min_games=0)


# ─── PromotionResult tests ──────────────────────────────────────────

class TestPromotionResult:
    def test_to_dict(self):
        r = PromotionResult(
            promoted=True,
            challenger="v2",
            champion="v1",
            games_played=100,
            wins=60,
            losses=35,
            draws=5,
            errors=0,
            win_rate=0.6,
            ci_lower=0.50,
            ci_upper=0.70,
            passed=True,
            reason="OK",
            timestamp="2026-01-01T00:00:00",
        )
        d = r.to_dict()
        assert d["promoted"] is True
        assert d["challenger"] == "v2"
        assert d["wins"] == 60

    def test_defaults(self):
        r = PromotionResult()
        assert r.promoted is False
        assert r.games_played == 0


# ─── PromotionGate unit tests (no real simulation) ──────────────────

class TestPromotionGateComputeResult:
    """Test _compute_result directly (no async, no simulation)."""

    def _make_gate(self, **kwargs):
        cfg = PromotionConfig(**kwargs)
        return PromotionGate(config=cfg)

    def _make_results(self, winners: list[int]) -> list[MatchResult]:
        return [
            MatchResult(match_id=f"m{i}", winner=w, ticks=500, elapsed=1.0, tps=500.0)
            for i, w in enumerate(winners)
        ]

    def test_clear_win(self):
        """65 wins, 25 losses, 10 draws out of 100 → should pass with threshold 0.55."""
        winners = [1] * 65 + [2] * 25 + [0] * 10
        gate = self._make_gate(min_games=100, win_threshold=0.55, confidence=0.95)
        result = gate._compute_result(self._make_results(winners), "v2", "v1")
        assert result.wins == 65
        assert result.losses == 25
        assert result.draws == 10
        assert result.win_rate == 0.65
        assert result.games_played == 100
        # CI lower should be > 0.55 for 65/100
        assert result.ci_lower > 0.55
        assert result.passed is True
        assert result.promoted is True

    def test_marginal_fail(self):
        """55 wins, 45 losses out of 100 → CI lower may be < 0.55 at 95% confidence."""
        winners = [1] * 55 + [2] * 45
        gate = self._make_gate(min_games=100, win_threshold=0.55, confidence=0.95)
        result = gate._compute_result(self._make_results(winners), "v2", "v1")
        assert result.win_rate == 0.55
        # At 95% CI with 55/100, the lower bound is ~0.452 < 0.55
        assert result.ci_lower < 0.55
        assert result.passed is False

    def test_insufficient_games(self):
        """Only 50 valid games with min_games=100 → should fail."""
        winners = [1] * 40 + [2] * 10
        gate = self._make_gate(min_games=100, win_threshold=0.55)
        result = gate._compute_result(self._make_results(winners), "v2", "v1")
        assert result.games_played == 50
        assert result.passed is False
        assert "Insufficient" in result.reason

    def test_errors_excluded(self):
        """Errored matches should not count toward valid games."""
        valid = [MatchResult(match_id=f"m{i}", winner=1, ticks=500, elapsed=1.0, tps=500.0) for i in range(50)]
        errors = [MatchResult(match_id=f"e{i}", winner=0, ticks=0, elapsed=0.0, tps=0.0, error="crash") for i in range(50)]
        gate = self._make_gate(min_games=100, win_threshold=0.55)
        result = gate._compute_result(valid + errors, "v2", "v1")
        assert result.games_played == 50
        assert result.errors == 50
        assert result.passed is False

    def test_all_draws(self):
        """All draws → win_rate = 0, CI lower = 0, should fail."""
        winners = [0] * 100
        gate = self._make_gate(min_games=100, win_threshold=0.55)
        result = gate._compute_result(self._make_results(winners), "v2", "v1")
        assert result.win_rate == 0.0
        assert result.passed is False

    def test_high_threshold_needs_higher_wr(self):
        """With threshold=0.65, even 60/100 wins fails."""
        winners = [1] * 60 + [2] * 40
        gate = self._make_gate(min_games=100, win_threshold=0.65, confidence=0.95)
        result = gate._compute_result(self._make_results(winners), "v2", "v1")
        assert result.win_rate == 0.60
        assert result.passed is False

    def test_lower_confidence_easier_to_pass(self):
        """At 80% confidence, 56/100 passes threshold 0.55, at 99% it doesn't."""
        winners = [1] * 56 + [2] * 44
        gate_lo = self._make_gate(min_games=100, win_threshold=0.55, confidence=0.80)
        gate_hi = self._make_gate(min_games=100, win_threshold=0.55, confidence=0.99)
        r_lo = gate_lo._compute_result(self._make_results(winners), "v2", "v1")
        r_hi = gate_hi._compute_result(self._make_results(winners), "v2", "v1")
        # Lower confidence → narrower CI → more likely to pass
        assert r_lo.ci_lower > r_hi.ci_lower


class TestPromotionGatePromoteRollback:
    """Test promote/rollback with a mock League."""

    def _make_mock_league(self):
        league = MagicMock()
        league.can_promote.return_value = True
        return league

    def test_promote_updates_production(self):
        league = self._make_mock_league()
        gate = PromotionGate(league=league)
        result = PromotionResult(
            promoted=True, challenger="v2", champion="v1",
            games_played=100, wins=60, losses=30, draws=10, errors=0,
            win_rate=0.6, ci_lower=0.51, ci_upper=0.69,
            passed=True, reason="OK", timestamp="2026-01-01T00:00:00",
        )
        gate.promote(result)
        assert gate.production_version == "v2"
        league.deregister.assert_called_with("v1")

    def test_rollback_keeps_champion(self):
        league = self._make_mock_league()
        gate = PromotionGate(league=league)
        result = PromotionResult(
            promoted=False, challenger="v2", champion="v1",
            games_played=100, wins=40, losses=50, draws=10, errors=0,
            win_rate=0.4, ci_lower=0.30, ci_upper=0.50,
            passed=False, reason="FAILED", timestamp="2026-01-01T00:00:00",
        )
        gate.rollback(result)
        assert gate.production_version == "v1"
        league.deregister.assert_called_with("v2")

    def test_emergency_rollback(self):
        """If a promoted version is later found bad, rollback restores the previous champion."""
        league = self._make_mock_league()
        gate = PromotionGate(league=league)

        # First promote v2
        result_promote = PromotionResult(
            promoted=True, challenger="v2", champion="v1",
            games_played=100, wins=60, losses=30, draws=10, errors=0,
            win_rate=0.6, ci_lower=0.51, ci_upper=0.69,
            passed=True, reason="OK", timestamp="2026-01-01T00:00:00",
        )
        gate.promote(result_promote)
        assert gate.production_version == "v2"

        # Now rollback v2
        result_rollback = PromotionResult(
            promoted=False, challenger="v2", champion="v1",
            games_played=100, wins=30, losses=60, draws=10, errors=0,
            win_rate=0.3, ci_lower=0.21, ci_upper=0.40,
            passed=False, reason="BAD", timestamp="2026-01-01T00:01:00",
        )
        gate.rollback(result_rollback)
        assert gate.production_version == "v1"


class TestPromotionGatePersist:
    """Test that results are persisted to JSONL."""

    def test_persist_creates_file(self, tmp_path):
        gate = PromotionGate(history_dir=str(tmp_path / "promo"))
        result = PromotionResult(
            promoted=True, challenger="v2", champion="v1",
            games_played=10, wins=6, losses=3, draws=1, errors=0,
            win_rate=0.6, ci_lower=0.30, ci_upper=0.85,
            passed=True, reason="OK", timestamp="2026-01-01T00:00:00",
        )
        gate._persist(result)

        history_path = tmp_path / "promo" / "promotion_history.jsonl"
        assert history_path.exists()

        lines = history_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["challenger"] == "v2"
        assert data["promoted"] is True

    def test_persist_appends(self, tmp_path):
        gate = PromotionGate(history_dir=str(tmp_path / "promo"))
        for i in range(3):
            result = PromotionResult(
                challenger=f"v{i}", champion=f"v{i-1}",
                timestamp=f"2026-01-0{i}",
            )
            gate._persist(result)

        history_path = tmp_path / "promo" / "promotion_history.jsonl"
        lines = history_path.read_text().strip().split("\n")
        assert len(lines) == 3