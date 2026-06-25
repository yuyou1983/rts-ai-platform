# EntitySpriteManager Extraction Design

**File**: `godot/scripts/game_view.gd` — ~2,800 lines  
**Target**: Extract Entity Rendering System (~380 lines) into `EntitySpriteManager`  
**Date**: 2026-06-24  

---

## 1. Overview

`game_view.gd` contains all entity sprite lifecycle management — visual identity resolution, sprite pool bookkeeping, atlas region calculation, fog-based visibility, and entity canvas drawing — interleaved with HUD overlays, input handling, and game state parsing. This extraction isolates the sprite subsystem into a dedicated `Node2D`, reducing `game_view.gd` by ~380 lines and establishing a clean boundary for future sprite/rendering work.

---

## 2. Functions That Move

| # | Function | Current Lines | LOC | Notes |
|---|----------|--------------|-----|-------|
| 1 | `_load_presentation_manifest` | 1450–1460 | 11 | JSON loader for manifest |
| 2 | `_resolve_visual_id` | 1463–1484 | 22 | Race-aware visual ID resolution |
| 3 | `_is_known_unit_visual` | 1486–1490 | 5 | Manifest + SpriteLoader lookup |
| 4 | `_is_known_building_visual` | 1492–1496 | 5 | Manifest + SpriteLoader lookup |
| 5 | `_is_building_entity_visual` | 1498–1499 | 2 | Dual check (type + known visual) |
| 6 | `_visual_scale` | 1501–1511 | 11 | Manifest / SpriteLoader scale |
| 7 | `_visual_radius` | 1513–1526 | 14 | Clamped radius for selection ring |
| 8 | `_unit_animation_key` | 1528–1541 | 14 | Derives animation name from entity state |
| 9 | `_calc_unit_region` | 1929–1966 | 38 | Atlas region math for unit sprites |
| 10 | `_get_building_region` | 1971–2025 | 55 | Race-aware building atlas regions |
| 11 | `_has_building_region_override` | 2027–2030 | 4 | Always false (legacy stub) |
| 12 | `_has_unit_region_override` | 2032–2033 | 2 | Checks worker/soldier/scout |
| 13 | `_get_unit_region_override` | 2035–2053 | 19 | Returns texture_key + region + scale |
| 14 | `_update_entity_sprites` | 2056–2193 | 138 | Sprite pool sync — the hot loop |
| 15 | `_draw_entities` | 2195–2231 | 37 | Canvas resource circles + target lines |
| 16 | `_is_in_fog` | 2233–2246 | 14 | Fog-alpha-based visibility check |

**Total**: ~392 lines moved (16 functions).

---

## 3. Variables That Move

| Variable | Type | Current Line | Notes |
|----------|------|-------------|-------|
| `_unit_textures` | `Dictionary` | 161 | Preloaded unit sprite sheets (keyed `"type_race"`) |
| `_building_textures` | `Dictionary` | 162 | Preloaded building atlases (keyed by race int) |
| `_player_races` | `Dictionary` | 163 | Maps player ID → race ID (`"1"`→`"1"`, etc.) |
| `_sprite_pool` | `Dictionary` | 164 | entity_id → `Sprite2D`/`AnimatedSprite2D` |
| `_sprite_container` | `Node2D` | 165 | Parent node for all entity Sprite2D children |
| `_sprite_loader` | `SpriteLoader` | 167 | Atlas + SpriteFrames loader |
| `_presentation_manifest` | `Dictionary` | 168 | Parsed `presentation_manifest.json` |
| `_entity_cache_by_id` | `Dictionary` | 180 | entity_id → entity dict (shared with HUDOverlayRenderer) |
| `_unit_anim_info` | `Dictionary` | 105 | Per-unit animation metadata (rows, cols, fw, fh, south) |
| `_anim_frame` | `int` | 101 | Current animation frame index |
| `_anim_tick` | `float` | 102 | Animation tick accumulator (unused but kept for compat) |
| `ANIM_FPS` | `const float` | 103 | 8.0 — frames per second for walk cycle |

