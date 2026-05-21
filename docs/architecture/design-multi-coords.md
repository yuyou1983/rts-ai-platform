# Design: Multi-Level Coordinate System

## Current State
- pos_x / pos_y = world coords = tile coords (TILE_SIZE=1)
- Godot renders pos_x/pos_y directly
- Pathfinding: simcore/pathfinder.py operates on build-tile grid (TileMap.world_to_tile)
- Collision: simcore/movement.py uses world coords with radius-based separation
- Fog: simcore/rules.py maps world coords to fog grid (scaled by fw/fh)
- Map size: typically 64×64 build tiles

## Proposed Addition (NOT replacement)
- KEEP pos_x/pos_y as-is (backward compat)
- Add COMPUTED properties to entity dicts:
  - build_tile_x, build_tile_y: integer grid position (same as current world_to_tile)
  - walk_tile_x, walk_tile_y: 4× resolution of build tile (8 walk tiles per build tile)
  - pixel_x, pixel_y: sub-walk-tile precision (8 pixels per walk tile = 32px per build tile)

## Scale Factors
- 1 build tile = 4 walk tiles (each direction)
- 1 walk tile = 8 pixels (each direction)  
- 1 build tile = 32 pixels
- Current TILE_SIZE=1 means 1 world unit = 1 build tile = 32 conceptual pixels

## Migration Path
1. Phase A: Add computed coordinate fields to GameState (no behavior change)
   - Entity dicts get build_tile_x/y, walk_tile_x/y, pixel_x/y as derived values
   - These are COMPUTED from pos_x/pos_y, not stored separately
2. Phase B: Move pathfinding to walk-tile grid
   - Pathfinder gets a walk-tile walkability grid
   - Much finer obstacle avoidance (buildings block build tiles, small units block walk tiles)
3. Phase C: Move collision to walk-tile grid
   - Collision separation uses walk-tile grid for precision
4. Phase D: Godot optionally reads pixel_x/y for smoother rendering
   - Sub-tile interpolation for unit movement
5. Phase E: Fog mapping uses walk-tile grid
   - Finer fog resolution

## Rollback
- All new fields are computed. Removing computation = revert.
- pos_x/pos_y never change meaning.
- enable_elevation feature flag for when elevation system is built on top of this.

## Impact Analysis
- Protocol: New fields in V2 proto only
- Godot: No change required (continues using pos_x/pos_y)
- Agent: Can use walk_tile coords for finer control (optional)
- Pathfinder: Biggest beneficiary (walk-tile precision)
- Tests: Must add coordinate property tests before migration