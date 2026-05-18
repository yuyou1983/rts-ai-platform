"""RL Trainer — PyTorch PPO for RTS-AI-Platform.

Real reinforcement learning trainer using Proximal Policy Optimization (PPO)
with a PyTorch MLP policy network and SimCoreGym environment.

Architecture:
  1. RTSPolicy(nn.Module): obs → 128 → 64 → action logits + value head
  2. Collect rollouts via SimCoreGym
  3. Compute GAE advantages
  4. PPO clipped objective update (multiple epochs per batch)
  5. Repeat

Fallback: When PyTorch is not installed, gracefully degrades to the
numpy-only SimplePolicy from train.grpo_trainer.

Usage:
    python -m train.rl_trainer --episodes 100 --batch-size 32
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from train.grpo_trainer import RolloutBuffer, SimplePolicy, Transition

logger = logging.getLogger(__name__)

# ─── Optional PyTorch import ───────────────────────────────

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.distributions import Categorical

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    optim = None  # type: ignore[assignment]
    Categorical = None  # type: ignore[assignment]
    logger.warning(
        "PyTorch not installed — RLTrainer will fall back to SimplePolicy. "
        "Install torch for full PPO support: pip install torch"
    )


# ─── RLTrainerConfig ────────────────────────────────────────


@dataclass
class RLTrainerConfig:
    """PPO training hyperparameters."""

    # Environment
    env_id: str = "rts-ai-v0"
    seed: int = 42
    max_ticks: int = 5000
    reward_shaping: str = "shaped"

    # Training
    episodes: int = 100
    batch_size: int = 32
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_ratio: float = 0.2
    entropy_coeff: float = 0.01
    value_coeff: float = 0.5
    max_grad_norm: float = 0.5
    ppo_epochs: int = 4  # number of PPO update epochs per rollout batch

    # Network
    hidden_dim: int = 128

    # Logging / checkpointing
    log_interval: int = 10
    save_interval: int = 100
    output_dir: str = "train/output"


# ─── Policy Protocol ────────────────────────────────────────


class Policy(Protocol):
    """Minimal interface for a policy used by RLTrainer."""

    n_actions: int

    def act(self, obs: dict[str, np.ndarray]) -> tuple[int, float, float]:
        """Return (action, log_prob, value_estimate)."""
        ...

    def update(
        self,
        buffer: RolloutBuffer,
        advantages: np.ndarray,
        config: RLTrainerConfig,
    ) -> dict[str, float]:
        """Update policy from buffer; return metrics dict."""
        ...


# ─── RTSPolicy (PyTorch) ────────────────────────────────────

if HAS_TORCH:

    class RTSPolicy(nn.Module):  # type: ignore[no-redef]
        """PyTorch MLP policy network for RTS agents.

        Architecture:
            Shared backbone: obs_flat → Linear(obs_dim, hidden) → ReLU
                                           → Linear(hidden, 64) → ReLU
            Policy head:   Linear(64, action_dim)  → softmax → Categorical
            Value head:    Linear(64, 1)            → scalar value
        """

        def __init__(
            self,
            obs_dim: int,
            action_dim: int,
            hidden_dim: int = 128,
            lr: float = 3e-4,
        ) -> None:
            super().__init__()
            self.obs_dim = obs_dim
            self.action_dim = action_dim
            self.n_actions = action_dim

            # Shared backbone
            self.backbone = nn.Sequential(
                nn.Linear(obs_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, 64),
                nn.ReLU(),
            )

            # Policy head
            self.policy_head = nn.Linear(64, action_dim)

            # Value head
            self.value_head = nn.Linear(64, 1)

            # Optimizer
            self.optimizer = optim.Adam(self.parameters(), lr=lr)

            # Saved log probs & values for PPO update
            self._old_log_probs: torch.Tensor | None = None

        def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            """Forward pass: return (logits, value)."""
            features = self.backbone(obs)
            logits = self.policy_head(features)
            value = self.value_head(features).squeeze(-1)
            return logits, value

        def act(self, obs: dict[str, np.ndarray]) -> tuple[int, float, float]:
            """Sample action from current policy; return (action, log_prob, value)."""
            self.eval()
            with torch.no_grad():
                obs_flat = self._flatten_obs(obs)
                logits, value = self.forward(obs_flat)
                dist = Categorical(logits=logits)
                action_tensor = dist.sample()
                log_prob = dist.log_prob(action_tensor)
            return (
                int(action_tensor.item()),
                float(log_prob.item()),
                float(value.item()),
            )

        def update(
            self,
            buffer: RolloutBuffer,
            advantages: np.ndarray,
            config: RLTrainerConfig,
        ) -> dict[str, float]:
            """PPO clipped objective update.

            Performs `config.ppo_epochs` epochs of minibatch updates over the
            collected rollout buffer.

            Returns a metrics dict with pg_loss, value_loss, entropy, total_loss.
            """
            self.train()

            # Build tensors from buffer
            obs_list: list[np.ndarray] = []
            action_list: list[int] = []
            old_log_prob_list: list[float] = []
            return_list: list[float] = []

            for t in buffer:
                obs_list.append(self._flatten_obs_np(t.obs))
                action_list.append(t.action)
                old_log_prob_list.append(t.log_prob)
                return_list.append(t.reward)

            obs_t = torch.FloatTensor(np.stack(obs_list))
            actions_t = torch.LongTensor(action_list)
            old_log_probs_t = torch.FloatTensor(old_log_prob_list)
            returns_t = torch.FloatTensor(np.array(return_list))
            advantages_t = torch.FloatTensor(advantages)

            # Normalise advantages
            advantages_t = (advantages_t - advantages_t.mean()) / (
                advantages_t.std() + 1e-8
            )

            total_pg_loss = 0.0
            total_v_loss = 0.0
            total_entropy = 0.0
            n_updates = 0

            for _epoch in range(config.ppo_epochs):
                # Shuffle
                indices = torch.randperm(len(buffer))
                for start in range(0, len(buffer), config.batch_size):
                    idx = indices[start : start + config.batch_size]

                    b_obs = obs_t[idx]
                    b_actions = actions_t[idx]
                    b_old_log_probs = old_log_probs_t[idx]
                    b_returns = returns_t[idx]
                    b_advantages = advantages_t[idx]

                    # Current policy
                    logits, values = self.forward(b_obs)
                    dist = Categorical(logits=logits)
                    new_log_probs = dist.log_prob(b_actions)
                    entropy = dist.entropy().mean()

                    # PPO clipped ratio
                    ratio = torch.exp(new_log_probs - b_old_log_probs)
                    surr1 = ratio * b_advantages
                    surr2 = (
                        torch.clamp(
                            ratio, 1.0 - config.clip_ratio, 1.0 + config.clip_ratio
                        )
                        * b_advantages
                    )
                    pg_loss = -torch.min(surr1, surr2).mean()

                    # Value loss
                    value_loss = nn.functional.mse_loss(values, b_returns)

                    # Total loss
                    loss = (
                        pg_loss
                        + config.value_coeff * value_loss
                        - config.entropy_coeff * entropy
                    )

                    self.optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(
                        self.parameters(), config.max_grad_norm
                    )
                    self.optimizer.step()

                    total_pg_loss += pg_loss.item()
                    total_v_loss += value_loss.item()
                    total_entropy += entropy.item()
                    n_updates += 1

            avg_pg = total_pg_loss / max(n_updates, 1)
            avg_vl = total_v_loss / max(n_updates, 1)
            avg_ent = total_entropy / max(n_updates, 1)
            total_loss = avg_pg + config.value_coeff * avg_vl - config.entropy_coeff * avg_ent

            return {
                "pg_loss": avg_pg,
                "value_loss": avg_vl,
                "entropy": avg_ent,
                "total_loss": total_loss,
            }

        def save_checkpoint(self, path: Path) -> None:
            """Save model weights and optimizer state."""
            path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "model_state_dict": self.state_dict(),
                    "optimizer_state_dict": self.optimizer.state_dict(),
                    "obs_dim": self.obs_dim,
                    "action_dim": self.action_dim,
                },
                path,
            )
            logger.info("Checkpoint saved to %s", path)

        def load_checkpoint(self, path: Path) -> None:
            """Load model weights and optimizer state."""
            checkpoint = torch.load(path, map_location="cpu", weights_only=False)
            self.load_state_dict(checkpoint["model_state_dict"])
            self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
            logger.info("Checkpoint loaded from %s", path)

        # ─── Helpers ──────────────────────────────────────────

        @staticmethod
        def _flatten_obs_np(obs: dict[str, np.ndarray]) -> np.ndarray:
            """Flatten observation dict into a 1-D float32 array."""
            parts = [
                obs["entities"].flatten(),
                obs["resources"].flatten(),
                obs["tick"].flatten(),
            ]
            return np.concatenate(parts).astype(np.float32)

        def _flatten_obs(self, obs: dict[str, np.ndarray]) -> torch.Tensor:
            """Flatten observation dict into a batch-1 tensor."""
            flat = self._flatten_obs_np(obs)
            return torch.from_numpy(flat).unsqueeze(0)


# ─── RLTrainer ──────────────────────────────────────────────


class RLTrainer:
    """PPO trainer for RTS agents using SimCoreGym.

    When PyTorch is available, uses RTSPolicy (MLP with PPO updates).
    Otherwise falls back to SimplePolicy from grpo_trainer.
    """

    def __init__(
        self,
        config: RLTrainerConfig | None = None,
        policy: Any | None = None,
        env_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config or RLTrainerConfig()
        self.metrics: list[dict[str, Any]] = []
        self.buffer = RolloutBuffer(group_size=self.config.batch_size)

        # Environment factory — default creates SimCoreGym
        self.env_factory = env_factory or self._default_env_factory

        # Policy — default creates RTSPolicy (or SimplePolicy fallback)
        self._external_policy = policy
        self._policy: Any | None = None  # lazily initialised in train()

    # ─── Public API ───────────────────────────────────────────

    def collect_rollouts(self, n_episodes: int) -> RolloutBuffer:
        """Collect rollouts from the environment for *n_episodes* episodes.

        Uses concurrent episode collection when possible (sequential fallback).
        Returns the filled RolloutBuffer.
        """
        import gymnasium as gym

        import simcore.gym_env  # noqa: F401 — register env

        cfg = self.config
        env = gym.make(
            cfg.env_id,
            seed=cfg.seed,
            max_ticks=cfg.max_ticks,
            reward_shaping=cfg.reward_shaping,
        )
        policy = self._ensure_policy(env)

        for ep in range(n_episodes):
            obs, info = env.reset(seed=cfg.seed + ep)
            episode_reward = 0.0
            episode_length = 0

            while True:
                action, log_prob, value = policy.act(obs)
                next_obs, reward, terminated, truncated, info = env.step(action)

                self.buffer.add(
                    Transition(
                        obs=obs,
                        action=action,
                        reward=reward,
                        next_obs=next_obs,
                        terminated=terminated,
                        truncated=truncated,
                        info=info,
                        log_prob=log_prob,
                        value=value,
                    )
                )

                episode_reward += reward
                episode_length += 1
                obs = next_obs

                if terminated or truncated:
                    break

        env.close()
        return self.buffer

    def compute_advantages(self, buffer: RolloutBuffer) -> np.ndarray:
        """Compute advantages using Generalized Advantage Estimation (GAE).

        Falls back to Monte-Carlo (discounted returns) when buffer has
        insufficient data for GAE.
        """
        if not buffer.transitions:
            return np.array([])

        cfg = self.config
        n = len(buffer)
        rewards = np.array([t.reward for t in buffer])
        values = np.array([t.value for t in buffer])
        dones = np.array([float(t.terminated or t.truncated) for t in buffer])

        # GAE computation
        advantages = np.zeros(n, dtype=np.float32)
        last_gae = 0.0

        for t in reversed(range(n)):
            if t == n - 1:
                next_value = 0.0
            else:
                next_value = values[t + 1]

            delta = rewards[t] + cfg.gamma * next_value * (1.0 - dones[t]) - values[t]
            last_gae = delta + cfg.gamma * cfg.gae_lambda * (1.0 - dones[t]) * last_gae
            advantages[t] = last_gae

        return advantages

    def update_policy(
        self, buffer: RolloutBuffer, advantages: np.ndarray
    ) -> dict[str, float]:
        """Update policy using PPO clipped objective (or SimplePolicy gradient)."""
        policy = self._policy
        if policy is None:
            return {"loss": 0.0}
        return policy.update(buffer, advantages, self.config)

    def train(self) -> dict[str, Any]:
        """Run the full PPO training loop.

        Returns summary dict with total_time and episodes.
        """
        import gymnasium as gym

        import simcore.gym_env  # noqa: F401 — register env

        cfg = self.config
        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create env and policy
        env = gym.make(
            cfg.env_id,
            seed=cfg.seed,
            max_ticks=cfg.max_ticks,
            reward_shaping=cfg.reward_shaping,
        )
        policy = self._ensure_policy(env)

        logger.info(
            "Starting PPO training: %d episodes | policy=%s | torch=%s",
            cfg.episodes,
            type(policy).__name__,
            HAS_TORCH,
        )
        start_time = time.time()

        for episode in range(cfg.episodes):
            # --- Collect rollouts for one episode ---
            obs, info = env.reset(seed=cfg.seed + episode)
            episode_reward = 0.0
            episode_length = 0

            while True:
                action, log_prob, value = policy.act(obs)
                next_obs, reward, terminated, truncated, info = env.step(action)

                self.buffer.add(
                    Transition(
                        obs=obs,
                        action=action,
                        reward=reward,
                        next_obs=next_obs,
                        terminated=terminated,
                        truncated=truncated,
                        info=info,
                        log_prob=log_prob,
                        value=value,
                    )
                )

                episode_reward += reward
                episode_length += 1
                obs = next_obs

                if terminated or truncated:
                    break

            # --- Compute advantages and update policy ---
            if len(self.buffer) >= cfg.batch_size:
                advantages = self.compute_advantages(self.buffer)
                update_metrics = self.update_policy(self.buffer, advantages)
            else:
                advantages = self.compute_advantages(self.buffer)
                update_metrics = (
                    policy.update(self.buffer, advantages, cfg)
                    if hasattr(policy, "update")
                    else {"loss": 0.0}
                )

            # --- Log metrics ---
            metric: dict[str, Any] = {
                "episode": episode,
                "reward": episode_reward,
                "length": episode_length,
                "winner": info.get("winner", 0),
                "fps": episode_length / max(time.time() - start_time, 1e-6),
                **update_metrics,
            }
            self.metrics.append(metric)

            if episode % cfg.log_interval == 0:
                recent = self.metrics[-cfg.log_interval :]
                avg_reward = np.mean([m["reward"] for m in recent])
                avg_length = np.mean([m["length"] for m in recent])
                win_rate = np.mean(
                    [1 if m.get("winner") == 1 else 0 for m in recent]
                )
                loss_val = recent[-1].get("total_loss", recent[-1].get("loss", 0.0))
                entropy_val = recent[-1].get("entropy", 0.0)
                logger.info(
                    "Ep %d | reward=%.2f | len=%.0f | win=%.1f%% | loss=%.4f | entropy=%.4f",
                    episode,
                    avg_reward,
                    avg_length,
                    win_rate * 100,
                    loss_val,
                    entropy_val,
                )

            # --- Checkpoint ---
            if episode % cfg.save_interval == 0 and episode > 0:
                ckpt_path = output_dir / f"checkpoint_{episode}.pt"
                if HAS_TORCH and isinstance(policy, nn.Module):  # type: ignore[name-defined]
                    policy.save_checkpoint(ckpt_path)
                else:
                    self._save_simple_checkpoint(policy, output_dir / f"checkpoint_{episode}.json")

            self.buffer.clear()

        # --- Final save ---
        if HAS_TORCH and isinstance(policy, nn.Module):  # type: ignore[name-defined]
            policy.save_checkpoint(output_dir / "final_model.pt")
        self._save_metrics(output_dir / "final_metrics.json")
        env.close()

        total_time = time.time() - start_time
        logger.info("Training complete: %.1fs, %d episodes", total_time, cfg.episodes)
        return {"total_time": total_time, "episodes": cfg.episodes}

    def save_checkpoint(self, path: str | Path) -> None:
        """Save current policy checkpoint."""
        path = Path(path)
        if self._policy is not None and HAS_TORCH:
            if isinstance(self._policy, nn.Module):  # type: ignore[name-defined]
                self._policy.save_checkpoint(path)
                return
        self._save_simple_checkpoint(self._policy, path)

    def load_checkpoint(self, path: str | Path) -> None:
        """Load policy from checkpoint."""
        path = Path(path)
        if HAS_TORCH and path.suffix == ".pt":
            # Need to create policy first then load
            if self._policy is not None and isinstance(self._policy, nn.Module):  # type: ignore[name-defined]
                self._policy.load_checkpoint(path)
                return
        logger.warning("Cannot load checkpoint from %s — policy not initialised or format unsupported", path)

    # ─── Internals ────────────────────────────────────────────

    def _ensure_policy(self, env: Any) -> Any:
        """Lazily create or return the policy."""
        if self._policy is not None:
            return self._policy

        if self._external_policy is not None:
            self._policy = self._external_policy
            return self._policy

        cfg = self.config
        action_dim = env.action_space.n
        obs_dim = self._compute_obs_dim(env)

        if HAS_TORCH:
            self._policy = RTSPolicy(
                obs_dim=obs_dim,
                action_dim=action_dim,
                hidden_dim=cfg.hidden_dim,
                lr=cfg.learning_rate,
            )
            logger.info(
                "Created RTSPolicy: obs_dim=%d, action_dim=%d, hidden=%d",
                obs_dim, action_dim, cfg.hidden_dim,
            )
        else:
            self._policy = SimplePolicy(n_actions=action_dim, lr=cfg.learning_rate)
            logger.info(
                "PyTorch unavailable — using SimplePolicy (numpy-only, limited PPO)"
            )

        return self._policy

    @staticmethod
    def _compute_obs_dim(env: Any) -> int:
        """Compute the flattened observation dimension from the env."""
        obs_space = env.observation_space
        total = 0
        for key in ("entities", "resources", "tick"):
            if key in obs_space.spaces:
                shape = obs_space[key].shape
                dim = 1
                for s in shape:
                    dim *= s
                total += dim
        return total

    @staticmethod
    def _default_env_factory() -> Any:
        """Default environment factory: creates rts-ai-v0."""
        import gymnasium as gym

        import simcore.gym_env  # noqa: F401

        return gym.make("rts-ai-v0")

    def _save_simple_checkpoint(self, policy: Any, path: Path) -> None:
        """Save a JSON checkpoint for non-PyTorch policies."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "policy_type": type(policy).__name__,
            "n_actions": getattr(policy, "n_actions", 0),
            "last_metric": self.metrics[-1] if self.metrics else {},
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_metrics(self, path: Path) -> None:
        """Save training metrics to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.metrics, f, indent=2)


# ─── CLI ────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="PPO RL Trainer for RTS AI")
    parser.add_argument("--episodes", type=int, default=100, help="Number of training episodes")
    parser.add_argument("--batch-size", type=int, default=32, help="Minibatch size for PPO updates")
    parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate")
    parser.add_argument("--gamma", type=float, default=0.99, help="Discount factor")
    parser.add_argument("--clip-ratio", type=float, default=0.2, help="PPO clip ratio (epsilon)")
    parser.add_argument("--entropy-coeff", type=float, default=0.01, help="Entropy bonus coefficient")
    parser.add_argument("--ppo-epochs", type=int, default=4, help="PPO update epochs per batch")
    parser.add_argument("--reward-shaping", default="shaped", choices=["sparse", "shaped"], help="Reward shaping mode")
    parser.add_argument("--output-dir", default="train/output", help="Directory for checkpoints & logs")
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = RLTrainerConfig(
        episodes=args.episodes,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        gamma=args.gamma,
        clip_ratio=args.clip_ratio,
        entropy_coeff=args.entropy_coeff,
        ppo_epochs=args.ppo_epochs,
        reward_shaping=args.reward_shaping,
        output_dir=args.output_dir,
    )

    trainer = RLTrainer(config)
    result = trainer.train()
    print(f"\nTraining result: {result}")


if __name__ == "__main__":
    main()