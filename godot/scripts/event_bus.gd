@warning_ignore("UNUSED_SIGNAL")
class_name EventBus
extends Node

## Central event bus for the RTS game.
## Register as an Autoload singleton (e.g. EventBus) for global access.
## Thin helper methods wrap emit_signal for convenience and call-site clarity.

# ── Selection ────────────────────────────────────────────────────────────────
signal selection_changed(selection)
signal entity_selected(entity_id: int)
signal entity_deselected(entity_id: int)

# ── Commands & Abilities ──────────────────────────────────────────────────────
signal command_issued(command)
signal ability_activated(ability_name: StringName, target)

# ── Game Flow ─────────────────────────────────────────────────────────────────
signal game_started(state)
signal game_over(winner, tick: int)

# ── Camera ────────────────────────────────────────────────────────────────────
signal camera_moved(position: Vector2)
signal camera_zoom_changed(zoom: Vector2)

# ── Control Groups ─────────────────────────────────────────────────────────────
signal control_group_created(index: int, ids: Array)
signal control_group_selected(index: int, ids: Array)

# ── Fog of War ────────────────────────────────────────────────────────────────
signal fog_updated(player: int)

# ── Resources ────────────────────────────────────────────────────────────────
signal resources_updated(minerals: int, gas: int, supply_used: int, supply_cap: int)

# ── Rally Point ──────────────────────────────────────────────────────────────
signal rally_point_set(building_id: String, position: Vector2)
signal rally_point_cleared(building_id: String)

# ── Combat Events ────────────────────────────────────────────────────────────
signal attack_occurred(position: Vector2, attacker_owner: int)

# ── Selection helpers ────────────────────────────────────────────────────────

func emit_selection_changed(selection) -> void:
	selection_changed.emit(selection)

func emit_entity_selected(entity_id: int) -> void:
	entity_selected.emit(entity_id)

func emit_entity_deselected(entity_id: int) -> void:
	entity_deselected.emit(entity_id)

# ── Command / Ability helpers ──────────────────────────────────────────────────

func emit_command_issued(command) -> void:
	command_issued.emit(command)

func emit_ability_activated(ability_name: StringName, target = null) -> void:
	ability_activated.emit(ability_name, target)

# ── Game flow helpers ─────────────────────────────────────────────────────────

func emit_game_started(state) -> void:
	game_started.emit(state)

func emit_game_over(winner, tick: int) -> void:
	game_over.emit(winner, tick)

# ── Camera helpers ────────────────────────────────────────────────────────────

func emit_camera_moved(position: Vector2) -> void:
	camera_moved.emit(position)

func emit_camera_zoom_changed(zoom: Vector2) -> void:
	camera_zoom_changed.emit(zoom)

# ── Control Group helpers ────────────────────────────────────────────────────

func emit_control_group_created(index: int, ids: Array) -> void:
	control_group_created.emit(index, ids)

func emit_control_group_selected(index: int, ids: Array) -> void:
	control_group_selected.emit(index, ids)

# ── Fog helpers ───────────────────────────────────────────────────────────────

func emit_fog_updated(player: int) -> void:
	fog_updated.emit(player)

# ── Resource helpers ──────────────────────────────────────────────────────────

func emit_resources_updated(minerals: int, gas: int, supply_used: int, supply_cap: int) -> void:
	resources_updated.emit(minerals, gas, supply_used, supply_cap)

# ── Rally point helpers ──────────────────────────────────────────────────────

func emit_rally_point_set(building_id: String, position: Vector2) -> void:
	rally_point_set.emit(building_id, position)

func emit_rally_point_cleared(building_id: String) -> void:
	rally_point_cleared.emit(building_id)

# ── Combat helpers ───────────────────────────────────────────────────────────

func emit_attack_occurred(position: Vector2, attacker_owner: int) -> void:
	attack_occurred.emit(position, attacker_owner)