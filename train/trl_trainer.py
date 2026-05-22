"""TRL GRPO Trainer — Group Relative Policy Optimization for RTS-AI-Platform.

Adapts TRL's GRPO algorithm for discrete-action Gymnasium environments.
TRL's native GRPOTrainer is designed for LLM fine-tuning with text generation,
which is incompatible with traditional RL discrete action spaces. This module
implements GRPO's core algorithm (group-relative advantage estimation + PPO-style
clipped objective) while keeping SimCoreGym as the environment interface.

Architecture:
  1. Collect rollouts from SimCoreGym (Discrete action space)
  2. Group episodes into groups of `group_size` for advantage estimation
  3. Compute group-relative advantages: (reward - mean) / (std + eps)
  4. Update PyTorch policy via PPO-style clipped objective
  5. Export training curves as CSV

Key difference from RLTrainer (PPO):
  - PPO uses GAE (Generalized Advantage Estimation) with temporal-difference
  - GRPO uses group-relative advantages: compare whole-episode returns against
    a group of episodes sampled from similar states
  - GRPO is better for sparse-reward environments like RTS (win/loss)

Usage:
    from train.trl_trainer import TRLGRPOTrainer, TRLGRPOConfig

    config = TRLGRPOConfig(episodes=100, group_size=4)
    trainer = TRLGRPOTrainer(config)
    result = trainer.train()
"""
from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

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

try:
    import trl

    HAS_TRL = True
except ImportError:
    HAS_TRL = False
    trl = None  # type: ignore[assignment]

from train.grpo_trainer import GRPOConfig, RolloutBuffer, SimplePolicy, Transition
from train.rl_trainer import HAS_TORCH as _RL_HAS_TORCH

logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────


@dataclass
class TRLGRPOConfig:
    """TRL GRPO training hyperparameters.

    Extends the base GRPOConfig with TRL-specific fields and provides
    a bridge between TRL's configuration concepts and our Gym env.
    """

    # Environment
    env_id: str = "rts-ai-v0"
    seed: int = 42
    max_ticks: int = 5000
    reward_shaping: str = "shaped"

    # Training
    episodes: int = 100
    batch_size: int = 32
    group_size: int = 4  # episodes per group for advantage estimation
    learning_rate: float = 3e-4
    gamma: float = 0.99
    clip_eps: float = 0.2  # PPO-style clipping epsilon
    entropy_coeff: float = 0.01
    value_coeff: float = 0.5
    max_grad_norm: float = 0.5
    ppo_epochs: int = 4  # number of PPO update epochs per batch

    # Network
    hidden_dim: int = 128

    # Logging
    log_interval: int = 10
    save_interval: int = 100
    output_dir: str = "train/output"
    export_curves: bool = True  # export loss/reward CSV

    # TRL integration
    use_trl: bool = True  # attempt TRL integration
    trl_version: str = ""  # filled at runtime

    # Worker integration
    use_worker: bool = False  # use RolloutWorker for concurrent collection

    # SimCore feature flags (OpenBW-inspired)
    enable_state_hash: bool = False
    enable_order_queue: bool = False
    enable_event_log: bool = False
    enable_replay_v2: bool = False

    def __post_init__(self) -> None:
        if HAS_TRL:
            self.trl_version = trl.__version__  # type: ignore[union-attr]


# ─── GRPO Policy Network (PyTorch) ─────────────────────────


