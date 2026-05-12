extends HBoxContainer

## UI overlay showing which control groups (1-9) are currently assigned.
## Listens to EventBus signals for control_group_created / control_group_selected.
## Minimal styling: each slot shows the group number; opacity distinguishes
## assigned (full opacity) from empty (dimmed).

const GROUP_COUNT := 9

## Reference to the SelectionManager autoload (set in _ready).
var _selection_manager: Node

## Per-slot UI elements.
var _labels: Array[Label] = []       # index 0 → group 1, …, index 8 → group 9
var _backgrounds: Array[Panel] = []  # subtle background panels

# ── Config ──────────────────────────────────────────────────────────────────────
@export_group("Style")
@export var assigned_opacity: float = 1.0
@export var empty_opacity: float = 0.3
@export var slot_min_width: int = 32
@export var slot_min_height: int = 28
@export var assigned_color: Color = Color(0.3, 0.85, 0.3)
@export var empty_color: Color = Color(0.7, 0.7, 0.7)
@export var highlight_color: Color = Color(1.0, 1.0, 0.4)

# ── Lifecycle ───────────────────────────────────────────────────────────────────

func _ready() -> void:
	# Obtain the SelectionManager autoload (weak-typed as Node).
	_selection_manager = get_node_or_null("/root/SelectionManager")
	if _selection_manager == null:
		push_warning("[ControlGroupsUI] SelectionManager autoload not found; retrying deferred.")
		_await_selection_manager.call_deferred()

	_build_slots()
	_connect_signals()
	_refresh_all()


func _await_selection_manager() -> void:
	await get_tree().process_frame
	_selection_manager = get_node_or_null("/root/SelectionManager")
	if _selection_manager == null:
		push_error("[ControlGroupsUI] SelectionManager autoload still not found.")
	_refresh_all()
	_connect_signals()


func _build_slots() -> void:
	for child in get_children():
		child.queue_free()
	_labels.clear()
	_backgrounds.clear()

	for i in GROUP_COUNT:
		var group_num: int = i + 1

		var panel := Panel.new()
		panel.custom_minimum_size = Vector2(slot_min_width, slot_min_height)
		var style := StyleBoxFlat.new()
		style.bg_color = Color(0.1, 0.1, 0.1, 0.6)
		style.border_color = Color(0.4, 0.4, 0.4, 0.8)
		style.set_border_width_all(1)
		style.set_corner_radius_all(2)
		panel.add_theme_stylebox_override("panel", style)
		add_child(panel)
		_backgrounds.append(panel)

		var label := Label.new()
		label.text = str(group_num)
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		label.anchors_preset = Control.PRESET_FULL_RECT
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		panel.add_child(label)
		_labels.append(label)


func _connect_signals() -> void:
	if _selection_manager == null:
		return
	if _selection_manager.has_signal("control_group_created"):
		_selection_manager.control_group_created.connect(_on_control_group_created)
	if _selection_manager.has_signal("control_group_selected"):
		_selection_manager.control_group_selected.connect(_on_control_group_selected)

# ── Signal Handlers ─────────────────────────────────────────────────────────────

func _on_control_group_created(index: int, _ids: Array) -> void:
	_refresh_slot(index)


func _on_control_group_selected(index: int, _ids: Array) -> void:
	_highlight_slot(index)

# ── Refresh ─────────────────────────────────────────────────────────────────────

func _refresh_all() -> void:
	for i in GROUP_COUNT:
		_refresh_slot(i + 1)


func _refresh_slot(group_num: int) -> void:
	var idx: int = group_num - 1
	if idx < 0 or idx >= _labels.size():
		return

	var is_assigned: bool = false
	if _selection_manager != null and _selection_manager.has_method("has_hotkey_group"):
		is_assigned = _selection_manager.has_hotkey_group(group_num)

	var label: Label = _labels[idx]
	var panel: Panel = _backgrounds[idx]

	if is_assigned:
		label.modulate.a = assigned_opacity
		label.add_theme_color_override("font_color", assigned_color)
		panel.modulate.a = 1.0
	else:
		label.modulate.a = empty_opacity
		label.add_theme_color_override("font_color", empty_color)
		panel.modulate.a = 0.5


func _highlight_slot(group_num: int) -> void:
	var idx: int = group_num - 1
	if idx < 0 or idx >= _labels.size():
		return

	var label: Label = _labels[idx]
	label.add_theme_color_override("font_color", highlight_color)

	var tween := create_tween()
	tween.tween_property(label, "modulate", Color(highlight_color, assigned_opacity), 0.0)
	tween.tween_callback(_revert_slot_color.bind(idx)).set_delay(0.25)


func _revert_slot_color(idx: int) -> void:
	if idx < 0 or idx >= _labels.size():
		return
	_labels[idx].add_theme_color_override("font_color", assigned_color)

# ── Cleanup ────────────────────────────────────────────────────────────────────

func _exit_tree() -> void:
	if _selection_manager == null:
		return
	if _selection_manager.has_signal("control_group_created"):
		if _selection_manager.control_group_created.is_connected(_on_control_group_created):
			_selection_manager.control_group_created.disconnect(_on_control_group_created)
	if _selection_manager.has_signal("control_group_selected"):
		if _selection_manager.control_group_selected.is_connected(_on_control_group_selected):
			_selection_manager.control_group_selected.disconnect(_on_control_group_selected)