"""Gym AI injection — adds ScriptAI commands for player 2 in single-player mode.

Moved from simcore/gym_env.py so that simcore (L1) no longer imports
from agents (L2).  The ``inject_ai_commands`` function merges AI
commands into the human-player command list when running in
single-player mode.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def inject_ai_commands(
    engine: Any,
    commands: list[dict],
    two_player: bool,
    agent_factory: Callable[[int], Any],
) -> list[dict]:
    """Return *commands* with AI commands for player 2 appended (when not two-player).

    Parameters
    ----------
    engine:
        SimCore engine instance (must expose ``state.get_observations()``).
    commands:
        Existing command list (typically from the human player / RL policy).
    two_player:
        If ``True``, both sides are human-controlled → no AI injection.
    agent_factory:
        Callable ``(player_id: int) -> Any`` that returns an AI agent
        with a ``decide(obs)`` interface.
    """
    all_commands = list(commands)

    if not two_player and engine.state is not None:
        ai = agent_factory(player_id=2)
        obs = engine.state.get_observations()
        obs_p2 = obs[1] if len(obs) > 1 else {}
        ai_result = ai.decide(obs_p2)
        ai_cmds = ai_result.get("commands", []) if isinstance(ai_result, dict) else []
        all_commands.extend(ai_cmds)

    return all_commands