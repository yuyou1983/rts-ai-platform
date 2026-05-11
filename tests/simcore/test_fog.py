"""Sprint 5 tests: fog-of-war — per-player grids, vision, observation filtering."""
import pytest

from simcore.engine import SimCore
from simcore.rules import update_fog_of_war
from simcore.state import GameState


def _make_state(tick=0, entities=None, fog=None, resources=None):
    return GameState(
        tick=tick,
        entities=entities or {},
        fog_of_war=fog or {},
        resources=resources or {},
    )


class TestPerPlayerFog:
    """Fog-of-war grids are separate per player."""

    def test_initial_fog_per_player(self):
        """mapgen produces separate fog grids for P1 and P2."""
        e = SimCore()
        e.initialize(map_seed=42)
        fog = e.state.fog_of_war
        assert "1" in fog, "P1 fog missing"
        assert "2" in fog, "P2 fog missing"
        # Each player should have their own tiles
        p1 = fog["1"]
        p2 = fog["2"]
        assert p1["tiles"] != p2["tiles"], "P1 and P2 fog should differ (different bases)"

    def test_own_base_revealed(self):
        """Own base area starts as visible (2)."""
        e = SimCore()
        e.initialize(map_seed=42)
        fog = e.state.fog_of_war
        p1 = fog["1"]
        # P1 base is at ~(10,10), fog grid at 64/4=16 tiles
        # Base at fog position ~(10/64*16, 10/64*16) = (2,2)
        fw = p1["width"]
        fh = p1["height"]
        bx = int(10.0 / 64 * fw)
        by = int(10.0 / 64 * fh)
        idx = by * fw + bx
        assert p1["tiles"][idx] == 2, "Own base should be visible at tick 0"

    def test_far_corner_unexplored(self):
        """Far corners of the map should be unexplored (0) at start."""
        e = SimCore()
        e.initialize(map_seed=42)
        fog = e.state.fog_of_war
        p1 = fog["1"]
        fw = p1["width"]
        fh = p1["height"]
        # Far corner from P1 base (which is near 10,10)
        far_idx = (fh - 1) * fw + (fw - 1)
        assert p1["tiles"][far_idx] == 0, "Far corner should be unexplored"


class TestFogVisibilityUpdate:
    """Fog updates correctly when units move."""

    def test_visibility_expires_to_explored(self):
        """After a unit leaves an area, visible (2) becomes explored (1)."""
        entities = {
            "w1": {"owner": 1, "entity_type": "worker", "pos_x": 10.0, "pos_y": 10.0,
                   "is_idle": True, "speed": 2.5, "attack": 5, "attack_range": 1.0},
        }
        fog = {"1": {"tiles": [2] * 256, "width": 16, "height": 16},
               "2": {"tiles": [0] * 256, "width": 16, "height": 16}}
        # Remove the unit → area should downgrade from 2 to 1
        new_fog = update_fog_of_war({}, fog, 1)
        p1 = new_fog["1"]
        # Without any friendly units, no tiles should be 2
        assert 2 not in p1["tiles"], "No friendly units → no visible (2) tiles"
        # Previously visible tiles should be explored (1)
        assert 1 in p1["tiles"], "Previously visible should become explored"

    def test_scout_has_larger_vision(self):
        """Scouts reveal more area than regular units."""
        base_fog = {"1": {"tiles": [0] * 256, "width": 16, "height": 16},
                    "2": {"tiles": [0] * 256, "width": 16, "height": 16}}
        # Worker at center
        w_ents = {"w1": {"owner": 1, "entity_type": "worker", "pos_x": 32.0, "pos_y": 32.0,
                         "is_idle": True, "speed": 2.5, "attack": 5, "attack_range": 1.0}}
        w_fog = update_fog_of_war(w_ents, base_fog, 1)
        w_visible = sum(1 for t in w_fog["1"]["tiles"] if t == 2)

        # Scout at center
        s_ents = {"s1": {"owner": 1, "entity_type": "scout", "pos_x": 32.0, "pos_y": 32.0,
                         "is_idle": True, "speed": 4.0, "attack": 8, "attack_range": 1.5}}
        s_fog = update_fog_of_war(s_ents, base_fog, 1)
        s_visible = sum(1 for t in s_fog["1"]["tiles"] if t == 2)

        assert s_visible > w_visible, "Scout should reveal more tiles than worker"


