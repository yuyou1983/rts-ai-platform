"""RTS AgentHub — M1 three-core architecture."""
from agents.combat import CombatAgent
from agents.coordinator import CoordinatorAgent
from agents.economy import EconomyAgent
from agents.script_ai import ScriptAI
from agents.sub_agents import ScoutAgent

__all__ = ["ScriptAI", "CoordinatorAgent", "EconomyAgent", "CombatAgent", "ScoutAgent"]