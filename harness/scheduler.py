"""League Scheduler — version-pool management, matchup generation, and
concurrent league execution for RTS-AI-Platform.

Architecture:
  AgentVersion   — named version entry with optional metadata
  LeagueScheduler— manages an agent version pool, generates matchup schedules
                    (round_robin / random_sample / focused), and drives
                    concurrent execution via SimulationPool
  LeagueStats    — aggregated per-version and head-to-head statistics

Usage::

    scheduler = LeagueScheduler(max_concurrent=8)
    scheduler.register("coordinator", "v0.3")
    scheduler.register("coordinator", "v0.4")
    scheduler.register("script",      "v1.0")
    await scheduler.run(mode="round_robin", repeats=2)
    print(scheduler.summary())
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from harness.pool import MatchConfig, MatchResult, MatchScheduler, SimulationPool

logger = logging.getLogger(__name__)


# ─── Data types ──────────────────────────────────────────────────────


class MatchMode(Enum):
    """Supported league matchup generation modes."""

    ROUND_ROBIN = "round_robin"      # full all-pairs permutation
    RANDOM_SAMPLE = "random_sample"  # random sampling of matchups
    FOCUSED = "focused"              # emphasis on newest versions


@dataclass
class AgentVersion:
    """A registered agent version in the league pool."""

    agent_type: str        # e.g. "coordinator", "script"
    version: str           # e.g. "v0.4", "2024-01-15"
    registered_at: float = 0.0   # monotonic timestamp of registration
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Unique identifier: agent_type@version."""
        return f"{self.agent_type}@{self.version}"

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AgentVersion):
            return NotImplemented
        return self.key == other.key


@dataclass
class VersionStats:
    """Per-version win/loss/draw statistics."""

    key: str = ""
    wins: int = 0
    losses: int = 0
    draws: int = 0
    total: int = 0
    ticks_sum: int = 0
    tps_sum: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total else 0.0

    @property
    def avg_ticks(self) -> float:
        return self.ticks_sum / self.total if self.total else 0.0

    @property
    def avg_tps(self) -> float:
        return self.tps_sum / self.total if self.total else 0.0


@dataclass
class LeagueStats:
    """Aggregate league statistics."""

    total_matches: int = 0
    completed: int = 0
    errors: int = 0
    wall_time: float = 0.0
    version_stats: dict[str, VersionStats] = field(default_factory=dict)
    # head-to-head matrix: (key1, key2) -> {"wins": n, "losses": m, "draws": d}
    h2h: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)


# ─── Matchup generators ──────────────────────────────────────────────


def _generate_round_robin(
    versions: list[AgentVersion],
    maps: list[int],
    repeats: int,
    max_ticks: int,
) -> list[MatchConfig]:
    """Full round-robin: every ordered pair plays on every map × repeats.

    Includes both (A vs B) and (B vs A) so positional asymmetry is covered.
    """
    configs: list[MatchConfig] = []
    for v1, v2 in itertools.permutations(versions, 2):
        for seed in maps:
            for r in range(repeats):
                configs.append(
                    MatchConfig(
                        map_seed=seed + r,
                        max_ticks=max_ticks,
                        player1_type=v1.agent_type,
                        player2_type=v2.agent_type,
                        player_races={1: "terran", 2: "terran"},
                    )
                )
    return configs


def _generate_random_sample(
    versions: list[AgentVersion],
    maps: list[int],
    repeats: int,
    max_ticks: int,
    sample_count: int,
    rng: random.Random,
) -> list[MatchConfig]:
    """Randomly sample matchups from the full round-robin set.

    If *sample_count* exceeds the full set size, the full set is returned.
    """
    full = _generate_round_robin(versions, maps, repeats, max_ticks)
    if sample_count >= len(full):
        return full
    return rng.sample(full, sample_count)


