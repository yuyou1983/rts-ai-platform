"""simcore.agents — simple rule-based AI baseline agents."""
from simcore.agents.greedy import GreedyGatherer
from simcore.agents.passive import PassiveAI
from simcore.agents.rush import RushAI

__all__ = ["PassiveAI", "GreedyGatherer", "RushAI"]
