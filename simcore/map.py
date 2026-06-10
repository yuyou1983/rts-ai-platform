"""TileMap system for the RTS engine.

Provides terrain grid, elevation height_map, passability checks,
and building occupation tracking.
Default map: 64×64 tiles, each tile = 1 world unit (TILE_SIZE=1).

Elevation system (Phase D):
  - height_map[y][x]: integer 0–8, where 0=lowland, 8=peak
  - Cliff threshold: adjacent tiles with Δheight ≥ 3 are impassable (cliff)
  - Ramp threshold: adjacent tiles with Δheight ∈ [1,2] are walkable at speed cost
  - Vision bonus: +1 vision range per 2 height levels above base
"""

import random
import math
from dataclasses import dataclass, field

# Terrain types
PLAIN = 0
WATER = 1
MOUNTAIN = 2
CREEP = 3

TERRAIN_NAMES = {PLAIN: "plain", WATER: "water", MOUNTAIN: "mountain", CREEP: "creep"}

# Elevation constants
MAX_HEIGHT = 8
CLIFF_DELTA = 3       # height difference ≥ 3 → impassable cliff
RAMP_DELTA = 2         # height difference ≤ 2 → walkable ramp
HEIGHT_VISION_BONUS = 2  # +1 vision per 2 height levels

# High ground advantage constants (SC1 core mechanic)
HIGH_GROUND_THRESHOLD = 4  # height ≥ this is considered "high ground"
HIGH_GROUND_HIT_RATE = 0.70   # attacker on high ground → 70% hit
LOW_GROUND_HIT_RATE = 0.30    # attacker on low ground → 30% hit


