extends Node2D

## RTS Game View — Full interactive RTS prototype.
## Sprint 4: Integrates CameraController, HUD, RallyPointIndicator,
## enhanced SelectionManager (caps, double-click, formation),
## enhanced FogRenderer (gradient edges), enhanced Minimap (fog, attack indicators).
##
## Controls:
##   WASD / Arrow keys     Move camera
##   Mouse edge scroll     Move camera
##   Scroll wheel          Zoom (0.5x - 2.0x)
##   Middle-click drag     Pan camera
##   F key                 Camera follow selected group
##   Left click / drag     Select units
##   Shift+click           Add to selection
##   Ctrl+click / Double-click  Select all same-type on screen
##   1-9                   Recall control group
##   Ctrl+1-9              Create control group
##   Shift+1-9             Add to control group
##   Double-tap 1-9        Jump camera to group
##   Right click           Context action (move / attack / gather / build / rally)
##   M / S / A / P / H     Ability hotkeys (move/stop/attack/patrol/hold)
##   G + click             Gather (workers)
##   B                     Toggle build menu (with worker selected)
##   T                     Train worker/soldier (with building selected)
##   Esc                   Deselect all

const GrpcBridgeScript := preload("res://scripts/grpc_bridge.gd")
const CallableStateMachine = preload("res://scripts/callable_state_machine.gd")
const CameraControllerScript = preload("res://scripts/camera_controller.gd")
const HUDScene := preload("res://scenes/hud.tscn")
const RallyPointIndicatorScript = preload("res://scripts/rally_point_indicator.gd")

# ─── Config ────────────────────────────────────────────────
@onready var _camera: Camera2D = $Camera2D
var _cell: float = 1.0
var _map_w: float = 64.0
var _map_h: float = 64.0

# ─── State ─────────────────────────────────────────────────
var _bridge
var _frame: int = 0
var _default_font: Font
var _analysis_written := false

# Entity cache
var _ents: Array = []
var _prev_hp: Dictionary = {}
var _dmg_floats: Array = []

# ─── Drag-select ───────────────────────────────────────────
var _dragging := false
var _drag_start := Vector2.ZERO
var _drag_end := Vector2.ZERO
const SELECT_RADIUS := 1.5

# Debug click marker
var _debug_click_pos: Vector2 = Vector2.ZERO
var _debug_click_ttl: int = 0
var _test_mode: bool = false
var _test_ents: Array = []
var _test_btn: Button = null
var _zoom_in_btn: Button = null
var _zoom_out_btn: Button = null
var _saved_ents: Array = []
var _saved_fog_tiles: PackedInt32Array = []
var _saved_fog_w: int = 0
var _saved_fog_h: int = 0
# Animation state
var _anim_frame: int = 0
var _anim_tick: float = 0.0
const ANIM_FPS := 8.0  # frames per second for walk cycle
# Unit animation layout: row, cols, frame_width, frame_height per unit per owner
var _unit_anim_info: Dictionary = {}

# ─── Build mode ────────────────────────────────────────────
var _build_mode := false

# ─── Game state ────────────────────────────────────────────
var _game_active := false
var _game_over_shown := false
var _replay_mode := false
var _replay_player: ReplayPlayer
var _replay_overlay: Control

# ─── Fog of war ────────────────────────────────────────────
var _fog_tiles: PackedInt32Array = []
var _fog_w: int = 0
var _fog_h: int = 0

# ─── Jitter monitor ────────────────────────────────────────
var _jitter_count: int = 0
var _total_jitter_px: float = 0.0

# ─── Minimap ───────────────────────────────────────────────
var _mm_size := Vector2(152, 136)  # minimap inner drawing area
var _mm_margin := Vector2(12, 28)  # bottom-right float: x=8+4, y=8+20
var _mm_rect_node: Control = null  # ref to MinimapRect node

# ─── Integrated Pattern References ─────────────────────────
var _selection: Node  # SelectionManager autoload
var _event_bus: Node  # EventBus autoload
var _ability_mgr: Node  # AbilityManager autoload

	# ─── Sprite textures ───────────────────────────────────────
var _unit_textures: Dictionary = {}
var _building_textures: Dictionary = {}
var _sprite_pool: Dictionary = {}  # entity_id -> Sprite2D
var _sprite_container: Node2D = null  # parent for all entity sprites
var _map_texture: Texture2D = null

# ─── Sprint 4 Components ──────────────────────────────────
var _cam_ctrl: Node = null  # CameraController
var _hud: Control = null    # HUD
var _ui_layer: CanvasLayer = null  # UI layer for HUD, minimap, replay overlay
var _rally_indicators: Dictionary = {}  # {building_id: RallyPointIndicator}

# ─── Entity Data Provider ──────────────────────────────────
var _entity_cache_by_id: Dictionary = {}

# ─── Resources state ──────────────────────────────────────
var _p1_minerals: int = 0
var _p1_gas: int = 0
var _p1_supply_used: int = 0
var _p1_supply_cap: int = 0

func _get_entity_data(entity_id: String) -> Dictionary:
	return _entity_cache_by_id.get(entity_id, {})

func _get_entity_type(entity_id: String) -> String:
	var data := _get_entity_data(entity_id)
	if data.is_empty():
		return ""
	return str(data.get("entity_type", data.get("type", "")))

