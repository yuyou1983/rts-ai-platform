extends ColorRect

## Minimap — draws entity dots and camera viewport via _draw().
##
## Parent (game_view.gd) calls queue_redraw() each tick.
## We read _entities and _camera from the GameView root.

const MINIMAP_W := 150
const MINIMAP_H := 112


func _draw() -> void:
	var game_view: Node2D = get_parent().get_parent()
	if not game_view or not game_view.has_method("_get_state_for_minimap"):
		return

	var state: Dictionary = game_view._get_state_for_minimap()
	var entities: Dictionary = state.get("entities", {})
	var map_w: float = state.get("map_width", 64.0)
	var map_h: float = state.get("map_height", 64.0)
	var cam_center: Vector2 = state.get("cam_center", Vector2.ZERO)
	var vp_size: Vector2 = state.get("vp_size", Vector2(1280, 720))
	var cell_size: int = state.get("cell_size", 16)

	# Background
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.05, 0.05, 0.08))

	var sx := size.x / map_w
	var sy := size.y / map_h

	# Entity dots
	for eid in entities:
		var e: Dictionary = entities[eid]
		var owner: int = e.get("owner", 0)
		var px: float = e.get("pos_x", 0.0) * sx
		var py: float = e.get("pos_y", 0.0) * sy
		var dot_color := Color.CYAN if owner == 1 else Color.MAGENTA if owner == 2 else Color.GREEN
		draw_rect(Rect2(px - 1, py - 1, 2, 2), dot_color)

	# Camera viewport rectangle
	var cam_left := (cam_center.x - vp_size.x / 2.0) / cell_size * sx
	var cam_top := (cam_center.y - vp_size.y / 2.0) / cell_size * sy
	var cam_w := vp_size.x / cell_size * sx
	var cam_h := vp_size.y / cell_size * sy
	var cam_rect := Rect2(cam_left, cam_top, cam_w, cam_h)
	# Clamp to minimap bounds
	cam_rect = cam_rect.intersection(Rect2(Vector2.ZERO, size))
	if cam_rect.size.x > 0 and cam_rect.size.y > 0:
		draw_rect(cam_rect, Color.WHITE, false, 1.0)