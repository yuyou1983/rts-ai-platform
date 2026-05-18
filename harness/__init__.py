"""Harness — match scheduling + concurrent simulation pool + league self-play + promotion gate."""
from harness.pool import MatchConfig, MatchResult, MatchScheduler, SimulationPool
from harness.promotion import PromotionConfig, PromotionGate, PromotionResult, wilson_ci
from harness.league import (
    AgentType,
    AgentVersion,
    League,
    LeaguePool,
    MatchupConfig,
    MatchupMode,
    MatchupResult,
    VersionStats,
    update_elo,
)

__all__ = [
    # pool
    "MatchConfig",
    "MatchResult",
    "MatchScheduler",
    "SimulationPool",
    # promotion
    "PromotionConfig",
    "PromotionGate",
    "PromotionResult",
    "wilson_ci",
    # league
    "AgentType",
    "AgentVersion",
    "League",
    "LeaguePool",
    "MatchupConfig",
    "MatchupMode",
    "MatchupResult",
    "VersionStats",
    "update_elo",
]