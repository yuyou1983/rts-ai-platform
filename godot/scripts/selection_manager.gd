class_name SelectionManager
extends Node

## Centralized selection manager for the RTS game.
## Adapted from RTS_Selection addon for our 2D server-authoritative architecture.
##
## Entities come from SimCore state dicts (not scene tree nodes).
## Selection is stored as Dictionary {entity_id: true} matching game_view.gd pattern.
## Register as an Autoload singleton for global access.

# ── Signals ─────────────────────────────────────────────────────────────────────
signal selection_changed(selection: Dictionary)
signal added_to_selection(added: Array)
signal removed_from_selection(removed: Array)
signal control_group_created(index: int, ids: Array)
signal control_group_selected(index: int, ids: Array)
signal camera_focus_requested(center: Vector2)

# ── State ───────────────────────────────────────────────────────────────────────
## Currently selected entity IDs: {entity_id: true}
var selection: Dictionary = {}

## Currently hovered entity IDs: {entity_id: true}
var hovered: Dictionary = {}

## Control groups (hotkey groups): {int(1-9): Array of entity_ids}
var hotkey_groups: Dictionary = {}

## Entities visible on screen: {entity_id: true}
## Populated externally (e.g. by game_view each frame or on visibility change).
var selectables_on_screen: Dictionary = {}

## The "primary" selected entity — buildings take priority over units (SC1 style).
var highest_selected_id: String = ""

## Callback that returns entity data for a given entity_id.
## Should be set by game_view or another system that has access to SimCore state.
## Signature: func(entity_id: String) -> Dictionary  (empty dict if not found)
var entity_data_provider: Callable

## Callback that returns entity type string for a given entity_id.
## Falls back to entity_data_provider if not set.
## Signature: func(entity_id: String) -> String
var entity_type_provider: Callable

## Whether buildings have higher priority than units for highest_selected (SC1 style).
var building_priority: bool = true

# ── Selection Methods ───────────────────────────────────────────────────────────

## Add multiple entity_ids to the selection at once.
func add_to_selection_bulk(ids: Array) -> void:
	var actually_added: Array = []
	for eid in ids:
		var key: String = str(eid)
		if not selection.has(key):
			selection[key] = true
			actually_added.append(key)
	if actually_added.is_empty():
		return
	added_to_selection.emit(actually_added)
	selection_changed.emit(selection)
	_update_highest_selected()


## Remove a single entity_id from the selection.
func remove_from_selection(entity_id: String) -> void:
	var key: String = str(entity_id)
	if not selection.has(key):
		return
	selection.erase(key)
	removed_from_selection.emit([key])
	selection_changed.emit(selection)
	_update_highest_selected()


## Remove multiple entity_ids from the selection.
func remove_from_selection_bulk(ids: Array) -> void:
	var actually_removed: Array = []
	for eid in ids:
		var key: String = str(eid)
		if selection.has(key):
			selection.erase(key)
			actually_removed.append(key)
	if actually_removed.is_empty():
		return
	removed_from_selection.emit(actually_removed)
	selection_changed.emit(selection)
	_update_highest_selected()


## Clear the entire selection.
func remove_all_selection() -> void:
	if selection.is_empty():
		return
	var removed: Array = selection.keys()
	selection.clear()
	highest_selected_id = ""
	removed_from_selection.emit(removed)
	selection_changed.emit(selection)


## Replace the current selection with a new set of entity_ids.
func set_selection(ids: Array) -> void:
	var removed: Array = selection.keys()
	var added: Array = []
	selection.clear()
	for eid in ids:
		var key: String = str(eid)
		selection[key] = true
		if not key in removed:
			added.append(key)
	if not added.is_empty():
		added_to_selection.emit(added)
	if not removed.is_empty():
		removed_from_selection.emit(removed)
	selection_changed.emit(selection)
	_update_highest_selected()


# ── Hover Methods ───────────────────────────────────────────────────────────────

func add_to_hovered(entity_id: String) -> void:
	hovered[str(entity_id)] = true


func remove_from_hovered(entity_id: String) -> void:
	hovered.erase(str(entity_id))


func remove_all_hovered() -> void:
	hovered.clear()


# ── Control Group (Hotkey) Methods ──────────────────────────────────────────────

## Ctrl+number: Save current selection as a control group.
func create_hotkey_group(key: int) -> void:
	if key < 1 or key > 9:
		return
	var ids: Array = selection.keys()
	hotkey_groups[key] = ids.duplicate()
	control_group_created.emit(key, ids)


## Shift+number: Add current selection to an existing control group.
func add_to_hotkey_group(key: int) -> void:
	if key < 1 or key > 9:
		return
	if not hotkey_groups.has(key):
		hotkey_groups[key] = []
	var existing: Array = hotkey_groups[key]
	var current_ids: Array = selection.keys()
	for eid in current_ids:
		if not existing.has(eid):
			existing.append(eid)
	control_group_created.emit(key, existing)


## Number: Recall a control group (select those units).
func select_hotkey_group(key: int) -> void:
	if key < 1 or key > 9:
		return
	if not hotkey_groups.has(key):
		return
	var ids: Array = hotkey_groups[key]
	# Filter out dead entities (ids that are no longer selectable on screen)
	var valid_ids: Array = []
	for eid in ids:
		if selectables_on_screen.has(eid):
			valid_ids.append(eid)
	# Also keep entities that might be off-screen but still in the game state
	# (the selectables_on_screen check is just a quick filter)
	if valid_ids.is_empty() and not ids.is_empty():
		# All entities off-screen; still select them if they exist in game state
		valid_ids = ids.duplicate()
	set_selection(valid_ids)
	control_group_selected.emit(key, valid_ids)


