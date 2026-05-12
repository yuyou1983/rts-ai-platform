extends Node2D

## RTS Game View — Full interactive RTS prototype.
## Now uses 6 adapted addon patterns: CallableStateMachine, EventBus,
## ObjectPool, SelectionManager, AbilityManager, ControlGroups.
##
## Controls:
##   WASD / Arrow keys     Move camera
##   Left click / drag     Select units
##   Shift+click           Add to selection
##   Ctrl+click            Select all same-type on screen
##   1-9                   Recall control group
##   Ctrl+1-9              Create control group
##   Shift+1-9             Add to control group
##   Double-tap 1-9        Jump camera to group
##   Right click           Context action (move / attack / gather)
##   M / S / A / P / H     Ability hotkeys (move/stop/attack/patrol/hold)
##   G + click             Gather (workers)
##   B + right-click       Build barracks (with worker selected)
##   T                     Train worker/soldier (with building selected)
##   Esc                   Deselect all

const GrpcBridgeScript := preload("res://scripts/grpc_bridge.gd")
const CallableStateMachine = preload("res://scripts/callable_state_machine.gd")

# ─── Config ────────────────────────────────────────────────
@onready var _camera: Camera2D = $Camera2D
var _cell: float = 16.0
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
const SELECT_RADIUS := 20.0

# ─── Camera ────────────────────────────────────────────────
var _cam_speed := 500.0

# ─── Build mode ────────────────────────────────────────────
var _build_mode := false

# ─── Game state ────────────────────────────────────────────
var _game_active := false
var _game_over_shown := false

# ─── Fog of war ────────────────────────────────────────────
var _fog_tiles: PackedInt32Array = []
var _fog_w: int = 0
var _fog_h: int = 0

# ─── Jitter monitor ────────────────────────────────────────
var _jitter_count: int = 0
var _total_jitter_px: float = 0.0

# ─── Minimap ───────────────────────────────────────────────
var _mm_size := Vector2(160, 120)
var _mm_margin := Vector2(8, 8)

# ─── Integrated Pattern References ─────────────────────────
# These are fetched via /root/ autoloads or created locally
var _selection: Node  # SelectionManager autoload
var _event_bus: Node  # EventBus autoload
var _ability_mgr: Node  # AbilityManager autoload

# ─── Entity Data Provider (bridges SimCore state → SelectionManager) ──
var _entity_cache_by_id: Dictionary = {}  # {entity_id: entity_dict}

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
	_camera.anchor_mode = Camera2D.ANCHOR_MODE_FIXED_TOP_LEFT
	_camera.position_smoothing_enabled = false

	_bridge = GrpcBridgeScript.new()
	_bridge.ai_player = 2
	add_child(_bridge)
	_bridge.game_started.connect(_on_start)
	_bridge.state_updated.connect(_on_state)
	_bridge.game_over.connect(_on_game_over)
	_bridge.start_game(42)
	_game_active = true

	# Connect to autoloads (may not exist yet in standalone test)
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

	print("===== GameView ready (Human P1 vs AI P2) path=", get_path())

# ─── Bridge between old _selected and new SelectionManager ──
var _selected: Dictionary = {}  # Kept for backward compat with drawing code

func _sync_selected_from_manager() -> void:
	if _selection:
		_selected = _selection.selection.duplicate()
	else:
		# Fallback: _selected managed directly
		pass

func _on_selection_changed(selection: Dictionary) -> void:
	_sync_selected_from_manager()
	if _ability_mgr:
		_ability_mgr.on_selection_changed(selection)

func _on_camera_focus_requested(center: Vector2) -> void:
	_camera.position = center - get_viewport().get_visible_rect().size / 2.0

# ───────────────────────────────────────────────────────────
func _process(_delta: float) -> void:
	_frame += 1
	_move_camera()
	_monitor_canvas_transform()
	_build_mode = Input.is_key_pressed(KEY_B)
	# Decay damage floaters
	for f in _dmg_floats:
		f.ttl -= 1
		f.y -= 0.5
	_dmg_floats = _dmg_floats.filter(func(f): return f.ttl > 0)
	queue_redraw()
	if _frame == 30 and not _analysis_written:
		_analysis_written = true
		_write_analysis()
	# Game over key handling
	if _game_over_shown:
		if Input.is_key_pressed(KEY_R):
			_restart_game()
		elif Input.is_key_pressed(KEY_Q):
			get_tree().quit()

