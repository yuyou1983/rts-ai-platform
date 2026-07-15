class_name CameraController
extends Node

## Camera Controller for the RTS game.
## Handles WASD/Arrow movement, mouse edge scrolling, scroll wheel zoom,
## middle-click drag pan, and F-key camera follow.
##
## Phase 1: Camera speed is expressed in screen-space (fraction of viewport
## traversed per second), converted to world units every frame so the
## perceived speed is stable regardless of zoom or window size.

# ── Signals ──────────────────────────────────────────────────────────────────
signal camera_position_changed(position: Vector2)
signal zoom_changed(zoom: Vector2)

# ── Exports ──────────────────────────────────────────────────────────────────
@export_group("Movement")
@export var edge_scroll_margin: float = 20.0

@export_group("Zoom")
@export var min_zoom: float = 2.0
@export var max_zoom: float = 20.0
@export var zoom_step: float = 0.5
@export var zoom_lerp_speed: float = 10.0

@export_group("Bounds")
@export var map_width: float = 64.0
@export var map_height: float = 64.0
@export var cell_size: float = 1.0

# ── Config ───────────────────────────────────────────────────────────────────
var _config: Dictionary = {}
var _baseline_config: Dictionary = {}

## Screen-space speeds (fraction of visible viewport width per second)
var keyboard_screen_per_second: float = 0.85
var edge_screen_per_second: float = 0.75
var edge_ramp_px: float = 28.0

## Zoom presets from sc1_feel_baseline.json
var _zoom_presets: Dictionary = {"gameplay": 1.0, "inspection": 1.35, "debug_overview": 0.65}
var _default_zoom_preset: String = "gameplay"

func _load_config() -> Dictionary:
	var path: String = "res://resources/feel/control_feel_config.json"
	if not ResourceLoader.exists(path):
		push_error("control_feel_config.json not found at " + path)
		return {}
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_error("Failed to open control_feel_config.json")
		return {}
	var text: String = f.get_as_text()
	f.close()
	var json: JSON = JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		push_error("JSON parse error in control_feel_config.json: " + json.get_error_message())
		return {}
	return json.data

func _load_baseline_config() -> Dictionary:
	var path: String = "res://resources/feel/sc1_feel_baseline.json"
	if not ResourceLoader.exists(path):
		return {}
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("Failed to open sc1_feel_baseline.json")
		return {}
	var text: String = f.get_as_text()
	f.close()
	var json: JSON = JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		push_warning("JSON parse error in sc1_feel_baseline.json: " + json.get_error_message())
		return {}
	return json.data

# ── Internal State ───────────────────────────────────────────────────────────
var _camera: Camera2D
var _target_zoom: Vector2 = Vector2.ONE
var _middle_dragging: bool = false
var _middle_drag_start: Vector2 = Vector2.ZERO
var _camera_drag_start: Vector2 = Vector2.ZERO
var _following_group: bool = false
var _follow_entity_ids: Array = []
var _entity_data_provider: Callable

func _ready() -> void:
	_config = _load_config()
	_baseline_config = _load_baseline_config()

	# Load screen-space speeds from sc1_feel_baseline.json, fallback to control_feel_config.json
	if _baseline_config.has("camera"):
		var bc: Dictionary = _baseline_config["camera"]
		keyboard_screen_per_second = float(bc.get("keyboard_screen_per_second", keyboard_screen_per_second))
		edge_screen_per_second = float(bc.get("edge_screen_per_second", edge_screen_per_second))
		edge_ramp_px = float(bc.get("edge_ramp_px", edge_ramp_px))
		_default_zoom_preset = str(bc.get("default_zoom_preset", _default_zoom_preset))
		if bc.has("zoom_presets"):
			_zoom_presets = bc["zoom_presets"]
	elif _config.has("camera"):
		# Fallback: derive screen-space speed from old world-unit speed
		var c: Dictionary = _config["camera"]
		# Use old values as fallback; they won't be screen-correct but maintain compat
		keyboard_screen_per_second = float(c.get("keyboard_screen_per_second", keyboard_screen_per_second))
		edge_screen_per_second = float(c.get("edge_screen_per_second", edge_screen_per_second))
		edge_scroll_margin = float(c.get("edge_scroll_margin", edge_scroll_margin))

	if _config.has("camera"):
		var c: Dictionary = _config["camera"]
		min_zoom = float(c.get("min_zoom", min_zoom))
		max_zoom = float(c.get("max_zoom", max_zoom))
		zoom_step = float(c.get("zoom_step", zoom_step))
		zoom_lerp_speed = float(c.get("zoom_lerp_speed", zoom_lerp_speed))

	set_process(true)
	set_process_input(true)

