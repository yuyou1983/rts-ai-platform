"""Procedural map generation — deterministic from seed."""
from __future__ import annotations

import math

from simcore.state import GameState


def _seeded_random(seed: int) -> float:
    """Simple LCG-based pseudo-random for deterministic generation.

    Not cryptographically secure — only for game determinism.
    """
    state = seed
    def next_val() -> float:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    return next_val


def generate_map(seed: int = 42, config: dict | None = None) -> GameState:
    """Generate initial game state from seed and config.

    Standard layout:
    - 64x64 tile map
    - 2 bases at opposite corners (p1 bottom-left, p2 top-right)
    - 4 mineral patches near each base
    - 2 gas geysers near each base
    - 6 starting workers per player

    Args:
        seed: Random seed for deterministic generation.
        config: Override defaults (map_size, starting_workers, resource_density, etc.).

    Returns:
        Initial GameState with starting entities and resources.
    """
    cfg = config or {}
    map_size = cfg.get("map_size", 64)
    starting_workers = cfg.get("starting_workers", 6)
    resource_density = cfg.get("resource_density", 1.0)

    rng = _seeded_random(seed)

    entities: dict = {}
    resources: dict = {
        "p1_mineral": cfg.get("starting_mineral", 200),
        "p1_gas": cfg.get("starting_gas", 0),
        "p2_mineral": cfg.get("starting_mineral", 200),
        "p2_gas": cfg.get("starting_gas", 0),
    }

    # Player 1 base (bottom-left quadrant)
    p1_base_x, p1_base_y = map_size * 0.15, map_size * 0.15
    entities["base_p1"] = {
        "id": "base_p1",
        "owner": 1,
        "entity_type": "building",
        "building_type": "base",
        "pos_x": p1_base_x,
        "pos_y": p1_base_y,
        "health": 1500,
        "max_health": 1500,
        "is_constructing": False,
        "production_queue": [],
    }

    # Player 2 base (top-right quadrant)
    p2_base_x, p2_base_y = map_size * 0.85, map_size * 0.85
    entities["base_p2"] = {
        "id": "base_p2",
        "owner": 2,
        "entity_type": "building",
        "building_type": "base",
        "pos_x": p2_base_x,
        "pos_y": p2_base_y,
        "health": 1500,
        "max_health": 1500,
        "is_constructing": False,
        "production_queue": [],
    }

    # Mineral patches near each base
    for pid, bx, by in [(1, p1_base_x, p1_base_y), (2, p2_base_x, p2_base_y)]:
        for i in range(4):
            rid = f"mineral_p{pid}_{i}"
            angle = i * math.pi / 2 + rng() * 0.3
            offset = 4 + rng() * 2
            entities[rid] = {
                "id": rid,
                "owner": 0,  # neutral
                "entity_type": "resource",
                "resource_type": "mineral",
                "pos_x": bx + math.cos(angle) * offset,
                "pos_y": by + math.sin(angle) * offset,
                "resource_amount": int(1500 * resource_density),
            }

        # Gas geysers
        for i in range(2):
            gid = f"gas_p{pid}_{i}"
            angle = math.pi / 4 + i * math.pi / 2 + rng() * 0.3
            offset = 5 + rng() * 2
            entities[gid] = {
                "id": gid,
                "owner": 0,
                "entity_type": "resource",
                "resource_type": "gas",
                "pos_x": bx + math.cos(angle) * offset,
                "pos_y": by + math.sin(angle) * offset,
                "resource_amount": int(2000 * resource_density),
            }

    # Starting workers
    for pid, bx, by in [(1, p1_base_x, p1_base_y), (2, p2_base_x, p2_base_y)]:
        for i in range(starting_workers):
            uid = f"worker_p{pid}_{i}"
            angle = i * 2 * math.pi / starting_workers
            offset = 2.0
            entities[uid] = {
                "id": uid,
                "owner": pid,
                "entity_type": "worker",
                "pos_x": bx + math.cos(angle) * offset,
                "pos_y": by + math.sin(angle) * offset,
                "health": 50,
                "max_health": 50,
                "speed": 2.5,
                "attack": 5,
                "attack_range": 1.0,
                "is_idle": True,
                "carry_amount": 0,
                "carry_capacity": 10.0,
            }

    # Central mineral patches (contested)
    center = map_size / 2
    for i in range(4):
        rid = f"mineral_center_{i}"
        angle = i * math.pi / 2 + rng() * 0.5
        offset = 5 + rng() * 3
        entities[rid] = {
            "id": rid,
            "owner": 0,
            "entity_type": "resource",
            "resource_type": "mineral",
            "pos_x": center + math.cos(angle) * offset,
            "pos_y": center + math.sin(angle) * offset,
            "resource_amount": int(2000 * resource_density),
        }

    # Fog-of-war: start fully unexplored (0) except near bases
    fog_width = map_size // 4  # downsampled grid
    fog_height = map_size // 4
    total_tiles = fog_width * fog_height
    fog_tiles = [0] * total_tiles  # 0=unexplored

    # Reveal area around each base
    reveal_radius = 4  # in fog-grid tiles
    for bx, by in [(p1_base_x, p1_base_y), (p2_base_x, p2_base_y)]:
        fg_x = int(bx / map_size * fog_width)
        fg_y = int(by / map_size * fog_height)
        for dy in range(-reveal_radius, reveal_radius + 1):
            for dx in range(-reveal_radius, reveal_radius + 1):
                gx, gy = fg_x + dx, fg_y + dy
                if (0 <= gx < fog_width and 0 <= gy < fog_height
                        and dx*dx + dy*dy <= reveal_radius*reveal_radius):
                    fog_tiles[gy * fog_width + gx] = 2  # visible

    fog_data = {
        "tiles": fog_tiles,
        "width": fog_width,
        "height": fog_height,
    }

    return GameState(
        tick=0,
        entities=entities,
        fog_of_war=fog_data,
        resources=resources,
        is_terminal=False,
    )
