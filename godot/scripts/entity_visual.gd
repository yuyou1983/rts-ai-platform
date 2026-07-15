class_name EntityVisual
extends AnimatedSprite2D

## Visual component for RTS entities (units and buildings).
## Uses SpriteLoader to dynamically load sprite frames, handles 8-direction
## facing with horizontal flipping, and syncs with SimCore state.
##
## Improved: smooth state transitions (settle/recovery), death fade-out,
## building construction animation, configurable via control_feel_config.json.

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
		if _current_state_raw != v:
			_begin_transition(_current_state_raw, v)
			_current_state_raw = v
			_update_animation()
	get:
		return _current_state_raw

var _current_state_raw: int = State.IDLE

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

# ─── Transition / Fade members ──────────────────────────────────────────────
var _transition_timer: float = 0.0
var _transition_target_state: int = -1
var _transition_from_state: int = -1

var _dying_timer: float = 0.0
var _dying_duration: float = 0.4

var _is_constructing: bool = false
var _construction_complete: bool = false
var _pop_timer: float = 0.0

# ─── Config (loaded from control_feel_config.json → animation key) ───────────
var _anim_config: Dictionary = {}

var _settle_duration: float = 0.15
var _recovery_duration: float = 0.2
var _death_fade_duration: float = 0.4
var _build_anim_fps: float = 4.0
var _normal_fps: float = 8.0
var _pop_speed_multiplier: float = 1.5
var _pop_duration: float = 0.3

# ─── Lifecycle ───────────────────────────────────────────────────────────────
func _ready() -> void:
	_sprite_loader = load("res://scripts/sprite_loader.gd").new()
	_load_sprite_frames()
	_load_anim_config()
	animation_finished.connect(_on_animation_finished)
	if Engine.has_singleton("AudioManager") or get_node_or_null("/root/AudioManager"):
		var am = get_node_or_null("/root/AudioManager")
		if am:
			am.play_selection_sound(entity_name)

func _process(delta: float) -> void:
	# ── Transition timer (settle / recovery) ──
	if _transition_timer > 0.0:
		_transition_timer -= delta
		if _transition_timer <= 0.0:
			_transition_timer = 0.0
			# Apply the target state — set raw to bypass setter (avoid re-triggering transition)
			var target := _transition_target_state
			_transition_target_state = -1
			_transition_from_state = -1
			speed_scale = 1.0
			if _current_state_raw != target:
				_current_state_raw = target
				_update_animation()

	# ── Death fade-out ──
	if _is_dead and not is_building_entity:
		if _dying_timer < _dying_duration:
			_dying_timer += delta
			modulate.a = 1.0 - (_dying_timer / _dying_duration)
		else:
			modulate.a = 0.0
			visible = false
			death_animation_finished.emit()

	# ── Building construction pop effect ──
	if _is_constructing and is_building_entity and not _is_dead:
		if _construction_complete:
			_pop_timer += delta
			if _pop_timer < _pop_duration:
				speed_scale = _pop_speed_multiplier
			else:
				speed_scale = 1.0
				_is_constructing = false
				_construction_complete = false
				_pop_timer = 0.0

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

# ─── Config loading ──────────────────────────────────────────────────────────
func _load_anim_config() -> void:
	var path: String = "res://resources/feel/control_feel_config.json"
	if not ResourceLoader.exists(path):
		# File may not be accessible via ResourceLoader; try direct file access
		pass
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		# Config not found — keep defaults
		return
	var json := JSON.new()
	var err := json.parse(f.get_as_text())
	f.close()
	if err != OK:
		push_warning("[EntityVisual] JSON parse error in control_feel_config.json: %s" % json.get_error_message())
		return
	var data: Dictionary = json.data
	if data.has("animation"):
		_anim_config = data["animation"]
		_settle_duration = float(_anim_config.get("settle_duration", _settle_duration))
		_recovery_duration = float(_anim_config.get("recovery_duration", _recovery_duration))
		_death_fade_duration = float(_anim_config.get("death_fade_duration", _death_fade_duration))
		_build_anim_fps = float(_anim_config.get("build_anim_fps", _build_anim_fps))
		_normal_fps = float(_anim_config.get("normal_fps", _normal_fps))
		_pop_speed_multiplier = float(_anim_config.get("pop_speed_multiplier", _pop_speed_multiplier))
		_pop_duration = float(_anim_config.get("pop_duration", _pop_duration))
	# Override dying duration from config
	_dying_duration = _death_fade_duration

# ─── Transition logic ────────────────────────────────────────────────────────
func _begin_transition(from_state: int, to_state: int) -> void:
	# Don't start a transition if we're already transitioning TO this state
	# (e.g., completing a settle where target is already IDLE)
	if _transition_target_state == to_state and _transition_timer > 0.0:
		return

	# MOVING → IDLE: settle phase (slow FPS to build_anim_fps briefly)
	if from_state == State.MOVING and to_state == State.IDLE:
		_transition_timer = _settle_duration
		_transition_target_state = State.IDLE
		_transition_from_state = from_state
		# Slow the animation speed during settle
		speed_scale = _build_anim_fps / _normal_fps
		return

	# ATTACKING → IDLE: recovery phase (hold pose briefly)
	if from_state == State.ATTACKING and to_state == State.IDLE:
		_transition_timer = _recovery_duration
		_transition_target_state = State.IDLE
		_transition_from_state = from_state
		# Hold at reduced speed during recovery
		speed_scale = 0.0  # Freeze frame for recovery hold
		return

	# Any other transition: clear transition state
	_transition_timer = 0.0
	_transition_target_state = -1
	_transition_from_state = -1
	speed_scale = 1.0

