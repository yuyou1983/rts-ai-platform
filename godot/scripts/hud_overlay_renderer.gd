class_name HUDOverlayRenderer
extends Node2D

## HUD Overlay Renderer — standalone Node2D that draws all HUD overlay decorations.
## Extracted from game_view.gd to isolate overlay concerns.
##
## Usage:
##   var hud_overlay := HUDOverlayRenderer.new()
##   add_child(hud_overlay)
##   hud_overlay.setup(_camera, _default_font)
##   hud_overlay.set_visual_helpers(
##       _visual_radius, _visual_scale, _resolve_visual_id,
##       _is_building_entity_visual, _screen_to_world, _world_to_screen,
##       _is_in_fog, _get_ent_by_id, _get_entity_data, _to_f, _ent_at_world_pos
##   )
##   hud_overlay.set_data_refs(_player_races, _rally_indicators, _selection)
##
## Per frame:
##   hud_overlay.provide_entity_data(_ents, _selected, _entity_cache_by_id)
##   hud_overlay.advance_timers(delta)
##
## In _draw():
##   hud_overlay.draw_all(self)

signal pings_updated()

# ─── Overlay Constants ──────────────────────────────────────────────────────
const ATTACK_FLASH_DURATION: float = 0.1
const DEATH_EFFECT_DURATION: float = 0.5
const HOVER_CHECK_INTERVAL: float = 0.05
const SELECTION_BREATHE_SPEED: float = 3.0
const SELECTION_BREATHE_MIN: float = 0.55
const SELECTION_BREATHE_MAX: float = 1.0

const SELECT_RADIUS: float = 1.5
const PYLON_POWER_RADIUS: float = 8.0

# ─── Command ping feedback ──────────────────────────────────────────────────
var _ground_ping_duration: float = 0.32
var _ground_ping_color: Color = Color(0.267, 1.0, 0.533)  # #44ff88
var _attack_ping_duration: float = 0.38
var _attack_ping_color: Color = Color(1.0, 0.267, 0.267)  # #ff4444
var _invalid_ping_duration: float = 0.22
var _invalid_ping_color: Color = Color(0.667, 0.4, 0.4)  # #aa6666
var _assign_flash_duration: float = 0.5
var _empty_group_hint_duration: float = 0.8

# ─── Combat visual feedback ─────────────────────────────────────────────────
var _attack_flash_timers: Dictionary = {}  # entity_id → remaining flash seconds
var _dead_effects: Array = []  # [{pos: Vector2, age: float, lifetime: float, color: Color, owner: int, entity_type: String}]
var _dmg_floats: Array = []

# ─── Hover / interaction state ──────────────────────────────────────────────
var _hovered_entity_id: String = ""
var _hover_check_timer: float = 0.0
var _game_time: float = 0.0
var _prev_attack_targets: Dictionary = {}  # entity_id → previous attack_target_id

# ─── Drag-select ────────────────────────────────────────────────────────────
var _dragging: bool = false
var _drag_start: Vector2 = Vector2.ZERO
var _drag_end: Vector2 = Vector2.ZERO

# ─── Command ping / control group hint state ────────────────────────────────
var _command_pings: Array = []  # [{pos: Vector2, age: float, duration: float, color: Color, type: String}]
var _control_group_hints: Array = []  # [{text: String, age: float, duration: float}]

# ─── Injected references ────────────────────────────────────────────────────
var _camera: Camera2D
var _default_font: Font
var _canvas: CanvasItem  # set during draw_all()

# Entity data (provided each frame)
var _ents: Array = []
var _selected: Dictionary = {}  # id → true
var _entity_cache_by_id: Dictionary = {}

# External data references (set via set_data_refs)
var _player_races: Dictionary = {}  # {"1": "1", "2": "2"}
var _rally_indicators: Dictionary = {}  # {building_id: RallyPointIndicator}
var _selection_node: Node = null  # SelectionManager autoload