@dataclass
class TileMap:
    width: int = 64
    height: int = 64
    tile_size: int = 1  # world coords = tile coords (no pixel scaling)
    terrain: list = field(default_factory=list)
    height_map: list = field(default_factory=list)  # elevation grid [0..8]
    occupied: set = field(default_factory=set)  # tiles blocked by buildings

    def __post_init__(self):
        if not self.terrain:
            self.terrain = [[PLAIN] * self.width for _ in range(self.height)]
        if not self.height_map:
            self.height_map = [[0] * self.width for _ in range(self.height)]

    # ── Elevation API ──────────────────────────────────────────────────

    def get_height(self, x: int, y: int) -> int:
        """Get elevation at tile (x, y). Out of bounds → 0."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.height_map[y][x]
        return 0

    def height_delta(self, x1: int, y1: int, x2: int, y2: int) -> int:
        """Absolute height difference between two tiles."""
        return abs(self.get_height(x1, y1) - self.get_height(x2, y2))

    def is_cliff(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """Check if movement from (x1,y1) to (x2,y2) is a cliff (impassable)."""
        return self.height_delta(x1, y1, x2, y2) >= CLIFF_DELTA

    def is_ramp(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """Check if movement is a ramp (walkable but slower)."""
        d = self.height_delta(x1, y1, x2, y2)
        return 1 <= d <= RAMP_DELTA

    def elevation_speed_mult(self, x1: int, y1: int, x2: int, y2: int) -> float:
        """Speed multiplier for movement between two tiles.

        - Uphill (ramp): 0.6× speed
        - Downhill (ramp): 0.85× speed
        - Cliff: 0.0 (impassable, but caller should check is_cliff first)
        - Flat: 1.0
        """
        if self.is_cliff(x1, y1, x2, y2):
            return 0.0
        h1 = self.get_height(x1, y1)
        h2 = self.get_height(x2, y2)
        delta = h2 - h1  # positive = uphill
        if delta > 0:
            return max(0.5, 1.0 - 0.2 * delta)
        elif delta < 0:
            return min(1.2, 1.0 + 0.05 * abs(delta))
        return 1.0

    def vision_bonus(self, x: int, y: int) -> int:
        """Extra vision range from elevation. +1 per 2 height levels."""
        h = self.get_height(x, y)
        return h // HEIGHT_VISION_BONUS

    def is_high_ground(self, x: int, y: int) -> bool:
        """Check if tile is considered high ground for combat purposes."""
        return self.get_height(x, y) >= HIGH_GROUND_THRESHOLD

    def high_ground_hit_chance(self, attacker_x: int, attacker_y: int,
                                target_x: int, target_y: int) -> float:
        """Calculate hit chance based on elevation difference.

        SC1 high ground advantage:
          - Attacker on high ground, target on low ground → 70% hit (30% miss)
          - Attacker on low ground, target on high ground → 30% hit (70% miss)
          - Same elevation → 100% hit

        Args:
            attacker_x, attacker_y: attacker tile position
            target_x, target_y: target tile position

        Returns:
            Hit probability (0.0 to 1.0).
        """
        a_high = self.is_high_ground(attacker_x, attacker_y)
        t_high = self.is_high_ground(target_x, target_y)
        if a_high and not t_high:
            return HIGH_GROUND_HIT_RATE
        elif not a_high and t_high:
            return LOW_GROUND_HIT_RATE
        return 1.0  # same elevation

    def get_elevation_grid(self) -> list[list[int]]:
        """Return a simplified 2-tier elevation grid (0=low, 1=high) for GameState.

        This is useful for storing in GameState when the full height_map is not needed.
        """
        return [
            [1 if self.height_map[y][x] >= HIGH_GROUND_THRESHOLD else 0
             for x in range(self.width)]
            for y in range(self.height)
        ]

    # ── Terrain API ──────────────────────────────────────────────────

    def get_terrain(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.terrain[y][x]
        return MOUNTAIN  # out of bounds = impassable

    def set_terrain(self, x: int, y: int, terrain_type: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.terrain[y][x] = terrain_type

    def is_passable(self, x: int, y: int, is_flying: bool = False,
                    from_x: int | None = None, from_y: int | None = None,
                    enable_elevation: bool = False) -> bool:
        """Check if a tile is passable for a unit.

        Args:
            x, y: target tile
            is_flying: flying units ignore terrain and elevation
            from_x, from_y: source tile (needed for elevation cliff check)
            enable_elevation: if True, check cliff/ramp constraints
        """
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return False
        t = self.terrain[y][x]
        if is_flying:
            return True  # flying units can go anywhere on the grid
        if t in (WATER, MOUNTAIN):
            return False
        if (x, y) in self.occupied:
            return False
        # Elevation cliff check
        if enable_elevation and from_x is not None and from_y is not None:
            if self.is_cliff(from_x, from_y, x, y):
                return False
        return True

    # ── Building occupation ──────────────────────────────────────────

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
        """Free tiles previously occupied by a building."""
        if len(args) == 1 and isinstance(args[0], (list, tuple, set)):
            for t in args[0]:
                self.occupied.discard(tuple(t))
        elif len(args) == 2 and isinstance(args[0], int):
            self.occupied.discard((args[0], args[1]))

    # ── Coordinate conversion ────────────────────────────────────────

    def tile_to_world(self, tx: int, ty: int) -> tuple:
        """Convert tile coords to world coords (center of tile)."""
        return (tx + 0.5) * self.tile_size, (ty + 0.5) * self.tile_size

    def world_to_tile(self, wx: float, wy: float) -> tuple:
        """Convert world coords to tile coords."""
        return int(wx / self.tile_size), int(wy / self.tile_size)

    # ── Backward compat ──────────────────────────────────────────────

    @property
    def tiles(self) -> list:
        """Alias for terrain grid (backward compatibility)."""
        return self.terrain

    def is_occupied(self, x: int, y: int) -> bool:
        """Check if a tile is occupied by a building."""
        return (x, y) in self.occupied

    # ── Serialization ─────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, d: dict) -> "TileMap":
        """Reconstruct TileMap from serialized dict."""
        tm = cls(width=d["width"], height=d["height"], tile_size=d.get("tile_size", 1))
        tm.terrain = d.get("terrain", [[PLAIN] * tm.width for _ in range(tm.height)])
        tm.height_map = d.get("height_map", [[0] * tm.width for _ in range(tm.height)])
        occ = d.get("occupied", [])
        for t in occ:
            tm.occupied.add(tuple(t))
        return tm

    def to_dict(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "tile_size": self.tile_size,
            "terrain": self.terrain,
            "height_map": self.height_map,
            "occupied": [list(t) for t in self.occupied],
        }

    # ── Procedural Generation ─────────────────────────────────────────

    @classmethod
    def generate(cls, seed: int = 42, width: int = 64, height: int = 64,
                 water_pct: float = 0.003, mountain_pct: float = 0.003,
                 enable_elevation: bool = True) -> "TileMap":
        """Procedurally generate a map with terrain and elevation.

        Elevation generation uses diamond-square algorithm for natural
        hills and valleys. Terrain types are set based on height:
          - height 0-1: PLAIN (or WATER for lowest valleys)
          - height 2-5: PLAIN (hills)
          - height 6-7: PLAIN with steep slopes
          - height 8+: treated as MOUNTAIN
        """
        rng = random.Random(seed)
        tm = cls(width=width, height=height)

        # Generate elevation via diamond-square
        if enable_elevation:
            tm.height_map = _generate_height_map(width, height, seed)
            # Set terrain based on elevation
            for y in range(height):
                for x in range(width):
                    h = tm.height_map[y][x]
                    if h >= MAX_HEIGHT:
                        tm.terrain[y][x] = MOUNTAIN
                    elif h == 0 and rng.random() < 0.15:
                        tm.terrain[y][x] = WATER
                    else:
                        tm.terrain[y][x] = PLAIN
        else:
            # Original generation without elevation
            for _ in range(int(width * height * water_pct)):
                cx, cy = rng.randint(0, width - 1), rng.randint(0, height - 1)
                r = rng.randint(1, 3)
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < width and 0 <= ny < height and dx*dx + dy*dy <= r*r:
                            tm.terrain[ny][nx] = WATER
            for _ in range(int(width * height * mountain_pct)):
                cx, cy = rng.randint(0, width - 1), rng.randint(0, height - 1)
                r = rng.randint(1, 2)
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            if tm.terrain[ny][nx] == PLAIN and dx*dx + dy*dy <= r*r:
                                tm.terrain[ny][nx] = MOUNTAIN

        # Clear starting areas (top-left and bottom-right corners)
        for by in range(12):
            for bx in range(12):
                tm.terrain[by][bx] = PLAIN
                tm.terrain[height - 1 - by][width - 1 - bx] = PLAIN
                # Flatten starting areas to height 0
                if enable_elevation:
                    tm.height_map[by][bx] = 0
                    tm.height_map[height - 1 - by][width - 1 - bx] = 0
                    # Also flatten a buffer zone around starts
                    if bx < 10 and by < 10:
                        tm.height_map[by][bx] = 0
                        tm.height_map[height - 1 - by][width - 1 - bx] = 0

        return tm


# ── Diamond-Square Height Map Generator ──────────────────────────────

def _generate_height_map(width: int, height: int, seed: int,
                         roughness: float = 0.7) -> list[list[int]]:
    """Generate a height map using diamond-square interpolation.

    Works on a power-of-2 grid, then crops/fills to the requested size.
    Returns integer grid [0..MAX_HEIGHT].
    """
    # Find smallest power of 2 that covers the map
    size = 1
    while size < max(width, height):
        size *= 2
    size += 1  # diamond-square needs 2^n + 1

    rng = random.Random(seed)
    grid = [[0.0] * size for _ in range(size)]

    # Seed corners
    grid[0][0] = rng.uniform(0, MAX_HEIGHT * 0.5)
    grid[0][size-1] = rng.uniform(0, MAX_HEIGHT * 0.5)
    grid[size-1][0] = rng.uniform(0, MAX_HEIGHT * 0.5)
    grid[size-1][size-1] = rng.uniform(0, MAX_HEIGHT * 0.5)

    step = size - 1
    scale = roughness * MAX_HEIGHT * 0.5

    while step > 1:
        half = step // 2

        # Diamond step
        for y in range(0, size - 1, step):
            for x in range(0, size - 1, step):
                avg = (grid[y][x] + grid[y][x+step] +
                       grid[y+step][x] + grid[y+step][x+step]) / 4.0
                grid[y + half][x + half] = avg + rng.uniform(-scale, scale)

        # Square step
        for y in range(0, size, half):
            for x in range((y + half) % step, size, step):
                neighbors = []
                if y >= half:
                    neighbors.append(grid[y - half][x])
                if y + half < size:
                    neighbors.append(grid[y + half][x])
                if x >=half:
                    neighbors.append(grid[y][x - half])
                if x + half < size:
                    neighbors.append(grid[y][x + half])
                avg = sum(neighbors) / len(neighbors)
                grid[y][x] = avg + rng.uniform(-scale, scale)

        step = half
        scale *= roughness

    # Normalize to [0, MAX_HEIGHT] and crop to requested size
    flat = [grid[y][x] for y in range(size) for x in range(size)]
    lo, hi = min(flat), max(flat)
    rng_range = hi - lo if hi > lo else 1.0

    result = [[0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if x < size and y < size:
                normalized = (grid[y][x] - lo) / rng_range
                result[y][x] = max(0, min(MAX_HEIGHT, int(round(normalized * MAX_HEIGHT))))
            else:
                result[y][x] = 0

    return result


def generate_tile_map(seed: int = 42, config: dict | None = None) -> TileMap:
    """Convenience function to generate a TileMap (compatible with engine import)."""
    cfg = config or {}
    return TileMap.generate(
        seed=seed,
        width=cfg.get("map_width", 64),
        height=cfg.get("map_height", 64),
        water_pct=cfg.get("water_pct", 0.003),
        mountain_pct=cfg.get("mountain_pct", 0.003),
        enable_elevation=cfg.get("enable_elevation", False),
    )