# ─── Animation updates ───────────────────────────────────────────────────────
func _update_animation() -> void:
	if is_building_entity or sprite_frames == null:
		return
	if _is_dead and current_state != State.DYING:
		return
	# If we're in a transition phase, don't switch animation yet
	if _transition_timer > 0.0:
		# For settle (MOVING→IDLE), keep playing moving anim at reduced speed
		if _transition_from_state == State.MOVING and _transition_target_state == State.IDLE:
			# Already handled in _begin_transition — keep current anim
			return
		# For recovery (ATTACKING→IDLE), freeze on last frame of attack
		if _transition_from_state == State.ATTACKING and _transition_target_state == State.IDLE:
			# Freeze on attack pose — speed_scale is already 0
			return

	var anim_base: String = _state_anim_map.get(current_state, "idle")
	var anim_key: String = _sprite_loader.get_animation_key(anim_base, direction_index)

	if sprite_frames.has_animation(anim_key):
		play(anim_key)
		_last_valid_anim = anim_key
		# Apply FPS based on state
		if current_state == State.BUILDING:
			speed_scale = _build_anim_fps / _normal_fps
		else:
			speed_scale = 1.0
	else:
		var fallback: String = _sprite_loader.get_animation_key("idle", direction_index)
		if sprite_frames.has_animation(fallback):
			play(fallback)
			_last_valid_anim = fallback
			speed_scale = 1.0
		elif _last_valid_anim != "" and sprite_frames.has_animation(_last_valid_anim):
			play(_last_valid_anim)
			speed_scale = 1.0

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
	_dying_timer = 0.0
	_dying_duration = _death_fade_duration
	if not is_building_entity and sprite_frames != null:
		var anim_key: String = _sprite_loader.get_animation_key("die", direction_index)
		if sprite_frames.has_animation(anim_key):
			play(anim_key)
			sprite_frames.set_animation_loop(anim_key, false)
	# Don't hide immediately — fade out over _dying_duration
	# _process will handle the fade

## Mark this building entity as under construction.
func start_construction() -> void:
	if is_building_entity:
		_is_constructing = true
		_construction_complete = false
		_pop_timer = 0.0
		current_state = State.BUILDING
		# Reduce FPS for construction animation
		speed_scale = _build_anim_fps / _normal_fps

## Signal that construction is complete — triggers the "pop" effect.
func finish_construction() -> void:
	if is_building_entity and _is_constructing:
		_construction_complete = true
		_pop_timer = 0.0
		# Speed up briefly for pop effect
		speed_scale = _pop_speed_multiplier

func reset() -> void:
	_is_dead = false
	_current_state_raw = State.IDLE
	direction_index = 6
	facing_angle = 0.0
	_last_valid_anim = ""
	_transition_timer = 0.0
	_transition_target_state = -1
	_transition_from_state = -1
	_dying_timer = 0.0
	_is_constructing = false
	_construction_complete = false
	_pop_timer = 0.0
	speed_scale = 1.0
	modulate = Color.WHITE
	visible = true

## Sync from a state dictionary received from SimCore via HTTP.
func sync_from_state(state: Dictionary) -> void:
	entity_name = state.get("type", entity_name)
	if _sprite_loader and _sprite_loader.is_building(entity_name):
		is_building_entity = true
	# ── Neutral team tint: override any team-color tinting ──
	if bool(state.get("neutral_team_tint", false)):
		modulate = Color.WHITE
	var speed: float = state.get("speed", 0.0)
	var is_idle: bool = state.get("is_idle", true)
	var pos_x: float = state.get("pos_x", 0.0)
	var pos_y: float = state.get("pos_y", 0.0)
	var target_x: float = state.get("target_x", pos_x)
	var target_y: float = state.get("target_y", pos_y)
	var attack: float = state.get("attack", 0.0)
	var is_constructing_flag = state.get("is_constructing", false)
	if is_constructing_flag != null:
		is_constructing_flag = bool(is_constructing_flag)

	if is_building_entity:
		# Construction state management
		if is_constructing_flag and not _is_constructing:
			start_construction()
		elif not is_constructing_flag and _is_constructing and not _construction_complete:
			finish_construction()

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
		# Death animation sprite loop finished; fade-out is handled by _process
		# Don't emit death_animation_finished here — wait for fade
		pause()
	elif current.begins_with("attack") or current.begins_with("cast") or current.begins_with("gather"):
		if current.begins_with("attack") and am:
			am.play_attack_sound(entity_name)
		animation_cycle_finished.emit(current)
		if current_state == State.ATTACKING or current_state == State.CASTING:
			# Transition to idle through recovery (not instant)
			_transition_timer = _recovery_duration
			_transition_target_state = State.IDLE
			_transition_from_state = current_state
			speed_scale = 0.0  # Freeze frame during recovery hold
