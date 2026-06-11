extends SceneTree

const GameViewScript := preload("res://scripts/game_view.gd")
const SpriteLoaderScript := preload("res://scripts/sprite_loader.gd")

var _pass: int = 0
var _fail: int = 0


func _init() -> void:
	_test_generated_probe_region()
	_test_resource_gallery_builds_generated_entities()

	print("\nGameView Probe override test: %d passed, %d failed" % [_pass, _fail])
	if _fail > 0:
		quit(1)
		return
	quit()


func _test_generated_probe_region() -> void:
	var view := GameViewScript.new()
	view._player_races["1"] = "3"
	view._unit_anim_info["worker_3"] = {
		"rows": 1,
		"cols": [17],
		"fw": [32],
		"fh": [32],
		"south": [8],
	}

	var image := Image.create(544, 32, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.8, 0.7, 1.0, 1.0))
	view._unit_textures["worker_3"] = ImageTexture.create_from_image(image)

	var region: Rect2 = view._calc_unit_region("worker", 1, 0, 8)
	var expected := Rect2(256, 0, 32, 32)
	view.free()

	if region == expected:
		_pass += 1
		print("PASS: Protoss worker uses generated Probe 17-frame strip region")
	else:
		_fail += 1
		print("FAIL: Probe region %s expected %s" % [str(region), str(expected)])


func _test_resource_gallery_builds_generated_entities() -> void:
	var manifest_path: String = "user://game_view_gallery_manifest_test.json"
	_write_gallery_manifest(manifest_path)

	var view := GameViewScript.new()
	view._test_mode = true
	view._sprite_loader = SpriteLoaderScript.new(manifest_path)
	view._build_test_entities()

	var found_building := false
	var found_resource := false
	var found_unit_move := false
	var found_unit_attack := false
	for e in view._ents:
		if str(e.get("generated_asset_id", "")) == "CommandCenter":
			found_building = true
		if str(e.get("generated_asset_id", "")) == "MineralFieldType1":
			found_resource = true
		if str(e.get("generated_asset_id", "")) == "SCV" and str(e.get("preview_action", "")) == "moving":
			found_unit_move = true
		if str(e.get("generated_asset_id", "")) == "SCV" and str(e.get("preview_action", "")) == "attack":
			found_unit_attack = true
	view.free()

	if found_building and found_resource and found_unit_move and found_unit_attack:
		_pass += 1
		print("PASS: Test Mode gallery builds generated building/resource/unit previews")
	else:
		_fail += 1
		print(
			"FAIL: gallery missing previews building=%s resource=%s move=%s attack=%s" %
			[found_building, found_resource, found_unit_move, found_unit_attack]
		)


func _write_gallery_manifest(path: String) -> void:
	var manifest: Dictionary = {
		"schema_version": 1,
		"assets": {
			"CommandCenter": {
				"kind": "building",
				"race": "terran",
				"runtime_enabled": true,
				"asset": "user://unused.png",
				"frame_width": 128,
				"frame_height": 160,
				"frame_count": 1,
				"atlas_rect": [0, 0, 128, 160],
				"render_scale": 0.035,
			},
			"SCV": {
				"kind": "unit",
				"race": "terran",
				"runtime_enabled": false,
				"asset": "user://unused.png",
				"frame_width": 32,
				"frame_height": 32,
				"frame_count": 8,
				"atlas_rect": [0, 0, 32, 32],
			},
			"MineralFieldType1": {
				"kind": "resource",
				"race": "neutral",
				"runtime_enabled": true,
				"asset": "user://unused.png",
				"frame_width": 64,
				"frame_height": 96,
				"frame_count": 1,
				"atlas_rect": [0, 0, 64, 96],
				"render_scale": 0.0151,
			},
		},
	}
	var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail += 1
		print("FAIL: cannot write gallery manifest")
		return
	file.store_string(JSON.stringify(manifest))
	file.close()
