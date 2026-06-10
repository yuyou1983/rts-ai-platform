"""Tests for cloak/detection system: cloaked units hidden from enemy
observations unless within detection range of a friendly detector."""
import math

import pytest

from simcore.state import GameState


def _make_state(tick=0, entities=None, fog=None, resources=None):
    return GameState(
        tick=tick,
        entities=entities or {},
        fog_of_war=fog or {},
        resources=resources or {},
    )


# ── Helper: 16×16 fog grid with all tiles visible (2) ──────────────
def _full_visible_fog():
    return {
        "1": {"tiles": [2] * 256, "width": 16, "height": 16},
        "2": {"tiles": [2] * 256, "width": 16, "height": 16},
    }


# ── Helper: 16×16 fog grid with all tiles unexplored (0) ──────────
def _full_unexplored_fog():
    return {
        "1": {"tiles": [0] * 256, "width": 16, "height": 16},
        "2": {"tiles": [0] * 256, "width": 16, "height": 16},
    }


class TestCloakBasic:
    """Cloaked enemy is hidden when no friendly detector is nearby."""

    def test_cloaked_enemy_hidden_from_opponent(self):
        """A cloaked DT (owner=1) should NOT appear in P2's observation
        when P2 has no detector in range."""
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 32.0,
                "pos_y": 32.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()

        # P1 sees own DT
        assert "dt1" in obs[0]["entities"], "P1 should always see own cloaked unit"

        # P2 does NOT see the cloaked enemy
        assert "dt1" not in obs[1]["entities"], (
            "P2 should NOT see cloaked enemy without detector"
        )

    def test_non_cloaked_enemy_still_visible(self):
        """A regular enemy unit (not cloaked) should still be visible
        in visible fog tiles — cloak filter doesn't affect non-cloaked."""
        entities = {
            "z1": {
                "owner": 2,
                "entity_type": "soldier",
                "unit_type": "Zergling",
                "pos_x": 32.0,
                "pos_y": 32.0,
                "health": 40,
                "max_health": 40,
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()
        assert "z1" in obs[0]["entities"], "Non-cloaked enemy should be visible in fog=2"

    def test_cloaked_enemy_in_fog_unexplored_still_hidden(self):
        """Even without cloak, an enemy in an unexplored tile is hidden.
        Cloak is a second layer filter — fog filter still applies."""
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 32.0,
                "pos_y": 32.0,
                "health": 80,
                "is_cloaked": True,
            },
        }
        # P2 has no vision at (32, 32)
        state = _make_state(entities=entities, fog=_full_unexplored_fog())
        obs = state.get_observations()
        assert "dt1" not in obs[1]["entities"], (
            "Cloaked enemy in unexplored fog is hidden (fog first, then cloak)"
        )