# ─── Camera ────────────────────────────────────────────────
func _move_camera() -> void:
	var dt := get_process_delta_time()
	if Input.is_action_pressed("move_camera_up"):
		_camera.position.y -= _cam_speed * dt
	if Input.is_action_pressed("move_camera_down"):
		_camera.position.y += _cam_speed * dt
	if Input.is_action_pressed("move_camera_left"):
		_camera.position.x -= _cam_speed * dt
	if Input.is_action_pressed("move_camera_right"):
		_camera.position.x += _cam_speed * dt
	var vp := get_viewport().get_visible_rect().size
	_camera.position.x = clampf(_camera.position.x, 0, maxf(0, _map_w * _cell - vp.x))
	_camera.position.y = clampf(_camera.position.y, 0, maxf(0, _map_h * _cell - vp.y))

func _cam_offset() -> Vector2:
	return -_camera.position

func _screen_to_world(sp: Vector2) -> Vector2:
	return sp + _camera.position

func _world_to_screen(wp: Vector2) -> Vector2:
	return wp - _camera.position

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
	if _game_over_shown:
		return

	# Right-click: context action
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		_handle_right_click()
		return

	# Left-click: check minimap first, then selection
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var mpos := get_viewport().get_mouse_position()
		if _is_minimap_click(mpos):
			_handle_minimap_click(mpos)
			return
		_dragging = true
		_drag_start = mpos
		_drag_end = mpos
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
			var group_idx: int = key - KEY_1 + 1  # 1-9
			if _selection:
				if event.ctrl_pressed:
					_selection.create_hotkey_group(group_idx)
				elif event.shift_pressed:
					_selection.add_to_hotkey_group(group_idx)
				else:
					_selection.select_hotkey_group(group_idx)
			return
		# Double-tap detection for jump (simplified: Ctrl+number = jump)
		if key >= KEY_1 + 512 and key <= KEY_9 + 512:  # physical keys
			pass

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

func _handle_right_click() -> void:
	var selected_ids: Array = []
	if _selection:
		selected_ids = _selection.get_selected_ids()
	else:
		selected_ids = _selected.keys()

	if selected_ids.is_empty():
		return

	var world_pos := _screen_to_world(get_viewport().get_mouse_position())
	var tgt_world := world_pos / _cell
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

	# Generate commands per selected unit
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
					else:
						cmds.append({
							"action": "move",
							"unit_id": uid,
							"target_x": tgt_world.x,
							"target_y": tgt_world.y,
							"issuer": 1,
						})
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
					cmds.append({
						"action": "move",
						"unit_id": uid,
						"target_x": tgt_world.x,
						"target_y": tgt_world.y,
						"issuer": 1,
					})

	if cmds.size() > 0:
		_bridge.submit_commands(cmds)

	# Also emit via EventBus
	if _event_bus and cmds.size() > 0:
		for cmd in cmds:
			_event_bus.emit_command_issued(cmd)

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

# ─── Bridge callbacks ─────────────────────────────────────
func _on_start(state: Dictionary) -> void:
	_map_w = float(state.get("map_width", 64))
	_map_h = float(state.get("map_height", 64))
	_parse(state)
	_camera.position = Vector2(10, 10) * _cell

func _on_state(state: Dictionary) -> void:
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
	var new_seed := randi() % 100000
	_bridge.start_game(new_seed)

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
			"owner": int(e.get("owner", 0)),
			"type": etype,
			"entity_type": etype,
			"building_type": btype,
			"resource_type": rtype,
			"resource_amount": float(e.get("resource_amount", 0)),
			"px": float(e.get("pos_x", 0)) * _cell,
			"py": float(e.get("pos_y", 0)) * _cell,
			"pos_x": float(e.get("pos_x", 0)),
			"pos_y": float(e.get("pos_y", 0)),
			"health": float(e.get("health", 0)),
			"max_health": float(e.get("max_health", 0)),
			"is_idle": bool(e.get("is_idle", true)),
			"carry_amount": float(e.get("carry_amount", 0)),
			"carry_cap": float(e.get("carry_capacity", 0)),
			"attack": float(e.get("attack", 0)),
			"attack_range": float(e.get("attack_range", 16.0)),
			"attack_target_id": str(e.get("attack_target_id", "")),
			"target_x": float(e.get("target_x", 0)),
			"target_y": float(e.get("target_y", 0)),
			"speed": float(e.get("speed", 0)),
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

	# Detect damage
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
					"y": e.py - 20.0,
					"amount": dmg,
					"ttl": 30,
				})
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

