"""League self-play system — version pool + ELO ranking + match configuration.

Core components:
  AgentVersion   — dataclass for a versioned agent (script / coordinator / grpo)
  VersionStats   — per-version ELO, wins, losses tracking
  LeaguePool     — manages the pool of agent versions
  MatchupConfig  — self-play matchup configuration (mirror / new-vs-old / cross-type)
  League         — top-level orchestrator combining pool, stats, and matchup generation

Designed to integrate with harness.scheduler.py LeagueScheduler and
harness.pool.py SimulationPool for running self-play tournaments.

Pure Python — no external AI/ML dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─── Enums ────────────────────────────────────────────────────────────────────


class AgentType(str, Enum):
    """Supported agent types in the league."""

    SCRIPT = "script"
    COORDINATOR = "coordinator"
    GRPO = "grpo"


class MatchupMode(str, Enum):
    """Self-play matchup modes.

    MIRROR     — same version vs itself (detect policy degeneration / collapse)
    NEW_VS_OLD — newest version vs best predecessor (detect improvement)
    CROSS_TYPE — different agent types face off (e.g. script vs coordinator)
    """

    MIRROR = "mirror"
    NEW_VS_OLD = "new_vs_old"
    CROSS_TYPE = "cross_type"


# ─── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class AgentVersion:
    """A versioned agent entry in the league pool.

    Attributes:
        name:            Human-readable version identifier (e.g. "script-v3")
        type:            Agent type — script / coordinator / grpo
        checkpoint_path: Path to model checkpoint or script module
        creation_tick:   Monotonic creation timestamp (game-tick or wall-clock)
        metadata:        Optional extra info (hyperparams, training config, etc.)
    """

    name: str
    type: AgentType
    checkpoint_path: str = ""
    creation_tick: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Coerce plain strings into AgentType enum
        if isinstance(self.type, str):
            self.type = AgentType(self.type)

    @property
    def sort_key(self) -> tuple[int, str]:
        """Sort by creation_tick then name for deterministic ordering."""
        return (self.creation_tick, self.name)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AgentVersion):
            return NotImplemented
        return self.name == other.name


@dataclass
class VersionStats:
    """Per-version ELO rating and win/loss record."""

    name: str
    elo: float = 1000.0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    games_played: int = 0

    @property
    def win_rate(self) -> float:
        if self.games_played == 0:
            return 0.0
        return self.wins / self.games_played

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "elo": round(self.elo, 1),
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "games_played": self.games_played,
            "win_rate": round(self.win_rate, 4),
        }


@dataclass
class MatchupResult:
    """Record of a single league matchup outcome.

    Attributes:
        player1:  Name of player 1's agent version
        player2:  Name of player 2's agent version
        winner:   1 or 2 (0 for draw)
        ticks:    Game ticks elapsed
        mode:     The matchup mode that produced this game
    """

    player1: str
    player2: str
    winner: int
    ticks: int = 0
    mode: MatchupMode = MatchupMode.MIRROR

    def __post_init__(self) -> None:
        if isinstance(self.mode, str):
            self.mode = MatchupMode(self.mode)


@dataclass
class MatchupConfig:
    """Configuration for generating league matchups.

    Attributes:
        mode:            Matchup mode (mirror / new_vs_old / cross_type)
        games_per_pair:  Number of games per unique pair
        map_seeds:       List of map seeds to cycle through
        max_ticks:       Tick limit per match
        mirror_enabled:  Whether mirror matchups are allowed
        mirror_min_games: Minimum mirror games before a version can be promoted
    """

    mode: MatchupMode = MatchupMode.NEW_VS_OLD
    games_per_pair: int = 5
    map_seeds: list[int] = field(default_factory=lambda: [42, 43, 44, 45, 46])
    max_ticks: int = 10000
    mirror_enabled: bool = True
    mirror_min_games: int = 3

    def __post_init__(self) -> None:
        if isinstance(self.mode, str):
            self.mode = MatchupMode(self.mode)


# ─── ELO rating engine ────────────────────────────────────────────────────────

# Standard ELO constants
_ELO_K_FACTOR = 32.0        # Sensitivity of rating changes
_ELO_BASE = 10.0            # Logarithm base for expected score
_ELO_DIVISOR = 400.0        # Rating difference scaling


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Compute expected score for player A given both ratings."""
    return 1.0 / (1.0 + _ELO_BASE ** ((rating_b - rating_a) / _ELO_DIVISOR))


