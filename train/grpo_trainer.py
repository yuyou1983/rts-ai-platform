"""GRPO Training Loop — Self-play RL for RTS agents using TRL.

Group Relative Policy Optimization (GRPO) for training RTS agents
via self-play. Uses the Gym environment as the reward source.

Architecture:
  1. Collect rollouts: agent vs ScriptAI
  2. Compute group-relative advantages
  3. Update policy via PPO-style clipped objective
  4. Repeat

When TRL is available, TRLGRPOTrainer (from train.trl_trainer) is used
for full PyTorch-based GRPO training with TRL's group-relative advantage
formula. Falls back to SimplePolicy (numpy-only) when TRL/PyTorch absent.

Usage:
    python -m train.grpo_trainer --episodes 1000 --batch-size 32
    python -m train.grpo_trainer --episodes 100 --use-trl
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ─── Optional TRL import ─────────────────────────────────────

try:
    import trl as _trl

    HAS_TRL = True
    _TRL_VERSION = _trl.__version__
except ImportError:
    HAS_TRL = False
    _TRL_VERSION = ""

# ─── Config ────────────────────────────────────────────────


@dataclass
class GRPOConfig:
    """GRPO training hyperparameters."""

    # Environment
    env_id: str = "rts-ai-v0"
    seed: int = 42
    max_ticks: int = 5000

    # Training
    episodes: int = 1000
    batch_size: int = 32
    group_size: int = 4  # rollouts per state for advantage estimation
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    entropy_coeff: float = 0.01
    value_coeff: float = 0.5
    max_grad_norm: float = 0.5

    # Logging
    log_interval: int = 10
    save_interval: int = 100
    output_dir: str = "train/output"
    reward_shaping: str = "shaped"

    # TRL integration
    use_trl: bool = True  # use TRLGRPOTrainer when TRL + PyTorch available


# ─── Rollout Buffer ────────────────────────────────────────


@dataclass
class Transition:
    """Single timestep transition."""

    obs: dict[str, np.ndarray]
    action: int
    reward: float
    next_obs: dict[str, np.ndarray]
    terminated: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)
    log_prob: float = 0.0
    value: float = 0.0


class RolloutBuffer:
    """Collects transitions and computes GRPO advantages."""

    def __init__(self, group_size: int = 4) -> None:
        self.group_size = group_size
        self.transitions: list[Transition] = []

    def add(self, t: Transition) -> None:
        self.transitions.append(t)

    def __len__(self) -> int:
        return len(self.transitions)

    def __iter__(self):
        return iter(self.transitions)

    def clear(self) -> None:
        self.transitions.clear()

    def compute_advantages(self) -> np.ndarray:
        """Group-relative advantage estimation.

        For each group of `group_size` rollouts from the same state,
        compute advantage = reward - mean(group_rewards).
        """
        if not self.transitions:
            return np.array([])

        rewards = np.array([t.reward for t in self.transitions])
        advantages = np.zeros_like(rewards)

        n = len(rewards)
        for start in range(0, n, self.group_size):
            end = min(start + self.group_size, n)
            group_rewards = rewards[start:end]
            group_mean = np.mean(group_rewards)
            group_std = np.std(group_rewards) + 1e-8
            advantages[start:end] = (group_rewards - group_mean) / group_std

        return advantages


# ─── Simple Policy Network (numpy-only for zero deps) ──────


class SimplePolicy:
    """Minimal feedforward policy for prototyping.

    In production, replace with a PyTorch policy network.
    This version uses random actions with slight reward bias.
    """

    def __init__(self, n_actions: int, lr: float = 3e-4) -> None:
        self.n_actions = n_actions
        self.lr = lr
        self._preferences = np.zeros(n_actions)

    def act(self, obs: dict[str, np.ndarray]) -> tuple[int, float, float]:
        """Sample action, return (action, log_prob, value)."""
        probs = self._softmax(self._preferences)
        action = np.random.choice(self.n_actions, p=probs)
        log_prob = np.log(probs[action] + 1e-10)
        value = float(np.mean(obs["resources"]))
        return int(action), float(log_prob), float(value)

    def update(self, actions: np.ndarray, advantages: np.ndarray) -> float:
        """Simple policy gradient update."""
        for a, adv in zip(actions, advantages, strict=False):
            self._preferences[a] += self.lr * adv
        return float(np.mean(advantages ** 2))

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        e = np.exp(x - np.max(x))
        return e / (e.sum() + 1e-10)


# ─── Training Loop ────────────────────────────────────────


class GRPOTrainer:
    """GRPO self-play trainer for RTS agents."""

    def __init__(self, config: GRPOConfig | None = None) -> None:
        self.config = config or GRPOConfig()
        self.buffer = RolloutBuffer(group_size=self.config.group_size)
        self.metrics: list[dict[str, Any]] = []

    def train(self) -> dict[str, Any]:
        """Run full training loop."""
        import gymnasium as gym

        import simcore.gym_env  # noqa: F401 — register env

        cfg = self.config
        env = gym.make(
            cfg.env_id,
            seed=cfg.seed,
            max_ticks=cfg.max_ticks,
            reward_shaping=cfg.reward_shaping,
        )

        policy = SimplePolicy(n_actions=env.action_space.n, lr=cfg.learning_rate)
        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Starting GRPO training: %d episodes", cfg.episodes)
        start_time = time.time()

        for episode in range(cfg.episodes):
            obs, info = env.reset(seed=cfg.seed + episode)
            episode_reward = 0.0
            episode_length = 0

            while True:
                action, log_prob, value = policy.act(obs)
                next_obs, reward, terminated, truncated, info = env.step(action)

                self.buffer.add(Transition(
                    obs=obs, action=action, reward=reward,
                    next_obs=next_obs, terminated=terminated,
                    truncated=truncated, info=info,
                    log_prob=log_prob, value=value,
                ))

                episode_reward += reward
                episode_length += 1
                obs = next_obs

                if terminated or truncated:
                    break

            # Compute advantages and update
            if len(self.buffer) >= cfg.group_size:
                advantages = self.buffer.compute_advantages()
                actions = np.array([t.action for t in self.buffer])
                loss = policy.update(actions, advantages)
            else:
                loss = 0.0

            # Metrics
            metric = {
                "episode": episode,
                "reward": episode_reward,
                "length": episode_length,
                "loss": loss,
                "winner": info.get("winner", 0),
                "fps": episode_length / max(time.time() - start_time, 1e-6),
            }
            self.metrics.append(metric)

            if episode % cfg.log_interval == 0:
                recent = self.metrics[-cfg.log_interval:]
                avg_reward = np.mean([m["reward"] for m in recent])
                avg_length = np.mean([m["length"] for m in recent])
                win_rate = np.mean([1 if m["winner"] == 1 else 0 for m in recent])
                logger.info(
                    "Ep %d | reward=%.2f | len=%.0f | win_rate=%.1f%% | loss=%.4f",
                    episode, avg_reward, avg_length, win_rate * 100, loss,
                )

            if episode % cfg.save_interval == 0 and episode > 0:
                self._save_checkpoint(output_dir / f"checkpoint_{episode}.json")

            self.buffer.clear()

        # Final save
        final_path = output_dir / "final_metrics.json"
        self._save_metrics(final_path)
        env.close()

        total_time = time.time() - start_time
        logger.info("Training complete: %.1fs, %d episodes", total_time, cfg.episodes)
        return {"total_time": total_time, "episodes": cfg.episodes}

    def _save_checkpoint(self, path: Path) -> None:
        if self.metrics:
            data = self.metrics[-1]
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    def _save_metrics(self, path: Path) -> None:
        with open(path, "w") as f:
            json.dump(self.metrics, f, indent=2)


# ─── TRL-aware factory ─────────────────────────────────────


def create_grpo_trainer(
    config: GRPOConfig | None = None,
) -> GRPOTrainer:
    """Create the appropriate GRPO trainer based on TRL availability.

    When TRL is installed and ``config.use_trl`` is True (the default),
    returns a :class:`~train.trl_trainer.TRLGRPOTrainer` which uses
    PyTorch and TRL's group-relative advantage formula for full GRPO
    training. Otherwise returns the numpy-only :class:`GRPOTrainer`
    (SimplePolicy-based, for prototyping).

    Parameters
    ----------
    config : GRPOConfig, optional
        Training configuration.  When *None*, defaults are used.

    Returns
    -------
    GRPOTrainer or TRLGRPOTrainer
    """
    config = config or GRPOConfig()

    if config.use_trl and HAS_TRL:
        try:
            from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

            trl_config = TRLGRPOConfig(
                env_id=config.env_id,
                seed=config.seed,
                max_ticks=config.max_ticks,
                reward_shaping=config.reward_shaping,
                episodes=config.episodes,
                batch_size=config.batch_size,
                group_size=config.group_size,
                learning_rate=config.learning_rate,
                gamma=config.gamma,
                clip_eps=config.clip_eps,
                entropy_coeff=config.entropy_coeff,
                value_coeff=config.value_coeff,
                max_grad_norm=config.max_grad_norm,
                log_interval=config.log_interval,
                save_interval=config.save_interval,
                output_dir=config.output_dir,
            )
            logger.info(
                "TRL %s available — using TRLGRPOTrainer", _TRL_VERSION
            )
            return TRLGRPOTrainer(trl_config)  # type: ignore[return-value]
        except Exception as exc:
            logger.warning(
                "TRLGRPOTrainer creation failed (%s) — falling back to "
                "SimplePolicy GRPOTrainer",
                exc,
            )

    logger.info("Using SimplePolicy GRPOTrainer (numpy-only)")
    return GRPOTrainer(config)


# ─── CLI ───────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="GRPO Trainer for RTS AI")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--group-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--reward-shaping", default="shaped")
    parser.add_argument("--output-dir", default="train/output")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--use-trl", action="store_true", default=True,
        help="Use TRLGRPOTrainer when TRL is available (default: True)",
    )
    parser.add_argument(
        "--no-trl", dest="use_trl", action="store_false",
        help="Force SimplePolicy GRPOTrainer even when TRL is available",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = GRPOConfig(
        episodes=args.episodes,
        batch_size=args.batch_size,
        group_size=args.group_size,
        learning_rate=args.lr,
        reward_shaping=args.reward_shaping,
        output_dir=args.output_dir,
        use_trl=args.use_trl,
    )

    trainer = create_grpo_trainer(config)
    result = trainer.train()
    print(f"\nTraining result: {result}")


if __name__ == "__main__":
    main()
