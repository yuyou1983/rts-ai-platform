class_name TestModeGallery
extends Node2D
## Standalone Test Mode gallery — extracted from GameView.
##
## Manages the asset-preview gallery, filter UI, catalog, animation state,
## and save/restore of game state. Emits signals so that GameView can react
## (swap entity arrays, update sprites, redraw, etc.).

signal entities_rebuilt(new_ents: Array)
signal state_changed()
signal combat_preview_event(event: Dictionary)

const UNIT_TYPE_CATALOG_PATH := "res://resources/unit_type_catalog.json"
const ANIM_FPS := 8.0  # frames per second for walk cycle
const ATTACK_FLASH_DURATION: float = 0.1
const ANIM_CYCLE_PERIOD: float = 3.0   # seconds per animation phase in Animation view
const COMBAT_REPLAY_PERIOD: float = 3.0  # seconds per combat replay cycle
const TESTMODE_WORLD_ORIGIN := Vector2(8.0, 6.0)
const TESTMODE_WORLD_RIGHT_LIMIT := 54.0
const TESTMODE_WORLD_BOTTOM_LIMIT := 58.0

# ─── Internal state ────────────────────────────────────────
var _active: bool = false
var _test_ents: Array = []
var _test_section_headers: Array = []

# ─── Pagination ────────────────────────────────────────────
var _test_page: int = 0
const TESTMODE_ITEMS_PER_PAGE := 24

# ─── Gallery mode ──────────────────────────────────────────
var _gallery_mode: String = "roster"  # "roster" / "scale" / "animation" / "combat"
var _gallery_mode_buttons: Dictionary = {}  # { mode: Button }

# ─── UI elements ───────────────────────────────────────────
var _test_btn: Button = null
var _test_filter_panel: PanelContainer = null
var _test_race_filter: OptionButton = null   # Kept for batch compat
var _test_kind_filter: OptionButton = null   # Kept for batch compat
var _test_batch_filter: OptionButton = null
var _elev_btn: Button = null
var _zoom_in_btn: Button = null
var _zoom_out_btn: Button = null
var _calib_btn: Button = null
var _tint_btn: Button = null
var _neutral_tint_enabled: bool = true
var _prev_page_btn: Button = null
var _next_page_btn: Button = null

# ─── Filter state ──────────────────────────────────────────
var _test_filter_race: String = ""    # "" = all, "terran"/"zerg"/"protoss"
var _test_filter_kind: String = ""    # "" = all, "unit"/"building"
var _test_filter_domain: String = ""  # "" = all, "ground"/"air"
var _test_filter_role: String = ""    # "" = all
var _test_filter_tier: String = ""    # "" = all
var _test_preview_mode: String = "idle"  # "idle"/"move"/"attack"/"death"
var _test_filter_batch: String = "all"

# ─── Filter button groups ──────────────────────────────────
var _race_buttons: Dictionary = {}   # { value: Button }
var _kind_buttons: Dictionary = {}   # { value: Button }
var _domain_buttons: Dictionary = {}  # { value: Button }
var _role_buttons: Dictionary = {}   # { value: Button }
var _tier_buttons: Dictionary = {}   # { value: Button }
var _preview_buttons: Dictionary = {}  # { value: Button }

# ─── Unit type catalog ─────────────────────────────────────
var _unit_type_catalog: Dictionary = {}  # Loaded from unit_type_catalog.json

# ─── Saved game state (for restoring) ───────────────────────
var _saved_ents: Array = []
var _saved_player_races: Dictionary = {}
var _saved_fog_tiles: PackedInt32Array = []
var _saved_fog_w: int = 0
var _saved_fog_h: int = 0

# ─── Animation state ───────────────────────────────────────
var _anim_frame: int = 0
var _anim_tick: float = 0.0
var _attack_flash_timers: Dictionary = {}  # entity_id → remaining flash seconds

# ─── Animation view cycle state ─────────────────────────────
var _anim_cycle_timer: float = 0.0
var _anim_current_phase: int = 0  # 0=idle, 1=move, 2=attack, 3=death
const _ANIM_PHASES: PackedStringArray = ["idle", "move", "attack", "death"]

# ─── Combat view state ─────────────────────────────────────
var _combat_timer: float = 0.0
var _combat_phase: int = 0  # 0=attack, 1=hit, 2=death, 3=reset
var _combat_current_pair: int = 0  # index into _COMBAT_PAIRS
var _combat_pair_positions: Dictionary = {}  # pair_idx → {attacker_pos, target_pos}

const _COMBAT_PAIRS: Array = [
	{"profile": "terran_ballistic", "attacker": "Marine", "target": "Zergling"},
	{"profile": "terran_explosive", "attacker": "Tank", "target": "Dragoon"},
	{"profile": "terran_flame", "attacker": "Firebat", "target": "Zergling"},
	{"profile": "zerg_melee", "attacker": "Zergling", "target": "Marine"},
	{"profile": "zerg_acid", "attacker": "Hydralisk", "target": "Zealot"},
	{"profile": "protoss_psi", "attacker": "Dragoon", "target": "Hydralisk"},
]

# ─── Scale view unit rows ──────────────────────────────────
const _SCALE_ROWS: Array = [
	{"label": "Workers", "units": ["SCV", "Drone", "Probe"]},
	{"label": "Basic Infantry", "units": ["Marine", "Zergling", "Zealot"]},
	{"label": "Townhalls", "units": ["CommandCenter", "Hatchery", "Nexus"]},
	{"label": "Production", "units": ["Barracks", "SpawningPool", "Gateway"]},
]

# ─── External references (injected via setup) ───────────────
var _ui_layer: CanvasLayer = null
var _sprite_loader: RefCounted = null      # SpriteLoader
var _default_font: Font = null
var _entity_cache_by_id: Dictionary = {}
var _sprite_pool: Dictionary = {}    # Injected via setup()
var _cam_ctrl: Node = null           # CameraController (optional)
var _show_elevation: bool = false
var _show_calibration: bool = false
var _calibration_overlay = null  # VisualCalibrationOverlay — set at runtime

# ─── Combat diagnostics overlay (Task 11) ───────────────────
# Only ever visible while Test Mode is active AND a matchup preset has been run.
var _diagnostics_overlay: CombatDiagnosticsOverlay = null
var _combat_preset_buttons: Dictionary = {}  # { preset_index: Button }
var _combat_presets: Array = []              # Loaded from JSON fixture in _build_combat_presets()
var _combat_controller: CombatVisualController = null  # Injected by GameView for event-driven VFX


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────

func is_active() -> bool:
	return _active


