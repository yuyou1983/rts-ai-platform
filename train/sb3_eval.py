"""SB3 PPO Evaluation Script — evaluate a trained model over N episodes.

Loads a saved stable-baselines3 PPO model, runs evaluation episodes,
and reports aggregate metrics:

  - Win rate   (fraction of episodes where info["winner"] == 1)
  - Mean episode reward
  - Mean APM    (actions per minute of game-time, derived from info)

Usage:
    python -m train.sb3_eval --model-path train/output/sb3_ppo.zip --episodes 10
    python -m train.sb3_eval --model-path train/output/sb3_ppo.zip --episodes 10 --render ascii

Notes:
  - Requires stable-baselines3 (pip install stable-baselines3).
  - The environment is wrapped with FlattenRTSObs so that the Dict
    observation space becomes a flat Box, which SB3 expects.
  - If the model file does not exist, a fresh PPO model is trained for
    ``--quick-train-steps`` steps (default 1024) and then evaluated.
    This is useful for smoke-testing the evaluation pipeline.
"""
from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ─── Optional SB3 import ─────────────────────────────────────

try:
    import gymnasium as gym
    from stable_baselines3 import PPO

    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False
    PPO = None  # type: ignore[assignment, misc]
    gym = None  # type: ignore[assignment]


# ─── Eval Config ────────────────────────────────────────────


@dataclass
class EvalConfig:
    """Configuration for SB3 PPO evaluation."""

    model_path: str = "train/output/sb3_ppo.zip"
    episodes: int = 10
    seed: int = 42
    max_ticks: int = 10000
    reward_shaping: str = "shaped"
    render: bool = False
    render_mode: str = "ascii"
    deterministic: bool = True
    quick_train_steps: int = 1024  # steps for ad-hoc training when model missing
    verbose: bool = True


# ─── Environment Factory ─────────────────────────────────────


def make_eval_env(cfg: EvalConfig) -> Any:
    """Create a wrapped evaluation environment.

    Applies FlattenRTSObs so the Dict obs becomes a flat Box(645,),
    which is required by stable-baselines3 PPO.
    """
    import gymnasium as gym  # type: ignore[no-redef]

    import simcore.gym_env  # noqa: F401 — register rts-ai-v0
    from simcore.wrappers import FlattenRTSObs

    render_mode = cfg.render_mode if cfg.render else None
    env = gym.make(
        "rts-ai-v0",
        seed=cfg.seed,
        max_ticks=cfg.max_ticks,
        reward_shaping=cfg.reward_shaping,
        render_mode=render_mode,
    )
    env = FlattenRTSObs(env)
    return env


# ─── Evaluation Loop ────────────────────────────────────────


@dataclass
class EvalResult:
    """Aggregated evaluation results."""

    episodes: int = 0
    wins: int = 0
    total_reward: float = 0.0
    total_steps: int = 0
    total_ticks: int = 0
    episode_rewards: list[float] = field(default_factory=list)
    episode_lengths: list[int] = field(default_factory=list)
    episode_apms: list[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / max(self.episodes, 1)

    @property
    def mean_reward(self) -> float:
        return float(np.mean(self.episode_rewards)) if self.episode_rewards else 0.0

    @property
    def mean_apm(self) -> float:
        return float(np.mean(self.episode_apms)) if self.episode_apms else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "episodes": self.episodes,
            "win_rate": self.win_rate,
            "mean_reward": self.mean_reward,
            "mean_apm": self.mean_apm,
            "mean_episode_length": float(np.mean(self.episode_lengths))
            if self.episode_lengths
            else 0.0,
        }


def _compute_apm(steps: int, ticks: int) -> float:
    """Compute APM (Actions Per Minute of in-game time).

    Each step = 1 action.  Game time assumes ~24 ticks per second
    (standard RTS speed).  APM = actions / (ticks / 24 / 60).
    Simplified: APM = actions * 24 * 60 / max(ticks, 1)
               = actions * 1440 / max(ticks, 1).
    """
    if ticks <= 0:
        return 0.0
    return steps * 1440.0 / ticks


