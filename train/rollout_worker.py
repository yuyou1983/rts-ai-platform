"""Rollout Worker — Async rollout collector for RTS-AI-Platform.

Collects episode transitions concurrently using asyncio for I/O
coordination and multiprocessing for CPU-bound environment simulation.

Architecture:
  - RolloutWorker manages a pool of worker processes, each running a
    Gymnasium environment instance produced by the user-supplied factory.
  - asyncio gathers episode results concurrently (collect_batch).
  - A callable policy (obs -> action) drives action selection; can be
    SimplePolicy (numpy-only) or any PyTorch policy via duck typing.
  - Progress is reported after each completed episode.

Usage:
    from train.rollout_worker import RolloutWorker

    def make_env():
        import gymnasium as gym
        import simcore.gym_env  # noqa: F401
        return gym.make("rts-ai-v0")

    worker = RolloutWorker(num_workers=4, env_factory=make_env, policy=my_policy)
    episodes = worker.run(n_episodes=16)

Integration with RLTrainer:
    trainer = RLTrainer(...)
    episodes = worker.run(n_episodes=trainer.config.batch_size)
    trainer.learn(episodes)
"""
from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import pickle
import time
from typing import Any, Callable, TYPE_CHECKING

import numpy as np
from train.grpo_trainer import Transition

try:
    from train.trl_trainer import GRPOPolicy as _GRPOPolicy, HAS_TORCH as _HAS_TORCH
except ImportError:
    _GRPOPolicy = None  # type: ignore[assignment,misc]
    _HAS_TORCH = False

if TYPE_CHECKING:
    from train.shared_buffer import SharedRolloutBuffer

logger = logging.getLogger(__name__)

# Type aliases
ObsType = dict[str, Any]
PolicyCallable = Callable[[ObsType], int]  # obs -> action


# ─── Worker process entry point ────────────────────────────


def _worker_episode(
    env_factory_bytes: bytes,
    policy_bytes: bytes,
    max_steps: int,
    seed: int,
    worker_id: int,
) -> list[Transition]:
    """Run a single episode inside a child process.

    Parameters
    ----------
    env_factory_bytes : bytes
        Pickled callable that returns a Gymnasium env.
    policy_bytes : bytes
        Pickled callable policy (obs -> action).
    max_steps : int
        Maximum number of steps per episode.
    seed : int
        Random seed for env.reset().
    worker_id : int
        Identifier of the worker (for logging).

    Returns
    -------
    list[Transition]
        Collected transitions for the episode.
    """
    env_factory: Callable[[], Any] = pickle.loads(env_factory_bytes)
    policy: PolicyCallable = pickle.loads(policy_bytes)

    env = env_factory()
    obs, info = env.reset(seed=seed)
    transitions: list[Transition] = []

    for step in range(max_steps):
        action = policy(obs)
        next_obs, reward, terminated, truncated, info = env.step(action)

        transitions.append(Transition(
            obs=obs,
            action=action,
            reward=reward,
            next_obs=next_obs,
            terminated=terminated,
            truncated=truncated,
            info=info,
        ))

        obs = next_obs
        if terminated or truncated:
            break

    env.close()
    return transitions


async def _run_episode_in_process(
    env_factory_bytes: bytes,
    policy_bytes: bytes,
    max_steps: int,
    seed: int,
    worker_id: int,
    loop: asyncio.AbstractEventLoop,
) -> list[Transition]:
    """Offload a single-episode collection to a child process.

    Uses ``loop.run_in_executor`` so that the blocking
    ``_worker_episode`` call does not stall the event loop.
    """
    result = await loop.run_in_executor(
        None,
        _worker_episode,
        env_factory_bytes,
        policy_bytes,
        max_steps,
        seed,
        worker_id,
    )
    return result


# ─── RolloutWorker ──────────────────────────────────────────


def _lazy_grpo_policy(obs: ObsType) -> int:
    """Sentinel callable — replaced after lazy GRPOPolicy init."""
    raise RuntimeError("GRPOPolicy not yet initialised; call _ensure_grpo_policy first.")


class _GRPOPolicyWrapper:
    """Picklable adapter: GRPOPolicy.act -> simple (obs) -> int callable.

    GRPOPolicy.act returns (action, log_prob, value); the worker process
    expects (obs) -> int.  This wrapper discards the extras.
    """

    def __init__(self, policy: Any) -> None:
        self._policy = policy

    def __call__(self, obs: ObsType) -> int:
        action, _log_prob, _value = self._policy.act(obs)
        return int(action)

    def __reduce__(self):
        # Make it picklable by saving the underlying policy
        return (self.__class__, (self._policy,))


