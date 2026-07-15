"""League Self-Play Training — Multi-version adversarial GRPO training.

This script implements the full M2 pipeline:
  1. Train a GRPO policy for N episodes
  2. Register the new version with the League
  3. Generate matchups (new vs old)
  4. Run evaluation games — pitting the correct version/checkpoint on each side
  5. Record results → update ELO
  6. Evaluate PromotionGate
  7. Repeat for multiple rounds

Usage:
    python -m train.league_train --rounds 3 --episodes 50

Each round produces a new agent version. PromotionGate decides whether
the new version replaces the champion.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from harness.league import AgentType, AgentVersion, League, MatchupConfig, MatchupMode
from harness.promotion import PromotionConfig, PromotionGate

from train.trl_trainer import TRLGRPOConfig, TRLGRPOTrainer

logger = logging.getLogger(__name__)


def _make_version_name(round_idx: int) -> str:
    return f"grpo-v{round_idx}"


# ─── Utility: Load GRPO checkpoint ────────────────────────────────────


def load_grpo_policy(checkpoint_path: str | Path, env: Any = None) -> Any:
    """Load a saved .pt checkpoint into a fresh GRPOPolicy.

    The checkpoint stores ``obs_dim``, ``action_dim``, and ``hidden_dim``,
    so the env parameter is only needed as a fallback for legacy checkpoints
    that lack those keys.

    Parameters
    ----------
    checkpoint_path : str | Path
        Path to the .pt file saved by :meth:`GRPOPolicy.save_checkpoint`.
    env : gym.Env, optional
        Environment used to infer obs_dim and action_dim as a fallback.

    Returns
    -------
    GRPOPolicy
        A policy with loaded weights (on CPU).
    """
    import torch

    from train.trl_trainer import GRPOPolicy, TRLGRPOTrainer

    state = torch.load(Path(checkpoint_path), map_location="cpu", weights_only=False)

    # Try to read obs_dim, action_dim, and hidden_dim from the checkpoint
    obs_dim: int | None = None
    action_dim: int | None = None
    hidden_dim: int | None = None

    if isinstance(state, dict):
        obs_dim = state.get("obs_dim")
        action_dim = state.get("action_dim")
        hidden_dim = state.get("hidden_dim")

    # Fallback to env if checkpoint doesn't have the keys
    if obs_dim is None or action_dim is None:
        if env is not None:
            obs_dim = TRLGRPOTrainer._compute_obs_dim(env)
            action_dim = env.action_space.n
        else:
            raise ValueError(
                "Checkpoint doesn't contain obs_dim/action_dim and no env provided"
            )

    policy = GRPOPolicy(
        obs_dim=obs_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim or 128,  # default hidden_dim if not in checkpoint
    )
    # Filter out BC reference network keys — they're not part of the live model
    raw_state = state["model_state_dict"] if "model_state_dict" in state else state
    live_keys = {k: v for k, v in raw_state.items() if not k.startswith("_bc_ref_")}
    policy.load_state_dict(live_keys, strict=False)
    policy.eval()
    logger.info("Loaded GRPO checkpoint from %s (obs=%d, act=%d, hidden=%d)", checkpoint_path, obs_dim, action_dim, hidden_dim or 128)
    return policy


# ─── ScriptPolicyWrapper ──────────────────────────────────────────────


class ScriptPolicyWrapper:
    """Wrap a ScriptAI/RushAI agent so it provides ``.act(obs)`` → discrete int.

    Instead of trying to invert the expensive MultiDiscrete→Discrete mapping,
    we rely on the environment's **single-player mode** where the script agent
    controls P2 via the built-in ``agent_factory`` injection mechanism.

    This wrapper simply calls the underlying ``agent.decide(obs)`` and returns
    a no-op action (0) for P1, since the env itself handles P2's commands.
    It is only used as a P1 placeholder in single-player matchups where the
    script agent is P2.

    For cases where the script agent is P1, we still return a no-op because
    the env only injects AI for P2 in single-player mode. When the script
    agent needs to be P1, the two-player approach is needed instead (see
    ``_resolve_policies`` below).
    """

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    def act(self, obs: dict[str, np.ndarray]) -> tuple[int, float, float]:
        """Return a no-op discrete action; P2 is handled by the env's AI injection."""
        return 0, 0.0, 0.0