# ───────────────────────────────────────────────────────────
func _ready() -> void:
	_default_font = ThemeDB.fallback_font

	# Check if entering in replay mode (set by main_menu)
	var _replay_match_id: String = ""
	if Engine.has_meta("replay_match_id"):
		_replay_match_id = Engine.get_meta("replay_match_id")
		Engine.remove_meta("replay_match_id")

	# ─── CanvasLayer for ALL UI (must be created before any Control children) ───
	_ui_layer = CanvasLayer.new()
	_ui_layer.layer = 10
	add_child(_ui_layer)

	_bridge = GrpcBridgeScript.new()
	_bridge.ai_player = 2
	add_child(_bridge)
	_bridge.game_started.connect(_on_start)
	_bridge.state_updated.connect(_on_state)
	_bridge.game_over.connect(_on_game_over)
	_bridge.replay_loaded.connect(_on_replay_loaded)

	# Replay system — ReplayPlayer as child of game_view (Node), overlay in CanvasLayer
	_replay_player = ReplayPlayer.new()
	add_child(_replay_player)
	_replay_player.replay_tick.connect(_on_state)
	_replay_player.replay_finished.connect(_on_replay_finished)

	var _replay_overlay_scene := preload("res://scenes/replay_overlay.tscn")
	_replay_overlay = _replay_overlay_scene.instantiate()
	_replay_overlay.set_player(_replay_player)
	_ui_layer.add_child(_replay_overlay)

	if _replay_match_id != "":
		# Replay mode: don't start a new game, fetch replay instead
		_replay_mode = true
		_game_active = false
		_replay_overlay.visible = true
		_bridge.fetch_replay(_replay_match_id)
		print("[GameView] Replay mode: fetching %s" % _replay_match_id)
	else:
		# Normal game mode
		_bridge.start_game(42)
		_game_active = true
		_replay_overlay.visible = false

	# Connect to autoloads
	_event_bus = get_node_or_null("/root/EventBus")
	_selection = get_node_or_null("/root/SelectionManager")
	_ability_mgr = get_node_or_null("/root/AbilityManager")

	# Wire up SelectionManager data providers
	if _selection:
		_selection.entity_data_provider = _get_entity_data
		_selection.entity_type_provider = _get_entity_type
		_selection.selection_changed.connect(_on_selection_changed)
		_selection.camera_focus_requested.connect(_on_camera_focus_requested)

	# Wire up AbilityManager
	if _ability_mgr:
		_ability_mgr.set_entity_data_provider(_get_entity_data)

	# ─── Sprint 4: Create CameraController ───
	_cam_ctrl = CameraControllerScript.new()
	add_child(_cam_ctrl)
	_cam_ctrl.setup(_camera)
	_cam_ctrl.set_entity_data_provider(_get_entity_data)
	_cam_ctrl.set_map_size(_map_w, _map_h)
	# Set initial camera position to map center immediately
	_camera.position = Vector2(_map_w / 2.0, _map_h / 2.0)

	# ─── Container for entity Sprite2D nodes ───
	_sprite_container = Node2D.new()
	_sprite_container.name = "EntitySprites"
	_sprite_container.z_index = 1  # Above map bg (z=-100)
	z_index = 5  # game_view _draw() renders above entity sprites
	add_child(_sprite_container)

	# ─── Preload sprite textures ───
	# Terran units
	_unit_textures["worker_1"] = load("res://assets/units/SCV.png")
	_unit_textures["soldier_1"] = load("res://assets/units/Marine.png")
	_unit_textures["scout_1"] = load("res://assets/units/Ghost.png")
	# Terran units (P2)
	_unit_textures["worker_2"] = load("res://assets/units/SCV.png")
	_unit_textures["soldier_2"] = load("res://assets/units/Marine.png")
	_unit_textures["scout_2"] = load("res://assets/units/Ghost.png")
	# Protoss units
	_unit_textures["worker_3"] = load("res://assets/units/Probe.png")
	_unit_textures["soldier_3"] = load("res://assets/units/Zealot.png")
	_unit_textures["scout_3"] = load("res://assets/units/Dragoon.png")
	_building_textures[1] = load("res://assets/buildings/TerranBuilding.png")
	_building_textures[2] = load("res://assets/buildings/ZergBuilding.png")
	# ─── Unit animation metadata (row, total_cols, frame_w, frame_h, south_col) ───
	# SCV: 8-dir, row0 walk, row1 carry, row2 attack, row3 gather
	_unit_anim_info["worker_1"] = {"rows": 4, "cols": [8,8,8,4], "fw": [33,41,42,46], "fh": [41,40,40,48], "south": [4,4,4,2]}
	# SCV (P2): same as worker_1
	_unit_anim_info["worker_2"] = _unit_anim_info.get("worker_1", {})
	# Probe: single strip
	_unit_anim_info["worker_3"] = {"rows": 1, "cols": [1], "fw": [286], "fh": [62], "south": [0]}
	# Marine: 17-dir, many rows
	_unit_anim_info["soldier_1"] = {"rows": 14, "cols": [18,18,18,18,18,18,18,18,18,18,18,18,18,7], "fw": [20,18,16,16,21,22,22,23,23,24,23,23,23,41], "fh": [28,28,28,34,28,27,29,27,28,29,31,30,29,37], "south": [9,9,9,9,9,9,9,9,9,9,9,9,9,3]}
	# Marine (P2): same as soldier_1
	_unit_anim_info["soldier_2"] = _unit_anim_info.get("soldier_1", {})
	# Zealot: 17-dir
	_unit_anim_info["soldier_3"] = {"rows": 14, "cols": [18,18,18,18,18,18,18,18,18,18,16,18,14,6], "fw": [19,21,26,21,19,21,26,22,22,19,18,23,27,33], "fh": [33,33,32,33,36,35,35,34,34,37,39,38,40,36], "south": [9,9,9,9,9,9,9,9,9,9,8,9,7,3]}
	# Ghost: 17-dir
	_unit_anim_info["scout_1"] = {"rows": 13, "cols": [18,18,18,18,18,18,18,18,18,18,18,16,3], "fw": [22,21,20,21,23,23,24,24,24,14,11,17,107], "fh": [28,29,29,28,28,28,29,29,27,28,28,109,101], "south": [9,9,9,9,9,9,9,9,9,9,9,8,1]}
	# Ghost (P2): same as scout_1
	_unit_anim_info["scout_2"] = _unit_anim_info.get("scout_1", {})
	# Dragoon (reuse Zealot info for now — will need its own sprite)
	_unit_anim_info["scout_3"] = _unit_anim_info.get("soldier_3", {})
	_map_texture = load("res://assets/maps/(2)Switchback.jpg")

	# ─── CanvasLayer for floating UI (above fullscreen game map) ───
	_ui_layer.layer = 10

	var vp_size := get_viewport().get_visible_rect().size

	# ─── Minimap: floating panel at bottom-right ───
	var mm_size := Vector2(160, 160)
	var mm_margin := 8
	var _mm_panel := Panel.new()
	_mm_panel.anchor_left = 1.0
	_mm_panel.anchor_top = 1.0
	_mm_panel.anchor_right = 1.0
	_mm_panel.anchor_bottom = 1.0
	_mm_panel.offset_left = -mm_size.x - mm_margin
	_mm_panel.offset_top = -mm_size.y - mm_margin
	_mm_panel.offset_right = -mm_margin
	_mm_panel.offset_bottom = -mm_margin
	_ui_layer.add_child(_mm_panel)

	# MinimapRect: actual drawing area — CHILD of panel, not sibling
	var mm_rect := ColorRect.new()
	mm_rect.name = "MinimapRect"
	mm_rect.color = Color.BLACK
	mm_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	mm_rect.offset_left = 4
	mm_rect.offset_top = 20
	mm_rect.offset_right = -4
	mm_rect.offset_bottom = -4
	var mm_script := load("res://scripts/minimap_rect.gd")
	if mm_script:
		mm_rect.set_script(mm_script)
	_mm_panel.add_child(mm_rect)  # child of panel, not ui_layer!
	_mm_rect_node = mm_rect  # store reference

	# ─── HUD: top-right horizontal info bar ───
	_hud = HUDScene.instantiate()
	_ui_layer.add_child(_hud)
	_hud.set_entity_data_provider(_get_entity_data)
	_hud.anchor_left = 1.0
	_hud.anchor_right = 1.0
	_hud.anchor_top = 0.0
	_hud.anchor_bottom = 0.0
	_hud.offset_left = -420
	_hud.offset_right = 0
	_hud.offset_top = 0
	_hud.offset_bottom = 36

	# ─── Test Mode Button (bottom-left corner) ───
	_test_btn = Button.new()
	_test_btn.text = "🧪 Test Mode"
	_test_btn.tooltip_text = "Click to preview all sprites on map"
	_test_btn.position = Vector2(8, 8)
	_test_btn.size = Vector2(120, 32)
	_test_btn.modulate = Color(0.8, 1.0, 0.8)
	_ui_layer.add_child(_test_btn)
	_test_btn.pressed.connect(_toggle_test_mode)
	# Zoom buttons
	_zoom_in_btn = Button.new()
	_zoom_in_btn.text = "🔍+"
	_zoom_in_btn.position = Vector2(4, 30)
	_zoom_in_btn.size = Vector2(40, 24)
	_zoom_in_btn.modulate = Color(0.9, 0.95, 1.0)
	_ui_layer.add_child(_zoom_in_btn)
	_zoom_in_btn.pressed.connect(func(): _cam_ctrl._zoom_in() if _cam_ctrl else null)
	_zoom_out_btn = Button.new()
	_zoom_out_btn.text = "🔍-"
	_zoom_out_btn.position = Vector2(46, 30)
	_zoom_out_btn.size = Vector2(40, 24)
	_zoom_out_btn.modulate = Color(0.9, 0.95, 1.0)
	_ui_layer.add_child(_zoom_out_btn)
	_zoom_out_btn.pressed.connect(func(): _cam_ctrl._zoom_out() if _cam_ctrl else null)

	print("===== GameView ready (Human P1 vs AI P2) Sprint 4 path=", get_path())

# ─── Bridge between old _selected and new SelectionManager ──
var _selected: Dictionary = {}

func _sync_selected_from_manager() -> void:
	if _selection:
		_selected = _selection.selection.duplicate()

func _on_selection_changed(selection: Dictionary) -> void:
	_sync_selected_from_manager()
	if _ability_mgr:
		_ability_mgr.on_selection_changed(selection)
	# Update camera follow entities
	if _cam_ctrl:
		_cam_ctrl.set_follow_entities(_selection.get_selected_ids() if _selection else [])
	# Update rally point indicators visibility
	_update_rally_indicator_visibility()

func _on_camera_focus_requested(center: Vector2) -> void:
	if _cam_ctrl:
		_cam_ctrl.move_to_world_position(center)

# ─── Sprint 4: HUD Signal Handlers ──────────────────────────
func _on_hud_ability_clicked(ability_id: StringName) -> void:
	if _ability_mgr:
		var sel := _selected.duplicate()
		var mpos := _screen_to_world(get_viewport().get_mouse_position())
		_ability_mgr.process_ability_input(
			InputEventKey.new(), sel, mpos
		)

func _on_hud_build_clicked(building_type: String) -> void:
	_build_mode = true
	# Will be used when right-click places building

func _on_hud_train_clicked(unit_type: String) -> void:
	_handle_train()

# ───────────────────────────────────────────────────────────
func _process(_delta: float) -> void:
	_frame += 1
	# Advance animation frame for test mode
	if _test_mode:
		_anim_tick += _delta
		if _anim_tick >= 1.0 / ANIM_FPS:
			_anim_tick -= 1.0 / ANIM_FPS
			_anim_frame = (_anim_frame + 1) % 17
			_update_entity_sprites()
	# CameraController handles all camera movement now
	_build_mode = Input.is_key_pressed(KEY_B) or (_hud and _hud.is_build_panel_visible())

	# Decay damage floaters
	for f in _dmg_floats:
		f.ttl -= 1
		f.y -= 0.5
	_dmg_floats = _dmg_floats.filter(func(f): return f.ttl > 0)

	# Tick minimap attack indicators and redraw minimap
	if _mm_rect_node and _mm_rect_node.has_method("tick_attack_indicators"):
		_mm_rect_node.tick_attack_indicators()
		_mm_rect_node.queue_redraw()

	queue_redraw()

