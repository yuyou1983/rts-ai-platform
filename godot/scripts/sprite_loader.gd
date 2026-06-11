class_name SpriteLoader
extends RefCounted

## Utility class for loading StarCraft sprite sheets into Godot SpriteFrames.
##
## Reads sprite_frames_config.json AND presentation_manifest.json.
## Manifest provides atlas_rect, pivot, render_scale, selection_radius,
## health_bar_offset, and fallback — eliminating hardcoded overrides.

# ─── Constants ────────────────────────────────────────────────────────────────
const CONFIG_PATH := "res://resources/sprite_frames_config.json"
const MANIFEST_PATH := "res://resources/presentation_manifest.json"
const GENERATED_MANIFEST_PATH := "res://assets/sc1_generated/generated_manifest.json"
const FRAME_TIME_MS := 100  # 10 FPS → 100ms per frame (matches original SC tick)
const BUILDING_ATLAS_PADDING := 12

# ─── Internal state ───────────────────────────────────────────────────────────
var _config: Dictionary = {}
var _manifest: Dictionary = {}
var _generated_manifest: Dictionary = {}
var _generated_manifest_path: String = GENERATED_MANIFEST_PATH
var _unit_cache: Dictionary = {}   # entity_name → SpriteFrames
var _building_cache: Dictionary = {}  # entity_name → AtlasTexture
var _generated_atlas_cache: Dictionary = {}  # kind:entity_name → AtlasTexture
var _generated_unit_preview_cache: Dictionary = {}  # entity_name:action → SpriteFrames
var _loaded_textures: Dictionary = {}  # file_path → Texture2D

# ─── Direction mapping ────────────────────────────────────────────────────────
# 0=E, 1=NE, 2=N, 3=NW, 4=W, 5=SW, 6=S, 7=SE
# Directions 4-7 (left-facing) will be horizontally flipped from 0-3.

static var DIRECTION_NAMES: PackedStringArray = [
	"east", "northeast", "north", "northwest",
	"west", "southwest", "south", "southeast"
]


# ─── Lifecycle ────────────────────────────────────────────────────────────────
func _init(generated_manifest_path: String = GENERATED_MANIFEST_PATH) -> void:
	_generated_manifest_path = generated_manifest_path
	_load_config()
	_load_manifest()
	_load_generated_manifest()


func _load_config() -> void:
	if FileAccess.file_exists(CONFIG_PATH):
		var f := FileAccess.open(CONFIG_PATH, FileAccess.READ)
		if f:
			var json_text := f.get_as_text()
			f.close()
			var json := JSON.new()
			var err := json.parse(json_text)
			if err == OK:
				_config = json.data
				print("[SpriteLoader] Loaded sprite config: %d units, %d buildings" % [
						_config.get("units", {}).size(),
						_config.get("buildings", {}).size()
					])
			else:
				push_error("[SpriteLoader] Failed to parse sprite config JSON: %s" % json.get_error_message())
	else:
		push_warning("[SpriteLoader] Config file not found: %s" % CONFIG_PATH)


func _load_manifest() -> void:
	if FileAccess.file_exists(MANIFEST_PATH):
		var f := FileAccess.open(MANIFEST_PATH, FileAccess.READ)
		if f:
			var json_text := f.get_as_text()
			f.close()
			var json := JSON.new()
			var err := json.parse(json_text)
			if err == OK:
				_manifest = json.data
				var b_count: int = _manifest.get("building_visuals", {}).size()
				var u_count: int = _manifest.get("unit_visuals", {}).size()
				print("[SpriteLoader] Loaded presentation manifest: %d buildings, %d units" % [b_count, u_count])
			else:
				push_error("[SpriteLoader] Failed to parse manifest JSON: %s" % json.get_error_message())
	else:
		push_warning("[SpriteLoader] Manifest not found: %s — visual params unavailable" % MANIFEST_PATH)


func _load_generated_manifest() -> void:
	_generated_manifest = {}
	if not FileAccess.file_exists(_generated_manifest_path):
		return

	var f := FileAccess.open(_generated_manifest_path, FileAccess.READ)
	if f:
		var json_text := f.get_as_text()
		f.close()
		var json := JSON.new()
		var err := json.parse(json_text)
		if err == OK and json.data is Dictionary:
			_generated_manifest = json.data
			var a_count: int = _generated_manifest.get("assets", {}).size()
			print("[SpriteLoader] Loaded generated SC1 manifest: %d assets" % a_count)
		else:
			push_error("[SpriteLoader] Failed to parse generated manifest JSON: %s" % json.get_error_message())


