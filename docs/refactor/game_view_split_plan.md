# Game View Split/Refactor Plan

**File**: `godot/scripts/game_view.gd` — 3,373 lines, 126KB  
**Date**: 2026-06-24

---

## 1. Functional Section Map

| Section | Lines | Functions | Description |
|---------|-------|-----------|-------------|
| **Constants & Config** | 1–39 | — | Preloads, HUD height, paths |
| **State Variables** | 40–206 | — | ~70 `var` declarations spanning 6 logical groups |
| **Entity Helpers** | 207–227 | `_get_entity_data`, `_get_entity_type`, `_load_texture_or_fallback` | Data-provider callbacks for autoloads |
| **_ready()** | 228–487 | `_ready` | Monolithic init: bridge, camera, sprites, VFX, HUD, minimap, test-mode UI, victory screen, APM label |
| **Test Filter Panel** | 488–663 | `_create_test_filter_panel`, `_add_row_label`, `_make_toggle_group`, `_on_filter_btn_pressed`, 6× `_on_*_filter_btn`, `_add_filter_item`, `_on_test_batch_filter_selected` | Builds + wires the test-mode filter UI |
| **Selection/HUD Bridge** | 664–755 | `_sync_selected_from_manager`, `_on_selection_changed`, `_on_camera_focus_requested`, 6× `_on_hud_*` | Relays between HUD, SelectionManager, AbilityManager |
| **_process()** | 756–827 | `_process` | Game loop: APM, test-anim, damage floats, flashes, death FX, pings, hover, minimap tick |
| **Camera/Entity Helpers** | 828–885 | `_screen_to_world`, `_world_to_screen`, `_ent_at_world_pos`, `_ents_in_world_rect`, `_is_own_combat`, `_is_own_building`, `_has_refinery_on_geyser`, `_find_nearest_enemy` | Coordinate transforms + entity queries |
| **Input** | 886–1060 | `_input`, `_unhandled_input` | Keyboard shortcuts, mouse button dispatch |
| **Command Dispatch** | 1060–1296 | `_handle_right_click`, `_handle_single_click`, `_handle_drag_select` | Context-action logic (move/attack/gather/build/rally) |
| **Train/Merge** | 1297–1365 | `_handle_train`, `_handle_merge` | Production & merging commands |
| **Visual/VFX Integration** | 1365–1498 | `_get_ent_by_id`, `_visual_unit_name`, `_vfx_profile_for`, `_set_rally_point`, `_clear_rally_point`, `_update_rally_indicator_visibility`, `_emit_attack_indicator`, `_load_feel_config`, `_spawn_command_ping` | VFX bridge + rally-point + feel-config |
| **State Callbacks** | 1498–1625 | `_on_start`, `_on_state`, `_apply_start_state`, `_on_game_over`, `_restart_game`, 3× `_on_victory_*` | Bridge signal handlers + game-over flow |
| **Manifest/Catalog Loaders** | 1626–1700 | `_load_presentation_manifest`, `_load_unit_type_catalog`, `_catalog_passes_filters` | JSON resource loading + filter logic |
| **Visual Identity** | 1701–1780 | `_resolve_visual_id`, `_is_known_unit_visual`, `_is_known_building_visual`, `_is_building_entity_visual`, `_visual_scale`, `_visual_radius`, `_unit_animation_key` | Sprite/animation resolution |
| **State Parsing** | 1781–1985 | `_parse` | The big one: entities, fog, resources, delta detection, death VFX |
| **Drawing Dispatcher** | 1986–2013 | `_draw` | Calls 16 `_draw_*` methods |
| **Map/Terrain Drawing** | 2014–2165 | `_draw_map_background`, `_draw_elevation`, `_draw_grid`, `_draw_fog_of_war` | Canvas terrain + fog |
| **Sprite Region Calc** | 2166–2293 | `_calc_unit_region`, `_get_building_region`, `_has_*_override`, `_get_unit_region_override` | Atlas region math |
| **Entity Sprite Update** | 2294–2485 | `_update_entity_sprites`, `_draw_entities`, `_is_in_fog` | Sprite pool + entity draw |
| **HUD Overlays** | 2486–2829 | `_draw_attack_flashes`, `_draw_death_explosions`, `_draw_hover_highlight`, `_draw_damage_floats`, `_draw_health_bars`, `_draw_build_progress_bars`, `_draw_production_bars`, `_draw_status_icons`, `_draw_selection_rings`, `_draw_pylon_power_range`, `_draw_rally_lines`, `_draw_drag_box`, `_draw_game_over_overlay`, `_team_color`, `_unit_letter` | Canvas-drawn HUD elements |
| **Minimap Bridge** | 2833–2921 | `_minimap_rect`, `_is_minimap_click`, `_handle_minimap_click`, `_get_state_for_minimap`, `_monitor_canvas_transform` | Data provider for MinimapRect child |
| **Analysis/Debug** | 2932–2960 | `_write_analysis` | End-of-game CSV dump |
| **Test Mode** | 2962–3318 | `_draw_test_labels`, `_toggle_test_mode`, `_toggle_elevation`, `_build_test_entities`, `_clear_test_entities`, `_clear_test_sprites`, `_add_test_header`, `_add_test_unit_pair`, `_make_test_asset_entity`, `_test_asset_race`, `_test_owner_for_race`, `_test_race_label`, `_test_race_color` | Full test/gallery mode system |
| **Replay** | 3321–3374 | `_on_replay_loaded`, `_on_replay_finished`, `_request_latest_replay`, `_on_replay_list_loaded` | Replay signal handlers |