# ─── Callable helpers (injected from game_view) ────────────────────────────
var _fn_resolve_visual_id: Callable
var _fn_visual_radius: Callable
var _fn_visual_scale: Callable
var _fn_is_building_entity_visual: Callable
var _fn_screen_to_world: Callable
var _fn_world_to_screen: Callable
var _fn_is_in_fog: Callable
var _fn_get_ent_by_id: Callable
var _fn_get_entity_data: Callable
var _fn_to_f: Callable
var _fn_ent_at_world_pos: Callable

# Map size (needed for fog checks and control group hint positioning)
var _map_w: float = 64.0
var _map_h: float = 64.0

# Fog data (needed for _is_in_fog checks inside draw methods)
var _fog_w: int = 0
var _fog_h: int = 0
var _fog_alpha: PackedFloat32Array = []


# ─── Public API ─────────────────────────────────────────────────────────────

func setup(camera: Camera2D, default_font: Font) -> void:
	_camera = camera
	_default_font = default_font


func set_visual_helpers(
	fn_visual_radius: Callable,
	fn_visual_scale: Callable,
	fn_resolve_visual_id: Callable,
	fn_is_building_entity_visual: Callable,
	fn_screen_to_world: Callable,
	fn_world_to_screen: Callable,
	fn_is_in_fog: Callable,
	fn_get_ent_by_id: Callable,
	fn_get_entity_data: Callable,
	fn_to_f: Callable,
	fn_ent_at_world_pos: Callable
) -> void:
	_fn_visual_radius = fn_visual_radius
	_fn_visual_scale = fn_visual_scale
	_fn_resolve_visual_id = fn_resolve_visual_id
	_fn_is_building_entity_visual = fn_is_building_entity_visual
	_fn_screen_to_world = fn_screen_to_world
	_fn_world_to_screen = fn_world_to_screen
	_fn_is_in_fog = fn_is_in_fog
	_fn_get_ent_by_id = fn_get_ent_by_id
	_fn_get_entity_data = fn_get_entity_data
	_fn_to_f = fn_to_f
	_fn_ent_at_world_pos = fn_ent_at_world_pos


func set_data_refs(
	player_races: Dictionary,
	rally_indicators: Dictionary,
	selection_node: Node
) -> void:
	_player_races = player_races
	_rally_indicators = rally_indicators
	_selection_node = selection_node


func set_map_size(map_w: float, map_h: float) -> void:
	_map_w = map_w
	_map_h = map_h


func set_fog_data(fog_w: int, fog_h: int, fog_alpha: PackedFloat32Array) -> void:
	_fog_w = fog_w
	_fog_h = fog_h
	_fog_alpha = fog_alpha


func provide_entity_data(ents: Array, selected: Dictionary, entity_cache_by_id: Dictionary) -> void:
	_ents = ents
	_selected = selected
	_entity_cache_by_id = entity_cache_by_id


func advance_timers(delta: float) -> void:
	_game_time += delta

	# Decay damage floaters
	for f in _dmg_floats:
		f["age"] = float(f.get("age", 0.0)) + delta
	_dmg_floats = _dmg_floats.filter(func(f): return float(f.get("age", 0.0)) < float(f.get("duration", 1.0)))

	# Decay attack flash timers
	var flash_ids: Array = _attack_flash_timers.keys()
	for eid in flash_ids:
		var remaining: float = float(_attack_flash_timers[eid]) - delta
		if remaining <= 0.0:
			_attack_flash_timers.erase(eid)
		else:
			_attack_flash_timers[eid] = remaining

	# Age and prune death explosion effects
	for effect in _dead_effects:
		effect["age"] = float(effect.get("age", 0.0)) + delta
	_dead_effects = _dead_effects.filter(func(eff): return float(eff.get("age", 0.0)) < float(eff.get("lifetime", DEATH_EFFECT_DURATION)))

	# Age and prune command pings
	for ping in _command_pings:
		ping["age"] = float(ping.get("age", 0.0)) + delta
	_command_pings = _command_pings.filter(func(p): return float(p.get("age", 0.0)) < float(p.get("duration", 0.32)))

	# Age and prune control group hints
	for hint in _control_group_hints:
		hint["age"] = float(hint.get("age", 0.0)) + delta
	_control_group_hints = _control_group_hints.filter(func(h): return float(h.get("age", 0.0)) < float(h.get("duration", 0.5)))

	# Hover detection (throttled)
	_hover_check_timer -= delta
	if _hover_check_timer <= 0.0:
		_hover_check_timer = HOVER_CHECK_INTERVAL
		if _fn_screen_to_world.is_valid() and _fn_ent_at_world_pos.is_valid():
			var mouse_world: Vector2 = _fn_screen_to_world.call(_camera.get_viewport().get_mouse_position())
			var hovered_ent: Dictionary = _fn_ent_at_world_pos.call(mouse_world, SELECT_RADIUS)
			_hovered_entity_id = "" if hovered_ent.is_empty() else str(hovered_ent.get("id", ""))


