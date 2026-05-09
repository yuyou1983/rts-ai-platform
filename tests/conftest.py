"""Shared test fixtures for RTS-AI-Platform."""
import pytest

from simcore.engine import SimCore
from simcore.state import GameState


@pytest.fixture
def engine() -> SimCore:
    """Fresh SimCore engine instance."""
    return SimCore()


@pytest.fixture
def initialized_engine() -> SimCore:
    """SimCore engine initialized with default seed."""
    eng = SimCore()
    eng.initialize(map_seed=42)
    return eng


@pytest.fixture
def empty_state() -> GameState:
    """Empty game state at tick 0."""
    return GameState(tick=0, entities={}, fog_of_war={}, resources={}, is_terminal=False)