# ─── Camera helpers (delegated to CameraController) ────────
func _screen_to_world(sp: Vector2) -> Vector2:
	# Convert screen position to world (local) position.
	# get_canvas_transform() maps local coords → viewport coords.
	# Its inverse maps viewport → local (= world with TILE_SIZE=1).
	# Use affine_inverse for numerical stability.
	return get_canvas_transform().affine_inverse() * sp

func _world_to_screen(wp: Vector2) -> Vector2:
	return get_canvas_transform() * wp

# ─── Entity helpers ────────────────────────────────────────
func _ent_at_world_pos(wp: Vector2, radius: float = SELECT_RADIUS) -> Dictionary:
	for e in _ents:
		if wp.distance_to(Vector2(e.px, e.py)) < radius:
			return e
	return {}

func _ents_in_world_rect(rect: Rect2) -> Array:
	var result: Array = []
	for e in _ents:
		if rect.has_point(Vector2(e.px, e.py)):
			result.append(e)
	return result

func _is_own_combat(e: Dictionary) -> bool:
	return e.owner == 1 and e.type in ["worker", "soldier", "scout"]

func _is_own_building(e: Dictionary) -> bool:
	return e.owner == 1 and e.type == "building"

func _find_nearest_enemy(from_px: float, from_py: float) -> Dictionary:
	var best: Dictionary = {}
	var best_dist: float = 999999.0
	for e in _ents:
		if e.owner == 2 and e.type != "resource":
			var d: float = Vector2(from_px, from_py).distance_to(Vector2(e.px, e.py))
			if d < best_dist:
				best_dist = d
				best = e
	return best

# ─── Input ─────────────────────────────────────────────────
func _input(event: InputEvent) -> void:
	if _replay_mode or _game_over_shown:
		return

	# Right-click: context action
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		_handle_right_click()
		return

	# Left-click: check minimap first, then selection
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var mpos := get_viewport().get_mouse_position()
		# Don't handle if clicking on HUD
		if _hud and _hud.get_global_rect().has_point(mpos):
			return
		if _is_minimap_click(mpos):
			_handle_minimap_click(mpos)
			return
		_dragging = true
		_drag_start = mpos
		_drag_end = mpos
		# Debug: show world click position
		_debug_click_pos = _screen_to_world(mpos)
		_debug_click_ttl = 30  # frames
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and not event.pressed:
		if _dragging:
			_dragging = false
			if _drag_start.distance_to(_drag_end) < 5.0:
				_handle_single_click()
			else:
				_handle_drag_select()
		return

	if event is InputEventMouseMotion and _dragging:
		_drag_end = get_viewport().get_mouse_position()

	# Control group hotkeys (1-9)
	if event is InputEventKey and event.pressed:
		var key: int = event.keycode
		if key >= KEY_1 and key <= KEY_9:
			var group_idx: int = key - KEY_1 + 1
			if _selection:
				if event.ctrl_pressed:
					_selection.create_hotkey_group(group_idx)
				elif event.shift_pressed:
					_selection.add_to_hotkey_group(group_idx)
				else:
					_selection.select_hotkey_group(group_idx)
			return

	# Ability hotkeys (if AbilityManager is loaded)
	if event is InputEventKey and event.pressed:
		if _ability_mgr:
			var consumed: bool = _ability_mgr.process_ability_input(event, _selected, _screen_to_world(get_viewport().get_mouse_position()))
			if consumed:
				return

	# Legacy keyboard shortcuts
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_T:
			_handle_train()
		elif event.keycode == KEY_ESCAPE:
			if _selection:
				_selection.remove_all_selection()
			else:
				_selected.clear()
			# Also hide build panel
			if _hud:
				_hud.hide_build_panel()

func _handle_right_click() -> void:
	var selected_ids: Array = []
	if _selection:
		selected_ids = _selection.get_selected_ids()
	else:
		selected_ids = _selected.keys()

	if selected_ids.is_empty():
		return

	var screen_pos := get_viewport().get_mouse_position()
	var world_pos := _screen_to_world(screen_pos)
	# Diagnostic: compare manual calc vs transform
	var vp_half := get_viewport().get_visible_rect().size / 2.0
	var manual := (screen_pos - vp_half) / _camera.zoom + _camera.position
	var xform := get_canvas_transform().affine_inverse() * screen_pos
	print("[RIGHT-CLICK] screen=(%d,%d) manual=(%.2f,%.2f) xform=(%.2f,%.2f) cam=(%.2f,%.2f) zoom=%.1f" % [
		int(screen_pos.x), int(screen_pos.y),
		manual.x, manual.y, xform.x, xform.y,
		_camera.position.x, _camera.position.y, _camera.zoom.x])
	var tgt_world := world_pos  # TILE_SIZE=1, world coords ARE tile coords
	var clicked_ent := _ent_at_world_pos(world_pos, SELECT_RADIUS * 3.0)
	var cmds: Array = []

	# Determine action type
	var action := "move"
	var workers_selected := false
	var buildings_selected := false
	var combat_selected := false

	for uid in selected_ids:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue
		if e.type == "worker":
			workers_selected = true
			combat_selected = true
		elif e.type in ["soldier", "scout"]:
			combat_selected = true
		elif e.type == "building":
			buildings_selected = true

	# ─── Sprint 4: Rally point for buildings ───
	if buildings_selected and not workers_selected and not combat_selected:
		for uid in selected_ids:
			var e = _get_ent_by_id(uid)
			if e.is_empty():
				continue
			if e.type == "building" and e.owner == 1:
				_set_rally_point(uid, world_pos)
				return

	# Smart context
	if not clicked_ent.is_empty():
		if clicked_ent.owner != 1 and clicked_ent.owner != 0 and clicked_ent.type != "resource":
			action = "attack"
		elif clicked_ent.type == "resource" and workers_selected:
			action = "gather"
		elif clicked_ent.type == "building" and clicked_ent.owner == 1 and workers_selected:
			action = "move"
	elif combat_selected and not workers_selected:
		action = "attack_nearest"

	if _build_mode and workers_selected:
		action = "build"

	# Generate commands per selected unit (with formation for moves)
	var moving_ids: Array = []
	for uid in selected_ids:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue

		match action:
			"attack":
				if _is_own_combat(e):
					cmds.append({
						"action": "attack",
						"attacker_id": uid,
						"target_id": clicked_ent.id,
						"issuer": 1,
					})
					_emit_attack_indicator(Vector2(e.px, e.py))
			"attack_nearest":
				if _is_own_combat(e):
					var nearest_enemy = _find_nearest_enemy(e.px, e.py)
					if not nearest_enemy.is_empty():
						cmds.append({
							"action": "attack",
							"attacker_id": uid,
							"target_id": nearest_enemy.id,
							"issuer": 1,
						})
						_emit_attack_indicator(Vector2(e.px, e.py))
					else:
						moving_ids.append(uid)
			"gather":
				if e.type == "worker":
					cmds.append({
						"action": "gather",
						"worker_id": uid,
						"resource_id": clicked_ent.id,
						"issuer": 1,
					})
			"build":
				if e.type == "worker":
					cmds.append({
						"action": "build",
						"builder_id": uid,
						"building_type": "barracks",
						"pos_x": tgt_world.x,
						"pos_y": tgt_world.y,
						"issuer": 1,
					})
			"move":
				if e.type in ["worker", "soldier", "scout"]:
					moving_ids.append(uid)

	# Formation-based move commands
	if not moving_ids.is_empty():
		var formation: Array = _selection.calculate_formation_positions(world_pos, moving_ids.size()) if _selection \
			else _calc_formation_fallback(world_pos, moving_ids.size())
		for i in range(moving_ids.size()):
			var fpos: Vector2 = formation[i] if i < formation.size() else world_pos
			var ftgt := fpos  # TILE_SIZE=1, world coords ARE tile coords
			cmds.append({
				"action": "move",
				"unit_id": moving_ids[i],
				"target_x": ftgt.x,
				"target_y": ftgt.y,
				"issuer": 1,
			})

	if cmds.size() > 0:
		_bridge.submit_commands(cmds)

	# Also emit via EventBus
	if _event_bus and cmds.size() > 0:
		for cmd in cmds:
			_event_bus.emit_command_issued(cmd)

	# Hide build panel after placing
	if _build_mode and _hud:
		_hud.hide_build_panel()

