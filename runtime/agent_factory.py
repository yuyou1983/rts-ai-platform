"""Agent factory — creates the best available AI agent for a given player.

Runtime (L2) may import from both simcore (L1) and agents (L2).
This module centralises the CoordinatorAgent → ScriptAI fallback chain
so that simcore no longer needs to import from agents directly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_ai_agent(player_id: int, *, difficulty: str = "medium"):
    """Return the best available AI agent for *player_id*.

    Tries CoordinatorAgent first (multi-agent M1 architecture).
    Falls back to ScriptAI (rule-based baseline) on ImportError.
    """
    try:
        from agents.coordinator import CoordinatorAgent
        logger.debug("Using CoordinatorAgent for player %d (difficulty=%s)", player_id, difficulty)
        return CoordinatorAgent(player_id=player_id, difficulty=difficulty)
    except (ImportError, TypeError):
        from agents.script_ai import ScriptAI
        logger.debug("CoordinatorAgent unavailable, using ScriptAI for player %d (difficulty=%s)", player_id, difficulty)
        return ScriptAI(player_id=player_id, difficulty=difficulty)