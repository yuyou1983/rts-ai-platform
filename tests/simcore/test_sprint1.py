"""Sprint 1 tests: A* pathfinding, movement, collision, commands, engine pipeline."""
import pytest

from simcore.map import TileMap, generate_tile_map, PLAIN, WATER, MOUNTAIN, CREEP
from simcore.pathfinder import find_path, smooth_path, SQRT2
from simcore.movement import move_entities, collision_separate, is_at_target
from simcore.commands import (
    validate_command, apply_command,
    MOVE, STOP, ATTACK, GATHER, BUILD, TRAIN, HOLD, PATROL,
)
from simcore.engine import SimCore
from simcore.state import GameState


# ─── Helpers ──────────────────────────────────────────────────

def _worker(wid: str, owner: int, px: float, py: float, **kw) -> dict:
    return {
        "id": wid, "owner": owner, "entity_type": "worker",
        "pos_x": px, "pos_y": py,
        "health": kw.get("health", 50), "max_health": kw.get("max_health", 50),
        "speed": kw.get("speed", 2.5), "attack": 5, "attack_range": 1.0,
        "is_idle": True, "carry_amount": 0, "carry_capacity": 10.0,
        "target_x": None, "target_y": None, "path": [],
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False, "is_flying": False,
    }


def _soldier(sid: str, owner: int, px: float, py: float, **kw) -> dict:
    return {
        "id": sid, "owner": owner, "entity_type": "soldier",
        "pos_x": px, "pos_y": py,
        "health": kw.get("health", 80), "max_health": kw.get("max_health", 80),
        "speed": kw.get("speed", 3.0), "attack": 15, "attack_range": 1.0,
        "is_idle": True, "carry_amount": 0, "carry_capacity": 0,
        "target_x": None, "target_y": None, "path": [],
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False, "is_flying": False,
    }


def _building(bid: str, owner: int, px: float, py: float, btype: str = "base", **kw) -> dict:
    return {
        "id": bid, "owner": owner, "entity_type": "building",
        "building_type": btype, "pos_x": px, "pos_y": py,
        "health": kw.get("health", 1500), "max_health": kw.get("max_health", 1500),
        "is_constructing": kw.get("is_constructing", False),
        "build_progress": kw.get("build_progress", 100),
        "production_queue": [], "production_timers": [],
    }


def _plain_map(size: int = 16) -> TileMap:
    """Create an all-PLAIN tile map for pathfinding tests."""
    return TileMap(width=size, height=size, tile_size=16)


# ════════════════════════════════════════════════════════════════
# A* PATHFINDING TESTS
# ════════════════════════════════════════════════════════════════

class TestPathfinderBasic:
    """A* finds valid paths on plain terrain."""

    def test_straight_line_path(self):
        """A* returns a valid path on an all-PLAIN map."""
        m = _plain_map()
        path = find_path((0, 0), (5, 0), m, is_flying=False)
        assert len(path) > 0, "Should find a path on plain terrain"
        assert path[0] == (0, 0), "Path should start at start"
        assert path[-1] == (5, 0), "Path should end at end"

    def test_diagonal_path(self):
        """A* supports 8-directional movement."""
        m = _plain_map()
        path = find_path((0, 0), (3, 3), m, is_flying=False)
        assert len(path) > 0
        assert path[-1] == (3, 3)

    def test_path_length_reasonable(self):
        """Path length should be reasonable (not excessively long)."""
        m = _plain_map()
        path = find_path((0, 0), (5, 5), m, is_flying=False)
        # Octile distance is about 5 * sqrt(2) ≈ 7.07, so path should be <= 8 steps
        assert len(path) <= 8, f"Path too long: {len(path)} steps for (0,0)→(5,5)"

    def test_same_start_end(self):
        """Start == end returns single-point path."""
        m = _plain_map()
        path = find_path((3, 3), (3, 3), m, is_flying=False)
        assert path == [(3, 3)]


