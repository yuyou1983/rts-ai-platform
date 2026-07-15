extends Node2D

## SC1-style tileset renderer.
## Reads a tileset_manifest.json and draws terrain tiles via atlas region blitting.
## Falls back to a solid green ImageTexture if the manifest or atlas cannot load.
##
## API:
##   update_terrain(tiles: Array)   — 2D Array [y][x] of tile_index (int)
##   clear()                        — reset and hide
##   set_visible_flag(show: bool)   — toggle visibility

# ── Public API ──────────────────────────────────────────────

func update_terrain(tiles: Array) -> void:
	if tiles.is_empty():
		return
	_tiles = tiles
	_rows = tiles.size()
	_cols = tiles[0].size() if _rows > 0 else 0
	queue_redraw()

func clear() -> void:
	_tiles.clear()
	_rows = 0
	_cols = 0
	visible = false
	queue_redraw()

func set_visible_flag(show: bool) -> void:
	_show = show
	visible = show and not _tiles.is_empty()

# ── Internal state ──────────────────────────────────────────

var _tiles: Array = []
var _rows: int = 0
var _cols: int = 0
var _show: bool = true

# Manifest data
var _tile_size_px: int = 64
var _atlas: Texture2D = null
var _tile_index_to_rect: Dictionary = {}
var _default_tile: int = 0
var _manifest_loaded: bool = false

# Fallback texture (solid green grass)
var _fallback_texture: ImageTexture = null

func _ready() -> void:
	z_index = -5  # same as terrain_renderer.gd
	_load_manifest()
	_ensure_fallback()

# ── Manifest loader ────────────────────────────────────────

func _load_manifest() -> void:
	if _manifest_loaded:
		return
	_manifest_loaded = true

	var path: String = "res://resources/terrain/tileset_manifest.json"
	if not ResourceLoader.exists(path):
		_apply_manifest_defaults()
		return
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		_apply_manifest_defaults()
		return
	var text: String = f.get_as_text()
	f.close()
	var json: JSON = JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		push_warning("sc1_tileset_renderer: JSON parse error in tileset_manifest.json")
		_apply_manifest_defaults()
		return
	var data: Dictionary = json.data

	_tile_size_px = int(data.get("tile_size_px", 64))
	_default_tile = int(data.get("default_tile", 0))

	# tile_index_to_rect: dict of string keys "0", "1", ... → [x, y, w, h]
	var raw_map: Dictionary = data.get("tile_index_to_rect", {})
	_tile_index_to_rect.clear()
	for key in raw_map:
		var val = raw_map[key]
		var idx: int = int(key)
		if val is Array and val.size() >= 4:
			_tile_index_to_rect[idx] = Rect2(
				float(val[0]), float(val[1]),
				float(val[2]), float(val[3])
			)

	# Load atlas texture
	var atlas_path: String = str(data.get("atlas", ""))
	if atlas_path != "":
		if ResourceLoader.exists(atlas_path):
			_atlas = ResourceLoader.load(atlas_path, "Texture2D") as Texture2D
		elif FileAccess.file_exists(atlas_path):
			var img := Image.new()
			if img.load(atlas_path) == OK:
				_atlas = ImageTexture.create_from_image(img)
	if _atlas == null:
		push_warning("sc1_tileset_renderer: atlas '%s' not found, using fallback" % atlas_path)

func _apply_manifest_defaults() -> void:
	_tile_size_px = 64
	_default_tile = 0
	_tile_index_to_rect = {}
	_atlas = null

func _ensure_fallback() -> void:
	if _fallback_texture != null:
		return
	var img := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	img.fill(Color(0.18, 0.40, 0.14, 1.0))  # SC1-like grass green
	_fallback_texture = ImageTexture.create_from_image(img)

# ── Drawing ────────────────────────────────────────────────

func _draw() -> void:
	if _rows == 0 or _cols == 0:
		return

	# Force nearest-neighbor filtering for pixel-perfect tile rendering
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST

	var use_fallback: bool = (_atlas == null or _tile_index_to_rect.is_empty())

	for y in range(_rows):
		var row = _tiles[y]
		for x in range(_cols):
			var tile_idx: int = int(row[x]) if x < row.size() else _default_tile
			var px: float = float(x)
			var py: float = float(y)

			if use_fallback:
				# Draw the green fallback tile at each position
				draw_texture_rect(
					_fallback_texture,
					Rect2(px, py, 1.0, 1.0),
					false
				)
			else:
				# Look up atlas region for this tile_index
				var region: Rect2 = _tile_index_to_rect.get(tile_idx, _tile_index_to_rect.get(_default_tile, Rect2()))
				if region == Rect2():
					# If no mapping, use fallback for this tile
					draw_texture_rect(
						_fallback_texture,
						Rect2(px, py, 1.0, 1.0),
						false
					)
				else:
					draw_texture_rect_region(
						_atlas,
						Rect2(px, py, 1.0, 1.0),
						region
					)
