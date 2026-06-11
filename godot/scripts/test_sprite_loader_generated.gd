extends SceneTree

const SpriteLoaderScript := preload("res://scripts/sprite_loader.gd")

var _pass: int = 0
var _fail: int = 0


func _init() -> void:
	var manifest_path: String = "user://sc1_generated_manifest_test.json"
	var texture_path: String = "user://sc1_generated_texture_test.png"
	_write_test_texture(texture_path)
	_write_test_manifest(manifest_path, texture_path)

	var loader: SpriteLoader = SpriteLoaderScript.new(manifest_path)
	_test_generated_building_atlas(loader)
	_test_generated_visual_params_override(loader)
	_test_generated_assets_are_enumerable(loader)
	_test_generated_unit_preview_frames(loader)
	_test_disabled_generated_entry_falls_back(loader)

	print("\nSpriteLoader generated manifest test: %d passed, %d failed" % [_pass, _fail])
	if _fail > 0:
		quit(1)
		return
	quit()


func _write_test_texture(path: String) -> void:
	var image := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.2, 0.4, 0.8, 1.0))
	var err := image.save_png(path)
	if err != OK:
		_fail += 1
		print("FAIL: cannot write test generated texture")


func _write_test_manifest(path: String, texture_path: String) -> void:
	var manifest: Dictionary = {
		"schema_version": 1,
		"assets": {
			"CommandCenter": {
				"kind": "building",
				"race": "terran",
				"runtime_enabled": true,
				"asset": texture_path,
				"frame_width": 32,
				"frame_height": 40,
				"frame_count": 6,
				"atlas_rect": [4, 6, 32, 40],
				"render_scale": 0.03125,
				"selection_radius": 3.0,
			},
			"Barracks": {
				"kind": "building",
				"race": "terran",
				"runtime_enabled": false,
				"asset": "res://assets/sprites/buildings/TerranBuilding.png",
				"frame_width": 8,
				"frame_height": 8,
				"frame_count": 1,
				"atlas_rect": [0, 0, 8, 8],
			},
			"Probe": {
				"kind": "unit",
				"race": "protoss",
				"runtime_enabled": false,
				"asset": texture_path,
				"frame_width": 16,
				"frame_height": 16,
				"frame_count": 8,
				"atlas_rect": [0, 0, 16, 16],
			},
		},
	}
	var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail += 1
		print("FAIL: cannot write test generated manifest")
		return
	file.store_string(JSON.stringify(manifest))
	file.close()


func _test_generated_building_atlas(loader: SpriteLoader) -> void:
	var atlas: AtlasTexture = loader.get_building_atlas("CommandCenter")
	if atlas == null:
		_fail += 1
		print("FAIL: generated atlas is null")
		return
	var expected := Rect2(4, 6, 32, 40)
	if atlas.region == expected:
		_pass += 1
		print("PASS: generated building atlas uses exact local rect")
	else:
		_fail += 1
		print("FAIL: generated atlas region %s expected %s" % [str(atlas.region), str(expected)])


func _test_generated_visual_params_override(loader: SpriteLoader) -> void:
	var params: Dictionary = loader.get_visual_params("CommandCenter", true)
	var scale: float = float(params.get("render_scale", 0.0))
	var radius: float = float(params.get("selection_radius", 0.0))
	if not is_equal_approx(scale, 0.03125):
		_fail += 1
		print("FAIL: generated visual scale %s expected 0.03125" % scale)
		return
	if not is_equal_approx(radius, 1.02):
		_fail += 1
		print("FAIL: generated selection radius %s expected 1.02" % radius)
		return
	_pass += 1
	print("PASS: generated visual params override presentation manifest")


func _test_generated_assets_are_enumerable(loader: SpriteLoader) -> void:
	var assets: Dictionary = loader.get_generated_assets()
	if assets.has("CommandCenter") and assets.has("Probe"):
		_pass += 1
		print("PASS: generated assets can be enumerated")
	else:
		_fail += 1
		print("FAIL: generated assets were not enumerable: %s" % str(assets.keys()))


func _test_generated_unit_preview_frames(loader: SpriteLoader) -> void:
	var moving: SpriteFrames = loader.get_generated_unit_preview_frames("Probe", "moving")
	var attack: SpriteFrames = loader.get_generated_unit_preview_frames("Probe", "attack")
	if moving == null or not moving.has_animation("moving_east"):
		_fail += 1
		print("FAIL: generated moving preview frames are unavailable")
		return
	if attack == null or not attack.has_animation("attack_east"):
		_fail += 1
		print("FAIL: generated attack preview frames are unavailable")
		return
	if moving.get_frame_count("moving_east") < 2 or attack.get_frame_count("attack_east") < 2:
		_fail += 1
		print("FAIL: generated unit preview animations need multiple frames")
		return
	_pass += 1
	print("PASS: generated unit preview frames provide moving and attack animations")


func _test_disabled_generated_entry_falls_back(loader: SpriteLoader) -> void:
	var atlas: AtlasTexture = loader.get_building_atlas("Barracks")
	if atlas == null:
		_fail += 1
		print("FAIL: fallback atlas is null")
		return
	if atlas.region.size != Vector2(8, 8):
		_pass += 1
		print("PASS: disabled generated entry falls back")
	else:
		_fail += 1
		print("FAIL: disabled generated entry was used")
