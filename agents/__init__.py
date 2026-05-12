"""RTS AgentHub — M1 three-core architecture."""
from agents.combat import CombatAgent
from agents.coordinator import CoordinatorAgent
from agents.economy import EconomyAgent
from agents.script_ai import ScriptAI
from agents.sub_agents import ScoutAgent
from agents.race_ai_base import RaceAIBase
from agents.terran_ai import TerranAI
from agents.zerg_ai import ZergAI
from agents.protoss_ai import ProtossAI

__all__ = [
    "ScriptAI", "CoordinatorAgent", "EconomyAgent", "CombatAgent", "ScoutAgent",
    "RaceAIBase", "TerranAI", "ZergAI", "ProtossAI",
]