func draw_all(canvas: CanvasItem) -> void:
	_canvas = canvas
	var co := Vector2.ZERO
	_draw_attack_flashes(co)
	_draw_death_explosions(co)
	_draw_hover_highlight(co)
	_draw_health_bars(co)
	_draw_build_progress_bars(co)
	_draw_production_bars(co)
	_draw_status_icons(co)
	_draw_selection_rings(co)
	_draw_pylon_power_range(co)
	_draw_rally_lines(co)
	_draw_drag_box()
	_draw_damage_floats(co)
	_draw_command_pings(co)
	_draw_control_group_hints(co)
	_draw_game_over_overlay()
	_canvas = null


# ─── Overlay state mutation (called by game_view) ──────────────────────────

func add_attack_flash(entity_id: String) -> void:
	_attack_flash_timers[entity_id] = ATTACK_FLASH_DURATION


func add_death_effect(pos: Vector2, owner: int, type: String, team_color: Color) -> void:
	_dead_effects.append({
		"pos": pos,
		"age": 0.0,
		"lifetime": DEATH_EFFECT_DURATION,
		"color": team_color,
		"owner": owner,
		"entity_type": type,
	})


func add_damage_float(text: String, world_pos: Vector2, owner: int) -> void:
	_dmg_floats.append({
		"text": text,
		"pos": world_pos,
		"owner": owner,
		"age": 0.0,
		"duration": 1.0,
	})


func add_command_ping(pos: Vector2, ping_type: String, duration: float, color: Color) -> void:
	_command_pings.append({
		"pos": pos,
		"age": 0.0,
		"duration": duration,
		"color": color,
		"type": ping_type,
	})
	pings_updated.emit()


func add_ground_ping(world_pos: Vector2) -> void:
	add_command_ping(world_pos, "move", _ground_ping_duration, _ground_ping_color)


func add_attack_ping(world_pos: Vector2) -> void:
	add_command_ping(world_pos, "attack", _attack_ping_duration, _attack_ping_color)


func add_control_group_hint(text: String, duration: float) -> void:
	_control_group_hints.append({
		"text": text,
		"age": 0.0,
		"duration": duration,
	})


func set_drag_state(dragging: bool, start: Vector2, end: Vector2) -> void:
	_dragging = dragging
	_drag_start = start
	_drag_end = end


func clear_all_effects() -> void:
	_attack_flash_timers.clear()
	_dead_effects.clear()
	_dmg_floats.clear()
	_command_pings.clear()
	_control_group_hints.clear()
	_prev_attack_targets.clear()


func set_prev_attack_targets(targets: Dictionary) -> void:
	_prev_attack_targets = targets


func update_ping_config(ground_ping_duration: float, ground_ping_color: Color,
						attack_ping_duration: float, attack_ping_color: Color,
						invalid_ping_duration: float, invalid_ping_color: Color,
						assign_flash_duration: float, empty_group_hint_duration: float) -> void:
	_ground_ping_duration = ground_ping_duration
	_ground_ping_color = ground_ping_color
	_attack_ping_duration = attack_ping_duration
	_attack_ping_color = attack_ping_color
	_invalid_ping_duration = invalid_ping_duration
	_invalid_ping_color = invalid_ping_color
	_assign_flash_duration = assign_flash_duration
	_empty_group_hint_duration = empty_group_hint_duration