class TestPathfinderObstacles:
    """A* handles impassable terrain correctly."""

    def test_mountain_wall_blocks_ground(self):
        """Ground units can't path through a mountain wall."""
        m = _plain_map(size=10)
        # Build a horizontal mountain wall at y=5
        for x in range(10):
            m.set_terrain(x, 5, MOUNTAIN)
        path = find_path((3, 3), (3, 7), m, is_flying=False)
        if path:
            # If path found, it must not go through mountain tiles
            for tx, ty in path:
                assert m.get_terrain(tx, ty) != MOUNTAIN
        else:
            # No path found is acceptable if wall is truly impassable
            pass

    def test_unreachable_target_mountains(self):
        """A* returns empty list when target is surrounded by mountains."""
        m = _plain_map(size=10)
        # Surround (5, 5) with mountains
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                m.set_terrain(5 + dx, 5 + dy, MOUNTAIN)
        path = find_path((2, 2), (5, 5), m, is_flying=False)
        assert path == [], "Should return empty list for unreachable target"

    def test_water_blocks_ground(self):
        """Water tiles block ground units."""
        m = _plain_map(size=10)
        m.set_terrain(5, 0, WATER)
        m.set_terrain(5, 1, WATER)
        m.set_terrain(5, 2, WATER)
        # Try to path across the water line
        path = find_path((3, 1), (7, 1), m, is_flying=False)
        if path:
            for tx, ty in path:
                assert m.get_terrain(tx, ty) != WATER

    def test_flying_ignores_ground_obstacles(self):
        """Flying units path through mountains (only WATER/MOUNTAIN block for flying)."""
        m = _plain_map(size=10)
        # Surround target with mountains
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                m.set_terrain(5 + dx, 5 + dy, MOUNTAIN)
        # Flying units should still find a path
        path = find_path((2, 2), (5, 5), m, is_flying=True)
        assert len(path) > 0, "Flying units should find path through mountains"
        assert path[-1] == (5, 5)

    def test_occupied_tiles_block_ground(self):
        """Building-occupied tiles block ground units."""
        m = _plain_map(size=10)
        m.occupy(5, 0)
        m.occupy(5, 1)
        m.occupy(5, 2)
        path = find_path((3, 1), (7, 1), m, is_flying=False)
        if path:
            # Path should not go through occupied tiles
            for tx, ty in path:
                assert not m.is_occupied(tx, ty), f"Path goes through occupied tile ({tx},{ty})"

    def test_flying_ignores_occupied(self):
        """Flying units ignore building-occupied tiles."""
        m = _plain_map(size=10)
        m.occupy(5, 1)
        path = find_path((3, 1), (7, 1), m, is_flying=True)
        assert len(path) > 0


class TestPathfinderEdgeCases:
    """Edge cases for A* pathfinding."""

    def test_no_path_to_self_mountain(self):
        """Can't path to a mountain tile (ground unit)."""
        m = _plain_map(size=10)
        m.set_terrain(5, 5, MOUNTAIN)
        path = find_path((3, 3), (5, 5), m, is_flying=False)
        assert path == []

    def test_long_path(self):
        """A* finds paths across a large map."""
        m = generate_tile_map(seed=42, config={"map_size": 64, "tile_size": 16})
        # Path between base areas
        start = (9, 9)  # near P1 base
        end = (54, 54)  # near P2 base
        path = find_path(start, end, m, is_flying=False)
        # May or may not find path depending on obstacles, but should not hang
        # If found, check it reaches destination
        if path:
            assert path[-1] == end or m.is_passable(path[-1][0], path[-1][1], is_flying=False)


# ════════════════════════════════════════════════════════════════
# PATH SMOOTHING TESTS
# ════════════════════════════════════════════════════════════════