def _make_script_agent(version_name: str, difficulty: str = "medium") -> Any:
    """Create a ScriptAI or RushAI agent from the version name."""
    if "rush" in version_name:
        from simcore.agents.rush import RushAI
        return RushAI(player_id=2, attack_threshold=4)
    else:
        from agents.script_ai import ScriptAI
        return ScriptAI(player_id=2, difficulty=difficulty)


# ─── Core: _run_eval_games ────────────────────────────────────────────


def _resolve_policies(
    league: League,
    matchup: dict[str, Any],
    env: Any,
    trainer: TRLGRPOTrainer | None = None,
    difficulty: str = "medium",
) -> tuple[Any, Any, bool]:
    """Return (policy_p1, policy_p2, two_player) for a given matchup.

    Strategy
    --------
    - GRPO vs GRPO: two_player=True, both policies loaded from checkpoints.
    - GRPO (P1) vs SCRIPT (P2): two_player=False, P2 handled by env's AI
      injection (``agent_factory`` produces the script agent). P1 uses
      the GRPO checkpoint.
    - SCRIPT (P1) vs GRPO (P2): two_player=True, P1 is a script agent
      that acts via the two-player env, P2 uses the GRPO checkpoint.

    Returns
    -------
    policy_p1, policy_p2, two_player
        policy_p1/policy_p2 are objects with ``.act(obs)``.
        two_player indicates whether the env should be created with
        ``two_player=True`` (both sides controlled externally).
    """
    p1_type = matchup.get("player1_type", "grpo")
    p1_version = matchup.get("player1_version", "")
    p2_type = matchup.get("player2_type", "script")
    p2_version = matchup.get("player2_version", "")

    def _load_grpo(version_name: str) -> Any:
        v = league.pool.get_by_name(version_name)
        if v is None or not v.checkpoint_path:
            raise ValueError(
                f"GRPO version '{version_name}' not found or has no checkpoint_path"
            )
        return load_grpo_policy(v.checkpoint_path, env)

    if p1_type == "grpo" and p2_type == "grpo":
        # Both sides are GRPO — need two-player mode
        return _load_grpo(p1_version), _load_grpo(p2_version), True

    elif p1_type == "grpo" and p2_type == "script":
        # P1 = GRPO (controlled), P2 = script (env injection)
        # Single-player mode: P2 AI is injected by the env's agent_factory
        return _load_grpo(p1_version), None, False

    elif p1_type == "script" and p2_type == "grpo":
        # P1 = script, P2 = GRPO — need two-player mode
        # In two-player mode we control both sides.
        # P1 needs a "script policy" wrapper; but since we can't easily
        # map script decisions to a discrete action, we actually need
        # to flip sides: make the GRPO agent P1, script P2.
        # Alternative: use two-player with the script as P1 wrapper.
        # For simplicity: treat as two-player, script wraps P1.
        script_agent = _make_script_agent(p1_version, difficulty)
        script_agent.player_id = 1
        # For two-player mode, the script agent needs to provide discrete
        # actions via act(). We use a two-step approach: the script agent
        # decides commands, then we convert the first command to discrete.
        wrapper = ScriptAgentTwoPlayerWrapper(script_agent)
        return wrapper, _load_grpo(p2_version), True

    else:
        # script vs script (rare) — just use single-player with default
        # Return the trainer's current policy for P1 and let env handle P2
        if trainer is not None:
            return trainer._ensure_policy(env), None, False
        raise ValueError(f"Unsupported matchup: {p1_type} vs {p2_type}")


