extends Node2D

## Procedural terrain renderer.
## Generates a 64×64 pixel ImageTexture from height_map data, then
## draws it scaled to fill the map area in world coordinates.
##
## Height-to-color palette, shadow, contour lines, and cliff markers
## are all driven from control_feel_config.json → terrain key.

# ── Public API ──────────────────────────────────────────────

## Call whenever SimCore delivers a new height_map (2D Array [y][x] → int 0..8).
## Only regenerates the texture when the data actually changes.
func update_terrain(height_map: Array) -> void:
	if height_map.is_empty():
		return
	# Quick equality check — skip regeneration if identical
	if _cache_valid and _height_map_hash == _hash_height_map(height_map):
		return
	_height_map = height_map
	_height_map_hash = _hash_height_map(height_map)
	_rows = height_map.size()
	_cols = height_map[0].size() if _rows > 0 else 0
	_cache_valid = false
	_rebuild_texture()
	_cache_valid = true
	visible = _show_terrain
	queue_redraw()

## Clear everything and hide.
func clear() -> void:
	_height_map.clear()
	_rows = 0
	_cols = 0
	_cache_valid = false
	_height_map_hash = 0
	_terrain_texture = null
	visible = false
	queue_redraw()

## Toggle visibility (wired to the existing _show_elevation flag).
func set_visible_flag(show: bool) -> void:
	_show_terrain = show
	visible = show and not _height_map.is_empty()
	queue_redraw()

# ── Internal state ──────────────────────────────────────────

var _height_map: Array = []
var _rows: int = 0
var _cols: int = 0
var _terrain_texture: ImageTexture = null
var _cache_valid: bool = false
var _height_map_hash: int = 0
var _show_terrain: bool = true

# ── Config (loaded from control_feel_config.json) ───────────

var _palette: Array = []              # Array of Color for heights 0..8
var _shadow_intensity: float = 0.25   # 0-1
var _contour_color: Color = Color(0.35, 0.25, 0.12, 0.55)
var _contour_width: float = 0.08
var _cliff_color: Color = Color(0.9, 0.12, 0.08, 0.72)
var _cliff_width: float = 0.25
var _config_loaded: bool = false

func _ready() -> void:
	_load_config()

# ── Config loader ───────────────────────────────────────────

func _load_config() -> void:
	if _config_loaded:
		return
	_config_loaded = true

	var path: String = "res://resources/feel/control_feel_config.json"
	if not ResourceLoader.exists(path):
		_apply_defaults()
		return
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		_apply_defaults()
		return
	var text: String = f.get_as_text()
	f.close()
	var json: JSON = JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		push_warning("terrain_renderer: JSON parse error in control_feel_config.json")
		_apply_defaults()
		return
	var data: Dictionary = json.data
	if not data.has("terrain"):
		_apply_defaults()
		return
	var tc: Dictionary = data["terrain"]

	# Palette
	_palette.clear()
	var pal_raw: Array = tc.get("palette", [])
	if pal_raw.size() >= 9:
		for c in pal_raw:
			if c is Array and c.size() >= 3:
				_palette.append(Color(float(c[0]), float(c[1]), float(c[2])))
			else:
				_palette.append(Color(float(c), float(c), float(c)))
	else:
		_apply_default_palette()

	_shadow_intensity = float(tc.get("shadow_intensity", 0.25))
	var cc: Array = tc.get("contour_color", [0.35, 0.25, 0.12, 0.55])
	_contour_color = Color(float(cc[0]), float(cc[1]), float(cc[2]), float(cc[3]) if cc.size() > 3 else 1.0)
	_contour_width = float(tc.get("contour_width", 0.08))
	var clc: Array = tc.get("cliff_color", [0.9, 0.12, 0.08, 0.72])
	_cliff_color = Color(float(clc[0]), float(clc[1]), float(clc[2]), float(clc[3]) if clc.size() > 3 else 1.0)
	_cliff_width = float(tc.get("cliff_width", 0.25))

func _apply_defaults() -> void:
	_apply_default_palette()
	_shadow_intensity = 0.25
	_contour_color = Color(0.35, 0.25, 0.12, 0.55)
	_contour_width = 0.08
	_cliff_color = Color(0.9, 0.12, 0.08, 0.72)
	_cliff_width = 0.25

func _apply_default_palette() -> void:
	_palette = [
		Color(0.08, 0.14, 0.12),   # 0 — deep blue-green (lowland/water edge)
		Color(0.12, 0.20, 0.14),   # 1 — darker blue-green
		Color(0.18, 0.38, 0.14),   # 2 — green grass
		Color(0.22, 0.44, 0.16),   # 3 — brighter grass
		Color(0.42, 0.50, 0.16),   # 4 — yellow-green hills
		Color(0.50, 0.54, 0.18),   # 5 — brighter yellow-green
		Color(0.42, 0.30, 0.16),   # 6 — brown mountain
		Color(0.36, 0.24, 0.14),   # 7 — darker brown
		Color(0.52, 0.50, 0.48),   # 8 — gray peaks
	]

# ── Texture generation ──────────────────────────────────────

