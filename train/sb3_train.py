"""Stable-Baselines3 PPO Baseline Training Script for RTS-AI-Platform.

Uses either:
  - MaskablePPO (sb3-contrib) when action masks are available via ActionMaskRTS wrapper
  - Standard PPO + FlattenRTSObs + NormalizeRTSReward when masks are not needed

Training flow:
  1. Create vectorised env (SubprocVecEnv / DummyVecEnv)
  2. Apply FlattenRTSObs + NormalizeRTSReward wrappers
  3. Optionally apply ActionMaskRTS for MaskablePPO
  4. Create PPO / MaskablePPO with MlpPolicy
  5. Train for 500k steps (~1000 episodes)
  6. Save model + VecNormalize statistics

Usage:
    python -m train.sb3_train
    python -m train.sb3_train --use-maskable --n-envs 4
    python -m train.sb3_train --total-timesteps 500000
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import gymnasium as gym
import numpy as np

logger = logging.getLogger(__name__)

# ─── Optional SB3 imports ────────────────────────────────────

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback, EvalCallback
    from stable_baselines3.common.vec_env import (
        DummyVecEnv,
        SubprocVecEnv,
        VecEnv,
        VecNormalize,
    )
    from stable_baselines3.common.policies import ActorCriticPolicy

    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

try:
    from sb3_contrib import MaskablePPO
    from sb3_contrib.common.wrappers import ActionMasker

    HAS_SB3_CONTRIB = True
except ImportError:
    HAS_SB3_CONTRIB = False

# ─── RTS Wrapper imports ─────────────────────────────────────

try:
    from simcore.wrappers import FlattenRTSObs, NormalizeRTSReward, ActionMaskRTS
except ImportError:
    # Wrappers not yet available — provide minimal fallback stubs
    import gymnasium as _gym

    class FlattenRTSObs(_gym.Wrapper):  # type: ignore[no-redef]
        """Flatten Dict obs into a 1-D Box for SB3 compatibility."""

        def __init__(self, env: _gym.Env) -> None:
            super().__init__(env)
            sample = env.observation_space.sample()
            flat_dim = int(np.prod([v.shape for v in sample.values()])) if isinstance(sample, dict) else int(np.prod(sample.shape))
            self.observation_space = _gym.spaces.Box(
                low=-np.inf, high=np.inf, shape=(flat_dim,), dtype=np.float32
            )

        def observation(self, obs: dict | np.ndarray) -> np.ndarray:
            if isinstance(obs, dict):
                return np.concatenate([np.asarray(v).flatten() for v in obs.values()])
            return np.asarray(obs).flatten()

        def reset(self, **kwargs):  # type: ignore[no-untyped-def]
            obs, info = self.env.reset(**kwargs)
            return self.observation(obs), info

        def step(self, action):  # type: ignore[no-untyped-def]
            obs, reward, terminated, truncated, info = self.env.step(action)
            return self.observation(obs), reward, terminated, truncated, info

    class NormalizeRTSReward(_gym.Wrapper):  # type: ignore[no-redef]
        """Running-mean-std reward normalisation (handled by VecNormalize in practice)."""
        pass

    class ActionMaskRTS(_gym.Wrapper):  # type: ignore[no-redef]
        """Wrapper that exposes action masks via info['action_masks']."""

        def __init__(self, env: _gym.Env) -> None:
            super().__init__(env)

        def reset(self, **kwargs):  # type: ignore[no-untyped-def]
            obs, info = self.env.reset(**kwargs)
            info["action_masks"] = np.ones(self.env.action_space.n, dtype=bool)
            return obs, info

        def step(self, action):  # type: ignore[no-untyped-def]
            obs, reward, terminated, truncated, info = self.env.step(action)
            info["action_masks"] = np.ones(self.env.action_space.n, dtype=bool)
            return obs, reward, terminated, truncated, info


# ─── Episode Counter Callback ───────────────────────────────

class EpisodeCounterCallback(BaseCallback):
    """Counts completed episodes and logs progress."""

    def __init__(self, target_episodes: int = 1000, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.target_episodes = target_episodes
        self.episode_count = 0
        self.episode_returns: list[float] = []

    def _on_step(self) -> bool:
        # Check which envs just finished an episode
        for done_arr in [self.locals.get("dones"), self.locals.get("terminateds")]:
            if done_arr is not None:
                for i, done in enumerate(done_arr):
                    if done:
                        self.episode_count += 1
                        info = self.locals.get("infos", [{}])[i] if self.locals.get("infos") is not None else {}
                        ep_rew = info.get("episode", {}).get("r", 0.0)
                        self.episode_returns.append(ep_rew)

        if self.episode_count % 50 == 0 and self.episode_count > 0:
            mean_ret = float(np.mean(self.episode_returns[-50:]))
            logger.info(
                "Episode %d/%d | mean reward (last 50): %.2f",
                self.episode_count, self.target_episodes, mean_ret,
            )

        return True


# ─── Env Factory ─────────────────────────────────────────────

def make_env(
    seed: int = 0,
    reward_shaping: str = "shaped",
    use_action_mask: bool = False,
) -> callable:
    """Return a callable that creates a wrapped RTS env."""

    def _init() -> gym.Env:
        env = gym.make("rts-ai-v0", seed=seed, reward_shaping=reward_shaping)
        # Flatten dict obs → 1-D Box for SB3 MlpPolicy
        env = FlattenRTSObs(env)
        # Add action mask wrapper if requested
        if use_action_mask:
            env = ActionMaskRTS(env)
        return env

    return _init


# ─── Main Training Loop ─────────────────────────────────────

def train(
    total_timesteps: int = 500_000,
    n_envs: int = 2,
    seed: int = 42,
    reward_shaping: str = "shaped",
    use_maskable: bool = False,
    n_steps: int = 2048,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
    target_episodes: int = 1000,
    output_dir: str = "train/output",
    eval_freq: int = 10_000,
    eval_episodes: int = 10,
) -> None:
    """Run SB3 PPO (or MaskablePPO) training on the RTS environment."""

    if not HAS_SB3:
        logger.error(
            "stable-baselines3 is not installed. "
            "Install with: pip install -e '.[train]'"
        )
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_path = output_path / "sb3_ppo_rts"
    vec_normalize_path = output_path / "sb3_ppo_rts_vecnormalize"

    # ── Create vectorised environments ──
    env_fns = [make_env(seed=seed + i, reward_shaping=reward_shaping,
                         use_action_mask=use_maskable)
               for i in range(n_envs)]

    # Use SubprocVecEnv for parallel rollout if n_envs > 1, else DummyVecEnv
    if n_envs > 1:
        try:
            train_env = SubprocVecEnv(env_fns)
        except Exception:
            logger.warning("SubprocVecEnv failed, falling back to DummyVecEnv")
            train_env = DummyVecEnv(env_fns)
    else:
        train_env = DummyVecEnv(env_fns)

    # Apply VecNormalize for obs + reward normalisation
    train_env = VecNormalize(
        train_env,
        norm_obs=True,
        norm_reward=True,
        clip_obs=10.0,
        clip_reward=10.0,
        gamma=0.99,
        epsilon=1e-8,
    )

    # ── Eval environment (separate, deterministic) ──
    eval_env_fn = make_env(seed=seed + 100, reward_shaping=reward_shaping,
                            use_action_mask=use_maskable)
    eval_env = DummyVecEnv([eval_env_fn])
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=False,
                             clip_obs=10.0, clip_reward=10.0,
                             gamma=0.99, epsilon=1e-8, training=False)

    # ── Create model ──
    if use_maskable:
        if not HAS_SB3_CONTRIB:
            logger.warning(
                "sb3-contrib not installed; falling back to standard PPO. "
                "Install with: pip install sb3-contrib"
            )
            use_maskable = False
        else:
            logger.info("Using MaskablePPO from sb3-contrib")
            model = MaskablePPO(
                "MlpPolicy",
                train_env,
                verbose=1,
                n_steps=n_steps,
                batch_size=batch_size,
                learning_rate=learning_rate,
                seed=seed,
                device="auto",
            )

    if not use_maskable:
        logger.info("Using standard PPO from stable-baselines3")
        model = PPO(
            "MlpPolicy",
            train_env,
            verbose=1,
            n_steps=n_steps,
            batch_size=batch_size,
            learning_rate=learning_rate,
            seed=seed,
            device="auto",
        )

    # ── Callbacks ──
    episode_cb = EpisodeCounterCallback(target_episodes=target_episodes, verbose=1)
    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=str(output_path / "best_model"),
        log_path=str(output_path / "eval_logs"),
        eval_freq=eval_freq,
        n_eval_episodes=eval_episodes,
        deterministic=True,
    )

    # ── Train ──
    logger.info(
        "Starting training: total_timesteps=%d, n_envs=%d, "
        "n_steps=%d, batch_size=%d, lr=%.1e, maskable=%s",
        total_timesteps, n_envs, n_steps, batch_size, learning_rate, use_maskable,
    )

    model.learn(
        total_timesteps=total_timesteps,
        callback=[episode_cb, eval_cb],
        progress_bar=True,
    )

    # ── Save model + VecNormalize stats ──
    model.save(str(model_path))
    train_env.save(str(vec_normalize_path))
    logger.info("Model saved to %s", model_path)
    logger.info("VecNormalize stats saved to %s", vec_normalize_path)

    # ── Training summary ──
    total_episodes = episode_cb.episode_count
    mean_return = float(np.mean(episode_cb.episode_returns)) if episode_cb.episode_returns else 0.0
    summary = {
        "total_timesteps": total_timesteps,
        "total_episodes": total_episodes,
        "mean_episode_return": mean_return,
        "model_path": str(model_path),
        "vec_normalize_path": str(vec_normalize_path),
        "use_maskable": use_maskable,
        "n_envs": n_envs,
    }

    summary_path = output_path / "sb3_training_summary.json"
    import json
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Training summary saved to %s", summary_path)
    logger.info("Episodes completed: %d | Mean return: %.2f", total_episodes, mean_return)

    # ── Cleanup ──
    train_env.close()
    eval_env.close()


# ─── CLI ─────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SB3 PPO baseline training for RTS-AI-Platform"
    )
    parser.add_argument(
        "--total-timesteps", type=int, default=500_000,
        help="Total timesteps for training (default: 500000)",
    )
    parser.add_argument(
        "--n-envs", type=int, default=2,
        help="Number of parallel envs (default: 2)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--reward-shaping", type=str, default="shaped",
        choices=["sparse", "shaped"],
        help="Reward shaping mode (default: shaped)",
    )
    parser.add_argument(
        "--use-maskable", action="store_true",
        help="Use MaskablePPO from sb3-contrib (requires action masks)",
    )
    parser.add_argument(
        "--n-steps", type=int, default=2048,
        help="Rollout buffer steps per env (default: 2048)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=64,
        help="Minibatch size (default: 64)",
    )
    parser.add_argument(
        "--learning-rate", type=float, default=3e-4,
        help="Learning rate (default: 3e-4)",
    )
    parser.add_argument(
        "--target-episodes", type=int, default=1000,
        help="Target episode count for logging (default: 1000)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="train/output",
        help="Directory to save model and stats (default: train/output)",
    )
    parser.add_argument(
        "--eval-freq", type=int, default=10_000,
        help="Evaluate every N steps (default: 10000)",
    )
    parser.add_argument(
        "--eval-episodes", type=int, default=10,
        help="Number of evaluation episodes (default: 10)",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    args = parse_args()
    train(
        total_timesteps=args.total_timesteps,
        n_envs=args.n_envs,
        seed=args.seed,
        reward_shaping=args.reward_shaping,
        use_maskable=args.use_maskable,
        n_steps=args.n_steps,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        target_episodes=args.target_episodes,
        output_dir=args.output_dir,
        eval_freq=args.eval_freq,
        eval_episodes=args.eval_episodes,
    )


if __name__ == "__main__":
    main()