# ─── Draw Methods ───────────────────────────────────────────────────────────

func _draw_attack_flashes(_co: Vector2) -> void:
	## Draw white overlay on entities that just attacked (attack flash).
	## game_view z_index=5 renders ABOVE sprite_container z_index=1,
	## so this overlay appears on top of entity sprites.
	for eid in _attack_flash_timers:
		var remaining: float = float(_attack_flash_timers[eid])
		var flash_alpha: float = clampf(remaining / ATTACK_FLASH_DURATION, 0.0, 1.0)
		var e: Dictionary = _fn_get_entity_data.call(str(eid))
		if e.is_empty():
			continue
		if int(e.owner) != 1 and _fn_is_in_fog.call(e):
			continue
		var pos := Vector2(float(e.get("px", 0.0)), float(e.get("py", 0.0)))
		var radius: float = _fn_visual_radius.call(e)
		# White overlay circle that fades out
		var flash_color: Color = Color(1.0, 1.0, 1.0, flash_alpha * 0.75)
		_canvas.draw_circle(pos, radius * 1.1, flash_color)
		# Bright white outline ring
		var ring_color: Color = Color(1.0, 1.0, 1.0, flash_alpha * 0.9)
		_canvas.draw_arc(pos, radius * 1.15, 0.0, TAU, 20, ring_color, 0.06, true)


func _draw_death_explosions(_co: Vector2) -> void:
	## Draw expanding + fading circle explosion at entity death positions.
	## Duration: ~0.5 seconds (DEATH_EFFECT_DURATION).
	for effect in _dead_effects:
		var lifetime: float = maxf(float(effect.get("lifetime", DEATH_EFFECT_DURATION)), 0.01)
		var age: float = float(effect.get("age", 0.0))
		var t := clampf(age / lifetime, 0.0, 1.0)
		var alpha: float = 1.0 - t
		var pos: Vector2 = effect.get("pos", Vector2.ZERO)
		var base_color: Color = effect.get("color", Color.WHITE)
		var entity_type: String = str(effect.get("entity_type", ""))
		# Buildings have larger explosions
		var is_building: bool = entity_type == "building"
		var base_radius: float = 1.2 if is_building else 0.6
		var max_radius: float = 3.0 if is_building else 1.5
		var radius := lerpf(base_radius, max_radius, t)
		# Outer expanding ring (team color, fading)
		var ring_color: Color = base_color
		ring_color.a = alpha * 0.8
		_canvas.draw_arc(pos, radius, 0.0, TAU, 24, ring_color, 0.08 if not is_building else 0.14, true)
		# Inner glow fill (fading faster)
		var fill_color: Color = Color(1.0, 0.85, 0.6, alpha * 0.35)
		_canvas.draw_circle(pos, radius * 0.6, fill_color)
		# Secondary ring for buildings
		if is_building:
			var ring2_color: Color = Color(1.0, 0.4, 0.1, alpha * 0.5)
			_canvas.draw_arc(pos, radius * 0.75, 0.0, TAU, 18, ring2_color, 0.10, true)


func _draw_hover_highlight(_co: Vector2) -> void:
	## Draw a bright outline on the entity currently under the mouse cursor.
	if _hovered_entity_id == "":
		return
	var e: Dictionary = _fn_get_entity_data.call(_hovered_entity_id)
	if e.is_empty():
		return
	if int(e.owner) != 1 and _fn_is_in_fog.call(e):
		return
	var pos := Vector2(float(e.get("px", 0.0)), float(e.get("py", 0.0)))
	var radius: float = _fn_visual_radius.call(e)
	# Bright white ring for hover feedback
	var hover_color: Color = Color(1.0, 1.0, 1.0, 0.65)
	_canvas.draw_arc(pos, radius * 1.08, 0.0, TAU, 24, hover_color, 0.055, true)
	# Subtle glow fill
	var glow_color: Color = Color(1.0, 1.0, 1.0, 0.08)
	_canvas.draw_circle(pos, radius * 1.05, glow_color)