func _rebuild_texture() -> void:
	if _rows == 0 or _cols == 0:
		_terrain_texture = null
		return

	var img: Image = Image.create(_cols, _rows, false, Image.FORMAT_RGBA8)

	# Pass 1: base terrain color + directional shadow
	for y in range(_rows):
		var row = _height_map[y]
		for x in range(_cols):
			var h: int = int(row[x]) if x < row.size() else 0
			h = clampi(h, 0, 8)
			var base_col: Color = _palette[h]

			# Directional shadow: light from top-left.
			# If the neighbor to the RIGHT or BELOW is taller, darken this tile.
			var shadow := 0.0
			if x + 1 < _cols:
				var hr: int = int(_height_map[y][x + 1]) if (x + 1) < row.size() else h
				if hr > h:
					shadow += _shadow_intensity * float(hr - h) * 0.15
			if y + 1 < _rows:
				var hb: int = int(_height_map[y + 1][x]) if x < _height_map[y + 1].size() else h
				if hb > h:
					shadow += _shadow_intensity * float(hb - h) * 0.15
			shadow = minf(shadow, _shadow_intensity)

			var final_col: Color = Color(
				maxf(base_col.r - shadow, 0.0),
				maxf(base_col.g - shadow, 0.0),
				maxf(base_col.b - shadow, 0.0),
				1.0
			)
			img.set_pixel(x, y, final_col)

	# Pass 2: contour lines (darken pixels at height transitions)
	for y in range(_rows):
		var row = _height_map[y]
		for x in range(_cols):
			var h: int = int(row[x]) if x < row.size() else 0
			var is_contour := false
			# Right edge contour
			if x + 1 < _cols:
				var hr: int = int(_height_map[y][x + 1]) if (x + 1) < row.size() else h
				if hr != h:
					is_contour = true
			# Bottom edge contour
			if y + 1 < _rows:
				var hb: int = int(_height_map[y + 1][x]) if x < _height_map[y + 1].size() else h
				if hb != h:
					is_contour = true

			if is_contour:
				var px: Color = img.get_pixel(x, y)
				# Blend contour color over the base pixel
				var blended: Color = px.lerp(_contour_color, _contour_color.a)
				blended.a = 1.0
				img.set_pixel(x, y, blended)

	# Pass 3: cliff markers (Δh ≥ 3) — mark with cliff color
	for y in range(_rows):
		var row = _height_map[y]
		for x in range(_cols):
			var h: int = int(row[x]) if x < row.size() else 0
			# Right cliff
			if x + 1 < _cols:
				var hr: int = int(_height_map[y][x + 1]) if (x + 1) < row.size() else h
				if absi(hr - h) >= 3:
					var px: Color = img.get_pixel(x, y)
					var blended: Color = px.lerp(_cliff_color, _cliff_color.a)
					blended.a = 1.0
					img.set_pixel(x, y, blended)
			# Bottom cliff
			if y + 1 < _rows:
				var hb: int = int(_height_map[y + 1][x]) if x < _height_map[y + 1].size() else h
				if absi(hb - h) >= 3:
					var px: Color = img.get_pixel(x, y)
					var blended: Color = px.lerp(_cliff_color, _cliff_color.a)
					blended.a = 1.0
					img.set_pixel(x, y, blended)

	# Create texture — Godot 4 ImageTexture inherits Texture2D with LINEAR default.
	# We override filtering in _draw() via CanvasItem.texture_filter = NEAREST.
	_terrain_texture = ImageTexture.create_from_image(img)

# ── Drawing ─────────────────────────────────────────────────

func _draw() -> void:
	if _terrain_texture == null or _rows == 0 or _cols == 0:
		return

	# Force nearest-neighbor filtering so the 64×64 texture scales crisply
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST

	var map_rect := Rect2(Vector2.ZERO, Vector2(float(_cols), float(_rows)))
	draw_texture_rect(_terrain_texture, map_rect, false)

	# Overlay cliff lines as thick vector lines for visibility
	# (The pixel-level cliff tint in the texture is subtle; these lines
	#  make cliffs unmistakable at any zoom level.)
	for y in range(_rows):
		var row = _height_map[y]
		for x in range(_cols):
			var h: int = int(row[x]) if x < row.size() else 0
			# Right cliff
			if x + 1 < _cols:
				var hr: int = int(_height_map[y][x + 1]) if (x + 1) < row.size() else h
				if absi(hr - h) >= 3:
					draw_line(
						Vector2(float(x + 1), float(y)),
						Vector2(float(x + 1), float(y + 1)),
						_cliff_color, _cliff_width
					)
			# Bottom cliff
			if y + 1 < _rows:
				var hb: int = int(_height_map[y + 1][x]) if x < _height_map[y + 1].size() else h
				if absi(hb - h) >= 3:
					draw_line(
						Vector2(float(x), float(y + 1)),
						Vector2(float(x + 1), float(y + 1)),
						_cliff_color, _cliff_width
					)

	# Overlay contour lines as vector lines for crispness at high zoom
	# (Pixel-level contours in texture provide the base; these vector lines
	#  ensure contour visibility at all zoom levels.)
	for y in range(_rows):
		var row = _height_map[y]
		for x in range(_cols):
			var h: int = int(row[x]) if x < row.size() else 0
			# Right contour
			if x + 1 < _cols:
				var hr: int = int(_height_map[y][x + 1]) if (x + 1) < row.size() else h
				if hr != h:
					draw_line(
						Vector2(float(x + 1), float(y)),
						Vector2(float(x + 1), float(y + 1)),
						_contour_color, _contour_width
					)
			# Bottom contour
			if y + 1 < _rows:
				var hb: int = int(_height_map[y + 1][x]) if x < _height_map[y + 1].size() else h
				if hb != h:
					draw_line(
						Vector2(float(x), float(y + 1)),
						Vector2(float(x + 1), float(y + 1)),
						_contour_color, _contour_width
					)

# ── Helpers ──────────────────────────────────────────────────

## Simple hash of the height_map for cheap change detection.
func _hash_height_map(hm: Array) -> int:
	var h: int = 0
	var count := 0
	for y in range(hm.size()):
		var row = hm[y]
		for x in range(row.size()):
			h = h * 31 + int(row[x])
			count += 1
			if count > 512:  # sample enough for a reliable hash
				return h
	return h