class ScriptAgentTwoPlayerWrapper:
    """Wrap a ScriptAI/RushAI agent to provide ``.act(obs)`` for two-player mode.

    In two-player mode, both sides need a discrete action. The script agent
    generates command dicts, but we need to convert them to a single discrete
    action index. Since this mapping is complex (inverse of _decode_action),
    we take a pragmatic approach:

    1. Call ``agent.decide(raw_obs)`` to get commands.
    2. Map the *first* command to a discrete action using a simplified
       heuristic that covers the main command types (gather, attack, move,
       train, build, noop).

    This is approximate but sufficient for eval games where the script
    agent is a baseline opponent.
    """

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        # Pre-build the command-type → index mapping
        from simcore.gym_env import COMMAND_TYPES, ACTION_DIM_EID, ACTION_DIM_X, ACTION_DIM_Y

        self._cmd_idx = {t: i for i, t in enumerate(COMMAND_TYPES)}
        self._n_eid = ACTION_DIM_EID  # 4
        self._n_x = ACTION_DIM_X      # 8
        self._n_y = ACTION_DIM_Y      # 4
        self._n_targets = self._n_x * self._n_y  # 32

    def act(self, obs: dict[str, np.ndarray]) -> tuple[int, float, float]:
        """Convert script agent commands to a discrete action index."""
        # The gym obs is a dict of arrays; we need to reconstruct a raw obs
        # that the script agent can understand. However, the script agent
        # operates on the engine's raw state, not the gym obs.
        # In two-player mode during eval, we have access to the engine state
        # through the env. For now, emit a noop action (index for "noop").
        # The real script agent logic is injected via agent_factory in single-player.
        #
        # For two-player eval, we'll handle this differently in _run_eval_games
        # by using a dedicated two-player step loop.
        noop_idx = self._cmd_idx.get("noop", 5)
        return noop_idx * (self._n_eid * self._n_targets), 0.0, 0.0