func setup(ui_layer: CanvasLayer, sprite_loader: RefCounted, default_font: Font,
		entity_cache_by_id: Dictionary, sprite_pool: Dictionary = {},
		cam_ctrl: Node = null) -> void:
	_ui_layer = ui_layer
	_sprite_loader = sprite_loader
	_default_font = default_font
	_entity_cache_by_id = entity_cache_by_id
	_sprite_pool = sprite_pool
	_cam_ctrl = cam_ctrl
	_load_unit_type_catalog()

	# ── Test Mode button ──
	_test_btn = Button.new()
	_test_btn.text = "🧪 Test Mode"
	_test_btn.tooltip_text = "Click to preview all sprites on map"
	_test_btn.position = Vector2(8, 8)
	_test_btn.size = Vector2(120, 32)
	_test_btn.modulate = Color(0.8, 1.0, 0.8)
	_ui_layer.add_child(_test_btn)
	_test_btn.pressed.connect(toggle)

	_create_gallery_mode_tabs()
	_create_test_filter_panel()

	# ── Elevation toggle button (below test button) ──
	_elev_btn = Button.new()
	_elev_btn.text = "⛰ Elev"
	_elev_btn.tooltip_text = "Toggle terrain elevation overlay"
	_elev_btn.position = Vector2(8, 42)
	_elev_btn.size = Vector2(120, 24)
	_elev_btn.modulate = Color(0.7, 0.85, 0.7)
	_ui_layer.add_child(_elev_btn)
	_elev_btn.pressed.connect(_toggle_elevation)

	# ── Calibration overlay toggle button (below elev button) ──
	_calib_btn = Button.new()
	_calib_btn.text = "📐 Cal"
	_calib_btn.tooltip_text = "Toggle visual calibration overlay"
	_calib_btn.position = Vector2(8, 68)
	_calib_btn.size = Vector2(120, 24)
	_calib_btn.modulate = Color(0.7, 0.7, 0.85)
	_ui_layer.add_child(_calib_btn)
	_calib_btn.pressed.connect(_toggle_calibration)

	# ── Tint toggle button ──
	_tint_btn = Button.new()
	_tint_btn.text = "🎨 Tint"
	_tint_btn.tooltip_text = "Toggle neutral team tint (original colors)"
	_tint_btn.position = Vector2(8, 94)
	_tint_btn.size = Vector2(120, 24)
	_tint_btn.modulate = Color(0.7, 0.7, 0.85)
	_tint_btn.toggle_mode = true
	_tint_btn.button_pressed = true
	_ui_layer.add_child(_tint_btn)
	_tint_btn.pressed.connect(_toggle_tint)

	# ── Zoom buttons ──
	_zoom_in_btn = Button.new()
	_zoom_in_btn.text = "🔍+"
	_zoom_in_btn.position = Vector2(4, 120)
	_zoom_in_btn.size = Vector2(40, 24)
	_zoom_in_btn.modulate = Color(0.9, 0.95, 1.0)
	_ui_layer.add_child(_zoom_in_btn)
	_zoom_in_btn.pressed.connect(func(): _cam_ctrl._zoom_in() if _cam_ctrl else null)

	_zoom_out_btn = Button.new()
	_zoom_out_btn.text = "🔍-"
	_zoom_out_btn.position = Vector2(46, 120)
	_zoom_out_btn.size = Vector2(40, 24)
	_zoom_out_btn.modulate = Color(0.9, 0.95, 1.0)
	_ui_layer.add_child(_zoom_out_btn)
	_zoom_out_btn.pressed.connect(func(): _cam_ctrl._zoom_out() if _cam_ctrl else null)

	# ── Pagination buttons ──
	_prev_page_btn = Button.new()
	_prev_page_btn.text = "◀ Page"
	_prev_page_btn.tooltip_text = "Previous page"
	_prev_page_btn.position = Vector2(4, 146)
	_prev_page_btn.size = Vector2(56, 24)
	_prev_page_btn.modulate = Color(0.85, 0.85, 0.9)
	_ui_layer.add_child(_prev_page_btn)
	_prev_page_btn.pressed.connect(_on_prev_page)

	_next_page_btn = Button.new()
	_next_page_btn.text = "Page ▶"
	_next_page_btn.tooltip_text = "Next page"
	_next_page_btn.position = Vector2(64, 146)
	_next_page_btn.size = Vector2(56, 24)
	_next_page_btn.modulate = Color(0.85, 0.85, 0.9)
	_ui_layer.add_child(_next_page_btn)
	_next_page_btn.pressed.connect(_on_next_page)

	# ── Combat diagnostics overlay + matchup preset buttons (Task 11) ──
	_create_diagnostics_overlay()
	_create_combat_preset_buttons()


func set_sprite_pool(sprite_pool: Dictionary) -> void:
	_sprite_pool = sprite_pool


func toggle_elevation() -> void:
	_toggle_elevation()


func is_elevation_active() -> bool:
	return _show_elevation

func is_calibration_active() -> bool:
	return _show_calibration

func get_calibration_overlay():  # returns VisualCalibrationOverlay at runtime
	return _calibration_overlay


# ── Combat diagnostics overlay (Task 11) ──

## Inject a CombatDiagnosticsOverlay created elsewhere (e.g. by GameView).
## When omitted, the gallery creates its own in _create_diagnostics_overlay().
func set_diagnostics_overlay(overlay: CombatDiagnosticsOverlay) -> void:
	if _diagnostics_overlay and is_instance_valid(_diagnostics_overlay) and _diagnostics_overlay != overlay:
		_diagnostics_overlay.queue_free()
	_diagnostics_overlay = overlay
	if _diagnostics_overlay:
		_diagnostics_overlay.test_mode_active = _active

func get_diagnostics_overlay() -> CombatDiagnosticsOverlay:
	return _diagnostics_overlay


## Inject the GameView's CombatVisualController so preset combat events are
## routed through the real event-driven VFX pipeline instead of a synthetic
## preview signal.
func set_combat_controller(controller: CombatVisualController) -> void:
	_combat_controller = controller


func get_combat_controller() -> CombatVisualController:
	return _combat_controller


func toggle() -> void:
	_active = not _active
	if _active:
		_build_test_entities()
		if _test_filter_panel:
			_test_filter_panel.visible = true
		_show_gallery_mode_tabs(true)
		if _test_btn:
			_test_btn.text = "Back"
			_test_btn.modulate = Color(1.0, 0.8, 0.8)
		if _diagnostics_overlay:
			_diagnostics_overlay.test_mode_active = true
		_update_combat_preset_visibility()
		print("[TEST MODE] ON — generated asset gallery (mode: %s)" % _gallery_mode)
	else:
		_clear_test_sprites()
		_test_ents.clear()
		_test_section_headers.clear()
		if _test_filter_panel:
			_test_filter_panel.visible = false
		_show_gallery_mode_tabs(false)
		if _test_btn:
			_test_btn.text = "🧪 Test Mode"
			_test_btn.modulate = Color(0.8, 1.0, 0.8)
		if _diagnostics_overlay:
			_diagnostics_overlay.test_mode_active = false
			_diagnostics_overlay.hide_overlay()
		_update_combat_preset_visibility()
		print("[TEST MODE] OFF — back to normal game")
	state_changed.emit()


func build() -> void:
	_build_test_entities()


func clear() -> void:
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()


func save_state(ents: Array, player_races: Dictionary, fog_tiles: PackedInt32Array,
		fog_w: int, fog_h: int) -> void:
	_saved_ents = ents.duplicate(true)
	_saved_player_races = player_races.duplicate(true)
	_saved_fog_tiles = fog_tiles
	_saved_fog_w = fog_w
	_saved_fog_h = fog_h


func get_saved_state() -> Dictionary:
	return {
		"ents": _saved_ents.duplicate(true),
		"player_races": _saved_player_races.duplicate(true),
		"fog_tiles": _saved_fog_tiles,
		"fog_w": _saved_fog_w,
		"fog_h": _saved_fog_h,
	}


var _use_screen_labels: bool = true

func draw_labels(canvas: CanvasItem) -> void:
	if _use_screen_labels:
		return  # Labels handled by TestModeLabelLayer instead
	var font: Font = _default_font
	if not font:
		return
	var title_size := 1.2
	var label_size := 0.8
	var vc_label_size := 0.55
	var info_label_size := 0.38
	for header in _test_section_headers:
		canvas.draw_string(
			font,
			header.get("pos", Vector2.ZERO),
			str(header.get("text", "")),
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			title_size,
			header.get("color", Color.WHITE)
		)
	for e in _test_ents:
		if not str(e.get("id", "")).begins_with("test_"):
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
			label_size,
			Color(1, 1, 1, 0.9)
		)
		# Visual class grouping label below the sprite
		var vc = str(e.get("visual_class", ""))
		if vc != "":
			var entity_type = str(e.get("entity_type", ""))
			var vc_y_offset = 2.5 if entity_type == "unit" else 4.2 if entity_type == "building" else 2.5
			canvas.draw_string(
				font,
				Vector2(float(e.get("px", 0.0)) + 1.3, float(e.get("py", 0.0)) + vc_y_offset),
				vc,
				HORIZONTAL_ALIGNMENT_LEFT,
				-1,
				vc_label_size,
				Color(0.7, 0.9, 1.0, 0.7)
			)
		# Calibration info below visual class label
		var render_scale_val = str(e.get("render_scale", ""))
		var sel_radius_val = str(e.get("selection_radius", ""))
		var footprint_val = ""
		var vfx_profile_val = str(e.get("vfx_profile", ""))
		var gen_id = str(e.get("generated_asset_id", e.get("unit_type", e.get("building_type", ""))))
		# Look up footprint from manifest if available
		var footprint_data = _get_footprint_for_entity(e)
		if not footprint_data.is_empty():
			footprint_val = "%s×%s" % [str(footprint_data.get("w", "")), str(footprint_data.get("h", ""))]
		var entity_type = str(e.get("entity_type", ""))
		var info_y_offset = 2.5 + 0.45 if entity_type == "unit" else 4.2 + 0.45 if entity_type == "building" else 2.95
		if vc != "":
			info_y_offset += 0.30
		# Build info lines
		var info_lines := PackedStringArray()
		info_lines.append("id:%s  rs:%s  sr:%s" % [gen_id, render_scale_val, sel_radius_val])
		if footprint_val != "":
			info_lines.append("fp:%s  vfx:%s" % [footprint_val, vfx_profile_val])
		else:
			info_lines.append("vfx:%s" % vfx_profile_val)
		for i in range(info_lines.size()):
			canvas.draw_string(
				font,
				Vector2(float(e.get("px", 0.0)) + 1.3, float(e.get("py", 0.0)) + info_y_offset + float(i) * 0.25),
				info_lines[i],
				HORIZONTAL_ALIGNMENT_LEFT,
				-1,
				info_label_size,
				Color(0.65, 0.75, 0.85, 0.55)
			)