# ───────────────────────────────────────────────────────────
# ─── DRAWING ───────────────────────────────────────────────
# ───────────────────────────────────────────────────────────
func _draw() -> void:
	var co := _cam_offset()
	_draw_map_background(co)
	_draw_grid(co)
	_draw_fog_of_war(co)
	_draw_entities(co)
	_draw_combat_effects(co)
	_draw_health_bars(co)
	_draw_selection_rings(co)
	_draw_drag_box()
	_draw_damage_floats(co)
	_draw_hud()
	_draw_minimap()

func _draw_map_background(co: Vector2) -> void:
	draw_rect(Rect2(co, Vector2(_map_w * _cell, _map_h * _cell)), Color(0.15, 0.18, 0.12, 1.0))

func _draw_grid(co: Vector2) -> void:
	var grid_color := Color(0.25, 0.28, 0.22, 0.3)
	var step := _cell * 8.0
	var map_px := _map_w * _cell
	var map_py := _map_h * _cell
	var x := step
	while x < map_px:
		draw_line(Vector2(x, 0) + co, Vector2(x, map_py) + co, grid_color, 1.0)
		x += step
	var y := step
	while y < map_py:
		draw_line(Vector2(0, y) + co, Vector2(map_px, y) + co, grid_color, 1.0)
		y += step

func _draw_fog_of_war(co: Vector2) -> void:
	if _fog_w <= 0 or _fog_h <= 0 or _fog_tiles.is_empty():
		return
	var map_px := _map_w * _cell
	var map_py := _map_h * _cell
	var tile_w := map_px / float(_fog_w)
	var tile_h := map_py / float(_fog_h)
	for gy in range(_fog_h):
		for gx in range(_fog_w):
			var idx := gy * _fog_w + gx
			if idx >= _fog_tiles.size():
				break
			var state_val: int = _fog_tiles[idx]
			var alpha := 0.0
			if state_val == 0:
				alpha = 0.85
			elif state_val == 1:
				alpha = 0.45
			else:
				continue
			var px := gx * tile_w + co.x
			var py := gy * tile_h + co.y
			draw_rect(Rect2(px, py, tile_w + 1.0, tile_h + 1.0), Color(0.02, 0.02, 0.05, alpha), true)

func _draw_entities(co: Vector2) -> void:
	for e in _ents:
		var pos := Vector2(e.px, e.py) + co
		var c: Color
		var radius: float = 8.0

		match e.owner:
			1: c = Color(0.0, 0.9, 0.9, 1.0)
			2: c = Color(0.9, 0.2, 0.9, 1.0)
			_: c = Color.WHITE

		match e.type:
			"worker":
				radius = 6.0
				draw_circle(pos, radius, c)
				draw_line(pos + Vector2(-3, -3), pos + Vector2(3, 3), Color.YELLOW, 1.5)
			"soldier":
				radius = 8.0
				var pts := PackedVector2Array([pos + Vector2(0, -radius), pos + Vector2(radius, 0), pos + Vector2(0, radius), pos + Vector2(-radius, 0)])
				draw_colored_polygon(pts, c)
				draw_line(pos, pos + Vector2(radius, 0), Color.WHITE, 2.0)
			"scout":
				radius = 5.0
				draw_circle(pos, radius, c)
				draw_arc(pos, radius + 3, 0, TAU, 12, Color(c.r, c.g, c.b, 0.5), 1.0, true)
			"building":
				radius = 12.0
				var half := Vector2(radius, radius * 0.7)
				draw_rect(Rect2(pos - half, half * 2), c, false, 2.0)
				if e.building_type == "base":
					draw_rect(Rect2(pos - half * 0.7, half * 1.4), Color(c.r, c.g, c.b, 0.5), true)
				if e.building_type != "" and e.max_health > 0 and e.health < e.max_health:
					var frac: float = e.health / e.max_health
					draw_rect(Rect2(pos - half, half * 2), Color(1, 1, 0, 0.3 * (1.0 - frac)), true)
			"resource":
				radius = 6.0
				if e.resource_type == "mineral":
					c = Color(1.0, 0.85, 0.0, 1.0)
					draw_rect(Rect2(pos - Vector2(radius, radius), Vector2(radius * 2, radius * 2)), c, true)
				elif e.resource_type == "gas":
					c = Color(0.0, 0.8, 0.0, 1.0)
					draw_circle(pos, radius, c)
				else:
					draw_circle(pos, radius, Color.GRAY)
			_:
				draw_circle(pos, radius, c)

	# Attack / move target lines
	for e in _ents:
		if e.attack_target_id != "" or not e.is_idle:
			var lpos := Vector2(e.px, e.py) + co
			if e.attack_target_id != "":
				var tgt = _get_ent_by_id(e.attack_target_id)
				if not tgt.is_empty():
					var tpos := Vector2(tgt.px, tgt.py) + co
					draw_line(lpos, tpos, Color(1.0, 0.3, 0.3, 0.5), 1.0, true)
			elif e.target_x != 0 or e.target_y != 0:
				var tpos := Vector2(e.target_x, e.target_y) * _cell + co
				draw_line(lpos, tpos, Color(0.3, 1.0, 0.3, 0.3), 1.0, true)