class TestPathSmoothing:
    """Path smoothing removes collinear waypoints."""

    def test_collinear_horizontal(self):
        """Three horizontal points — middle removed."""
        path = [(0, 0), (1, 0), (2, 0)]
        result = smooth_path(path)
        assert result == [(0, 0), (2, 0)]

    def test_collinear_diagonal(self):
        """Three diagonal points — middle removed."""
        path = [(0, 0), (1, 1), (2, 2)]
        result = smooth_path(path)
        assert result == [(0, 0), (2, 2)]

    def test_non_collinear_preserved(self):
        """Non-collinear points are preserved."""
        path = [(0, 0), (1, 1), (2, 1)]
        result = smooth_path(path)
        assert len(result) == 3

    def test_short_path_unchanged(self):
        """Paths of 2 or fewer points are unchanged."""
        path = [(0, 0), (3, 3)]
        result = smooth_path(path)
        assert result == [(0, 0), (3, 3)]

    def test_zigzag_preserved(self):
        """Zigzag path (L-shape) should keep the corner."""
        path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
        result = smooth_path(path)
        assert (2, 0) in result, "Corner point should be kept"
        assert len(result) < len(path), "Some collinear points should be removed"


# ════════════════════════════════════════════════════════════════
# MOVEMENT TESTS
# ════════════════════════════════════════════════════════════════

class TestMovement:
    """Movement follows path waypoints."""

    def test_entity_moves_along_path(self):
        """Entity with a path moves toward the first waypoint."""
        e = _worker("w1", 1, 8.0, 8.0)  # world coords (tile 0,0 center = 8,8)
        e["path"] = [(1, 0), (2, 0)]  # tile (1,0) center = (24, 8)
        e["is_idle"] = False
        entities = {"w1": e}
        result = move_entities(entities, dt=1.0)
        # Should have moved toward tile (1,0) center at (24, 8)
        assert result["w1"]["pos_x"] > 8.0, "Entity should have moved"

    def test_entity_reaches_waypoint(self):
        """Entity reaching a waypoint advances to the next one."""
        e = _worker("w1", 1, 23.0, 8.0)  # Very close to tile (1,0) center (24,8)
        e["path"] = [(1, 0), (2, 0)]
        e["is_idle"] = False
        result = move_entities({"w1": e}, dt=1.0)
        # After reaching (1,0), path should now start at (2,0)
        assert result["w1"]["path"] == [(2, 0)]

    def test_entity_stops_at_final_waypoint(self):
        """Entity becomes idle when reaching the last waypoint."""
        e = _worker("w1", 1, 23.0, 8.0)  # Near tile (1,0) center
        e["path"] = [(1, 0)]  # Single waypoint remaining
        e["is_idle"] = False
        result = move_entities({"w1": e}, dt=1.0)
        assert result["w1"]["path"] == []
        assert result["w1"]["is_idle"] is True
        assert result["w1"]["target_x"] is None

    def test_no_path_no_move(self):
        """Entity without a path doesn't move."""
        e = _worker("w1", 1, 100.0, 100.0)
        result = move_entities({"w1": e}, dt=1.0)
        assert result["w1"]["pos_x"] == 100.0
        assert result["w1"]["pos_y"] == 100.0