# ─── Public API ───────────────────────────────────────────────────────────────

## Get or create SpriteFrames for a unit entity.
## Each animation is split into 8-direction variants: "anim_dir" (e.g. "moving_north").
## Directions 4-7 use horizontally flipped frames from directions 0-3.
func get_frames(entity_name: String) -> SpriteFrames:
	if _unit_cache.has(entity_name):
		return _unit_cache[entity_name]

	var units: Dictionary = _config.get("units", {})
	if not units.has(entity_name):
		push_warning("[SpriteLoader] Unit not found in config: %s" % entity_name)
		return null

	var info: Dictionary = units[entity_name]
	var sprite_frames := SpriteFrames.new()

	var texture := _get_texture(info["file"])
	if texture == null:
		return null

	var frame_w: int = int(info["frame_width"])
	var frame_h: int = int(info["frame_height"])
	var directions: int = mini(int(info.get("directions", 8)), maxi(1, int(texture.get_height() / max(frame_h, 1))))
	var animations: Dictionary = info.get("animations", {})

	# Create animation for each (anim_name, direction) pair
	for anim_name in animations:
		var frame_count: int = int(animations[anim_name])

		for dir_idx in range(directions):
			var anim_key := "%s_%s" % [anim_name, DIRECTION_NAMES[dir_idx]]
			sprite_frames.add_animation(anim_key)
			sprite_frames.set_animation_speed(anim_key, 1000.0 / FRAME_TIME_MS)  # 10 FPS

			for frame_idx in range(frame_count):
				var atlas := AtlasTexture.new()
				atlas.atlas = texture
				var region_x := frame_idx * frame_w
				var region_y := dir_idx * frame_h
				atlas.region = Rect2(region_x, region_y, frame_w, frame_h)
				atlas.filter_clip = true
				sprite_frames.add_frame(anim_key, atlas)

	# Also create a default "idle" animation pointing south for quick setup
	var default_anim := "idle_south"
	if not sprite_frames.has_animation(default_anim):
		# Try any idle variant
		for a in sprite_frames.get_animation_names():
			if a.begins_with("idle_"):
				default_anim = a
				break
	if sprite_frames.get_animation_names().size() > 0:
		sprite_frames.set_animation_loop(default_anim, true)

	_unit_cache[entity_name] = sprite_frames
	return sprite_frames


## Get or create an AtlasTexture for a building.
## Priority: presentation_manifest.atlas_rect > sprite_frames_config offset.
func get_building_atlas(entity_name: String) -> AtlasTexture:
	if _building_cache.has(entity_name):
		return _building_cache[entity_name]

	var generated_atlas := _get_generated_building_atlas(entity_name)
	if generated_atlas != null:
		_building_cache[entity_name] = generated_atlas
		return generated_atlas

	# Try manifest first — it has the precise hand-tuned atlas_rect
	var bv: Dictionary = _manifest.get("building_visuals", {}).get(entity_name, {})
	var manifest_atlas_rect: Array = bv.get("atlas_rect", [])

	if manifest_atlas_rect.size() == 4:
		var texture_path: String = str(bv.get("asset", ""))
		var texture := _get_texture(texture_path)
		if texture:
			var raw_region := Rect2(
				int(manifest_atlas_rect[0]),
				int(manifest_atlas_rect[1]),
				int(manifest_atlas_rect[2]),
				int(manifest_atlas_rect[3])
			)
			var expanded_region := raw_region.grow(BUILDING_ATLAS_PADDING)
			var texture_rect := Rect2(Vector2.ZERO, texture.get_size())
			var final_region := expanded_region.intersection(texture_rect)

			var atlas := AtlasTexture.new()
			atlas.atlas = texture
			atlas.region = final_region
			atlas.filter_clip = true

			_building_cache[entity_name] = atlas
			return atlas

	# Fallback to sprite_frames_config
	var buildings: Dictionary = _config.get("buildings", {})
	if not buildings.has(entity_name):
		push_warning("[SpriteLoader] Building not found in config or manifest: %s" % entity_name)
		return null

	var info: Dictionary = buildings[entity_name]
	var texture := _get_texture(info["file"])
	if texture == null:
		return null

	var raw_region := Rect2(
		int(info.get("offset_x", 0)),
		int(info.get("offset_y", 0)),
		int(info.get("frame_width", 128)),
		int(info.get("frame_height", 128))
	)
	var expanded_region := raw_region.grow(BUILDING_ATLAS_PADDING)
	var texture_rect := Rect2(Vector2.ZERO, texture.get_size())
	var final_region := expanded_region.intersection(texture_rect)

	var atlas := AtlasTexture.new()
	atlas.atlas = texture
	atlas.region = final_region
	atlas.filter_clip = true

	_building_cache[entity_name] = atlas
	return atlas


