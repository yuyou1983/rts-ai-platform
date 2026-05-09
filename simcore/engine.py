"""RTS SimCore — Headless deterministic game engine.

Produces immutable state snapshots per tick. No rendering, no I/O delays.
Designed for: parallel batch simulation, deterministic replay, RL training.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from simcore.rules import RuleEngine
from simcore.state import GameState


class AgentInterface(Protocol):
    """Protocol for agent integration — AgentScope ReActAgent implements this."""

    def decide(self, obs: dict) -> dict: ...


@dataclass
class SimCore:
    """Main game engine loop. Tick-based, deterministic, headless.

    Usage:
        engine = SimCore()
        engine.initialize(map_seed=42)
        state = engine.step(commands=[{"unit": "worker_1", "action": "gather"}])
    """

    tick_rate: float = 20.0  # ticks per second
    max_ticks: int = 10_000
    rule_engine: RuleEngine = field(default_factory=RuleEngine)

    _tick: int = field(default=0, init=False)
    _state: GameState | None = field(default=None, init=False)
    _replay: list[dict] = field(default_factory=list, init=False)

    def initialize(self, map_seed: int = 42, config: dict | None = None) -> None:
        """Initialize game state from seed + config (deterministic).

        Args:
            map_seed: Seed for procedural map generation.
            config: Optional game configuration (unit stats, resources, etc.).
        """
        from simcore.mapgen import generate_map

        self._state = generate_map(seed=map_seed, config=config or {})
        self._tick = 0
        self._replay = [self._state.to_snapshot()]

    def step(self, commands: list[dict]) -> GameState:
        """Advance one tick: apply commands → resolve rules → snapshot state.

        Args:
            commands: List of command dicts matching cmd.proto schema.

        Returns:
            New immutable GameState after tick resolution.
        """
        if self._state is None:
            raise RuntimeError("SimCore not initialized. Call initialize() first.")

        self._tick += 1
        self._state = self.rule_engine.apply(self._state, commands, self._tick)
        self._replay.append(self._state.to_snapshot())
        return self._state

    def run(self, agents: list[AgentInterface]) -> GameState:
        """Run full game loop with agent decisions each tick.

        Args:
            agents: List of agents implementing AgentInterface.

        Returns:
            Final GameState when game terminates.
        """
        self.initialize()
        while self._tick < self.max_ticks and not self._state.is_terminal:
            obs = self._state.get_observations()
            commands = [a.decide(o) for a, o in zip(agents, obs, strict=True)]
            self.step(commands)
        return self._state

    @property
    def tick(self) -> int:
        """Current tick number."""
        return self._tick

    @property
    def state(self) -> GameState | None:
        """Current game state (or None if not initialized)."""
        return self._state

    @property
    def replay(self) -> list[dict]:
        """Full replay trace — can be replayed deterministically."""
        return list(self._replay)
