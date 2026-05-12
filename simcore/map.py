"""TileMap system for the RTS engine.

Provides terrain grid, passability checks, and building occupation tracking.
Default map: 64×64 tiles, each tile = 16 pixels in Godot coordinates.
"""

import random
from dataclasses import dataclass, field

# Terrain types
PLAIN = 0
WATER = 1
MOUNTAIN = 2
CREEP = 3

TERRAIN_NAMES = {PLAIN: "plain", WATER: "water", MOUNTAIN: "mountain", CREEP: "creep"}


@dataclass
class TileMap:
    width: int = 64
    height: int = 64
    tile_size: int = 1  # world coords = tile coords (no pixel scaling)
    terrain: list = field(default_factory=list)
    occupied: set = field(default_factory=set)  # tiles blocked by buildings

    def __post_init__(self):
        if not self.terrain:
            self.terrain = [[PLAIN] * self.width for _ in range(self.height)]

    @classmethod
    def generate(cls, seed: int = 42, width: int = 64, height: int = 64,
                 water_pct: float = 0.003, mountain_pct: float = 0.003) -> "TileMap":
        """Procedurally generate a map with water and mountain patches.
        
        water_pct / mountain_pct control the NUMBER of patch centers as a
        fraction of total tiles.  Actual coverage depends on patch radius.
        Keep these very low (≤0.005) to avoid blocking the map.
        """
        rng = random.Random(seed)
        tm = cls(width=width, height=height)
        # Place water patches
        for _ in range(int(width * height * water_pct)):
            cx, cy = rng.randint(0, width - 1), rng.randint(0, height - 1)
            r = rng.randint(1, 3)
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < width and 0 <= ny < height and dx * dx + dy * dy <= r * r:
                        tm.terrain[ny][nx] = WATER
        # Place mountain patches
        for _ in range(int(width * height * mountain_pct)):
            cx, cy = rng.randint(0, width - 1), rng.randint(0, height - 1)
            r = rng.randint(1, 2)
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        if tm.terrain[ny][nx] == PLAIN and dx * dx + dy * dy <= r * r:
                            tm.terrain[ny][nx] = MOUNTAIN
        # Clear starting areas (top-left and bottom-right corners)
        for by in range(12):
            for bx in range(12):
                tm.terrain[by][bx] = PLAIN
                tm.terrain[height - 1 - by][width - 1 - bx] = PLAIN
        return tm

    def get_terrain(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.terrain[y][x]
        return MOUNTAIN  # out of bounds = impassable

    def set_terrain(self, x: int, y: int, terrain_type: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.terrain[y][x] = terrain_type

    def is_passable(self, x: int, y: int, is_flying: bool = False) -> bool:
        """Check if a tile is passable for a unit."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return False
        t = self.terrain[y][x]
        if is_flying:
            return True  # flying units can go anywhere on the grid
        if t in (WATER, MOUNTAIN):
            return False
        if (x, y) in self.occupied:
            return False
        return True

    def occupy(self, *args) -> None:
        """Mark tiles as occupied by a building.
        
        Supports both:
          occupy([(3,3), (4,4)])  — list of tuples
          occupy(3, 3)           — single tile as two ints
        """
        if len(args) == 1 and isinstance(args[0], (list, tuple, set)):
            for t in args[0]:
                self.occupied.add(tuple(t))
        elif len(args) == 2 and isinstance(args[0], int):
            self.occupied.add((args[0], args[1]))
        elif len(args) >= 1:
            for t in args:
                self.occupied.add(tuple(t))

    def free(self, *args) -> None:
        """Free tiles previously occupied by a building.
        
        Supports both:
          free([(3,3), (4,4)])  — list of tuples
          free(3, 3)           — single tile as two ints
        """
        if len(args) == 1 and isinstance(args[0], (list, tuple, set)):
            for t in args[0]:
                self.occupied.discard(tuple(t))
        elif len(args) == 2 and isinstance(args[0], int):
            self.occupied.discard((args[0], args[1]))

    def tile_to_world(self, tx: int, ty: int) -> tuple:
        """Convert tile coords to world (pixel) coords (center of tile)."""
        return (tx + 0.5) * self.tile_size, (ty + 0.5) * self.tile_size

    def world_to_tile(self, wx: float, wy: float) -> tuple:
        """Convert world (pixel) coords to tile coords."""
        return int(wx / self.tile_size), int(wy / self.tile_size)

    @property
    def tiles(self) -> list:
        """Alias for terrain grid (backward compatibility)."""
        return self.terrain

    def is_occupied(self, x: int, y: int) -> bool:
        """Check if a tile is occupied by a building."""
        return (x, y) in self.occupied

    @classmethod
    def from_dict(cls, d: dict) -> "TileMap":
        """Reconstruct TileMap from serialized dict."""
        tm = cls(width=d["width"], height=d["height"], tile_size=d.get("tile_size", 1))
        tm.terrain = d.get("terrain", [[PLAIN] * tm.width for _ in range(tm.height)])
        occ = d.get("occupied", [])
        for t in occ:
            tm.occupied.add(tuple(t))
        return tm

    def to_dict(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "tile_size": self.tile_size,
            "terrain": self.terrain,
            "occupied": [list(t) for t in self.occupied],
        }


def generate_tile_map(seed: int = 42, config: dict | None = None) -> TileMap:
    """Convenience function to generate a TileMap (compatible with engine import)."""
    cfg = config or {}
    return TileMap.generate(
        seed=seed,
        width=cfg.get("map_width", 64),
        height=cfg.get("map_height", 64),
        water_pct=cfg.get("water_pct", 0.003),
        mountain_pct=cfg.get("mountain_pct", 0.003),
    )