func _draw_damage_floats(_co: Vector2) -> void:
	for f in _dmg_floats:
		var age: float = float(f.get("age", 0.0))
		var duration: float = float(f.get("duration", 1.0))
		var alpha: float = clampf(1.0 - age / duration, 0.0, 1.0)
		var base_pos: Vector2 = Vector2(f.get("pos", Vector2.ZERO))
		var pos := base_pos + Vector2(0.0, -age * 0.5)
		var text: String = str(f.get("text", ""))
		var owner: int = int(f.get("owner", 0))
		var team_col := _team_color(owner)
		var color := Color(team_col.r, team_col.g, team_col.b, alpha)
		_canvas.draw_string(_default_font, pos, text, HORIZONTAL_ALIGNMENT_CENTER, -1, 8, color)


func _draw_health_bars(co: Vector2) -> void:
	for e in _ents:
		if int(e.max_health) <= 0 or e.type == "resource":
			continue
		if int(e.owner) != 1 and _fn_is_in_fog.call(e):
			continue
		if not _selected.has(str(e.id)) and float(e.health) >= float(e.max_health):
			continue
		var pos := Vector2(float(e.px), float(e.py))
		var radius: float = _fn_visual_radius.call(e)
		var bar_w := clampf(radius * 1.45, 0.55, 2.8)
		var bar_h := 0.15
		var bar_y := pos.y - radius - 0.28
		var frac: float = float(e.health) / float(e.max_health)
		_canvas.draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.3, 0.3, 0.3, 0.8), true)
		var hp_color := Color.GREEN if frac > 0.6 else Color.YELLOW if frac > 0.3 else Color.RED
		_canvas.draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * frac, bar_h), hp_color, true)


# ─── Build Progress Bar ────────────────────────────────────────────────────
func _draw_build_progress_bars(_co: Vector2) -> void:
	## Draw yellow/orange progress bar above buildings that are under construction.
	## Positioned above the health bar for constructing buildings.
	for e in _ents:
		if e.type != "building":
			continue
		var is_constructing: bool = bool(e.get("is_constructing", false))
		if not is_constructing:
			continue
		if int(e.owner) != 1 and _fn_is_in_fog.call(e):
			continue
		var pos := Vector2(float(e.px), float(e.py))
		var radius: float = _fn_visual_radius.call(e)
		var bar_w := clampf(radius * 1.45, 0.55, 2.8)
		var bar_h := 0.12
		# Position above the health bar (which is at radius + 0.28 above center)
		var bar_y := pos.y - radius - 0.28 - bar_h - 0.08
		# Build progress: 0.0 to 1.0 (if unavailable, show 0)
		var build_progress: float = clampf(_fn_to_f.call(e.get("build_progress"), 0.0), 0.0, 1.0)
		# Background bar (dark)
		_canvas.draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.25, 0.2, 0.1, 0.8), true)
		# Progress fill — yellow to orange gradient based on progress
		var fill_color: Color = Color(1.0, 0.85, 0.15, 0.9).lerp(Color(1.0, 0.55, 0.1, 0.9), build_progress)
		_canvas.draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * build_progress, bar_h), fill_color, true)
		# Border outline
		_canvas.draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.6, 0.5, 0.3, 0.5), false, 0.03)


# ─── Team Color Helper ──────────────────────────────────────────────────────
func _team_color(owner: int) -> Color:
	## Return a team color for the given owner ID.
	match owner:
		1: return Color(0.2, 0.8, 0.3)   # green (player)
		2: return Color(0.9, 0.2, 0.2)   # red (enemy AI)
		3: return Color(0.9, 0.8, 0.2)   # yellow (Protoss)
		_: return Color(0.6, 0.6, 0.6)   # gray (neutral)


