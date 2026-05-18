extends ColorRect

## Minimap — draws entity dots, fog of war, attack indicators, and camera viewport.
##
## Parent (game_view.gd) calls queue_redraw() each tick.
## We read _entities and _camera from the GameView root.
## Sprint 4: Fog of war overlay, attack indicators (red flashes), colored unit dots.

const MINIMAP_W := 150
const MINIMAP_H := 112

var _font: Font

func _ready() -> void:
	_font = ThemeDB.fallback_font

# ── Attack indicator state ────────────────────────────────────────────────────
var _attack_indicators: Array = []  # [{position: Vector2, ttl: int}]
const ATTACK_INDICATOR_TTL := 20   # frames

func _draw() -> void:
	var game_view = get_node_or_null("/root/GameView")
	if not game_view or not game_view.has_method("_get_state_for_minimap"):
		game_view = get_parent()
		while game_view and not game_view.has_method("_get_state_for_minimap"):
			game_view = game_view.get_parent()
	if not game_view or not game_view.has_method("_get_state_for_minimap"):
		return

	var state: Dictionary = game_view._get_state_for_minimap()
	var entities: Dictionary = state.get("entities", {})
	var map_w: float = state.get("map_width", 64.0)
	var map_h: float = state.get("map_height", 64.0)
	var cam_center: Vector2 = state.get("cam_center", Vector2.ZERO)
	var vp_size: Vector2 = state.get("vp_size", Vector2(1280, 720))
	var fog_tiles: PackedInt32Array = state.get("fog_tiles", PackedInt32Array())
	var fog_w: int = state.get("fog_width", 0)
	var fog_h: int = state.get("fog_height", 0)

	# Background — distinctive dark blue-green
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.02, 0.04, 0.06))
	# Border — bright yellow to distinguish from game map
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.8, 0.7, 0.2), false, 2.0)
	# Label
	draw_string(_font, Vector2(4, 14), "MINIMAP", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color(0.6, 0.55, 0.2, 0.7))

	var sx := size.x / map_w
	var sy := size.y / map_h

	# ── Draw fog of war on minimap ──
	if fog_w > 0 and fog_h > 0 and not fog_tiles.is_empty():
		var fog_sx := size.x / float(fog_w)
		var fog_sy := size.y / float(fog_h)
		for fy in range(fog_h):
			for fx in range(fog_w):
				var fidx := fy * fog_w + fx
				if fidx >= fog_tiles.size():
					break
				var fval: int = fog_tiles[fidx]
				var f_alpha: float
				match fval:
					0: f_alpha = 0.8   # unexplored: dark
					1: f_alpha = 0.35  # explored: dimmed
					2: f_alpha = 0.0   # visible: clear
					_: f_alpha = 0.8
				if f_alpha > 0.01:
					draw_rect(
						Rect2(fx * fog_sx, fy * fog_sy, fog_sx + 1.0, fog_sy + 1.0),
						Color(0.01, 0.01, 0.03, f_alpha)
					)

	# ── Draw entity dots ──
	for eid in entities:
		var e: Dictionary = entities[eid]
		var owner: int = e.get("owner", 0)
		# TILE_SIZE=1, world coords ARE tile coords
		var px: float = e.get("px", e.get("pos_x", 0.0)) * sx
		var py: float = e.get("py", e.get("pos_y", 0.0)) * sy

		# Only show entities in visible fog (state_val == 2) for non-own entities
		# Own entities are always visible on minimap
		var show_on_minimap := true
		if owner != 1 and fog_w > 0 and fog_h > 0 and not fog_tiles.is_empty():
			# Check if entity is in visible fog area
			var fog_x := int(e.get("px", e.get("pos_x", 0.0)) * float(fog_w) / map_w)
			var fog_y := int(e.get("py", e.get("pos_y", 0.0)) * float(fog_h) / map_h)
			fog_x = clampi(fog_x, 0, fog_w - 1)
			fog_y = clampi(fog_y, 0, fog_h - 1)
			var fidx := fog_y * fog_w + fog_x
			if fidx < fog_tiles.size() and fog_tiles[fidx] < 2:
				show_on_minimap = false

		if not show_on_minimap:
			continue

		var dot_color: Color
		if owner == 1:
			dot_color = Color.CYAN
		elif owner == 2:
			dot_color = Color.MAGENTA
		elif e.get("type", "") == "resource" and e.get("resource_type", "") == "mineral":
			dot_color = Color.GOLD
		elif e.get("type", "") == "resource" and e.get("resource_type", "") == "gas":
			dot_color = Color.GREEN
		else:
			dot_color = Color.WHITE

		var dot_size := 2.0 if e.get("type", "") != "building" else 3.0
		draw_circle(Vector2(px, py), dot_size, dot_color)

	# ── Draw attack indicators ──
	for ai in _attack_indicators:
		var pos: Vector2 = ai.position
		var ttl: int = ai.ttl
		var flash_alpha: float = clampf(float(ttl) / float(ATTACK_INDICATOR_TTL), 0.0, 1.0)
		var px: float = pos.x * sx
		var py: float = pos.y * sy
		draw_circle(Vector2(px, py), 4.0, Color(1.0, 0.15, 0.15, flash_alpha * 0.8))

	# ── Camera viewport rectangle ──
	# Camera uses CENTER anchor, so cam_center = _camera.position
	# Visible world area: [cam_center - vp_size/2, cam_center + vp_size/2]
	var cam_left := (cam_center.x - vp_size.x / 2.0) * sx
	var cam_top := (cam_center.y - vp_size.y / 2.0) * sy
	var cam_w := vp_size.x * sx
	var cam_h := vp_size.y * sy
	var cam_rect := Rect2(cam_left, cam_top, cam_w, cam_h)
	cam_rect = cam_rect.intersection(Rect2(Vector2.ZERO, size))
	if cam_rect.size.x > 0 and cam_rect.size.y > 0:
		draw_rect(cam_rect, Color.WHITE, false, 1.5)

## Called by game_view to register attack events on the minimap.
func add_attack_indicator(world_pos: Vector2) -> void:
	_attack_indicators.append({
		"position": world_pos,
		"ttl": ATTACK_INDICATOR_TTL,
	})

## Called by game_view each frame to decay attack indicators.
func tick_attack_indicators() -> void:
	for ai in _attack_indicators:
		ai.ttl -= 1
	_attack_indicators = _attack_indicators.filter(func(ai): return ai.ttl > 0)