**Not moved** (remain in `game_view.gd`):
- `_map_texture` (line 169) — used only in `_draw_map_background`
- `_vfx_manager` (line 166) — VFX spawning stays in game_view
- `_ents` (line 54) — owned by game_view, passed into EntitySpriteManager
- `_fog_tiles`, `_fog_w`, `_fog_h`, `_fog_alpha` (lines 134–139) — owned by game_view, passed in
- `_test_gallery` (line 96) — separate extraction
- `_selected` (line 479) — owned by SelectionManager, read by HUD overlays

---

## 4. Coupling Analysis

### 4.1 What Each Function Reads from `game_view` State

| Function | Reads | Writes |
|----------|-------|--------|
| `_load_presentation_manifest` | `PRESENTATION_MANIFEST_PATH` (const) | `_presentation_manifest` |
| `_resolve_visual_id` | `_player_races`, `_presentation_manifest`, `_sprite_loader` | — |
| `_is_known_unit_visual` | `_presentation_manifest`, `_sprite_loader` | — |
| `_is_known_building_visual` | `_presentation_manifest`, `_sprite_loader` | — |
| `_is_building_entity_visual` | `_presentation_manifest`, `_sprite_loader` | — |
| `_visual_scale` | `_sprite_loader`, `_presentation_manifest` | — |
| `_visual_radius` | `_sprite_loader`, `_presentation_manifest` | — |
| `_unit_animation_key` | `_sprite_loader` | — |
| `_calc_unit_region` | `_unit_anim_info`, `_unit_textures`, `_player_races` | — |
| `_get_building_region` | `_player_races` | — |
| `_has_building_region_override` | — | — |
| `_has_unit_region_override` | — | — |
| `_get_unit_region_override` | `_player_races`, `_calc_unit_region`, `_anim_frame` | — |
| `_update_entity_sprites` | `_ents`, `_sprite_container`, `_sprite_pool`, `_sprite_loader`, `_player_races`, `_anim_frame`, `_unit_textures`, `_building_textures`, `_test_gallery` (for generated previews), `_bridge` (for tick logging) | `_sprite_pool`, `_sprite_container` children |
| `_draw_entities` | `_ents`, `_get_ent_by_id`, `_is_in_fog` | — |
| `_is_in_fog` | `_fog_w`, `_fog_h`, `_fog_alpha`, `_map_w`, `_map_h` | — |

### 4.2 Callers of These Functions from `game_view.gd`

| Caller Site | Function Called | Purpose |
|-------------|----------------|---------|
| `_ready()` L309 | `_load_presentation_manifest()` | Init manifest |
| `_ready()` L412–415 | `_visual_radius`, `_visual_scale`, `_resolve_visual_id`, `_is_building_entity_visual`, `_is_in_fog` | Wire into `HUDOverlayRenderer.set_visual_helpers()` |
| `_parse()` L1663 | `_update_entity_sprites()` | Sync sprites after state tick |
| `_draw()` L1756 | `_draw_entities(co)` | Draw entity overlays |
| `_visual_unit_name()` L1199 | `_resolve_visual_id(e)` | VFX lookup |
| `_vfx_profile_for()` L1204–1211 | `_presentation_manifest` (direct read) | VFX profile |
| `_draw_attack_flashes` L2258 | `_is_in_fog(e)` | Hide flashes in fog |
| `_draw_hover_highlight` L2304 | `_is_in_fog(e)` | Hide hover in fog |
| `_draw_health_bars` L2326 | `_is_in_fog(e)` | Hide HP in fog |
| `_draw_build_progress_bars` L2350 | `_is_in_fog(e)` | Hide progress in fog |
| `_draw_production_bars` L2406 | `_is_in_fog(e)` | Hide production in fog |
| `_draw_status_icons` L2435 | `_is_in_fog(e)` | Hide status in fog |
| Various draw functions | `_visual_radius(e)`, `_visual_scale(v, b)` | Sizing bars/icons |