func get_screen_labels() -> Array:
	var labels: Array = []
	for header in _test_section_headers:
		labels.append({
			"world_pos": header.get("pos", Vector2.ZERO),
			"text": str(header.get("text", "")),
			"color": header.get("color", Color.WHITE),
		})
	for e in _test_ents:
		if not str(e.get("id", "")).begins_with("test_"):
			continue
		if bool(e.get("preview_hidden", false)):
			continue
		var text := str(e.get("label", ""))
		if text != "":
			labels.append({
				"world_pos": Vector2(float(e.get("px", 0.0)) + 0.6, float(e.get("py", 0.0)) + 0.9),
				"text": text,
				"color": Color(0.95, 0.95, 0.9, 0.95),
			})
	return labels


func _get_footprint_for_entity(e: Dictionary) -> Dictionary:
	var entity_type = str(e.get("entity_type", ""))
	var visual_id = str(e.get("generated_asset_id", e.get("unit_type", e.get("building_type", ""))))
	if visual_id == "":
		return {}
	# Try to load manifest if not already loaded
	if _presentation_manifest.is_empty():
		_load_presentation_manifest()
	if _presentation_manifest.is_empty():
		return {}
	var section: String = "building_visuals" if entity_type == "building" else "unit_visuals"
	var entry: Dictionary = _presentation_manifest.get(section, {}).get(visual_id, {})
	if entry.is_empty():
		return {}
	var fp = entry.get("footprint", {})
	if fp is Dictionary:
		return fp
	if fp is Array and fp.size() >= 2:
		return {"w": float(fp[0]), "h": float(fp[1])}
	return {}


var _presentation_manifest: Dictionary = {}

func _load_presentation_manifest() -> void:
	var path: String = "res://resources/presentation_manifest.json"
	if not FileAccess.file_exists(path):
		return
	var raw_text: String = FileAccess.get_file_as_string(path)
	var parsed = JSON.parse_string(raw_text)
	if parsed is Dictionary:
		_presentation_manifest = parsed


func advance_animation(delta: float) -> void:
	if not _active:
		return
	_anim_tick += delta
	if _anim_tick >= 1.0 / ANIM_FPS:
		_anim_tick -= 1.0 / ANIM_FPS
		_anim_frame = (_anim_frame + 1) % 17
		for e in _test_ents:
			if str(e.get("preview_action", "")) == "attack":
				_attack_flash_timers[str(e.get("id", ""))] = ATTACK_FLASH_DURATION
		state_changed.emit()


func get_anim_frame() -> int:
	return _anim_frame


func get_attack_flash_timers() -> Dictionary:
	return _attack_flash_timers


func tick_attack_flash_timers(delta: float) -> void:
	var flash_ids: Array = _attack_flash_timers.keys()
	for eid in flash_ids:
		var remaining: float = float(_attack_flash_timers[eid]) - delta
		if remaining <= 0.0:
			_attack_flash_timers.erase(eid)
		else:
			_attack_flash_timers[eid] = remaining


# ────────────────────────────────────────────────────────────
# _process — Animation cycle, Combat replay, F12 screenshot
# ────────────────────────────────────────────────────────────

func _process(delta: float) -> void:
	if not _active:
		return

	# Animation view: auto-cycle idle→move→attack→death
	if _gallery_mode == "animation":
		_anim_cycle_timer += delta
		if _anim_cycle_timer >= ANIM_CYCLE_PERIOD:
			_anim_cycle_timer -= ANIM_CYCLE_PERIOD
			_anim_current_phase = (_anim_current_phase + 1) % _ANIM_PHASES.size()
			_test_preview_mode = _ANIM_PHASES[_anim_current_phase]
			# Update preview button highlights
			for val in _preview_buttons:
				var btn: Button = _preview_buttons[val]
				if val == _test_preview_mode:
					btn.button_pressed = true
					btn.modulate = Color(0.5, 1.0, 0.5)
				else:
					btn.button_pressed = false
					btn.modulate = Color(0.85, 0.85, 0.85)
			_build_test_entities()
			print("[TEST MODE] Animation phase: %s" % _test_preview_mode)

	# Combat view: replay cycle
	if _gallery_mode == "combat":
		_combat_timer += delta
		if _combat_timer >= COMBAT_REPLAY_PERIOD:
			_combat_timer -= COMBAT_REPLAY_PERIOD
			_combat_phase = (_combat_phase + 1) % 4
			if _combat_phase == 0:
				_combat_current_pair = (_combat_current_pair + 1) % _COMBAT_PAIRS.size()
			_update_combat_phase()


func _update_combat_phase() -> void:
	if _test_ents.is_empty():
		return
	# Find attacker and target entities and update their preview_action
	var pair = _COMBAT_PAIRS[_combat_current_pair]
	var attacker_id_prefix = "test_unit_%s" % pair["attacker"]
	var target_id_prefix = "test_unit_%s" % pair["target"]

	# Emit combat preview event for VFX system
	var profile_name: String = str(pair.get("profile", "none"))
	var positions: Dictionary = _combat_pair_positions.get(_combat_current_pair, {})
	var source_pos: Vector2 = positions.get("attacker_pos", Vector2.ZERO)
	var target_pos: Vector2 = positions.get("target_pos", Vector2.ZERO)

	combat_preview_event.emit({
		"event_type": "projectile_fired",
		"vfx_profile": profile_name,
		"source_pos": source_pos,
		"target_pos": target_pos,
	})

	for e in _test_ents:
		var eid = str(e.get("id", ""))
		match _combat_phase:
			0:  # attack phase
				if eid.begins_with(attacker_id_prefix) and "attack" in eid:
					e["preview_action"] = "attack"
				elif eid.begins_with(target_id_prefix) and "idle" in eid:
					e["preview_action"] = "idle"
			1:  # hit phase — flash target
				if eid.begins_with(attacker_id_prefix) and "attack" in eid:
					e["preview_action"] = "attack"
				elif eid.begins_with(target_id_prefix) and "idle" in eid:
					e["preview_action"] = "idle"
					_attack_flash_timers[eid] = ATTACK_FLASH_DURATION * 5.0
			2:  # death phase
				if eid.begins_with(attacker_id_prefix) and "attack" in eid:
					e["preview_action"] = "idle"
				elif eid.begins_with(target_id_prefix) and "idle" in eid:
					e["preview_action"] = "death"
			3:  # reset
				if eid.begins_with(attacker_id_prefix):
					e["preview_action"] = "idle"
				elif eid.begins_with(target_id_prefix):
					e["preview_action"] = "idle"
	state_changed.emit()


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_F12:
		_take_screenshot()
	elif event is InputEventKey and event.pressed and event.keycode == KEY_F11:
		if _active:
			_export_all_mode_screenshots()


func _take_screenshot() -> void:
	var img: Image = get_viewport().get_texture().get_image()
	var dir_path: String = "user://screenshots"
	DirAccess.make_dir_recursive_absolute(dir_path)
	var timestamp: String = Time.get_datetime_string_from_system().replace(":", "-")
	var mode_suffix: String = "_" + _gallery_mode if _active else ""
	var file_name: String = "testmode%s_%s.png" % [mode_suffix, timestamp]
	var full_path: String = dir_path.path_join(file_name)
	var err: int = img.save_png(full_path)
	if err == OK:
		print("[TEST MODE] Screenshot saved: %s" % full_path)
	else:
		push_warning("[TEST MODE] Screenshot save failed (error %d): %s" % [err, full_path])


func _export_all_mode_screenshots() -> void:
	var exporter: TestmodeScreenshotExporter = TestmodeScreenshotExporter.new()
	add_child(exporter)
	exporter.setup(self)
	exporter.export_all_modes()


# ────────────────────────────────────────────────────────────
# Gallery mode tab buttons
# ────────────────────────────────────────────────────────────

