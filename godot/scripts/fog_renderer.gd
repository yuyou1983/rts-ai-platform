class_name FogRenderer
extends Node2D

## Renders fog-of-war tiles based on SimCore visibility data.
## 0=unexplored (black), 1=explored (dark), 2=visible (clear)

var _tile_size: int = 32
var _fog_data: PackedByteArray = []
var _width: int = 0
var _height: int = 0


func update_fog(fog_tiles: PackedByteArray, width: int, height: int) -> void:
	_fog_data = fog_tiles
	_width = width
	_height = height
	queue_redraw()


func _draw() -> void:
	if _fog_data.is_empty():
		return
	for y in range(_height):
		for x in range(_width):
			var idx := y * _width + x
			if idx >= _fog_data.size():
				break
			var val := _fog_data[idx]
			var color: Color
			match val:
				0: color = Color(0, 0, 0, 1.0)        # unexplored
				1: color = Color(0, 0, 0, 0.6)        # explored
				2: color = Color(0, 0, 0, 0.0)        # visible
				_: color = Color(0, 0, 0, 1.0)
			if color.a > 0.01:
				draw_rect(
					Rect2(x * _tile_size, y * _tile_size, _tile_size, _tile_size),
					color
				)