# ─── Unit Letter Helper ─────────────────────────────────────────────────────
func _unit_letter(unit_type: String) -> String:
	match unit_type.to_lower():
		"marine": return "M"
		"firebat": return "F"
		"ghost": return "G"
		"medic": return "D"
		"worker", "scv": return "W"
		"vulture": return "V"
		"tank", "siege_tank": return "T"
		"goliath": return "L"
		"wraith": return "R"
		"dropship": return "P"
		"vessel", "science_vessel": return "S"
		"zergling": return "Z"
		"hydralisk": return "H"
		"ultralisk": return "U"
		"overlord": return "O"
		"queen": return "Q"
		"mutalisk": return "Mu"
		_: return unit_type.left(1).to_upper()


# ─── Phase B1: Production Queue Visualization ────────────────────────────────
func _draw_production_bars(_co: Vector2) -> void:
	for e in _ents:
		if e.type != "building":
			continue
		var queue: Array = e.get("production_queue", [])
		if queue.is_empty():
			continue
		if int(e.owner) != 1 and _fn_is_in_fog.call(e):
			continue
		var pos := Vector2(float(e.px), float(e.py))
		var radius: float = _fn_visual_radius.call(e)
		var bar_w := radius * 1.4
		var bar_h := 0.12
		var base_y := pos.y - radius - 0.48
		var timers: Array = e.get("production_timers", [])
		for i in range(queue.size()):
			var bar_y := base_y - i * (bar_h + 0.04)
			var unit_type: String = str(queue[i])
			var letter := _unit_letter(unit_type)
			# Background bar
			_canvas.draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.2, 0.2, 0.2, 0.8), true)
			if i == 0 and timers.size() > 0:
				# First item: green progress bar
				var timer_val: float = _fn_to_f.call(timers[0], 0.0)
				var max_timer: float = 20.0  # approximate if unknown
				var progress: float = clampf(1.0 - timer_val / max_timer, 0.0, 1.0)
				_canvas.draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * progress, bar_h), Color(0.2, 0.85, 0.2, 0.9), true)
			# Unit type letter above the bar
			var letter_y := bar_y - 0.14
			_canvas.draw_string(_default_font, Vector2(pos.x - 0.1, letter_y), letter, HORIZONTAL_ALIGNMENT_CENTER, -1, 8, Color(0.9, 0.9, 0.9, 0.9))


# ─── Phase B5: Unit Status Icons ────────────────────────────────────────────
func _draw_status_icons(_co: Vector2) -> void:
	for e in _ents:
		if e.type == "resource" or e.type == "building":
			continue
		if int(e.owner) != 1 and _fn_is_in_fog.call(e):
			continue
		var pos := Vector2(float(e.px), float(e.py))
		var radius: float = _fn_visual_radius.call(e)
		var icon_y := pos.y - radius - 0.50
		var icon_x := pos.x
		var has_target: bool = str(e.get("attack_target_id", "")) != ""
		var is_idle: bool = bool(e.get("is_idle", true))
		var speed: float = _fn_to_f.call(e.get("speed", 0.0), 0.0)
		var is_moving: bool = not is_idle and not has_target and speed > 0.0
		var carry_amount: float = _fn_to_f.call(e.get("carry_amount", 0.0), 0.0)
		var carry_cap: float = _fn_to_f.call(e.get("carry_cap", 0.0), 0.0)
		var is_gathering: bool = carry_amount > 0 and carry_cap > 0
		if has_target:
			# Attacking: small red triangle (sword icon)
			var s := 0.12
			var pts := PackedVector2Array([
				Vector2(icon_x, icon_y + s),
				Vector2(icon_x - s, icon_y - s * 0.6),
				Vector2(icon_x + s, icon_y - s * 0.6),
			])
			_canvas.draw_colored_polygon(pts, Color(1.0, 0.2, 0.2, 0.9))
		elif is_gathering:
			# Gathering: small yellow diamond (crystal icon)
			var s := 0.10
			var pts := PackedVector2Array([
				Vector2(icon_x, icon_y + s),
				Vector2(icon_x - s, icon_y),
				Vector2(icon_x, icon_y - s),
				Vector2(icon_x + s, icon_y),
			])
			_canvas.draw_colored_polygon(pts, Color(1.0, 0.9, 0.2, 0.9))
		elif is_moving:
			# Moving: small blue chevron
			var s := 0.12
			var pts := PackedVector2Array([
				Vector2(icon_x - s, icon_y + s * 0.5),
				Vector2(icon_x, icon_y - s * 0.5),
				Vector2(icon_x + s, icon_y + s * 0.5),
			])
			_canvas.draw_colored_polygon(pts, Color(0.3, 0.6, 1.0, 0.9))
		elif is_idle:
			# Idle: small white dot
			_canvas.draw_circle(Vector2(icon_x, icon_y), 0.08, Color(1.0, 1.0, 1.0, 0.6))