def _generate_focused(
    versions: list[AgentVersion],
    maps: list[int],
    repeats: int,
    max_ticks: int,
    focus_count: int,
) -> list[MatchConfig]:
    """Focused mode: every version plays the *focus_count* newest versions
    plus a round-robin among the newest versions themselves.

    The newest versions are determined by ``registered_at`` (latest first).
    This ensures the latest agent versions get the most matches while older
    versions are still tested against recent competition.
    """
    if not versions:
        return []

    sorted_versions = sorted(versions, key=lambda v: v.registered_at, reverse=True)
    newest = sorted_versions[:focus_count]
    older = sorted_versions[focus_count:]

    configs: list[MatchConfig] = []

    # 1) Round-robin among the newest versions (both directions)
    configs.extend(_generate_round_robin(newest, maps, repeats, max_ticks))

    # 2) Each older version plays against each newest version
    for old_v in older:
        for new_v in newest:
            for seed in maps:
                for r in range(repeats):
                    # old as P1, new as P2
                    configs.append(
                        MatchConfig(
                            map_seed=seed + r,
                            max_ticks=max_ticks,
                            player1_type=old_v.agent_type,
                            player2_type=new_v.agent_type,
                            player_races={1: "terran", 2: "terran"},
                        )
                    )
                    # new as P1, old as P2 (reverse)
                    configs.append(
                        MatchConfig(
                            map_seed=seed + r + 1000,  # offset seed for reverse
                            max_ticks=max_ticks,
                            player1_type=new_v.agent_type,
                            player2_type=old_v.agent_type,
                            player_races={1: "terran", 2: "terran"},
                        )
                    )

    return configs


# ─── LeagueScheduler ─────────────────────────────────────────────────