func _draw_combat_effects(co: Vector2) -> void:
	for e in _ents:
		if e.attack_target_id != "":
			var pos := Vector2(e.px, e.py) + co
			var pulse: float = 0.4 + 0.6 * abs(sin(_frame * 0.15))
			draw_arc(pos, 12.0, 0, TAU, 16, Color(1.0, 0.15, 0.15, pulse), 2.5, true)
	for f in _dmg_floats:
		if f.ttl > 25:
			var tgt = _get_ent_by_id(f.id)
			if not tgt.is_empty():
				var pos := Vector2(tgt.px, tgt.py) + co
				draw_circle(pos, 14.0, Color(1.0, 0.2, 0.2, 0.35))

func _draw_damage_floats(co: Vector2) -> void:
	for f in _dmg_floats:
		var alpha: float = clampf(f.ttl / 30.0, 0.0, 1.0)
		var pos := Vector2(f.x, f.y) + co
		var txt := "-%d" % int(f.amount)
		draw_string(_default_font, pos, txt, HORIZONTAL_ALIGNMENT_CENTER, -1, 14, Color(1.0, 0.2, 0.2, alpha))

func _draw_health_bars(co: Vector2) -> void:
	for e in _ents:
		if e.max_health <= 0 or e.type == "resource":
			continue
		var pos := Vector2(e.px, e.py) + co
		var bar_w := 20.0
		var bar_h := 3.0
		var bar_y := pos.y - 18.0
		var frac: float = e.health / e.max_health
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.3, 0.3, 0.3, 0.8), true)
		var hp_color := Color.GREEN if frac > 0.6 else Color.YELLOW if frac > 0.3 else Color.RED
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * frac, bar_h), hp_color, true)

func _draw_selection_rings(co: Vector2) -> void:
	for uid in _selected:
		var e := _get_ent_by_id(uid)
		if e.is_empty():
			continue
		var pos := Vector2(e.px, e.py) + co
		draw_arc(pos, 14.0, 0.0, TAU, 16, Color(0.2, 1.0, 0.2, 0.9), 2.0, true)

func _draw_drag_box() -> void:
	if not _dragging:
		return
	var tl := Vector2(minf(_drag_start.x, _drag_end.x), minf(_drag_start.y, _drag_end.y))
	var size := Vector2(absf(_drag_end.x - _drag_start.x), absf(_drag_end.y - _drag_start.y))
	draw_rect(Rect2(tl, size), Color(0.2, 1.0, 0.2, 0.15), true)
	draw_rect(Rect2(tl, size), Color(0.2, 1.0, 0.2, 0.6), false, 1.5)