---

## 2. Candidate Extraction Targets

### A. Test Mode System — **~660 lines**

**Functions to move** (20):
- `_create_test_filter_panel`, `_add_row_label`, `_make_toggle_group`
- `_on_filter_btn_pressed`, `_on_race_filter_btn`, `_on_kind_filter_btn`, `_on_domain_filter_btn`, `_on_role_filter_btn`, `_on_tier_filter_btn`, `_on_preview_mode_btn`
- `_add_filter_item`, `_on_test_batch_filter_selected`
- `_draw_test_labels`, `_toggle_test_mode`, `_toggle_elevation`
- `_build_test_entities`, `_clear_test_entities`, `_clear_test_sprites`
- `_add_test_header`, `_add_test_unit_pair`, `_make_test_asset_entity`
- `_test_asset_race`, `_test_owner_for_race`, `_test_race_label`, `_test_race_color`
- `_catalog_passes_filters`, `_load_unit_type_catalog`

**Variables to move** (~25):
- `_test_mode`, `_test_ents`, `_test_btn`, `_test_filter_panel`, `_test_race/kind/domain/role/tier_filter`, `_test_preview_mode`, `_test_filter_batch`, `_test_section_headers`, `_test_batch_filter`
- `_race_buttons`, `_kind_buttons`, `_domain_buttons`, `_role_buttons`, `_tier_buttons`, `_preview_buttons`
- `_elev_btn`, `_zoom_in_btn`, `_zoom_out_btn`
- `_saved_ents`, `_saved_player_races`, `_saved_fog_tiles/w/h`
- `_unit_type_catalog`

**Coupling to game_view**:
- **Writes**: `_ents`, `_fog_tiles/w/h`, `_player_races`, `_test_ents` → calls `_update_entity_sprites()`, `queue_redraw()`
- **Reads**: `_sprite_loader`, `_sprite_pool` (for cleanup), `_ents`, `_default_font`
- **Bridge needed**: Entity data + sprite system access

### B. HUD Overlays / Decoration System — **~530 lines**

**Functions to move** (16):
- `_draw_attack_flashes`, `_draw_death_explosions`, `_draw_hover_highlight`
- `_draw_damage_floats`, `_draw_health_bars`, `_draw_build_progress_bars`
- `_draw_production_bars`, `_draw_status_icons`, `_draw_selection_rings`
- `_draw_pylon_power_range`, `_draw_rally_lines`, `_draw_drag_box`
- `_draw_command_pings`, `_draw_control_group_hints`, `_draw_game_over_overlay`
- `_team_color`, `_unit_letter`