class LeagueScheduler:
    """Manages an agent version pool, generates matchup schedules, and
    runs a league tournament with concurrent match execution.

    Typical workflow::

        ls = LeagueScheduler(max_concurrent=8)
        ls.register("coordinator", "v0.3")
        ls.register("coordinator", "v0.4")
        ls.register("script", "v1.0")
        results = await ls.run(mode="round_robin", repeats=2)
        print(ls.summary())
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        maps: list[int] | None = None,
        max_ticks: int = 10000,
        seed: int = 42,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.maps = maps if maps is not None else [42, 137, 256, 999]
        self.max_ticks = max_ticks
        self._rng = random.Random(seed)

        # Version pool — keyed by AgentVersion.key
        self._versions: dict[str, AgentVersion] = {}
        # Registration order to resolve "newest" when timestamps tie
        self._registration_order: list[str] = []

        # Results from the last run
        self._last_results: list[MatchResult] = []
        self._last_configs: list[MatchConfig] = []
        self._last_stats: LeagueStats | None = None

    # ── Version pool management ──────────────────────────────────────

    def register(
        self,
        agent_type: str,
        version: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentVersion:
        """Register an agent version into the league pool.

        If the same (agent_type, version) already exists, its metadata is
        updated and the original registration timestamp is preserved.

        Returns:
            The registered :class:`AgentVersion`.
        """
        import time

        v = AgentVersion(
            agent_type=agent_type,
            version=version,
            registered_at=time.monotonic(),
            metadata=metadata or {},
        )
        if v.key not in self._versions:
            self._registration_order.append(v.key)
        else:
            # Preserve the earlier registration timestamp on re-register
            v.registered_at = self._versions[v.key].registered_at
            # But still allow metadata update
            v.metadata = {**self._versions[v.key].metadata, **(metadata or {})}

        self._versions[v.key] = v
        logger.info("Registered agent version: %s", v.key)
        return v

    def unregister(self, agent_type: str, version: str) -> bool:
        """Remove a version from the pool.  Returns ``True`` if found."""
        key = f"{agent_type}@{version}"
        if key in self._versions:
            del self._versions[key]
            self._registration_order = [
                k for k in self._registration_order if k != key
            ]
            logger.info("Unregistered agent version: %s", key)
            return True
        return False

    @property
    def versions(self) -> list[AgentVersion]:
        """All registered versions in registration order."""
        return [self._versions[k] for k in self._registration_order if k in self._versions]

    @property
    def version_keys(self) -> list[str]:
        return [v.key for v in self.versions]

    # ── Schedule generation ───────────────────────────────────────────

    def generate_schedule(
        self,
        mode: str | MatchMode = "round_robin",
        repeats: int = 1,
        sample_count: int = 50,
        focus_count: int = 3,
    ) -> list[MatchConfig]:
        """Generate matchup configurations according to *mode*.

        Args:
            mode: One of ``"round_robin"``, ``"random_sample"``,
                  ``"focused"`` (or the :class:`MatchMode` enum).
            repeats: Number of times each matchup is repeated per map.
            sample_count: For ``random_sample`` mode — max matchups to sample.
            focus_count: For ``focused`` mode — how many newest versions
                         to focus on.

        Returns:
            List of :class:`MatchConfig` instances ready for execution.
        """
        if isinstance(mode, str):
            mode = MatchMode(mode)

        versions = self.versions
        if len(versions) < 2:
            logger.warning("Need at least 2 versions for a league, got %d", len(versions))
            return []

        if mode is MatchMode.ROUND_ROBIN:
            configs = _generate_round_robin(versions, self.maps, repeats, self.max_ticks)
        elif mode is MatchMode.RANDOM_SAMPLE:
            configs = _generate_random_sample(
                versions, self.maps, repeats, self.max_ticks, sample_count, self._rng
            )
        elif mode is MatchMode.FOCUSED:
            configs = _generate_focused(
                versions, self.maps, repeats, self.max_ticks, focus_count
            )
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        logger.info(
            "Generated %d matchups (mode=%s, repeats=%d)",
            len(configs), mode.value, repeats,
        )
        return configs

    # ── League execution ──────────────────────────────────────────────

    async def run(
        self,
        mode: str | MatchMode = "round_robin",
        repeats: int = 1,
        sample_count: int = 50,
        focus_count: int = 3,
    ) -> list[MatchResult]:
        """Generate the schedule and run all matches concurrently.

        Returns:
            List of :class:`MatchResult` from all executed matches.
        """
        import time

        configs = self.generate_schedule(
            mode=mode,
            repeats=repeats,
            sample_count=sample_count,
            focus_count=focus_count,
        )
        self._last_configs = configs

        if not configs:
            logger.warning("No matches to run")
            self._last_results = []
            self._last_stats = LeagueStats()
            return []

        # Build a MatchScheduler from the generated configs and run
        match_scheduler = MatchScheduler()
        match_scheduler.add_custom(configs)

        pool = SimulationPool(max_concurrent=self.max_concurrent)
        t0 = time.monotonic()
        results = await pool.run_all(match_scheduler)
        wall_time = time.monotonic() - t0

        self._last_results = results
        self._last_stats = self._compute_stats(results, configs, wall_time)

        logger.info(
            "League complete: %d matches in %.1fs wall, %d errors",
            len(results), wall_time, self._last_stats.errors,
        )
        return results

    # ── Statistics ─────────────────────────────────────────────────────

    def _compute_stats(
        self,
        results: list[MatchResult],
        configs: list[MatchConfig],
        wall_time: float,
    ) -> LeagueStats:
        """Compute per-version and head-to-head statistics."""
        stats = LeagueStats(
            total_matches=len(results),
            completed=sum(1 for r in results if r.error is None),
            errors=sum(1 for r in results if r.error is not None),
            wall_time=wall_time,
        )

        # Build a lookup from match_id → config so we know which version
        # was on which side.
        config_map: dict[str, MatchConfig] = {
            c.match_id: c for c in configs
        }

        # Initialize version stats for all registered versions
        for v in self.versions:
            stats.version_stats[v.key] = VersionStats(key=v.key)

        for result in results:
            if result.error is not None:
                continue

            cfg = config_map.get(result.match_id)
            if cfg is None:
                # Fallback: try to find by player types
                continue

            # Determine version keys for each side.
            # Since MatchConfig stores agent_type (not version), we match
            # by agent_type. If multiple versions share the same type, we
            # pick the most recently registered one (best-effort heuristic).
            p1_key = self._resolve_version_key(cfg.player1_type)
            p2_key = self._resolve_version_key(cfg.player2_type)

            # Update version stats
            if p1_key:
                vs = stats.version_stats.setdefault(p1_key, VersionStats(key=p1_key))
                vs.total += 1
                vs.ticks_sum += result.ticks
                vs.tps_sum += result.tps
                if result.winner == 1:
                    vs.wins += 1
                elif result.winner == 2:
                    vs.losses += 1
                else:
                    vs.draws += 1

            if p2_key:
                vs = stats.version_stats.setdefault(p2_key, VersionStats(key=p2_key))
                vs.total += 1
                vs.ticks_sum += result.ticks
                vs.tps_sum += result.tps
                if result.winner == 2:
                    vs.wins += 1
                elif result.winner == 1:
                    vs.losses += 1
                else:
                    vs.draws += 1

            # Head-to-head
            if p1_key and p2_key:
                h2h_key = (p1_key, p2_key)
                h2h = stats.h2h.setdefault(h2h_key, {"wins": 0, "losses": 0, "draws": 0})
                if result.winner == 1:
                    h2h["wins"] += 1
                elif result.winner == 2:
                    h2h["losses"] += 1
                else:
                    h2h["draws"] += 1

        return stats

    def _resolve_version_key(self, agent_type: str) -> str | None:
        """Best-effort resolution of agent_type to a version key.

        When multiple versions share the same agent_type, returns the most
        recently registered one.
        """
        candidates = [v for v in self.versions if v.agent_type == agent_type]
        if not candidates:
            return None
        # Most recently registered
        return max(candidates, key=lambda v: v.registered_at).key

    @property
    def stats(self) -> LeagueStats | None:
        """Statistics from the last league run, or ``None``."""
        return self._last_stats

    @property
    def last_results(self) -> list[MatchResult]:
        """Raw results from the last league run."""
        return list(self._last_results)

    # ── Reporting ──────────────────────────────────────────────────────

    def summary(self) -> str:
        """Human-readable league summary string."""
        if self._last_stats is None:
            return "No league has been run yet."

        s = self._last_stats
        lines: list[str] = [
            "=" * 64,
            "  RTS AI Platform — League Summary",
            "=" * 64,
            "",
            f"  Total Matches:  {s.total_matches}",
            f"  Completed:      {s.completed}",
            f"  Errors:         {s.errors}",
            f"  Wall Time:      {s.wall_time:.1f}s",
            "",
            "  ── Per-Version Stats ──",
            "",
        ]

        # Sort by win rate descending
        ranked = sorted(
            s.version_stats.values(),
            key=lambda v: v.win_rate,
            reverse=True,
        )
        for i, vs in enumerate(ranked, 1):
            lines.append(
                f"  {i}. {vs.key:<30s}  "
                f"W {vs.wins:>3d}  L {vs.losses:>3d}  D {vs.draws:>3d}  "
                f"WinRate {vs.win_rate:>6.1%}  "
                f"AvgTicks {vs.avg_ticks:>6.0f}  "
                f"AvgTPS {vs.avg_tps:>6.0f}"
            )

        if s.h2h:
            lines.append("")
            lines.append("  ── Head-to-Head ──")
            lines.append("")
            for (k1, k2), h2h in sorted(s.h2h.items()):
                lines.append(
                    f"  {k1} vs {k2}:  "
                    f"W {h2h['wins']}  L {h2h['losses']}  D {h2h['draws']}"
                )

        lines.append("")
        lines.append("=" * 64)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize league results to a plain dict (JSON-friendly)."""
        if self._last_stats is None:
            return {"status": "not_run"}

        s = self._last_stats
        return {
            "total_matches": s.total_matches,
            "completed": s.completed,
            "errors": s.errors,
            "wall_time": s.wall_time,
            "version_stats": {
                k: {
                    "key": v.key,
                    "wins": v.wins,
                    "losses": v.losses,
                    "draws": v.draws,
                    "total": v.total,
                    "win_rate": v.win_rate,
                    "avg_ticks": v.avg_ticks,
                    "avg_tps": v.avg_tps,
                }
                for k, v in s.version_stats.items()
            },
            "head_to_head": {
                f"{k1} vs {k2}": v
                for (k1, k2), v in s.h2h.items()
            },
        }