## Return generated local SC1 assets from the optional ignored manifest.
## Used by Test Mode/resource QA only; generated commercial assets are not committed.
func get_generated_assets() -> Dictionary:
	return _generated_manifest.get("assets", {}).duplicate(true)


## Return all entries from generated_manifest where entry['batch'] == batch_name.
func get_assets_by_batch(batch_name: String) -> Dictionary:
	var result = {}
	var assets = _generated_manifest.get("assets", {})
	for asset_id in assets:
		var entry = assets[asset_id]
		if str(entry.get("batch", "")) == batch_name:
			result[asset_id] = entry.duplicate(true)
	return result


## Return all entries from generated_manifest where entry['visual_class'] == vc.
func get_assets_by_visual_class(vc: String) -> Dictionary:
	var result = {}
	var assets = _generated_manifest.get("assets", {})
	for asset_id in assets:
		var entry = assets[asset_id]
		if str(entry.get("visual_class", "")) == vc:
			result[asset_id] = entry.duplicate(true)
	return result


## Return unique batch names from generated_manifest.
func get_batches() -> PackedStringArray:
	var seen = {}
	var assets = _generated_manifest.get("assets", {})
	for asset_id in assets:
		var b = str(assets[asset_id].get("batch", ""))
		if b != "" and not seen.has(b):
			seen[b] = true
	return PackedStringArray(seen.keys())


## Return unique visual_class values from generated_manifest.
func get_visual_classes() -> PackedStringArray:
	var seen = {}
	var assets = _generated_manifest.get("assets", {})
	for asset_id in assets:
		var vc = str(assets[asset_id].get("visual_class", ""))
		if vc != "" and not seen.has(vc):
			seen[vc] = true
	return PackedStringArray(seen.keys())


## Build simple generated unit preview animations from a converted GRP contact sheet.
## The generated manifest does not know StarCraft iscript action ranges yet, so this
## samples different windows of the frame strip for movement and attack QA.
func get_generated_unit_preview_frames(entity_name: String, action: String) -> SpriteFrames:
	var cache_key := "%s:%s" % [entity_name, action]
	if _generated_unit_preview_cache.has(cache_key):
		return _generated_unit_preview_cache[cache_key]

	var entry := _get_generated_asset_entry(entity_name, "unit", false)
	if entry.is_empty():
		return null

	var texture_path: String = str(entry.get("asset", ""))
	if texture_path == "":
		return null
	var texture := _get_texture(texture_path)
	if texture == null:
		return null

	var frame_count: int = int(entry.get("frame_count", 0))
	var frame_width: int = int(entry.get("frame_width", 0))
	var frame_height: int = int(entry.get("frame_height", 0))
	if frame_count <= 0 or frame_width <= 0 or frame_height <= 0:
		return null

	var columns: int = maxi(1, int(texture.get_width() / frame_width))
	var start_frame: int = 0
	if action == "attack" and frame_count > 2:
		start_frame = int(frame_count * 0.55)
	elif action == "moving" and frame_count > 17:
		start_frame = mini(17, frame_count - 1)
	var preview_count: int = mini(10, frame_count)
	if frame_count < 2:
		preview_count = 1

	var anim_name := "%s_east" % action
	var frames := SpriteFrames.new()
	frames.add_animation(anim_name)
	frames.set_animation_loop(anim_name, true)
	frames.set_animation_speed(anim_name, 1000.0 / FRAME_TIME_MS)

	for i in range(preview_count):
		var frame_idx: int = (start_frame + i) % frame_count
		var atlas := AtlasTexture.new()
		atlas.atlas = texture
		atlas.region = Rect2(
			(frame_idx % columns) * frame_width,
			int(frame_idx / columns) * frame_height,
			frame_width,
			frame_height
		)
		atlas.filter_clip = true
		frames.add_frame(anim_name, atlas)

	_generated_unit_preview_cache[cache_key] = frames
	return frames


