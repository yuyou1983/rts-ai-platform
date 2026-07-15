"""V11 PPO callbacks: entropy scheduling + performance-based LR reduction.

These callbacks address the V10 policy collapse issues:
1. EntropyCoefScheduler: linear decay of ent_coef from 0.1 → 0.01 over 300K steps
   to prevent the policy from becoming deterministic too early.
2. ReduceLROnPlateau: halve learning_rate when ep_rew_mean drops >20% for 3
   consecutive evaluations, preventing destabilising large updates.
"""
from __future__ import annotations

from stable_baselines3.common.callbacks import BaseCallback


class EntropyCoefScheduler(BaseCallback):
    """Linearly decay ``model.ent_coef`` from *start* to *end* over *total_steps*.

    After *total_steps* the coefficient stays at *end* indefinitely.

    Parameters
    ----------
    start : float
        Initial entropy coefficient (default 0.1 for V11).
    end : float
        Final entropy coefficient (default 0.01).
    total_steps : int
        Number of environment steps over which to linearly decay (default 300_000).
    verbose : int
        Verbosity level (0 = silent, 1 = info, 2 = debug).
    """

    def __init__(
        self,
        start: float = 0.1,
        end: float = 0.01,
        total_steps: int = 300_000,
        verbose: int = 0,
    ):
        super().__init__(verbose=verbose)
        self._start = start
        self._end = end
        self._total_steps = total_steps

    def _on_step(self) -> bool:
        progress = min(self.num_timesteps / self._total_steps, 1.0)
        new_coef = self._start + (self._end - self._start) * progress
        self.model.ent_coef = new_coef  # type: ignore[attr-defined]

        # Log every 10K steps so we can inspect the schedule in TensorBoard.
        if self.num_timesteps % 10_000 == 0 and self.verbose >= 1:
            print(
                f"[EntropyCoefScheduler] step={self.num_timesteps:>7d}  "
                f"ent_coef={new_coef:.5f}"
            )
        # Also record to SB3 logger (available every rollout).
        self.logger.record("custom/ent_coef", new_coef)
        return True


class CurriculumStepSync(BaseCallback):
    """Push the current global training step into the env's SubgoalTracker
    so that curriculum reward gating works correctly during PPO training.

    V11: without this, the tracker always thinks step=0 and only Phase-1
    milestones (first_mineral_gathered) fire — the agent never gets rewarded
    for building barracks or training combat units.
    """

    def __init__(self, verbose: int = 0):
        super().__init__(verbose=verbose)

    def _on_step(self) -> bool:
        # Access the underlying HierarchicalRTSEnv through ActionMasker
        env = self.training_env
        # Unwrap through VecEnv gymnastics
        try:
            # SubprocVecEnv / DummyVecEnv: envs is a list
            for e in env.envs:
                inner = e.unwrapped
                # If ActionMasker is in the wrapper stack, dig through it
                while hasattr(inner, 'env'):
                    if hasattr(inner, '_subgoal_tracker'):
                        inner._subgoal_tracker.current_training_step = self.num_timesteps
                        break
                    inner = inner.env
                else:
                    # Direct env
                    if hasattr(inner, '_subgoal_tracker'):
                        inner._subgoal_tracker.current_training_step = self.num_timesteps
        except Exception:
            pass
        return True


class ReduceLROnPlateau(BaseCallback):
    """Halve ``model.learning_rate`` when ep_rew_mean drops >20% for 3
    consecutive evaluations.

    This is a lightweight alternative to KL-based early stopping — instead of
    inspecting internal KL approximations (which SB3 PPO does not expose per
    epoch), we monitor the downstream reward signal. A sustained >20% drop
    is a strong sign that the latest policy update was too aggressive.

    Parameters
    ----------
    patience : int
        Number of consecutive evaluations with >threshold% drop before
        reducing LR (default 3).
    threshold : float
        Minimum fractional drop (0.2 = 20%) in ep_rew_mean to count as
        a "decline" (default 0.2).
    factor : float
        Multiplicative factor to scale LR (default 0.5 = halve).
    min_lr : float
        Floor for learning rate — stop reducing once LR hits this value
        (default 1e-6).
    verbose : int
        Verbosity level.
    """

    def __init__(
        self,
        patience: int = 3,
        threshold: float = 0.2,
        factor: float = 0.5,
        min_lr: float = 1e-6,
        verbose: int = 0,
    ):
        super().__init__(verbose=verbose)
        self._patience = patience
        self._threshold = threshold
        self._factor = factor
        self._min_lr = min_lr

        self._prev_ep_rew_mean: float | None = None
        self._decline_count: int = 0

    def _on_step(self) -> bool:
        # We read ep_rew_mean from the SB3 logger buffer.  It is refreshed
        # every rollout (every n_steps * n_envs steps).  We check every
        # 10K steps so that the check frequency is independent of n_steps.
        if self.num_timesteps % 10_000 != 0:
            return True

        # Try to read the latest ep_rew_mean from logger.
        ep_rew_mean = None
        try:
            # SB3 stores recent values in a dict accessible via _logs.
            # The canonical way is to read from the logger's name-val store.
            if hasattr(self.model, "_logger") and self.model._logger is not None:
                log_dict = self.model._logger.name_to_value
                ep_rew_mean = log_dict.get("rollout/ep_rew_mean")
        except Exception:
            pass

        # Fallback: read from SB3 Callback logger (populated after each rollout).
        if ep_rew_mean is None:
            try:
                ep_rew_mean = self.logger.name_to_value.get("rollout/ep_rew_mean")
            except Exception:
                pass

        if ep_rew_mean is None:
            return True

        if self._prev_ep_rew_mean is not None and self._prev_ep_rew_mean != 0:
            drop_frac = (self._prev_ep_rew_mean - ep_rew_mean) / abs(self._prev_ep_rew_mean)
            if drop_frac > self._threshold:
                self._decline_count += 1
                if self.verbose >= 1:
                    print(
                        f"[ReduceLROnPlateau] ep_rew_mean declined {drop_frac:.1%} "
                        f"({self._prev_ep_rew_mean:.1f} → {ep_rew_mean:.1f})  "
                        f"decline_count={self._decline_count}/{self._patience}"
                    )
            else:
                # Reset counter when performance is stable or improving.
                self._decline_count = 0

        self._prev_ep_rew_mean = ep_rew_mean

        if self._decline_count >= self._patience:
            current_lr = self.model.lr_schedule(self._current_progress_remaining)
            new_lr = max(current_lr * self._factor, self._min_lr)
            if new_lr < current_lr:
                # Patch the LR schedule — SB3 PPO stores a callable lr_schedule
                # and also the optimiser param groups.  We update both.
                self.model.learning_rate = new_lr
                for pg in self.model.optimizer.param_groups:
                    pg["lr"] = new_lr
                self._decline_count = 0  # reset patience after action
                if self.verbose >= 1:
                    print(
                        f"[ReduceLROnPlateau] ⚠  Reducing LR: {current_lr:.2e} → {new_lr:.2e}  "
                        f"(step={self.num_timesteps})"
                    )
                self.logger.record("custom/lr", new_lr)

        return True