def update_elo(
    stats_a: VersionStats,
    stats_b: VersionStats,
    winner: int,
    k_factor: float = _ELO_K_FACTOR,
) -> None:
    """Update ELO ratings for two versions after a match.

    Args:
        stats_a:  VersionStats for player 1
        stats_b:  VersionStats for player 2
        winner:   1 = a wins, 2 = b wins, 0 = draw
        k_factor: ELO K-factor (default 32)
    """
    ea = _expected_score(stats_a.elo, stats_b.elo)
    eb = 1.0 - ea

    if winner == 1:
        sa, sb = 1.0, 0.0
        stats_a.wins += 1
        stats_b.losses += 1
    elif winner == 2:
        sa, sb = 0.0, 1.0
        stats_a.losses += 1
        stats_b.wins += 1
    else:
        sa, sb = 0.5, 0.5
        stats_a.draws += 1
        stats_b.draws += 1

    stats_a.elo += k_factor * (sa - ea)
    stats_b.elo += k_factor * (sb - eb)
    stats_a.games_played += 1
    stats_b.games_played += 1


# ─── LeaguePool ────────────────────────────────────────────────────────────────


class LeaguePool:
    """Manages the pool of agent versions.

    Provides:
    - add_version()    — register a new agent version
    - get_all_versions() — return all versions sorted by creation_tick
    - get_latest()     — return the most recently created version
    - get_by_name()    — look up a version by its unique name
    - get_by_type()    — filter versions by agent type
    - remove_version() — deregister a version
    """

    def __init__(self) -> None:
        self._versions: dict[str, AgentVersion] = {}

    def add_version(self, version: AgentVersion) -> None:
        """Register a new agent version. Raises ValueError on duplicate name."""
        if version.name in self._versions:
            raise ValueError(
                f"Version '{version.name}' already exists in the pool"
            )
        self._versions[version.name] = version

    def remove_version(self, name: str) -> AgentVersion:
        """Remove and return a version by name. Raises KeyError if not found."""
        if name not in self._versions:
            raise KeyError(f"Version '{name}' not found in the pool")
        return self._versions.pop(name)

    def get_all_versions(self) -> list[AgentVersion]:
        """Return all versions sorted by creation_tick (oldest first)."""
        return sorted(self._versions.values(), key=lambda v: v.sort_key)

    def get_latest(self) -> AgentVersion | None:
        """Return the most recently created version, or None if pool is empty."""
        versions = self.get_all_versions()
        return versions[-1] if versions else None

    def get_by_name(self, name: str) -> AgentVersion | None:
        """Look up a version by name. Returns None if not found."""
        return self._versions.get(name)

    def get_by_type(self, agent_type: AgentType) -> list[AgentVersion]:
        """Return all versions of a given agent type, sorted by creation_tick."""
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type)
        return [
            v
            for v in self.get_all_versions()
            if v.type == agent_type
        ]

    def __len__(self) -> int:
        return len(self._versions)

    def __contains__(self, name: str) -> bool:
        return name in self._versions

    def __iter__(self):
        return iter(self.get_all_versions())


# ─── League (top-level orchestrator) ───────────────────────────────────────────


