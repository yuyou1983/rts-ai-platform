"""League Self-Play Training — Multi-version adversarial GRPO training.

This script implements the full M2 pipeline:
  1. Train a GRPO policy for N episodes
  2. Register the new version with the League
  3. Generate matchups (new vs old)
  4. Run evaluation games
  5. Record results → update ELO
  6. Evaluate PromotionGate
  7. Repeat for multiple rounds

Usage:
    python -m train.league_train --rounds 3 --episodes 50

Each round produces a new agent version. PromotionGate decides whether
the new version replaces the champion.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from harness.league import AgentType, AgentVersion, League, MatchupConfig, MatchupMode
from harness.promotion import PromotionConfig, PromotionGate

from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

logger = logging.getLogger(__name__)


def _make_version_name(round_idx: int) -> str:
    return f"grpo-v{round_idx}"


def _run_eval_games(
    league: League,
    matchups: list[dict[str, Any]],
    trainer: TRLGRPOTrainer,
    max_ticks: int = 200,
) -> list[dict[str, Any]]:
    """Run evaluation games for generated matchups.

    Returns a list of result dicts with keys:
      player1, player2, winner, ticks, p1_reward, p2_reward
    """
    import gymnasium as gym
    import simcore.gym_env  # noqa: F401

    results: list[dict[str, Any]] = []
    cfg = trainer.config

    for i, matchup in enumerate(matchups):
        # Each matchup is a self-play game — both sides use the same policy
        # but we track which version each side represents
        env = gym.make(
            cfg.env_id,
            seed=matchup.get("map_seed", cfg.seed + i),
            max_ticks=max_ticks,
            reward_shaping=cfg.reward_shaping,
            enable_state_hash=cfg.enable_state_hash,
            enable_order_queue=cfg.enable_order_queue,
            enable_event_log=cfg.enable_event_log,
        )
        obs, info = env.reset(seed=matchup.get("map_seed", cfg.seed + i))

        policy = trainer._ensure_policy(env)

        total_reward_p1 = 0.0
        total_reward_p2 = 0.0
        ticks = 0
        winner = 0

        while True:
            action, _, _ = policy.act(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward_p1 += reward
            ticks += 1

            if terminated or truncated:
                winner = info.get("winner", 0)
                break

        env.close()

        results.append({
            "player1": matchup.get("player1_version", "?"),
            "player2": matchup.get("player2_version", "?"),
            "winner": winner,
            "ticks": ticks,
            "p1_reward": total_reward_p1,
            "p2_reward": total_reward_p2,
        })

    return results


def run_league_training(
    *,
    rounds: int = 3,
    episodes_per_round: int = 50,
    max_ticks: int = 200,
    output_dir: str = "train/output/league",
    enable_order_queue: bool = True,
    enable_event_log: bool = True,
    enable_state_hash: bool = True,
) -> dict[str, Any]:
    """Run full league self-play training loop.

    Parameters
    ----------
    rounds : int
        Number of training rounds (each produces a new agent version).
    episodes_per_round : int
        Episodes to train per round.
    max_ticks : int
        Max ticks per episode/game.
    output_dir : str
        Base output directory.
    enable_order_queue : bool
        Enable SimCore order queue feature flag.
    enable_event_log : bool
        Enable SimCore event log feature flag.
    enable_state_hash : bool
        Enable SimCore state hash feature flag.

    Returns
    -------
    dict[str, Any]
        Summary with league state, promotion history, and metrics.
    """
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    league = League()
    promotion_gate = PromotionGate(
        config=PromotionConfig(
            min_games=10,
            win_threshold=0.50,
            confidence=0.80,
            max_ticks=max_ticks,
        ),
        league=league,
    )

    # Register initial scripted baseline
    v0 = AgentVersion("script-v0", AgentType.SCRIPT, creation_tick=0)
    league.register(v0)

    all_metrics: list[dict[str, Any]] = []
    promotion_log: list[dict[str, Any]] = []
    t0 = time.time()

    for round_idx in range(rounds):
        round_dir = base / f"round_{round_idx}"
        version_name = _make_version_name(round_idx)
        logger.info("=== Round %d: Training %s ===", round_idx, version_name)

        # ── 1. Train new version ────────────────────────────────────
        cfg = TRLGRPOConfig(
            episodes=episodes_per_round,
            max_ticks=max_ticks,
            output_dir=str(round_dir),
            enable_state_hash=enable_state_hash,
            enable_order_queue=enable_order_queue,
            enable_event_log=enable_event_log,
            group_size=4,
            ppo_epochs=2,
            log_interval=10,
        )
        trainer = TRLGRPOTrainer(cfg)
        train_result = trainer.train()

        # ── 2. Register with League ──────────────────────────────────
        new_version = AgentVersion(
            name=version_name,
            type=AgentType.GRPO,
            checkpoint_path=str(round_dir / "final_model.pt"),
            creation_tick=int(time.time()),
            metadata={
                "round": round_idx,
                "episodes": episodes_per_round,
                "train_time": train_result.get("total_time", 0),
            },
        )
        league.register(new_version)

        # ── 3. Generate matchups (new vs all old) ──────────────────
        matchup_config = MatchupConfig(
            mode=MatchupMode.NEW_VS_OLD,
            games_per_pair=2,
            max_ticks=max_ticks,
        )
        matchups = league.generate_matchups(matchup_config)

        if not matchups:
            logger.info("No matchups generated — only 1 version in league")
            round_metrics = {
                "round": round_idx,
                "version": version_name,
                "train_result": train_result,
                "matchups": 0,
                "promoted": True,  # auto-promote if only version
                "elo": 1000.0,
            }
            all_metrics.append(round_metrics)
            promotion_log.append({"round": round_idx, "version": version_name, "promoted": True, "reason": "auto"})
            continue

        # ── 4. Run eval games ────────────────────────────────────────
        logger.info("Running %d evaluation games...", len(matchups))
        eval_results = _run_eval_games(league, matchups, trainer, max_ticks=max_ticks)

        # ── 5. Record results ───────────────────────────────────────
        from harness.league import MatchupResult
        league_results = []
        wins = 0
        for r in eval_results:
            winner_name = r["player1"] if r["winner"] == 1 else r["player2"]
            league_results.append(MatchupResult(r["player1"], r["player2"], winner=r["winner"]))
            if winner_name == version_name:
                wins += 1

        league.record_results(league_results)
        win_rate = wins / len(eval_results) if eval_results else 0.0
        new_elo = league.get_elo(version_name)

        logger.info(
            "Round %d: %s — win_rate=%.2f, elo=%.0f, games=%d",
            round_idx, version_name, win_rate, new_elo, len(eval_results),
        )

        # ── 6. Promotion evaluation ─────────────────────────────────
        # Find the champion (highest ELO non-new version)
        champion = None
        for vs in league.get_leaderboard():
            if vs.name != version_name:
                champion = vs.name
                break

        promoted = False
        if champion:
            promo_result = promotion_gate.evaluate_sync(
                challenger=version_name,
                champion=champion,
                challenger_agent_type="grpo",
                champion_agent_type="script",
            )
            promoted = promo_result.promoted
            if promoted:
                promotion_gate.promote(promo_result)
            else:
                promotion_gate.rollback(promo_result)

            logger.info(
                "Promotion: %s vs %s → promoted=%s, win_rate=%.2f, CI=[%.2f, %.2f]",
                version_name, champion, promoted,
                promo_result.win_rate, promo_result.ci_lower, promo_result.ci_upper,
            )
        else:
            promoted = True

        round_metrics = {
            "round": round_idx,
            "version": version_name,
            "train_result": train_result,
            "matchups": len(matchups),
            "eval_games": len(eval_results),
            "win_rate": win_rate,
            "elo": new_elo,
            "promoted": promoted,
        }
        all_metrics.append(round_metrics)
        promotion_log.append({
            "round": round_idx,
            "version": version_name,
            "promoted": promoted,
            "win_rate": win_rate,
            "elo": new_elo,
        })

    # ── Final summary ────────────────────────────────────────────────
    total_time = time.time() - t0
    summary = {
        "total_time": total_time,
        "rounds": rounds,
        "leaderboard": [
            {"name": s.name, "elo": s.elo, "games_played": s.games_played, "wins": s.wins}
            for s in league.get_leaderboard()
        ],
        "promotion_log": promotion_log,
        "round_metrics": all_metrics,
    }

    out_path = base / "league_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    logger.info("League training complete: %.1fs, %d rounds", total_time, rounds)
    logger.info("Leaderboard:\n%s", json.dumps(summary["leaderboard"], indent=2))

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="League Self-Play Training")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--max-ticks", type=int, default=200)
    parser.add_argument("--output-dir", default="train/output/league")
    parser.add_argument("--enable-order-queue", action="store_true", default=True)
    parser.add_argument("--no-order-queue", dest="enable_order_queue", action="store_false")
    parser.add_argument("--enable-event-log", action="store_true", default=True)
    parser.add_argument("--no-event-log", dest="enable_event_log", action="store_false")
    parser.add_argument("--enable-state-hash", action="store_true", default=True)
    parser.add_argument("--no-state-hash", dest="enable_state_hash", action="store_false")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    run_league_training(
        rounds=args.rounds,
        episodes_per_round=args.episodes,
        max_ticks=args.max_ticks,
        output_dir=args.output_dir,
        enable_order_queue=args.enable_order_queue,
        enable_event_log=args.enable_event_log,
        enable_state_hash=args.enable_state_hash,
    )


if __name__ == "__main__":
    main()