class RolloutWorker:
    """Async rollout collector with concurrent multi-episode gathering.

    Parameters
    ----------
    num_workers : int
        Maximum number of concurrent worker processes / episodes.
    env_factory : Callable[[], gymnasium.Env]
        A callable that creates and returns a fresh Gymnasium env.
        Called once per episode inside a child process.
    policy : Callable[[ObsType], int]
        A callable that maps an observation dict to a discrete action int.
        Must be picklable (lambda/closure over non-picklable objects will fail).
    max_steps : int
        Step limit per episode (prevents infinite loops in broken envs).
    shared_buffer : SharedRolloutBuffer | None
        If provided, collected transitions are added to this shared buffer
        instead of being returned directly. Useful for concurrent collection
        feeding into TRLGRPOTrainer.
    policy_type : str
        "simple" (default) uses SimplePolicy/numpy; "grpo" lazily creates
        a GRPOPolicy (requires PyTorch).
    """

    def __init__(
        self,
        num_workers: int = 4,
        env_factory: Callable[[], Any] | None = None,
        policy: PolicyCallable | None = None,
        max_steps: int = 5000,
        shared_buffer: SharedRolloutBuffer | None = None,
        policy_type: str = "simple",
    ) -> None:
        self.num_workers = num_workers
        self.env_factory = env_factory or _default_env_factory
        self.max_steps = max_steps
        self.shared_buffer = shared_buffer
        self.policy_type = policy_type

        # Lazy GRPO policy init (needs obs_dim / action_dim from env)
        self._grpo_policy: Any | None = None

        if policy is not None:
            self.policy = policy
        elif policy_type == "grpo" and _HAS_TORCH and _GRPOPolicy is not None:
            # Will be lazily created on first use once env is available
            self.policy = _lazy_grpo_policy  # type: ignore[assignment]
        else:
            self.policy = policy or _default_policy

        # Pre-pickle factory & policy once (child processes receive bytes)
        if self.policy is not _lazy_grpo_policy:
            self._policy_bytes = pickle.dumps(self.policy)
        else:
            self._policy_bytes = b""  # placeholder, set after lazy init

        self._env_factory_bytes = pickle.dumps(self.env_factory)

        # Accumulated stats
        self._episodes_completed = 0
        self._total_steps = 0

        # Throughput tracking
        self._episode_times: list[float] = []

    # ── Public API ──────────────────────────────────────────

    async def collect_episode(self, seed: int | None = None) -> list[Transition]:
        """Collect a single episode asynchronously.

        Parameters
        ----------
        seed : int | None
            Seed passed to ``env.reset()``.  When *None*, a unique seed
            derived from ``time.monotonic_ns()`` is used.

        Returns
        -------
        list[Transition]
        """
        if seed is None:
            seed = int(time.monotonic_ns()) % (2**31)

        self._ensure_grpo_policy()

        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        transitions = await _run_episode_in_process(
            env_factory_bytes=self._env_factory_bytes,
            policy_bytes=self._policy_bytes,
            max_steps=self.max_steps,
            seed=seed,
            worker_id=0,
            loop=loop,
        )
        elapsed = time.perf_counter() - t0
        self._episode_times.append(elapsed)

        self._episodes_completed += 1
        self._total_steps += len(transitions)
        self._log_progress(episode_num=self._episodes_completed, steps=len(transitions))

        if self.shared_buffer is not None:
            self.shared_buffer.add_batch(transitions)

        return transitions

    async def collect_batch(
        self,
        n_episodes: int,
        base_seed: int = 0,
    ) -> list[list[Transition]]:
        """Collect *n_episodes* concurrently.

        At most ``num_workers`` episodes run in parallel; the rest are
        scheduled as slots free up (first-come-first-served).

        Parameters
        ----------
        n_episodes : int
            Number of episodes to collect.
        base_seed : int
            Seeds are ``base_seed + i`` for episode *i*, ensuring
            reproducibility across runs.

        Returns
        -------
        list[list[Transition]]
            One list of Transitions per episode, in episode-index order.
        """
        self._ensure_grpo_policy()

        loop = asyncio.get_running_loop()
        semaphore = asyncio.Semaphore(self.num_workers)
        results: dict[int, list[Transition]] = {}
        completed_count = 0

        async def _guarded_collect(episode_idx: int) -> None:
            nonlocal completed_count
            async with semaphore:
                t0 = time.perf_counter()
                transitions = await _run_episode_in_process(
                    env_factory_bytes=self._env_factory_bytes,
                    policy_bytes=self._policy_bytes,
                    max_steps=self.max_steps,
                    seed=base_seed + episode_idx,
                    worker_id=episode_idx,
                    loop=loop,
                )
                elapsed = time.perf_counter() - t0
                self._episode_times.append(elapsed)

                results[episode_idx] = transitions
                completed_count += 1
                self._episodes_completed += 1
                self._total_steps += len(transitions)
                self._log_progress(
                    episode_num=completed_count,
                    steps=len(transitions),
                    total=n_episodes,
                )

                if self.shared_buffer is not None:
                    self.shared_buffer.add_batch(transitions)

        tasks = [asyncio.create_task(_guarded_collect(i)) for i in range(n_episodes)]
        await asyncio.gather(*tasks)

        # Return in deterministic order
        return [results[i] for i in range(n_episodes)]

    def run(self, n_episodes: int, base_seed: int = 0) -> list[list[Transition]]:
        """Synchronous entry point — runs ``collect_batch`` via ``asyncio.run``.

        This is the primary interface for RLTrainer integration::

            worker = RolloutWorker(num_workers=8, env_factory=make_env, policy=pi)
            episodes = worker.run(n_episodes=32)

        Parameters
        ----------
        n_episodes : int
            Number of episodes to collect.
        base_seed : int
            Base random seed for reproducibility.

        Returns
        -------
        list[list[Transition]]
        """
        # Reset per-run stats
        self._episodes_completed = 0
        self._total_steps = 0
        self._episode_times.clear()
        return asyncio.run(self.collect_batch(n_episodes, base_seed))

    # ── Throughput ──────────────────────────────────────────

    @property
    def games_per_hour(self) -> float:
        """Estimated games per hour based on recent episode timings."""
        if not self._episode_times:
            return 0.0
        avg_seconds = sum(self._episode_times) / len(self._episode_times)
        if avg_seconds <= 0:
            return 0.0
        return 3600.0 / avg_seconds

    # ── Lazy GRPO policy init ───────────────────────────────

    def _ensure_grpo_policy(self) -> None:
        """Lazily initialise GRPOPolicy when policy_type='grpo'."""
        if self.policy_type != "grpo" or self._grpo_policy is not None:
            return
        if not _HAS_TORCH or _GRPOPolicy is None:
            raise RuntimeError(
                "Cannot create GRPOPolicy: PyTorch not available. "
                "Install torch or use policy_type='simple'."
            )

        env = self.env_factory()
        action_dim = env.action_space.n
        obs_dim = 0
        obs_space = env.observation_space
        # Use .spaces dict to be compatible with both real and mock obs spaces
        spaces = obs_space.spaces if hasattr(obs_space, "spaces") else {}
        for key in ("entities", "resources", "tick"):
            if key in spaces:
                shape = spaces[key].shape
                dim = 1
                for s in shape:
                    dim *= s
                obs_dim += dim
        env.close()

        self._grpo_policy = _GRPOPolicy(
            obs_dim=obs_dim,
            action_dim=action_dim,
        )
        wrapped = _GRPOPolicyWrapper(self._grpo_policy)
        self.policy = wrapped  # type: ignore[assignment]
        self._policy_bytes = pickle.dumps(wrapped)

    # ── Progress reporting ──────────────────────────────────

    def _log_progress(
        self,
        episode_num: int,
        steps: int,
        total: int | None = None,
    ) -> None:
        """Print progress after each completed episode."""
        total_str = f"/{total}" if total is not None else ""
        logger.info(
            "Episode %d%s completed | steps=%d | total_steps=%d",
            episode_num,
            total_str,
            steps,
            self._total_steps,
        )