class TestDetection:
    """Detector units reveal cloaked enemies within detection_range."""

    def test_observer_detects_cloaked_dt(self):
        """An Observer (owner=2) with detection_range=8 at position (32,32)
        should reveal a cloaked DT (owner=1) at distance ≤ 8."""
        # DT at (32,0), Observer at (32,4) → distance = 4 < 8
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 32.0,
                "pos_y": 0.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
            "obs1": {
                "owner": 2,
                "entity_type": "scout",
                "unit_type": "Observer",
                "pos_x": 32.0,
                "pos_y": 4.0,
                "health": 40,
                "max_health": 40,
                "detection_range": 8,
                "is_cloaked": True,  # Observer itself is cloaked
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()

        # P2 now sees the cloaked DT because Observer detects it
        assert "dt1" in obs[1]["entities"], (
            "P2 Observer should detect cloaked DT within detection_range"
        )

    def test_detector_out_of_range_no_reveal(self):
        """If the detector is too far, the cloaked enemy stays hidden."""
        # DT at (32,0), Observer at (32,20) → distance = 20 > 8
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 32.0,
                "pos_y": 0.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
            "obs1": {
                "owner": 2,
                "entity_type": "scout",
                "unit_type": "Observer",
                "pos_x": 32.0,
                "pos_y": 20.0,
                "health": 40,
                "max_health": 40,
                "detection_range": 8,
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()

        assert "dt1" not in obs[1]["entities"], (
            "P2 Observer too far → cloaked DT stays hidden"
        )

    def test_building_detector_reveals(self):
        """Missile Turret (owner=2) with detection_range=7 reveals cloaked enemy."""
        # DT at (10,10), Turret at (13,10) → distance = 3 < 7
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 10.0,
                "pos_y": 10.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
            "turret1": {
                "owner": 2,
                "entity_type": "building",
                "building_type": "MissileTurret",
                "pos_x": 13.0,
                "pos_y": 10.0,
                "health": 250,
                "max_health": 250,
                "detection_range": 7,
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()

        assert "dt1" in obs[1]["entities"], (
            "P2 Missile Turret should detect cloaked DT within range"
        )

    def test_own_cloaked_unit_always_visible_to_self(self):
        """A player always sees their own cloaked units regardless of detectors."""
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 32.0,
                "pos_y": 32.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
        }
        # P1 has no fog at all (all unexplored), but own units always visible
        state = _make_state(entities=entities, fog=_full_unexplored_fog())
        obs = state.get_observations()
        assert "dt1" in obs[0]["entities"], "Own cloaked unit always visible to self"

    def test_neutral_resources_not_affected_by_cloak(self):
        """Resource nodes (owner=0) ignore the cloak filter entirely."""
        entities = {
            "m1": {
                "owner": 0,
                "entity_type": "resource",
                "resource_type": "mineral",
                "pos_x": 32.0,
                "pos_y": 32.0,
                "resource_amount": 1000,
            },
        }
        fog = {
            "1": {"tiles": [1] * 256, "width": 16, "height": 16},  # explored
            "2": {"tiles": [1] * 256, "width": 16, "height": 16},
        }
        state = _make_state(entities=entities, fog=fog)
        obs = state.get_observations()
        assert "m1" in obs[0]["entities"], "Resource in explored area is visible"


class TestDetectionRangeBoundary:
    """Exact boundary: detection_range is inclusive."""

    def test_exactly_at_detection_range(self):
        """Enemy exactly at detection_range distance (8.0) IS detected."""
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 0.0,
                "pos_y": 0.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
            "obs1": {
                "owner": 2,
                "entity_type": "scout",
                "unit_type": "Observer",
                "pos_x": 8.0,
                "pos_y": 0.0,
                "health": 40,
                "max_health": 40,
                "detection_range": 8,
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()
        assert "dt1" in obs[1]["entities"], (
            "Enemy exactly at detection_range should be detected (inclusive)"
        )

    def test_just_beyond_detection_range(self):
        """Enemy just beyond detection_range (8.01) is NOT detected."""
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 0.0,
                "pos_y": 0.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
            "obs1": {
                "owner": 2,
                "entity_type": "scout",
                "unit_type": "Observer",
                "pos_x": 8.01,
                "pos_y": 0.0,
                "health": 40,
                "max_health": 40,
                "detection_range": 8,
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()
        assert "dt1" not in obs[1]["entities"], (
            "Enemy just beyond detection_range should stay hidden"
        )


class TestMultipleDetectors:
    """Multiple detectors: any one in range is sufficient."""

    def test_second_detector_covers(self):
        """If first detector is out of range but second is in range,
        the cloaked enemy is detected."""
        entities = {
            "dt1": {
                "owner": 1,
                "entity_type": "soldier",
                "unit_type": "DarkTemplar",
                "pos_x": 0.0,
                "pos_y": 0.0,
                "health": 80,
                "max_health": 80,
                "is_cloaked": True,
            },
            "obs_far": {
                "owner": 2,
                "entity_type": "scout",
                "pos_x": 50.0,
                "pos_y": 50.0,
                "health": 40,
                "detection_range": 8,
            },
            "obs_near": {
                "owner": 2,
                "entity_type": "scout",
                "pos_x": 5.0,
                "pos_y": 0.0,
                "health": 40,
                "detection_range": 8,
            },
        }
        state = _make_state(entities=entities, fog=_full_visible_fog())
        obs = state.get_observations()
        assert "dt1" in obs[1]["entities"], (
            "Second detector in range should reveal cloaked enemy"
        )