## Convert a screen-space speed (fraction of visible viewport width per second)
## to world units per second, based on current zoom and viewport size.
func _screen_speed_to_world(screen_per_second: float) -> float:
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	var visible_world_w: float = vp_size.x / maxf(_camera.zoom.x, 0.001)
	return visible_world_w * screen_per_second

func setup(camera: Camera2D) -> void:
	_camera = camera
	_camera.anchor_mode = Camera2D.ANCHOR_MODE_DRAG_CENTER
	_camera.position_smoothing_enabled = false

	# Use the default zoom preset (gameplay) — fixed, not derived from map size
	var preset_zoom: float = float(_zoom_presets.get(_default_zoom_preset, 1.0))

	# Calculate minimum zoom so viewport always fits inside map
	var vp := get_viewport().get_visible_rect().size
	var min_zoom_x := vp.x / maxf(map_width, 1.0)
	var min_zoom_y := vp.y / maxf(map_height, 1.0)
	var dynamic_min := maxf(min_zoom_x, min_zoom_y)
	# Use the larger of: preset zoom (scaled to be meaningful) or dynamic min
	# The preset is a *multiplier* on a baseline, so we need a base zoom.
	# For a 64x64 map on 1280x720, min zoom = 20. We treat "gameplay=1.0" as
	# the minimum zoom for normal play, and apply the preset as a ratio.
	var base_zoom := maxf(dynamic_min, min_zoom)
	var start_zoom := base_zoom * preset_zoom
	# Clamp to valid range
	start_zoom = clampf(start_zoom, maxf(dynamic_min, min_zoom), max_zoom)
	_target_zoom = Vector2(start_zoom, start_zoom)
	_camera.zoom = _target_zoom

	# NOTE: No more `keyboard_speed *= zoom` or `edge_scroll_speed *= zoom`.
	# Speed is now screen-space, converted per-frame via _screen_speed_to_world.

func _process(delta: float) -> void:
	if _camera == null:
		return

	_handle_keyboard_movement(delta)
	_handle_edge_scroll(delta)
	_handle_middle_drag()
	_handle_zoom_lerp(delta)
	_handle_follow_group(delta)
	_clamp_camera()

	camera_position_changed.emit(_camera.position)

func _input(event: InputEvent) -> void:
	if _camera == null:
		return

	# Scroll wheel zoom
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			_zoom_in()
			get_viewport().set_input_as_handled()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			_zoom_out()
			get_viewport().set_input_as_handled()

	# Middle-click drag start/end
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_MIDDLE:
		if event.pressed:
			_middle_dragging = true
			_middle_drag_start = event.position
			_camera_drag_start = _camera.position
		else:
			_middle_dragging = false

	# Middle-click drag motion
	if event is InputEventMouseMotion and _middle_dragging:
		# Handled in _process via _handle_middle_drag
		pass

	# F key to follow selected group
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F:
			toggle_follow_group()

# ── Keyboard Movement ───────────────────────────────────────────────────────
func _handle_keyboard_movement(delta: float) -> void:
	var world_speed: float = _screen_speed_to_world(keyboard_screen_per_second)
	var dt := delta
	if Input.is_action_pressed("move_camera_up"):
		_camera.position.y -= world_speed * dt
	if Input.is_action_pressed("move_camera_down"):
		_camera.position.y += world_speed * dt
	if Input.is_action_pressed("move_camera_left"):
		_camera.position.x -= world_speed * dt
	if Input.is_action_pressed("move_camera_right"):
		_camera.position.x += world_speed * dt

# ── Edge Scroll ──────────────────────────────────────────────────────────────
func _handle_edge_scroll(delta: float) -> void:
	var mpos := _get_viewport_mouse_position()
	var vp_size := get_viewport().get_visible_rect().size
	var world_speed: float = _screen_speed_to_world(edge_screen_per_second)

	# Left edge with ramp
	if mpos.x < edge_scroll_margin:
		var left_strength: float = clampf((edge_scroll_margin - mpos.x) / edge_ramp_px, 0.0, 1.0)
		_camera.position.x -= world_speed * left_strength * delta
	# Right edge with ramp
	if mpos.x > vp_size.x - edge_scroll_margin:
		var right_strength: float = clampf((mpos.x - (vp_size.x - edge_scroll_margin)) / edge_ramp_px, 0.0, 1.0)
		_camera.position.x += world_speed * right_strength * delta
	# Top edge with ramp
	if mpos.y < edge_scroll_margin:
		var top_strength: float = clampf((edge_scroll_margin - mpos.y) / edge_ramp_px, 0.0, 1.0)
		_camera.position.y -= world_speed * top_strength * delta
	# Bottom edge with ramp
	if mpos.y > vp_size.y - edge_scroll_margin:
		var bottom_strength: float = clampf((mpos.y - (vp_size.y - edge_scroll_margin)) / edge_ramp_px, 0.0, 1.0)
		_camera.position.y += world_speed * bottom_strength * delta

