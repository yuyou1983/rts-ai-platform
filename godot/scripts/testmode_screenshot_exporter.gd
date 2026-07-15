class_name TestmodeScreenshotExporter
extends Node
## Exports all four Test Mode gallery views as PNG screenshots.
## Called via F11 key from TestModeGallery.

var _gallery: TestModeGallery = null
var _output_dir: String = ""


func setup(gallery: TestModeGallery, output_dir: String = "") -> void:
	_gallery = gallery
	_output_dir = output_dir


func export_all_modes(output_dir: String = "") -> void:
	var dir := output_dir if output_dir != "" else _output_dir
	if dir == "":
		dir = "user://testmode_screenshots"
	var abs_dir := DirAccess.open(dir)
	if abs_dir == null:
		DirAccess.make_dir_recursive_absolute(dir)

	var timestamp := Time.get_datetime_string_from_system().replace(":", "")
	var subdir := dir.path_join(timestamp)
	DirAccess.make_dir_recursive_absolute(subdir)

	for mode in ["roster", "scale", "animation", "combat"]:
		if _gallery:
			_gallery._gallery_mode = mode
			_gallery.build()
		await get_tree().process_frame
		await get_tree().process_frame
		var img := get_viewport().get_texture().get_image()
		var path := subdir.path_join("%s.png" % mode)
		img.save_png(path)
		print("[ScreenshotExporter] Saved %s" % path)

	if _gallery:
		_gallery._gallery_mode = "roster"
		_gallery.build()
	print("[ScreenshotExporter] All modes exported to %s" % subdir)
