#!/usr/bin/env python3
"""League self-play runner — round-robin tournament with ELO ranking + PromotionGate."""
import asyncio
import json
import logging
import time
from pathlib import Path

from harness.league import AgentType, AgentVersion, League, MatchupConfig, MatchupMode, MatchupResult
from harness.pool import MatchConfig, MatchScheduler, SimulationPool
from harness.promotion import PromotionConfig, PromotionGate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    # 1. Create League, register 3 versions
    league = League()
    league.register(AgentVersion("v1_script", AgentType.SCRIPT, creation_tick=0))
    league.register(AgentVersion("v2_coordinator", AgentType.COORDINATOR, creation_tick=100))
    league.register(AgentVersion("v3_random", AgentType.SCRIPT, creation_tick=200))

    # 2. Generate matchups via League — cross-type round-robin with version names
    matchup_config = MatchupConfig(
        mode=MatchupMode.CROSS_TYPE,
        games_per_pair=10,
        map_seeds=list(range(42, 52)),  # 10 seeds
        max_ticks=5000,
    )
    matchups = league.generate_matchups(matchup_config)
    print(f"Generated {len(matchups)} matchups")

    # 3. Convert league matchups → MatchConfig and schedule
    configs = [
        MatchConfig(
            map_seed=m["map_seed"],
            max_ticks=m["max_ticks"],
            player1_type=m["player1_type"],
            player2_type=m["player2_type"],
        )
        for m in matchups
    ]
    scheduler = MatchScheduler()
    scheduler.add_custom(configs)

    # 4. Run
    pool = SimulationPool(max_concurrent=4)
    t0 = time.monotonic()
    results = await pool.run_all(scheduler)
    wall = time.monotonic() - t0

    # 5. Record results to League with proper version mapping
    for r, m in zip(results, matchups):
        if r.error is not None:
            continue
        league.record_result(
            MatchupResult(
                player1=m["player1_version"],
                player2=m["player2_version"],
                winner=r.winner,
                ticks=r.ticks,
                mode=MatchupMode(m.get("mode", "cross_type")),
            )
        )

    # 6. Output ranking
    print("\n" + league.format_leaderboard())

    # 7. PromotionGate check (dry-run)
    gate = PromotionGate(
        config=PromotionConfig(min_games=10, win_threshold=0.55),
        league=league,
    )
    board = league.get_leaderboard()
    if len(board) >= 2:
        challenger = board[0].name   # highest ELO
        champion = board[1].name    # second highest
        challenger_type = "coordinator" if "coordinator" in challenger else "script"
        champion_type = "coordinator" if "coordinator" in champion else "script"
        print(f"\nPromotion eval: {challenger} vs {champion}")
        result = await gate.evaluate(
            challenger=challenger,
            champion=champion,
            challenger_agent_type=challenger_type,
            champion_agent_type=champion_type,
        )
        print(f"  Result: {'PROMOTED' if result.promoted else 'REJECTED'} "
              f"(win_rate={result.win_rate:.3f}, CI=[{result.ci_lower:.3f}, {result.ci_upper:.3f}])")
        if result.promoted:
            gate.promote(result)
        else:
            gate.rollback(result)

    # 8. Save results
    out = Path("harness/output")
    out.mkdir(parents=True, exist_ok=True)
    ranking_data = [s.to_dict() for s in league.get_leaderboard()]
    (out / "league_ranking.json").write_text(json.dumps(ranking_data, indent=2))
    print(f"\nWall time: {wall:.1f}s")
    print(f"Results saved to harness/output/league_ranking.json")


if __name__ == "__main__":
    asyncio.run(main())