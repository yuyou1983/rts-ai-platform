extends Node2D

## Visual feedback system — floating damage numbers, kill toasts,
## building ghost preview, rally lines, selection icons, minimap pings.

var _floating_texts: Array[Dictionary] = []
var _attack_pings: Array[Dictionary] = []
var _ghost_building: Dictionary = {}
var _rally_lines: Array[Dictionary] = []

const FLOAT_SPEED: float = 40.0
const FLOAT_LIFETIME: float = 1.2
const PING_LIFETIME: float = 1.5
const PING_RADIUS: float = 8.0


func _process(delta: float) -> void:
	# Update floating damage numbers
	var i: int = _floating_texts.size() - 1
	while i >= 0:
		var ft: Dictionary = _floating_texts[i]
		ft.age += delta
		ft.pos_y -= FLOAT_SPEED * delta
		if ft.age >= FLOAT_LIFETIME:
			_floating_texts.remove_at(i)
		i -= 1

	# Update attack pings
	i = _attack_pings.size() - 1
	while i >= 0:
		_attack_pings[i].age += delta
		if _attack_pings[i].age >= PING_LIFETIME:
			_attack_pings.remove_at(i)
		i -= 1

	queue_redraw()


func _draw() -> void:
	var default_font: Font = ThemeDB.fallback_font
	var default_font_size: int = ThemeDB.fallback_font_size

	# Draw floating damage numbers
	for ft in _floating_texts:
		var alpha: float = 1.0 - (ft.age / FLOAT_LIFETIME)
		var color: Color = ft.get("color", Color.WHITE)
		color.a = alpha
		var text: String = ft.get("text", "")
		var pos: Vector2 = Vector2(ft.pos_x, ft.pos_y)
		draw_string(default_font, pos, text, HORIZONTAL_ALIGNMENT_CENTER, -1, default_font_size, color)

	# Draw attack pings
	for ping in _attack_pings:
		var alpha: float = 1.0 - (ping.age / PING_LIFETIME)
		var color: Color = Color.RED
		color.a = alpha * 0.8
		draw_circle(Vector2(ping.pos_x, ping.pos_y), PING_RADIUS * (1.0 - alpha * 0.5), color)

	# Draw building placement ghost
	if _ghost_building:
		var gx: float = _ghost_building.get("pos_x", 0.0)
		var gy: float = _ghost_building.get("pos_y", 0.0)
		var ghost_color: Color = Color(0.3, 1.0, 0.3, 0.4)
		# TILE_SIZE=1: building occupies ~1 world unit, scale to screen pixels
		var bsize: float = 32.0  # pixels on screen for a single tile building
		draw_rect(Rect2(gx - bsize / 2, gy - bsize / 2, bsize, bsize), ghost_color)

	# Draw rally lines
	for rl in _rally_lines:
		var line_color: Color = Color(0.0, 1.0, 1.0, 0.5)
		var dash_len: float = 4.0
		var sx: float = rl.get("start_x", 0.0)
		var sy: float = rl.get("start_y", 0.0)
		var ex: float = rl.get("end_x", 0.0)
		var ey: float = rl.get("end_y", 0.0)
		var dx: float = ex - sx
		var dy: float = ey - sy
		var dist: float = sqrt(dx * dx + dy * dy)
		if dist < 1.0:
			continue
		var nx: float = dx / dist
		var ny: float = dy / dist
		var t: float = 0.0
		while t < dist:
			var seg_end: float = minf(t + dash_len, dist)
			draw_line(
				Vector2(sx + nx * t, sy + ny * t),
				Vector2(sx + nx * seg_end, sy + ny * seg_end),
				line_color, 1.5
			)
			t += dash_len * 2.0
		# Draw flag at end
		draw_circle(Vector2(ex, ey), 3.0, line_color)


# ─── Public API ───────────────────────────────────────────────

func add_damage_number(world_x: float, world_y: float, amount: int) -> void:
	_floating_texts.append({
		"pos_x": world_x,
		"pos_y": world_y,
		"text": str(amount),
		"age": 0.0,
		"color": Color.YELLOW if amount > 0 else Color.RED,
	})


func add_kill_toast(unit_name: String) -> void:
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	_floating_texts.append({
		"pos_x": vp_size.x / 2.0,
		"pos_y": 100.0,
		"text": "Killed: " + unit_name,
		"age": 0.0,
		"color": Color.ORANGE,
	})


func add_attack_ping(world_x: float, world_y: float) -> void:
	_attack_pings.append({"pos_x": world_x, "pos_y": world_y, "age": 0.0})


func set_ghost_building(pos_x: float, pos_y: float, btype: String = "") -> void:
	_ghost_building = {"pos_x": pos_x, "pos_y": pos_y, "type": btype}


func clear_ghost_building() -> void:
	_ghost_building = {}


func set_rally_line(start_x: float, start_y: float, end_x: float, end_y: float) -> void:
	_rally_lines = [{"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y}]


func clear_rally_lines() -> void:
	_rally_lines.clear()