func _handle_single_click() -> void:
	var wp := _screen_to_world(_drag_start)
	var clicked_ent := _ent_at_world_pos(wp)

	if _selection:
		if clicked_ent.is_empty():
			if not Input.is_key_pressed(KEY_SHIFT):
				_selection.remove_all_selection()
			return
		if not Input.is_key_pressed(KEY_SHIFT):
			_selection.remove_all_selection()
		# Sprint 4: Double-click detection
		var was_double: bool = _selection.handle_click_with_double_select(clicked_ent.id)
		if not was_double:
			# Ctrl+click = select all same type on screen
			if Input.is_key_pressed(KEY_CTRL):
				_selection.select_all_similar_on_screen(clicked_ent.id)
			else:
				_selection.add_to_selection_bulk([clicked_ent.id])
	else:
		# Fallback without SelectionManager
		if clicked_ent.is_empty():
			if not Input.is_key_pressed(KEY_SHIFT):
				_selected.clear()
			return
		if not Input.is_key_pressed(KEY_SHIFT):
			_selected.clear()
		_selected[clicked_ent.id] = true

func _handle_drag_select() -> void:
	var tl := _screen_to_world(Vector2(minf(_drag_start.x, _drag_end.x), minf(_drag_start.y, _drag_end.y)))
	var br := _screen_to_world(Vector2(maxf(_drag_start.x, _drag_end.x), maxf(_drag_start.y, _drag_end.y)))
	var rect := Rect2(tl, br - tl)

	var selected_ents := _ents_in_world_rect(rect)
	var own_ids: Array = []
	for e in selected_ents:
		if e.owner == 1:
			own_ids.append(e.id)

	if _selection:
		if not Input.is_key_pressed(KEY_SHIFT):
			_selection.remove_all_selection()
		_selection.add_to_selection_bulk(own_ids)
	else:
		if not Input.is_key_pressed(KEY_SHIFT):
			_selected.clear()
		for e in selected_ents:
			if e.owner == 1:
				_selected[e.id] = true

	# Update selectables_on_screen for SelectionManager
	if _selection:
		var screen_ids: Dictionary = {}
		for e in _ents:
			screen_ids[e.id] = true
		_selection.selectables_on_screen = screen_ids

func _handle_train() -> void:
	var cmds: Array = []
	var selected_ids: Array = []
	if _selection:
		selected_ids = _selection.get_selected_ids()
	else:
		selected_ids = _selected.keys()

	for uid in selected_ids:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue
		if e.type == "building" and e.owner == 1:
			var utype := "worker" if e.building_type == "base" else "soldier"
			cmds.append({
				"action": "train",
				"building_id": uid,
				"unit_type": utype,
				"issuer": 1,
			})
	if cmds.size() > 0:
		_bridge.submit_commands(cmds)

func _get_ent_by_id(eid: String) -> Dictionary:
	for e in _ents:
		if e.id == eid:
			return e
	return {}

# ─── Sprint 4: Rally Point System ──────────────────────────
func _set_rally_point(building_id: String, world_pos: Vector2) -> void:
	if not _rally_indicators.has(building_id):
		var indicator = RallyPointIndicatorScript.new()
		add_child(indicator)
		_rally_indicators[building_id] = indicator
		var e = _get_ent_by_id(building_id)
		if not e.is_empty():
			indicator.set_building_position(Vector2(e.px, e.py))
	var indicator = _rally_indicators[building_id]
	indicator.set_rally_point(world_pos)
	indicator.show_indicator()

	# Submit rally point command to SimCore
	var tgt_world := world_pos  # TILE_SIZE=1, world coords ARE tile coords
	var cmds: Array = [{
		"action": "set_rally",
		"building_id": building_id,
		"target_x": tgt_world.x,
		"target_y": tgt_world.y,
		"issuer": 1,
	}]
	_bridge.submit_commands(cmds)
	if _event_bus:
		_event_bus.emit_rally_point_set(building_id, world_pos)

func _clear_rally_point(building_id: String) -> void:
	if _rally_indicators.has(building_id):
		var indicator = _rally_indicators[building_id]
		indicator.clear_rally_point()
		indicator.hide_indicator()
	if _event_bus:
		_event_bus.emit_rally_point_cleared(building_id)

func _update_rally_indicator_visibility() -> void:
	# Show rally indicators only for selected buildings
	for bid in _rally_indicators:
		var indicator = _rally_indicators[bid]
		if _selection and _selection.is_selected(bid):
			indicator.show_indicator()
		else:
			indicator.hide_indicator()
		# Update building position from current entity data
		var e = _get_ent_by_id(bid)
		if not e.is_empty():
			indicator.set_building_position(Vector2(e.px, e.py))

# ─── Sprint 4: Attack Indicators on Minimap ─────────────────
func _emit_attack_indicator(world_pos: Vector2) -> void:
	if _mm_rect_node and _mm_rect_node.has_method("add_attack_indicator"):
		_mm_rect_node.add_attack_indicator(world_pos)
	if _event_bus:
		_event_bus.emit_attack_occurred(world_pos, 1)

# ─── Formation Fallback ────────────────────────────────────
static func _calc_formation_fallback(center: Vector2, count: int, spacing: float = 0.8) -> Array:
	var positions: Array = []
	if count == 0:
		return positions
	var cols: int = int(ceilf(sqrt(float(count))))
	for i in range(count):
		var row: int = i / cols
		var col: int = i % cols
		var offset := Vector2(
			(float(col) - float(cols - 1) * 0.5) * spacing,
			(float(row) - float(count / cols - 1) * 0.5) * spacing
		)
		positions.append(center + offset)
	return positions

# ─── Bridge callbacks ──────────────────────────────────────
func _on_start(state: Dictionary) -> void:
	_map_w = _to_f(state.get("map_width"), 64.0)
	_map_h = _to_f(state.get("map_height"), 64.0)
	if _cam_ctrl:
		_cam_ctrl.set_map_size(_map_w, _map_h)
	_parse(state)
	_camera.position = Vector2(_map_w / 2.0, _map_h / 2.0)  # Center on map

func _on_state(state: Dictionary) -> void:
	if _test_mode:
		return
	_parse(state)

func _on_game_over(winner: int, tick: int) -> void:
	_game_active = false
	_game_over_shown = true
	print("===== GAME OVER: P%d wins at tick %d" % [winner, tick])

func _restart_game() -> void:
	_game_over_shown = false
	_game_active = true
	if _selection:
		_selection.remove_all_selection()
	else:
		_selected.clear()
	_bridge._pending_commands.clear()
	_ents.clear()
	_entity_cache_by_id.clear()
	# Clear rally indicators
	for bid in _rally_indicators:
		_rally_indicators[bid].queue_free()
	_rally_indicators.clear()
	var new_seed := randi() % 100000
	_bridge.start_game(new_seed)

func _to_f(value, fallback: float = 0.0) -> float:
	if value == null:
		return fallback
	return value + 0.0

