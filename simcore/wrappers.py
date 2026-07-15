"""Gymnasium Wrapper layer for RTS SimCore environment.

Provides five wrappers:
  1. FlattenRTSObs            — Dict obs → Box(1093,) float32
  2. NormalizeRTSReward       — Running z-score reward normalization (eps=1e-8, clip=10.0, warm-up=100 steps)
  3. ActionMaskRTS            — Invalid-action masking via info["action_mask"]
  4. MultiDiscreteActionMaskRTS — Convenience wrapper for MultiDiscrete per-dim masks
  5. RNDRewardWrapper         — Random Network Distillation intrinsic reward (Burda et al. 2018)

Usage::

    import gymnasium as gym
    import simcore.gym_env          # registers rts-ai-v0
    from simcore.wrappers import FlattenRTSObs, NormalizeRTSReward, ActionMaskRTS

    env = gym.make("rts-ai-v0", seed=42)
    env = FlattenRTSObs(env)
    env = NormalizeRTSReward(env)
    env = ActionMaskRTS(env)                     # discrete mode (default)

    # MultiDiscrete mode
    env = ActionMaskRTS(env, action_mode='multidiscrete')
    # or use convenience wrapper:
    env = MultiDiscreteActionMaskRTS(env)
"""
from __future__ import annotations

import gymnasium as gym
import numpy as np
import torch
import torch.nn as nn
from gymnasium import spaces

# ─── Constants (must stay in sync with simcore.gym_env) ────────────
MAX_ENTITIES = 64
ENTITY_FEATURES = 17
N_RESOURCES = 4
N_TICK = 1
FLAT_DIM = MAX_ENTITIES * ENTITY_FEATURES + N_RESOURCES + N_TICK  # 64*17+4+1 = 1093

COMMAND_TYPES = 6   # move, gather, attack, build, train, noop
ACTION_DIM_EID = 4  # entity selection buckets
N_X = 8             # X position quantisation buckets
N_Y = 4             # Y position quantisation buckets
N_TARGETS = N_X * N_Y  # 32
TOTAL_ACTIONS = COMMAND_TYPES * ACTION_DIM_EID * N_TARGETS  # 768


