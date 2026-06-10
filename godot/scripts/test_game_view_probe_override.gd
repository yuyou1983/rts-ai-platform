extends SceneTree

const GameViewScript := preload("res://scripts/game_view.gd")

var _pass: int = 0
var _fail: int = 0


func _init() -> void:
	_test_generated_probe_region()

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