# ─── Default factory / policy (for testing / prototyping) ──


def _default_env_factory() -> Any:
    """Create a default RTS Gymnasium env (lazy import)."""
    import gymnasium as gym

    import simcore.gym_env  # noqa: F401 — registers the env

    return gym.make("rts-ai-v0")


def _default_policy(obs: ObsType) -> int:
    """Random policy fallback — uniform over 6 RTS command types."""
    import numpy as np

    return int(np.random.randint(0, 6))


# ─── CLI ────────────────────────────────────────────────────


def main() -> None:
    """Quick smoke-test: collect a few episodes and print stats."""
    import argparse

    parser = argparse.ArgumentParser(description="Rollout Worker smoke test")
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--n-episodes", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Use multiprocessing "spawn" to avoid fork-safety issues with asyncio
    mp_context = mp.get_context("spawn")
    # Note: we use the default ProcessPoolExecutor via run_in_executor,
    # which respects the mp context set below on some Python versions.
    # For robust production use, pass an explicit executor.

    worker = RolloutWorker(
        num_workers=args.num_workers,
        max_steps=args.max_steps,
    )

    logger.info(
        "Starting rollout collection: %d episodes, %d workers",
        args.n_episodes,
        args.num_workers,
    )
    start = time.perf_counter()
    episodes = worker.run(n_episodes=args.n_episodes, base_seed=args.seed)
    elapsed = time.perf_counter() - start

    total_transitions = sum(len(ep) for ep in episodes)
    avg_len = total_transitions / len(episodes) if episodes else 0
    print(f"\n{'='*50}")
    print(f"Rollout collection complete")
    print(f"  Episodes:       {len(episodes)}")
    print(f"  Transitions:    {total_transitions}")
    print(f"  Avg episode len: {avg_len:.1f}")
    print(f"  Elapsed:         {elapsed:.2f}s")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()