func _draw_selection_rings(_co: Vector2) -> void:
	## Selected units: green ring with breathing (sinusoidal) glow pulse.
	var breathe_phase: float = sin(_game_time * SELECTION_BREATHE_SPEED)
	var breathe_alpha: float = lerpf(SELECTION_BREATHE_MIN, SELECTION_BREATHE_MAX, 0.5 + 0.5 * breathe_phase)
	for uid in _selected:
		var e: Dictionary = _fn_get_ent_by_id.call(uid)
		if e.is_empty():
			continue
		var pos := Vector2(float(e.px), float(e.py))
		var radius: float = _fn_visual_radius.call(e)
		# Main selection ring with breathing alpha
		var ring_color: Color = Color(0.2, 1.0, 0.2, breathe_alpha)
		_canvas.draw_arc(pos, radius, 0.0, TAU, 24, ring_color, 0.055, true)
		# Outer glow ring (subtler, also breathing but offset phase)
		var glow_phase: float = sin(_game_time * SELECTION_BREATHE_SPEED + PI * 0.5)
		var glow_alpha: float = lerpf(0.0, 0.25, 0.5 + 0.5 * glow_phase)
		var glow_color: Color = Color(0.4, 1.0, 0.4, glow_alpha)
		_canvas.draw_arc(pos, radius * 1.12, 0.0, TAU, 24, glow_color, 0.04, true)


# ─── Pylon Power Range Visualization ───────────────────────────────────────
func _draw_pylon_power_range(_co: Vector2) -> void:
	"""Render semi-transparent blue circles for Pylon power range.
	Only drawn for player 1's Pylons when player 1's race is Protoss (race ID '3').
	Power radius: PYLON_POWER_RADIUS (8 game-coordinate cells)."""
	# Only render if player 1's race is Protoss
	var p1_race: String = str(_player_races.get("1", "1"))
	if p1_race != "3":
		return

	# Semi-transparent blue fill (SC1-style Pylon aura)
	var fill_color: Color = Color(0.2, 0.4, 1.0, 0.10)
	# Slightly more opaque blue border ring
	var ring_color: Color = Color(0.3, 0.5, 1.0, 0.35)
	var ring_width: float = 0.08

	for e in _ents:
		if int(e.owner) != 1:
			continue
		if e.type != "building":
			continue
		# Pylon is building_type "supply_depot" with unit_type "Pylon" for Protoss
		var btype: String = str(e.get("building_type", ""))
		var utype: String = str(e.get("unit_type", ""))
		if btype != "supply_depot" and utype != "Pylon":
			continue
		# If unit_type is present but not "Pylon", it's a Terran/Zerg supply depot — skip
		if utype != "" and utype != "Pylon":
			continue

		var pos := Vector2(float(e.px), float(e.py))
		# Filled semi-transparent blue circle
		_canvas.draw_circle(pos, PYLON_POWER_RADIUS, fill_color)
		# Blue ring outline
		_canvas.draw_arc(pos, PYLON_POWER_RADIUS, 0.0, TAU, 64, ring_color, ring_width, true)


