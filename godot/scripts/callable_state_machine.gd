## A flexible state machine using StringName keys and Callable callbacks.
## Adapted from RTS_CallableStateMachine for 2D, server-authoritative architecture.
## Supports deferred state transitions to avoid re-entrancy during update/enter/leave.
## Extends RefCounted — no Node dependency, safe to own from any object.
class_name CallableStateMachine
extends RefCounted

signal exit_state(previous_state: StringName)
signal enter_state(new_state: StringName)

## Maps StringName state keys to dictionaries: { enter: Callable, leave: Callable, update: Callable }
var _states: Dictionary = {}
var _current_state: StringName = &""
var _previous_state: StringName = &""
var _pending_state: StringName = &""


func add_state(
	state_name: StringName,
	enter_callable: Callable = Callable(),
	leave_callable: Callable = Callable(),
	update_callable: Callable = Callable()
) -> void:
	_states[state_name] = {
		&"enter": enter_callable,
		&"leave": leave_callable,
		&"update": update_callable,
	}


func remove_state(state_name: StringName) -> void:
	_states.erase(state_name)


func has_state(state_name: StringName) -> bool:
	return _states.has(state_name)


func start(initial_state: StringName) -> void:
	if _current_state != &"":
		push_warning(
			"CallableStateMachine: Already started with state '%s'. Use change_state() instead."
			% _current_state
		)
		return
	if not _states.has(initial_state):
		push_error("CallableStateMachine: Initial state '%s' not found." % initial_state)
		return

	_current_state = initial_state
	_previous_state = &""
	var enter_cb: Callable = _states[initial_state].get(&"enter", Callable())
	if enter_cb.is_valid():
		enter_cb.call()
	enter_state.emit(initial_state)


## Request a deferred state transition. Only one pending transition is allowed;
## subsequent calls within the same frame are rejected with a warning.
func change_state(new_state: StringName) -> void:
	if _pending_state != &"":
		push_warning(
			"CallableStateMachine: Transition already pending to '%s'. Ignoring change to '%s'."
			% [_pending_state, new_state]
		)
		return
	if _current_state == &"":
		push_error("CallableStateMachine: Not started. Call start() first.")
		return
	if not _states.has(new_state):
		push_error("CallableStateMachine: State '%s' not found." % new_state)
		return

	_pending_state = new_state
	_apply_pending_state.call_deferred()


func _apply_pending_state() -> void:
	if _pending_state == &"":
		return
	var new_state := _pending_state
	_pending_state = &""

	# --- leave old state ---
	var old_state := _current_state
	var old_data: Dictionary = _states.get(old_state, {})
	var leave_cb: Callable = old_data.get(&"leave", Callable())
	if leave_cb.is_valid():
		leave_cb.call()
	exit_state.emit(old_state)

	# --- transition ---
	_previous_state = old_state
	_current_state = new_state

	# --- enter new state ---
	var new_data: Dictionary = _states.get(new_state, {})
	var enter_cb: Callable = new_data.get(&"enter", Callable())
	if enter_cb.is_valid():
		enter_cb.call()
	enter_state.emit(new_state)


## Call once per frame (e.g. from _process or _physics_process) to tick the current state.
func update(delta: float) -> void:
	if _current_state == &"" or _pending_state != &"":
		return
	var data: Dictionary = _states.get(_current_state, {})
	var update_cb: Callable = data.get(&"update", Callable())
	if update_cb.is_valid():
		update_cb.call(delta)


func is_in_state(state_name: StringName) -> bool:
	return _current_state == state_name


func get_current_state() -> StringName:
	return _current_state


func get_previous_state() -> StringName:
	return _previous_state