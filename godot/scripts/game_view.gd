extends Node2D

## Game view — renders SimCore state, relays player commands via HTTP gateway.
##
## Entity rendering:
##   worker   = yellow  square  (8x8)
##   soldier  = red     circle  (radius 6)
##   scout    = blue    diamond (8x8)
##   building = gray    rect    (24x24 for base, 16x16 for barracks)
##   resource = green   circle  (radius 4)
##
## Controls:
##   Left-click      → select unit (highlight green border)
##   Left-drag       → box-select units
##   Right-click     → move selected units to cursor
##   WASD            → scroll camera
##   Shift+click     → add to selection
##
## Minimap:
##   Bottom-right corner, 150x112 px
##   Shows all entity dots color-coded by owner

const GrpcBridge := preload("res://scripts/grpc_bridge.gd")

@onready var _tick_label: Label = %TickLabel if has_node("%TickLabel") else $HUD/TopBar/TickLabel
@onready var _resource_label: Label = %ResourceLabel if has_node("%ResourceLabel") else $HUD/TopBar/ResourceLabel
@onready var _map_container: Node2D = $MapContainer
@onready var _camera: Camera2D = $Camera2D
@onready var _minimap: ColorRect = $HUD/Minimap
@onready var _select_rect_node: ColorRect = $HUD/SelectRect

var _bridge: GrpcBridge
var _game_tick: int = 0
var _entity_sprites: Dictionary = {}  # entity_id → Sprite2D
var _health_bars: Dictionary = {}    # entity_id → ColorRect (health bar bg+fg)
var _cell_size: int = 16  # pixels per world unit

# Selection state
var _selected_ids: PackedStringArray = []
var _drag_start: Vector2 = Vector2.ZERO
var _is_dragging: bool = false

# Map bounds (for minimap & camera clamping)
var _map_width: float = 64.0
var _map_height: float = 64.0


func _ready() -> void:
	_bridge = GrpcBridge.new()
	add_child(_bridge)
	_bridge.game_started.connect(_on_game_started)
	_bridge.state_updated.connect(_on_state_updated)
	_bridge.start_game(42)
	_select_rect_node.visible = false
	_select_rect_node.color = Color(0.2, 0.8, 0.2, 0.3)


func _process(_delta: float) -> void:
	pass  # GrpcBridge handles polling via its timer


func _input(event: InputEvent) -> void:
	# Camera scroll with WASD
	var speed := 500.0
	if Input.is_action_pressed("move_camera_up"):
		_camera.position.y -= speed * get_process_delta_time()
	if Input.is_action_pressed("move_camera_down"):
		_camera.position.y += speed * get_process_delta_time()
	if Input.is_action_pressed("move_camera_left"):
		_camera.position.x -= speed * get_process_delta_time()
	if Input.is_action_pressed("move_camera_right"):
		_camera.position.x += speed * get_process_delta_time()
	# Clamp camera
	_camera.position.x = clampf(_camera.position.x, 0, _map_width * _cell_size)
	_camera.position.y = clampf(_camera.position.y, 0, _map_height * _cell_size)

	# Left-click: start drag or select
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			_drag_start = _camera.get_global_mouse_position()
			_is_dragging = true
		elif _is_dragging:
			_is_dragging = false
			_select_rect_node.visible = false
			var drag_end := _camera.get_global_mouse_position()
			var rect := Rect2(_drag_start, drag_end - _drag_start).abs()
			if rect.size.length() < 6.0:
				# Single click select
				if not Input.is_key_pressed(KEY_SHIFT):
					_selected_ids.clear()
				_try_select_at(_drag_start)
			else:
				# Box select
				if not Input.is_key_pressed(KEY_SHIFT):
					_selected_ids.clear()
				_select_in_rect(rect)
			_update_selection_highlights()

	# Right-click: move selected units
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		if _selected_ids.is_empty():
			return
		var target := _camera.get_global_mouse_position() / _cell_size
		var commands: Array = []
		for uid in _selected_ids:
			commands.append({
				"action": "move",
				"issuer": 1,
				"unit_id": uid,
				"target_x": target.x,
				"target_y": target.y,
			})
		_bridge.submit_commands(commands)

	# Drag selection rect visual
	if event is InputEventMouseMotion and _is_dragging:
		var drag_current := _camera.get_global_mouse_position()
		var rect := Rect2(_drag_start, drag_current - _drag_start).abs()
		_select_rect_node.visible = true
		_select_rect_node.position = rect.position
		_select_rect_node.size = rect.size


func _try_select_at(world_pos: Vector2) -> void:
	var best_id := ""
	var best_dist := 12.0
	for eid in _entity_sprites:
		var sprite: Sprite2D = _entity_sprites[eid]
		var dist := world_pos.distance_to(sprite.position)
		if dist < best_dist:
			best_dist = dist
			best_id = eid
	if best_id != "":
		if best_id not in _selected_ids:
			_selected_ids.append(best_id)
	else:
		_selected_ids.clear()