# ─── Sprint 4: Draw Rally Point Lines ──────────────────────────────────────
func _draw_rally_lines(co: Vector2) -> void:
	for bid in _rally_indicators:
		var indicator = _rally_indicators[bid]
		if not indicator.has_rally():
			continue
		# Only draw if building is selected
		if _selection_node and not _selection_node.is_selected(bid):
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
				_canvas.draw_line(start, end, Color(0.2, 1.0, 0.2, 0.7), 0.06, true)
			drawn += seg_len
			is_dash = not is_dash

		# Flag at rally point — compact tile-space flag
		var pole_top: Vector2 = rpos - Vector2(0, 0.4)
		_canvas.draw_line(rpos, pole_top, Color(1.0, 0.9, 0.2, 0.8), 0.04, true)
		var flag_pts := PackedVector2Array([
			pole_top,
			pole_top + Vector2(0.2, 0.07),
			pole_top + Vector2(0, 0.14)
		])
		_canvas.draw_colored_polygon(flag_pts, Color(1.0, 0.9, 0.2, 0.7))


func _draw_drag_box() -> void:
	if not _dragging:
		return
	if _drag_start.distance_to(_drag_end) < 5.0:
		return
	# Convert screen-space drag coords to world space for drawing
	var ws: Vector2 = _fn_screen_to_world.call(_drag_start)
	var we: Vector2 = _fn_screen_to_world.call(_drag_end)
	var rect := Rect2(ws, we - ws).abs()
	_canvas.draw_rect(rect, Color(0.3, 1.0, 0.3, 0.15), true)
	_canvas.draw_rect(rect, Color(0.3, 1.0, 0.3, 0.7), false, 0.06)


func _draw_game_over_overlay() -> void:
	# Game over overlay is now handled by _victory_screen in CanvasLayer
	pass


func _draw_command_pings(_co: Vector2) -> void:
	for ping in _command_pings:
		var age: float = float(ping.get("age", 0.0))
		var duration: float = float(ping.get("duration", 0.32))
		var progress: float = clampf(age / duration, 0.0, 1.0)
		var alpha: float = 1.0 - progress
		var base_color: Color = Color(ping.get("color", _ground_ping_color))
		var pos: Vector2 = Vector2(ping.get("pos", Vector2.ZERO))
		var ping_type: String = str(ping.get("type", "move"))

		# Expanding ring
		var max_radius: float = 0.6 if ping_type != "invalid" else 0.35
		var radius: float = progress * max_radius
		var ring_color: Color = Color(base_color.r, base_color.g, base_color.b, alpha * 0.9)
		_canvas.draw_arc(pos, radius, 0.0, TAU, 24, ring_color, 0.06, true)

		# Center dot (only for first 40% of duration)
		if progress < 0.4:
			var dot_alpha: float = alpha * (1.0 - progress / 0.4)
			var dot_color: Color = Color(base_color.r, base_color.g, base_color.b, dot_alpha)
			_canvas.draw_circle(pos, 0.1, dot_color)


func _draw_control_group_hints(_co: Vector2) -> void:
	for hint in _control_group_hints:
		var age: float = float(hint.get("age", 0.0))
		var duration: float = float(hint.get("duration", 0.5))
		var progress: float = clampf(age / duration, 0.0, 1.0)
		var alpha: float = 1.0 - progress
		var text: String = str(hint.get("text", ""))

		var screen_center := _camera.get_viewport().get_visible_rect().size / 2.0
		var hint_pos := _fn_screen_to_world.call(screen_center) + Vector2(0, _map_h * 0.4)
		var font_size: int = 16
		var font: Font = _default_font if _default_font else ThemeDB.fallback_font
		var text_size: Vector2 = font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size)
		var bg_rect := Rect2(hint_pos - text_size / 2.0 - Vector2(6, 3), text_size + Vector2(12, 6))

		var bg_alpha: float = alpha * 0.6
		_canvas.draw_rect(bg_rect, Color(0.0, 0.0, 0.0, bg_alpha), true)
		_canvas.draw_rect(bg_rect, Color(1.0, 1.0, 1.0, alpha * 0.3), false, 1.0)
		_canvas.draw_string(font, hint_pos - text_size / 2.0 + Vector2(0, font_size * 0.35), text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color(1, 1, 1, alpha))