func _parse(state: Dictionary) -> void:
	_ents.clear()
	_entity_cache_by_id.clear()
	var entities: Dictionary = state.get("entities", {})
	for eid in entities:
		var e: Dictionary = entities[eid]
		var etype: String = str(e.get("entity_type", ""))
		var btype: String = str(e.get("building_type", ""))
		var rtype: String = str(e.get("resource_type", ""))
		var ent_dict := {
			"id": str(eid),
			"owner": int(e.get("owner") if e.get("owner") != null else 0),
			"type": etype,
			"entity_type": etype,
			"building_type": btype,
			"resource_type": rtype,
			"resource_amount": _to_f(e.get("resource_amount"), 0.0),
			"px": _to_f(e.get("pos_x"), 0.0),  # TILE_SIZE=1, world=tile
			"py": _to_f(e.get("pos_y"), 0.0),
			"pos_x": _to_f(e.get("pos_x"), 0.0),
			"pos_y": _to_f(e.get("pos_y"), 0.0),
			"health": _to_f(e.get("health"), 0.0),
			"max_health": _to_f(e.get("max_health"), 0.0),
			"is_idle": bool(e.get("is_idle", true) if e.get("is_idle") != null else true),
			"carry_amount": _to_f(e.get("carry_amount"), 0.0),
			"carry_cap": _to_f(e.get("carry_capacity"), 0.0),
			"attack": _to_f(e.get("attack"), 0.0),
			"attack_range": _to_f(e.get("attack_range"), 16.0),
			"attack_target_id": str(e.get("attack_target_id", "")),
			"target_x": _to_f(e.get("target_x"), 0.0),
			"target_y": _to_f(e.get("target_y"), 0.0),
			"speed": _to_f(e.get("speed"), 0.0),
			"energy": _to_f(e.get("energy"), 0.0),
			"max_energy": _to_f(e.get("max_energy"), 0.0),
		}
		_ents.append(ent_dict)
		_entity_cache_by_id[str(eid)] = ent_dict

	# Parse fog-of-war for P1
	var fog: Dictionary = state.get("fog_of_war", {})
	var p1_fog: Dictionary = fog.get("1", fog)
	_fog_w = int(p1_fog.get("width", 0))
	_fog_h = int(p1_fog.get("height", 0))
	var raw_tiles: Array = p1_fog.get("tiles", [])
	_fog_tiles.clear()
	for t in raw_tiles:
		_fog_tiles.append(int(t))

	# Parse resources for P1
	var resources: Dictionary = state.get("resources", {})
	var p1_res: Dictionary = resources.get("1", resources)
	_p1_minerals = int(p1_res.get("minerals", _p1_minerals))
	_p1_gas = int(p1_res.get("gas", _p1_gas))
	_p1_supply_used = int(p1_res.get("supply_used", _p1_supply_used))
	_p1_supply_cap = int(p1_res.get("supply_cap", _p1_supply_cap))

	# Update HUD resources
	if _hud:
		_hud.update_resources(_p1_minerals, _p1_gas, _p1_supply_used, _p1_supply_cap)

	# Update entity Sprite2D nodes
	_update_entity_sprites()
	if _frame == 60:
		print("[DEBUG] Entity sprites: %d active, %d in pool" % [_sprite_pool.size(), _sprite_pool.size()])
		for eid in _sprite_pool:
			var s = _sprite_pool[eid]
			if s.visible:
				print("[DEBUG] Visible sprite: id=%s pos=(%.1f,%.1f) tex=%s scale=%s" % [eid, s.position.x, s.position.y, str(s.texture).get_file() if s.texture else "null", str(s.scale)])
			break

	# Detect damage and attack events
	for e in _ents:
		var eid_str: String = e.id
		var hp: float = e.health
		if _prev_hp.has(eid_str):
			var prev: float = _prev_hp[eid_str]
			if hp < prev and prev > 0:
				var dmg: float = prev - hp
				_dmg_floats.append({
					"id": eid_str,
					"x": e.px,
					"y": e.py - 1.2,
					"amount": dmg,
					"ttl": 30,
				})
				# Attack indicator on minimap
				_emit_attack_indicator(Vector2(e.px, e.py))
	_prev_hp.clear()
	for e in _ents:
		_prev_hp[e.id] = e.health

	# Purge dead entities from selection
	var valid_ids: Array = []
	for e in _ents:
		valid_ids.append(e.id)
	if _selection:
		_selection.purge_invalid_ids(valid_ids)

	# Update selectables_on_screen
	if _selection:
		_selection.selectables_on_screen = _entity_cache_by_id.duplicate()

	# Update rally indicator building positions
	for bid in _rally_indicators:
		var indicator = _rally_indicators[bid]
		var e = _get_ent_by_id(bid)
		if not e.is_empty():
			indicator.set_building_position(Vector2(e.px, e.py))

# ───────────────────────────────────────────────────────────
# ─── DRAWING ───────────────────────────────────────────────
# ───────────────────────────────────────────────────────────
func _draw() -> void:
	# NO camera offset needed — Camera2D handles canvas transform automatically.
	# _draw() local coordinates ARE world coordinates.
	var co := Vector2.ZERO
	_draw_map_background(co)
	_draw_grid(co)
	_draw_fog_of_war(co)
	_draw_entities(co)
	_draw_combat_effects(co)
	_draw_health_bars(co)
	_draw_selection_rings(co)
	_draw_rally_lines(co)
	_draw_drag_box()
	_draw_damage_floats(co)
	_draw_game_over_overlay()
	_draw_debug_click()
	if _test_mode:
		_draw_test_labels()

func _draw_map_background(_co: Vector2) -> void:
	# Map fills from world origin (0,0) to (_map_w, _map_h)
	var map_rect := Rect2(Vector2.ZERO, Vector2(_map_w, _map_h))
	if _map_texture:
		draw_texture_rect(_map_texture, map_rect, false)
	else:
		draw_rect(map_rect, Color(0.15, 0.18, 0.12, 1.0))

func _draw_grid(co: Vector2) -> void:
	var grid_color := Color(0.25, 0.28, 0.22, 0.3)
	var step := 8.0  # TILE_SIZE=1, grid every 8 tiles
	var map_px := _map_w
	var map_py := _map_h
	var x := step
	while x < map_px:
		draw_line(Vector2(x, 0), Vector2(x, map_py), grid_color, 0.06)
		x += step
	var y := step
	while y < map_py:
		draw_line(Vector2(0, y), Vector2(map_px, y), grid_color, 0.06)
		y += step

func _draw_fog_of_war(co: Vector2) -> void:
	# Sprint 4: Uses FogRenderer's gradient approach directly inline for performance.
	# The separate FogRenderer node is also updated.
	if _fog_w <= 0 or _fog_h <= 0 or _fog_tiles.is_empty():
		return
	var map_px := _map_w  # TILE_SIZE=1
	var map_py := _map_h
	var tile_w := map_px / float(_fog_w)
	var tile_h := map_py / float(_fog_h)

	# Pre-build grid for neighbor lookup
	var fog_grid: Array = []
	fog_grid.resize(_fog_h)
	for gy in range(_fog_h):
		fog_grid[gy] = []
		fog_grid[gy].resize(_fog_w)
		for gx in range(_fog_w):
			var idx := gy * _fog_w + gx
			if idx < _fog_tiles.size():
				fog_grid[gy][gx] = _fog_tiles[idx]
			else:
				fog_grid[gy][gx] = 0

	for gy in range(_fog_h):
		for gx in range(_fog_w):
			var state_val: int = fog_grid[gy][gx]
			var base_alpha: float
			match state_val:
				0: base_alpha = 0.88
				1: base_alpha = 0.50
				2: base_alpha = 0.0
				_: base_alpha = 0.88

			if base_alpha < 0.01:
				continue

			# Gradient smoothing at boundaries
			var is_boundary := false
			var neighbor_sum: float = 0.0
			var neighbor_count: int = 0
			for dy in range(-1, 2):
				for dx in range(-1, 2):
					if dx == 0 and dy == 0:
						continue
					var nx: int = gx + dx
					var ny: int = gy + dy
					if nx < 0 or nx >= _fog_w or ny < 0 or ny >= _fog_h:
						neighbor_sum += 0.88
						neighbor_count += 1
						if state_val != 0:
							is_boundary = true
						continue
					var n_val: int = fog_grid[ny][nx]
					var n_alpha: float
					match n_val:
						0: n_alpha = 0.88
						1: n_alpha = 0.50
						2: n_alpha = 0.0
						_: n_alpha = 0.88
					neighbor_sum += n_alpha
					neighbor_count += 1
					if n_val != state_val:
						is_boundary = true

			var alpha: float
			if is_boundary:
				var neighbor_avg := neighbor_sum / float(neighbor_count) if neighbor_count > 0 else base_alpha
				alpha = lerpf(base_alpha, neighbor_avg, 0.35)
			else:
				alpha = base_alpha

			alpha = clampf(alpha, 0.0, 1.0)
			if alpha < 0.01:
				continue

			var px: float = gx * tile_w
			var py: float = gy * tile_h

			var color: Color
			match state_val:
				0: color = Color(0.02, 0.02, 0.05, alpha)
				1: color = Color(0.02, 0.02, 0.05, alpha * 0.55)
				2: color = Color(0.02, 0.02, 0.05, alpha * 0.15)
				_: color = Color(0.02, 0.02, 0.05, alpha)

			draw_rect(Rect2(px, py, tile_w + 1.0, tile_h + 1.0), color, true)

## Calculate unit sprite region from animation metadata.
func _calc_unit_region(utype: String, owner: int, row: int, frame: int) -> Rect2:
	var key := "%s_%d" % [utype, owner]
	var info: Dictionary = _unit_anim_info.get(key, {})
	if info.is_empty():
		return Rect2(0, 0, 96, 96)
	
	var cols_arr: Array = info.get("cols", [17])
	var fw_arr: Array = info.get("fw", [38])
	var fh_arr: Array = info.get("fh", [40])
	
	row = mini(row, cols_arr.size() - 1)
	var n_cols: int = cols_arr[row]
	var fh: int = fh_arr[row]
	
	# Cycle frame within available directions
	frame = frame % n_cols
	
	# Get texture to calculate column width
	var tex: Texture2D = _unit_textures.get(key, null)
	if not tex:
		return Rect2(0, 0, fw_arr[row], fh)
	
	# Approximate uniform spacing based on sheet width and column count
	var sheet_w: int = tex.get_width()
	var col_w: float = float(sheet_w) / float(maxi(n_cols, 1))
	var px: int = int(float(frame) * col_w)
	
	# Calculate y offset by accumulating row heights
	var py: int = 0
	for r in range(row):
		if r < fh_arr.size():
			py += fh_arr[r] + 10  # ~10px gap between rows
		else:
			py += fh_arr[-1] + 10
	
	return Rect2(px, py, int(col_w), fh)

