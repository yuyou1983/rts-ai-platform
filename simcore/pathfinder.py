"""A* pathfinding engine — 8-directional, with path smoothing.

Features:
  - 8-directional movement (diagonal cost = sqrt(2))
  - Flying units: only WATER/MOUNTAIN block; ignore ground obstacles
  - Ground units: avoid WATER, MOUNTAIN, and building-occupied tiles
  - Path smoothing: remove collinear waypoints
  - Max search depth 2000 nodes to prevent stalls
  - Return empty list if no path found
"""
from __future__ import annotations

import heapq
import math
from typing import Any

from simcore.map import TileMap, MOUNTAIN, WATER

SQRT2 = math.sqrt(2)
MAX_SEARCH_DEPTH = 2000

# 8-directional offsets: (dx, dy, cost)
DIRECTIONS = [
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
    (1, 1, SQRT2),
    (-1, 1, SQRT2),
    (1, -1, SQRT2),
    (-1, -1, SQRT2),
]


def find_path(
    start: tuple[int, int],
    end: tuple[int, int],
    tile_map: TileMap,
    is_flying: bool = False,
    occupied: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """Find the shortest path from start to end using A*.

    Args:
        start: (x, y) tile coordinates.
        end: (x, y) tile coordinates.
        tile_map: The TileMap to pathfind on.
        is_flying: If True, ignore ground obstacles and building-occupied tiles.
        occupied: Additional set of blocked tiles (buildings). If None, use
                  tile_map.occupied.

    Returns:
        List of (x, y) tile waypoints from start to end (inclusive).
        Empty list if no path found.
    """
    if occupied is None:
        occupied = tile_map.occupied

    # Quick check: if end is impassable, no path
    if not _is_tile_passable(end[0], end[1], tile_map, is_flying, occupied):
        # For ground units, the end might be occupied by a building we want to
        # reach — allow pathing to adjacent tile instead
        if not is_flying and (end[0], end[1]) in occupied:
            # Find nearest passable neighbor to end
            best_neighbor = None
            best_dist = float("inf")
            for dx, dy, _ in DIRECTIONS:
                nx, ny = end[0] + dx, end[1] + dy
                if _is_tile_passable(nx, ny, tile_map, is_flying, occupied):
                    d = abs(dx) + abs(dy)
                    if d < best_dist:
                        best_dist = d
                        best_neighbor = (nx, ny)
            if best_neighbor is not None:
                result = find_path(start, best_neighbor, tile_map, is_flying, occupied)
                return result
        return []

    # A* search
    sx, sy = start
    ex, ey = end

    # Heuristic: octile distance
    def heuristic(x: int, y: int) -> float:
        dx = abs(x - ex)
        dy = abs(y - ey)
        return max(dx, dy) + (SQRT2 - 1) * min(dx, dy)

    # Priority queue: (f, g, x, y)
    open_set: list[tuple[float, float, int, int]] = []
    heapq.heappush(open_set, (heuristic(sx, sy), 0.0, sx, sy))

    # Track visited and costs
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {(sx, sy): 0.0}
    closed: set[tuple[int, int]] = set()
    nodes_explored = 0

    while open_set and nodes_explored < MAX_SEARCH_DEPTH:
        _f, g, x, y = heapq.heappop(open_set)

        if (x, y) in closed:
            continue
        closed.add((x, y))
        nodes_explored += 1

        if (x, y) == (ex, ey):
            # Reconstruct path
            path = _reconstruct(came_from, (ex, ey))
            return smooth_path(path)

        for dx, dy, cost in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if (nx, ny) in closed:
                continue
            if not _is_tile_passable(nx, ny, tile_map, is_flying, occupied):
                continue
            # For diagonal moves, ensure both cardinal neighbors are passable
            # to avoid cutting through walls
            if dx != 0 and dy != 0:
                if not _is_tile_passable(x + dx, y, tile_map, is_flying, occupied):
                    continue
                if not _is_tile_passable(x, y + dy, tile_map, is_flying, occupied):
                    continue

            new_g = g + cost
            if new_g < g_score.get((nx, ny), float("inf")):
                g_score[(nx, ny)] = new_g
                came_from[(nx, ny)] = (x, y)
                f = new_g + heuristic(nx, ny)
                heapq.heappush(open_set, (f, new_g, nx, ny))

    # No path found
    return []


def _is_tile_passable(
    x: int, y: int,
    tile_map: TileMap,
    is_flying: bool,
    occupied: set[tuple[int, int]],
) -> bool:
    """Check if a single tile is passable for the given movement type."""
    if x < 0 or x >= tile_map.width or y < 0 or y >= tile_map.height:
        return False
    terrain = tile_map.get_terrain(x, y)
    if is_flying:
        # Flying units can go over water and ground obstacles
        return True
    # Ground units: blocked by WATER, MOUNTAIN, and building-occupied tiles
    if terrain in (WATER, MOUNTAIN):
        return False
    if (x, y) in occupied:
        return False
    return True


def _reconstruct(
    came_from: dict[tuple[int, int], tuple[int, int]],
    end: tuple[int, int],
) -> list[tuple[int, int]]:
    """Reconstruct path from A* came_from map."""
    path: list[tuple[int, int]] = [end]
    current = end
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def smooth_path(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove unnecessary collinear waypoints from a path.

    If three consecutive points are on a straight line (horizontal, vertical,
    or diagonal), the middle point is redundant and can be removed.

    Args:
        path: List of (x, y) tile coordinates.

    Returns:
        Simplified path with collinear waypoints removed.
    """
    if len(path) <= 2:
        return list(path)

    result: list[tuple[int, int]] = [path[0]]
    for i in range(1, len(path) - 1):
        px, py = result[-1]
        cx, cy = path[i]
        nx, ny = path[i + 1]

        # Check if (px,py) → (cx,cy) → (nx,ny) is collinear
        dx1 = cx - px
        dy1 = cy - py
        dx2 = nx - cx
        dy2 = ny - cy

        # Normalize direction to unit steps
        step1 = (int(dx1 / max(abs(dx1), abs(dy1), 1)),
                 int(dy1 / max(abs(dx1), abs(dy1), 1)))
        step2 = (int(dx2 / max(abs(dx2), abs(dy2), 1)),
                 int(dy2 / max(abs(dx2), abs(dy2), 1)))

        if step1 != step2:
            result.append(path[i])

    result.append(path[-1])
    return result