## Load a generated building/resource frame directly from the generated manifest.
func get_generated_asset_atlas(
	entity_name: String,
	expected_kind: String,
	require_runtime_enabled: bool = false
) -> AtlasTexture:
	var cache_key := "%s:%s" % [expected_kind, entity_name]
	if _generated_atlas_cache.has(cache_key):
		return _generated_atlas_cache[cache_key]

	var atlas := _get_generated_asset_atlas(entity_name, expected_kind, require_runtime_enabled)
	if atlas != null:
		_generated_atlas_cache[cache_key] = atlas
	return atlas


## Get visual parameters from presentation_manifest.
## Returns: {"render_scale": float, "selection_radius": float, "pivot": Vector2,
##           "health_bar_offset": Vector2, "selection_ring_offset": Vector2,
##           "fallback": Dictionary}
func get_visual_params(entity_name: String, is_building: bool) -> Dictionary:
	var section_name: String = "building_visuals" if is_building else "unit_visuals"
	var section: Dictionary = _manifest.get(section_name, {})
	var visual: Dictionary = section.get(entity_name, {}).duplicate(true)
	var generated_visual := _get_generated_visual_entry(entity_name, "building" if is_building else "unit")
	if not generated_visual.is_empty():
		for key in ["render_scale", "selection_radius", "pivot", "health_bar_offset", "selection_ring_offset"]:
			if generated_visual.has(key):
				visual[key] = generated_visual[key]
	var _rendering: Dictionary = _manifest.get("_rendering", {})

	var building_xform: Dictionary = _rendering.get("building_selection_transform", {})
	var unit_xform: Dictionary = _rendering.get("unit_selection_transform", {})

	var fallback_rs: float = 0.018 if is_building else 0.022
	var fallback_sr: float = 1.5 if is_building else 0.55
	var rs: float = float(visual.get("render_scale", fallback_rs))
	var sr: float = float(visual.get("selection_radius", fallback_sr))

	# Apply the same transform game_view.gd used, but make it configurable
	if is_building:
		var m: float = float(building_xform.get("multiplier", 0.34))
		var lo: float = float(building_xform.get("min", 0.95))
		var hi: float = float(building_xform.get("max", 1.65))
		sr = clampf(sr * m, lo, hi)
	else:
		var m: float = float(unit_xform.get("multiplier", 0.78))
		var lo: float = float(unit_xform.get("min", 0.38))
		var hi: float = float(unit_xform.get("max", 0.72))
		sr = clampf(sr * m, lo, hi)

	var pivot_arr: Array = visual.get("pivot", [0.5, 0.72 if is_building else 0.5])
	var hbo_arr: Array = visual.get("health_bar_offset", [0, -0.28])
	var sro_arr: Array = visual.get("selection_ring_offset", [0, 0.1 if is_building else 0.05])

	return {
		"render_scale": rs,
		"selection_radius": sr,
		"pivot": Vector2(float(pivot_arr[0]), float(pivot_arr[1])),
		"health_bar_offset": Vector2(float(hbo_arr[0]), float(hbo_arr[1])),
		"selection_ring_offset": Vector2(float(sro_arr[0]), float(sro_arr[1])),
		"fallback": visual.get("fallback", {}),
	}


## Get global rendering parameters (selection ring, health bar, etc).
func get_rendering_params() -> Dictionary:
	return _manifest.get("_rendering", {})


## Convert a facing angle (radians) to one of 8 direction indices.
## 0=E, 1=NE, 2=N, 3=NW, 4=W, 5=SW, 6=S, 7=SE
## Angle 0 = right/east, increases counter-clockwise (standard math convention).
func get_direction_index(facing: float) -> int:
	# Normalize to [0, 2π)
	var angle := fposmod(facing, TAU)
	# Divide circle into 8 sectors of 45° each
	# Offset by 22.5° (half sector) so sector centers align with cardinal/ordinal dirs
	var sector := int(round(angle / (PI / 4.0))) % 8
	# Map: 0→E(0), 1→NE(1), 2→N(2), 3→NW(3), 4→W(4), 5→SW(5), 6→S(6), 7→SE(7)
	return sector


