"""Movement & collision separation system.

Handles:
  - Advancing entities along their A* path waypoints
  - Collision separation: push apart overlapping ground units each tick
  - Flying units don't collide with ground units
"""
from __future__ import annotations

import math
from typing import Any

from simcore.map import TileMap

TILE_SIZE = 1  # world coords are tile coords (no pixel scaling)


def move_entities(
    entities: dict[str, Any],
    dt: float = 1.0,
    tile_map: TileMap | None = None,
) -> dict[str, Any]:
    """Advance all entities one tick along their paths.

    Each entity dict should have:
      - pos_x, pos_y: current world position
      - path: list of (tile_x, tile_y) waypoints from A*
      - speed: pixels per tick
      - is_flying: bool
      - target_x, target_y: final destination (set for compatibility)

    When entity reaches the final waypoint, it stops and is marked idle.

    Args:
        entities: Dict of entity_id → entity dict
        dt: Delta time (default 1 tick)
        tile_map: Optional TileMap for coordinate conversion

    Returns:
        Updated entities dict
    """
    moved = dict(entities)

    for uid, e in list(moved.items()):
        if e.get("entity_type") not in ("worker", "soldier", "scout"):
            continue

        path = list(e.get("path", []))
        if not path:
            continue

        # Skip the first waypoint if we're already at or near it
        if tile_map is not None:
            current_tile = tile_map.world_to_tile(e["pos_x"], e["pos_y"])
            while path and path[0] == current_tile:
                path = path[1:]
        else:
            # Without a tile_map, check proximity to first waypoint center
            first_tx, first_ty = path[0]
            first_wx = first_tx * TILE_SIZE + TILE_SIZE * 0.5
            first_wy = first_ty * TILE_SIZE + TILE_SIZE * 0.5
            dist_to_first = math.hypot(e["pos_x"] - first_wx, e["pos_y"] - first_wy)
            if dist_to_first < 1.0:
                path = path[1:]

        if not path:
            # Already at all waypoints — arrived but keep target for apply_movement
            moved[uid] = {
                **e,
                "path": [],
                "is_idle": True,
                # Keep target_x/y intact for apply_movement to continue
            }
            continue

        # Get current waypoint (first in remaining path)
        target_tx, target_ty = path[0]

        # Convert tile target to world coordinates (tile center)
        target_wx = target_tx * TILE_SIZE + TILE_SIZE * 0.5
        target_wy = target_ty * TILE_SIZE + TILE_SIZE * 0.5

        cx, cy = e["pos_x"], e["pos_y"]
        dx = target_wx - cx
        dy = target_wy - cy
        dist = math.sqrt(dx * dx + dy * dy)

        speed = e.get("speed", 2.0)

        if dist <= speed * dt:
            # Reached this waypoint — snap to tile center and advance
            e = {**e, "pos_x": target_wx, "pos_y": target_wy}
            new_path = path[1:]
            if not new_path:
                # Reached final A* waypoint — become idle but keep target_x/y
                # so apply_movement can continue direct-line movement to target
                moved[uid] = {
                    **e,
                    "path": [],
                    "is_idle": True,
                    # Keep target_x/y intact for apply_movement to continue
                }
            else:
                moved[uid] = {**e, "path": new_path, "is_idle": False}
        else:
            # Move toward waypoint
            nx = cx + (dx / dist) * speed * dt
            ny = cy + (dy / dist) * speed * dt
            moved[uid] = {**e, "pos_x": nx, "pos_y": ny, "is_idle": False}

    return moved


def collision_separate(entities: dict[str, Any]) -> dict[str, Any]:
    """Push apart overlapping ground units each tick.

    Ground units that are too close get pushed apart.
    Flying units don't collide with ground units.

    Args:
        entities: Dict of entity_id → entity dict

    Returns:
        Updated entities dict with positions adjusted
    """
    SEPARATION_RADIUS = 1.5  # world units minimum distance
    PUSH_STRENGTH = 0.5  # how much to push per tick

    result = dict(entities)
    ground_units = [
        (uid, e) for uid, e in result.items()
        if e.get("entity_type") in ("worker", "soldier", "scout")
        and not e.get("is_flying", False)
    ]

    # Build displacement map
    displacements: dict[str, tuple[float, float]] = {}

    for i in range(len(ground_units)):
        uid_i, ei = ground_units[i]
        for j in range(i + 1, len(ground_units)):
            uid_j, ej = ground_units[j]
            dx = ei["pos_x"] - ej["pos_x"]
            dy = ei["pos_y"] - ej["pos_y"]
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < SEPARATION_RADIUS and dist > 0:
                # Push apart
                overlap = SEPARATION_RADIUS - dist
                nx, ny = dx / dist, dy / dist
                push = overlap * PUSH_STRENGTH

                # Add displacements
                dix, diy = displacements.get(uid_i, (0.0, 0.0))
                displacements[uid_i] = (dix + nx * push, diy + ny * push)

                djx, djy = displacements.get(uid_j, (0.0, 0.0))
                displacements[uid_j] = (djx - nx * push, djy - ny * push)
            elif dist == 0:
                # Exactly overlapping — push in arbitrary direction
                push = SEPARATION_RADIUS * PUSH_STRENGTH
                dix, diy = displacements.get(uid_i, (0.0, 0.0))
                displacements[uid_i] = (dix + push, diy)
                djx, djy = displacements.get(uid_j, (0.0, 0.0))
                displacements[uid_j] = (djx - push, djy)

    # Apply displacements
    for uid, (dx, dy) in displacements.items():
        e = result[uid]
        result[uid] = {**e, "pos_x": e["pos_x"] + dx, "pos_y": e["pos_y"] + dy}

    return result


def is_at_target(entity: dict[str, Any]) -> bool:
    """Check if entity has reached its target position.

    An entity is at target if it has no path remaining and no target coords,
    or if it's within a small threshold of its target.

    Args:
        entity: Entity dict with pos_x, pos_y, target_x, target_y, path

    Returns:
        True if the entity is at its target destination.
    """
    # If there are path waypoints remaining, not at target
    if entity.get("path"):
        return False

    # No path and idle — at target
    if entity.get("is_idle", True):
        return True

    # Check distance to explicit target
    tx = entity.get("target_x")
    ty = entity.get("target_y")
    if tx is None or ty is None:
        return True

    dist = math.hypot(entity["pos_x"] - tx, entity["pos_y"] - ty)
    return dist < 1.0