func _select_in_rect(rect: Rect2) -> void:
	for eid in _entity_sprites:
		var sprite: Sprite2D = _entity_sprites[eid]
		if rect.has_point(sprite.position):
			# Only select player-owned units
			var meta = sprite.get_meta("owner", 0)
			if meta == 1 and eid not in _selected_ids:
				_selected_ids.append(eid)


func _update_selection_highlights() -> void:
	for eid in _entity_sprites:
		var sprite: Sprite2D = _entity_sprites[eid]
		if eid in _selected_ids:
			sprite.modulate = Color(0.5, 1.0, 0.5)
		else:
			sprite.modulate = Color.WHITE


# ─── Signal handlers ──────────────────────────────────────────

func _on_game_started(initial_state: Dictionary) -> void:
	_game_tick = 0
	# Parse map size from state
	_map_width = float(initial_state.get("map_width", 64))
	_map_height = float(initial_state.get("map_height", 64))
	_render_entities(initial_state)
	_draw_minimap(initial_state)


func _on_state_updated(state: Dictionary) -> void:
	_game_tick = state.get("tick", _game_tick)
	_update_hud(state)
	_render_entities(state)
	_draw_minimap(state)


# ─── HUD ─────────────────────────────────────────────────────

func _update_hud(state: Dictionary) -> void:
	if _tick_label:
		_tick_label.text = "Tick: %d" % _game_tick
	if _resource_label:
		var res: Dictionary = state.get("resources", {})
		_resource_label.text = "Mineral: %d | Gas: %d" % [res.get("p1_mineral", 0), res.get("p1_gas", 0)]


# ─── Entity rendering ────────────────────────────────────────

func _render_entities(state: Dictionary) -> void:
	var entities: Dictionary = state.get("entities", {})
	var alive_ids: Array = entities.keys()

	# Remove sprites for dead entities
	for eid in _entity_sprites.keys():
		if eid not in alive_ids:
			_entity_sprites[eid].queue_free()
			_entity_sprites.erase(eid)
			if eid in _health_bars:
				_health_bars[eid].queue_free()
				_health_bars.erase(eid)
			if eid in _selected_ids:
				_selected_ids.remove_at(_selected_ids.find(eid))

	# Create or update sprites
	for eid in alive_ids:
		var e: Dictionary = entities[eid]
		var pos := Vector2(e.get("pos_x", 0.0), e.get("pos_y", 0.0)) * _cell_size
		var etype: String = e.get("entity_type", "")
		var owner: int = e.get("owner", 0)
		var health: float = float(e.get("health", 1))
		var max_health: float = float(e.get("max_health", 1))

		if eid not in _entity_sprites:
			var sprite := _create_entity_sprite(eid, e)
			_map_container.add_child(sprite)
			_entity_sprites[eid] = sprite
			# Health bar
			var bar := _create_health_bar(max_health)
			_map_container.add_child(bar)
			_health_bars[eid] = bar

		var sprite: Sprite2D = _entity_sprites[eid]
		sprite.position = pos

		# Update health bar
		if eid in _health_bars:
			var bar: ColorRect = _health_bars[eid]
			bar.position = pos + Vector2(-8, -10)
			var fg: ColorRect = bar.get_child(0) as ColorRect
			if fg and max_health > 0:
				fg.size.x = 16.0 * (health / max_health)
				fg.modulate = Color.GREEN if health > max_health * 0.5 else Color.YELLOW if health > max_health * 0.25 else Color.RED

		# Dim damaged entities
		var health_ratio: float = health / max(max_health, 1.0)
		if eid not in _selected_ids:
			sprite.modulate.a = clampf(0.3 + 0.7 * health_ratio, 0.3, 1.0)

	_update_selection_highlights()


