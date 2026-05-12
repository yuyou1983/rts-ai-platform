class_name EntityVisual
extends AnimatedSprite2D

## Visual component for RTS entities (units and buildings).
## Uses SpriteLoader to dynamically load sprite frames, handles 8-direction
## facing with horizontal flipping, and syncs with SimCore state.

signal animation_cycle_finished(anim_name: String)
signal death_animation_finished()

# ─── Exports ─────────────────────────────────────────────────────────────────
@export var entity_name: String = "":
	set(v):
		entity_name = v
		_load_sprite_frames()

@export var is_building_entity: bool = false

# ─── State ───────────────────────────────────────────────────────────────────
enum State { IDLE, MOVING, ATTACKING, GATHERING, CASTING, DYING, BUILDING }

var current_state: int = State.IDLE:
	set(v):
		if current_state != v:
			current_state = v
			_update_animation()

var facing_angle: float = 0.0:
	set(v):
		facing_angle = v
		_update_direction()

var direction_index: int = 6:  # Default south
	set(v):
		if direction_index != v:
			direction_index = v
			_update_direction()

var _last_valid_anim: String = ""
var _sprite_loader = null  # SpriteLoader instance (loaded lazily)
var _building_texture = null
var _is_dead: bool = false

var _state_anim_map: Dictionary = {
	State.IDLE: "idle",
	State.MOVING: "moving",
	State.ATTACKING: "attack",
	State.GATHERING: "gather",
	State.CASTING: "cast",
	State.DYING: "die",
	State.BUILDING: "build",
}

# ─── Lifecycle ───────────────────────────────────────────────────────────────
func _ready() -> void:
	_sprite_loader = load("res://scripts/sprite_loader.gd").new()
	_load_sprite_frames()
	animation_finished.connect(_on_animation_finished)
	if Engine.has_singleton("AudioManager") or get_node_or_null("/root/AudioManager"):
		var am = get_node_or_null("/root/AudioManager")
		if am:
			am.play_selection_sound(entity_name)

func _load_sprite_frames() -> void:
	if entity_name.is_empty() or _sprite_loader == null:
		return
	if is_building_entity:
		_setup_building()
	else:
		_setup_unit()

func _setup_unit() -> void:
	var frames = _sprite_loader.get_frames(entity_name)
	if frames == null:
		push_warning("[EntityVisual] No frames for unit: %s" % entity_name)
		return
	sprite_frames = frames
	var start_anim := "idle_south"
	if sprite_frames.has_animation(start_anim):
		play(start_anim)
		_last_valid_anim = start_anim

func _setup_building() -> void:
	var atlas = _sprite_loader.get_building_atlas(entity_name)
	if atlas == null:
		push_warning("[EntityVisual] No atlas for building: %s" % entity_name)
		return
	_building_texture = atlas
	_clear_children()
	var spr := Sprite2D.new()
	spr.texture = atlas
	spr.name = "BuildingSprite"
	spr.offset = Vector2(-atlas.region.size.x / 2.0, -atlas.region.size.y / 2.0)
	add_child(spr)

func _clear_children() -> void:
	for child in get_children():
		child.queue_free()

# ─── Animation updates ───────────────────────────────────────────────────────
func _update_animation() -> void:
	if is_building_entity or sprite_frames == null:
		return
	if _is_dead and current_state != State.DYING:
		return
	var anim_base: String = _state_anim_map.get(current_state, "idle")
	var anim_key: String = _sprite_loader.get_animation_key(anim_base, direction_index)
	if sprite_frames.has_animation(anim_key):
		play(anim_key)
		_last_valid_anim = anim_key
	else:
		var fallback: String = _sprite_loader.get_animation_key("idle", direction_index)
		if sprite_frames.has_animation(fallback):
			play(fallback)
			_last_valid_anim = fallback
		elif _last_valid_anim != "" and sprite_frames.has_animation(_last_valid_anim):
			play(_last_valid_anim)

func _update_direction() -> void:
	if _sprite_loader:
		var new_dir: int = _sprite_loader.get_direction_index(facing_angle)
		if new_dir != direction_index:
			direction_index = new_dir
			_update_animation()

# ─── Public API ───────────────────────────────────────────────────────────────
func set_entity_state(new_state: int) -> void:
	current_state = new_state

func set_facing_from_velocity(velocity: Vector2) -> void:
	if velocity.length_squared() > 0.01:
		facing_angle = velocity.angle()
		_update_direction()

func set_facing_toward(target_pos: Vector2) -> void:
	var dir := target_pos - global_position
	if dir.length_squared() > 0.01:
		facing_angle = dir.angle()
		_update_direction()

func play_death() -> void:
	_is_dead = true
	current_state = State.DYING
	if not is_building_entity and sprite_frames != null:
		var anim_key: String = _sprite_loader.get_animation_key("die", direction_index)
		if sprite_frames.has_animation(anim_key):
			play(anim_key)
			sprite_frames.set_animation_loop(anim_key, false)

func reset() -> void:
	_is_dead = false
	current_state = State.IDLE
	direction_index = 6
	facing_angle = 0.0
	_last_valid_anim = ""

## Sync from a state dictionary received from SimCore via HTTP.
func sync_from_state(state: Dictionary) -> void:
	entity_name = state.get("type", entity_name)
	if _sprite_loader and _sprite_loader.is_building(entity_name):
		is_building_entity = true
	var speed: float = state.get("speed", 0.0)
	var is_idle: bool = state.get("is_idle", true)
	var pos_x: float = state.get("pos_x", 0.0)
	var pos_y: float = state.get("pos_y", 0.0)
	var target_x: float = state.get("target_x", pos_x)
	var target_y: float = state.get("target_y", pos_y)
	var attack: float = state.get("attack", 0.0)

	if speed > 0.0 and not is_idle:
		var dx := target_x - pos_x
		var dy := target_y - pos_y
		if absf(dx) > 0.01 or absf(dy) > 0.01:
			facing_angle = Vector2(dx, -dy).angle()
		current_state = State.MOVING
	elif attack > 0.0 and not is_idle:
		current_state = State.ATTACKING
	elif is_idle and current_state != State.DYING:
		current_state = State.IDLE

# ─── Callbacks ────────────────────────────────────────────────────────────────
func _on_animation_finished() -> void:
	var current: String = animation
	var am = get_node_or_null("/root/AudioManager")
	if current.begins_with("die"):
		if am:
			am.play_death_sound(entity_name)
		death_animation_finished.emit()
		pause()
	elif current.begins_with("attack") or current.begins_with("cast") or current.begins_with("gather"):
		if current.begins_with("attack") and am:
			am.play_attack_sound(entity_name)
		animation_cycle_finished.emit(current)
		if current_state == State.ATTACKING or current_state == State.CASTING:
			current_state = State.IDLE