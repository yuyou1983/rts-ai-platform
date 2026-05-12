class_name RallyPointIndicator
extends Node2D

## Visual indicator for building rally points.
## Shows a dashed line from building to rally point, and a flag at the target.
## Set rally point with right-click while building is selected.

# ── Config ───────────────────────────────────────────────────────────────────
const DASH_LENGTH := 8.0
const DASH_GAP := 6.0
const FLAG_SIZE := 10.0
const LINE_COLOR := Color(0.2, 1.0, 0.2, 0.7)
const FLAG_COLOR := Color(1.0, 0.9, 0.2, 0.8)

# ── State ─────────────────────────────────────────────────────────────────────
var _building_pos: Vector2 = Vector2.ZERO
var _rally_pos: Vector2 = Vector2.ZERO
var _has_rally: bool = false
var _visible_flag: bool = true

# ── Public API ───────────────────────────────────────────────────────────────

func set_building_position(pos: Vector2) -> void:
	_building_pos = pos
	if _has_rally:
		queue_redraw()

func set_rally_point(pos: Vector2) -> void:
	_rally_pos = pos
	_has_rally = true
	queue_redraw()

func clear_rally_point() -> void:
	_has_rally = false
	queue_redraw()

func has_rally() -> bool:
	return _has_rally

func get_rally_point() -> Vector2:
	return _rally_pos

func show_indicator() -> void:
	_visible_flag = true
	queue_redraw()

func hide_indicator() -> void:
	_visible_flag = false
	queue_redraw()

# ── Drawing ──────────────────────────────────────────────────────────────────

func _draw() -> void:
	if not _has_rally or not _visible_flag:
		return

	# Draw dashed line from building to rally point
	var direction := _rally_pos - _building_pos
	var length := direction.length()
	if length < 1.0:
		return

	var dir_norm := direction / length
	var drawn: float = 0.0
	var is_dash: bool = true

	while drawn < length:
		var seg_len := DASH_LENGTH if is_dash else DASH_GAP
		var remaining := length - drawn
		seg_len = minf(seg_len, remaining)

		if is_dash:
			var start := _building_pos + dir_norm * drawn
			var end := _building_pos + dir_norm * (drawn + seg_len)
			draw_line(start, end, LINE_COLOR, 2.0, true)

		drawn += seg_len
		is_dash = not is_dash

	# Draw flag at rally point
	_draw_flag(_rally_pos)

func _draw_flag(pos: Vector2) -> void:
	# Pole
	var pole_top := pos - Vector2(0, FLAG_SIZE * 2)
	draw_line(pos, pole_top, FLAG_COLOR, 2.0, true)

	# Flag triangle
	var pts := PackedVector2Array([
		pole_top,
		pole_top + Vector2(FLAG_SIZE, FLAG_SIZE * 0.3),
		pole_top + Vector2(0, FLAG_SIZE * 0.6)
	])
	draw_colored_polygon(pts, FLAG_COLOR)

	# Base dot
	draw_circle(pos, 3.0, FLAG_COLOR)