func _create_gallery_mode_tabs() -> void:
	var modes: PackedStringArray = ["roster", "scale", "animation", "combat"]
	var labels: PackedStringArray = ["📋 Roster", "📐 Scale", "🎬 Animation", "⚔ Combat"]
	for i in range(modes.size()):
		var btn := Button.new()
		btn.text = labels[i]
		btn.toggle_mode = true
		btn.visible = false  # hidden until test mode is active
		btn.position = Vector2(8, 126 + i * 26)
		btn.size = Vector2(120, 24)
		var mode_val: String = modes[i]
		if mode_val == _gallery_mode:
			btn.button_pressed = true
			btn.modulate = Color(0.5, 1.0, 0.5)
		else:
			btn.modulate = Color(0.85, 0.85, 0.85)
		btn.pressed.connect(_on_gallery_mode_btn.bind(mode_val))
		_ui_layer.add_child(btn)
		_gallery_mode_buttons[mode_val] = btn


func _show_gallery_mode_tabs(show: bool) -> void:
	for mode_val in _gallery_mode_buttons:
		var btn: Button = _gallery_mode_buttons[mode_val]
		btn.visible = show
		if mode_val == _gallery_mode:
			btn.button_pressed = true
			btn.modulate = Color(0.5, 1.0, 0.5)
		else:
			btn.button_pressed = false
			btn.modulate = Color(0.85, 0.85, 0.85)


func _on_gallery_mode_btn(mode: String) -> void:
	_gallery_mode = mode
	# Update button highlights
	for mode_val in _gallery_mode_buttons:
		var btn: Button = _gallery_mode_buttons[mode_val]
		if mode_val == mode:
			btn.button_pressed = true
			btn.modulate = Color(0.5, 1.0, 0.5)
		else:
			btn.button_pressed = false
			btn.modulate = Color(0.85, 0.85, 0.85)
	# Reset animation/combat timers
	_anim_cycle_timer = 0.0
	_anim_current_phase = 0
	_combat_timer = 0.0
	_combat_phase = 0
	_combat_current_pair = 0
	# Update preview mode based on gallery mode
	if _gallery_mode == "animation":
		_test_preview_mode = "idle"
	elif _gallery_mode == "combat":
		_test_preview_mode = "idle"
	# Show/hide filter panel (only visible in roster mode)
	if _test_filter_panel:
		_test_filter_panel.visible = (_gallery_mode == "roster")
	if _active:
		_build_test_entities()
	# Combat diagnostics preset buttons are only relevant in combat mode.
	_update_combat_preset_visibility()
	if _diagnostics_overlay and mode != "combat":
		_diagnostics_overlay.hide_overlay()
	print("[TEST MODE] Switched to gallery mode: %s" % mode)


# ── Public methods for TestModeUIController integration ──

func set_gallery_mode(mode: String) -> void:
	_on_gallery_mode_btn(mode)

func set_filter(key: String, value: String) -> void:
	match key:
		"race":
			_test_filter_race = value
		"kind":
			_test_filter_kind = value
		"domain":
			_test_filter_domain = value
		"role":
			_test_filter_role = value
		"tier":
			_test_filter_tier = value
		"preview":
			_test_preview_mode = value
		"batch":
			_test_filter_batch = value
	if _active:
		_build_test_entities()


# ────────────────────────────────────────────────────────────
# Filter panel creation
# ────────────────────────────────────────────────────────────

func _create_test_filter_panel() -> void:
	_test_filter_panel = PanelContainer.new()
	_test_filter_panel.visible = false
	_test_filter_panel.anchor_left = 0.0
	_test_filter_panel.anchor_top = 0.0
	_test_filter_panel.anchor_right = 0.0
	_test_filter_panel.anchor_bottom = 0.0
	_test_filter_panel.offset_left = 168
	_test_filter_panel.offset_top = 8
	_test_filter_panel.offset_right = -320
	_test_filter_panel.offset_bottom = 175
	_ui_layer.add_child(_test_filter_panel)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	_test_filter_panel.add_child(vbox)

	# Row 1: Race filter
	var row1 := HBoxContainer.new()
	row1.add_theme_constant_override("separation", 4)
	vbox.add_child(row1)
	_add_row_label(row1, "Race:")
	_race_buttons = _make_toggle_group(row1, ["All", "Terran", "Zerg", "Protoss"],
		["", "terran", "zerg", "protoss"], _test_filter_race, "_on_race_filter_btn")

	# Row 2: Kind filter
	var row2 := HBoxContainer.new()
	row2.add_theme_constant_override("separation", 4)
	vbox.add_child(row2)
	_add_row_label(row2, "Type:")
	_kind_buttons = _make_toggle_group(row2, ["All", "Units", "Buildings"],
		["", "unit", "building"], _test_filter_kind, "_on_kind_filter_btn")

	# Row 3: Domain filter
	var row3 := HBoxContainer.new()
	row3.add_theme_constant_override("separation", 4)
	vbox.add_child(row3)
	_add_row_label(row3, "Domain:")
	_domain_buttons = _make_toggle_group(row3, ["All", "Ground", "Air"],
		["", "ground", "air"], _test_filter_domain, "_on_domain_filter_btn")

	# Row 4: Role filter
	var row4 := HBoxContainer.new()
	row4.add_theme_constant_override("separation", 4)
	vbox.add_child(row4)
	_add_row_label(row4, "Role:")
	_role_buttons = _make_toggle_group(row4, ["All", "Worker", "Infantry", "Vehicle", "Air", "Caster", "Siege", "Support"],
		["", "worker", "infantry", "vehicle", "air", "caster", "siege", "support"], _test_filter_role, "_on_role_filter_btn")

	# Row 5: Tier filter
	var row5 := HBoxContainer.new()
	row5.add_theme_constant_override("separation", 4)
	vbox.add_child(row5)
	_add_row_label(row5, "Tier:")
	_tier_buttons = _make_toggle_group(row5, ["All", "Basic", "Advanced", "Tech"],
		["", "basic", "advanced", "tech"], _test_filter_tier, "_on_tier_filter_btn")

	# Row 6: Preview mode (includes "death" for Animation view)
	var row6 := HBoxContainer.new()
	row6.add_theme_constant_override("separation", 4)
	vbox.add_child(row6)
	_add_row_label(row6, "Preview:")
	_preview_buttons = _make_toggle_group(row6, ["Idle", "Move", "Attack", "Death"],
		["idle", "move", "attack", "death"], _test_preview_mode, "_on_preview_mode_btn")

	# Keep batch filter as OptionButton (it has dynamic content)
	var batch_row := HBoxContainer.new()
	batch_row.add_theme_constant_override("separation", 4)
	vbox.add_child(batch_row)
	_add_row_label(batch_row, "Batch:")
	_test_batch_filter = OptionButton.new()
	_add_filter_item(_test_batch_filter, "All", "all")
	if _sprite_loader:
		var batches = _sprite_loader.get_batches()
		for b in batches:
			var b_str = str(b)
			_add_filter_item(_test_batch_filter, b_str.to_upper(), b_str.to_lower())
	_test_batch_filter.item_selected.connect(_on_test_batch_filter_selected)
	batch_row.add_child(_test_batch_filter)


