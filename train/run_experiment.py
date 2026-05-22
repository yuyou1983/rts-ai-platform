"""Run baseline vs enhanced training comparison.

Compares training with all SimCore feature flags disabled (baseline)
against training with flags enabled (enhanced). Outputs a comparison
JSON with timing, reward, and loss metrics.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run_comparison(
    episodes: int = 100,
    max_ticks: int = 200,
    output_base: str = "train/output",
) -> dict[str, Any]:
    """Run two training runs: baseline (flags off) vs enhanced (flags on).

    Parameters
    ----------
    episodes : int
        Number of training episodes per run.
    max_ticks : int
        Max ticks per episode.
    output_base : str
        Base directory for output artifacts.

    Returns
    -------
    dict[str, Any]
        Comparison metrics for baseline vs enhanced.
    """
    import numpy as np

    from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

    base = Path(output_base)

    # ── Baseline: all flags off ───────────────────────────────────────
    logger.info("Starting baseline training run (flags OFF) ...")
    cfg_base = TRLGRPOConfig(
        episodes=episodes,
        max_ticks=max_ticks,
        output_dir=str(base / "baseline"),
        enable_state_hash=False,
        enable_order_queue=False,
        enable_event_log=False,
        enable_replay_v2=False,
    )
    trainer_base = TRLGRPOTrainer(cfg_base)
    t0 = time.time()
    trainer_base.train()
    time_base = time.time() - t0
    logger.info("Baseline training completed in %.1fs", time_base)

    # ── Enhanced: flags on ─────────────────────────────────────────────
    logger.info("Starting enhanced training run (flags ON) ...")
    cfg_enh = TRLGRPOConfig(
        episodes=episodes,
        max_ticks=max_ticks,
        output_dir=str(base / "enhanced"),
        enable_state_hash=True,
        enable_order_queue=True,
        enable_event_log=True,
        enable_replay_v2=False,  # replay_v2 can be heavy; off by default
    )
    trainer_enh = TRLGRPOTrainer(cfg_enh)
    t0 = time.time()
    trainer_enh.train()
    time_enh = time.time() - t0
    logger.info("Enhanced training completed in %.1fs", time_enh)

    # ── Compare ───────────────────────────────────────────────────────
    base_rewards = [m["reward"] for m in trainer_base.metrics]
    enh_rewards = [m["reward"] for m in trainer_enh.metrics]
    base_losses = [m.get("total_loss", 0) for m in trainer_base.metrics]
    enh_losses = [m.get("total_loss", 0) for m in trainer_enh.metrics]

    comparison: dict[str, Any] = {
        "baseline": {
            "time": time_base,
            "reward_mean": float(np.mean(base_rewards)) if base_rewards else 0.0,
            "reward_last20": (
                float(np.mean(base_rewards[-20:]))
                if len(base_rewards) >= 20
                else float(np.mean(base_rewards)) if base_rewards else 0.0
            ),
            "loss_first10": (
                float(np.mean(base_losses[:10]))
                if len(base_losses) >= 10
                else float(np.mean(base_losses)) if base_losses else 0.0
            ),
            "loss_last10": (
                float(np.mean(base_losses[-10:]))
                if len(base_losses) >= 10
                else float(np.mean(base_losses)) if base_losses else 0.0
            ),
        },
        "enhanced": {
            "time": time_enh,
            "reward_mean": float(np.mean(enh_rewards)) if enh_rewards else 0.0,
            "reward_last20": (
                float(np.mean(enh_rewards[-20:]))
                if len(enh_rewards) >= 20
                else float(np.mean(enh_rewards)) if enh_rewards else 0.0
            ),
            "loss_first10": (
                float(np.mean(enh_losses[:10]))
                if len(enh_losses) >= 10
                else float(np.mean(enh_losses)) if enh_losses else 0.0
            ),
            "loss_last10": (
                float(np.mean(enh_losses[-10:]))
                if len(enh_losses) >= 10
                else float(np.mean(enh_losses)) if enh_losses else 0.0
            ),
        },
    }

    out_path = base / "comparison.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(comparison, indent=2))
    print(f"\nComparison saved to {out_path}")
    print(json.dumps(comparison, indent=2))
    return comparison


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_comparison()