# ── Middle-click Drag ────────────────────────────────────────────────────────
func _handle_middle_drag() -> void:
	if not _middle_dragging:
		return
	var current_mouse := _get_viewport_mouse_position()
	var diff := _middle_drag_start - current_mouse
	_camera.position = _camera_drag_start + diff / _camera.zoom

# ── Zoom ─────────────────────────────────────────────────────────────────────
func _zoom_in() -> void:
	var new_zoom_x := _target_zoom.x + zoom_step
	_target_zoom = Vector2(minf(new_zoom_x, max_zoom), minf(new_zoom_x, max_zoom))
	_following_group = false

func _zoom_out() -> void:
	var new_zoom_x := _target_zoom.x - zoom_step
	# Prevent zoom out beyond map boundaries: viewport must fit inside map
	var vp := get_viewport().get_visible_rect().size
	var min_zoom_x := vp.x / maxf(map_width, 1.0)
	var min_zoom_y := vp.y / maxf(map_height, 1.0)
	var dynamic_min := maxf(min_zoom_x, min_zoom_y)
	var final_min := maxf(min_zoom, dynamic_min)
	_target_zoom = Vector2(maxf(new_zoom_x, final_min), maxf(new_zoom_x, final_min))
	_following_group = false

func _handle_zoom_lerp(delta: float) -> void:
	# Enforce dynamic min zoom so viewport never exceeds map
	var vp := get_viewport().get_visible_rect().size
	var dz_x := vp.x / maxf(map_width, 1.0)
	var dz_y := vp.y / maxf(map_height, 1.0)
	var dynamic_min := maxf(dz_x, dz_y)
	var final_min := maxf(min_zoom, dynamic_min)
	if _target_zoom.x < final_min:
		_target_zoom = Vector2(final_min, final_min)
	_camera.zoom = _camera.zoom.lerp(_target_zoom, zoom_lerp_speed * delta)
	if _camera.zoom.distance_to(_target_zoom) < 0.001:
		_camera.zoom = _target_zoom

# ── Camera Follow ────────────────────────────────────────────────────────────
func toggle_follow_group() -> void:
	_following_group = not _following_group
	if _following_group and _follow_entity_ids.is_empty():
		_following_group = false

func set_follow_entities(entity_ids: Array) -> void:
	_follow_entity_ids = entity_ids
	if entity_ids.is_empty():
		_following_group = false

func _handle_follow_group(_delta: float) -> void:
	if not _following_group or _follow_entity_ids.is_empty():
		return

	var center := Vector2.ZERO
	var count := 0
	for eid in _follow_entity_ids:
		var pos := _get_entity_position(str(eid))
		if pos != Vector2.ZERO or count == 0:
			center += pos
			count += 1

	if count > 0:
		center /= float(count)
		# With CENTER anchor, camera position IS the center of viewport
		_camera.position = center

func _get_entity_position(entity_id: String) -> Vector2:
	if _entity_data_provider.is_valid():
		var data: Dictionary = _entity_data_provider.call(entity_id)
		if not data.is_empty():
			var px: float = float(data.get("px", data.get("pos_x", 0.0)))
			var py: float = float(data.get("py", data.get("pos_y", 0.0)))
			return Vector2(px, py)
	return Vector2.ZERO

# ── Bounds ───────────────────────────────────────────────────────────────────
func _clamp_camera() -> void:
	var vp_size := get_viewport().get_visible_rect().size / _camera.zoom
	var map_px_w: float = map_width
	var map_px_h: float = map_height
	# Map boundary = window boundary: viewport must stay fully inside the map
	var half_vp_x := vp_size.x / 2.0
	var half_vp_y := vp_size.y / 2.0
	# Clamp camera center so viewport edges align with map edges
	_camera.position.x = clampf(_camera.position.x, half_vp_x, map_px_w - half_vp_x)
	_camera.position.y = clampf(_camera.position.y, half_vp_y, map_px_h - half_vp_y)

# ── Public API ───────────────────────────────────────────────────────────────
func set_entity_data_provider(provider: Callable) -> void:
	_entity_data_provider = provider

func set_map_size(w: float, h: float) -> void:
	map_width = w
	map_height = h

func move_to_world_position(world_pos: Vector2) -> void:
	if _camera == null:
		return
	# With CENTER anchor, camera.position IS the center
	_camera.position = world_pos
	_clamp_camera()

func get_camera_center() -> Vector2:
	if _camera == null:
		return Vector2.ZERO
	# With CENTER anchor, camera.position IS the center
	return _camera.position

# ── Helpers ──────────────────────────────────────────────────────────────────
func _get_viewport_mouse_position() -> Vector2:
	return get_viewport().get_mouse_position()
