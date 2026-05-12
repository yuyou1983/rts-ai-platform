## Ability Manager — server-authoritative ability input handler.
##
## Adapted from the RTS_AbilityManager addon for our architecture where abilities
## DON'T execute locally. Instead they build command dicts and emit them via
## EventBus.command_issued so GrpcBridge can submit them to SimCore.
##
## Selection is Dictionary {entity_id: true} (not Array[RTS_Selectable]).
## Register as an Autoload singleton (AbilityManager) for global access.
extends Node

# ── Preloads ─────────────────────────────────────────────────────────────────
const AbilityResource := preload("res://scripts/ability_resource.gd")

# ── Signals ──────────────────────────────────────────────────────────────────

signal abilities_changed()
signal ability_initiated(ability_id: StringName)
signal ability_terminated(ability_id: StringName, cancelled: bool)
signal abilities_activated(ability_ids: Array)

# ── Internal State Machine ──────────────────────────────────────────────────

enum State {
	NO_ACTIVE_ABILITIES,           ## No ability pending; hotkeys are accepted
	ACTIVE_ABILITIES,              ## A no-target ability is executing
	QUEUED_CLICK_ABILITY_VALID,    ## A click-target ability is awaiting valid click
	QUEUED_CLICK_ABILITY_INVALID,  ## A click-target ability awaiting click (target invalid / cursor not ready)
}

# ── Public State ────────────────────────────────────────────────────────────

## Maps ability_id → Array of entity_ids that possess it.
## Rebuilt whenever selection changes.
var selected_abilities: Dictionary = {}

## The ability currently awaiting a target click (empty StringName if none).
var initiated_ability: StringName = &""

## Commands queued via Shift+click, awaiting flush to SimCore.
var command_queue: Array = []

# ── Internal State ──────────────────────────────────────────────────────────

var _state: State = State.NO_ACTIVE_ABILITIES
var _ability_registry: Dictionary = {}  # {ability_id: AbilityResource}
var _entity_data_provider: Callable    # func(entity_id: String) -> Dictionary
var _event_bus: Node = null            # Cached reference to EventBus autoload

# ── Built-in Hotkey Mapping ─────────────────────────────────────────────────
# Maps Key constants to ability ids. Extended at runtime by AbilityResources.

var _hotkey_map: Dictionary = {
	KEY_M: &"move",
	KEY_S: &"stop",
	KEY_A: &"attack",
	KEY_P: &"patrol",
	KEY_H: &"hold",
	KEY_G: &"gather",
	KEY_B: &"build",
}

# ── Lifecycle ───────────────────────────────────────────────────────────────

func _ready() -> void:
	_event_bus = get_node_or_null("/root/EventBus")
	if _event_bus == null:
		push_warning("[AbilityManager] EventBus autoload not found; commands will not be forwarded.")
	_load_ability_registry()


# ── Public API ──────────────────────────────────────────────────────────────

## Set the callback that returns entity data from SimCore state.
## Signature: func(entity_id: String) -> Dictionary
func set_entity_data_provider(provider: Callable) -> void:
	_entity_data_provider = provider


## Called whenever the selection changes. Rebuilds selected_abilities so the HUD
## can show the intersection of abilities the selected entities share.
##
## [param selection] is {entity_id: true}.
func on_selection_changed(selection: Dictionary) -> void:
	selected_abilities.clear()

	if selection.is_empty():
		abilities_changed.emit()
		return

	# Count how many selected entities have each ability
	var ability_counts: Dictionary = {}  # {ability_id: count}

	for eid in selection:
		var entity_data: Dictionary = _get_entity_data(str(eid))
		if entity_data.is_empty():
			continue
		var entity_abilities: Array = _get_abilities_for_entity(entity_data)
		for aid in entity_abilities:
			var aid_sn: StringName = StringName(aid)
			if not ability_counts.has(aid_sn):
				ability_counts[aid_sn] = 0
			ability_counts[aid_sn] += 1

	# Build selected_abilities: ability_id → [entity_ids that have it]
	for aid in ability_counts:
		var entity_ids: Array = []
		for eid in selection:
			var entity_data: Dictionary = _get_entity_data(str(eid))
			if not entity_data.is_empty():
				var entity_abilities: Array = _get_abilities_for_entity(entity_data)
				if aid in entity_abilities:
					entity_ids.append(str(eid))
		selected_abilities[aid] = entity_ids

	# Clear any pending ability if it's no longer available
	if initiated_ability != &"" and not selected_abilities.has(initiated_ability):
		clear_queued_ability(true)

	abilities_changed.emit()


