"""Tests for GameState immutability and snapshots."""
import pytest

from simcore.state import GameState


class TestImmutability:
    """Frozen dataclass ensures state can't be mutated."""

    def test_frozen_state(self):
        """GameState is frozen — attribute assignment raises."""
        state = GameState(tick=0)
        with pytest.raises(AttributeError):
            state.tick = 1  # type: ignore[misc]

    def test_snapshot_matches_state(self):
        """to_snapshot() output matches state fields."""
        state = GameState(
            tick=5,
            entities={"unit_1": {"owner": 1}},
            resources={"p1_mineral": 500},
            is_terminal=False,
        )
        snap = state.to_snapshot()
        assert snap["tick"] == 5
        assert snap["entities"]["unit_1"]["owner"] == 1
        assert snap["resources"]["p1_mineral"] == 500
        assert snap["is_terminal"] is False


class TestObservations:
    """Test observation generation."""

    def test_returns_list(self):
        """get_observations() returns a list."""
        state = GameState(tick=0)
        obs = state.get_observations()
        assert isinstance(obs, list)

    def test_includes_tick(self):
        """Each observation includes tick number."""
        state = GameState(tick=0)
        obs = state.get_observations()
        assert len(obs) > 0
        assert obs[0]["tick"] == 0