## Get the correct sprite region and scale for a building type.
## Use only the COMPLETE (fully built) form — single building, no tiling.
func _get_building_region(btype: String, owner: int) -> Dictionary:
	var region := Rect2(1, 1, 128, 109)
	var scale_sz := Vector2(0.015, 0.015)

	if owner == 1:  # Terran
		match btype:
			"base":
				# Command Center COMPLETE form (2nd of 3): x=191-379
				region = Rect2(191, 108, 189, 188)
				scale_sz = Vector2(0.022, 0.022)  # 189*0.022≈4.2 world units
			"barracks":
				region = Rect2(120, 1, 145, 114)
				scale_sz = Vector2(0.017, 0.017)
			"factory":
				# Factory is 3rd section in Row1: x=381-574
				region = Rect2(381, 108, 193, 188)
				scale_sz = Vector2(0.021, 0.021)
			"refinery":
				region = Rect2(941, 1, 186, 109)
				scale_sz = Vector2(0.014, 0.014)
			"starport":
				region = Rect2(577, 108, 363, 184)
				scale_sz = Vector2(0.012, 0.012)
			_:
				region = Rect2(1, 1, 128, 109)
				scale_sz = Vector2(0.015, 0.015)
	elif owner == 2:  # Zerg
		match btype:
			"base":
				# Hatchery: Row0 frame0, COMPLETE form (bottom section only)
				region = Rect2(30, 301, 121, 128)
				scale_sz = Vector2(0.033, 0.033)  # ~4 world units
			"barracks":
				# Spawning Pool: Row1 small frames, complete form only
				# Tight crop below the gap: (1478, 688, 83, 85)
				region = Rect2(1478, 688, 83, 85)
				scale_sz = Vector2(0.048, 0.048)  # ~4 world units
			"lair":
				region = Rect2(10, 627, 210, 132)
				scale_sz = Vector2(0.019, 0.019)
			"hive":
				region = Rect2(11, 1184, 141, 124)
				scale_sz = Vector2(0.028, 0.028)
			_:
				# Generic fallback: small Spawning Pool form
				region = Rect2(1475, 670, 89, 100)
				scale_sz = Vector2(0.045, 0.045)

	return {"region": region, "scale": scale_sz}

## Sync Sprite2D nodes with entity data each tick.
func _update_entity_sprites() -> void:
	if not _sprite_container:
		return
	var active_ids: Dictionary = {}

	for e in _ents:
		var eid: String = str(e.id)
		active_ids[eid] = true

		# Skip entities in fog (non-own)
		if e.owner != 1 and _is_in_fog(e):
			if _sprite_pool.has(eid):
				_sprite_pool[eid].visible = false
			continue

		var sprite: Sprite2D = _sprite_pool.get(eid, null)
		if not sprite:
			sprite = Sprite2D.new()
			sprite.name = "Ent_" + eid
			sprite.z_index = 1
			sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_DISABLED
			_sprite_container.add_child(sprite)
			_sprite_pool[eid] = sprite

		# Determine texture and region based on entity type
		var tex: Texture2D = null
		var region: Rect2 = Rect2()
		var scale_sz := Vector2.ONE

		match e.type:
			"worker":
				tex = _unit_textures.get("worker_%d" % e.owner, null)
				if tex:
					region = _calc_unit_region("worker", e.owner, 0, _anim_frame)
					scale_sz = Vector2(0.02, 0.02)  # ~0.7 world units
			"soldier":
				tex = _unit_textures.get("soldier_%d" % e.owner, null)
				if tex:
					region = _calc_unit_region("soldier", e.owner, 0, _anim_frame)
					scale_sz = Vector2(0.03, 0.03)  # ~0.7 world units
			"scout":
				tex = _unit_textures.get("scout_%d" % e.owner, null)
				if tex:
					region = _calc_unit_region("scout", e.owner, 0, _anim_frame)
					scale_sz = Vector2(0.03, 0.03)  # ~0.7 world units
			"building":
				tex = _building_textures.get(e.owner, null)
				if tex:
					var btype: String = e.get("building_type", "")
					var binfo: Dictionary = _get_building_region(btype, e.owner)
					region = binfo["region"]
					scale_sz = binfo["scale"]
			_:
				pass

		if tex:
			sprite.texture = tex
			sprite.region_enabled = true
			sprite.region_rect = region
			sprite.scale = scale_sz
			sprite.visible = true
			sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_DISABLED
			sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			# Color by owner
			if e.owner == 2:
				sprite.modulate = Color(1.0, 0.4, 0.4)
			elif e.owner == 1:
				sprite.modulate = Color.CYAN
			else:
				sprite.modulate = Color.WHITE
		else:
			sprite.texture = null
			sprite.visible = false

		sprite.position = Vector2(e.px, e.py)

	# Hide sprites for entities that no longer exist
	for eid in _sprite_pool:
		if not active_ids.has(eid):
			_sprite_pool[eid].visible = false

func _draw_entities(co: Vector2) -> void:
	# Sprint 4: Entities in unexplored (state 0) or explored (state 1) fog are hidden
	# (explored shows terrain but not units from other players).
	for e in _ents:
		# Fog visibility check: hide non-own entities in non-visible fog
		if e.owner != 1 and _is_in_fog(e):
			continue

		var pos := Vector2(e.px, e.py) 

		# ─── Only draw circles for resources (no sprite) ───
		# Workers, soldiers, scouts, buildings use Sprite2D nodes instead
		if e.type == "resource":
			var radius := 0.4
			if e.resource_type == "mineral":
				draw_rect(Rect2(pos - Vector2(radius, radius), Vector2(radius * 2, radius * 2)), Color(1.0, 0.85, 0.0, 1.0), true)
			elif e.resource_type == "gas":
				draw_circle(pos, radius, Color(0.0, 0.8, 0.0, 1.0))
			else:
				draw_circle(pos, radius, Color.GRAY)

	# Attack / move target lines
	for e in _ents:
		if e.owner != 1:
			continue
		if e.attack_target_id != "" or not e.is_idle:
			var lpos := Vector2(e.px, e.py) 
			if e.attack_target_id != "":
				var tgt = _get_ent_by_id(e.attack_target_id)
				if not tgt.is_empty():
					var tpos := Vector2(tgt.px, tgt.py) 
					draw_line(lpos, tpos, Color(1.0, 0.3, 0.3, 0.5), 0.06, true)
			elif e.target_x != 0 or e.target_y != 0:
				var tpos := Vector2(e.target_x, e.target_y)   # TILE_SIZE=1, no _cell multiplier
				draw_line(lpos, tpos, Color(0.3, 1.0, 0.3, 0.3), 0.06, true)

func _is_in_fog(e: Dictionary) -> bool:
	"""Check if an entity is in non-visible fog (unexplored or explored but not currently visible)."""
	if _fog_w <= 0 or _fog_h <= 0 or _fog_tiles.is_empty():
		return false
	var fog_x := int(e.px * float(_fog_w) / _map_w)
	var fog_y := int(e.py * float(_fog_h) / _map_h)
	fog_x = clampi(fog_x, 0, _fog_w - 1)
	fog_y = clampi(fog_y, 0, _fog_h - 1)
	var idx := fog_y * _fog_w + fog_x
	if idx < _fog_tiles.size():
		return _fog_tiles[idx] < 2
	return true

func _draw_combat_effects(co: Vector2) -> void:
	for e in _ents:
		if e.owner != 1:
			continue
		if e.attack_target_id != "":
			var pos := Vector2(e.px, e.py) 
			var pulse: float = 0.4 + 0.6 * abs(sin(_frame * 0.15))
			draw_arc(pos, 0.7, 0, TAU, 16, Color(1.0, 0.15, 0.15, pulse), 0.15, true)
	for f in _dmg_floats:
		if f.ttl > 25:
			var tgt = _get_ent_by_id(f.id)
			if not tgt.is_empty():
				var pos := Vector2(tgt.px, tgt.py) 
				draw_circle(pos, 0.8, Color(1.0, 0.2, 0.2, 0.35))

func _draw_damage_floats(co: Vector2) -> void:
	for f in _dmg_floats:
		var alpha: float = clampf(f.ttl / 30.0, 0.0, 1.0)
		var pos := Vector2(f.x, f.y) 
		var txt := "-%d" % int(f.amount)
		draw_string(_default_font, pos, txt, HORIZONTAL_ALIGNMENT_CENTER, -1, 8, Color(1.0, 0.2, 0.2, alpha))

func _draw_health_bars(co: Vector2) -> void:
	for e in _ents:
		if e.max_health <= 0 or e.type == "resource":
			continue
		if e.owner != 1 and _is_in_fog(e):
			continue
		var pos := Vector2(e.px, e.py) 
		var bar_w := 1.2
		var bar_h := 0.15
		var bar_y := pos.y - 1.0
		var frac: float = e.health / e.max_health
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.3, 0.3, 0.3, 0.8), true)
		var hp_color := Color.GREEN if frac > 0.6 else Color.YELLOW if frac > 0.3 else Color.RED
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * frac, bar_h), hp_color, true)

