class_name SpriteLoader
extends RefCounted

## Utility class for loading StarCraft sprite sheets into Godot SpriteFrames.
##
## Reads sprite_frames_config.json and dynamically creates SpriteFrames resources
## for units (8-direction animated) and AtlasTexture for buildings (sub-region
## of a combined sprite sheet).

# ─── Constants ────────────────────────────────────────────────────────────────
const CONFIG_PATH := "res://resources/sprite_frames_config.json"
const FRAME_TIME_MS := 100  # 10 FPS → 100ms per frame (matches original SC tick)

# ─── Internal state ───────────────────────────────────────────────────────────
var _config: Dictionary = {}
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
				print("[SpriteLoader] Loaded config: %d units, %d buildings" % [
					_config.get("units", {}).size(),
					_config.get("buildings", {}).size()
				])
			else:
				push_error("[SpriteLoader] Failed to parse config JSON: %s" % json.get_error_message())
	else:
		push_warning("[SpriteLoader] Config file not found: %s" % CONFIG_PATH)


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
	var directions: int = int(info.get("directions", 8))
	var animations: Dictionary = info.get("animations", {})

	# Create animation for each (anim_name, direction) pair
	for anim_name in animations:
		var frame_count: int = int(animations[anim_name])

		for dir_idx in range(directions):
			var mirror := dir_idx >= 4
			var src_dir := dir_idx
			if mirror:
				# Mirror left-facing from right-facing:
				# 4(W)→0(E), 5(SW)→3(NW), 6(S)→2(N), 7(SE)→1(NE)
				src_dir = (8 - dir_idx) % 8

			var anim_key := "%s_%s" % [anim_name, DIRECTION_NAMES[dir_idx]]
			sprite_frames.add_animation(anim_key)
			sprite_frames.set_animation_speed(anim_key, 1000.0 / FRAME_TIME_MS)  # 10 FPS

			for frame_idx in range(frame_count):
				var atlas := AtlasTexture.new()
				atlas.atlas = texture
				var region_x := frame_idx * frame_w
				var region_y := src_dir * frame_h
				atlas.region = Rect2(region_x, region_y, frame_w, frame_h)
				atlas.filter_clip = true
				if mirror:
					atlas.flip_h = true
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


## Get or create an AtlasTexture for a building from the combined sprite sheet.
func get_building_atlas(entity_name: String) -> AtlasTexture:
	if _building_cache.has(entity_name):
		return _building_cache[entity_name]

	var buildings: Dictionary = _config.get("buildings", {})
	if not buildings.has(entity_name):
		push_warning("[SpriteLoader] Building not found in config: %s" % entity_name)
		return null

	var info: Dictionary = buildings[entity_name]
	var texture := _get_texture(info["file"])
	if texture == null:
		return null

	var atlas := AtlasTexture.new()
	atlas.atlas = texture
	atlas.region = Rect2(
		int(info.get("offset_x", 0)),
		int(info.get("offset_y", 0)),
		int(info.get("frame_width", 128)),
		int(info.get("frame_height", 128))
	)
	atlas.filter_clip = true

	_building_cache[entity_name] = atlas
	return atlas


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