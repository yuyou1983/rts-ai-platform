#!/usr/bin/env python3
"""RL training runner — PPO+GAE policy optimization with RolloutWorker."""
import json
import logging
import time
from pathlib import Path

from train.rl_trainer import RLTrainer, RLTrainerConfig
from train.rollout_worker import RolloutWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    # 1. Create trainer config
    config = RLTrainerConfig(
        episodes=100,
        batch_size=32,
        learning_rate=3e-4,
        gamma=0.99,
        gae_lambda=0.95,
        clip_ratio=0.2,
        entropy_coeff=0.01,
        value_coeff=0.5,
        ppo_epochs=4,
        max_ticks=5000,
        log_interval=10,
        save_interval=10,
        output_dir="train/checkpoints",
    )

    # 2. Create trainer (auto-fallback to SimplePolicy if no torch)
    trainer = RLTrainer(config=config)

    # 3. Also create a RolloutWorker for concurrent episode collection
    worker = RolloutWorker(
        num_workers=4,
        max_steps=config.max_ticks,
    )

    # 4. Training loop
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("Starting RL training...")
    t0 = time.monotonic()

    # Use the trainer's built-in train() method for the main PPO loop.
    # This handles collection, GAE, PPO updates, logging, and checkpointing.
    result = trainer.train()

    wall = time.monotonic() - t0
    print(f"\nTraining complete: {wall:.1f}s, {config.episodes} episodes")
    print(f"  Result: {result}")

    # 5. Also do a separate rollout collection + save for analysis
    print("\nCollecting rollouts with RolloutWorker for evaluation...")
    episodes = worker.run(n_episodes=4, base_seed=9999)
    total_transitions = sum(len(ep) for ep in episodes)
    print(f"  Collected {len(episodes)} episodes, {total_transitions} transitions")

    # 6. Save final checkpoint and metrics
    trainer.save_checkpoint(out / "checkpoint_final.pt")

    metrics_path = out / "training_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(trainer.metrics, f, indent=2)

    # Save rollout summary
    rollout_summary = {
        "n_episodes": len(episodes),
        "total_transitions": total_transitions,
        "avg_episode_length": total_transitions / len(episodes) if episodes else 0,
    }
    with open(out / "rollout_summary.json", "w") as f:
        json.dump(rollout_summary, f, indent=2)

    print(f"Checkpoints saved to {out}/")
    print(f"Metrics saved to {metrics_path}")


if __name__ == "__main__":
    main()