func _draw_selection_rings(co: Vector2) -> void:
	for uid in _selected:
		var e := _get_ent_by_id(uid)
		if e.is_empty():
			continue
		var pos := Vector2(e.px, e.py) 
		draw_arc(pos, 0.8, 0.0, TAU, 16, Color(0.2, 1.0, 0.2, 0.9), 0.12, true)

# ─── Sprint 4: Draw Rally Point Lines ──────────────────────
func _draw_rally_lines(co: Vector2) -> void:
	for bid in _rally_indicators:
		var indicator = _rally_indicators[bid]
		if not indicator.has_rally():
			continue
		# Only draw if building is selected
		if _selection and not _selection.is_selected(bid):
			continue
		var bpos: Vector2 = indicator._building_pos 
		var rpos: Vector2 = indicator._rally_pos 

		# Dashed line
		var direction: Vector2 = rpos - bpos
		var length: float = direction.length()
		if length < 1.0:
			continue
		var dir_norm: Vector2 = direction / length
		var drawn: float = 0.0
		var is_dash: bool = true
		const DASH_LEN := 0.5
		const GAP_LEN := 0.4

		while drawn < length:
			var seg_len: float = DASH_LEN if is_dash else GAP_LEN
			var remaining: float = length - drawn
			seg_len = minf(seg_len, remaining)
			if is_dash:
				var start: Vector2 = bpos + dir_norm * drawn
				var end: Vector2 = bpos + dir_norm * (drawn + seg_len)
				draw_line(start, end, Color(0.2, 1.0, 0.2, 0.7), 0.06, true)
			drawn += seg_len
			is_dash = not is_dash

		# Flag at rally point — compact tile-space flag
		var pole_top: Vector2 = rpos - Vector2(0, 0.4)
		draw_line(rpos, pole_top, Color(1.0, 0.9, 0.2, 0.8), 0.04, true)
		var flag_pts := PackedVector2Array([
			pole_top,
			pole_top + Vector2(0.2, 0.07),
			pole_top + Vector2(0, 0.14)
		])
		draw_colored_polygon(flag_pts, Color(1.0, 0.9, 0.2, 0.7))

func _draw_drag_box() -> void:
	if not _dragging:
		return
	if _drag_start.distance_to(_drag_end) < 5.0:
		return
	# Convert screen-space drag coords to world space for drawing
	var ws := _screen_to_world(_drag_start)
	var we := _screen_to_world(_drag_end)
	var rect := Rect2(ws, we - ws).abs()
	draw_rect(rect, Color(0.3, 1.0, 0.3, 0.15), true)
	draw_rect(rect, Color(0.3, 1.0, 0.3, 0.7), false, 0.06)

func _draw_game_over_overlay() -> void:
	if not _game_over_shown:
		return
	# Draw overlay in world space covering the visible area
	var vp := get_viewport().get_visible_rect().size / _camera.zoom
	var cam := _camera.position
	draw_rect(Rect2(cam - vp / 2.0, vp), Color(0, 0, 0, 0.6), true)
	var center := cam
	var winner_text := "YOU WIN!" if _bridge._winner == 1 else "YOU LOSE!"
	var win_color := Color.GREEN if _bridge._winner == 1 else Color.RED
	draw_string(_default_font, center + Vector2(-4, -2), winner_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 6, win_color)
	draw_string(_default_font, center + Vector2(-5, 0.8), "Press R to restart", HORIZONTAL_ALIGNMENT_LEFT, -1, 3, Color.WHITE)
	draw_string(_default_font, center + Vector2(-5, 2.2), "Press Q to quit", HORIZONTAL_ALIGNMENT_LEFT, -1, 3, Color.GRAY)

# ─── Minimap ──────────────────────────────────────────────
# Minimap is now drawn by the MinimapRect child node.
func _minimap_rect() -> Rect2:
	if _mm_rect_node and _mm_rect_node is Control:
		return _mm_rect_node.get_global_rect()
	# Fallback: bottom-right floating position
	var vp := get_viewport().get_visible_rect().size
	var mm_pos := Vector2(vp.x - _mm_size.x - _mm_margin.x, vp.y - _mm_size.y - _mm_margin.y)
	return Rect2(mm_pos, _mm_size)

func _is_minimap_click(screen_pos: Vector2) -> bool:
	return _minimap_rect().has_point(screen_pos)

func _handle_minimap_click(screen_pos: Vector2) -> void:
	var mm := _minimap_rect()
	var local := screen_pos - mm.position
	var frac_x: float = local.x / mm.size.x
	var frac_y: float = local.y / mm.size.y
	var target_pos := Vector2(frac_x * _map_w, frac_y * _map_h)
	if _cam_ctrl:
		_cam_ctrl.move_to_world_position(target_pos)
	else:
		_camera.position = target_pos

func _draw_debug_click() -> void:
	if _debug_click_ttl <= 0:
		return
	_debug_click_ttl -= 1
	var alpha: float = clampf(float(_debug_click_ttl) / 30.0, 0.0, 1.0)
	# Draw a bright green cross at the resolved world position
	draw_line(_debug_click_pos - Vector2(0.5, 0), _debug_click_pos + Vector2(0.5, 0), Color(0, 1, 0, alpha), 0.08, true)
	draw_line(_debug_click_pos - Vector2(0, 0.5), _debug_click_pos + Vector2(0, 0.5), Color(0, 1, 0, alpha), 0.08, true)
	draw_circle(_debug_click_pos, 0.3, Color(0, 1, 0, alpha * 0.3))

## Provides state data to the minimap_rect child node.
func _get_state_for_minimap() -> Dictionary:
	var entities_dict: Dictionary = {}
	for e in _ents:
		entities_dict[e.id] = {
			"owner": e.owner,
			"type": e.type,
				"px": e.px,
			"py": e.py,
			"resource_type": e.resource_type,
		}
	return {
		"entities": entities_dict,
		"map_width": _map_w,
		"map_height": _map_h,
		"cam_center": _camera.position,  # CENTER anchor: position IS center
		"vp_size": get_viewport().get_visible_rect().size / _camera.zoom,
		"cell_size": int(_cell),
		"fog_tiles": _fog_tiles,
		"fog_width": _fog_w,
		"fog_height": _fog_h,
	}

func _monitor_canvas_transform() -> void:
	var ct := get_viewport().get_canvas_transform()
	var origin_x: float = ct.get_origin().x
	if absf(origin_x) > 2.0:
		_jitter_count += 1
		_total_jitter_px += absf(origin_x)
		if _frame % 60 == 0 or _jitter_count <= 5:
			print("[Frame %d] ⚠️ CANVAS JITTER: origin_x=%.1f (count=%d)" % [_frame, origin_x, _jitter_count])

func _write_analysis() -> void:
	var positions: Array = []
	for e in _ents:
		positions.append("(%.1f, %.1f)" % [e.px, e.py])
	var pos_count: Dictionary = {}
	for p in positions:
		pos_count[p] = pos_count.get(p, 0) + 1
	var dupes: Array = []
	for p in pos_count:
		if pos_count[p] > 1:
			dupes.append(p)
	var verdict := {
		"pass": dupes.is_empty() and positions.size() == _ents.size(),
		"ents_parsed": _ents.size(),
		"unique_positions": pos_count.size(),
		"duplicates": dupes.size(),
		"tree_children": get_tree().root.get_child_count(),
		"jitter_frames": _jitter_count,
		"jitter_total_px": _total_jitter_px,
		"jitter_free": _jitter_count == 0,
		"camera_anchor": "DRAG_CENTER",
		"stretch_mode": "canvas_items",
	}
	var vf := FileAccess.open("user://render_verdict.json", FileAccess.WRITE)
	if vf:
		vf.store_string(JSON.stringify(verdict, "\t"))
		vf.close()
		print("[Verdict] ", "PASS" if verdict["pass"] else "FAIL",
				" jitter=", "NONE" if verdict["jitter_free"] else str(_jitter_count))

