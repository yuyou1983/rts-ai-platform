"""Behavioral Cloning pre-training from AI agents, then PPO fine-tuning.

Usage:
    python -m simcore.bc_pretrain        # collect demos + pretrain + PPO finetune
    python -m simcore.bc_pretrain --collect-only   # just collect demos
    python -m simcore.bc_pretrain --train-only      # pretrain + finetune from saved demos
"""
from __future__ import annotations

import argparse
import os
import pickle
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback, EvalCallback

from simcore.ppo_callbacks import EntropyCoefScheduler, ReduceLROnPlateau, CurriculumStepSync

from simcore.gym_env import (
    ACTION_DIM_EID,
    ACTION_DIM_X,
    ACTION_DIM_Y,
    COMMAND_TYPES,
    MAP_SIZE,
    RTSSimCoreEnv,
)
from simcore.wrappers import FlattenRTSObs, NormalizeRTSReward, RNDRewardWrapper
from simcore.reward_shaping import RewardShapingConfig

# ─── Constants ───────────────────────────────────────────────

DEMO_DIR = Path("logs/demos")
OBS_DIM = 1093  # FlattenRTSObs output dimension


# ─── Action encoding (inverse of _decode_action) ─────────────

def encode_action(commands: list[dict], state, owner: int = 1) -> np.ndarray:
    """Convert AI agent commands → MultiDiscrete action array.

    If no valid command, returns noop [5, 0, 0, 0].
    """
    cmd_map = {c: i for i, c in enumerate(COMMAND_TYPES)}

    for cmd in commands:
        if cmd.get("issuer", 0) != owner:
            continue
        action_name = cmd.get("action", "noop")
        # Map deprecated "move" to "attack" (closest semantic equivalent for mobile units)
        if action_name == "move":
            action_name = "attack"
        if action_name not in cmd_map:
            continue
        ct_idx = cmd_map[action_name]

        # Find entity bucket
        controlled_owners = {1, 2}  # two-player for demos
        own_entities = sorted(
            [(eid, e) for eid, e in state.entities.items()
             if e.get("owner", 0) in controlled_owners and e.get("health", 0) > 0],
            key=lambda p: p[0],
        )
        eid_target = cmd.get("attacker_id", cmd.get("unit_id", ""))
        eid_bucket = 0
        for i, (eid, _) in enumerate(own_entities):
            if eid == eid_target and i < ACTION_DIM_EID:
                eid_bucket = i
                break

        # Quantise position
        tx = cmd.get("target_x", cmd.get("x", 0.0))
        ty = cmd.get("target_y", cmd.get("y", 0.0))
        x_bucket = int(np.clip(tx / (MAP_SIZE / ACTION_DIM_X), 0, ACTION_DIM_X - 1))
        y_bucket = int(np.clip(ty / (MAP_SIZE / ACTION_DIM_Y), 0, ACTION_DIM_Y - 1))

        return np.array([ct_idx, eid_bucket, x_bucket, y_bucket], dtype=np.int64)

    # No command for this owner → noop
    noop_idx = cmd_map.get("noop", len(COMMAND_TYPES) - 1)
    return np.array([noop_idx, 0, 0, 0], dtype=np.int64)


# ─── Demonstration collection ────────────────────────────────

