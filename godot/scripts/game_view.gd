extends Node2D

## Game view — renders SimCore state, relays player commands via gRPC.
##
## Entity rendering:
##   worker   = yellow  square  (8×8)
##   soldier  = red     circle  (radius 6)
##   scout    = blue    diamond (8×8)
##   building = gray    rect    (24×24 for base, 16×16 for barracks)
##   resource = green   circle  (radius 4)

const GrpcBridge := preload("res://scripts/grpc_bridge.gd")

@onready var _tick_label: Label = %TickLabel if has_node("%TickLabel") else $HUD/TopBar/TickLabel
@onready var _resource_label: Label = %ResourceLabel if has_node("%ResourceLabel") else $HUD/TopBar/ResourceLabel
@onready var _map_container: Node2D = $MapContainer
@onready var _camera: Camera2D = $Camera2D

var _bridge: GrpcBridge
var _game_tick: int = 0
var _entity_sprites: Dictionary = {}  # entity_id → Sprite2D
var _cell_size: int = 16  # pixels per world unit


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

	# Right-click sends move command to selected units
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		var target := _camera.get_global_mouse_position()
		_bridge.submit_command({"action": "move", "target_x": target.x, "target_y": target.y})


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

	# Create or update sprites for each entity
	for eid in alive_ids:
		var e: Dictionary = entities[eid]
		var pos := Vector2(e.get("pos_x", 0.0), e.get("pos_y", 0.0)) * _cell_size
		var etype: String = e.get("entity_type", "")
		var owner: int = e.get("owner", 0)

		if eid not in _entity_sprites:
			var sprite := _create_entity_sprite(eid, etype, owner)
			_map_container.add_child(sprite)
			_entity_sprites[eid] = sprite

		var sprite: Sprite2D = _entity_sprites[eid]
		sprite.position = pos
		# Update health bar (modulate alpha based on health ratio)
		var health_ratio: float = float(e.get("health", 1)) / max(float(e.get("max_health", 1)), 1.0)
		sprite.modulate.a = clampf(0.3 + 0.7 * health_ratio, 0.3, 1.0)


func _create_entity_sprite(eid: String, etype: String, owner: int) -> Sprite2D:
	"""Create a colored sprite for the given entity type and owner."""
	var sprite := Sprite2D.new()
	sprite.name = eid

	# Owner colors: P1=cyan, P2=magenta, Neutral=white
	var color := Color.CYAN if owner == 1 else Color.MAGENTA if owner == 2 else Color.WHITE

	var img := Image.create_empty(16, 16, false, Image.FORMAT_RGBA8)
	img.fill(Color.TRANSPARENT)

	match etype:
		"worker":
			# Yellow square 8×8 centered
			var sc := Color.YELLOW if owner != 0 else Color.GREEN
			img.fill_rect(Rect2i(4, 4, 8, 8), sc)
		"soldier":
			# Red circle radius 6
			var sc := Color.RED if owner != 0 else Color.GRAY
			_draw_circle_on_image(img, 8, 8, 6, sc)
		"scout":
			# Blue diamond
			var sc := Color.BLUE if owner != 0 else Color.WHITE
			_draw_diamond_on_image(img, 8, 8, 6, sc)
		"building":
			# Gray rectangle — base=24×24, barracks=16×16
			var sz := 24 if _is_base(eid) else 16
			var offset := (16 - sz) / 2
			img.fill_rect(Rect2i(offset, offset, sz, sz), Color.GRAY)
		"resource":
			# Green circle radius 4
			_draw_circle_on_image(img, 8, 8, 4, Color.GREEN)
		_:
			img.fill_rect(Rect2i(4, 4, 8, 8), color)

	var tex := ImageTexture.create_from_image(img)
	sprite.texture = tex
	return sprite


func _is_base(eid: String) -> bool:
	"""Check if this entity ID looks like a base (heuristic)."""
	return "base" in eid


# ─── Image drawing helpers ───────────────────────────────────

func _draw_circle_on_image(img: Image, cx: int, cy: int, r: int, color: Color) -> void:
	for x in range(max(cx - r, 0), min(cx + r + 1, 16)):
		for y in range(max(cy - r, 0), min(cy + r + 1, 16)):
			if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r:
				img.set_pixel(x, y, color)


func _draw_diamond_on_image(img: Image, cx: int, cy: int, r: int, color: Color) -> void:
	for x in range(max(cx - r, 0), min(cx + r + 1, 16)):
		for y in range(max(cy - r, 0), min(cy + r + 1, 16)):
			if abs(x - cx) + abs(y - cy) <= r:
				img.set_pixel(x, y, color)


# ─── Minimap ─────────────────────────────────────────────────

func _draw_minimap_background() -> void:
	# TODO(#M2): dynamic minimap with live entity dots
	pass