### 4.3 Cross-Cutting Dependencies

**Shared `_entity_cache_by_id`**: Used by `HUDOverlayRenderer`, `SelectionManager`, `AbilityManager`, and `TestModeGallery`. EntitySpriteManager will own it and expose a read accessor.

**Shared `_player_races`**: Written by `_apply_start_state()` in game_view, read by EntitySpriteManager and HUDOverlayRenderer. EntitySpriteManager owns a copy; game_view pushes updates via `setup()` or a setter.

**Shared `_is_in_fog`**: Called by 7+ HUD overlay draw functions. Must be exposed as a Callable or public method on EntitySpriteManager so HUDOverlayRenderer can invoke it.

---

## 5. Proposed Public API

### File: `godot/scripts/entity_sprite_manager.gd`

```gdscript
class_name EntitySpriteManager
extends Node2D

## EntitySpriteManager — extracted from game_view.gd.
## Owns entity sprite lifecycle: pool management, visual ID resolution,
## atlas region calculation, fog visibility, and canvas entity drawing.

# ─── Signals ──────────────────────────────────────────────────
## Emitted when the sprite pool changes (for debug/logging).
signal sprites_updated(total: int, visible: int)

# ─── Setup (called once from game_view._ready) ────────────────
func setup(
    sprite_loader: SpriteLoader,
    presentation_manifest: Dictionary,
    sprite_pool: Dictionary,        # entity_id → Sprite2D/AnimatedSprite2D
    sprite_container: Node2D        # parent node for sprites
) -> void

# ─── Per-tick update ──────────────────────────────────────────
## Sync sprite nodes with the current entity list.
## game_view calls this once after _parse().
func update_sprites(
    ents: Array,                     # current entity dicts
    player_races: Dictionary,        # player_id → race_id
    fog_tiles: PackedInt32Array,
    fog_w: int,
    fog_h: int,
    fog_alpha: PackedFloat32Array,
    map_w: float,
    map_h: float,
    camera: Camera2D,
    test_mode: bool                  # whether TestModeGallery is active
) -> void

# ─── Canvas drawing ──────────────────────────────────────────
## Draw resource circles and attack/move target lines.
## Must be called from game_view._draw() (canvas item = self).
func draw_entities(
    canvas: CanvasItem,              # game_view (the _draw caller)
    ents: Array,
    get_ent_by_id_fn: Callable,      # game_view._get_ent_by_id
    fog_tiles: PackedInt32Array,
    fog_w: int,
    fog_h: int,
    fog_alpha: PackedFloat32Array,
    map_w: float,
    map_h: float,
    camera: Camera2D,
    is_in_fog_fn: Callable           # self._is_in_fog (exposed below)
) -> void

# ─── Visual identity queries (used by HUDOverlayRenderer, VFX) ──
func resolve_visual_id(entity: Dictionary) -> String
func visual_scale(visual_id: String, is_building: bool) -> Vector2
func visual_radius(entity: Dictionary) -> float
func is_building_entity_visual(entity: Dictionary, visual_id: String) -> bool
func animation_key(entity: Dictionary, frames: SpriteFrames) -> String
func is_known_unit_visual(visual_id: String) -> bool
func is_known_building_visual(visual_id: String) -> bool

# ─── Atlas region queries ────────────────────────────────────
func calc_unit_region(unit_type: String, owner: int, row: int, frame: int) -> Rect2
func get_building_region(building_type: String, owner: int) -> Dictionary

# ─── Fog visibility (Callable-compatible) ─────────────────────
## Returns true if entity is in non-visible fog (alpha > 0.15).
func is_in_fog(entity: Dictionary) -> bool

# ─── Entity cache accessor ────────────────────────────────────
## Returns entity dict by ID (or empty dict if missing).
func get_entity_data(entity_id: String) -> Dictionary
```