## Main input handler. Returns true if the input was consumed (ability hotkey
## pressed or target click processed).
##
## [param input_event] is the raw InputEvent.
## [param selection] is {entity_id: true}.
## [param mouse_world_pos] is the cursor position in world coordinates.
func process_ability_input(
	input_event: InputEvent,
	selection: Dictionary,
	mouse_world_pos: Vector2
) -> bool:
	if selection.is_empty():
		if initiated_ability != &"":
			clear_queued_ability(true)
		return false

	# ── No pending ability: check hotkeys ─────────────────────────────────
	if initiated_ability == &"":
		if input_event is InputEventKey and input_event.pressed and not input_event.echo:
			var keycode: Key = input_event.keycode
			if _hotkey_map.has(keycode):
				var ability_id: StringName = _hotkey_map[keycode]
				if selected_abilities.has(ability_id):
					_initiate_ability(ability_id)
					return true
			# Also check AbilityResource hotkeys from registry
			for aid in _ability_registry:
				var res: AbilityResource = _ability_registry[aid]
				if res.hotkey == keycode and selected_abilities.has(aid):
					_initiate_ability(aid)
					return true
		return false

	# ── Pending ability: check target click ────────────────────────────────
	var ability_res: AbilityResource = _get_ability_resource(initiated_ability)
	if ability_res == null:
		clear_queued_ability(true)
		return false

	var t_type: int = ability_res.target_type

	# Right-click cancels a pending ability
	if input_event is InputEventMouseButton \
		and input_event.button_index == MOUSE_BUTTON_RIGHT \
		and input_event.pressed:
		clear_queued_ability(true)
		return true

	# Left-click: attempt to resolve target
	if input_event is InputEventMouseButton \
		and input_event.button_index == MOUSE_BUTTON_LEFT \
		and input_event.pressed:

		var shift_held: bool = Input.is_key_pressed(KEY_SHIFT)
		var target: Dictionary = _resolve_target(
			initiated_ability, t_type, mouse_world_pos
		)

		if target.is_empty():
			# Invalid target — stay in queued state
			_state = State.QUEUED_CLICK_ABILITY_INVALID
			return true

		# Valid target found
		var entity_ids: Array = selected_abilities.get(initiated_ability, [])

		if shift_held and ability_res.is_chainable:
			# Queue instead of immediate submit
			var cmd: Dictionary = _build_command(initiated_ability, entity_ids, target)
			queue_command(cmd)
		else:
			activate_abilities(initiated_ability, entity_ids, target)

		# If ability clears targets (most do), exit initiated state.
		# Patrol / attack-move keep it for waypoint chaining.
		if not ability_res.dont_clear_targets:
			clear_queued_ability(false)
		else:
			# Stay in initiated mode for Shift-style chaining
			_state = State.QUEUED_CLICK_ABILITY_VALID

		return true

	return false


## Build command dicts for the given ability and entities, then emit them via
## EventBus.command_issued.
func activate_abilities(
	ability_id: StringName,
	entity_ids: Array,
	target: Dictionary
) -> void:
	if entity_ids.is_empty() or target.is_empty():
		return

	var ability_res: AbilityResource = _get_ability_resource(ability_id)

	var commands: Array = []
	if ability_res != null and ability_res.activate_as_group:
		commands = coordinate_activation(ability_id, entity_ids, target)
	else:
		for eid in entity_ids:
			var cmd: Dictionary = _build_command(ability_id, [eid], target)
			commands.append(cmd)

	# Emit each command via EventBus
	for cmd in commands:
		_emit_command(cmd)

	var activated_ids: Array = [ability_id]
	abilities_activated.emit(activated_ids)


## For group-activated abilities (e.g. move), build one command per entity but
## with formation offsets so they spread out instead of all stacking on the
## same pixel.
func coordinate_activation(
	ability_id: StringName,
	entity_ids: Array,
	target: Dictionary
) -> Array:
	var commands: Array = []
	var count: int = entity_ids.size()
	if count == 0:
		return commands

	# Formation: arrange in a grid centered on the target position
	var cols: int = int(ceilf(sqrt(float(count))))
	var spacing: float = 32.0  # world-unit spacing between units in formation

	for i in range(count):
		var row: int = i / cols
		var col: int = i % cols
		var offset := Vector2(
			(float(col) - float(cols - 1) * 0.5) * spacing,
			(float(row) - float(count / cols - 1) * 0.5) * spacing
		)

		var entity_target: Dictionary = target.duplicate()
		# Apply formation offset to position targets
		if entity_target.has("target_x"):
			entity_target["target_x"] = float(entity_target["target_x"]) + offset.x
			entity_target["target_y"] = float(entity_target["target_y"]) + offset.y

		var cmd: Dictionary = _build_command(ability_id, [entity_ids[i]], entity_target)
		commands.append(cmd)

	return commands