## Get the animation key for a given base animation name and direction.
## e.g. get_animation_key("moving", 2) → "moving_north"
func get_animation_key(anim_name: String, direction: int) -> String:
	var dir_idx := direction % 8
	return "%s_%s" % [anim_name, DIRECTION_NAMES[dir_idx]]


## Get a list of all available animation base names for a unit.
func get_animation_names(entity_name: String) -> PackedStringArray:
	var units: Dictionary = _config.get("units", {})
	if not units.has(entity_name):
		return []
	var info: Dictionary = units[entity_name]
	var anims: Dictionary = info.get("animations", {})
	return PackedStringArray(anims.keys())


## Check if an entity is a building (in the buildings config).
func is_building(entity_name: String) -> bool:
	return _config.get("buildings", {}).has(entity_name)


## Check if an entity is a unit (in the units config).
func is_unit(entity_name: String) -> bool:
	return _config.get("units", {}).has(entity_name)


## Clear all cached resources (useful for hot-reloading during development).
func clear_cache() -> void:
	_unit_cache.clear()
	_building_cache.clear()
	_generated_atlas_cache.clear()
	_generated_unit_preview_cache.clear()
	_loaded_textures.clear()


## Reload manifest and config (for hot-reload during development).
func reload() -> void:
	clear_cache()
	_load_config()
	_load_manifest()
	_load_generated_manifest()


# ─── Internal helpers ─────────────────────────────────────────────────────────

func _get_generated_building_atlas(entity_name: String) -> AtlasTexture:
	return _get_generated_asset_atlas(entity_name, "building", true)


func _get_generated_asset_atlas(
	entity_name: String,
	expected_kind: String,
	require_runtime_enabled: bool
) -> AtlasTexture:
	var entry := _get_generated_asset_entry(entity_name, expected_kind, require_runtime_enabled)
	if entry.is_empty():
		return null

	var texture_path: String = str(entry.get("asset", ""))
	if texture_path == "":
		return null
	var texture := _get_texture(texture_path)
	if texture == null:
		return null

	var atlas_rect: Array = entry.get("atlas_rect", [])
	var frame_width: int = int(entry.get("frame_width", 0))
	var frame_height: int = int(entry.get("frame_height", 0))
	var raw_region := Rect2(0, 0, frame_width, frame_height)
	if atlas_rect.size() == 4:
		raw_region = Rect2(
			int(atlas_rect[0]),
			int(atlas_rect[1]),
			int(atlas_rect[2]),
			int(atlas_rect[3])
		)
	if raw_region.size.x <= 0 or raw_region.size.y <= 0:
		raw_region = Rect2(Vector2.ZERO, texture.get_size())

	var texture_rect := Rect2(Vector2.ZERO, texture.get_size())
	var final_region := raw_region.intersection(texture_rect)
	if final_region.size.x <= 0 or final_region.size.y <= 0:
		return null

	var atlas := AtlasTexture.new()
	atlas.atlas = texture
	atlas.region = final_region
	atlas.filter_clip = true
	return atlas


func _get_generated_visual_entry(entity_name: String, expected_kind: String) -> Dictionary:
	return _get_generated_asset_entry(entity_name, expected_kind, true)


func _get_generated_asset_entry(
	entity_name: String,
	expected_kind: String,
	require_runtime_enabled: bool
) -> Dictionary:
	var assets: Dictionary = _generated_manifest.get("assets", {})
	var entry: Dictionary = assets.get(entity_name, {})
	if entry.is_empty():
		return {}
	if str(entry.get("kind", "")) != expected_kind:
		return {}
	if require_runtime_enabled and not bool(entry.get("runtime_enabled", false)):
		return {}
	return entry


func _get_texture(file_path: String) -> Texture2D:
	if _loaded_textures.has(file_path):
		return _loaded_textures[file_path]

	var tex: Texture2D = null
	if ResourceLoader.exists(file_path):
		tex = ResourceLoader.load(file_path, "Texture2D") as Texture2D
	else:
		tex = _load_image_texture(file_path)
	if tex:
		_loaded_textures[file_path] = tex
	else:
		push_error("[SpriteLoader] Texture not found: %s" % file_path)
	return tex


func _load_image_texture(file_path: String) -> Texture2D:
	if not FileAccess.file_exists(file_path):
		return null
	var image := Image.new()
	var err := image.load(file_path)
	if err != OK:
		push_error("[SpriteLoader] Failed to load image texture %s: %s" % [file_path, err])
		return null
	return ImageTexture.create_from_image(image)
