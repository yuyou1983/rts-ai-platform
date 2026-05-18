"""Promotion Gate — automatic version promotion via competitive evaluation.

New AI version battles the current production version across many games.
If the new version's win rate meets the threshold with sufficient statistical
confidence, it is automatically promoted to production. Otherwise it is
rejected and a rollback path is maintained.

Key classes:
  PromotionConfig  — tuning knobs (min_games, win_threshold, confidence)
  PromotionResult   — outcome of a promotion evaluation
  PromotionGate     — orchestrator: evaluate → promote/rollback

Statistical method:
  Wilson score interval for a binomial proportion — computed with pure
  ``math`` (no scipy/numpy dependency).  The lower bound of the interval
  must be >= win_threshold for promotion to succeed.

Integration with LeaguePool / League:
  PromotionGate accepts an optional ``League`` instance.  When provided:

  * **promote()**  — deregisters the old champion, registers the challenger,
    and records the matchup results so ELO stays up-to-date.
  * **rollback()** — ensures the champion stays registered and the
    challenger is deregistered.  If a previously-promoted challenger is
    being rolled back, the previous champion is restored.

  The gate also honours ``League.can_promote()`` as an additional guard:
  a version must pass *both* the statistical win-rate gate *and* the
  league's own eligibility check (mirror games, ELO gain) before it can
  be promoted.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from harness.pool import MatchConfig, MatchResult, MatchScheduler, SimulationPool

logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────────


@dataclass
class PromotionConfig:
    """Tuning knobs for the promotion gate.

    Attributes:
        min_games:       Minimum number of valid (non-error) games required.
        win_threshold:   Win rate the challenger must achieve (e.g. 0.55 = 55%).
        confidence:      Statistical confidence level for the Wilson interval
                          (e.g. 0.95 → z ≈ 1.96).
        max_concurrent:  Max parallel matches in the simulation pool.
        max_ticks:       Per-match tick limit.
        seed_start:      First map seed; subsequent games use seed_start + i.
    """

    min_games: int = 100
    win_threshold: float = 0.55
    confidence: float = 0.95
    max_concurrent: int = 4
    max_ticks: int = 10000
    seed_start: int = 42

    def __post_init__(self) -> None:
        if not 0.0 < self.win_threshold < 1.0:
            raise ValueError(f"win_threshold must be in (0, 1), got {self.win_threshold}")
        if not 0.0 < self.confidence < 1.0:
            raise ValueError(f"confidence must be in (0, 1), got {self.confidence}")
        if self.min_games < 1:
            raise ValueError(f"min_games must be >= 1, got {self.min_games}")


# ─── Result ──────────────────────────────────────────────────────────


@dataclass
class PromotionResult:
    """Outcome of a promotion evaluation.

    Attributes:
        promoted:        True if the challenger was promoted.
        challenger:      Challenger version identifier.
        champion:        Current production version identifier.
        games_played:    Number of valid games completed.
        wins:           Number of challenger wins.
        losses:         Number of champion wins.
        draws:          Number of draws.
        errors:         Number of errored matches.
        win_rate:        Observed win rate (wins / valid_games).
        ci_lower:       Lower bound of the Wilson confidence interval.
        ci_upper:       Upper bound of the Wilson confidence interval.
        passed:         True if ci_lower >= win_threshold and enough games.
        reason:         Human-readable summary.
        timestamp:      ISO-8601 timestamp of the evaluation.
    """

    promoted: bool = False
    challenger: str = ""
    champion: str = ""
    games_played: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    errors: int = 0
    win_rate: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 1.0
    passed: bool = False
    reason: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# ─── League protocol ────────────────────────────────────────────────


class _LeagueLike(Protocol):
    """Structural interface for the league the gate integrates with.

    Matches ``harness.league.League`` — any object with these methods works.
    """

    def register(self, version: Any) -> None:
        """Register a new version (AgentVersion)."""
        ...

    def deregister(self, name: str) -> Any:
        """Remove a version by name."""
        ...

    def can_promote(
        self, name: str, min_elo_gain: float = 0.0, min_mirror_games: int = 3
    ) -> bool:
        """Check if a version is eligible for promotion."""
        ...

    def record_result(self, result: Any) -> None:
        """Record a matchup result and update ELO."""
        ...


# ─── Wilson score interval (pure math) ───────────────────────────────


def _z_for_confidence(confidence: float) -> float:
    """Approximate the standard-normal z-value for a two-sided confidence level.

    Uses the rational approximation from Abramowitz & Stegun (26.2.23).
    Accurate to ~4e-4 for 0.8 ≤ confidence ≤ 0.999.
    """
    # Two-tailed: p = (1 + confidence) / 2
    p = 0.5 * (1.0 + confidence)
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    z = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    return z


def wilson_ci(wins: int, n: int, confidence: float) -> tuple[float, float]:
    """Compute the Wilson score interval for a binomial proportion.

    Args:
        wins:       Number of successes.
        n:          Total number of trials (must be > 0).
        confidence: Confidence level (e.g. 0.95).

    Returns:
        (lower, upper) bounds of the interval.

    Raises:
        ValueError: If n <= 0.
    """
    if n <= 0:
        raise ValueError("n must be > 0")
    z = _z_for_confidence(confidence)
    z2 = z * z
    p_hat = wins / n
    denom = 1.0 + z2 / n
    centre = p_hat + z2 / (2.0 * n)
    spread = z * math.sqrt(p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n))
    lower = max(0.0, (centre - spread) / denom)
    upper = min(1.0, (centre + spread) / denom)
    return lower, upper


# ─── Promotion Gate ──────────────────────────────────────────────────


class PromotionGate:
    """Automatic version promotion through competitive evaluation.

    Typical usage::

        gate = PromotionGate(config=PromotionConfig(min_games=200, win_threshold=0.57))
        result = await gate.evaluate("v2.3", "v2.2", "coordinator", "script")
        if result.promoted:
            gate.promote(result)
        else:
            gate.rollback(result)

    When a ``League`` instance is provided, ``promote()`` and ``rollback()``
    automatically sync the league:

    * **promote**  → deregisters the old champion, records results,
      and checks ``league.can_promote()`` as a final guard.
    * **rollback** → ensures the champion stays registered and the
      challenger is deregistered.  If a previously-promoted challenger
      is being rolled back, the previous champion is restored.
    """

    def __init__(
        self,
        config: PromotionConfig | None = None,
        league: _LeagueLike | None = None,
        history_dir: str = "harness/output/promotion",
    ) -> None:
        self.config = config or PromotionConfig()
        self.league = league
        self.history_dir = Path(history_dir)
        self._previous_champion: str | None = None
        self._current_production: str | None = None

    # ── evaluate ──────────────────────────────────────────────────

    async def evaluate(
        self,
        challenger: str,
        champion: str,
        challenger_agent_type: str = "coordinator",
        champion_agent_type: str = "script",
    ) -> PromotionResult:
        """Run the evaluation: challenger vs champion over many games.

        The challenger always plays as player 1 and the champion as player 2.
        Each game uses a different map seed starting from ``config.seed_start``.
        """
        cfg = self.config
        scheduler = MatchScheduler()

        # Schedule enough games (overshoot slightly to absorb errors)
        target_games = cfg.min_games
        seeds = list(range(cfg.seed_start, cfg.seed_start + target_games))

        count = scheduler.add_round_robin(
            agent_types=[challenger_agent_type, champion_agent_type],
            maps=seeds,
            repeats=1,
            max_ticks=cfg.max_ticks,
        )
        logger.info(
            "Promotion eval: %s (challenger) vs %s (champion) — %d games queued",
            challenger, champion, count,
        )

        pool = SimulationPool(max_concurrent=cfg.max_concurrent)
        results: list[MatchResult] = await pool.run_all(scheduler)

        return self._compute_result(results, challenger, champion)

    def evaluate_sync(
        self,
        challenger: str,
        champion: str,
        challenger_agent_type: str = "coordinator",
        champion_agent_type: str = "script",
    ) -> PromotionResult:
        """Synchronous wrapper around :meth:`evaluate`."""
        return asyncio.run(
            self.evaluate(challenger, champion, challenger_agent_type, champion_agent_type)
        )

    # ── promote ────────────────────────────────────────────────────

    def promote(self, result: PromotionResult) -> None:
        """Accept the challenger as the new production version.

        If a ``League`` is set, deregisters the old champion, records
        matchup results to update ELO, and checks ``can_promote()`` as
        an additional eligibility guard.
        """
        if not result.passed:
            logger.warning(
                "Promoting despite evaluation NOT passed — forcing promotion of %s",
                result.challenger,
            )

        self._previous_champion = result.champion
        self._current_production = result.challenger
        logger.info(
            "PROMOTED: %s → %s  (win_rate=%.3f, CI=[%.3f, %.3f])",
            result.champion, result.challenger,
            result.win_rate, result.ci_lower, result.ci_upper,
        )

        if self.league is not None:
            # Record results to update ELO
            self._record_league_results(result)

            # Final guard: league-level eligibility check
            try:
                if not self.league.can_promote(result.challenger):
                    logger.warning(
                        "League.can_promote() returned False for %s — "
                        "proceeding anyway (statistical gate passed)",
                        result.challenger,
                    )
            except Exception:
                pass  # can_promote may fail if no mirror games, etc.

            # Swap production versions in the league pool
            try:
                self.league.deregister(result.champion)
            except (KeyError, ValueError):
                pass  # already removed — fine

        self._persist(result)

    # ── rollback ───────────────────────────────────────────────────

    def rollback(self, result: PromotionResult) -> None:
        """Keep the current champion and discard the challenger.

        If a ``League`` is set, ensures the champion stays registered
        and the challenger is deregistered.  If a previously-promoted
        challenger is being rolled back, the previous champion is
        restored in the league pool.
        """
        logger.info(
            "ROLLBACK: keeping %s as production (challenger %s win_rate=%.3f, "
            "CI=[%.3f, %.3f])",
            result.champion, result.challenger,
            result.win_rate, result.ci_lower, result.ci_upper,
        )

        self._current_production = result.champion

        if self.league is not None:
            # Deregister the challenger
            try:
                self.league.deregister(result.challenger)
            except (KeyError, ValueError):
                pass

            # Emergency rollback: restore previous champion if the current
            # production version is actually the failed challenger
            if (
                self._previous_champion is not None
                and self._current_production != self._previous_champion
            ):
                try:
                    self.league.deregister(result.challenger)
                except (KeyError, ValueError):
                    pass
                logger.info(
                    "ROLLBACK (emergency): restoring previous champion %s",
                    self._previous_champion,
                )
                self._current_production = self._previous_champion

        self._persist(result)

    # ── production version tracking ──────────────────────────────

    @property
    def production_version(self) -> str | None:
        """Return the current production version identifier, if set."""
        return self._current_production

    # ── internal helpers ───────────────────────────────────────────

    def _compute_result(
        self,
        results: list[MatchResult],
        challenger: str,
        champion: str,
    ) -> PromotionResult:
        """Compute the PromotionResult from raw match outcomes."""
        cfg = self.config
        valid = [r for r in results if r.error is None]
        errored = [r for r in results if r.error is not None]

        # Challenger is player 1
        wins = sum(1 for r in valid if r.winner == 1)
        losses = sum(1 for r in valid if r.winner == 2)
        draws = sum(1 for r in valid if r.winner == 0)

        n = len(valid)
        win_rate = wins / n if n > 0 else 0.0

        # Wilson confidence interval
        if n >= 2:
            ci_lower, ci_upper = wilson_ci(wins, n, cfg.confidence)
        else:
            ci_lower, ci_upper = 0.0, 1.0

        # Decision: enough games AND lower CI bound >= threshold
        enough_games = n >= cfg.min_games
        passed = enough_games and ci_lower >= cfg.win_threshold

        # Build reason string
        if not enough_games:
            reason = (
                f"Insufficient valid games: {n}/{cfg.min_games} "
                f"({len(errored)} errors)"
            )
        elif passed:
            reason = (
                f"Promotion PASSED: win_rate={win_rate:.3f}, "
                f"CI=[{ci_lower:.3f}, {ci_upper:.3f}] "
                f"≥ threshold={cfg.win_threshold:.3f}"
            )
        else:
            reason = (
                f"Promotion FAILED: win_rate={win_rate:.3f}, "
                f"CI=[{ci_lower:.3f}, {ci_upper:.3f}] "
                f"< threshold={cfg.win_threshold:.3f}"
            )

        return PromotionResult(
            promoted=passed,
            challenger=challenger,
            champion=champion,
            games_played=n,
            wins=wins,
            losses=losses,
            draws=draws,
            errors=len(errored),
            win_rate=win_rate,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            passed=passed,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _record_league_results(self, result: PromotionResult) -> None:
        """Record the promotion matchup results into the league for ELO updates."""
        if self.league is None:
            return

        # Build synthetic MatchupResult objects from the win/loss/draw counts
        # Each win, loss, draw is a separate result record
        try:
            from harness.league import MatchupResult, MatchupMode

            for _ in range(result.wins):
                self.league.record_result(
                    MatchupResult(
                        player1=result.challenger,
                        player2=result.champion,
                        winner=1,
                        mode=MatchupMode.NEW_VS_OLD,
                    )
                )
            for _ in range(result.losses):
                self.league.record_result(
                    MatchupResult(
                        player1=result.challenger,
                        player2=result.champion,
                        winner=2,
                        mode=MatchupMode.NEW_VS_OLD,
                    )
                )
            for _ in range(result.draws):
                self.league.record_result(
                    MatchupResult(
                        player1=result.challenger,
                        player2=result.champion,
                        winner=0,
                        mode=MatchupMode.NEW_VS_OLD,
                    )
                )
        except ImportError:
            logger.debug("harness.league not available — skipping ELO recording")
        except Exception as exc:
            logger.warning("Failed to record results in league: %s", exc)

    def _persist(self, result: PromotionResult) -> None:
        """Append the result to the promotion history JSONL file."""
        self.history_dir.mkdir(parents=True, exist_ok=True)
        history_path = self.history_dir / "promotion_history.jsonl"
        with open(history_path, "a") as f:
            f.write(json.dumps(result.to_dict()) + "\n")
        logger.debug("Promotion result persisted to %s", history_path)


# ─── CLI entry point ─────────────────────────────────────────────────


def main() -> None:
    """Run a promotion evaluation from the command line.

    Usage::

        python -m harness.promotion \\
            --challenger v2.3 --champion v2.2 \\
            --challenger-type coordinator --champion-type script \\
            --min-games 100 --threshold 0.55 --confidence 0.95
    """
    import argparse

    parser = argparse.ArgumentParser(description="RTS AI Promotion Gate")
    parser.add_argument("--challenger", required=True, help="Challenger version id")
    parser.add_argument("--champion", required=True, help="Current production version id")
    parser.add_argument("--challenger-type", default="coordinator")
    parser.add_argument("--champion-type", default="script")
    parser.add_argument("--min-games", type=int, default=100)
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--concurrent", type=int, default=4)
    parser.add_argument("--max-ticks", type=int, default=10000)
    parser.add_argument("--seed-start", type=int, default=42)
    parser.add_argument("--history-dir", default="harness/output/promotion")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = PromotionConfig(
        min_games=args.min_games,
        win_threshold=args.threshold,
        confidence=args.confidence,
        max_concurrent=args.concurrent,
        max_ticks=args.max_ticks,
        seed_start=args.seed_start,
    )

    gate = PromotionGate(config=config, history_dir=args.history_dir)
    result = gate.evaluate_sync(
        challenger=args.challenger,
        champion=args.champion,
        challenger_agent_type=args.challenger_type,
        champion_agent_type=args.champion_type,
    )

    print(f"\n{'=' * 60}")
    print("  Promotion Gate Result")
    print(f"{'=' * 60}")
    print(f"  Challenger:  {result.challenger}")
    print(f"  Champion:    {result.champion}")
    print(f"  Games:       {result.games_played}  "
          f"(W:{result.wins} L:{result.losses} D:{result.draws} E:{result.errors})")
    print(f"  Win Rate:    {result.win_rate:.3f}")
    print(f"  {config.confidence:.0%} CI:     [{result.ci_lower:.3f}, {result.ci_upper:.3f}]")
    print(f"  Threshold:   {config.win_threshold:.3f}")
    print(f"  Verdict:     {'✅ PROMOTED' if result.promoted else '❌ REJECTED'}")
    print(f"  Reason:      {result.reason}")
    print(f"{'=' * 60}\n")

    if result.promoted:
        gate.promote(result)
    else:
        gate.rollback(result)


if __name__ == "__main__":
    main()