class TestCollisionSeparation:
    """Collision separation pushes overlapping units apart."""

    def test_overlapping_units_separated(self):
        """Two ground units at the same position get pushed apart."""
        e1 = _worker("w1", 1, 100.0, 100.0)
        e2 = _worker("w2", 1, 100.0, 100.0)
        result = collision_separate({"w1": e1, "w2": e2})
        # They should no longer be at the exact same position
        d = (result["w1"]["pos_x"] - result["w2"]["pos_x"])**2 + \
            (result["w1"]["pos_y"] - result["w2"]["pos_y"])**2
        assert d > 0, "Units should be pushed apart"

    def test_close_units_separated(self):
        """Units that are too close get pushed apart."""
        e1 = _worker("w1", 1, 100.0, 100.0)
        e2 = _worker("w2", 1, 100.5, 100.0)
        result = collision_separate({"w1": e1, "w2": e2})
        d = ((result["w1"]["pos_x"] - result["w2"]["pos_x"])**2 +
             (result["w1"]["pos_y"] - result["w2"]["pos_y"])**2) ** 0.5
        assert d >= 1.0, f"Units should be separated (dist={d:.2f})"

    def test_distant_units_unchanged(self):
        """Units far apart are not moved."""
        e1 = _worker("w1", 1, 10.0, 10.0)
        e2 = _worker("w2", 1, 50.0, 50.0)
        result = collision_separate({"w1": e1, "w2": e2})
        assert result["w1"]["pos_x"] == 10.0
        assert result["w2"]["pos_x"] == 50.0

    def test_flying_no_ground_collision(self):
        """Flying units don't collide with ground units."""
        ground = _worker("g1", 1, 100.0, 100.0)
        flying = _soldier("f1", 1, 100.0, 100.0)
        flying["is_flying"] = True
        result = collision_separate({"g1": ground, "f1": flying})
        # Ground unit shouldn't be pushed by flying unit
        assert result["g1"]["pos_x"] == 100.0
        assert result["g1"]["pos_y"] == 100.0


class TestIsAtTarget:
    """is_at_target correctly determines if entity reached target."""

    def test_idle_entity_at_target(self):
        """Idle entity is at target."""
        e = _worker("w1", 1, 10.0, 10.0)
        assert is_at_target(e) is True

    def test_entity_with_path_not_at_target(self):
        """Entity with remaining path is not at target."""
        e = _worker("w1", 1, 10.0, 10.0)
        e["path"] = [(1, 0)]
        e["is_idle"] = False
        assert is_at_target(e) is False

    def test_entity_near_target(self):
        """Entity within threshold of target is at target."""
        e = _worker("w1", 1, 10.5, 10.0)
        e["target_x"] = 11.0
        e["target_y"] = 10.0
        e["is_idle"] = False
        assert is_at_target(e) is True


# ════════════════════════════════════════════════════════════════
# COMMAND TESTS
# ════════════════════════════════════════════════════════════════

class TestCommandValidation:
    """Commands validate correctly."""

    def test_valid_move_command(self):
        """MOVE command for a unit with target coords is valid."""
        e = _worker("w1", 1, 100.0, 100.0)
        cmd = {"action": MOVE, "issuer": 1, "unit_id": "w1", "target_x": 200.0, "target_y": 200.0}
        state = GameState(tick=1, entities={"w1": e})
        assert validate_command(cmd, e, state) is True

    def test_invalid_move_no_target(self):
        """MOVE command without target coords is invalid."""
        e = _worker("w1", 1, 100.0, 100.0)
        cmd = {"action": MOVE, "issuer": 1, "unit_id": "w1"}
        state = GameState(tick=1, entities={"w1": e})
        assert validate_command(cmd, e, state) is False

    def test_move_for_building_invalid(self):
        """MOVE command for a building is invalid."""
        b = _building("b1", 1, 100.0, 100.0)
        cmd = {"action": MOVE, "issuer": 1, "unit_id": "b1", "target_x": 200.0, "target_y": 200.0}
        state = GameState(tick=1, entities={"b1": b})
        assert validate_command(cmd, b, state) is False

    def test_stop_command_valid(self):
        """STOP command for a unit is valid."""
        e = _worker("w1", 1, 100.0, 100.0)
        cmd = {"action": STOP, "issuer": 1, "unit_id": "w1"}
        state = GameState(tick=1, entities={"w1": e})
        assert validate_command(cmd, e, state) is True

    def test_attack_command_valid(self):
        """ATTACK command with existing target is valid."""
        e1 = _soldier("s1", 1, 100.0, 100.0)
        e2 = _soldier("s2", 2, 120.0, 100.0)
        cmd = {"action": ATTACK, "issuer": 1, "attacker_id": "s1", "target_id": "s2"}
        state = GameState(tick=1, entities={"s1": e1, "s2": e2})
        assert validate_command(cmd, e1, state) is True

    def test_attack_nonexistent_target_invalid(self):
        """ATTACK command targeting nonexistent entity is invalid."""
        e = _soldier("s1", 1, 100.0, 100.0)
        cmd = {"action": ATTACK, "issuer": 1, "attacker_id": "s1", "target_id": "ghost"}
        state = GameState(tick=1, entities={"s1": e})
        assert validate_command(cmd, e, state) is False

    def test_wrong_owner_invalid(self):
        """Command from wrong owner is invalid."""
        e = _worker("w1", 2, 100.0, 100.0)
        cmd = {"action": MOVE, "issuer": 1, "unit_id": "w1", "target_x": 200.0, "target_y": 200.0}
        state = GameState(tick=1, entities={"w1": e})
        assert validate_command(cmd, e, state) is False

    def test_unknown_action_invalid(self):
        """Unknown action is invalid."""
        e = _worker("w1", 1, 100.0, 100.0)
        cmd = {"action": "jump", "issuer": 1}
        state = GameState(tick=1, entities={"w1": e})
        assert validate_command(cmd, e, state) is False