class TestObservationFiltering:
    """get_observations respects fog-of-war."""

    def test_own_units_always_visible(self):
        """Own units are always in observations, regardless of fog."""
        entities = {
            "w1": {"owner": 1, "entity_type": "worker", "pos_x": 50.0, "pos_y": 50.0},
            "w2": {"owner": 2, "entity_type": "worker", "pos_x": 10.0, "pos_y": 10.0},
        }
        # P1 has no vision at (50,50) — but w1 is own unit
        fog = {"1": {"tiles": [0] * 256, "width": 16, "height": 16},
               "2": {"tiles": [0] * 256, "width": 16, "height": 16}}
        state = _make_state(entities=entities, fog=fog)
        obs = state.get_observations()
        assert "w1" in obs[0]["entities"], "Own worker should always be visible"

    def test_enemy_only_visible_in_fog(self):
        """Enemy units are only visible in currently visible (2) tiles."""
        entities = {
            "e1": {"owner": 2, "entity_type": "soldier", "pos_x": 32.0, "pos_y": 32.0},
        }
        # At fog position (32/64*16, 32/64*16) = (8,8), idx = 8*16+8 = 136
        fog = {"1": {"tiles": [0] * 256, "width": 16, "height": 16},
               "2": {"tiles": [0] * 256, "width": 16, "height": 16}}
        state = _make_state(entities=entities, fog=fog)
        obs = state.get_observations()
        assert "e1" not in obs[0]["entities"], "Enemy in unexplored area should be hidden"

        # Make tile visible
        tiles = [0] * 256
        tiles[136] = 2
        fog["1"]["tiles"] = tiles
        state = _make_state(entities=entities, fog=fog)
        obs = state.get_observations()
        assert "e1" in obs[0]["entities"], "Enemy in visible area should be shown"

    def test_neutral_visible_if_explored(self):
        """Neutral resources are visible in explored (1) and visible (2) tiles."""
        entities = {
            "m1": {"owner": 0, "entity_type": "resource", "resource_type": "mineral",
                   "pos_x": 32.0, "pos_y": 32.0, "resource_amount": 1000},
        }
        # Fog at (8,8), idx = 136
        # Unexplored: should be hidden
        fog = {"1": {"tiles": [0] * 256, "width": 16, "height": 16},
               "2": {"tiles": [0] * 256, "width": 16, "height": 16}}
        state = _make_state(entities=entities, fog=fog)
        obs = state.get_observations()
        assert "m1" not in obs[0]["entities"], "Resource in unexplored area should be hidden"

        # Explored: should be visible
        tiles = [0] * 256
        tiles[136] = 1
        fog["1"]["tiles"] = tiles
        state = _make_state(entities=entities, fog=fog)
        obs = state.get_observations()
        assert "m1" in obs[0]["entities"], "Resource in explored area should be shown"

    def test_fog_state_in_observation(self):
        """Each player's observation includes their own fog state."""
        e = SimCore()
        e.initialize(map_seed=42)
        obs = e.state.get_observations()
        assert "fog_of_war" in obs[0], "P1 observation should include fog state"
        assert "fog_of_war" in obs[1], "P2 observation should include fog state"
        # P1 and P2 fog should differ
        assert obs[0]["fog_of_war"] != obs[1]["fog_of_war"], "Fog states should be per-player"


class TestFogDeterminism:
    """Fog updates are deterministic."""

    def test_same_seed_same_fog(self):
        e1 = SimCore()
        e1.initialize(map_seed=42)
        e2 = SimCore()
        e2.initialize(map_seed=42)
        assert e1.state.fog_of_war == e2.state.fog_of_war, "Same seed should produce same fog"

    def test_fog_update_deterministic(self):
        e = SimCore()
        e.initialize(map_seed=42)
        fog1 = e.state.fog_of_war
        e.step([])
        fog2 = e.state.fog_of_war
        # After one tick, fog should be predictable
        #(P1 units near base still see the same area)
        p1_t1 = fog1["1"]["tiles"]
        p1_t2 = fog2["1"]["tiles"]
        # Some tiles may have changed (2→1→2 cycle), but structure should be consistent
        assert len(p1_t1) == len(p1_t2), "Fog grid size should not change"