class_name InputFeedbackController
extends Node2D

## Input Feedback Controller — handles local input feedback visuals only.
## Ground pings, attack pings, invalid pings, and control group flashes.
## All runtime timing data is loaded from control_feel_config.json.
##
## Uses an internal _canvas (Node2D) for all drawing — never draws directly on game_view.

# ─── Config ─────────────────────────────────────────────────────────────────
var _feedback_config: Dictionary = {}

# ─── Ping timing (seconds) ─────────────────────────────────────────────────
var right_click_ping_seconds: float = 0.22
var attack_ping_seconds: float = 0.28
var invalid_ping_seconds: float = 0.16
var control_group_assign_flash_seconds: float = 0.5
var control_group_empty_hint_seconds: float = 0.8

# ─── Ping colors ────────────────────────────────────────────────────────────
var ground_ping_color: Color = Color(0.267, 1.0, 0.533)  # #44ff88
var attack_ping_color: Color = Color(1.0, 0.267, 0.267)  # #ff4444
var invalid_ping_color: Color = Color(0.667, 0.4, 0.4)   # #aa6666

# ─── Active pings ───────────────────────────────────────────────────────────
var _active_pings: Array[Dictionary] = []  # [{pos, age, duration, color, type}]

# ─── Control group hints ────────────────────────────────────────────────────
var _active_hints: Array[Dictionary] = []  # [{text, age, duration}]

# ─── Canvas for drawing ─────────────────────────────────────────────────────
var _canvas: Node2D = null

signal pings_updated()


func _ready() -> void:
	_feedback_config = _load_feel_config()
	_apply_config()
	_canvas = Node2D.new()
	_canvas.name = "InputFeedbackCanvas"
	add_child(_canvas)


func _load_feel_config() -> Dictionary:
	var path: String = "res://resources/feel/control_feel_config.json"
	if not ResourceLoader.exists(path):
		return {}
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var text: String = f.get_as_text()
	f.close()
	var json: JSON = JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		push_warning("JSON parse error in control_feel_config.json: " + json.get_error_message())
		return {}
	return json.data


func _apply_config() -> void:
	if _feedback_config.has("command_feedback"):
		var cf: Dictionary = _feedback_config["command_feedback"]
		right_click_ping_seconds = float(cf.get("ground_ping_duration", right_click_ping_seconds))
		attack_ping_seconds = float(cf.get("attack_ping_duration", attack_ping_seconds))
		invalid_ping_seconds = float(cf.get("invalid_ping_duration", invalid_ping_seconds))
		if cf.has("ground_ping_color"):
			ground_ping_color = Color.from_string(str(cf["ground_ping_color"]), ground_ping_color)
		if cf.has("attack_ping_color"):
			attack_ping_color = Color.from_string(str(cf["attack_ping_color"]), attack_ping_color)
		if cf.has("invalid_ping_color"):
			invalid_ping_color = Color.from_string(str(cf["invalid_ping_color"]), invalid_ping_color)

	if _feedback_config.has("control_group_feedback"):
		var cg: Dictionary = _feedback_config["control_group_feedback"]
		control_group_assign_flash_seconds = float(cg.get("assign_flash_duration", control_group_assign_flash_seconds))
		control_group_empty_hint_seconds = float(cg.get("empty_group_hint_duration", control_group_empty_hint_seconds))


# ─── Public API ──────────────────────────────────────────────────────────────

func show_ground_ping(world_pos: Vector2) -> void:
	_active_pings.append({
		"pos": world_pos,
		"age": 0.0,
		"duration": right_click_ping_seconds,
		"color": ground_ping_color,
		"type": "move",
	})
	pings_updated.emit()


func show_attack_ping(world_pos: Vector2) -> void:
	_active_pings.append({
		"pos": world_pos,
		"age": 0.0,
		"duration": attack_ping_seconds,
		"color": attack_ping_color,
		"type": "attack",
	})
	pings_updated.emit()


