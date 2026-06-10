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
const FRAME_TIME_MS := 100  # 10 FPS → 100ms per frame (matches original SC tick)
const BUILDING_ATLAS_PADDING := 12

# ─── Internal state ───────────────────────────────────────────────────────────
var _config: Dictionary = {}
var _manifest: Dictionary = {}
var _unit_cache: Dictionary = {}   # entity_name → SpriteFrames
var _building_cache: Dictionary = {}  # entity_name → AtlasTexture
var _loaded_textures: Dictionary = {}  # file_path → Texture2D

# ─── Direction mapping ────────────────────────────────────────────────────────
# 0=E, 1=NE, 2=N, 3=NW, 4=W, 5=SW, 6=S, 7=SE
# Directions 4-7 (left-facing) will be horizontally flipped from 0-3.

static var DIRECTION_NAMES: PackedStringArray = [
	"east", "northeast", "north", "northwest",
	"west", "southwest", "south", "southeast"
]


# ─── Lifecycle ────────────────────────────────────────────────────────────────
func _init() -> void:
	_load_config()
	_load_manifest()


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


## Get visual parameters from presentation_manifest.
## Returns: {"render_scale": float, "selection_radius": float, "pivot": Vector2,
##           "health_bar_offset": Vector2, "selection_ring_offset": Vector2,
##           "fallback": Dictionary}
func get_visual_params(entity_name: String, is_building: bool) -> Dictionary:
	var section_name: String = "building_visuals" if is_building else "unit_visuals"
	var section: Dictionary = _manifest.get(section_name, {})
	var visual: Dictionary = section.get(entity_name, {})
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
	_loaded_textures.clear()


## Reload manifest and config (for hot-reload during development).
func reload() -> void:
	clear_cache()
	_load_config()
	_load_manifest()


# ─── Internal helpers ─────────────────────────────────────────────────────────

func _get_texture(file_path: String) -> Texture2D:
	if _loaded_textures.has(file_path):
		return _loaded_textures[file_path]

	if not ResourceLoader.exists(file_path):
		push_error("[SpriteLoader] Texture not found: %s" % file_path)
		return null

	var tex := ResourceLoader.load(file_path, "Texture2D") as Texture2D
	if tex:
		_loaded_textures[file_path] = tex
	return tex