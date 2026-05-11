#!/usr/bin/env python3
"""MVP smoke test: verify full Human P1 vs AI P2 game loop works."""
from simcore.engine import SimCore
from agents.coordinator import CoordinatorAgent
from agents.script_ai import ScriptAI


def main() -> None:
    print("=== MVP Smoke Test ===")
    e = SimCore()
    e.initialize(map_seed=42)
    c1 = CoordinatorAgent(player_id=1)
    s2 = ScriptAI(player_id=2)

    for t in range(2000):
        obs = e._state.get_observations()
        cmd1 = c1.decide(obs[0]).get("commands", [])
        cmd2 = s2.decide(obs[1]).get("commands", [])
        e.step(cmd1 + cmd2)
        if e._state.is_terminal:
            break

    w = e._state.winner
    assert w > 0, "No winner!"
    print(f"MVP smoke: P{w} wins @ tick {t}, ents={len(e._state.entities)}")
    print("✓ MVP smoke test PASSED")


if __name__ == "__main__":
    main()