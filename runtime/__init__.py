"""Runtime — L2 orchestration layer between SimCore (L1) and Agents (L2).

This package centralises AI agent creation and lifecycle so that
simcore never needs to import from agents directly, preserving the
layer invariant:  SimCore(L1) ❌→ Agents(L2).

Public API
----------
create_ai_agent(player_id)
    Factory that tries CoordinatorAgent, falls back to ScriptAI.

RuntimeAutoStepper
    Drives a SimCore engine tick loop with AI agents.

inject_ai_commands(engine, commands, two_player, agent_factory)
    Merges AI commands for P2 in single-player gym environments.
"""
from runtime.agent_factory import create_ai_agent
from runtime.auto_step import RuntimeAutoStepper
from runtime.gym_ai import inject_ai_commands

__all__ = [
    "create_ai_agent",
    "RuntimeAutoStepper",
    "inject_ai_commands",
]