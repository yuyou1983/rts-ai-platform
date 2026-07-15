class_name TestModeLabelLayer
extends Control

## Screen-space label layer for Test Mode.
## Converts world-space positions to screen-space using the camera canvas transform,
## then draws text at fixed pixel size regardless of zoom level.

var _camera: Camera2D
var _font: Font
var _labels: Array = []

func setup(camera: Camera2D, font: Font) -> void:
	_camera = camera
	_font = font
	anchor_left = 0.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	mouse_filter = Control.MOUSE_FILTER_IGNORE

func set_labels(labels: Array) -> void:
	_labels = labels
	queue_redraw()

func _draw() -> void:
	if _camera == null or _font == null:
		return
	var canvas_xform: Transform2D = _camera.get_canvas_transform()
	for label in _labels:
		var world_pos: Vector2 = label.get("world_pos", Vector2.ZERO)
		var text: String = str(label.get("text", ""))
		var color: Color = label.get("color", Color.WHITE)
		var screen_pos: Vector2 = canvas_xform * world_pos
		draw_string(_font, screen_pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, color)
