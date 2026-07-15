class_name VisualCalibrationOverlay
extends Node2D

## Visual Calibration Overlay — debug overlay showing sprite bounds, footprint rect,
## selection radius, pivot cross, and health bar anchor.
##
## Designed for Test Mode / debug use only. Uses low-contrast debug colors so
## it doesn't interfere with normal gameplay readability.
##
## Usage:
##   var overlay := VisualCalibrationOverlay.new()
##   add_child(overlay)
##   overlay.setup(_default_font, _fn_visual_scale, _fn_visual_radius, _presentation_manifest)
##   overlay.active = true   # or bind to a toggle button

# ─── Low-contrast debug colors ──────────────────────────────────────────────
const COL_BOUNDS: Color       = Color(0.6, 0.4, 0.3, 0.35)   # sprite bounds outline
const COL_FOOTPRINT: Color    = Color(0.3, 0.6, 0.5, 0.30)   # footprint fill
const COL_FOOTPRINT_EDGE: Color = Color(0.3, 0.6, 0.5, 0.55) # footprint outline
const COL_RADIUS: Color       = Color(1.0, 1.0, 0.3, 0.40)   # selection radius ring
const COL_PIVOT: Color        = Color(1.0, 0.5, 0.2, 0.60)   # pivot cross
const COL_HBAR_ANCHOR: Color  = Color(0.4, 0.7, 1.0, 0.55)   # health bar anchor
const PIVOT_SIZE: float       = 0.5       # half-size of pivot cross
const CROSS_THICK: float      = 0.03     # thickness of pivot cross lines
const HBAR_DOT_R: float       = 0.10     # radius of health bar anchor dot

# ─── State ──────────────────────────────────────────────────────────────────
var _active: bool = false
var _font: Font = null
var _fn_visual_scale: Callable
var _fn_visual_radius: Callable
var _manifest: Dictionary = {}   # loaded presentation_manifest

# ─── References ────────────────────────────────────────────────────────────
var _canvas: CanvasItem = null  # set during draw_to()
var _ents: Array = []
var _selected: Dictionary = {}

# ─── Public API ─────────────────────────────────────────────────────────────

var active: bool:
	get:
		return _active
	set(value):
		_active = value

func setup(font: Font, fn_visual_scale: Callable, fn_visual_radius: Callable,
		manifest: Dictionary = {}) -> void:
	_font = font
	_fn_visual_scale = fn_visual_scale
	_fn_visual_radius = fn_visual_radius
	_manifest = manifest

func provide_entity_data(ents: Array, selected: Dictionary) -> void:
	_ents = ents
	_selected = selected

## Called by game_view's _draw() — draws all calibration marks on the canvas.
func draw_to(canvas: CanvasItem) -> void:
	if not _active:
		return
	_canvas = canvas
	for e in _ents:
		if int(e.owner) != 1 and not _selected.has(str(e.id)):
			continue  # only draw for player's visible entities
		_draw_entity_cal(e)
	_canvas = null

# ─── Private draw helpers ──────────────────────────────────────────────────

func _draw_entity_cal(e: Dictionary) -> void:
	var pos := Vector2(float(e.px), float(e.py))
	var render_scale: float = _fn_visual_scale.call(e)
	var sel_radius: float = _fn_visual_radius.call(e)
	var entity_type: String = str(e.get("type", ""))
	var unit_type: String = str(e.get("unit_type", ""))
	var building_type: String = str(e.get("building_type", ""))

	# ── Look up footprint from manifest ──
	var footprint: Dictionary = _get_footprint(unit_type if entity_type == "unit" else building_type, entity_type)
	var health_bar_offset: Array = _get_health_bar_offset(unit_type if entity_type == "unit" else building_type, entity_type)

	# ── 1. Sprite bounds ──
	# Approximate sprite extent from render_scale (content_extent * render_scale ≈ visible half-size)
	var sprite_half: float = sel_radius * 0.85
	_canvas.draw_rect(
		Rect2(pos.x - sprite_half, pos.y - sprite_half, sprite_half * 2.0, sprite_half * 2.0),
		COL_BOUNDS, false, 0.04
	)

	# ── 2. Footprint rect ──
	if not footprint.is_empty():
		var fw: float = float(footprint.get("w", 0.0))
		var fh: float = float(footprint.get("h", 0.0))
		if fw > 0.0 and fh > 0.0:
			var foot_rect := Rect2(
				pos.x - fw / 2.0,
				pos.y - fh / 2.0,
				fw, fh
			)
			_canvas.draw_rect(foot_rect, COL_FOOTPRINT, true)
			_canvas.draw_rect(foot_rect, COL_FOOTPRINT_EDGE, false, 0.04)

	# ── 3. Selection radius ring ──
	_canvas.draw_arc(pos, sel_radius, 0.0, TAU, 24, COL_RADIUS, 0.04, true)

	# ── 4. Pivot cross ──
	# Horizontal line
	_canvas.draw_line(
		pos + Vector2(-PIVOT_SIZE, 0.0),
		pos + Vector2(PIVOT_SIZE, 0.0),
		COL_PIVOT, CROSS_THICK, true
	)
	# Vertical line
	_canvas.draw_line(
		pos + Vector2(0.0, -PIVOT_SIZE),
		pos + Vector2(0.0, PIVOT_SIZE),
		COL_PIVOT, CROSS_THICK, true
	)

	# ── 5. Health bar anchor ──
	if health_bar_offset.size() >= 2:
		var anchor_pos := pos + Vector2(float(health_bar_offset[0]), float(health_bar_offset[1]))
		_canvas.draw_circle(anchor_pos, HBAR_DOT_R, COL_HBAR_ANCHOR)

# ─── Manifest lookup ────────────────────────────────────────────────────────

## Draw a tile ruler — vertical tick marks every tile, horizontal baseline.
func draw_tile_ruler(canvas: CanvasItem, origin: Vector2, tile_count: int = 8) -> void:
	for i in range(tile_count + 1):
		var x := origin.x + float(i)
		canvas.draw_line(Vector2(x, origin.y), Vector2(x, origin.y + 0.25), Color(1, 1, 1, 0.55), 0.03)
	canvas.draw_line(origin, origin + Vector2(float(tile_count), 0.0), Color(1, 1, 1, 0.55), 0.03)

func _get_footprint(visual_id: String, entity_type: String) -> Dictionary:
	if _manifest.is_empty():
		return {}
	var section: String = "building_visuals" if entity_type == "building" else "unit_visuals"
	var entry: Dictionary = _manifest.get(section, {}).get(visual_id, {})
	if entry.is_empty():
		return {}
	# Accept "footprint" as {"w": ..., "h": ...} or [w, h]
	var fp = entry.get("footprint", {})
	if fp is Dictionary:
		return fp
	if fp is Array and fp.size() >= 2:
		return {"w": float(fp[0]), "h": float(fp[1])}
	return {}

func _get_health_bar_offset(visual_id: String, entity_type: String) -> Array:
	if _manifest.is_empty():
		return []
	var section: String = "building_visuals" if entity_type == "building" else "unit_visuals"
	var entry: Dictionary = _manifest.get(section, {}).get(visual_id, {})
	if entry.is_empty():
		return []
	var hbo = entry.get("health_bar_offset", [])
	if hbo is Array:
		return hbo
	return []