# ─── CLI entry point ─────────────────────────────────────────────────


async def _cli_run(
    mode: str = "round_robin",
    repeats: int = 1,
    concurrent: int = 4,
    max_ticks: int = 10000,
    agents: list[tuple[str, str]] | None = None,
) -> None:
    """Convenience async runner for CLI usage."""
    ls = LeagueScheduler(max_concurrent=concurrent, max_ticks=max_ticks)
    if agents is None:
        # Default demo agents
        agents = [
            ("coordinator", "v0.3"),
            ("coordinator", "v0.4"),
            ("script", "v1.0"),
        ]
    for agent_type, version in agents:
        ls.register(agent_type, version)

    await ls.run(mode=mode, repeats=repeats)
    print(ls.summary())


def main() -> None:
    """CLI entry point for the league scheduler."""
    import argparse

    parser = argparse.ArgumentParser(
        description="RTS AI Platform — League Scheduler"
    )
    parser.add_argument(
        "--mode",
        choices=[m.value for m in MatchMode],
        default="round_robin",
        help="Matchup generation mode (default: round_robin)",
    )
    parser.add_argument("--repeats", type=int, default=1, help="Repeats per matchup")
    parser.add_argument("--concurrent", type=int, default=4, help="Max concurrent matches")
    parser.add_argument("--max-ticks", type=int, default=10000, help="Max ticks per match")
    parser.add_argument(
        "--agents",
        nargs="*",
        default=None,
        help="Agents as type:version pairs, e.g. coordinator:v0.3 script:v1.0",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    agents: list[tuple[str, str]] | None = None
    if args.agents:
        agents = []
        for token in args.agents:
            if ":" not in token:
                logger.warning("Skipping malformed agent spec: %s (expected type:version)", token)
                continue
            atype, aver = token.split(":", 1)
            agents.append((atype, aver))

    asyncio.run(
        _cli_run(
            mode=args.mode,
            repeats=args.repeats,
            concurrent=args.concurrent,
            max_ticks=args.max_ticks,
            agents=agents,
        )
    )


if __name__ == "__main__":
    main()