**Variables to move** (~25):
- `_attack_flash_timers`, `_dead_effects`, `_dmg_floats`
- `_hovered_entity_id`, `_hover_check_timer`, `_game_time`
- `_prev_attack_targets`, `_command_pings`, `_control_group_hints`
- All ping constants (`_ground_ping_*`, `_attack_ping_*`, etc.)
- Attack flash / death effect / hover / selection-breathe constants
- `_dragging`, `_drag_start`, `_drag_end`

**Coupling to game_view**:
- **Read-only**: `_ents`, `_selected`, `_entity_cache_by_id`, `_camera`, `_fog_alpha`
- **Calls**: `_visual_radius()`, `_visual_scale()`, `_resolve_visual_id()`, `_screen_to_world()`, `_is_in_fog()`, `_is_building_entity_visual()`
- **Writes**: Decays its own timers (self-contained)

### C. Entity Rendering System — **~380 lines**

**Functions to move** (13):
- `_calc_unit_region`, `_get_building_region`, `_has_building_region_override`, `_has_unit_region_override`, `_get_unit_region_override`
- `_update_entity_sprites`
- `_draw_entities`, `_is_in_fog`
- `_resolve_visual_id`, `_is_known_unit_visual`, `_is_known_building_visual`, `_is_building_entity_visual`
- `_visual_scale`, `_visual_radius`, `_unit_animation_key`

**Variables to move** (~10):
- `_unit_textures`, `_building_textures`, `_sprite_pool`, `_sprite_container`
- `_unit_anim_info`, `_presentation_manifest`, `_entity_cache_by_id`, `_sprite_loader`

**Coupling to game_view**:
- **Reads**: `_ents`, `_player_races`, `_default_font`, `_test_mode`
- **Writes**: `_sprite_pool`, `_sprite_container` children
- **Bridge**: Needs entity data source; `draw_*` must remain in game_view or receive canvas

---

## 3. Top 3 Extractions by Impact

| Rank | Target | Lines Removed | Coupling | Risk | Impact Score |
|------|--------|---------------|----------|------|--------------|
| **#1** | **Test Mode System** | ~660 | Low-Medium | Low | ★★★★★ |
| **#2** | **HUD Overlays** | ~530 | Medium | Medium | ★★★★☆ |
| **#3** | **Entity Rendering** | ~380 | Medium-High | Medium-High | ★★★☆☆ |

### Why #1 (Test Mode) is the clear winner:
- **Largest single chunk** (~20% of the file)
- **Near-zero gameplay coupling**: test mode is a debug/gallery feature, not in the hot path
- **Clean lifecycle**: toggle on → save state → build entities → toggle off → restore state
- **No _draw() calls on the main canvas**: `_draw_test_labels` is the only draw call, and it's trivially conditional
- **Only 2 integration points**: needs `_ents` (write) and `_update_entity_sprites()` (call)

---

## 4. Concrete Skeleton for #1 Extraction: `TestModeGallery`

### New file: `godot/scripts/test_mode_gallery.gd`