## ─── TEST MODE: Draw labels for test entities ───
func _draw_test_labels() -> void:
	var font: Font = _default_font
	if not font:
		return
	# Font sizes in world units — small enough to read when zoomed in
	var title_size := 1.2
	var label_size := 0.8
	const BX := 4.0
	const UX := 40.0
	# Building section headers
	var y := 2.5
	draw_string(font, Vector2(BX, y), "TERRAN BUILDINGS", HORIZONTAL_ALIGNMENT_LEFT, -1, title_size, Color(0.4, 0.6, 1.0))
	y += 4.0 * 5 + 1.0
	draw_string(font, Vector2(BX, y), "ZERG BUILDINGS", HORIZONTAL_ALIGNMENT_LEFT, -1, title_size, Color(1.0, 0.5, 0.3))
	y += 4.0 * 5 + 1.0
	draw_string(font, Vector2(BX, y), "PROTOSS BUILDINGS", HORIZONTAL_ALIGNMENT_LEFT, -1, title_size, Color(1.0, 0.9, 0.3))
	# Unit section headers
	var uy := 2.5
	draw_string(font, Vector2(UX, uy), "TERRAN UNITS", HORIZONTAL_ALIGNMENT_LEFT, -1, title_size, Color(0.4, 0.6, 1.0))
	uy += 2.5 * 3 + 1.0
	draw_string(font, Vector2(UX, uy), "ZERG UNITS", HORIZONTAL_ALIGNMENT_LEFT, -1, title_size, Color(1.0, 0.5, 0.3))
	uy += 2.5 * 3 + 1.0
	draw_string(font, Vector2(UX, uy), "PROTOSS UNITS", HORIZONTAL_ALIGNMENT_LEFT, -1, title_size, Color(1.0, 0.9, 0.3))
	# Individual entity labels
	for e in _ents:
		if not str(e.id).begins_with("test_"):
			continue
		var label: String = ""
		if e.type == "building":
			label = e.building_type
		else:
			label = e.type
		var owner_tag := "T" if e.owner == 1 else ("Z" if e.owner == 2 else "P")
		var full_label := "%s/%s" % [owner_tag, label]
		draw_string(font, Vector2(e.px + 1.5, e.py - 0.3), full_label, HORIZONTAL_ALIGNMENT_LEFT, -1, label_size, Color(1,1,1,0.9))


func _toggle_test_mode() -> void:
	_test_mode = not _test_mode
	if _test_mode:
		_build_test_entities()
		if _test_btn:
			_test_btn.text = "🔙 Back"
			_test_btn.modulate = Color(1.0, 0.8, 0.8)
		print("[TEST MODE] ON — showing all sprites on map")
	else:
		_clear_test_entities()
		if _test_btn:
			_test_btn.text = "🧪 Test Mode"
			_test_btn.modulate = Color(0.8, 1.0, 0.8)
		print("[TEST MODE] OFF — back to normal game")
	queue_redraw()

func _build_test_entities() -> void:
	_clear_test_entities()
	# Save fog state and disable it
	_saved_fog_tiles = _fog_tiles
	_saved_fog_w = _fog_w
	_saved_fog_h = _fog_h
	_fog_tiles = PackedInt32Array()
	_fog_w = 0
	_fog_h = 0
	
	const BX := 4.0      # building section X start
	const UX := 40.0     # unit section X start
	const SPACING := 4.0
	var y := 4.0
	
	# ════════════ BUILDINGS (left side) ════════════
	# Terran buildings
	for bt in ["base", "barracks", "factory", "refinery", "starport"]:
		_test_ents.append({
			"id": "test_t_%s" % bt, "owner": 1, "type": "building",
			"entity_type": "building", "building_type": bt,
			"px": BX, "py": y, "health": 1000, "max_health": 1000,
			"is_idle": true, "carry_amount": 0, "carry_capacity": 0,
			"attack": 0, "attack_range": 0, "speed": 0,
			"resource_amount": 0, "resource_type": "",
			"attack_target_id": "", "target_x": 0, "target_y": 0,
			"energy": 0, "max_energy": 0,
		})
		y += SPACING
	
	# Zerg buildings
	y += 1.0
	for bt in ["base", "barracks", "lair", "hive", "spire"]:
		_test_ents.append({
			"id": "test_z_%s" % bt, "owner": 2, "type": "building",
			"entity_type": "building", "building_type": bt,
			"px": BX, "py": y, "health": 1000, "max_health": 1000,
			"is_idle": true, "carry_amount": 0, "carry_capacity": 0,
			"attack": 0, "attack_range": 0, "speed": 0,
			"resource_amount": 0, "resource_type": "",
			"attack_target_id": "", "target_x": 0, "target_y": 0,
			"energy": 0, "max_energy": 0,
		})
		y += SPACING
	
	# Protoss buildings
	y += 1.0
	for bt in ["base", "barracks", "spire"]:
		_test_ents.append({
			"id": "test_p_%s" % bt, "owner": 3, "type": "building",
			"entity_type": "building", "building_type": bt,
			"px": BX, "py": y, "health": 1000, "max_health": 1000,
			"is_idle": true, "carry_amount": 0, "carry_capacity": 0,
			"attack": 0, "attack_range": 0, "speed": 0,
			"resource_amount": 0, "resource_type": "",
			"attack_target_id": "", "target_x": 0, "target_y": 0,
			"energy": 0, "max_energy": 0,
		})
		y += SPACING
	
	# ════════════ UNITS (right side) ════════════
	var uy := 4.0
	# Terran units
	for utype in ["worker", "soldier", "scout"]:
		_test_ents.append({
			"id": "test_u1_%s" % utype, "owner": 1, "type": utype,
			"entity_type": utype, "building_type": "",
			"px": UX, "py": uy, "health": 100, "max_health": 100,
			"is_idle": true, "carry_amount": 0, "carry_capacity": 0,
			"attack": 10, "attack_range": 5, "speed": 3,
			"resource_amount": 0, "resource_type": "",
			"attack_target_id": "", "target_x": 0, "target_y": 0,
			"energy": 0, "max_energy": 0,
		})
		uy += 2.5
	
	uy += 1.0
	# Zerg units
	for utype in ["worker", "soldier", "scout"]:
		_test_ents.append({
			"id": "test_u2_%s" % utype, "owner": 2, "type": utype,
			"entity_type": utype, "building_type": "",
			"px": UX, "py": uy, "health": 100, "max_health": 100,
			"is_idle": true, "carry_amount": 0, "carry_capacity": 0,
			"attack": 10, "attack_range": 5, "speed": 3,
			"resource_amount": 0, "resource_type": "",
			"attack_target_id": "", "target_x": 0, "target_y": 0,
			"energy": 0, "max_energy": 0,
		})
		uy += 2.5
	
	uy += 1.0
	# Protoss units
	for utype in ["worker", "soldier", "scout"]:
		_test_ents.append({
			"id": "test_u3_%s" % utype, "owner": 3, "type": utype,
			"entity_type": utype, "building_type": "",
			"px": UX, "py": uy, "health": 100, "max_health": 100,
			"is_idle": true, "carry_amount": 0, "carry_capacity": 0,
			"attack": 10, "attack_range": 5, "speed": 3,
			"resource_amount": 0, "resource_type": "",
			"attack_target_id": "", "target_x": 0, "target_y": 0,
			"energy": 0, "max_energy": 0,
		})
		uy += 2.5
	
	_saved_ents = _ents.duplicate(true)
	_ents = _test_ents
	_update_entity_sprites()
	queue_redraw()

func _clear_test_entities() -> void:
	# Remove test sprites
	var to_remove: Array = []
	for eid in _sprite_pool:
		if str(eid).begins_with("test_"):
			_sprite_pool[eid].queue_free()
			to_remove.append(eid)
	for eid in to_remove:
		_sprite_pool.erase(eid)
	_test_ents.clear()
	# Restore original entities
	_ents = _saved_ents.duplicate(true)
	_saved_ents.clear()
	# Restore fog
	_fog_tiles = _saved_fog_tiles
	_fog_w = _saved_fog_w
	_fog_h = _saved_fog_h
	queue_redraw()


# ─── Replay Callbacks ──────────────────────────────────────
func _on_replay_loaded(replay_data: Dictionary) -> void:
	_replay_mode = true
	_game_active = false
	_replay_overlay.visible = true

	# Set map size + camera from first tick (same as _on_start does for live games)
	var first_tick: Dictionary = {}
	if replay_data.get("ticks", []).size() > 0:
		first_tick = replay_data["ticks"][0]
	_map_w = _to_f(first_tick.get("map_width"), 64.0)
	_map_h = _to_f(first_tick.get("map_height"), 64.0)
	if _map_w < 1.0:
		_map_w = 64.0
	if _map_h < 1.0:
		_map_h = 64.0
	if _cam_ctrl:
		_cam_ctrl.set_map_size(_map_w, _map_h)
	_camera.position = Vector2(_map_w / 2.0, _map_h / 2.0)

	_replay_player.load_replay(replay_data)
	print("[Replay] Loaded: %s (%d ticks, %s vs %s)" % [
		replay_data.get("match_id", "?"),
		replay_data.get("tick_count", 0),
		replay_data.get("player_races", {}).get("1", "?"),
		replay_data.get("player_races", {}).get("2", "?"),
	])
	# Auto-play the replay so it starts moving immediately
	_replay_player.play()

func _on_replay_finished() -> void:
	print("[Replay] Playback finished")
	_replay_mode = false