## Cancel or finish the currently pending click-target ability.
func clear_queued_ability(cancelled: bool) -> void:
	if initiated_ability == &"":
		return
	var prev: StringName = initiated_ability
	initiated_ability = &""
	_state = State.NO_ACTIVE_ABILITIES
	ability_terminated.emit(prev, cancelled)


## Add a command to the Shift-queue.
func queue_command(command: Dictionary) -> void:
	command_queue.append(command)


## Submit all queued commands via EventBus and clear the queue.
func flush_queue() -> void:
	if command_queue.is_empty():
		return
	for cmd in command_queue:
		_emit_command(cmd)
	command_queue.clear()


# ── Private Helpers ──────────────────────────────────────────────────────────

func _emit_command(cmd: Dictionary) -> void:
	if _event_bus != null and _event_bus.has_signal("command_issued"):
		_event_bus.command_issued.emit(cmd)
	else:
		push_warning("[AbilityManager] Cannot emit command — EventBus not available: %s" % cmd)


func _initiate_ability(ability_id: StringName) -> void:
	var ability_res: AbilityResource = _get_ability_resource(ability_id)
	initiated_ability = ability_id
	ability_initiated.emit(ability_id)

	if ability_res == null or ability_res.target_type == 0:
		# No-target ability (stop, hold): activate immediately
		var entity_ids: Array = selected_abilities.get(ability_id, [])
		activate_abilities(ability_id, entity_ids, {})
		clear_queued_ability(false)
		_state = State.ACTIVE_ABILITIES
	else:
		# Needs a target click
		_state = State.QUEUED_CLICK_ABILITY_VALID


func _resolve_target(
	ability_id: StringName,
	target_type: int,
	mouse_world_pos: Vector2
) -> Dictionary:
	var target: Dictionary = {}

	# Try entity target first (for target_type 2 or 3)
	if target_type == 2 or target_type == 3:
		var clicked_entity: Dictionary = _entity_at_world_pos(mouse_world_pos)
		if not clicked_entity.is_empty():
			target["target_entity_id"] = str(clicked_entity.get("id", ""))
			# For attack: also store position as fallback
			target["target_x"] = float(clicked_entity.get("px", mouse_world_pos.x))
			target["target_y"] = float(clicked_entity.get("py", mouse_world_pos.y))
			return target

	# Try position target (for target_type 1 or 3)
	if target_type == 1 or target_type == 3:
		target["target_x"] = mouse_world_pos.x
		target["target_y"] = mouse_world_pos.y
		return target

	# target_type 0 = self / none — return empty (handled in _initiate_ability)
	return target


func _build_command(
	ability_id: StringName,
	entity_ids: Array,
	target: Dictionary
) -> Dictionary:
	# Build the command dict expected by SimCore.
	# The "action" field maps ability_id to the SimCore command name.
	var action_name: String = _ability_id_to_action(ability_id)

	var cmd: Dictionary = {
		"action": action_name,
		"issuer": 1,  # P1 = local human player
	}

	# Attach entity IDs
	if entity_ids.size() == 1:
		# Single-entity commands use "unit_id" / "attacker_id" / etc.
		var eid: String = str(entity_ids[0])
		match action_name:
			"move":
				cmd["unit_id"] = eid
			"attack":
				cmd["attacker_id"] = eid
			"gather":
				cmd["worker_id"] = eid
			"build":
				cmd["builder_id"] = eid
			"train":
				cmd["building_id"] = eid
			_:
				cmd["unit_id"] = eid
	else:
		# Multi-entity: store as array (GrpcBridge handles batching)
		cmd["unit_ids"] = entity_ids.map(func(e): return str(e))

	# Merge target data
	cmd.merge(target, true)

	return cmd