```gdscript
class_name TestModeGallery
extends Node2D

## Test Mode Gallery — asset preview/debug system extracted from game_view.gd.
## Toggle via signal or direct call. Owns filter panel UI, entity generation,
## and state save/restore. Emits signals when game_view needs to update sprites.

# ─── Signals (bridge to game_view) ─────────────────────────
## Emitted when entities list needs to be hot-swapped into game_view._ents
signal entities_rebuilt(new_ents: Array)
## Emitted when fog/race state changes and game_view should refresh
signal state_changed()

# ─── Config ──────────────────────────────────────────────────
const UNIT_TYPE_CATALOG_PATH := "res://resources/unit_type_catalog.json"

# ─── Test mode state ─────────────────────────────────────────
var _active: bool = false
var _test_ents: Array = []
var _section_headers: Array = []

# ─── Saved game state (restored on exit) ─────────────────────
var _saved_ents: Array = []
var _saved_player_races: Dictionary = {}
var _saved_fog_tiles: PackedInt32Array = []
var _saved_fog_w: int = 0
var _saved_fog_h: int = 0

# ─── Filter state ────────────────────────────────────────────
var _filter_race: String = ""
var _filter_kind: String = ""
var _filter_domain: String = ""
var _filter_role: String = ""
var _filter_tier: String = ""
var _preview_mode: String = "idle"
var _filter_batch: String = "all"

# ─── UI refs ─────────────────────────────────────────────────
var _btn: Button = null
var _filter_panel: PanelContainer = null
var _batch_filter: OptionButton = null
var _elev_btn: Button = null
var _race_buttons: Dictionary = {}
var _kind_buttons: Dictionary = {}
var _domain_buttons: Dictionary = {}
var _role_buttons: Dictionary = {}
var _tier_buttons: Dictionary = {}
var _preview_buttons: Dictionary = {}

# ─── External deps (injected) ────────────────────────────────
var _sprite_loader: Node = null   # SpriteLoader reference
var _font: Font = null            # ThemeDB.fallback_font

# ─── Catalog ─────────────────────────────────────────────────
var _unit_type_catalog: Dictionary = {}

# ─── Public API ──────────────────────────────────────────────

func is_active() -> bool:
	return _active

func setup(ui_layer: CanvasLayer, sprite_loader: Node, default_font: Font) -> void:
	_sprite_loader = sprite_loader
	_font = default_font
	_load_unit_type_catalog()
	_create_test_btn(ui_layer)
	_create_filter_panel(ui_layer)

func toggle() -> void:
	_active = not _active
	if _active:
		# game_view must: save its _ents/_player_races/_fog, then call build()
		_btn.text = "Back"
		_btn.modulate = Color(1.0, 0.8, 0.8)
		_filter_panel.visible = true
		build()
	else:
		# game_view must: restore its saved state
		_btn.text = "🧪 Test Mode"
		_btn.modulate = Color(0.8, 1.0, 0.8)
		_filter_panel.visible = false
		clear()
		state_changed.emit()

func build() -> void:
	_clear_sprites()
	_test_ents.clear()
	_section_headers.clear()
	# ... (full _build_test_entities logic, same as current)
	# At end:
	entities_rebuilt.emit(_test_ents)
	state_changed.emit()

func clear() -> void:
	_clear_sprites()
	_test_ents.clear()
	_section_headers.clear()

## Returns saved state so game_view can restore
func get_saved_state() -> Dictionary:
	return {
		"ents": _saved_ents,
		"player_races": _saved_player_races,
		"fog_tiles": _saved_fog_tiles,
		"fog_w": _saved_fog_w,
		"fog_h": _saved_fog_h,
	}

## Called by game_view to save current state before entering test mode
func save_state(ents: Array, player_races: Dictionary, fog_tiles: PackedInt32Array, fog_w: int, fog_h: int) -> void:
	_saved_ents = ents.duplicate(true)
	_saved_player_races = player_races.duplicate(true)
	_saved_fog_tiles = fog_tiles
	_saved_fog_w = fog_w
	_saved_fog_h = fog_h

## Draw test labels on game_view's canvas (called from game_view._draw)
func draw_labels(canvas: CanvasItem) -> void:
	if not _active:
		return
	var font: Font = _font
	if not font:
		return
	for header in _section_headers:
		canvas.draw_string(
			font,
			header.get("pos", Vector2.ZERO),
			str(header.get("text", "")),
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			1.2,
			header.get("color", Color.WHITE)
		)
	for e in _test_ents:
		if not str(e.id).begins_with("test_"):
			continue
		if bool(e.get("preview_hidden", false)):
			continue
		var full_label = str(e.get("label", ""))
		if full_label == "":
			continue
		canvas.draw_string(
			font,
			Vector2(float(e.get("px", 0.0)) + 1.3, float(e.get("py", 0.0)) - 0.3),
			full_label,
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			0.8,
			Color(1, 1, 1, 0.9)
		)

# ─── Private: UI construction ────────────────────────────────

func _create_test_btn(ui_layer: CanvasLayer) -> void:
	_btn = Button.new()
	_btn.text = "🧪 Test Mode"
	_btn.tooltip_text = "Click to preview all sprites on map"
	_btn.position = Vector2(8, 8)
	_btn.size = Vector2(120, 32)
	_btn.modulate = Color(0.8, 1.0, 0.8)
	ui_layer.add_child(_btn)
	_btn.pressed.connect(toggle)

func _create_filter_panel(ui_layer: CanvasLayer) -> void:
	# ... (same logic as current _create_test_filter_panel)
	# Filter callbacks call build() when _active
	pass

# ─── Private: entity generation ─────────────────────────────

func _clear_sprites() -> void:
	# game_view._sprite_pool cleanup for test_ entries
	# Emits state_changed so game_view can prune
	state_changed.emit()

func _build_test_entities() -> void:
	# ... (same logic as current _build_test_entities)
	pass

# (All _make_test_asset_entity, _test_asset_race, _test_owner_for_race,
#  _test_race_label, _test_race_color, _catalog_passes_filters,
#  _load_unit_type_catalog, filter callbacks — moved verbatim)

# ─── Private: filter helpers ─────────────────────────────────

func _add_row_label(row: HBoxContainer, text: String) -> void:
	# ... (same as current)
	pass

func _make_toggle_group(
	row: HBoxContainer,
	labels: Array,
	values: Array,
	current: String,
	callback: String
) -> Dictionary:
	# ... (same as current)
	return {}

func _on_filter_btn_pressed(value: String, callback: String, buttons: Dictionary) -> void:
	# ... (same as current)
	pass

# (Individual filter callbacks _on_race_filter_btn, etc.)
```