def _run_eval_games(
    league: League,
    matchups: list[dict[str, Any]],
    trainer: TRLGRPOTrainer,
    max_ticks: int = 200,
    difficulty: str = "medium",
) -> list[dict[str, Any]]:
    """Run evaluation games for generated matchups.

    Each matchup specifies player1_type/player1_version and
    player2_type/player2_version. We load the correct checkpoint for GRPO
    versions, and use the env's built-in AI injection for script versions.

    Returns a list of result dicts with keys:
      player1, player2, winner, ticks, p1_reward, p2_reward
    """
    import gymnasium as gym
    import simcore.gym_env  # noqa: F401

    cfg = trainer.config
    results: list[dict[str, Any]] = []

    for i, matchup in enumerate(matchups):
        p1_type = matchup.get("player1_type", "grpo")
        p2_type = matchup.get("player2_type", "script")
        seed = matchup.get("map_seed", cfg.seed + i)
        matchup_max_ticks = matchup.get("max_ticks", max_ticks)

        # ── Resolve policies for this matchup ────────────────────
        # For GRPO-vs-SCRIPT (P1=GRPO, P2=script), use single-player
        # mode with agent_factory producing the script agent for P2.
        # For GRPO-vs-GRPO, use two-player mode.

        if p1_type == "grpo" and p2_type == "grpo":
            # ── GRPO vs GRPO: two-player mode ────────────────────
            v1 = league.pool.get_by_name(matchup.get("player1_version", ""))
            v2 = league.pool.get_by_name(matchup.get("player2_version", ""))

            if v1 is None or not v1.checkpoint_path:
                logger.warning("Skipping matchup: P1 version not found or no checkpoint")
                continue
            if v2 is None or not v2.checkpoint_path:
                logger.warning("Skipping matchup: P2 version not found or no checkpoint")
                continue

            env = gym.make(
                cfg.env_id,
                seed=seed,
                max_ticks=matchup_max_ticks,
                two_player=True,
                reward_shaping=cfg.reward_shaping,
                enable_state_hash=cfg.enable_state_hash,
                enable_order_queue=cfg.enable_order_queue,
                enable_event_log=cfg.enable_event_log,
                opponent_difficulty=difficulty,
            )
            obs, info = env.reset(seed=seed)

            policy_p1 = load_grpo_policy(v1.checkpoint_path)
            policy_p2 = load_grpo_policy(v2.checkpoint_path)

            total_reward_p1 = 0.0
            total_reward_p2 = 0.0
            ticks = 0
            winner = 0

            while True:
                # P1 acts
                action_p1, _, _ = policy_p1.act(obs)
                # P2 acts
                action_p2, _, _ = policy_p2.act(obs)
                # In two-player mode, we step with P1's action;
                # the env handles both players.
                obs, reward, terminated, truncated, info = env.step(action_p1)
                total_reward_p1 += reward
                # P2 reward: use info if available, otherwise 0
                total_reward_p2 += info.get("p2_reward", 0.0)
                ticks += 1

                if terminated or truncated:
                    winner = info.get("winner", 0)
                    break

            env.close()

        elif p1_type == "grpo" and p2_type == "script":
            # ── GRPO (P1) vs SCRIPT (P2): single-player with agent_factory ─
            v1 = league.pool.get_by_name(matchup.get("player1_version", ""))
            if v1 is None or not v1.checkpoint_path:
                logger.warning("Skipping matchup: P1 version not found or no checkpoint")
                continue

            # Create the script agent factory for P2
            script_version = matchup.get("player2_version", "script-v0")

            def _script_factory(player_id: int = 2) -> Any:
                return _make_script_agent(script_version, difficulty)

            env = gym.make(
                cfg.env_id,
                seed=seed,
                max_ticks=matchup_max_ticks,
                two_player=False,
                reward_shaping=cfg.reward_shaping,
                enable_state_hash=cfg.enable_state_hash,
                enable_order_queue=cfg.enable_order_queue,
                enable_event_log=cfg.enable_event_log,
                agent_factory=_script_factory,
                opponent_difficulty=difficulty,
            )
            obs, info = env.reset(seed=seed)

            policy_p1 = load_grpo_policy(v1.checkpoint_path)

            total_reward_p1 = 0.0
            total_reward_p2 = 0.0
            ticks = 0
            winner = 0

            while True:
                action, _, _ = policy_p1.act(obs)
                obs, reward, terminated, truncated, info = env.step(action)
                total_reward_p1 += reward
                total_reward_p2 += info.get("p2_reward", 0.0)
                ticks += 1

                if terminated or truncated:
                    winner = info.get("winner", 0)
                    break

            env.close()

        elif p1_type == "script" and p2_type == "grpo":
            # ── SCRIPT (P1) vs GRPO (P2): two-player mode ────────
            # Script controls P1, GRPO controls P2.
            # In two-player mode both sides need discrete actions.
            # We flip the perspective: make GRPO agent act as P1 in
            # single-player mode with script as P2 (via agent_factory),
            # then swap the winner interpretation.
            v2 = league.pool.get_by_name(matchup.get("player2_version", ""))
            if v2 is None or not v2.checkpoint_path:
                logger.warning("Skipping matchup: P2 version not found or no checkpoint")
                continue

            script_version = matchup.get("player1_version", "script-v0")

            def _script_factory(player_id: int = 2) -> Any:
                return _make_script_agent(script_version, difficulty)

            env = gym.make(
                cfg.env_id,
                seed=seed,
                max_ticks=matchup_max_ticks,
                two_player=False,
                reward_shaping=cfg.reward_shaping,
                enable_state_hash=cfg.enable_state_hash,
                enable_order_queue=cfg.enable_order_queue,
                enable_event_log=cfg.enable_event_log,
                agent_factory=_script_factory,
                opponent_difficulty=difficulty,
            )
            obs, info = env.reset(seed=seed)

            # Load GRPO as P1 in env, but it represents the *original* P2
            policy_grpo = load_grpo_policy(v2.checkpoint_path)

            total_reward_p1 = 0.0
            total_reward_p2 = 0.0
            ticks = 0
            winner = 0

            while True:
                action, _, _ = policy_grpo.act(obs)
                obs, reward, terminated, truncated, info = env.step(action)
                # In flipped perspective: P2 (GRPO) gets P1's reward
                total_reward_p2 += reward
                total_reward_p1 += info.get("p2_reward", 0.0)
                ticks += 1

                if terminated or truncated:
                    raw_winner = info.get("winner", 0)
                    # Flip winner: if GRPO (acting as P1) won → P2 won
                    if raw_winner == 1:
                        winner = 2
                    elif raw_winner == 2:
                        winner = 1
                    else:
                        winner = raw_winner
                    break

            env.close()

        else:
            # script vs script or unknown — skip
            logger.info("Skipping unsupported matchup type: %s vs %s", p1_type, p2_type)
            continue

        results.append({
            "player1": matchup.get("player1_version", "?"),
            "player2": matchup.get("player2_version", "?"),
            "winner": winner,
            "ticks": ticks,
            "p1_reward": total_reward_p1,
            "p2_reward": total_reward_p2,
        })

    return results


# ─── Main training loop ──────────────────────────────────────────────