### GDScript 4 Constraints

| Constraint | Impact |
|-----------|--------|
| No multiple inheritance | `EntitySpriteManager` extends `Node2D` (needs `add_child` for sprites, needs position/z_index in scene tree) |
| No generics | `Dictionary` and `Array` for all collections; `Callable` for callback injection |
| `@onready` not available for injected deps | Use `setup()` called from `_ready()` of parent; all injected refs stored as plain `var` |
| `draw_*` only works inside `_draw()` | `draw_entities()` receives the `CanvasItem` (game_view) as parameter and calls `canvas.draw_*()` |
| Signal connection must be manual | `sprites_updated` connected in `game_view._ready()` |

---

## 6. How `game_view.gd` Calls It

### 6.1 `_ready()` — Initialization

```gdscript
# Before (in _ready):
_sprite_container = Node2D.new()
_sprite_container.name = "EntitySprites"
_sprite_container.z_index = 1
add_child(_sprite_container)
_sprite_loader = SpriteLoaderScript.new()
_load_presentation_manifest()
# ... then _unit_textures, _building_textures, _unit_anim_info init ...

# After:
_sprite_manager = EntitySpriteManager.new()
_sprite_manager.name = "EntitySpriteManager"
add_child(_sprite_manager)
_sprite_manager.setup(
    _sprite_loader,            # created by game_view
    _presentation_manifest,    # loaded by game_view
    _sprite_pool,              # owned by EntitySpriteManager after setup
    _sprite_container          # owned by EntitySpriteManager after setup
)
# game_view no longer directly references _sprite_pool or _sprite_container
# Texture preloading and _unit_anim_info remain in game_view._ready() and
# are injected into EntitySpriteManager via setup() or separate init calls.
```

### 6.2 `_parse()` — Per-Tick Sprite Sync

```gdscript
# Before:
_update_entity_sprites()

# After:
_sprite_manager.update_sprites(
    _ents, _player_races,
    _fog_tiles, _fog_w, _fog_h, _fog_alpha,
    _map_w, _map_h, _camera,
    _test_gallery != null and _test_gallery.is_active()
)
```

### 6.3 `_draw()` — Entity Overlay Drawing

```gdscript
# Before:
_draw_entities(co)

# After:
_sprite_manager.draw_entities(
    self,                       # canvas: CanvasItem
    _ents,
    _get_ent_by_id,             # Callable
    _fog_tiles, _fog_w, _fog_h, _fog_alpha,
    _map_w, _map_h, _camera,
    _sprite_manager.is_in_fog   # Callable
)
```

### 6.4 `HUDOverlayRenderer` Wiring

```gdscript
# Before:
_hud_overlay.set_visual_helpers(
    _visual_radius, _visual_scale, _resolve_visual_id,
    _is_building_entity_visual, _screen_to_world, _world_to_screen, _is_in_fog
)

# After:
_hud_overlay.set_visual_helpers(
    _sprite_manager.visual_radius, _sprite_manager.visual_scale,
    _sprite_manager.resolve_visual_id, _sprite_manager.is_building_entity_visual,
    _screen_to_world, _world_to_screen,
    _sprite_manager.is_in_fog
)
```

### 6.5 VFX Integration

```gdscript
# Before:
_vfx_manager.spawn_hit(_visual_unit_name(e), ...)
# _visual_unit_name calls _resolve_visual_id internally

# After:
_vfx_manager.spawn_hit(_sprite_manager.resolve_visual_id(e), ...)
# Or: keep _visual_unit_name as thin wrapper that delegates
```

---

## 7. Detailed Migration Plan

### Phase 1: Extract & Compile (≈2h)