def collect_demonstrations(
    n_episodes: int = 50,
    seed_start: int = 42,
    max_ticks: int = 1000,
) -> tuple[np.ndarray, np.ndarray]:
    """Collect expert trajectories from RushAI vs GreedyGatherer."""
    from simcore.engine import SimCore
    from simcore.agents import RushAI, GreedyGatherer

    all_obs: list[np.ndarray] = []
    all_act: list[np.ndarray] = []

    # Create a single-player env just for the obs wrapper
    ref_env = FlattenRTSObs(RTSSimCoreEnv(seed=0, max_ticks=1))

    for ep in range(n_episodes):
        seed = seed_start + ep
        engine = SimCore(max_ticks=max_ticks)
        engine.initialize(map_seed=seed)

        agent1 = RushAI(player_id=1)
        agent2 = GreedyGatherer(player_id=2)

        for tick in range(max_ticks):
            state = engine.state
            if state.is_terminal:
                break

            obs1 = engine.get_observations(1)
            obs2 = engine.get_observations(2)

            cmds1 = agent1.decide(obs1)
            cmds2 = agent2.decide(obs2)
            all_cmds = (cmds1 or []) + (cmds2 or [])

            # Encode P1 action
            action_arr = encode_action(cmds1 or [], state, owner=1)

            # Get flattened observation for P1
            # Use the ref_env to flatten: set internal state, then call _state_to_obs
            raw_env = ref_env.env  # unwrapped RTSSimCoreEnv
            raw_env._engine = engine
            flat_obs = ref_env.observation(raw_env._state_to_obs(state))

            all_obs.append(flat_obs.astype(np.float32))
            all_act.append(action_arr)

            engine.step(all_cmds)

        if (ep + 1) % 10 == 0:
            print(f"  Collected {ep+1}/{n_episodes} episodes, "
                  f"{len(all_obs)} transitions total")

        engine = None  # release

    ref_env.close()

    obs_array = np.stack(all_obs)
    act_array = np.stack(all_act)
    print(f"Demonstration collection done: {obs_array.shape[0]} transitions")
    return obs_array, act_array


