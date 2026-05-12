class_name CameraController
extends Node

## Camera Controller for the RTS game.
## Handles WASD/Arrow movement, mouse edge scrolling, scroll wheel zoom,
## middle-click drag pan, and F-key camera follow.

# ── Signals ──────────────────────────────────────────────────────────────────
signal camera_position_changed(position: Vector2)
signal zoom_changed(zoom: Vector2)

# ── Exports ──────────────────────────────────────────────────────────────────
@export_group("Movement")
@export var keyboard_speed: float = 500.0
@export var edge_scroll_margin: float = 20.0
@export var edge_scroll_speed: float = 400.0

@export_group("Zoom")
@export var min_zoom: float = 0.5
@export var max_zoom: float = 2.0
@export var zoom_step: float = 0.1
@export var zoom_lerp_speed: float = 10.0

@export_group("Bounds")
@export var map_width: float = 64.0
@export var map_height: float = 64.0
@export var cell_size: float = 1.0

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
	set_process(true)
	set_process_input(true)

func setup(camera: Camera2D) -> void:
	_camera = camera
	_camera.anchor_mode = Camera2D.ANCHOR_MODE_FIXED_TOP_LEFT
	_camera.position_smoothing_enabled = false
	_target_zoom = _camera.zoom
	# DPI-aware default zoom for Retina displays
	var screen_dpi := DisplayServer.screen_get_dpi()
	if screen_dpi >= 192:  # Retina or higher
		_target_zoom = Vector2(2.0, 2.0)
		_camera.zoom = _target_zoom
	keyboard_speed *= float(_target_zoom.x)
	edge_scroll_speed *= float(_target_zoom.x)

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
	var dt := delta
	if Input.is_action_pressed("move_camera_up"):
		_camera.position.y -= keyboard_speed * dt
	if Input.is_action_pressed("move_camera_down"):
		_camera.position.y += keyboard_speed * dt
	if Input.is_action_pressed("move_camera_left"):
		_camera.position.x -= keyboard_speed * dt
	if Input.is_action_pressed("move_camera_right"):
		_camera.position.x += keyboard_speed * dt

# ── Edge Scroll ──────────────────────────────────────────────────────────────
func _handle_edge_scroll(delta: float) -> void:
	var mpos := _get_viewport_mouse_position()
	var vp_size := get_viewport().get_visible_rect().size
	var speed := edge_scroll_speed * delta

	if mpos.x < edge_scroll_margin:
		_camera.position.x -= speed
	if mpos.x > vp_size.x - edge_scroll_margin:
		_camera.position.x += speed
	if mpos.y < edge_scroll_margin:
		_camera.position.y -= speed
	if mpos.y > vp_size.y - edge_scroll_margin:
		_camera.position.y += speed

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
	_target_zoom = Vector2(maxf(new_zoom_x, min_zoom), maxf(new_zoom_x, min_zoom))
	_following_group = false

func _handle_zoom_lerp(delta: float) -> void:
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
		var vp_size := get_viewport().get_visible_rect().size
		_camera.position = center - vp_size / (2.0 * _camera.zoom)

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
	var map_px_w: float = map_width  # no cell_size multiplier needed since TILE_SIZE=1
	var map_px_h: float = map_height
	_camera.position.x = clampf(_camera.position.x, 0, maxf(0, map_px_w - vp_size.x))
	_camera.position.y = clampf(_camera.position.y, 0, maxf(0, map_px_h - vp_size.y))

# ── Public API ───────────────────────────────────────────────────────────────
func set_entity_data_provider(provider: Callable) -> void:
	_entity_data_provider = provider

func set_map_size(w: float, h: float) -> void:
	map_width = w
	map_height = h

func move_to_world_position(world_pos: Vector2) -> void:
	if _camera == null:
		return
	var vp_size := get_viewport().get_visible_rect().size / _camera.zoom
	_camera.position = world_pos - vp_size / 2.0
	_clamp_camera()

func get_camera_center() -> Vector2:
	if _camera == null:
		return Vector2.ZERO
	var vp_size := get_viewport().get_visible_rect().size / _camera.zoom
	return _camera.position + vp_size / 2.0

# ── Helpers ──────────────────────────────────────────────────────────────────
func _get_viewport_mouse_position() -> Vector2:
	return get_viewport().get_mouse_position()