func _create_entity_sprite(eid: String, e: Dictionary) -> Sprite2D:
	var sprite := Sprite2D.new()
	sprite.name = eid
	sprite.set_meta("owner", e.get("owner", 0))

	var etype: String = e.get("entity_type", "")
	var owner: int = e.get("owner", 0)
	var building_type: String = e.get("building_type", "")
	var unit_type: String = e.get("unit_type", "")

	# Owner colors: P1=cyan, P2=magenta, Neutral=white
	var color := Color.CYAN if owner == 1 else Color.MAGENTA if owner == 2 else Color.WHITE

	var img := Image.create_empty(16, 16, false, Image.FORMAT_RGBA8)
	img.fill(Color.TRANSPARENT)

	var shape_type := etype
	if etype == "unit" and unit_type != "":
		shape_type = unit_type
	elif etype == "building" and building_type != "":
		shape_type = building_type

	match shape_type:
		"worker":
			var sc := Color.YELLOW if owner != 0 else Color.GREEN
			img.fill_rect(Rect2i(4, 4, 8, 8), sc)
		"soldier":
			var sc := Color.RED if owner != 0 else Color.GRAY
			_draw_circle_on_image(img, 8, 8, 6, sc)
		"scout":
			var sc := Color.BLUE if owner != 0 else Color.WHITE
			_draw_diamond_on_image(img, 8, 8, 6, sc)
		"base":
			img.fill_rect(Rect2i(0, 0, 16, 16), Color.GRAY)
			img.fill_rect(Rect2i(2, 2, 12, 12), color)
		"barracks":
			img.fill_rect(Rect2i(2, 2, 12, 12), Color.GRAY)
			img.fill_rect(Rect2i(4, 4, 8, 8), color)
		"resource":
			_draw_circle_on_image(img, 8, 8, 4, Color.GREEN)
		_:
			img.fill_rect(Rect2i(4, 4, 8, 8), color)

	var tex := ImageTexture.create_from_image(img)
	sprite.texture = tex
	return sprite


func _create_health_bar(max_health: float) -> ColorRect:
	var bg := ColorRect.new()
	bg.size = Vector2(16, 3)
	bg.color = Color(0.1, 0.1, 0.1, 0.7)
	var fg := ColorRect.new()
	fg.size = Vector2(16, 3)
	fg.color = Color.GREEN
	bg.add_child(fg)
	return bg


# ─── Minimap ─────────────────────────────────────────────────

func _draw_minimap(state: Dictionary) -> void:
	var entities: Dictionary = state.get("entities", {})
	var minimap_img := Image.create_empty(150, 112, false, Image.FORMAT_RGBA8)
	minimap_img.fill(Color(0.05, 0.05, 0.08))

	var sx := 150.0 / _map_width
	var sy := 112.0 / _map_height

	for eid in entities:
		var e: Dictionary = entities[eid]
		var owner: int = e.get("owner", 0)
		var px := int(e.get("pos_x", 0.0) * sx)
		var py := int(e.get("pos_y", 0.0) * sy)
		px = clampi(px, 0, 149)
		py = clampi(py, 0, 111)
		var dot_color := Color.CYAN if owner == 1 else Color.MAGENTA if owner == 2 else Color.GREEN
		# 2x2 dot for visibility
		for dx in range(2):
			for dy in range(2):
				var cx := mini(px + dx, 149)
				var cy := mini(py + dy, 111)
				minimap_img.set_pixel(cx, cy, dot_color)

	# Draw camera viewport rectangle
	var cam_x := int(_camera.position.x / (_cell_size) * sx)
	var cam_y := int(_camera.position.y / (_cell_size) * sy)
	var cam_w := int(get_viewport().size.x / (_cell_size) * sx)
	var cam_h := int(get_viewport().size.y / (_cell_size) * sy)
	for x in range(maxi(cam_x, 0), mini(cam_x + cam_w, 150)):
		for y in [maxi(cam_y, 0), mini(cam_y + cam_h - 1, 111)]:
			if 0 <= x and x < 150 and 0 <= y and y < 112:
				minimap_img.set_pixel(x, y, Color.WHITE)
	for y in range(maxi(cam_y, 0), mini(cam_y + cam_h, 112)):
		for x in [maxi(cam_x, 0), mini(cam_x + cam_w - 1, 149)]:
			if 0 <= x and x < 150 and 0 <= y and y < 112:
				minimap_img.set_pixel(x, y, Color.WHITE)

	var tex := ImageTexture.create_from_image(minimap_img)
	# Apply to minimap ColorRect via a TextureRect child
	if _minimap.get_child_count() == 0:
		var tr := TextureRect.new()
		tr.name = "MinimapTexture"
		tr.texture = tex
		tr.stretch_mode = TextureRect.STRETCH_SCALE
		_minimap.add_child(tr)
	else:
		var tr: TextureRect = _minimap.get_child(0)
		tr.texture = tex


# ─── Image drawing helpers ───────────────────────────────────

func _draw_circle_on_image(img: Image, cx: int, cy: int, r: int, color: Color) -> void:
	for x in range(maxi(cx - r, 0), mini(cx + r + 1, 16)):
		for y in range(maxi(cy - r, 0), mini(cy + r + 1, 16)):
			if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r:
				img.set_pixel(x, y, color)


func _draw_diamond_on_image(img: Image, cx: int, cy: int, r: int, color: Color) -> void:
	for x in range(maxi(cx - r, 0), mini(cx + r + 1, 16)):
		for y in range(maxi(cy - r, 0), mini(cy + r + 1, 16)):
			if absi(x - cx) + absi(y - cy) <= r:
				img.set_pixel(x, y, color)


func _exit_tree() -> void:
	pass