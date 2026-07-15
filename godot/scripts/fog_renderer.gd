extends Node2D

## Renders fog-of-war tiles based on SimCore visibility data.
## Three-state fog (SC1-style):
##   0 = unexplored (black, alpha 0.92)
##   1 = explored    (dark shroud, alpha 0.55)
##   2 = visible     (transparent, alpha 0.0)
##
## Edge smoothing is preserved at reduced amplitude (blend_factor 0.15).

var _tile_size: int = 1  # TILE_SIZE=1, world coords ARE tile coords
var _fog_data: PackedByteArray = []
var _width: int = 0
var _height: int = 0

# Gradient rendering: we compute alpha per tile with neighbor-aware blending
# for smooth edges — but at reduced amplitude to avoid modern gradient fog.
const GRADIENT_RADIUS := 1  ## How many tiles to consider for gradient smoothing

func update_fog(fog_tiles: PackedByteArray, width: int, height: int) -> void:
	_fog_data = fog_tiles
	_width = width
	_height = height
	queue_redraw()

func _draw() -> void:
	if _fog_data.is_empty() or _width <= 0 or _height <= 0:
		return

	var map_px := float(_width) * _tile_size
	var map_py := float(_height) * _tile_size
	var tile_w := map_px / float(_width)
	var tile_h := map_py / float(_height)

	# Precompute fog values into a 2D array for neighbor lookups
	var fog_grid: Array = []
	fog_grid.resize(_height)
	for gy in range(_height):
		fog_grid[gy] = []
		fog_grid[gy].resize(_width)
		for gx in range(_width):
			var idx := gy * _width + gx
			if idx < _fog_data.size():
				fog_grid[gy][gx] = _fog_data[idx]
			else:
				fog_grid[gy][gx] = 0

	# Draw each fog tile with gradient-smoothed alpha
	for gy in range(_height):
		for gx in range(_width):
			var state_val: int = fog_grid[gy][gx]

			# Compute smoothed alpha based on neighbors
			var alpha := _compute_fog_alpha(gx, gy, state_val, fog_grid)

			if alpha < 0.01:
				continue

			var px: float = gx * tile_w
			var py: float = gy * tile_h

			# Choose color based on state:
			# 0 (unexplored): black
			# 1 (explored): dark shroud with slight blue tint
			# 2 (visible): don't draw (alpha should be ~0)
			var color: Color
			match state_val:
				0:
					color = Color(0.0, 0.0, 0.0, alpha)
				1:
					color = Color(0.03, 0.03, 0.06, alpha)
				2:
					# Visible tiles: no fog drawn
					# (only residual alpha from neighbor blending)
					color = Color(0.0, 0.0, 0.0, alpha)
				_:
					color = Color(0.0, 0.0, 0.0, alpha)

			draw_rect(
				Rect2(px, py, tile_w + 1.0, tile_h + 1.0),
				color
			)

## Compute a gradient-smoothed alpha for a fog tile by considering
## the visibility states of neighboring tiles. Reduced blend factor
## prevents the modern gradient-fog look.
func _compute_fog_alpha(gx: int, gy: int, state_val: int, fog_grid: Array) -> float:
	# Base alpha per state (SC1 three-state values)
	var base_alpha: float
	match state_val:
		0:
			base_alpha = 0.92  # unexplored: near-black
		1:
			base_alpha = 0.55  # explored: dark shroud
		2:
			base_alpha = 0.0   # visible: transparent
		_:
			base_alpha = 0.92

	# If fully visible with no fog, skip gradient calculation
	if state_val == 2 and base_alpha <= 0.01:
		return 0.0

	# Check if we're at a fog boundary (near transition between states)
	var is_boundary := false
	var neighbor_sum: float = 0.0
	var neighbor_count: int = 0

	for dy in range(-GRADIENT_RADIUS, GRADIENT_RADIUS + 1):
		for dx in range(-GRADIENT_RADIUS, GRADIENT_RADIUS + 1):
			if dx == 0 and dy == 0:
				continue
			var nx: int = gx + dx
			var ny: int = gy + dy
			if nx < 0 or nx >= _width or ny < 0 or ny >= _height:
				neighbor_sum += 0.0  # Off-map counts as unexplored
				neighbor_count += 1
				if state_val != 0:
					is_boundary = true
				continue
			var n_val: int = fog_grid[ny][nx]
			var n_alpha: float
			match n_val:
				0: n_alpha = 0.92
				1: n_alpha = 0.55
				2: n_alpha = 0.0
				_: n_alpha = 0.92
			neighbor_sum += n_alpha
			neighbor_count += 1
			if n_val != state_val:
				is_boundary = true

	# If not at a boundary, use the base alpha directly (no smoothing needed)
	if not is_boundary:
		return base_alpha

	# At boundaries: blend between own alpha and neighbor average
	# Reduced blend_factor (0.15) prevents modern gradient fog look
	var neighbor_avg: float = neighbor_sum / float(neighbor_count) if neighbor_count > 0 else base_alpha
	var blend_factor := 0.15
	var smoothed := lerpf(base_alpha, neighbor_avg, blend_factor)

	return clampf(smoothed, 0.0, 1.0)