func _add_row_label(row: HBoxContainer, text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.custom_minimum_size.x = 60
	row.add_child(lbl)


func _make_toggle_group(
	row: HBoxContainer,
	labels: Array,
	values: Array,
	current: String,
	callback: String
) -> Dictionary:
	# Returns { value: Button } dictionary for highlight management
	var buttons: Dictionary = {}
	for i in range(labels.size()):
		var btn := Button.new()
		btn.text = labels[i]
		btn.toggle_mode = true
		# Highlight active button
		var val: String = values[i]
		if val == current:
			btn.button_pressed = true
			btn.modulate = Color(0.5, 1.0, 0.5)
		else:
			btn.modulate = Color(0.85, 0.85, 0.85)
		btn.pressed.connect(_on_filter_btn_pressed.bind(val, callback, buttons))
		row.add_child(btn)
		buttons[val] = btn
	return buttons


func _on_filter_btn_pressed(value: String, callback: String, buttons: Dictionary) -> void:
	# Update button highlights
	for btn_val in buttons:
		var btn: Button = buttons[btn_val]
		if btn_val == value:
			btn.button_pressed = true
			btn.modulate = Color(0.5, 1.0, 0.5)
		else:
			btn.button_pressed = false
			btn.modulate = Color(0.85, 0.85, 0.85)
	# Dispatch to specific handler
	call(callback, value)


# ────────────────────────────────────────────────────────────
# Filter callbacks
# ────────────────────────────────────────────────────────────

func _on_race_filter_btn(value: String) -> void:
	_test_filter_race = value
	_test_page = 0
	if _active and _gallery_mode == "roster":
		_build_test_entities()


func _on_kind_filter_btn(value: String) -> void:
	_test_filter_kind = value
	_test_page = 0
	if _active and _gallery_mode == "roster":
		_build_test_entities()


func _on_domain_filter_btn(value: String) -> void:
	_test_filter_domain = value
	_test_page = 0
	if _active and _gallery_mode == "roster":
		_build_test_entities()


func _on_role_filter_btn(value: String) -> void:
	_test_filter_role = value
	_test_page = 0
	if _active and _gallery_mode == "roster":
		_build_test_entities()


func _on_tier_filter_btn(value: String) -> void:
	_test_filter_tier = value
	_test_page = 0
	if _active and _gallery_mode == "roster":
		_build_test_entities()


func _on_preview_mode_btn(value: String) -> void:
	_test_preview_mode = value
	_test_page = 0
	if _active:
		_build_test_entities()


func _add_filter_item(option: OptionButton, label: String, value: String) -> void:
	option.add_item(label)
	option.set_item_metadata(option.item_count - 1, value)


func _on_test_batch_filter_selected(index: int) -> void:
	if _test_batch_filter == null:
		return
	_test_filter_batch = str(_test_batch_filter.get_item_metadata(index))
	_test_page = 0
	if _active and _gallery_mode == "roster":
		_build_test_entities()


# ────────────────────────────────────────────────────────────
# Pagination callbacks
# ────────────────────────────────────────────────────────────

func _on_prev_page() -> void:
	if _test_page > 0:
		_test_page -= 1
		_build_test_entities()

func _on_next_page() -> void:
	var test_count := 0
	for e in _test_ents:
		if str(e.get("id", "")).begins_with("test_"):
			test_count += 1
	var max_page := maxi(0, ceili(float(test_count) / float(TESTMODE_ITEMS_PER_PAGE)) - 1)
	if _test_page < max_page:
		_test_page += 1
		_build_test_entities()


# ────────────────────────────────────────────────────────────
# Toggle elevation
# ────────────────────────────────────────────────────────────

func _toggle_elevation() -> void:
	_show_elevation = not _show_elevation
	if _elev_btn:
		_elev_btn.text = "⛰ Elev ON" if _show_elevation else "⛰ Elev"
		_elev_btn.modulate = Color(0.5, 1.0, 0.5) if _show_elevation else Color(0.7, 0.85, 0.7)
	state_changed.emit()


func _toggle_calibration() -> void:
	_show_calibration = not _show_calibration
	if _calib_btn:
		_calib_btn.text = "📐 Cal ON" if _show_calibration else "📐 Cal"
		_calib_btn.modulate = Color(0.5, 1.0, 0.5) if _show_calibration else Color(0.7, 0.7, 0.85)
	if _calibration_overlay:
		_calibration_overlay.active = _show_calibration
	state_changed.emit()


func _toggle_tint() -> void:
	_neutral_tint_enabled = _tint_btn.button_pressed
	for e in _test_ents:
		e["neutral_team_tint"] = _neutral_tint_enabled
	entities_rebuilt.emit(_test_ents)


# ────────────────────────────────────────────────────────────
# Catalog loading & filtering
# ────────────────────────────────────────────────────────────

func _load_unit_type_catalog() -> void:
	if not FileAccess.file_exists(UNIT_TYPE_CATALOG_PATH):
		push_warning("[TestModeGallery] Missing unit type catalog: %s — falling back to unfiltered test mode" % UNIT_TYPE_CATALOG_PATH)
		_unit_type_catalog = {}
		return
	var raw_text: String = FileAccess.get_file_as_string(UNIT_TYPE_CATALOG_PATH)
	var parsed = JSON.parse_string(raw_text)
	if parsed is Dictionary:
		# Strip _meta key — it's not a unit entry
		_unit_type_catalog = {}
		for key in parsed.keys():
			if key.casecmp_to("_meta") != 0:
				var entry: Dictionary = parsed[key]
				if entry is Dictionary:
					_unit_type_catalog[key] = entry
		if _unit_type_catalog.size() > 0:
			print("[TestModeGallery] Unit type catalog loaded: %d entries" % _unit_type_catalog.size())
		else:
			push_warning("[TestModeGallery] Unit type catalog was empty after stripping _meta")
			_unit_type_catalog = {}
	else:
		push_warning("[TestModeGallery] Invalid unit type catalog: %s" % UNIT_TYPE_CATALOG_PATH)
		_unit_type_catalog = {}


## Check whether a unit_type passes all current filter state using the catalog.
## Returns true if the unit should be shown, false if filtered out.
## When catalog is empty (failed to load), always returns true (backward compat).
func _catalog_passes_filters(unit_id: String) -> bool:
	if _unit_type_catalog.is_empty():
		return true  # Backward compatibility: show all if no catalog
	var entry: Dictionary = _unit_type_catalog.get(unit_id, {})
	if entry.is_empty():
		# Unit not in catalog — still show it (backward compat)
		return true
	# Race filter
	if _test_filter_race != "":
		var race: String = str(entry.get("race", "")).to_lower()
		if race != _test_filter_race:
			return false
	# Kind filter
	if _test_filter_kind != "":
		var kind: String = str(entry.get("kind", "")).to_lower()
		if kind != _test_filter_kind:
			return false
	# Domain filter
	if _test_filter_domain != "":
		var domain: String = str(entry.get("domain", "")).to_lower()
		if domain != _test_filter_domain:
			return false
	# Role filter
	if _test_filter_role != "":
		var role: String = str(entry.get("role", "")).to_lower()
		if role != _test_filter_role:
			return false
	# Tier filter
	if _test_filter_tier != "":
		var tier: String = str(entry.get("tier", "")).to_lower()
		if tier != _test_filter_tier:
			return false
	return true


# ────────────────────────────────────────────────────────────
# Build / clear test entities — dispatches by _gallery_mode
# ────────────────────────────────────────────────────────────

func _build_test_entities() -> void:
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()

	match _gallery_mode:
		"roster":
			_create_view_roster()
		"scale":
			_create_view_scale()
		"animation":
			_create_view_animation()
		"combat":
			_create_view_combat()
		_:
			_create_view_roster()

	entities_rebuilt.emit(_test_ents)


func _clear_test_entities() -> void:
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()


func _clear_test_sprites() -> void:
	var to_remove: Array = []
	for eid in _sprite_pool:
		if str(eid).begins_with("test_"):
			_sprite_pool[eid].queue_free()
			to_remove.append(eid)
	for eid in to_remove:
		_sprite_pool.erase(eid)


# ────────────────────────────────────────────────────────────
# Roster view — existing behavior
# ────────────────────────────────────────────────────────────

func _create_view_roster() -> void:
	var assets: Dictionary = _sprite_loader.get_generated_assets() if _sprite_loader else {}
	# Apply batch filter first — use SpriteLoader batch API if active
	if _test_filter_batch != "all" and _sprite_loader:
		var batch_assets = _sprite_loader.get_assets_by_batch(_test_filter_batch)
		assets = batch_assets
	var kind_x: Dictionary = {"building": 10.0, "unit": 28.0, "resource": 50.0}
	var kind_title: Dictionary = {"building": "Buildings", "unit": "Units", "resource": "Resources"}
	var race_order: Array = ["terran", "zerg", "protoss", "neutral"]
	var kind_order: Array = ["building", "unit", "resource"]

	for kind in kind_order:
		# Kind filter: if catalog is loaded, filter uses "" for "all"
		var kind_filter_val: String = _test_filter_kind if _unit_type_catalog.is_empty() else _test_filter_kind
		if kind_filter_val != "" and kind_filter_val != kind:
			continue
		# Legacy compat: old filter used "all" for all
		if _unit_type_catalog.is_empty() and _test_filter_kind != "" and _test_filter_kind != kind:
			continue
		var x: float = float(kind_x[kind])
		var y: float = 4.0
		_add_test_header(kind_title[kind], Vector2(x, 2.5), Color(0.75, 0.9, 1.0))
		for race in race_order:
			var race_filter_val: String = _test_filter_race
			if race_filter_val != "" and race_filter_val != race:
				continue
			var ids: Array = []
			for asset_id in assets.keys():
				var entry: Dictionary = assets[asset_id]
				if str(entry.get("kind", "")) != kind:
					continue
				# Use catalog for additional filtering (domain, role, tier)
				if not _catalog_passes_filters(str(asset_id)):
					continue
				if _test_asset_race(str(asset_id), entry) != race:
					continue
				ids.append(str(asset_id))
			# Sort buildings by (race, tech_tier); sort units by (race, visual_class)
			if kind == "building":
				ids.sort_custom(func(a, b):
					var ea = assets.get(a, {})
					var eb = assets.get(b, {})
					var ta = int(ea.get("tech_tier", 1))
					var tb = int(eb.get("tech_tier", 1))
					if ta != tb:
						return ta < tb
					return a.casecmp_to(b) < 0
				)
			elif kind == "unit":
				ids.sort_custom(func(a, b):
					var ea = assets.get(a, {})
					var eb = assets.get(b, {})
					var vca = str(ea.get("visual_class", ""))
					var vcb = str(eb.get("visual_class", ""))
					if vca != vcb:
						return vca.casecmp_to(vcb) < 0
					return a.casecmp_to(b) < 0
				)
			else:
				ids.sort()
			if ids.is_empty():
				continue

			_add_test_header(
				"%s %s" % [_test_race_label(race), kind_title[kind]],
				Vector2(x, y),
				_test_race_color(race)
			)
			y += 2.0

			for asset_id in ids:
				var entry: Dictionary = assets[asset_id]
				if kind == "unit":
					# Preview mode controls which unit poses are shown
					match _test_preview_mode:
						"idle":
							_test_ents.append(_make_test_asset_entity(asset_id, entry, race, "unit", Vector2(x, y), ""))
							y += 3.2
						"move":
							_test_ents.append(_make_test_asset_entity(asset_id, entry, race, "unit", Vector2(x, y), "moving"))
							y += 3.2
						"attack":
							_add_test_unit_pair(asset_id, entry, race, Vector2(x, y))
							y += 3.2
						"death":
							_test_ents.append(_make_test_asset_entity(asset_id, entry, race, "unit", Vector2(x, y), "death"))
							y += 3.2
						_:
							# Fallback: show all four (legacy behavior)
							_add_test_unit_pair(asset_id, entry, race, Vector2(x, y))
							y += 3.2
				else:
					_test_ents.append(_make_test_asset_entity(asset_id, entry, race, kind, Vector2(x, y)))
					y += 4.6 if kind == "building" else 3.0

	# Apply pagination — hide entities beyond current page
	var test_ids: Array = []
	for e in _test_ents:
		if str(e.get("id", "")).begins_with("test_"):
			test_ids.append(e)
	var start := _test_page * TESTMODE_ITEMS_PER_PAGE
	for i in range(test_ids.size()):
		var e = test_ids[i]
		if i < start or i >= start + TESTMODE_ITEMS_PER_PAGE:
			e["preview_hidden"] = true
		else:
			e["preview_hidden"] = false
	var total_count := test_ids.size()
	var total_pages := maxi(1, ceili(float(total_count) / float(TESTMODE_ITEMS_PER_PAGE)))
	_add_test_header("Page %d/%d (%d items)" % [_test_page + 1, total_pages, total_count], Vector2(8.0, 52.0), Color(0.9, 0.9, 0.7))


# ────────────────────────────────────────────────────────────
# Scale view — three-race side-by-side comparison
# ────────────────────────────────────────────────────────────

func _create_view_scale() -> void:
	var assets: Dictionary = _sprite_loader.get_generated_assets() if _sprite_loader else {}
	var start_x: float = 5.0
	var start_y: float = 4.0
	var col_spacing: float = 12.0  # horizontal spacing between Terran/Zerg/Protoss
	var row_spacing: float = 6.0   # vertical spacing between rows
	var race_labels: PackedStringArray = ["Terran", "Zerg", "Protoss"]

	_add_test_header("📐 Scale Comparison — Core Units & Buildings", Vector2(start_x, 2.0), Color(1.0, 0.9, 0.6))

	# Auto-enable calibration overlay in scale view
	_show_calibration = true
	if _calibration_overlay:
		_calibration_overlay.active = true

	for row_idx in range(_SCALE_ROWS.size()):
		var row_info: Dictionary = _SCALE_ROWS[row_idx]
		var row_label: String = row_info["label"]
		var row_units: Array = row_info["units"]
		var y: float = start_y + float(row_idx) * row_spacing

		# Row header
		_add_test_header(row_label, Vector2(start_x, y - 1.5), Color(0.8, 0.9, 1.0))

		for col_idx in range(row_units.size()):
			var unit_id: String = row_units[col_idx]
			var x: float = start_x + float(col_idx) * col_spacing
			var race_label: String = race_labels[col_idx] if col_idx < race_labels.size() else ""
			var entry: Dictionary = assets.get(unit_id, {})
			var race: String = _test_asset_race(unit_id, entry)

			if entry.is_empty():
				# Unit not found in assets — create a placeholder
				_test_ents.append(_make_placeholder_entity(unit_id, race_label, Vector2(x, y)))
			else:
				var kind: String = str(entry.get("kind", "unit"))
				var entity := _make_test_asset_entity(unit_id, entry, race, kind, Vector2(x, y), "")
				var rs := str(entry.get("render_scale", ""))
				var sr := str(entry.get("selection_radius", ""))
				var fp_dict = entry.get("footprint", {})
				var fp_str := ""
				if fp_dict is Dictionary and fp_dict.has("w"):
					fp_str = "%sx%s" % [str(fp_dict["w"]), str(fp_dict["h"])]
				elif fp_dict is Array and fp_dict.size() >= 2:
					fp_str = "%sx%s" % [str(fp_dict[0]), str(fp_dict[1])]
				var hbo = entry.get("health_bar_offset", [])
				var hbo_str := ""
				if hbo is Array and hbo.size() >= 2:
					hbo_str = "hbo:%s,%s" % [str(hbo[0]), str(hbo[1])]
				var parts: PackedStringArray = PackedStringArray()
				parts.append(unit_id)
				parts.append("rs=%s" % rs)
				if sr != "":
					parts.append("sr=%s" % sr)
				if fp_str != "":
					parts.append("fp=%s" % fp_str)
				if hbo_str != "":
					parts.append(hbo_str)
				entity["label"] = "\n".join(parts)
				_test_ents.append(entity)


func _make_placeholder_entity(unit_id: String, race_label: String, pos: Vector2) -> Dictionary:
	var owner := 0
	match race_label.to_lower():
		"terran":
			owner = 1
		"zerg":
			owner = 2
		"protoss":
			owner = 3
	return {
		"id": "test_unit_%s_idle" % unit_id,
		"owner": owner,
		"type": "unit",
		"entity_type": "unit",
		"unit_type": unit_id,
		"building_type": "",
		"resource_type": "",
		"generated_asset_id": unit_id,
		"preview_action": "",
		"label": "%s (missing)" % unit_id,
		"visual_class": "",
		"tech_tier": -1,
		"uses_sprite": false,
		"render_scale": 0.018,
		"neutral_team_tint": true,
		"px": pos.x,
		"py": pos.y,
		"health": 1,
		"max_health": 1,
		"is_idle": true,
		"carry_amount": 0,
		"carry_capacity": 0,
		"attack": 0,
		"attack_range": 0,
		"speed": 0,
		"resource_amount": 0,
		"attack_target_id": "",
		"target_x": 0,
		"target_y": 0,
		"energy": 0,
		"max_energy": 0,
	}


# ────────────────────────────────────────────────────────────
# Animation view — cycle idle/move/attack/death
# ────────────────────────────────────────────────────────────

func _create_view_animation() -> void:
	var assets: Dictionary = _sprite_loader.get_generated_assets() if _sprite_loader else {}
	var start_x: float = 5.0
	var start_y: float = 4.0
	var col_spacing: float = 4.0
	var row_spacing: float = 4.0

	_add_test_header("🎬 Animation View — Auto-cycling idle→move→attack→death", Vector2(start_x, 2.0), Color(0.6, 1.0, 0.8))

	# Show all units that have animation support, in compact layout
	var race_order: Array = ["terran", "zerg", "protoss"]
	var y: float = start_y

	for race in race_order:
		_add_test_header(_test_race_label(race), Vector2(start_x, y - 1.0), _test_race_color(race))
		y += 1.0
		var x: float = start_x
		var count: int = 0

		for asset_id in assets.keys():
			var entry: Dictionary = assets[asset_id]
			if str(entry.get("kind", "")) != "unit":
				continue
			if _test_asset_race(str(asset_id), entry) != race:
				continue
			# Show unit with current preview mode
			var action: String = ""
			match _test_preview_mode:
				"move":
					action = "moving"
				"attack":
					action = "attack"
				"death":
					action = "death"
				_:
					action = ""
			var entity := _make_test_asset_entity(str(asset_id), entry, race, "unit", Vector2(x, y), action)
			_test_ents.append(entity)
			x += col_spacing
			count += 1
			if count >= 10:
				count = 0
				x = start_x
				y += row_spacing
		y += row_spacing + 1.0

	# Add current phase label header
	_add_test_header("Current phase: %s" % _test_preview_mode.to_upper(), Vector2(start_x + 40.0, 2.0), Color(1.0, 1.0, 0.6))


# ────────────────────────────────────────────────────────────
# Combat view — fixed attacker→target pairs
# ────────────────────────────────────────────────────────────

func _create_view_combat() -> void:
	var assets: Dictionary = _sprite_loader.get_generated_assets() if _sprite_loader else {}
	var start_x: float = 5.0
	var start_y: float = 4.0
	var pair_spacing: float = 10.0
	var row_spacing: float = 6.0

	_add_test_header("⚔ Combat View — Auto-replay attack→hit→death cycles", Vector2(start_x, 2.0), Color(1.0, 0.6, 0.6))

	for pair_idx in range(_COMBAT_PAIRS.size()):
		var pair: Dictionary = _COMBAT_PAIRS[pair_idx]
		var attacker_id: String = pair["attacker"]
		var target_id: String = pair["target"]
		var y: float = start_y + float(pair_idx) * row_spacing
		var x: float = start_x

		# Pair label
		var profile_name: String = str(pair.get("profile", "none"))
		_add_test_header("[%s] %s → %s" % [profile_name, attacker_id, target_id], Vector2(x, y - 1.5), Color(0.9, 0.7, 0.6))

		# Attacker
		var attacker_entry: Dictionary = assets.get(attacker_id, {})
		var attacker_race: String = _test_asset_race(attacker_id, attacker_entry)
		if attacker_entry.is_empty():
			_test_ents.append(_make_placeholder_entity(attacker_id, "Attacker", Vector2(x, y)))
		else:
			var atk_entity := _make_test_asset_entity(attacker_id, attacker_entry, attacker_race, "unit", Vector2(x, y), "idle")
			atk_entity["label"] = attacker_id
			_test_ents.append(atk_entity)

		# Arrow / gap
		x += 5.0

		# Target
		var target_entry: Dictionary = assets.get(target_id, {})
		var target_race: String = _test_asset_race(target_id, target_entry)
		if target_entry.is_empty():
			_test_ents.append(_make_placeholder_entity(target_id, "Target", Vector2(x, y)))
		else:
			var tgt_entity := _make_test_asset_entity(target_id, target_entry, target_race, "unit", Vector2(x, y), "idle")
			tgt_entity["label"] = target_id
			_test_ents.append(tgt_entity)

		# Set initial combat state: attacker idle, target idle
		_combat_phase = 0
		_combat_timer = 0.0
		_combat_current_pair = 0

		# Store positions for this pair for later combat event emission
		_combat_pair_positions[pair_idx] = {
			"attacker_pos": Vector2(start_x, y),
			"target_pos": Vector2(start_x + 5.0, y),
		}


# ────────────────────────────────────────────────────────────
# Test entity helpers
# ────────────────────────────────────────────────────────────

func _add_test_header(text: String, pos: Vector2, color: Color) -> void:
	_test_section_headers.append({"text": text, "pos": pos, "color": color})


func _add_test_unit_pair(asset_id: String, entry: Dictionary, race: String, pos: Vector2) -> void:
	var move_entity := _make_test_asset_entity(asset_id, entry, race, "unit", pos, "moving")
	_test_ents.append(move_entity)

	var attack_pos := pos + Vector2(6.0, 0.0)
	var attack_entity := _make_test_asset_entity(asset_id, entry, race, "unit", attack_pos, "attack")
	var target_id := "%s_target" % str(attack_entity["id"])
	attack_entity["attack_target_id"] = target_id
	_test_ents.append(attack_entity)
	_test_ents.append({
		"id": target_id,
		"owner": attack_entity["owner"],
		"type": "marker",
		"entity_type": "marker",
		"unit_type": "",
		"building_type": "",
		"resource_type": "",
		"preview_hidden": true,
		"px": attack_pos.x + 2.0,
		"py": attack_pos.y,
		"health": 0,
		"max_health": 0,
		"is_idle": true,
		"carry_amount": 0,
		"carry_capacity": 0,
		"attack": 0,
		"attack_range": 0,
		"speed": 0,
		"resource_amount": 0,
		"attack_target_id": "",
		"target_x": 0,
		"target_y": 0,
		"energy": 0,
		"max_energy": 0,
	})


func _make_test_asset_entity(
	asset_id: String,
	entry: Dictionary,
	race: String,
	kind: String,
	pos: Vector2,
	action: String = ""
) -> Dictionary:
	var owner := _test_owner_for_race(race)
	var entity_type := "building" if kind == "building" else ("resource" if kind == "resource" else "unit")
	var visual_class = str(entry.get("visual_class", ""))
	var label := asset_id
	if kind == "unit":
		var action_tag = "atk" if action == "attack" else ("die" if action == "death" else "move")
		if action != "":
			if "air" in visual_class:
				label = "✈%s %s" % [asset_id, action_tag]
			else:
				label = "%s %s" % [asset_id, action_tag]
	# Look up catalog for vfx_profile and selection info
	var catalog_entry: Dictionary = _unit_type_catalog.get(asset_id, {})
	var vfx_profile: String = str(catalog_entry.get("vfx_profile", str(entry.get("vfx_profile", "none"))))
	var selection_radius: float = float(catalog_entry.get("selection_radius", 0.0))
	if selection_radius == 0.0:
		# Try manifest
		if _presentation_manifest.is_empty():
			_load_presentation_manifest()
		var section: String = "building_visuals" if kind == "building" else "unit_visuals"
		var manifest_entry: Dictionary = _presentation_manifest.get(section, {}).get(asset_id, {})
		selection_radius = float(manifest_entry.get("selection_radius", 1.5 if kind == "unit" else 3.0))

	var entity := {
		"id": "test_%s_%s_%s" % [kind, asset_id, action if action != "" else "idle"],
		"owner": owner,
		"type": entity_type,
		"entity_type": entity_type,
		"unit_type": asset_id if kind == "unit" else "",
		"building_type": asset_id if kind == "building" else "",
		"resource_type": asset_id if kind == "resource" else "",
		"generated_asset_id": asset_id,
		"preview_action": action,
		"label": label,
		"visual_class": visual_class,
		"tech_tier": int(entry.get("tech_tier", 1)) if kind == "building" else -1,
		"uses_sprite": kind == "resource",
		"render_scale": float(entry.get("render_scale", 0.018)),
		"selection_radius": selection_radius,
		"vfx_profile": vfx_profile,
		"neutral_team_tint": true,
		"px": pos.x,
		"py": pos.y,
		"health": 1000 if kind == "building" else 100,
		"max_health": 1000 if kind == "building" else 100,
		"is_idle": action == "",
		"carry_amount": 0,
		"carry_capacity": 0,
		"attack": 10 if kind == "unit" else 0,
		"attack_range": 5 if kind == "unit" else 0,
		"speed": 3 if kind == "unit" else 0,
		"resource_amount": 0,
		"attack_target_id": "",
		"target_x": pos.x + 2.0 if action == "moving" else 0,
		"target_y": pos.y if action == "moving" else 0,
		"energy": 0,
		"max_energy": 0,
	}
	return entity


func _test_asset_race(asset_id: String, entry: Dictionary) -> String:
	var race := str(entry.get("race", "")).to_lower()
	if race != "":
		return race
	match asset_id:
		"SCV", "Marine", "Firebat", "Ghost", "Medic", "Vulture", "Tank", "Goliath", "Wraith", "Valkyrie", "Battlecruiser", "Dropship", "CommandCenter", "Barracks", "Refinery", "SupplyDepot", "Academy", "Factory", "Starport", "EngineeringBay", "MissileTurret", "Bunker", "ComSatStation", "NuclearSilo", "MachineShop", "Armory", "ScienceFacility":
			return "terran"
		"Drone", "Zergling", "Hydralisk", "Overlord", "Mutalisk", "Scourge", "Queen", "Broodling", "Ultralisk", "Defiler", "InfestedTerran", "Hatchery", "SpawningPool", "Extractor", "CreepColony", "SporeColony", "SunkenColony", "HydraliskDen", "EvolutionChamber", "NydusCanal", "QueensNest", "Spire", "GreaterSpire", "UltraliskCavern", "DefilerMound":
			return "zerg"
		"Probe", "Zealot", "Dragoon", "HighTemplar", "Archon", "Reaver", "Shuttle", "Observer", "Corsair", "Scout", "Arbiter", "Carrier", "DarkTemplar", "Nexus", "Gateway", "Pylon", "Assimilator", "CyberneticsCore", "Forge", "PhotonCannon", "CitadelOfAdun", "RoboticsFacility", "Stargate", "TemplarArchives", "FleetBeacon", "RoboticsSupportBay", "Observatory", "ArbiterTribunal":
			return "protoss"
		_:
			return "neutral"


func _test_owner_for_race(race: String) -> int:
	match race:
		"terran":
			return 1
		"zerg":
			return 2
		"protoss":
			return 3
		_:
			return 0


func _test_race_label(race: String) -> String:
	match race:
		"terran":
			return "Terran"
		"zerg":
			return "Zerg"
		"protoss":
			return "Protoss"
		_:
			return "Neutral"


func _test_race_color(race: String) -> Color:
	match race:
		"terran":
			return Color(0.45, 0.65, 1.0)
		"zerg":
			return Color(1.0, 0.45, 0.35)
		"protoss":
			return Color(1.0, 0.85, 0.25)
		_:
			return Color(0.75, 0.75, 0.75)


# ────────────────────────────────────────────────────────────
# Combat diagnostics — Task 11 matchup presets
# ────────────────────────────────────────────────────────────

## Create the CombatDiagnosticsOverlay (unless one was injected via
## set_diagnostics_overlay) and parent it to the UI layer. It stays hidden until
## a preset is run and Test Mode is active.
func _create_diagnostics_overlay() -> void:
	if _diagnostics_overlay != null and is_instance_valid(_diagnostics_overlay):
		return
	if _ui_layer == null:
		return
	_diagnostics_overlay = CombatDiagnosticsOverlay.new()
	_diagnostics_overlay.test_mode_active = _active
	_ui_layer.add_child(_diagnostics_overlay)

## Show the 10 matchup preset buttons only inside Test Mode + combat gallery.
func _update_combat_preset_visibility() -> void:
	var show_btns: bool = _active and _gallery_mode == "combat"
	for idx in _combat_preset_buttons:
		var btn: Button = _combat_preset_buttons[idx]
		if btn:
			btn.visible = show_btns

func _create_combat_preset_buttons() -> void:
	if _combat_presets.is_empty():
		_combat_presets = _build_combat_presets()
	var x: float = 140.0
	var y: float = 8.0
	for i in range(_combat_presets.size()):
		var preset: Dictionary = _combat_presets[i]
		var btn := Button.new()
		btn.text = str(preset.get("label", "Preset %d" % (i + 1)))
		btn.tooltip_text = "Run %s and show combat diagnostics" % str(preset.get("label", ""))
		btn.position = Vector2(x, y)
		btn.size = Vector2(150, 22)
		btn.modulate = Color(0.85, 0.7, 0.7)
		btn.visible = false  # only visible in Test Mode + combat mode
		btn.pressed.connect(_run_combat_preset.bind(i))
		if _ui_layer:
			_ui_layer.add_child(btn)
		_combat_preset_buttons[i] = btn
		y += 24.0

## Build the attacker + target gallery entities for a preset and emit them so
## GameView can render the matchup, then show the diagnostics overlay with the
## resolved combat events.
func _run_combat_preset(idx: int) -> void:
	if idx < 0 or idx >= _combat_presets.size():
		return
	var preset: Dictionary = _combat_presets[idx]
	var label: String = str(preset.get("label", ""))
	var events: Array = preset.get("events", [])

	# Rebuild gallery entities for this matchup.
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()
	_add_test_header("⚔ %s" % label, Vector2(5.0, 2.0), Color(1.0, 0.6, 0.6))
	for e in _make_matchup_entities(preset):
		_test_ents.append(e)
	entities_rebuilt.emit(_test_ents)

	# Route the preset's authoritative combat events through the
	# CombatVisualController (event-driven VFX pipeline) instead of emitting a
	# synthetic preview signal. Clearing seen events first lets the user re-run
	# the same preset and still see the VFX.
	if _combat_controller != null and is_instance_valid(_combat_controller):
		_combat_controller.clear_seen_events()
		_combat_controller.process_combat_events(events)

	# Show the diagnostics overlay (gated by Test Mode internally).
	if _diagnostics_overlay:
		_diagnostics_overlay.test_mode_active = _active
		_diagnostics_overlay.display_events(events, label)
	print("[TEST MODE] Combat preset run: %s (%d event(s))" % [label, events.size()])

## Build attacker + target entities for a preset using the sprite catalog, with
## placeholders for any unit that has no generated asset yet.
func _make_matchup_entities(preset: Dictionary) -> Array:
	var assets: Dictionary = _sprite_loader.get_generated_assets() if _sprite_loader else {}
	var ents: Array = []
	var attacker_id: String = str(preset.get("attacker", ""))
	var targets: Array = preset.get("targets", [])
	var ax: float = 5.0
	var ay: float = 4.0

	# Attacker
	var atk_entry: Dictionary = assets.get(attacker_id, {})
	var atk_race: String = _test_asset_race(attacker_id, atk_entry)
	if atk_entry.is_empty():
		ents.append(_make_placeholder_entity(attacker_id, _test_race_label(atk_race), Vector2(ax, ay)))
	else:
		var atk := _make_test_asset_entity(attacker_id, atk_entry, atk_race, "unit", Vector2(ax, ay), "attack")
		atk["label"] = attacker_id
		ents.append(atk)

	# Targets (stacked vertically to the right)
	var tx: float = 10.0
	for i in range(targets.size()):
		var tid: String = str(targets[i])
		var tgt_entry: Dictionary = assets.get(tid, {})
		var tgt_race: String = _test_asset_race(tid, tgt_entry)
		var ty: float = ay + float(i) * 3.0
		if tgt_entry.is_empty():
			ents.append(_make_placeholder_entity(tid, _test_race_label(tgt_race), Vector2(tx, ty)))
		else:
			var tgt := _make_test_asset_entity(tid, tgt_entry, tgt_race, "unit", Vector2(tx, ty), "idle")
			tgt["label"] = tid
			ents.append(tgt)
	return ents

## Load the SC1 combat presets from the JSON fixture produced by the headless
## SimCore resolver. Each preset carries full combat_events, initial_entities,
## final_entities, commands, and ticks — the gallery only needs label/attacker/
## targets/events for rendering, so the rest is passed through verbatim.
const COMBAT_PRESETS_PATH := "res://resources/test/sc1_combat_presets.json"

func _build_combat_presets() -> Array:
	if not FileAccess.file_exists(COMBAT_PRESETS_PATH):
		push_warning("[TestModeGallery] Combat presets fixture not found: %s" % COMBAT_PRESETS_PATH)
		return []
	var raw_text: String = FileAccess.get_file_as_string(COMBAT_PRESETS_PATH)
	var parsed = JSON.parse_string(raw_text)
	if not parsed is Dictionary or not parsed.has("presets"):
		push_warning("[TestModeGallery] Invalid combat presets fixture (expected {\"presets\": [...]})")
		return []
	var raw_presets: Array = parsed.get("presets", [])
	var presets: Array = []
	for i in range(raw_presets.size()):
		var p: Dictionary = raw_presets[i]
		if not p is Dictionary:
			continue
		var preset_id: String = str(p.get("id", "preset_%d" % (i + 1)))
		var label: String = "%d. %s" % [i + 1, preset_id.replace("_", " ").capitalize()]
		presets.append({
			"label": label,
			"id": preset_id,
			"attacker": str(p.get("attacker", "")),
			"targets": p.get("targets", []),
			"events": p.get("combat_events", []),
			"initial_entities": p.get("initial_entities", []),
			"final_entities": p.get("final_entities", {}),
			"commands": p.get("commands", []),
			"ticks": int(p.get("ticks", 0)),
		})
	return presets