1. Create `godot/scripts/entity_sprite_manager.gd` with the API above.
2. Move all 16 functions (§2) and 12 variables (§3) into the new class.
3. In `EntitySpriteManager._ready()`, do NOT auto-init; rely on `setup()` called by parent.
4. Keep `_unit_textures`, `_building_textures`, and `_unit_anim_info` population in `game_view._ready()`, then inject them via `setup()`.
5. Add `var _sprite_manager: EntitySpriteManager = null` to `game_view.gd`.
6. Replace all direct calls (`_update_entity_sprites()`, `_draw_entities()`, etc.) with delegating calls per §6.
7. Run `godot --headless --check-only` to verify GDScript compilation.

### Phase 2: Functional Verification (≈2h)

1. Launch game in normal mode — verify all unit/building sprites render correctly.
2. Test fog-of-war: move units into and out of fog, verify sprites hide/show.
3. Test attack/move target lines render.
4. Test resource circles (mineral/gas) render.
5. Test race switching (Terran/Zerg/Protoss) — verify visual IDs resolve correctly.

### Phase 3: HUD Overlay Integration (≈1h)

1. Re-wire `HUDOverlayRenderer.set_visual_helpers()` to use EntitySpriteManager Callables.
2. Verify selection rings, health bars, production bars all size correctly.
3. Verify hover highlight hides correctly in fog.

---

## 8. Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| **Sprite pool ownership transfer** — `_sprite_pool` Dict is mutated by both `_update_entity_sprites` and `TestModeGallery._clear_test_sprites` | **High** | Medium | Add `clear_pool()` method on EntitySpriteManager; TestModeGallery calls it instead of directly iterating `_sprite_pool` |
| **`draw_entities` receives canvas** — Calling `canvas.draw_*()` from another class is unusual in Godot | **Medium** | Low | Well-documented pattern: `CanvasItem.draw_*()` is public API; the receiver just needs a valid `CanvasItem` reference |
| **`_is_in_fog` called from 7+ sites** — Breaks if signature changes or if `_fog_alpha`/`_fog_w`/`_fog_h` are stale | **High** | Low | `is_in_fog()` always uses its own stored fog state (set by `update_sprites()`); game_view must call `update_sprites()` before any `_draw_*` that uses `is_in_fog` |
| **`_entity_cache_by_id` shared ownership** — HUDOverlayRenderer, SelectionManager, and AbilityManager all read from this | **Medium** | Medium | EntitySpriteManager owns the cache; expose `get_entity_data()` and `get_entity_cache()` accessor. HUDOverlayRenderer reads via the accessor. game_view pushes entity data into EntitySpriteManager in `_parse()`. |
| **`_player_races` write-after-setup** — `_apply_start_state()` writes `_player_races` after `_ready()` | **Medium** | High | `update_sprites()` takes `player_races` as a parameter each tick, so EntitySpriteManager always has the latest value. No separate setter needed. |
| **`_anim_frame` never updated** — It's read at L2051 but never incremented | **Low** | Already broken | Keep as-is; this is a pre-existing bug. Document it as a known issue for future fix. |
| **Texture preloading split** — `_unit_textures`/`_building_textures` populated in game_view._ready() but consumed by EntitySpriteManager | **Low** | Low | Pass them in via `setup()` or a separate `set_textures()` call. They're immutable after init. |

---

## 9. Integration Test Plan

### 9.1 Smoke Tests (Must Pass Before Merge)

| Test | Steps | Expected |
|------|-------|----------|
| Normal gameplay | Start game, observe units and buildings | All sprites visible, correct race visuals |
| Fog-of-war visibility | Move own unit out of view of enemy building | Enemy building sprite hides |
| Resource rendering | Observe mineral/gas patches | Yellow/green circles drawn |
| Attack target lines | Command unit to attack | Red line drawn from attacker to target |
| Move target lines | Command unit to move | Green line drawn to destination |
| HUD overlays | Select a unit | Health bar, selection ring render correctly at right size |
| Race-specific visuals | Play as Terran vs Zerg | Terran sprites for P1, Zerg sprites for P2 |
| Build progress | Start constructing building | Yellow progress bar appears |