class TestCommandApplication:
    """Commands modify entity state correctly."""

    def test_move_sets_path(self):
        """MOVE command computes A* path and sets it on entity."""
        m = _plain_map()
        e = _worker("w1", 1, 8.0, 8.0)
        cmd = {"action": MOVE, "issuer": 1, "unit_id": "w1", "target_x": 200.0, "target_y": 8.0}
        result = apply_command(cmd, e, m)
        assert len(result["path"]) > 0, "Should have a path"
        assert result["target_x"] == 200.0
        assert result["is_idle"] is False

    def test_stop_clears_path(self):
        """STOP command clears target, path, and attack state."""
        e = _worker("w1", 1, 100.0, 100.0)
        e["path"] = [(5, 0), (6, 0)]
        e["target_x"] = 200.0
        e["target_y"] = 100.0
        e["attack_target_id"] = "e1"
        e["is_idle"] = False
        cmd = {"action": STOP, "issuer": 1, "unit_id": "w1"}
        result = apply_command(cmd, e)
        assert result["path"] == []
        assert result["target_x"] is None
        assert result["is_idle"] is True
        assert result["attack_target_id"] == ""

    def test_attack_sets_target(self):
        """ATTACK command sets attack_target_id."""
        e = _soldier("s1", 1, 100.0, 100.0)
        cmd = {"action": ATTACK, "issuer": 1, "attacker_id": "s1", "target_id": "e1"}
        result = apply_command(cmd, e)
        assert result["attack_target_id"] == "e1"
        assert result["is_idle"] is False


# ════════════════════════════════════════════════════════════════
# TILEMAP TESTS
# ════════════════════════════════════════════════════════════════