func _draw_hud() -> void:
	var info_lines: Array = [
		"Tick: %d  Ents: %d  Sel: %d" % [_bridge._tick, _ents.size(), _selected.size()],
	]
	if _fog_w > 0 and _fog_h > 0 and not _fog_tiles.is_empty():
		var total := _fog_tiles.size()
		var explored := 0
		for t in _fog_tiles:
			if t >= 1:
				explored += 1
		var pct := explored * 100 / total
		info_lines.append("Map explored: %d%%" % pct)
	if _build_mode:
		info_lines.append("[BUILD MODE] Right-click to place barracks")

	var sel_types: Dictionary = {}
	for uid in _selected:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue
		var key = "%s(%s)" % [e.type, e.building_type if e.building_type else e.resource_type]
		sel_types[key] = sel_types.get(key, 0) + 1

	if not sel_types.is_empty():
		var sel_str := "Selected: "
		for k in sel_types:
			sel_str += "%s×%d " % [k, sel_types[k]]
		info_lines.append(sel_str)

	if not _selected.is_empty():
		var hints: Array = []
		var has_workers := false
		var has_buildings := false
		for uid in _selected:
			var e = _get_ent_by_id(uid)
			if e.is_empty(): continue
			if e.type == "worker": has_workers = true
			if e.type == "building": has_buildings = true
		if has_workers:
			hints.append("Right-click: Move/Gather/Attack | B+Right-click: Build")
		if has_buildings:
			for uid2 in _selected:
				var eb = _get_ent_by_id(uid2)
				if eb.is_empty(): continue
				if eb.type == "building" and eb.owner == 1:
					if eb.building_type == "base":
						hints.append("T→Worker(50$)")
					elif eb.building_type == "barracks":
						hints.append("T→Soldier(100$)")
		if hints.size() > 0:
			info_lines.append("  ".join(hints))

	for i in info_lines.size():
		draw_string(_default_font, Vector2(8, 20 + i * 16), info_lines[i], HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color.YELLOW)

	if _game_over_shown:
		var vp := get_viewport().get_visible_rect().size
		draw_rect(Rect2(Vector2.ZERO, vp), Color(0, 0, 0, 0.6), true)
		var winner_text := "YOU WIN!" if _bridge._winner == 1 else "YOU LOSE!"
		var win_color := Color.GREEN if _bridge._winner == 1 else Color.RED
		draw_string(_default_font, Vector2(vp.x / 2 - 60, vp.y / 2 - 30), winner_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 32, win_color)
		draw_string(_default_font, Vector2(vp.x / 2 - 80, vp.y / 2 + 10), "Press R to restart", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color.WHITE)
		draw_string(_default_font, Vector2(vp.x / 2 - 80, vp.y / 2 + 30), "Press Q to quit", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color.GRAY)

# ─── Minimap ──────────────────────────────────────────────
func _minimap_rect() -> Rect2:
	var vp := get_viewport().get_visible_rect().size
	var mm_pos := vp - _mm_size - _mm_margin
	return Rect2(mm_pos, _mm_size)

func _is_minimap_click(screen_pos: Vector2) -> bool:
	return _minimap_rect().has_point(screen_pos)

func _handle_minimap_click(screen_pos: Vector2) -> void:
	var mm := _minimap_rect()
	var local := screen_pos - mm.position
	var frac_x: float = local.x / mm.size.x
	var frac_y: float = local.y / mm.size.y
	var map_px_w: float = _map_w * _cell
	var map_px_h: float = _map_h * _cell
	_camera.position = Vector2(frac_x * map_px_w, frac_y * map_px_h)

func _draw_minimap() -> void:
	var vp := get_viewport().get_visible_rect().size
	var mm_pos := vp - _mm_size - _mm_margin
	draw_rect(Rect2(mm_pos, _mm_size), Color(0.0, 0.0, 0.0, 0.6), true)
	draw_rect(Rect2(mm_pos, _mm_size), Color(0.5, 0.5, 0.5, 0.8), false, 1.0)
	var sx: float = _mm_size.x / (_map_w * _cell)
	var sy: float = _mm_size.y / (_map_h * _cell)
	for e in _ents:
		var epos := Vector2(e.px * sx, e.py * sy) + mm_pos
		var c: Color
		if e.owner == 1: c = Color.CYAN
		elif e.owner == 2: c = Color.MAGENTA
		elif e.type == "resource" and e.resource_type == "mineral": c = Color.GOLD
		elif e.type == "resource" and e.resource_type == "gas": c = Color.GREEN
		else: c = Color.WHITE
		var dot_size := 2.0 if e.type != "building" else 3.0
		draw_circle(epos, dot_size, c)
	var cam_tl_x: float = _camera.position.x * sx + mm_pos.x
	var cam_tl_y: float = _camera.position.y * sy + mm_pos.y
	var cam_w: float = vp.x * sx
	var cam_h: float = vp.y * sy
	draw_rect(Rect2(cam_tl_x, cam_tl_y, cam_w, cam_h), Color(1.0, 1.0, 1.0, 0.5), false, 1.0)

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
		"camera_anchor": "FIXED_TOP_LEFT",
		"stretch_mode": "canvas_items",
	}
	var vf := FileAccess.open("user://render_verdict.json", FileAccess.WRITE)
	if vf:
		vf.store_string(JSON.stringify(verdict, "\t"))
		vf.close()
		print("[Verdict] ", "PASS" if verdict["pass"] else "FAIL",
				" jitter=", "NONE" if verdict["jitter_free"] else str(_jitter_count))