### Changes to `game_view.gd`

```gdscript
# ─── New member ─────────────────────────────────────────────
var _test_gallery: TestModeGallery = null

# ─── In _ready(), replace test-mode setup ───────────────────
# REMOVE: _test_btn creation, _create_test_filter_panel(), zoom button setup
# ADD:
_test_gallery = TestModeGallery.new()
_test_gallery.name = "TestModeGallery"
add_child(_test_gallery)
_test_gallery.setup(_ui_layer, _sprite_loader, _default_font)
_test_gallery.entities_rebuilt.connect(_on_test_entities_rebuilt)
_test_gallery.state_changed.connect(_on_test_state_changed)

# ─── New signal handlers ────────────────────────────────────
func _on_test_entities_rebuilt(new_ents: Array) -> void:
	_ents = new_ents
	_update_entity_sprites()
	queue_redraw()

func _on_test_state_changed() -> void:
	# After test mode clears, restore saved state
	if not _test_gallery.is_active():
		var saved: Dictionary = _test_gallery.get_saved_state()
		if not saved.is_empty():
			_ents = saved["ents"]
			_player_races = saved["player_races"]
			_fog_tiles = saved["fog_tiles"]
			_fog_w = saved["fog_w"]
			_fog_h = saved["fog_h"]
	_update_entity_sprites()
	queue_redraw()

# ─── In _process(), replace test-mode block ─────────────────
# REMOVE: the entire `if _test_mode:` animation block
# ADD:
if _test_gallery.is_active():
	_anim_tick += delta
	if _anim_tick >= 1.0 / ANIM_FPS:
		_anim_tick -= 1.0 / ANIM_FPS
		_anim_frame = (_anim_frame + 1) % 17
		# Flash for attack-preview entities
		for e in _ents:
			if str(e.get("preview_action", "")) == "attack":
				_attack_flash_timers[str(e.get("id", ""))] = ATTACK_FLASH_DURATION
		_update_entity_sprites()

# ─── In _draw(), replace test label call ────────────────────
# REMOVE: `if _test_mode: _draw_test_labels()`
# ADD:
_test_gallery.draw_labels(self)

# ─── In toggle_test_mode flow ────────────────────────────────
# When _test_gallery.toggle() is about to activate, game_view saves:
if _test_gallery.is_active():
	_test_gallery.save_state(_ents, _player_races, _fog_tiles, _fog_w, _fog_h)
	_fog_tiles = PackedInt32Array()
	_fog_w = 0
	_fog_h = 0
	_player_races["1"] = "1"
	_player_races["2"] = "2"
	_player_races["3"] = "3"
```