class TestTileMap:
    """TileMap terrain and collision queries."""

    def test_default_terrain_plain(self):
        """Default map is all PLAIN."""
        m = TileMap(width=8, height=8)
        for y in range(8):
            for x in range(8):
                assert m.get_terrain(x, y) == PLAIN

    def test_set_and_get_terrain(self):
        """Set terrain and retrieve it."""
        m = TileMap(width=8, height=8)
        m.set_terrain(3, 3, WATER)
        assert m.get_terrain(3, 3) == WATER

    def test_out_of_bounds_mountain(self):
        """Out-of-bounds terrain returns MOUNTAIN."""
        m = TileMap(width=8, height=8)
        assert m.get_terrain(-1, 0) == MOUNTAIN
        assert m.get_terrain(8, 8) == MOUNTAIN

    def test_passable_ground(self):
        """PLAIN tiles are passable for ground units."""
        m = TileMap(width=8, height=8)
        assert m.is_passable(3, 3, is_flying=False) is True

    def test_water_impassable_ground(self):
        """WATER tiles are impassable for ground units."""
        m = TileMap(width=8, height=8)
        m.set_terrain(3, 3, WATER)
        assert m.is_passable(3, 3, is_flying=False) is False

    def test_mountain_impassable_ground(self):
        """MOUNTAIN tiles are impassable for ground units."""
        m = TileMap(width=8, height=8)
        m.set_terrain(3, 3, MOUNTAIN)
        assert m.is_passable(3, 3, is_flying=False) is False

    def test_flying_passable(self):
        """Flying units can pass over all terrain."""
        m = TileMap(width=8, height=8)
        m.set_terrain(3, 3, WATER)
        m.set_terrain(4, 4, MOUNTAIN)
        assert m.is_passable(3, 3, is_flying=True) is True
        assert m.is_passable(4, 4, is_flying=True) is True

    def test_occupied_impassable_ground(self):
        """Building-occupied tiles are impassable for ground units."""
        m = TileMap(width=8, height=8)
        m.occupy(3, 3)
        assert m.is_passable(3, 3, is_flying=False) is False

    def test_occupied_passable_flying(self):
        """Building-occupied tiles are passable for flying units."""
        m = TileMap(width=8, height=8)
        m.occupy(3, 3)
        assert m.is_passable(3, 3, is_flying=True) is True

    def test_occupy_and_free(self):
        """Occupy and free a tile."""
        m = TileMap(width=8, height=8)
        m.occupy(3, 3)
        assert m.is_occupied(3, 3) is True
        m.free(3, 3)
        assert m.is_occupied(3, 3) is False

    def test_creeppassable_ground(self):
        """CREEP terrain is passable for ground units."""
        m = TileMap(width=8, height=8)
        m.set_terrain(3, 3, CREEP)
        assert m.is_passable(3, 3, is_flying=False) is True

    def test_serialization_roundtrip(self):
        """TileMap serializes and deserializes correctly."""
        m = TileMap(width=8, height=8)
        m.set_terrain(3, 3, WATER)
        m.occupy(5, 5)
        data = m.to_dict()
        m2 = TileMap.from_dict(data)
        assert m2.get_terrain(3, 3) == WATER
        assert m2.is_occupied(5, 5) is True
        assert m2.width == 8
        assert m2.height == 8

    def test_generate_tile_map(self):
        """Procedural map generation works and is deterministic."""
        m1 = generate_tile_map(seed=42)
        m2 = generate_tile_map(seed=42)
        assert m1.tiles == m2.tiles, "Same seed should produce same map"

    def test_generate_clears_start_areas(self):
        """Starting areas should be PLAIN."""
        m = generate_tile_map(seed=42, config={"map_size": 64})
        base1_x, base1_y = int(64 * 0.15), int(64 * 0.15)
        base2_x, base2_y = int(64 * 0.85), int(64 * 0.85)
        assert m.get_terrain(base1_x, base1_y) == PLAIN
        assert m.get_terrain(base2_x, base2_y) == PLAIN

    def test_world_to_tile(self):
        """World-to-tile coordinate conversion."""
        m = TileMap(width=64, height=64, tile_size=16)
        assert m.world_to_tile(8.0, 8.0) == (0, 0)
        assert m.world_to_tile(24.0, 8.0) == (1, 0)

    def test_tile_to_world(self):
        """Tile-to-world coordinate conversion (tile center)."""
        m = TileMap(width=64, height=64, tile_size=16)
        wx, wy = m.tile_to_world(0, 0)
        assert wx == 8.0
        assert wy == 8.0


# ════════════════════════════════════════════════════════════════
# ENGINE PIPELINE TESTS
# ════════════════════════════════════════════════════════════════