class League:
    """Self-play league orchestrator.

    Combines a version pool, ELO stats tracking, and matchup generation
    into a single coherent system.

    Typical usage::

        league = League()
        v1 = AgentVersion("script-v1", AgentType.SCRIPT, creation_tick=0)
        v2 = AgentVersion("coord-v1", AgentType.COORDINATOR, creation_tick=100)
        league.register(v1)
        league.register(v2)

        # Generate self-play matchups
        matchups = league.generate_matchups(MatchupConfig(mode=MatchupMode.NEW_VS_OLD))

        # After running games, record results to update ELO
        league.record_result(MatchupResult("coord-v1", "script-v1", winner=1))
    """

    def __init__(self) -> None:
        self.pool: LeaguePool = LeaguePool()
        self._stats: dict[str, VersionStats] = {}
        self._history: list[MatchupResult] = []

    # ── Version management ────────────────────────────────────────────────

    def register(self, version: AgentVersion) -> None:
        """Register a new agent version in the league pool.

        Also initializes its stats at the default ELO (1000).
        Raises ValueError if the version name already exists.
        """
        self.pool.add_version(version)
        self._stats[version.name] = VersionStats(name=version.name)

    def deregister(self, name: str) -> AgentVersion:
        """Remove a version from the pool. Stats are preserved for history."""
        return self.pool.remove_version(name)

    # ── Stats access ───────────────────────────────────────────────────────

    def get_stats(self, name: str) -> VersionStats:
        """Return stats for a version. Raises KeyError if unknown."""
        if name not in self._stats:
            raise KeyError(f"No stats for version '{name}'")
        return self._stats[name]

    def get_leaderboard(self) -> list[VersionStats]:
        """Return all version stats sorted by ELO descending."""
        return sorted(self._stats.values(), key=lambda s: s.elo, reverse=True)

    def get_elo(self, name: str) -> float:
        """Convenience: return ELO for a version (0.0 if unknown)."""
        stats = self._stats.get(name)
        return stats.elo if stats else 0.0

    # ── Result recording ───────────────────────────────────────────────────

    def record_result(self, result: MatchupResult) -> None:
        """Record a matchup result and update ELO ratings.

        Both versions must have been previously registered.
        """
        stats_p1 = self._stats.get(result.player1)
        stats_p2 = self._stats.get(result.player2)

        if stats_p1 is None:
            raise KeyError(f"No stats for version '{result.player1}'")
        if stats_p2 is None:
            raise KeyError(f"No stats for version '{result.player2}'")

        update_elo(stats_p1, stats_p2, result.winner)
        self._history.append(result)

    def record_results(self, results: list[MatchupResult]) -> None:
        """Record multiple matchup results."""
        for r in results:
            self.record_result(r)

    # ── Matchup generation ─────────────────────────────────────────────────

    def generate_matchups(
        self,
        config: MatchupConfig | None = None,
    ) -> list[dict[str, Any]]:
        """Generate match configurations based on the league state and mode.

        Returns a list of dicts compatible with harness.pool.MatchConfig::

            {
                "player1_type": "coordinator",
                "player1_version": "coord-v2",
                "player2_type": "coordinator",
                "player2_version": "coord-v1",
                "map_seed": 42,
                "max_ticks": 10000,
                "mode": "new_vs_old",
            }

        These can be fed into a LeagueScheduler to create MatchConfig objects.
        """
        if config is None:
            config = MatchupConfig()

        matchups: list[dict[str, Any]] = []
        seed_idx = 0
        seeds = config.map_seeds

        if config.mode == MatchupMode.MIRROR:
            matchups.extend(
                self._gen_mirror_matchups(config, seeds, seed_idx)
            )
        elif config.mode == MatchupMode.NEW_VS_OLD:
            matchups.extend(
                self._gen_new_vs_old_matchups(config, seeds, seed_idx)
            )
        elif config.mode == MatchupMode.CROSS_TYPE:
            matchups.extend(
                self._gen_cross_type_matchups(config, seeds, seed_idx)
            )

        return matchups

    def _gen_mirror_matchups(
        self,
        config: MatchupConfig,
        seeds: list[int],
        seed_idx: int,
    ) -> list[dict[str, Any]]:
        """Mirror: each version plays against itself."""
        if not config.mirror_enabled:
            return []

        matchups: list[dict[str, Any]] = []
        for version in self.pool.get_all_versions():
            for _ in range(config.games_per_pair):
                matchups.append({
                    "player1_type": version.type.value,
                    "player1_version": version.name,
                    "player2_type": version.type.value,
                    "player2_version": version.name,
                    "map_seed": seeds[seed_idx % len(seeds)],
                    "max_ticks": config.max_ticks,
                    "mode": MatchupMode.MIRROR.value,
                })
                seed_idx += 1
        return matchups

    def _gen_new_vs_old_matchups(
        self,
        config: MatchupConfig,
        seeds: list[int],
        seed_idx: int,
    ) -> list[dict[str, Any]]:
        """New-vs-old: each version faces its best predecessor (by ELO)."""
        matchups: list[dict[str, Any]] = []
        versions = self.pool.get_all_versions()

        for i, version in enumerate(versions):
            # Find predecessors (older versions of same type)
            predecessors = [
                v for v in versions[:i] if v.type == version.type
            ]
            if not predecessors:
                continue

            # Pick the best predecessor by ELO
            best_pred = max(
                predecessors,
                key=lambda v: self.get_elo(v.name),
            )

            for _ in range(config.games_per_pair):
                matchups.append({
                    "player1_type": version.type.value,
                    "player1_version": version.name,
                    "player2_type": best_pred.type.value,
                    "player2_version": best_pred.name,
                    "map_seed": seeds[seed_idx % len(seeds)],
                    "max_ticks": config.max_ticks,
                    "mode": MatchupMode.NEW_VS_OLD.value,
                })
                seed_idx += 1

        return matchups

    def _gen_cross_type_matchups(
        self,
        config: MatchupConfig,
        seeds: list[int],
        seed_idx: int,
    ) -> list[dict[str, Any]]:
        """Cross-type: versions of different agent types face each other."""
        matchups: list[dict[str, Any]] = []
        versions = self.pool.get_all_versions()

        for i, v1 in enumerate(versions):
            for v2 in versions[i + 1:]:
                if v1.type == v2.type:
                    continue
                for _ in range(config.games_per_pair):
                    matchups.append({
                        "player1_type": v1.type.value,
                        "player1_version": v1.name,
                        "player2_type": v2.type.value,
                        "player2_version": v2.name,
                        "map_seed": seeds[seed_idx % len(seeds)],
                        "max_ticks": config.max_ticks,
                        "mode": MatchupMode.CROSS_TYPE.value,
                    })
                    seed_idx += 1

        return matchups

    # ── Promotion gate ────────────────────────────────────────────────────

    def can_promote(self, name: str, min_elo_gain: float = 0.0,
                    min_mirror_games: int = 3) -> bool:
        """Check if a version is eligible for promotion.

        A version can be promoted when:
        1. It has played at least min_mirror_games mirror matches
           (policy degeneration check).
        2. Its ELO is higher than the baseline by at least min_elo_gain.

        The baseline is the ELO of the best predecessor of the same type,
        or 1000 (default) if there are no predecessors.
        """
        stats = self._stats.get(name)
        version = self.pool.get_by_name(name)
        if stats is None or version is None:
            return False

        # Check mirror game count
        mirror_games = sum(
            1 for h in self._history
            if h.player1 == name and h.player2 == name
            and h.mode == MatchupMode.MIRROR
        )
        if mirror_games < min_mirror_games:
            return False

        # Find best predecessor's ELO as baseline
        all_versions = self.pool.get_all_versions()
        predecessors = [
            v for v in all_versions
            if v.type == version.type and v.creation_tick < version.creation_tick
        ]
        if predecessors:
            baseline = max(self.get_elo(v.name) for v in predecessors)
        else:
            baseline = 1000.0

        return stats.elo >= baseline + min_elo_gain

    # ── History & reporting ────────────────────────────────────────────────

    @property
    def history(self) -> list[MatchupResult]:
        """Return the full matchup result history."""
        return list(self._history)

    @property
    def total_games(self) -> int:
        return len(self._history)

    def format_leaderboard(self) -> str:
        """Format a human-readable leaderboard table."""
        board = self.get_leaderboard()
        if not board:
            return "League is empty — no versions registered."

        lines = [
            "=" * 72,
            "  RTS AI Platform — League Leaderboard",
            "=" * 72,
            f"  {'Rank':<5} {'Version':<20} {'ELO':>7} {'W':>5} {'L':>5} "
            f"{'D':>5} {'GP':>5} {'Win%':>7}",
            "-" * 72,
        ]

        for rank, stats in enumerate(board, 1):
            lines.append(
                f"  {rank:<5} {stats.name:<20} {stats.elo:>7.1f} "
                f"{stats.wins:>5} {stats.losses:>5} {stats.draws:>5} "
                f"{stats.games_played:>5} {stats.win_rate:>6.1%}"
            )

        lines.append("=" * 72)
        return "\n".join(lines)

    def summary(self) -> dict[str, Any]:
        """Return a machine-readable summary of the league state."""
        return {
            "versions": len(self.pool),
            "total_games": self.total_games,
            "leaderboard": [s.to_dict() for s in self.get_leaderboard()],
        }