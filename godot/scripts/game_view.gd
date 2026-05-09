extends Node2D

## Game view — renders SimCore state, relays player commands via gRPC.
##
## Entity rendering:
##   worker   = yellow  square  (8×8)
##   soldier  = red     circle  (radius 6)
##   scout    = blue    diamond (8×8)
##   building = gray    rect    (24×24 for base, 16×16 for barracks)
##   resource = green   circle  (radius 4)
##
## Controls:
##   Left-click  → select unit (highlight green border)
##   Right-click → move selected units to cursor
##   WASD        → scroll camera

const GrpcBridge := preload("res://scripts/grpc_bridge.gd")

@onready var _tick_label: Label = %TickLabel if has_node("%TickLabel") else $HUD/TopBar/TickLabel
@onready var _resource_label: Label = %ResourceLabel if has_node("%ResourceLabel") else $HUD/TopBar/ResourceLabel
@onready var _map_container: Node2D = $MapContainer
@onready var _camera: Camera2D = $Camera2D

var _bridge: GrpcBridge
var _game_tick: int = 0
var _entity_sprites: Dictionary = {}  # entity_id → Sprite2D
var _cell_size: int = 16  # pixels per world unit

# Selection state
var _selected_ids: PackedStringArray = []


func _ready() -> void:
	_bridge = GrpcBridge.new()
	add_child(_bridge)
	_bridge.game_started.connect(_on_game_started)
	_bridge.state_updated.connect(_on_state_updated)
	_bridge.start_game(42)


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

	# Left-click: select unit
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var click_pos := _camera.get_global_mouse_position()
		_try_select_at(click_pos)

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
		print("[GameView] Sent move command for %d units to (%.1f, %.1f)" % [_selected_ids.size(), target.x, target.y])


func _try_select_at(world_pos: Vector2) -> void:
	"""Try to select an entity near the click position."""
	var best_id := ""
	var best_dist := 12.0  # pixel threshold
	for eid in _entity_sprites:
		var sprite: Sprite2D = _entity_sprites[eid]
		var dist := world_pos.distance_to(sprite.position)
		if dist < best_dist:
			best_dist = dist
			best_id = eid

	if best_id != "":
		# Toggle selection
		if best_id in _selected_ids:
			_selected_ids.remove_at(_selected_ids.find(best_id))
		else:
			_selected_ids.append(best_id)
	else:
		# Click on empty → deselect all
		_selected_ids.clear()

	_update_selection_highlights()


func _update_selection_highlights() -> void:
	"""Green border for selected units."""
	for eid in _entity_sprites:
		var sprite: Sprite2D = _entity_sprites[eid]
		if eid in _selected_ids:
			sprite.modulate = Color(0.5, 1.0, 0.5)  # bright green tint
		else:
			sprite.modulate = Color.WHITE  # reset


# ─── Signal handlers ──────────────────────────────────────────

func _on_game_started(initial_state: Dictionary) -> void:
	_game_tick = 0
	_render_entities(initial_state)
	_draw_minimap_background()


func _on_state_updated(state: Dictionary) -> void:
	_game_tick = state.get("tick", _game_tick)
	_update_hud(state)
	_render_entities(state)


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

	# Remove sprites for entities that no longer exist
	for eid in _entity_sprites.keys():
		if eid not in alive_ids:
			_entity_sprites[eid].queue_free()
			_entity_sprites.erase(eid)
			_selected_ids.remove_at(_selected_ids.find(eid)) if eid in _selected_ids else null

	# Create or update sprites for each entity
	for eid in alive_ids:
		var e: Dictionary = entities[eid]
		var pos := Vector2(e.get("pos_x", 0.0), e.get("pos_y", 0.0)) * _cell_size
		var etype: String = e.get("entity_type", "")
		var owner: int = e.get("owner", 0)

		if eid not in _entity_sprites:
			var sprite := _create_entity_sprite(eid, e)
			_map_container.add_child(sprite)
			_entity_sprites[eid] = sprite

		var sprite: Sprite2D = _entity_sprites[eid]
		sprite.position = pos
		# Health-based alpha (dimmer when damaged)
		var health_ratio: float = float(e.get("health", 1)) / max(float(e.get("max_health", 1)), 1.0)
		if eid not in _selected_ids:
			sprite.modulate.a = clampf(0.3 + 0.7 * health_ratio, 0.3, 1.0)

	# Refresh selection highlights after render
	_update_selection_highlights()


func _create_entity_sprite(eid: String, e: Dictionary) -> Sprite2D:
	"""Create a colored sprite for the given entity."""
	var sprite := Sprite2D.new()
	sprite.name = eid

	var etype: String = e.get("entity_type", "")
	var owner: int = e.get("owner", 0)
	var building_type: String = e.get("building_type", "")
	var unit_type: String = e.get("unit_type", "")

	# Owner colors: P1=cyan, P2=magenta, Neutral=white
	var color := Color.CYAN if owner == 1 else Color.MAGENTA if owner == 2 else Color.WHITE

	var img := Image.create_empty(16, 16, false, Image.FORMAT_RGBA8)
	img.fill(Color.TRANSPARENT)

	# Pick shape by entity type
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


# ─── Image drawing helpers ───────────────────────────────────

func _draw_circle_on_image(img: Image, cx: int, cy: int, r: int, color: Color) -> void:
	for x in range(maxi(cx - r, 0), mini(cx + r + 1, 16)):
		for y in range(maxi(cy - r, 0), mini(cy + r + 1, 16)):
			if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r:
				img.set_pixel(x, y, color)


func _draw_diamond_on_image(img: Image, cx: int, cy: int, r: int, color: Color)-> void:
	for x in range(maxi(cx - r, 0), mini(cx + r + 1, 16)):
		for y in range(maxi(cy - r, 0), mini(cy + r + 1, 16)):
			if absi(x - cx) + absi(y - cy) <= r:
				img.set_pixel(x, y, color)


# ─── Minimap ─────────────────────────────────────────────────

func _draw_minimap_background() -> void:
	# TODO(#M2): dynamic minimap with live entity dots
	pass