### Variables/functions REMOVED from game_view.gd (complete list)

**Removed vars** (~25):
- `_test_mode`, `_test_ents`, `_test_btn`, `_test_filter_panel`
- `_test_filter_race/kind/domain/role/tier`, `_test_preview_mode`, `_test_filter_batch`
- `_test_section_headers`, `_test_batch_filter`
- `_race_buttons`, `_kind_buttons`, `_domain_buttons`, `_role_buttons`, `_tier_buttons`, `_preview_buttons`
- `_elev_btn`, `_zoom_in_btn`, `_zoom_out_btn`
- `_saved_ents`, `_saved_player_races`, `_saved_fog_tiles/w/h`
- `_unit_type_catalog`

**Removed funcs** (~24):
- `_create_test_filter_panel`, `_add_row_label`, `_make_toggle_group`
- `_on_filter_btn_pressed`, `_on_race/kind/domain/role/tier_filter_btn`, `_on_preview_mode_btn`
- `_add_filter_item`, `_on_test_batch_filter_selected`
- `_draw_test_labels`, `_toggle_test_mode`, `_toggle_elevation`
- `_build_test_entities`, `_clear_test_entities`, `_clear_test_sprites`
- `_add_test_header`, `_add_test_unit_pair`, `_make_test_asset_entity`
- `_test_asset_race`, `_test_owner_for_race`, `_test_race_label`, `_test_race_color`
- `_catalog_passes_filters`, `_load_unit_type_catalog`

**Net reduction**: ~660 lines removed from game_view.gd → **~2,713 lines remaining**

---

## 5. Roadmap for Subsequent Extractions

| Step | Target | Expected Remaining | Notes |
|------|--------|--------------------|-------|
| After #1 | HUD Overlays → `HUDOverlayRenderer` (Node2D child) | ~2,180 | All `_draw_*` overlay methods move; reads entity data via a provider interface |
| After #2 | Entity Rendering → `EntitySpriteManager` (Node2D child) | ~1,800 | Owns `_sprite_pool`, `_sprite_container`, region calc; game_view just calls `update_sprites(_ents)` |
| After #3 | State Parsing → `StateParser` (RefCounted) | ~1,600 | Pure data transform; no Godot node deps |
| Final | game_view.gd ~1,600 lines | — | Orchestrator: _ready wiring, _input dispatch, _process loop, _draw dispatcher |

---

## 6. Implementation Checklist for Step #1

1. [ ] Create `godot/scripts/test_mode_gallery.gd` with skeleton above
2. [ ] Move all 24 functions and 25 variables from game_view.gd → test_mode_gallery.gd
3. [ ] Wire `_test_gallery` in game_view._ready() (replace inline test-mode setup)
4. [ ] Wire signal handlers `_on_test_entities_rebuilt` and `_on_test_state_changed`
5. [ ] Replace `_test_mode` checks in _process() and _draw() with `_test_gallery.is_active()`
6. [ ] Move zoom/elevation button wiring into test_mode_gallery.setup() (or a separate DebugButtons helper)
7. [ ] Run the project, verify test mode toggle works identically
8. [ ] Run any existing test scripts (e.g. `test_game_view_probe_override.gd`)
9. [ ] Lint: ensure no `:=` on Variant returns (GDScript 4 constraint)