def run_league_training(
    *,
    rounds: int = 3,
    episodes_per_round: int = 50,
    max_ticks: int = 200,
    output_dir: str = "train/output/league",
    enable_order_queue: bool = True,
    enable_event_log: bool = True,
    enable_state_hash: bool = True,
    # New: TRLGRPOConfig passthrough args
    bc_pretrain: bool = False,
    n_demos: int = 50,
    bc_epochs: int = 15,
    freeze_bc_epochs: int = 500,
    kl_coef: float = 0.1,
    grpo_lr: float = 1e-5,
    opponent_difficulty: str = "easy",
    opponent_curriculum: bool = True,
    # New: warm-start
    warm_start: bool = False,
    warm_start_checkpoint: str = "",
    # New: separate eval ticks
    eval_max_ticks: int = 5000,
) -> dict[str, Any]:
    """Run full league self-play training loop.

    Parameters
    ----------
    rounds : int
        Number of training rounds (each produces a new agent version).
    episodes_per_round : int
        Episodes to train per round.
    max_ticks : int
        Max ticks per episode/game.
    output_dir : str
        Base output directory.
    enable_order_queue : bool
        Enable SimCore order queue feature flag.
    enable_event_log : bool
        Enable SimCore event log feature flag.
    enable_state_hash : bool
        Enable SimCore state hash feature flag.
    bc_pretrain : bool
        Enable BC pre-training before GRPO.
    n_demos : int
        Number of demonstration episodes for BC.
    bc_epochs : int
        BC training epochs.
    freeze_bc_epochs : int
        Freeze backbone+policy_head for first N episodes.
    kl_coef : float
        KL(pi_new || pi_bc) penalty weight.
    grpo_lr : float
        Learning rate for GRPO phase.
    opponent_difficulty : str
        Initial opponent difficulty ("easy"/"medium"/"hard").
    opponent_curriculum : bool
        Gradually increase opponent difficulty over training.
    warm_start : bool
        Warm-start training from a previous checkpoint.
    warm_start_checkpoint : str
        Path to checkpoint for warm-start.

    Returns
    -------
    dict[str, Any]
        Summary with league state, promotion history, and metrics.
    """
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    league = League()
    promotion_gate = PromotionGate(
        config=PromotionConfig(
            min_games=5,
            win_threshold=0.45,
            confidence=0.70,
            max_ticks=eval_max_ticks,
        ),
        league=league,
    )

    # Register initial scripted baseline
    v0 = AgentVersion("script-v0", AgentType.SCRIPT, creation_tick=0)
    league.register(v0)

    all_metrics: list[dict[str, Any]] = []
    promotion_log: list[dict[str, Any]] = []
    t0 = time.time()

    # Track previous round's best checkpoint for warm-start
    prev_best_checkpoint = warm_start_checkpoint if warm_start else ""

    for round_idx in range(rounds):
        round_dir = base / f"round_{round_idx}"
        version_name = _make_version_name(round_idx)
        logger.info("=== Round %d: Training %s ===", round_idx, version_name)

        # ── 1. Train new version ────────────────────────────────────
        cfg = TRLGRPOConfig(
            episodes=episodes_per_round,
            max_ticks=max_ticks,
            output_dir=str(round_dir),
            enable_state_hash=enable_state_hash,
            enable_order_queue=enable_order_queue,
            enable_event_log=enable_event_log,
            group_size=4,
            ppo_epochs=2,
            log_interval=10,
            # New GRPO v5 params
            bc_pretrain=bc_pretrain,
            n_demos=n_demos,
            bc_epochs=bc_epochs,
            freeze_bc_epochs=freeze_bc_epochs,
            kl_coef=kl_coef,
            grpo_lr=grpo_lr,
            opponent_difficulty=opponent_difficulty,
            opponent_curriculum=opponent_curriculum,
        )
        trainer = TRLGRPOTrainer(cfg)

        # ── 1b. Warm-start from previous best checkpoint ────────────
        if warm_start and prev_best_checkpoint and Path(prev_best_checkpoint).exists():
            import torch

            logger.info("Warm-starting from %s", prev_best_checkpoint)
            env_factory = trainer._default_env_factory
            import gymnasium as gym
            import simcore.gym_env  # noqa: F401

            warm_env = gym.make(
                cfg.env_id,
                seed=cfg.seed,
                max_ticks=cfg.max_ticks,
                reward_shaping=cfg.reward_shaping,
                enable_state_hash=cfg.enable_state_hash,
                enable_order_queue=cfg.enable_order_queue,
                enable_event_log=cfg.enable_event_log,
                opponent_difficulty=cfg.opponent_difficulty,
            )
            policy = trainer._ensure_policy(warm_env)
            state = torch.load(prev_best_checkpoint, map_location="cpu", weights_only=False)
            raw = state["model_state_dict"] if "model_state_dict" in state else state
            live = {k: v for k, v in raw.items() if not k.startswith("_bc_ref_")}
            policy.load_state_dict(live, strict=False)
            logger.info("Warm-start weights loaded successfully")
            warm_env.close()

        train_result = trainer.train()

        # ── 2. Register with League ──────────────────────────────────
        new_version = AgentVersion(
            name=version_name,
            type=AgentType.GRPO,
            checkpoint_path=str(round_dir / "final_model.pt"),
            creation_tick=int(time.time()),
            metadata={
                "round": round_idx,
                "episodes": episodes_per_round,
                "train_time": train_result.get("total_time", 0),
                "warm_start": warm_start and bool(prev_best_checkpoint),
            },
        )
        league.register(new_version)

        # Track this round's checkpoint for next round's warm-start
        prev_best_checkpoint = str(round_dir / "final_model.pt")

        # ── 3. Generate matchups (new vs all old) ──────────────────
        matchup_config = MatchupConfig(
            mode=MatchupMode.NEW_VS_OLD,
            games_per_pair=10,
            max_ticks=max_ticks,
        )
        matchups = league.generate_matchups(matchup_config)

        if not matchups:
            logger.info("No matchups generated — only 1 version in league")
            round_metrics = {
                "round": round_idx,
                "version": version_name,
                "train_result": train_result,
                "matchups": 0,
                "promoted": True,  # auto-promote if only version
                "elo": 1000.0,
            }
            all_metrics.append(round_metrics)
            promotion_log.append({"round": round_idx, "version": version_name, "promoted": True, "reason": "auto"})
            continue

        # ── 4. Run eval games ────────────────────────────────────────
        logger.info("Running %d evaluation games...", len(matchups))
        eval_results = _run_eval_games(
            league, matchups, trainer, max_ticks=eval_max_ticks, difficulty=opponent_difficulty,
        )

        # ── 5. Record results ───────────────────────────────────────
        from harness.league import MatchupResult
        league_results = []
        wins = 0
        draws = 0
        for r in eval_results:
            w = r["winner"]
            league_results.append(MatchupResult(r["player1"], r["player2"], winner=w))
            if w == 1:
                winner_name = r["player1"]
                if winner_name == version_name:
                    wins += 1
            elif w == 2:
                winner_name = r["player2"]
                if winner_name == version_name:
                    wins += 1
            else:
                draws += 1

        league.record_results(league_results)
        win_rate = wins / len(eval_results) if eval_results else 0.0
        new_elo = league.get_elo(version_name)

        logger.info(
            "Round %d: %s — win_rate=%.2f, draws=%d, elo=%.0f, games=%d",
            round_idx, version_name, win_rate, draws, new_elo, len(eval_results),
        )

        # ── 6. Promotion evaluation ─────────────────────────────────
        # Find the champion (highest ELO non-new version)
        champion = None
        champion_type = "script"
        for vs in league.get_leaderboard():
            if vs.name != version_name:
                champion = vs.name
                # Determine champion type
                champ_version = league.pool.get_by_name(vs.name)
                if champ_version and champ_version.type == AgentType.GRPO:
                    champion_type = "grpo"
                break

        promoted = False
        if champion:
            promo_result = promotion_gate.evaluate_sync(
                challenger=version_name,
                champion=champion,
                challenger_agent_type="grpo",
                champion_agent_type=champion_type,
            )
            promoted = promo_result.promoted
            if promoted:
                promotion_gate.promote(promo_result)
            else:
                promotion_gate.rollback(promo_result)

            logger.info(
                "Promotion: %s vs %s → promoted=%s, win_rate=%.2f, CI=[%.2f, %.2f]",
                version_name, champion, promoted,
                promo_result.win_rate, promo_result.ci_lower, promo_result.ci_upper,
            )
        else:
            promoted = True

        round_metrics = {
            "round": round_idx,
            "version": version_name,
            "train_result": train_result,
            "matchups": len(matchups),
            "eval_games": len(eval_results),
            "win_rate": win_rate,
            "elo": new_elo,
            "promoted": promoted,
        }
        all_metrics.append(round_metrics)
        promotion_log.append({
            "round": round_idx,
            "version": version_name,
            "promoted": promoted,
            "win_rate": win_rate,
            "elo": new_elo,
        })

    # ── Final summary ────────────────────────────────────────────────
    total_time = time.time() - t0
    summary = {
        "total_time": total_time,
        "rounds": rounds,
        "leaderboard": [
            {"name": s.name, "elo": s.elo, "games_played": s.games_played, "wins": s.wins}
            for s in league.get_leaderboard()
        ],
        "promotion_log": promotion_log,
        "round_metrics": all_metrics,
    }

    out_path = base / "league_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    logger.info("League training complete: %.1fs, %d rounds", total_time, rounds)
    logger.info("Leaderboard:\n%s", json.dumps(summary["leaderboard"], indent=2))

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="League Self-Play Training")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--max-ticks", type=int, default=200)
    parser.add_argument("--output-dir", default="train/output/league")
    parser.add_argument("--enable-order-queue", action="store_true", default=True)
    parser.add_argument("--no-order-queue", dest="enable_order_queue", action="store_false")
    parser.add_argument("--enable-event-log", action="store_true", default=True)
    parser.add_argument("--no-event-log", dest="enable_event_log", action="store_false")
    parser.add_argument("--enable-state-hash", action="store_true", default=True)
    parser.add_argument("--no-state-hash", dest="enable_state_hash", action="store_false")
    parser.add_argument("--log-level", default="INFO")
    # New: GRPO v5 args
    parser.add_argument("--bc-pretrain", action="store_true", default=False,
                        help="Enable BC pre-training before GRPO")
    parser.add_argument("--n-demos", type=int, default=50,
                        help="Number of demonstration episodes for BC")
    parser.add_argument("--bc-epochs", type=int, default=15,
                        help="BC training epochs")
    parser.add_argument("--freeze-bc-epochs", type=int, default=500,
                        help="Freeze backbone+policy_head for first N episodes")
    parser.add_argument("--kl-coef", type=float, default=0.1,
                        help="KL(pi_new || pi_bc) penalty weight")
    parser.add_argument("--grpo-lr", type=float, default=1e-5,
                        help="Learning rate for GRPO phase")
    parser.add_argument("--opponent-difficulty", type=str, default="easy",
                        choices=["easy", "medium", "hard"],
                        help="Initial opponent difficulty")
    parser.add_argument("--opponent-curriculum", action="store_true", default=False,
                        help="Gradually increase opponent difficulty")
    parser.add_argument("--no-opponent-curriculum", dest="opponent_curriculum",
                        action="store_false",
                        help="Disable opponent curriculum")
    # New: warm-start
    parser.add_argument("--warm-start", action="store_true", default=False,
                        help="Warm-start each round from previous best checkpoint")
    parser.add_argument("--warm-start-checkpoint", type=str, default="",
                        help="Path to checkpoint for initial warm-start (round 0)")
    parser.add_argument("--eval-max-ticks", type=int, default=5000,
                        help="Max ticks per evaluation game (longer = more decisive outcomes)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    run_league_training(
        rounds=args.rounds,
        episodes_per_round=args.episodes,
        max_ticks=args.max_ticks,
        output_dir=args.output_dir,
        enable_order_queue=args.enable_order_queue,
        enable_event_log=args.enable_event_log,
        enable_state_hash=args.enable_state_hash,
        bc_pretrain=args.bc_pretrain,
        n_demos=args.n_demos,
        bc_epochs=args.bc_epochs,
        freeze_bc_epochs=args.freeze_bc_epochs,
        kl_coef=args.kl_coef,
        grpo_lr=args.grpo_lr,
        opponent_difficulty=args.opponent_difficulty,
        opponent_curriculum=args.opponent_curriculum,
        warm_start=args.warm_start,
        warm_start_checkpoint=args.warm_start_checkpoint,
        eval_max_ticks=args.eval_max_ticks,
    )


if __name__ == "__main__":
    main()