func show_attack_move_ping(world_pos: Vector2) -> void:
	_active_pings.append({
		"pos": world_pos,
		"age": 0.0,
		"duration": attack_ping_seconds,
		"color": attack_ping_color,
		"type": "attack_move",
	})
	pings_updated.emit()


func show_invalid_ping(world_pos: Vector2) -> void:
	_active_pings.append({
		"pos": world_pos,
		"age": 0.0,
		"duration": invalid_ping_seconds,
		"color": invalid_ping_color,
		"type": "invalid",
	})
	pings_updated.emit()


func show_control_group_flash(group_id: int, assigned: bool) -> void:
	var text: String = ""
	if assigned:
		text = "Ctrl+%d → Group %d" % [group_id, group_id]
	else:
		text = "Group %d (empty)" % group_id
	var duration: float = control_group_assign_flash_seconds if assigned else control_group_empty_hint_seconds
	_active_hints.append({
		"text": text,
		"age": 0.0,
		"duration": duration,
	})
	pings_updated.emit()


# ─── Per-frame update (called by game_view) ─────────────────────────────────

func advance_timers(delta: float) -> void:
	# Age and prune pings
	for ping in _active_pings:
		ping["age"] = float(ping.get("age", 0.0)) + delta
	_active_pings = _active_pings.filter(func(p): return float(p.get("age", 0.0)) < float(p.get("duration", 0.32)))

	# Age and prune hints
	for hint in _active_hints:
		hint["age"] = float(hint.get("age", 0.0)) + delta
	_active_hints = _active_hints.filter(func(h): return float(h.get("age", 0.0)) < float(h.get("duration", 0.5)))


func draw_all(canvas: CanvasItem) -> void:
	_draw_pings(canvas)
	_draw_hints(canvas)


func _draw_pings(canvas: CanvasItem) -> void:
	for ping in _active_pings:
		var age: float = float(ping.get("age", 0.0))
		var duration: float = maxf(float(ping.get("duration", 0.22)), 0.01)
		var t := clampf(age / duration, 0.0, 1.0)
		var alpha: float = 1.0 - t
		var pos: Vector2 = ping.get("pos", Vector2.ZERO)
		var base_color: Color = ping.get("color", Color.WHITE)
		var ring_color: Color = Color(base_color.r, base_color.g, base_color.b, alpha * 0.85)
		# Expanding ring
		var radius := lerpf(0.3, 1.2, t)
		canvas.draw_arc(pos, radius, 0.0, TAU, 20, ring_color, 0.06, true)
		# Inner glow
		var fill_color: Color = Color(base_color.r, base_color.g, base_color.b, alpha * 0.25)
		canvas.draw_circle(pos, radius * 0.4, fill_color)
		if str(ping.get("type", "")) == "attack_move":
			var arm: float = radius * 0.65
			canvas.draw_line(pos + Vector2(-arm, 0.0), pos + Vector2(arm, 0.0), ring_color, 0.08, true)
			canvas.draw_line(pos + Vector2(0.0, -arm), pos + Vector2(0.0, arm), ring_color, 0.08, true)


func _draw_hints(canvas: CanvasItem) -> void:
	# Use the theme fallback font for control group hints
	var font: Font = ThemeDB.fallback_font
	for hint in _active_hints:
		var age: float = float(hint.get("age", 0.0))
		var duration: float = maxf(float(hint.get("duration", 0.5)), 0.01)
		var alpha: float = clampf(1.0 - age / duration, 0.0, 1.0)
		var text: String = str(hint.get("text", ""))
		var pos := Vector2(0.0, -0.5 - age * 0.3)  # float upward
		var color := Color(0.85, 0.92, 1.0, alpha)
		canvas.draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_CENTER, -1, 10, color)


func clear_all() -> void:
	_active_pings.clear()
	_active_hints.clear()