## Double-tap number: Center camera on the control group.
func jump_to_hotkey_group(key: int) -> void:
	if key < 1 or key > 9:
		return
	if not hotkey_groups.has(key):
		return
	var ids: Array = hotkey_groups[key]
	if ids.is_empty():
		return
	# Calculate center position of the group
	var center := Vector2.ZERO
	var count: int = 0
	for eid in ids:
		var pos := _get_entity_position(eid)
		if pos != Vector2.ZERO or count == 0:
			center += pos
			count += 1
	if count > 0:
		center /= float(count)
		camera_focus_requested.emit(center)
	# Also select the group
	select_hotkey_group(key)


## Whether a given control group key has been assigned.
func has_hotkey_group(key: int) -> bool:
	return hotkey_groups.has(key) and not hotkey_groups[key].is_empty()


# ── Smart Selection ────────────────────────────────────────────────────────────

## Ctrl+click: Select all entities of the same type currently visible on screen.
func select_all_similar_on_screen(entity_id: String) -> void:
	var target_type: String = _get_entity_type(entity_id)
	var target_building_type: String = _get_entity_building_type(entity_id)
	if target_type.is_empty():
		return

	var similar_ids: Array = []
	for eid in selectables_on_screen:
		var etype: String = _get_entity_type(eid)
		if etype != target_type:
			continue
		# For buildings, match building_type as well
		if target_type == "building":
			var btype: String = _get_entity_building_type(eid)
			if btype != target_building_type:
				continue
		# Only select own entities (owner == local player)
		if not _is_own_entity(eid):
			continue
		similar_ids.append(eid)

	set_selection(similar_ids)


# ── Query Methods ───────────────────────────────────────────────────────────────

func get_selected_ids() -> Array:
	return selection.keys()


func is_selected(entity_id: String) -> bool:
	return selection.has(str(entity_id))


func get_selection_size() -> int:
	return selection.size()


# ── Highest Selected ───────────────────────────────────────────────────────────

## Determine the "primary" selected entity. Buildings take priority over units
## in SC1 style (building_priority = true).
func update_highest_selected() -> void:
	_update_highest_selected()


func _update_highest_selected() -> void:
	if selection.is_empty():
		highest_selected_id = ""
		return

	var best_id: String = ""
	var best_is_building: bool = false

	for eid in selection:
		var etype: String = _get_entity_type(eid)
		var is_building: bool = (etype == "building")

		if best_id.is_empty():
			best_id = eid
			best_is_building = is_building
			continue

		if building_priority:
			# Buildings beat units
			if is_building and not best_is_building:
				best_id = eid
				best_is_building = true
			# If same category, keep first (or could compare health, etc.)
		else:
			# Units beat buildings (reverse priority)
			if not is_building and best_is_building:
				best_id = eid
				best_is_building = false

	highest_selected_id = best_id


# ── Internal Helpers ────────────────────────────────────────────────────────────

func _get_entity_type(entity_id: String) -> String:
	if entity_type_provider.is_valid():
		return entity_type_provider.call(entity_id)
	if entity_data_provider.is_valid():
		var data: Dictionary = entity_data_provider.call(entity_id)
		if not data.is_empty():
			return str(data.get("entity_type", data.get("type", "")))
	return ""


func _get_entity_building_type(entity_id: String) -> String:
	if entity_data_provider.is_valid():
		var data: Dictionary = entity_data_provider.call(entity_id)
		if not data.is_empty():
			return str(data.get("building_type", ""))
	return ""


func _get_entity_position(entity_id: String) -> Vector2:
	if entity_data_provider.is_valid():
		var data: Dictionary = entity_data_provider.call(entity_id)
		if not data.is_empty():
			var px: float = float(data.get("px", data.get("pos_x", 0.0)))
			var py: float = float(data.get("py", data.get("pos_y", 0.0)))
			return Vector2(px, py)
	return Vector2.ZERO


func _is_own_entity(entity_id: String) -> bool:
	if entity_data_provider.is_valid():
		var data: Dictionary = entity_data_provider.call(entity_id)
		if not data.is_empty():
			return int(data.get("owner", 0)) == 1  # P1 = local human
	return false


# ── Cleanup ────────────────────────────────────────────────────────────────────

## Remove entity IDs from selection/hover/groups that no longer exist.
## Call this periodically or when entities are destroyed.
func purge_invalid_ids(valid_ids: Array) -> void:
	var valid_set: Dictionary = {}
	for vid in valid_ids:
		valid_set[str(vid)] = true

	# Purge selection
	var removed: Array = []
	for eid in selection:
		if not valid_set.has(eid):
			removed.append(eid)
	for eid in removed:
		selection.erase(eid)

	if not removed.is_empty():
		removed_from_selection.emit(removed)
		selection_changed.emit(selection)
		_update_highest_selected()

	# Purge hovered
	for eid in hovered.keys():
		if not valid_set.has(eid):
			hovered.erase(eid)

	# Purge hotkey groups
	for key in hotkey_groups:
		var group: Array = hotkey_groups[key]
		hotkey_groups[key] = group.filter(_is_id_valid.bind(valid_set))

static func _is_id_valid(eid: String, valid_set: Dictionary) -> bool:
	return valid_set.has(eid)