def evaluate(model: Any, cfg: EvalConfig) -> EvalResult:
    """Run *cfg.episodes* evaluation episodes and return aggregated results.

    Parameters
    ----------
    model :
        A stable-baselines3 PPO (or compatible) model with a ``predict`` method.
    cfg :
        Evaluation configuration.

    Returns
    -------
    EvalResult
        Aggregated metrics across all episodes.
    """
    env = make_eval_env(cfg)
    result = EvalResult()

    for ep in range(cfg.episodes):
        obs, info = env.reset(seed=cfg.seed + ep)
        episode_reward = 0.0
        episode_steps = 0
        final_info: dict[str, Any] = {}

        while True:
            action, _ = model.predict(obs, deterministic=cfg.deterministic)
            obs, reward, terminated, truncated, info = env.step(action)
            episode_reward += float(reward)
            episode_steps += 1
            final_info = info

            if terminated or truncated:
                break

        # Determine winner from final info
        winner = final_info.get("winner", 0)
        won = winner == 1
        final_tick = final_info.get("tick", 0)

        apm = _compute_apm(episode_steps, final_tick)

        result.episodes += 1
        result.wins += int(won)
        result.total_reward += episode_reward
        result.total_steps += episode_steps
        result.total_ticks += final_tick
        result.episode_rewards.append(episode_reward)
        result.episode_lengths.append(episode_steps)
        result.episode_apms.append(apm)

        if cfg.verbose:
            logger.info(
                "Episode %d | reward=%.2f | steps=%d | tick=%d | winner=%s | APM=%.1f",
                ep,
                episode_reward,
                episode_steps,
                final_tick,
                winner,
                apm,
            )

    env.close()
    return result


# ─── Model Loading / Quick Train ─────────────────────────────


def load_or_quick_train(cfg: EvalConfig) -> Any:
    """Load a saved model, or quick-train one if the file is missing.

    This allows the eval script to be smoke-tested end-to-end even
    without a pre-trained model checkpoint.
    """
    model_path = Path(cfg.model_path)

    if model_path.exists():
        logger.info("Loading model from %s", model_path)
        model = PPO.load(str(model_path))
        return model

    logger.warning(
        "Model not found at %s — quick-training for %d steps",
        model_path,
        cfg.quick_train_steps,
    )
    env = make_eval_env(cfg)
    model = PPO(
        "MlpPolicy",
        env,
        verbose=0,
        seed=cfg.seed,
        n_steps=cfg.quick_train_steps,
    )
    model.learn(total_timesteps=cfg.quick_train_steps)
    # Save for potential reuse
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    env.close()
    return model


# ─── CLI ─────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a trained SB3 PPO model on RTS-AI-Platform"
    )
    parser.add_argument(
        "--model-path",
        default="train/output/sb3_ppo.zip",
        help="Path to saved SB3 PPO model (.zip)",
    )
    parser.add_argument(
        "--episodes", type=int, default=10, help="Number of evaluation episodes"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--max-ticks", type=int, default=10000, help="Max ticks per episode"
    )
    parser.add_argument(
        "--reward-shaping",
        default="shaped",
        choices=["sparse", "shaped"],
        help="Reward shaping mode",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        default=False,
        help="Enable ASCII rendering",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        default=True,
        help="Use deterministic policy (default True)",
    )
    parser.add_argument(
        "--quick-train-steps",
        type=int,
        default=1024,
        help="Steps for ad-hoc training when model missing",
    )
    parser.add_argument(
        "--log-level", default="INFO", help="Python logging level"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if not HAS_SB3:
        logger.error(
            "stable-baselines3 is not installed. "
            "Install it with: pip install stable-baselines3"
        )
        raise SystemExit(1)

    cfg = EvalConfig(
        model_path=args.model_path,
        episodes=args.episodes,
        seed=args.seed,
        max_ticks=args.max_ticks,
        reward_shaping=args.reward_shaping,
        render=args.render,
        deterministic=args.deterministic,
        quick_train_steps=args.quick_train_steps,
    )

    start = time.time()
    model = load_or_quick_train(cfg)
    result = evaluate(model, cfg)
    elapsed = time.time() - start

    summary = result.summary()
    summary["eval_time_s"] = round(elapsed, 2)

    print("\n" + "=" * 50)
    print("  SB3 PPO Evaluation Summary")
    print("=" * 50)
    print(f"  Episodes:        {summary['episodes']}")
    print(f"  Win Rate:        {summary['win_rate']:.1%}")
    print(f"  Mean Reward:     {summary['mean_reward']:.2f}")
    print(f"  Mean APM:        {summary['mean_apm']:.1f}")
    print(f"  Mean Ep Length:  {summary['mean_episode_length']:.1f}")
    print(f"  Eval Time:       {summary['eval_time_s']:.1f}s")
    print("=" * 50)

    # Also dump to JSON next to model
    import json

    model_path = Path(cfg.model_path)
    report_path = model_path.with_suffix(".eval.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Evaluation report saved to %s", report_path)


if __name__ == "__main__":
    main()