if HAS_TORCH:

    class GRPOPolicy(nn.Module):  # type: ignore[no-redef]
        """PyTorch policy network for GRPO training.

        Similar to RTSPolicy but optimized for group-relative advantages:
          - Shared backbone: obs_flat → Linear(obs_dim, hidden) → ReLU
                                       → Linear(hidden, 64) → ReLU
          - Policy head:   Linear(64, action_dim)  → softmax → Categorical
          - Value head:    Linear(64, 1)            → scalar value
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

        def forward(
            self, obs: torch.Tensor
        ) -> tuple[torch.Tensor, torch.Tensor]:
            """Forward pass: return (logits, value)."""
            features = self.backbone(obs)
            logits = self.policy_head(features)
            value = self.value_head(features).squeeze(-1)
            return logits, value

        def act(
            self, obs: dict[str, np.ndarray]
        ) -> tuple[int, float, float]:
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

        def update_grpo(
            self,
            buffer: RolloutBuffer,
            advantages: np.ndarray,
            config: TRLGRPOConfig,
        ) -> dict[str, float]:
            """GRPO update step: PPO-style clipped objective with group-relative advantages.

            The group-relative advantage formula (from TRL's GRPO):
                advantage_i = (reward_i - mean(group_rewards)) / (std(group_rewards) + eps)

            This is already computed in `advantages` parameter. Here we apply
            the PPO clipped objective using these advantages.

            Returns metrics dict with pg_loss, value_loss, entropy, total_loss.
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

            # Normalise advantages (standard practice for stability)
            advantages_t = (advantages_t - advantages_t.mean()) / (
                advantages_t.std() + 1e-8
            )

            total_pg_loss = 0.0
            total_v_loss = 0.0
            total_entropy = 0.0
            n_updates = 0

            for _epoch in range(config.ppo_epochs):
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
                            ratio,
                            1.0 - config.clip_eps,
                            1.0 + config.clip_eps,
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
            total_loss = (
                avg_pg
                + config.value_coeff * avg_vl
                - config.entropy_coeff * avg_ent
            )

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

        def _flatten_obs(
            self, obs: dict[str, np.ndarray]
        ) -> torch.Tensor:
            """Flatten observation dict into a batch-1 tensor."""
            flat = self._flatten_obs_np(obs)
            return torch.from_numpy(flat).unsqueeze(0)


# ─── TRL GRPO Trainer ──────────────────────────────────────


class TRLGRPOTrainer:
    """GRPO trainer for discrete-action Gym environments using TRL-inspired algorithms.

    When TRL is available, uses the group-relative advantage formula from TRL's
    GRPOTrainer (adapted for discrete action spaces). Falls back to numpy-only
    SimplePolicy when TRL or PyTorch is unavailable.

    The key algorithmic insight from TRL's GRPO:
      - Group episodes by similar starting states
      - Compute advantage = (reward - mean(group)) / (std(group) + eps)
      - Use PPO-style clipped objective for stable updates
    """

    def __init__(
        self,
        config: TRLGRPOConfig | None = None,
        env_factory: Callable[[], Any] | None = None,
        policy: Any | None = None,
    ) -> None:
        self.config = config or TRLGRPOConfig()
        self.buffer = RolloutBuffer(group_size=self.config.group_size)
        self.metrics: list[dict[str, Any]] = []
        self.env_factory = env_factory or self._default_env_factory
        self._external_policy = policy
        self._policy: Any | None = None

    # ─── Public API ───────────────────────────────────────────

    def train(self) -> dict[str, Any]:
        """Run full GRPO training loop.

        Returns summary dict with total_time and episodes.
        """
        import gymnasium as gym

        import simcore.gym_env  # noqa: F401 — register env

        cfg = self.config
        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create environment and policy
        env = gym.make(
            cfg.env_id,
            seed=cfg.seed,
            max_ticks=cfg.max_ticks,
            reward_shaping=cfg.reward_shaping,
            enable_state_hash=cfg.enable_state_hash,
            enable_order_queue=cfg.enable_order_queue,
            enable_event_log=cfg.enable_event_log,
            enable_replay_v2=cfg.enable_replay_v2,
        )
        policy = self._ensure_policy(env)

        logger.info(
            "Starting TRL-GRPO training: %d episodes | policy=%s | "
            "trl=%s | torch=%s",
            cfg.episodes,
            type(policy).__name__,
            HAS_TRL,
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

            # --- Compute group-relative advantages and update ---
            if len(self.buffer) >= cfg.group_size:
                advantages = self._compute_grpo_advantages()
                update_metrics = self._update_policy(advantages)
            else:
                # Not enough data for group estimation; use simple advantage
                rewards = np.array([t.reward for t in self.buffer])
                advantages = rewards - np.mean(rewards)
                update_metrics = self._update_policy(advantages)

            # --- Log metrics ---
            metric: dict[str, Any] = {
                "episode": episode,
                "reward": episode_reward,
                "length": episode_length,
                "winner": info.get("winner", 0),
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
                loss_val = recent[-1].get(
                    "total_loss", recent[-1].get("loss", 0.0)
                )
                logger.info(
                    "Ep %d | reward=%.2f | len=%.0f | win=%.1f%% | loss=%.4f",
                    episode,
                    avg_reward,
                    avg_length,
                    win_rate * 100,
                    loss_val,
                )

            if episode % cfg.save_interval == 0 and episode > 0:
                if HAS_TORCH and isinstance(self._policy, nn.Module):  # type: ignore[name-defined]
                    policy.save_checkpoint(output_dir / f"checkpoint_{episode}.pt")

            self.buffer.clear()

        # --- Final save ---
        if HAS_TORCH and isinstance(self._policy, nn.Module):  # type: ignore[name-defined]
            policy.save_checkpoint(output_dir / "final_model.pt")

        # Export training curves
        if cfg.export_curves:
            self._export_curves(output_dir / "training_curves.csv")

        env.close()

        total_time = time.time() - start_time
        logger.info(
            "Training complete: %.1fs, %d episodes", total_time, cfg.episodes
        )
        return {"total_time": total_time, "episodes": cfg.episodes}

    def compute_advantages(self) -> np.ndarray:
        """Compute group-relative GRPO advantages.

        Public API for external callers who want to compute advantages
        without running the full training loop.
        """
        return self._compute_grpo_advantages()

    # ─── Worker-based training ──────────────────────────────────

    def train_with_worker(
        self,
        worker: Any | None = None,
        *,
        num_workers: int = 4,
    ) -> dict[str, Any]:
        """Train using RolloutWorker for concurrent episode collection.

        This replaces the sequential env.step() loop in :meth:`train` with
        concurrent episode collection via :class:`~train.rollout_worker.RolloutWorker`.
        The policy update logic (GRPO advantages + PPO-style clipped objective)
        remains identical.

        Parameters
        ----------
        worker : RolloutWorker | None
            Pre-configured worker.  When *None* a worker is created
            automatically with ``num_workers`` concurrent collectors and
            ``policy_type="grpo"``.
        num_workers : int
            Concurrency level when creating a default worker.

        Returns
        -------
        dict[str, Any]
            Summary with ``total_time``, ``episodes``, ``games_per_hour``.
        """
        from train.rollout_worker import RolloutWorker

        cfg = self.config
        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create worker if not provided
        if worker is None:
            worker = RolloutWorker(
                num_workers=num_workers,
                policy_type="grpo",
                max_steps=cfg.max_ticks,
            )

        # We need a policy for updates — lazily create via env
        env = self.env_factory()
        policy = self._ensure_policy(env)
        env.close()

        # If the worker lazily creates its own GRPOPolicy, warm it up
        # so both the trainer and worker share the same env dimensions.
        worker._ensure_grpo_policy()

        logger.info(
            "Starting TRL-GRPO training with RolloutWorker: %d episodes | "
            "workers=%d | policy=%s",
            cfg.episodes, worker.num_workers, type(policy).__name__,
        )
        start_time = time.time()

        episodes_per_batch = cfg.group_size
        total_episodes = 0

        for episode in range(0, cfg.episodes, episodes_per_batch):
            n_collect = min(episodes_per_batch, cfg.episodes - episode)

            # --- Concurrent episode collection ---
            episode_batches = worker.run(
                n_episodes=n_collect,
                base_seed=cfg.seed + episode,
            )

            # --- Process collected transitions into buffer ---
            episode_rewards: list[float] = []
            episode_lengths: list[int] = []
            last_info: dict[str, Any] = {}

            for ep_transitions in episode_batches:
                ep_reward = 0.0
                ep_len = 0
                for t in ep_transitions:
                    # Reconstruct log_prob and value from the current policy
                    log_prob = 0.0
                    value = 0.0
                    if HAS_TORCH and isinstance(policy, nn.Module):  # type: ignore[name-defined]
                        action, log_prob, value = policy.act(t.obs)
                    self.buffer.add(
                        Transition(
                            obs=t.obs,
                            action=t.action,
                            reward=t.reward,
                            next_obs=t.next_obs,
                            terminated=t.terminated,
                            truncated=t.truncated,
                            info=t.info,
                            log_prob=log_prob,
                            value=value,
                        )
                    )
                    ep_reward += t.reward
                    ep_len += 1
                episode_rewards.append(ep_reward)
                episode_lengths.append(ep_len)
                if ep_transitions:
                    last_info = ep_transitions[-1].info
                total_episodes += 1

            # --- Compute advantages and update policy ---
            if len(self.buffer) >= cfg.group_size:
                advantages = self._compute_grpo_advantages()
                update_metrics = self._update_policy(advantages)
            else:
                rewards_arr = np.array([t.reward for t in self.buffer])
                advantages = rewards_arr - np.mean(rewards_arr)
                update_metrics = self._update_policy(advantages)

            # --- Log metrics ---
            avg_reward = float(np.mean(episode_rewards)) if episode_rewards else 0.0
            avg_length = float(np.mean(episode_lengths)) if episode_lengths else 0.0
            win_rate = float(np.mean(
                [1 if last_info.get("winner") == 1 else 0]
            )) if last_info else 0.0

            metric: dict[str, Any] = {
                "episode": episode,
                "reward": avg_reward,
                "length": avg_length,
                "winner": last_info.get("winner", 0),
                **update_metrics,
            }
            self.metrics.append(metric)

            if episode % cfg.log_interval == 0 and self.metrics:
                loss_val = metric.get("total_loss", metric.get("loss", 0.0))
                logger.info(
                    "Ep %d | reward=%.2f | len=%.0f | win=%.1f%% | loss=%.4f",
                    episode, avg_reward, avg_length, win_rate * 100, loss_val,
                )

            if episode % cfg.save_interval == 0 and episode > 0:
                if HAS_TORCH and isinstance(self._policy, nn.Module):  # type: ignore[name-defined]
                    policy.save_checkpoint(output_dir / f"checkpoint_{episode}.pt")

            self.buffer.clear()

        # --- Final save ---
        if HAS_TORCH and isinstance(self._policy, nn.Module):  # type: ignore[name-defined]
            policy.save_checkpoint(output_dir / "final_model.pt")

        if cfg.export_curves:
            self._export_curves(output_dir / "training_curves.csv")

        total_time = time.time() - start_time
        gph = worker.games_per_hour
        logger.info(
            "Worker training complete: %.1fs, %d episodes, %.0f games/hr",
            total_time, total_episodes, gph,
        )
        return {
            "total_time": total_time,
            "episodes": total_episodes,
            "games_per_hour": gph,
        }

    # ─── League + Promotion integration ─────────────────────────

    def train_and_promote(
        self,
        *,
        league: Any | None = None,
        promotion_config: Any | None = None,
        version_name: str = "",
        n_rounds: int = 5,
    ) -> dict[str, Any]:
        """Train, register with League, then evaluate via PromotionGate.

        This is the full closed-loop:

        1. **Train** a new policy version (using :meth:`train` or
           :meth:`train_with_worker` depending on ``config.use_worker``).
        2. **Register** the resulting version with the League.
        3. **Evaluate** the new version against the current champion using
           :class:`~harness.promotion.PromotionGate`.  When the gate
           passes the new version is promoted; otherwise it is rolled back.

        Parameters
        ----------
        league : League | None
            Existing league.  A fresh one is created when *None*.
        promotion_config : PromotionConfig | None
            Config for the gate.  Defaults are used when *None*.
        version_name : str
            Name for the new AgentVersion.  Auto-generated when empty.
        n_rounds : int
            Number of self-play training rounds.

        Returns
        -------
        dict[str, Any]
            Summary with training metrics, promotion result, and league
            state.
        """
        from harness.league import AgentVersion, AgentType, League as _League
        from harness.promotion import PromotionGate, PromotionConfig as _PConfig

        cfg = self.config

        # ── 1. Train ──────────────────────────────────────────────
        if cfg.use_worker:
            train_result = self.train_with_worker()
        else:
            train_result = self.train()

        # ── 2. Register with League ───────────────────────────────
        if league is None:
            league = _League()

        if not version_name:
            version_name = f"grpo-v{len(league.pool)}"

        new_version = AgentVersion(
            name=version_name,
            type=AgentType.GRPO,
            checkpoint_path=str(Path(cfg.output_dir) / "final_model.pt"),
            creation_tick=int(time.time()),
            metadata={
                "episodes": cfg.episodes,
                "group_size": cfg.group_size,
                "learning_rate": cfg.learning_rate,
            },
        )
        league.register(new_version)

        # Find champion (latest non-GRPO version, or the best by ELO)
        champion_name: str | None = None
        for v in league.pool.get_all_versions():
            if v.name != version_name:
                champion_name = v.name
                break

        # If no champion exists, the new version is promoted by default
        if champion_name is None:
            return {
                **train_result,
                "version": version_name,
                "promoted": True,
                "reason": "No champion exists — auto-promoted",
                "league_summary": league.summary(),
            }

        # ── 3. Evaluate with PromotionGate ────────────────────────
        if promotion_config is None:
            promotion_config = _PConfig(
                min_games=20,       # reduced for test speed
                win_threshold=0.50, # >50% to promote
                confidence=0.90,
                max_ticks=cfg.max_ticks,
            )

        gate = PromotionGate(config=promotion_config, league=league)
        result = gate.evaluate_sync(
            challenger=version_name,
            champion=champion_name,
            challenger_agent_type="grpo",
            champion_agent_type="script",
        )

        if result.promoted:
            gate.promote(result)
        else:
            gate.rollback(result)

        return {
            **train_result,
            "version": version_name,
            "promoted": result.promoted,
            "win_rate": result.win_rate,
            "ci_lower": result.ci_lower,
            "ci_upper": result.ci_upper,
            "games_played": result.games_played,
            "reason": result.reason,
            "league_summary": league.summary(),
        }

    # ─── Internals ────────────────────────────────────────────

    def _compute_grpo_advantages(self) -> np.ndarray:
        """Compute GRPO group-relative advantages.

        This implements TRL's core GRPO advantage formula:
            advantage_i = (reward_i - mean(group_rewards)) / (std(group_rewards) + eps)

        For Gym environments, we group consecutive episodes (each representing
        a complete trajectory) and compare their episode returns.
        """
        if not self.buffer.transitions:
            return np.array([])

        rewards = np.array([t.reward for t in self.buffer])
        advantages = np.zeros_like(rewards)
        group_size = self.config.group_size
        eps = 1e-8

        n = len(rewards)
        for start in range(0, n, group_size):
            end = min(start + group_size, n)
            group_rewards = rewards[start:end]
            group_mean = np.mean(group_rewards)
            group_std = np.std(group_rewards) + eps
            advantages[start:end] = (group_rewards - group_mean) / group_std

        return advantages.astype(np.float32)

    def _update_policy(self, advantages: np.ndarray) -> dict[str, float]:
        """Update policy with computed advantages."""
        policy = self._policy
        if policy is None:
            return {"loss": 0.0}

        if HAS_TORCH and isinstance(policy, nn.Module):  # type: ignore[name-defined]
            return policy.update_grpo(self.buffer, advantages, self.config)
        else:
            # Fallback: SimplePolicy gradient update
            actions = np.array([t.action for t in self.buffer])
            loss = policy.update(actions, advantages)
            return {"loss": float(loss)}

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
            self._policy = GRPOPolicy(
                obs_dim=obs_dim,
                action_dim=action_dim,
                hidden_dim=cfg.hidden_dim,
                lr=cfg.learning_rate,
            )
            logger.info(
                "Created GRPOPolicy: obs_dim=%d, action_dim=%d, hidden=%d",
                obs_dim,
                action_dim,
                cfg.hidden_dim,
            )
        else:
            self._policy = SimplePolicy(
                n_actions=action_dim, lr=cfg.learning_rate
            )
            logger.info(
                "PyTorch unavailable — using SimplePolicy (numpy-only, limited GRPO)"
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

    def _default_env_factory(self) -> Any:
        """Default environment factory: creates rts-ai-v0 with config flags."""
        import gymnasium as gym

        import simcore.gym_env  # noqa: F401

        cfg = self.config
        return gym.make(
            cfg.env_id,
            seed=cfg.seed,
            max_ticks=cfg.max_ticks,
            reward_shaping=cfg.reward_shaping,
            enable_state_hash=cfg.enable_state_hash,
            enable_order_queue=cfg.enable_order_queue,
            enable_event_log=cfg.enable_event_log,
            enable_replay_v2=cfg.enable_replay_v2,
        )

    def _export_curves(self, path: Path) -> None:
        """Export training curves as CSV with loss and reward columns."""
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "episode",
            "reward",
            "length",
            "winner",
        ]
        # Add loss columns if available
        if self.metrics:
            for key in ("total_loss", "loss", "pg_loss", "value_loss", "entropy"):
                if key in self.metrics[0]:
                    fieldnames.append(key)

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for m in self.metrics:
                writer.writerow(m)

        logger.info("Training curves exported to %s", path)


# ─── CLI ────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for TRL GRPO training."""
    import argparse

    parser = argparse.ArgumentParser(description="TRL-GRPO Trainer for RTS AI")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--group-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--reward-shaping", default="shaped")
    parser.add_argument("--output-dir", default="train/output")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = TRLGRPOConfig(
        episodes=args.episodes,
        batch_size=args.batch_size,
        group_size=args.group_size,
        learning_rate=args.lr,
        reward_shaping=args.reward_shaping,
        output_dir=args.output_dir,
    )

    trainer = TRLGRPOTrainer(config)
    result = trainer.train()
    print(f"\nTraining result: {result}")


if __name__ == "__main__":
    main()