def collect_hierarchical_demonstrations(
    n_episodes: int = 50,
    seed_start: int = 42,
    max_ticks: int = 1000,
    c_step: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """Collect (obs, goal_idx) pairs for Manager BC pre-training."""
    from simcore.engine import SimCore
    from simcore.agents import RushAI, GreedyGatherer
    from simcore.hierarchical_env import command_to_goal, N_GOALS

    all_obs: list[np.ndarray] = []
    all_goals: list[int] = []

    ref_env = FlattenRTSObs(RTSSimCoreEnv(seed=0, max_ticks=1))

    for ep in range(n_episodes):
        seed = seed_start + ep
        engine = SimCore(max_ticks=max_ticks)
        engine.initialize(map_seed=seed)

        agent1 = RushAI(player_id=1)
        agent2 = GreedyGatherer(player_id=2)

        for tick in range(max_ticks):
            state = engine.state
            if state.is_terminal:
                break

            obs1 = engine.get_observations(1)
            obs2 = engine.get_observations(2)

            cmds1 = agent1.decide(obs1)
            cmds2 = agent2.decide(obs2)
            all_cmds = (cmds1 or []) + (cmds2 or [])

            # Map P1 commands → high-level goal
            goal = command_to_goal(cmds1[0]) if cmds1 else command_to_goal({})

            # Get flattened observation
            raw_env = ref_env.env
            raw_env._engine = engine
            flat_obs = ref_env.observation(raw_env._state_to_obs(state))

            # Build manager obs: flat_obs + goal_onehot + step_frac
            goal_oh = np.zeros(N_GOALS, dtype=np.float32)
            goal_oh[goal] = 1.0
            step_frac = np.array([tick / max_ticks], dtype=np.float32)
            manager_obs = np.concatenate([flat_obs, goal_oh, step_frac])

            all_obs.append(manager_obs.astype(np.float32))
            all_goals.append(int(goal))

            engine.step(all_cmds)

        if (ep + 1) % 10 == 0:
            print(f"  Collected {ep+1}/{n_episodes} episodes, "
                  f"{len(all_obs)} transitions total")

        engine = None

    ref_env.close()

    obs_array = np.stack(all_obs)
    goal_array = np.array(all_goals, dtype=np.int64)
    print(f"Hierarchical demo collection done: {obs_array.shape[0]} transitions")
    return obs_array, goal_array


# ─── Behavioral Cloning pre-trainer ──────────────────────────

def bc_pretrain(
    model: PPO,
    obs_array: np.ndarray,
    act_array: np.ndarray,
    n_epochs: int = 15,
    batch_size: int = 256,
    lr: float = 1e-3,
) -> PPO:
    """Supervised pre-training of the policy network via BC."""
    device = model.device
    policy = model.policy

    optimizer = torch.optim.Adam(policy.action_net.parameters(), lr=lr)
    # Also train the shared feature extractor
    optimizer.add_param_group({"params": policy.features_extractor.parameters(), "lr": lr * 0.1})

    n_samples = obs_array.shape[0]
    criterion = nn.CrossEntropyLoss()

    obs_t = torch.tensor(obs_array, dtype=torch.float32, device=device)
    # MultiDiscrete: separate targets per dim
    targets = [torch.tensor(act_array[:, d], dtype=torch.long, device=device) for d in range(4)]

    print(f"BC pre-training: {n_samples} samples, {n_epochs} epochs, lr={lr}")

    for epoch in range(n_epochs):
        perm = torch.randperm(n_samples, device=device)
        epoch_loss = 0.0
        n_batches = 0

        for i in range(0, n_samples, batch_size):
            idx = perm[i:i + batch_size]
            batch_obs = obs_t[idx]

            features = policy.extract_features(batch_obs)
            latent = policy.mlp_extractor.forward_actor(features)

            # action_net outputs logits for all dims concatenated
            logits = policy.action_net(latent)
            # Split logits into 4 heads: [6, 4, 8, 4]
            split_sizes = [ACTION_DIM_EID + 2, ACTION_DIM_EID, ACTION_DIM_X, ACTION_DIM_Y]  # 6, 4, 8, 4
            # Actually read from model.action_space
            split_sizes = list(model.action_space.nvec)

            logit_splits = torch.split(logits, split_sizes, dim=-1)

            loss = sum(criterion(s, t[idx]) for s, t in zip(logit_splits, targets))

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / max(n_batches, 1)
        print(f"  Epoch {epoch+1}/{n_epochs}  loss={avg_loss:.4f}")

    return model


def bc_pretrain_manager(
    model: PPO,
    obs_array: np.ndarray,
    goal_array: np.ndarray,
    n_epochs: int = 15,
    batch_size: int = 256,
    lr: float = 1e-3,
) -> PPO:
    """Supervised pre-training of the Manager (Discrete(6)) policy."""
    device = model.device
    policy = model.policy

    optimizer = torch.optim.Adam(
        list(policy.action_net.parameters()) + list(policy.features_extractor.parameters()),
        lr=lr,
    )

    n_samples = obs_array.shape[0]
    criterion = nn.CrossEntropyLoss()

    obs_t = torch.tensor(obs_array, dtype=torch.float32, device=device)
    targets = torch.tensor(goal_array, dtype=torch.long, device=device)

    print(f"BC Manager pre-training: {n_samples} samples, {n_epochs} epochs, lr={lr}")

    for epoch in range(n_epochs):
        perm = torch.randperm(n_samples, device=device)
        epoch_loss = 0.0
        n_batches = 0

        for i in range(0, n_samples, batch_size):
            idx = perm[i:i + batch_size]
            batch_obs = obs_t[idx]

            features = policy.extract_features(batch_obs)
            latent = policy.mlp_extractor.forward_actor(features)
            logits = policy.action_net(latent)  # shape: (B, 6)

            loss = criterion(logits, targets[idx])

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / max(n_batches, 1)
        acc = (logits.argmax(dim=-1) == targets[idx]).float().mean().item()
        print(f"  Epoch {epoch+1}/{n_epochs}  loss={avg_loss:.4f}  acc={acc:.2%}")

    return model

def run_pipeline(
    n_demo_episodes: int = 50,
    bc_epochs: int = 15,
    ppo_timesteps: int = 500_000,
    seed: int = 42,
):
    cfg = RewardShapingConfig()

    # ── Step 1: Collect demonstrations ──
    demo_path = DEMO_DIR / "p1_rush_vs_greedy.pkl"
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    if demo_path.exists():
        print(f"Loading cached demos from {demo_path}")
        with open(demo_path, "rb") as f:
            obs_array, act_array = pickle.load(f)
    else:
        print("=== Collecting expert demonstrations ===")
        obs_array, act_array = collect_demonstrations(n_episodes=n_demo_episodes)
        with open(demo_path, "wb") as f:
            pickle.dump((obs_array, act_array), f)
        print(f"Demos cached to {demo_path}")

    # ── Step 2: Create PPO model ──
    raw_env = RTSSimCoreEnv(seed=seed, max_ticks=1000, two_player=False,
                             reward_shaping="dense", action_mode="multidiscrete",
                             reward_config=cfg)
    env = FlattenRTSObs(raw_env)
    env = NormalizeRTSReward(env, eps=1e-8, clip=10.0)
    env = RNDRewardWrapper(env, intrinsic_weight=0.15, lr=1e-4)  # low RND

    raw_eval = RTSSimCoreEnv(seed=123, max_ticks=1000, two_player=False,
                              reward_shaping="dense", action_mode="multidiscrete",
                              reward_config=cfg)
    eval_env = FlattenRTSObs(raw_eval)
    eval_env = NormalizeRTSReward(eval_env, eps=1e-8, clip=10.0)

    model = PPO(
        "MlpPolicy", env,
        n_steps=4096, batch_size=256,           # v10: 2048→4096, 64→256
        n_epochs=10, learning_rate=1e-4,        # v10: 3e-4→1e-4
        ent_coef=0.02,  # lower after BC pretrain
        clip_range=0.2,
        verbose=1, device="auto",
    )

    # ── Step 3: BC pre-train ──
    print("\n=== BC Pre-training ===")
    model = bc_pretrain(model, obs_array, act_array, n_epochs=bc_epochs)

    # ── Step 4: PPO fine-tune ──
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = f"logs/train/ppo_v7_bc_{timestamp}"
    os.makedirs(log_dir, exist_ok=True)

    eval_cb = EvalCallback(
        eval_env, best_model_save_path=f"{log_dir}/best",
        log_path=f"{log_dir}/eval", eval_freq=10_000,
        n_eval_episodes=5, deterministic=True,
    )

    print(f"\n=== PPO Fine-tuning (v7 BC+PPO) ===")
    print(f"Log dir: {log_dir}")
    model.learn(total_timesteps=ppo_timesteps, callback=eval_cb, progress_bar=True)
    model.save(f"{log_dir}/ppo_v7_final")
    print(f"\nDone. Model saved to {log_dir}/ppo_v7_final.zip")

    env.close()
    eval_env.close()


def run_hierarchical_pipeline(
    n_demo_episodes: int = 50,
    bc_epochs: int = 15,
    ppo_timesteps: int = 500_000,
    seed: int = 42,
    c_step: int = 20,
):
    """Train hierarchical Manager: BC pretrain → PPO finetune (V11).

    V11 changes vs V10:
    - Entropy coefficient scheduling: 0.1 → 0.01 linearly over 300K steps
      (V10 used fixed 0.02, leading to premature determinism & collapse).
    - ReduceLROnPlateau: halve LR when ep_rew_mean drops >20% for 3
      consecutive evals (V10 had no LR adaptation → destabilising late updates).
    - PPO hyper-params: n_steps=2048, batch_size=128, lr=3e-4, ent_coef=0.1
      (V10 used n_steps=4096, batch_size=256, lr=1e-4, ent_coef=0.02).
    """
    from simcore.hierarchical_env import HierarchicalRTSEnv, ActionMasker
    from simcore.reward_shaping import get_curriculum_phase

    cfg = RewardShapingConfig()

    # ── Step 1: Collect hierarchical demos ──
    hier_demo_path = DEMO_DIR / "hierarchical_manager.pkl"
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    if hier_demo_path.exists():
        print(f"Loading cached hierarchical demos from {hier_demo_path}")
        with open(hier_demo_path, "rb") as f:
            obs_array, goal_array = pickle.load(f)
    else:
        print("=== Collecting hierarchical demonstrations ===")
        obs_array, goal_array = collect_hierarchical_demonstrations(
            n_episodes=n_demo_episodes, c_step=c_step)
        with open(hier_demo_path, "wb") as f:
            pickle.dump((obs_array, goal_array), f)
        print(f"Demos cached to {hier_demo_path}")

    # ── Step 2: Create Manager PPO model (V11 params) ──
    # V11: wrap with ActionMasker so info["action_masks"] is exposed
    raw_env = HierarchicalRTSEnv(seed=seed, max_ticks=1000, c_step=c_step,
                                  two_player=False, reward_shaping="dense",
                                  reward_config=cfg)
    env = ActionMasker(raw_env)
    raw_eval = HierarchicalRTSEnv(seed=123, max_ticks=1000, c_step=c_step,
                                   two_player=False, reward_shaping="dense",
                                   reward_config=cfg)
    eval_env = ActionMasker(raw_eval)

    model = PPO(
        "MlpPolicy", env,
        n_steps=2048, batch_size=128,            # v11: smaller rollout & batch to reduce value overfitting
        n_epochs=10, learning_rate=3e-4,          # v11: higher LR for faster early learning
        ent_coef=0.1,                             # v11: start high; EntropyCoefScheduler will decay it
        clip_range=0.2,
        verbose=1, device="auto",
    )

    # ── Step 3: BC pre-train Manager ──
    print("\n=== BC Manager Pre-training ===")
    model = bc_pretrain_manager(model, obs_array, goal_array, n_epochs=bc_epochs)

    # ── Step 4: PPO fine-tune with V11 callbacks ──
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = f"logs/train/ppo_v11_hier_{timestamp}"
    os.makedirs(log_dir, exist_ok=True)

    # Callback: periodic evaluation on eval_env.
    eval_cb = EvalCallback(
        eval_env, best_model_save_path=f"{log_dir}/best",
        log_path=f"{log_dir}/eval", eval_freq=10_000,
        n_eval_episodes=5, deterministic=True,
    )

    # Callback: entropy coefficient linear decay 0.1 → 0.01 over 300K steps.
    entropy_cb = EntropyCoefScheduler(
        start=0.1,
        end=0.01,
        total_steps=300_000,
        verbose=1,
    )

    # Callback: reduce LR when reward plateaus / collapses.
    reduce_lr_cb = ReduceLROnPlateau(
        patience=3,
        threshold=0.2,
        factor=0.5,
        min_lr=1e-6,
        verbose=1,
    )

    # Callback: sync curriculum training step into env's SubgoalTracker.
    curriculum_cb = CurriculumStepSync(verbose=1)

    # Compose all callbacks.
    from stable_baselines3.common.callbacks import CallbackList
    callbacks = CallbackList([eval_cb, entropy_cb, reduce_lr_cb, curriculum_cb])

    print(f"\n=== PPO Fine-tuning Hierarchical Manager (V11) ===")
    print(f"Manager action space: Discrete(6)")
    print(f"c_step: {c_step}")
    print(f"V11 hyper-params: n_steps=2048, batch=128, lr=3e-4, ent_coef=0.1→0.01")
    print(f"V11: action masks + curriculum reward + entropy scheduling + LR plateau reduction")
    print(f"Log dir: {log_dir}")
    model.learn(total_timesteps=ppo_timesteps, callback=callbacks, progress_bar=True)
    model.save(f"{log_dir}/ppo_v11_final")
    print(f"\nDone. Model saved to {log_dir}/ppo_v11_final.zip")

    env.close()
    eval_env.close()


# ─── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect-only", action="store_true")
    ap.add_argument("--train-only", action="store_true")
    ap.add_argument("--n-demos", type=int, default=50)
    ap.add_argument("--ppo-steps", type=int, default=500_000)
    ap.add_argument("--hierarchical", action="store_true", help="Use hierarchical Manager")
    ap.add_argument("--c-step", type=int, default=20, help="Manager decision interval")
    args = ap.parse_args()

    if args.collect_only:
        obs, act = collect_demonstrations(n_episodes=args.n_demos)
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEMO_DIR / "p1_rush_vs_greedy.pkl", "wb") as f:
            pickle.dump((obs, act), f)
    elif args.train_only:
        run_pipeline(n_demo_episodes=0)  # will load cached
    elif args.hierarchical:
        run_hierarchical_pipeline(
            n_demo_episodes=args.n_demos, ppo_timesteps=args.ppo_steps, c_step=args.c_step)
    else:
        run_pipeline(n_demo_episodes=args.n_demos, ppo_timesteps=args.ppo_steps)