func _ability_id_to_action(ability_id: StringName) -> String:
	# Map our internal ability IDs to SimCore action names
	match ability_id:
		&"move":
			return "move"
		&"stop":
			return "stop"
		&"attack":
			return "attack"
		&"patrol":
			return "patrol"
		&"hold":
			return "hold"
		&"gather":
			return "gather"
		&"build":
			return "build"
		&"train":
			return "train"
		_:
			return str(ability_id)


func _get_ability_resource(ability_id: StringName) -> AbilityResource:
	if _ability_registry.has(ability_id):
		return _ability_registry[ability_id]
	return null


func _get_entity_data(entity_id: String) -> Dictionary:
	if _entity_data_provider.is_valid():
		return _entity_data_provider.call(entity_id)
	return {}


func _entity_at_world_pos(world_pos: Vector2, radius: float = 20.0) -> Dictionary:
	# Delegate to the entity_data_provider to find entity at world position.
	# Falls back to a simple distance check if a provider returns raw entity list.
	if _entity_data_provider.is_valid():
		var result: Dictionary = _entity_data_provider.call("__at_pos__", world_pos, radius)
		if not result.is_empty():
			return result
	# No spatial lookup available — return empty
	return {}


## Determine which abilities an entity possesses based on its type.
## Maps entity_type → list of ability_ids from the built-in set.
func _get_abilities_for_entity(entity_data: Dictionary) -> Array:
	var etype: String = str(entity_data.get("entity_type", entity_data.get("type", "")))
	var btype: String = str(entity_data.get("building_type", ""))

	match etype:
		"worker":
			return [&"move", &"stop", &"attack", &"patrol", &"hold", &"gather", &"build"]
		"soldier", "scout":
			return [&"move", &"stop", &"attack", &"patrol", &"hold"]
		"building":
			if btype == "base":
				return [&"train"]
			elif btype == "barracks":
				return [&"train"]
			else:
				return [&"stop", &"hold"]
		_:
			return []


## Load AbilityResources from disk and register them.
## Also syncs their hotkeys into _hotkey_map.
func _load_ability_registry() -> void:
	# Load built-in default AbilityResources for the standard hotkey set
	var defaults: Array = [
		_built_in_resource(&"move", "Move", "Move to target position", KEY_M, 1, true, true, true),
		_built_in_resource(&"stop", "Stop", "Cancel current action", KEY_S, 0, true, true, true, false),
		_built_in_resource(&"attack", "Attack", "Attack target", KEY_A, 3, true, true, false),
		_built_in_resource(&"patrol", "Patrol", "Patrol between points", KEY_P, 1, true, true, true, true, true),
		_built_in_resource(&"hold", "Hold Position", "Hold position and attack nearby", KEY_H, 0, true, true, true, false),
		_built_in_resource(&"gather", "Gather", "Gather resources from target", KEY_G, 2, true, true, false),
		_built_in_resource(&"build", "Build", "Build a structure", KEY_B, 1, true, true, false),
		_built_in_resource(&"train", "Train", "Train a unit", KEY_T, 0, true, false, true, false),
	]

	for res in defaults:
		_ability_registry[res.id] = res
		if res.hotkey != KEY_NONE:
			_hotkey_map[res.hotkey] = res.id

	# Attempt to load additional AbilityResources from project resources
	var dir := DirAccess.open("res://resources/abilities/")
	if dir != null:
		dir.list_dir_begin()
		var fname: String = dir.get_next()
		while fname != "":
			if fname.get_extension() == "tres" or fname.get_extension() == "res":
				var res: Resource = load("res://resources/abilities/" + fname)
				if res is AbilityResource:
					_ability_registry[res.id] = res
					if res.hotkey != KEY_NONE:
						_hotkey_map[res.hotkey] = res.id
			fname = dir.get_next()
		dir.list_dir_end()


func _built_in_resource(
	p_id: StringName,
	p_display_name: String,
	p_description: String,
	p_hotkey: Key,
	p_target_type: int,
	p_is_chainable: bool = true,
	p_allow_multiple: bool = true,
	p_as_group: bool = true,
	p_dont_clear: bool = false,
	p_auto_move: bool = true,
) -> AbilityResource:
	var res: AbilityResource = AbilityResource.new()
	res.id = p_id
	res.display_name = p_display_name
	res.description = p_description
	res.hotkey = p_hotkey
	res.target_type = p_target_type
	res.is_chainable = p_is_chainable
	res.allow_trigger_multiple = p_allow_multiple
	res.activate_as_group = p_as_group
	res.dont_clear_targets = p_dont_clear
	res.auto_move_to_cast = p_auto_move
	return res