### 9.2 Regression Tests (Run If Time Permits)

| Test | Steps | Expected |
|------|-------|----------|
| Test Mode Gallery | Toggle test mode, verify gallery entities appear | Gallery sprites render, filter panels work |
| Death effects | Kill enemy unit | Death explosion VFX renders at correct position |
| Attack flash | Unit fires weapon | White flash overlay renders on sprite |
| Production queue | Queue units in building | Production bars with unit letters render |
| Hover highlight | Mouse over enemy unit in visible fog | White hover ring appears |
| Replay mode | Watch a replay | All sprites render identically to live game |

### 9.3 Automated Test Skeleton

```gdscript
# test_entity_sprite_manager.gd
extends Node

var _manager: EntitySpriteManager

func before_each() -> void:
    _manager = EntitySpriteManager.new()
    var mock_loader = SpriteLoader.new()  # or a mock
    _manager.setup(mock_loader, {}, {}, Node2D.new())

func test_resolve_visual_id_worker() -> void:
    var e = {"type": "worker", "unit_type": "worker", "owner": 1}
    var vid = _manager.resolve_visual_id(e)
    assert(vid != "", "resolve_visual_id should return non-empty for worker")

func test_is_in_fog_outside_fog() -> void:
    _manager._fog_w = 4
    _manager._fog_h = 4
    _manager._fog_alpha = PackedFloat32Array([0.0, 0.0, 0.0, 0.0,
                                               0.0, 0.0, 0.0, 0.0,
                                               0.0, 0.0, 0.0, 0.0,
                                               0.0, 0.0, 0.0, 0.0])
    _manager._map_w = 64.0
    _manager._map_h = 64.0
    var e = {"px": 32.0, "py": 32.0}
    assert(not _manager.is_in_fog(e), "Entity at center should not be in fog when alpha=0")

func test_calc_unit_region_fallback() -> void:
    var region = _manager.calc_unit_region("unknown_type", 1, 0, 0)
    assert(region.position == Vector2.ZERO, "Fallback region should start at (0,0)")
```

---

## 10. File Changes Summary

| File | Action | Lines Added | Lines Removed |
|------|--------|-------------|---------------|
| `godot/scripts/entity_sprite_manager.gd` | **Create** | ~420 | 0 |
| `godot/scripts/game_view.gd` | Modify | ~50 (delegation) | ~392 (functions + vars) |
| `godot/scripts/hud_overlay_renderer.gd` | Modify | ~5 (re-wire Callables) | ~5 |

**Net reduction in `game_view.gd`**: ~342 lines (392 removed, 50 added for delegation).  
**New file**: `entity_sprite_manager.gd` at ~420 lines (including doc comments and blank lines).

---

## 11. Open Questions / Future Work

1. **`_anim_frame` / `_anim_tick` are dead code** — `_anim_frame` is read but never incremented. After extraction, add a proper frame-advance mechanism inside `EntitySpriteManager._process()` or via a `tick_animation()` call.
2. **Texture preloading could move into EntitySpriteManager** — Currently `_unit_textures` and `_building_textures` are populated in `game_view._ready()`. A future refactor could make EntitySpriteManager own the preload step.
3. **`_entity_cache_by_id` lifecycle** — Currently rebuilt every `_parse()` tick. Consider whether EntitySpriteManager should own the rebuild, or receive a pre-built cache from game_view.
4. **Fog state ownership** — `_fog_tiles`, `_fog_w`, `_fog_h`, `_fog_alpha` are currently game_view state. A future extraction could create a `FogState` struct or move fog into a `FogManager`.
5. **`draw_entities` canvas delegation** — The pattern of passing `canvas: CanvasItem` into a child manager is clean but unusual. If more draw functions are extracted, consider a `CanvasItem` mixin or a shared `DrawingContext` utility.