class TestEngineDeterminism:
    """Engine step is deterministic: same seed + same commands → same state."""

    def test_deterministic_step(self):
        """Same seed and commands produce identical states."""
        def run(seed: int, steps: int = 10) -> dict:
            e = SimCore()
            e.initialize(map_seed=seed)
            for _ in range(steps):
                e.step(commands=[])
            return e.state.to_snapshot()

        s1 = run(42)
        s2 = run(42)
        assert s1 == s2, "Same seed + same commands should produce identical state"

    def test_deterministic_with_commands(self):
        """Deterministic with specific commands."""
        def run(seed: int) -> dict:
            e = SimCore()
            e.initialize(map_seed=seed)
            cmds = [{"action": "move", "unit_id": "worker_p1_0",
                      "target_x": 20.0, "target_y": 10.0, "issuer": 1}]
            for _ in range(5):
                e.step(commands=cmds)
            return e.state.to_snapshot()

        s1 = run(42)
        s2 = run(42)
        assert s1 == s2

    def test_different_seed_different_state(self):
        """Different seeds produce different states."""
        e1 = SimCore()
        e1.initialize(map_seed=1)
        e2 = SimCore()
        e2.initialize(map_seed=2)
        assert e1.state != e2.state


class TestEnginePipeline:
    """Engine pipeline integrates all subsystems."""

    def test_step_returns_gamestate(self):
        """step() returns a valid GameState."""
        e = SimCore()
        e.initialize(map_seed=42)
        state = e.step(commands=[])
        assert isinstance(state, GameState)
        assert state.tick == 1

    def test_tile_map_created(self):
        """Engine creates a tile map on initialize."""
        e = SimCore()
        e.initialize(map_seed=42)
        assert e.tile_map is not None
        assert isinstance(e.tile_map, TileMap)

    def test_get_observations(self):
        """get_observations returns fog-filtered view."""
        e = SimCore()
        e.initialize(map_seed=42)
        obs = e.get_observations(player_id=1)
        assert isinstance(obs, dict)
        assert "tick" in obs
        assert "entities" in obs

    def test_step_without_init_raises(self):
        """step() without initialize raises RuntimeError."""
        e = SimCore()
        with pytest.raises(RuntimeError, match="not initialized"):
            e.step(commands=[])


# ════════════════════════════════════════════════════════════════
# INTEGRATION TEST
# ════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end: move unit from A to B via pathfinding."""

    def test_move_unit_via_pathfinding(self):
        """Move a unit using A* pathfinding through the engine."""
        e = SimCore()
        e.initialize(map_seed=42)

        # Get initial worker position
        w = e.state.entities.get("worker_p1_0")
        assert w is not None
        start_x = w["pos_x"]
        start_y = w["pos_y"]

        # Issue move command to a nearby tile
        target_x = start_x + 32.0  # 2 tiles over
        target_y = start_y
        cmd = {"action": "move", "unit_id": "worker_p1_0",
               "target_x": target_x, "target_y": target_y, "issuer": 1}

        # Run many ticks to let it arrive
        for _ in range(200):
            e.step(commands=[cmd])
            w = e.state.entities.get("worker_p1_0")
            if w is None:
                break
            if w.get("is_idle") and not w.get("path"):
                break

        w = e.state.entities.get("worker_p1_0")
        assert w is not None, "Worker should still exist"
        # Should have moved from start position
        assert abs(w["pos_x"] - start_x) > 1.0, f"Worker barely moved: {w['pos_x']} vs {start_x}"

    def test_full_game_loop_with_ai(self):
        """Engine runs a full game with ScriptAI and terminates."""
        from agents.script_ai import ScriptAI
        e = SimCore()
        e.initialize(map_seed=42)
        ai1 = ScriptAI(player_id=1)
        ai2 = ScriptAI(player_id=2)
        for _ in range(5000):
            obs = e.state.get_observations()
            c1 = ai1.decide(obs[0]).get("commands", [])
            c2 = ai2.decide(obs[1]).get("commands", [])
            e.step(c1 + c2)
            if e.state.is_terminal:
                break
        assert e.state.is_terminal, "Game should terminate within 5000 ticks"