# ─── 1. FlattenRTSObs ──────────────────────────────────────────────
class FlattenRTSObs(gym.ObservationWrapper):
    """Flatten the Dict observation into a single Box(1093,) float32 vector.

    Original obs layout:
        entities:  Box(64, 17)  → 1088 floats
        resources: Box(4,)     →   4 floats
        tick:      Box(1,)     →   1 float
    Concatenated: 1093 floats total.
    """

    def __init__(self, env: gym.Env) -> None:
        super().__init__(env)
        # Compute flat bounds from the wrapped env's Dict space
        orig = env.observation_space  # Dict
        low = np.concatenate([
            orig["entities"].low.flatten(),
            orig["resources"].low.flatten(),
            orig["tick"].low.flatten(),
        ])
        high = np.concatenate([
            orig["entities"].high.flatten(),
            orig["resources"].high.flatten(),
            orig["tick"].high.flatten(),
        ])
        self.observation_space = spaces.Box(
            low=low, high=high, shape=(FLAT_DIM,), dtype=np.float32,
        )

    def observation(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        flat = np.concatenate([
            obs["entities"].flatten(),
            obs["resources"].flatten(),
            obs["tick"].flatten(),
        ])
        return flat.astype(np.float32)


# ─── 2. NormalizeRTSReward ─────────────────────────────────────────
class NormalizeRTSReward(gym.RewardWrapper):
    """Running z-score normalization of rewards with warm-up and clipping.

    Maintains a Welford online mean/variance estimator and normalises each
    incoming reward as::

        r_norm = clip((r - mean) / sqrt(var + eps), -clip, +clip)

    **Warm-up**: During the first ``100`` steps (``count < 100``) the
    running statistics are still updated internally but the raw reward is
    returned unchanged.  This prevents the unstable early estimates from
    distorting the reward signal — e.g. a large mineral income of 3132
    would otherwise make milestone rewards negligible after normalisation.

    **Clipping**: After normalisation the result is clipped to
    ``[-clip, +clip]`` (default ±10) to prevent extreme outliers from
    destabilising training.

    ``reset()`` does *not* clear the running statistics so that they
    accumulate across episodes (standard practice for reward normalisation
    in RL training loops).  Call ``reset_stats()`` manually (e.g. before
    an eval run) to reset statistics so eval rewards are on the same
    scale as training rewards.
    """

    def __init__(self, env: gym.Env, eps: float = 1e-8, clip: float = 10.0) -> None:
        super().__init__(env)
        self.eps = eps
        self.clip = clip
        self._mean: float = 0.0
        self._var: float = 1.0
        self._count: int = 0

    # -- Reset statistics (manual, for eval) --------------------------
    def reset_stats(self) -> None:
        """Clear running mean/var/count so eval rewards share the training scale.

        Call this before an evaluation run if you want eval rewards
        normalised against training-time statistics, or call it to start
        fresh.  ``reset()`` does *not* call this — statistics accumulate
        across episodes by design.
        """
        self._mean = 0.0
        self._var = 1.0
        self._count = 0

    # -- Welford online update ----------------------------------------
    def _update_stats(self, reward: float) -> None:
        self._count += 1
        delta = reward - self._mean
        self._mean += delta / self._count
        delta2 = reward - self._mean
        self._var += delta * delta2

    @property
    def _std(self) -> float:
        if self._count < 2:
            return 1.0  # not enough data yet; return identity scale
        return float(np.sqrt(self._var / (self._count - 1) + self.eps))

    # -- RewardWrapper hook -------------------------------------------
    def reward(self, reward: float) -> float:
        self._update_stats(reward)
        # Warm-up: return raw reward until we have enough samples
        if self._count < 100:
            return float(reward)
        r_norm = (reward - self._mean) / self._std
        # Clip to prevent extreme values
        return float(np.clip(r_norm, -self.clip, self.clip))


# ─── 3. ActionMaskRTS ──────────────────────────────────────────────
class ActionMaskRTS(gym.Wrapper):
    """Action-masking wrapper for the RTS environment.

    Inspects ``obs["entities"]`` to determine which entity buckets correspond
    to alive units owned by the controlling player(s).  A boolean mask of
    shape ``(768,)`` is placed into ``info["action_mask"]`` so that downstream
    consumers (e.g. sb3-contrib ``MaskablePPO``) can mask invalid actions.

    When ``action_mode='multidiscrete'``, ``info["action_mask"]`` is instead
    a tuple of 4 per-dimension boolean arrays suitable for MultiDiscrete
    action spaces:

        cmd_mask:   shape(6,)  — always all True (6 commands available)
        eid_mask:   shape(4,)  — True for buckets with alive owned entities
        x_mask:     shape(8,)  — always all True
        y_mask:     shape(4,)  — always all True

    In both modes, ``info["action_mask_discrete"]`` contains the flat
    (768,) boolean mask for compatibility with sb3 standard PPO.

    Entity feature index 2 = normalised health (>0 means alive).
    Entity feature index 7 = normalised owner (owner==1 → value ≈ 0.5).

    The mask is True for valid actions and False for invalid ones.
    """

    # Feature indices inside the entity row (after normalisation in gym_env)
    _HEALTH_IDX = 2     # health / max_health  (>0 → alive)
    _OWNER_IDX = 7      # owner / 2.0          (0.5 → player 1)
    _PLAYER1_VALUE = 0.5

    # MultiDiscrete dimension sizes
    _N_CMD = COMMAND_TYPES        # 6
    _N_EID = ACTION_DIM_EID       # 4
    _N_X = N_X                    # 8
    _N_Y = N_Y                    # 4

    def __init__(self, env: gym.Env, action_mode: str = "discrete") -> None:
        super().__init__(env)
        if action_mode not in ("discrete", "multidiscrete"):
            raise ValueError(
                f"action_mode must be 'discrete' or 'multidiscrete', got {action_mode!r}"
            )
        self.action_mode = action_mode
        # Cached mask from most recent step/reset (for MaskablePPO compat)
        self._cached_mask: np.ndarray | None = None

    # ─── MaskablePPO compatibility ──────────────────────────────
    def action_masks(self) -> np.ndarray:
        """Return the (768,) boolean action mask.

        Required by ``sb3_contrib.MaskablePPO`` which calls
        ``env.action_masks()`` before every policy forward pass.
        Always returns the flat discrete mask regardless of action_mode,
        because MaskablePPO only supports Discrete action spaces.
        """
        if self._cached_mask is None:
            # Fallback: compute from current obs if no step yet
            obs = self.env.reset()[0] if not hasattr(self, '_last_obs') else self._last_obs
            self._cached_mask = self._compute_discrete_mask(obs)
        return self._cached_mask

    # ─── reset / step ───────────────────────────────────────────
    def reset(
        self, *, seed: int | None = None, options: dict | None = None,
    ) -> tuple[np.ndarray | dict, dict]:
        obs, info = self.env.reset(seed=seed, options=options)
        discrete_mask = self._compute_discrete_mask(obs)
        self._cached_mask = discrete_mask
        info["action_mask_discrete"] = discrete_mask
        info["action_mask"] = (
            self._compute_multidiscrete_mask(obs)
            if self.action_mode == "multidiscrete"
            else discrete_mask
        )
        return obs, info

    def step(
        self, action: int,
    ) -> tuple[np.ndarray | dict, float, bool, bool, dict]:
        obs, reward, terminated, truncated, info = self.env.step(action)
        discrete_mask = self._compute_discrete_mask(obs)
        self._cached_mask = discrete_mask
        info["action_mask_discrete"] = discrete_mask
        info["action_mask"] = (
            self._compute_multidiscrete_mask(obs)
            if self.action_mode == "multidiscrete"
            else discrete_mask
        )
        return obs, reward, terminated, truncated, info

    # ─── mask computation ──────────────────────────────────────
    def _extract_entity_indices(self, obs: dict | np.ndarray) -> np.ndarray:
        """Extract alive owned entity indices from either dict or flat obs.

        Returns an array of entity bucket indices (0..3) that correspond to
        alive owned entities, based on the first 4 alive owned entities
        found in the entity list.
        """
        if isinstance(obs, dict):
            entities = obs["entities"]
        else:
            entities = obs[:MAX_ENTITIES * ENTITY_FEATURES].reshape(
                MAX_ENTITIES, ENTITY_FEATURES,
            )
        health = entities[:, self._HEALTH_IDX]
        owner = entities[:, self._OWNER_IDX]
        alive_owned = (health > 0.0) & (np.isclose(owner, self._PLAYER1_VALUE, atol=0.05))
        # Return bucket indices: for each alive owned entity found (up to 4),
        # its bucket index is its position in the alive-owned list.
        alive_indices = np.where(alive_owned)[0]
        # The bucket indices are 0, 1, 2, 3 for up to 4 alive owned entities
        return np.arange(min(len(alive_indices), ACTION_DIM_EID))

    def _compute_discrete_mask(self, obs: dict | np.ndarray) -> np.ndarray:
        """Build the full (768,) boolean action mask.

        An action index is decomposed as:
            action = cmd * (ACTION_DIM_EID * N_TARGETS) + eid_bucket * N_TARGETS + target

        Only actions whose ``eid_bucket`` slot corresponds to an alive owned
        entity are marked valid (True).  All others are False.
        """
        valid_buckets = self._extract_entity_indices(obs)

        full_mask = np.zeros(TOTAL_ACTIONS, dtype=np.bool_)
        for eb in valid_buckets:
            start = eb * N_TARGETS
            for cmd in range(COMMAND_TYPES):
                base = cmd * (ACTION_DIM_EID * N_TARGETS) + start
                full_mask[base : base + N_TARGETS] = True
        return full_mask

    def _compute_multidiscrete_mask(
        self, obs: dict | np.ndarray,
    ) -> tuple[np.ndarray, ...]:
        """Build per-dimension boolean masks for MultiDiscrete action space.

        Returns a tuple of 4 boolean arrays:
            cmd_mask:   shape(6,)  — always all True
            eid_mask:   shape(4,)  — True for buckets with alive owned entities
            x_mask:     shape(8,)  — always all True
            y_mask:     shape(4,)  — always all True
        """
        valid_buckets = self._extract_entity_indices(obs)

        eid_mask = np.zeros(self._N_EID, dtype=np.bool_)
        eid_mask[valid_buckets] = True

        cmd_mask = np.ones(self._N_CMD, dtype=np.bool_)
        x_mask = np.ones(self._N_X, dtype=np.bool_)
        y_mask = np.ones(self._N_Y, dtype=np.bool_)

        return (cmd_mask, eid_mask, x_mask, y_mask)


# ─── 4. MultiDiscreteActionMaskRTS ────────────────────────────────
class MultiDiscreteActionMaskRTS(ActionMaskRTS):
    """Convenience wrapper that auto-selects multidiscrete action masking.

    If the wrapped env uses a ``MultiDiscrete`` action space, this wrapper
    automatically sets ``action_mode='multidiscrete'``.  Otherwise it
    falls back to ``'discrete'``.
    """

    def __init__(self, env: gym.Env) -> None:
        detected = (
            "multidiscrete"
            if isinstance(env.action_space, spaces.MultiDiscrete)
            else "discrete"
        )
        super().__init__(env, action_mode=detected)


# ─── 5. RNDRewardWrapper ──────────────────────────────────────────
class _RNDFeatureNetwork(nn.Module):
    """Simple 2-layer MLP feature encoder used by both target & predictor.

    Architecture:  Linear(obs_dim → 256) → ReLU → Linear(256 → 128)
    """

    def __init__(self, obs_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class RNDRewardWrapper(gym.Wrapper):
    """Random Network Distillation (RND) intrinsic reward wrapper.

    Implements the intrinsic reward mechanism from
    *Burda et al.*, "Exploration by Random Network Distillation" (2018)
    https://arxiv.org/abs/1810.12894

    Two neural networks share the same architecture (2-layer MLP:
    obs_dim → 256 → 128):

    * **Target network** — randomly initialised, weights frozen.  Provides a
      fixed, random embedding of the observation.
    * **Predictor network** — same architecture, trained online with SGD to
      predict the target network's output.

    The intrinsic reward is the mean-squared error between the two embeddings::

        r_int = MSE(predictor(obs), target(obs))

    Novel / unfamiliar states yield high prediction error → high intrinsic
    reward → encourages exploration.  As the predictor learns to match the
    target on visited states, the intrinsic reward for those states decays,
    naturally shifting focus toward still-unexplored regions.

    The intrinsic reward is normalised with a running mean/std (Welford
    online estimator) before being scaled by ``intrinsic_weight`` and added
    to the environment's extrinsic reward::

        r_total = r_ext + intrinsic_weight * normalise(r_int)

    Args:
        env:               Gymnasium environment (must produce flat Box obs).
        intrinsic_weight:  Scaling factor for the intrinsic reward (default 0.5).
        lr:                Learning rate for the predictor SGD optimiser.
        obs_dim:           Observation dimension (auto-detected from env if None).

    Note:
        ``obs`` arriving in ``step()`` is expected to be a **flat** numpy array
        (e.g. after ``FlattenRTSObs``).  The wrapper converts it to a torch
        tensor internally.
    """

    def __init__(
        self,
        env: gym.Env,
        intrinsic_weight: float = 0.5,
        lr: float = 1e-4,
        obs_dim: int | None = None,
    ) -> None:
        super().__init__(env)

        if obs_dim is None:
            obs_space = env.observation_space
            if isinstance(obs_space, spaces.Box) and len(obs_space.shape) == 1:
                obs_dim = int(obs_space.shape[0])
            else:
                raise ValueError(
                    "Cannot auto-detect obs_dim from observation space "
                    f"{obs_space}.  Pass obs_dim explicitly."
                )

        self.intrinsic_weight = intrinsic_weight
        self._obs_dim = obs_dim

        # --- Target network (fixed random weights) ---
        self._target = _RNDFeatureNetwork(obs_dim)
        self._target.eval()  # always in eval mode
        for p in self._target.parameters():
            p.requires_grad = False

        # --- Predictor network (trainable) ---
        self._predictor = _RNDFeatureNetwork(obs_dim)
        self._predictor.train()

        # --- Optimiser (SGD, as per the paper) ---
        self._optimizer = torch.optim.SGD(self._predictor.parameters(), lr=lr)

        # --- Running mean / std for intrinsic reward normalisation ---
        self._int_mean: float = 0.0
        self._int_var: float = 1.0
        self._int_count: int = 0
        self._eps: float = 1e-8

    # ─── Intrinsic reward normalisation (Welford online) ─────────

    def _update_int_stats(self, r_int: float) -> None:
        """Welford online update of running mean/var for intrinsic reward."""
        self._int_count += 1
        delta = r_int - self._int_mean
        self._int_mean += delta / self._int_count
        delta2 = r_int - self._int_mean
        self._int_var += delta * delta2

    def _normalise_int(self, r_int: float) -> float:
        """Return normalised intrinsic reward (identity during warm-up)."""
        if self._int_count < 2:
            return r_int
        std = float(np.sqrt(self._int_var / (self._int_count - 1) + self._eps))
        return r_int / std

    # ─── Core step logic ────────────────────────────────────────

    def step(
        self, action,
    ) -> tuple[np.ndarray | dict, float, bool, bool, dict]:
        obs, reward, terminated, truncated, info = self.env.step(action)

        # Convert flat obs numpy → torch tensor
        obs_tensor = torch.as_tensor(
            obs, dtype=torch.float32
        ).reshape(1, self._obs_dim)

        # --- Compute intrinsic reward ---
        with torch.no_grad():
            target_emb = self._target(obs_tensor)          # (1, 128)
        predictor_emb = self._predictor(obs_tensor)         # (1, 128)

        # MSE between predictor and target embeddings (scalar)
        r_int_tensor = ((predictor_emb - target_emb) ** 2).mean()
        r_int = float(r_int_tensor.item())

        # --- Train predictor on this step ---
        self._optimizer.zero_grad()
        loss = ((predictor_emb - target_emb.detach()) ** 2).mean()
        loss.backward()
        self._optimizer.step()

        # --- Normalise & blend intrinsic reward ---
        self._update_int_stats(r_int)
        r_int_normed = self._normalise_int(r_int)

        total_reward = float(reward) + self.intrinsic_weight * r_int_normed

        # Store intrinsic reward in info for logging / analysis
        info["rnd_int_reward"] = r_int
        info["rnd_int_reward_normed"] = r_int_normed

        return obs, total_reward, terminated, truncated, info

    # ─── Utility methods ───────────────────────────────────────

    def reset_int_stats(self) -> None:
        """Clear running intrinsic reward statistics (call before eval)."""
        self._int_mean = 0.0
        self._int_var = 1.0
        self._int_count = 0

    def reset(
        self, *, seed: int | None = None, options: dict | None = None,
    ) -> tuple[np.ndarray | dict, dict]:
        """Reset the environment; intrinsic reward stats are *not* cleared."""
        return self.env.reset(seed=seed, options=options)
