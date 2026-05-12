class_name HUD
extends Control

## Bottom HUD panel for the RTS game.
## Shows: resource bar, selected unit info, ability buttons (3×3 grid),
## build menu (for workers), and unit portrait area.

# ── Signals ──────────────────────────────────────────────────────────────────
signal ability_clicked(ability_id: StringName)
signal build_clicked(building_type: String)
signal train_clicked(unit_type: String)

# ── Layout Constants ─────────────────────────────────────────────────────────
const HUD_HEIGHT := 140
const RESOURCE_BAR_HEIGHT := 28
const PORTRAIT_SIZE := 96
const ABILITY_BTN_SIZE := 36
const ABILITY_PADDING := 4
const ABILITY_COLS := 3
const ABILITY_ROWS := 3

# ── Resource Data ────────────────────────────────────────────────────────────
var minerals: int = 0
var gas: int = 0
var supply_used: int = 0
var supply_cap: int = 0

# ── Selected Unit Data ──────────────────────────────────────────────────────
var selected_type: String = ""
var selected_hp: float = 0.0
var selected_max_hp: float = 0.0
var selected_energy: float = 0.0
var selected_max_energy: float = 0.0
var selected_building_type: String = ""
var selected_count: int = 0

# ── Ability Buttons ─────────────────────────────────────────────────────────
var _ability_buttons: Array[Button] = []
var _ability_ids: Array[StringName] = []
var _build_panel: PanelContainer = null
var _build_visible: bool = false

# ── References ──────────────────────────────────────────────────────────────
var _selection_manager: Node = null
var _ability_manager: Node = null
var _entity_data_provider: Callable

# ── Sub-controls ─────────────────────────────────────────────────────────────
var _resource_bar: HBoxContainer
var _minerals_label: Label
var _gas_label: Label
var _supply_label: Label
var _info_panel: VBoxContainer
var _type_label: Label
var _hp_bar: ProgressBar
var _energy_bar: ProgressBar
var _portrait_panel: Panel
var _ability_grid: GridContainer
var _status_label: Label

# ── Hotkey mapping ──────────────────────────────────────────────────────────
var _hotkey_names: Dictionary = {
	KEY_M: "Move",
	KEY_S: "Stop",
	KEY_A: "Attack",
	KEY_P: "Patrol",
	KEY_H: "Hold",
	KEY_G: "Gather",
	KEY_B: "Build",
	KEY_T: "Train",
}

# ── Lifecycle ───────────────────────────────────────────────────────────────

func _ready() -> void:
	_selection_manager = get_node_or_null("/root/SelectionManager")
	_ability_manager = get_node_or_null("/root/AbilityManager")

	_build_ui()
	_connect_signals()

func _build_ui() -> void:
	# Position HUD at bottom
	anchor_right = 1.0
	anchor_bottom = 1.0
	anchor_top = 1.0 - (HUD_HEIGHT / 720.0)
	offset_top = 0
	offset_bottom = 0
	offset_left = 0
	offset_right = 0

	var bg := Panel.new()
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	# ── Resource Bar (top of HUD) ──
	_resource_bar = HBoxContainer.new()
	_resource_bar.set_anchors_preset(Control.PRESET_TOP_LEFT)
	_resource_bar.offset_right = 0
	_resource_bar.offset_bottom = RESOURCE_BAR_HEIGHT
	add_child(_resource_bar)

	_minerals_label = Label.new()
	_minerals_label.custom_minimum_size = Vector2(120, 24)
	_minerals_label.add_theme_color_override("font_color", Color.CYAN)
	_resource_bar.add_child(_minerals_label)

	_gas_label = Label.new()
	_gas_label.custom_minimum_size = Vector2(120, 24)
	_gas_label.add_theme_color_override("font_color", Color.GREEN)
	_resource_bar.add_child(_gas_label)

	_supply_label = Label.new()
	_supply_label.custom_minimum_size = Vector2(120, 24)
	_supply_label.add_theme_color_override("font_color", Color.WHITE)
	_resource_bar.add_child(_supply_label)

	# ── Content area (below resource bar) ──
	var content := HBoxContainer.new()
	content.set_anchors_preset(Control.PRESET_TOP_LEFT)
	content.offset_top = RESOURCE_BAR_HEIGHT
	content.offset_bottom = 0
	content.offset_left = 0
	content.offset_right = 0
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(content)

	# ── Portrait Panel (left) ──
	_portrait_panel = Panel.new()
	_portrait_panel.custom_minimum_size = Vector2(PORTRAIT_SIZE, HUD_HEIGHT - RESOURCE_BAR_HEIGHT)
	content.add_child(_portrait_panel)

	var portrait_label := Label.new()
	portrait_label.text = "Portrait"
	portrait_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	portrait_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	portrait_label.set_anchors_preset(Control.PRESET_FULL_RECT)
	portrait_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_portrait_panel.add_child(portrait_label)

	# ── Info Panel (center) ──
	_info_panel = VBoxContainer.new()
	_info_panel.custom_minimum_size = Vector2(200, 0)
	_info_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_child(_info_panel)

	_type_label = Label.new()
	_type_label.add_theme_color_override("font_color", Color.WHITE)
	_info_panel.add_child(_type_label)

	# HP bar row
	var hp_row := HBoxContainer.new()
	_info_panel.add_child(hp_row)

	var hp_label := Label.new()
	hp_label.text = "HP:"
	hp_label.custom_minimum_size = Vector2(28, 16)
	hp_label.add_theme_color_override("font_color", Color.GREEN)
	hp_row.add_child(hp_label)

	_hp_bar = ProgressBar.new()
	_hp_bar.custom_minimum_size = Vector2(160, 14)
	_hp_bar.max_value = 100.0
	_hp_bar.value = 100.0
	_hp_bar.show_percentage = false
	hp_row.add_child(_hp_bar)

	# Energy bar row
	var energy_row := HBoxContainer.new()
	_info_panel.add_child(energy_row)

	var energy_label := Label.new()
	energy_label.text = "EN:"
	energy_label.custom_minimum_size = Vector2(28, 16)
	energy_label.add_theme_color_override("font_color", Color(0.3, 0.6, 1.0))
	energy_row.add_child(energy_label)

	_energy_bar = ProgressBar.new()
	_energy_bar.custom_minimum_size = Vector2(160, 14)
	_energy_bar.max_value = 100.0
	_energy_bar.value = 0.0
	_energy_bar.show_percentage = false
	energy_row.add_child(_energy_bar)

	_status_label = Label.new()
	_status_label.add_theme_color_override("font_color", Color.YELLOW)
	_status_label.add_theme_font_size_override("font_size", 11)
	_info_panel.add_child(_status_label)

	# ── Ability Grid (right) ──
	var ability_panel := Panel.new()
	ability_panel.custom_minimum_size = Vector2(
		ABILITY_COLS * (ABILITY_BTN_SIZE + ABILITY_PADDING) + ABILITY_PADDING,
		ABILITY_ROWS * (ABILITY_BTN_SIZE + ABILITY_PADDING) + ABILITY_PADDING
	)
	content.add_child(ability_panel)

	_ability_grid = GridContainer.new()
	_ability_grid.columns = ABILITY_COLS
	_ability_grid.set_anchors_preset(Control.PRESET_FULL_RECT)
	_ability_grid.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ability_panel.add_child(_ability_grid)

	# Create 3×3 ability buttons
	for i in range(ABILITY_COLS * ABILITY_ROWS):
		var btn := Button.new()
		btn.custom_minimum_size = Vector2(ABILITY_BTN_SIZE, ABILITY_BTN_SIZE)
		btn.disabled = true
		btn.text = ""
		btn.tooltip_text = ""
		btn.mouse_filter = Control.MOUSE_FILTER_STOP
		var idx: int = i
		btn.pressed.connect(_on_ability_button_pressed.bind(idx))
		_ability_grid.add_child(btn)
		_ability_buttons.append(btn)
		_ability_ids.append(&"")

	# ── Build Panel (overlay, hidden by default) ──
	_build_panel = PanelContainer.new()
	_build_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_build_panel.visible = false
	add_child(_build_panel)

	var build_vbox := VBoxContainer.new()
	build_vbox.mouse_filter = Control.MOUSE_FILTER_STOP
	_build_panel.add_child(build_vbox)

	var build_title := Label.new()
	build_title.text = "Build Menu"
	build_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	build_vbox.add_child(build_title)

	var build_options: Array = ["base", "barracks", "refinery"]
	for bopt in build_options:
		var bbtn := Button.new()
		bbtn.text = str(bopt).capitalize()
		bbtn.custom_minimum_size = Vector2(100, 28)
		var btype: String = str(bopt)
		bbtn.pressed.connect(_on_build_option_clicked.bind(btype))
		build_vbox.add_child(bbtn)

	var close_btn := Button.new()
	close_btn.text = "Close (B)"
	close_btn.pressed.connect(_toggle_build_panel)
	build_vbox.add_child(close_btn)

func _connect_signals() -> void:
	if _selection_manager and _selection_manager.has_signal("selection_changed"):
		_selection_manager.selection_changed.connect(_on_selection_changed)
	if _ability_manager and _ability_manager.has_signal("abilities_changed"):
		_ability_manager.abilities_changed.connect(_on_abilities_changed)

# ── Update ───────────────────────────────────────────────────────────────────

func _process(_delta: float) -> void:
	_update_resource_display()
	_update_selection_display()
	_update_ability_display()

func _update_resource_display() -> void:
	_minerals_label.text = "⛏ Minerals: %d" % minerals
	_gas_label.text = "🛢 Gas: %d" % gas
	_supply_label.text = "📦 Supply: %d/%d" % [supply_used, supply_cap]

func _update_selection_display() -> void:
	if selected_count == 0:
		_type_label.text = "No selection"
		_hp_bar.value = 0
		_energy_bar.value = 0
		_status_label.text = ""
		return

	var display_name := _format_entity_name(selected_type, selected_building_type)
	if selected_count > 1:
		_type_label.text = "%s ×%d" % [display_name, selected_count]
	else:
		_type_label.text = display_name

	var hp_pct: float = 0.0
	if selected_max_hp > 0:
		hp_pct = (selected_hp / selected_max_hp) * 100.0
	_hp_bar.value = hp_pct

	if selected_max_energy > 0:
		_energy_bar.value = (selected_energy / selected_max_energy) * 100.0
		_energy_bar.visible = true
	else:
		_energy_bar.visible = false

	var status_parts: Array = []
	if selected_type == "worker":
		status_parts.append("Worker")
	if selected_type == "building":
		status_parts.append("Building")
	_status_label.text = " ".join(status_parts)

func _update_ability_display() -> void:
	if _ability_manager and _ability_manager.has_method("get_selected_abilities_keys"):
		var keys: Array = _ability_manager.get_selected_abilities_keys()
		for i in range(ABILITY_COLS * ABILITY_ROWS):
			if i < keys.size():
				var aid: StringName = keys[i]
				_ability_ids[i] = aid
				_ability_buttons[i].disabled = false
				_ability_buttons[i].text = _ability_display_text(aid)
				_ability_buttons[i].tooltip_text = _ability_tooltip(aid)
			else:
				_ability_ids[i] = &""
				_ability_buttons[i].disabled = true
				_ability_buttons[i].text = ""
				_ability_buttons[i].tooltip_text = ""

func _format_entity_name(etype: String, btype: String) -> String:
	if etype == "building":
		return btype.capitalize() if btype else "Building"
	return etype.capitalize()

func _ability_display_text(ability_id: StringName) -> String:
	var aid_str: String = str(ability_id)
	match aid_str:
		"move": return "M"
		"stop": return "S"
		"attack": return "A"
		"patrol": return "P"
		"hold": return "H"
		"gather": return "G"
		"build": return "B"
		"train": return "T"
		_: return aid_str.left(1).to_upper()

func _ability_tooltip(ability_id: StringName) -> String:
	var aid_str: String = str(ability_id)
	match aid_str:
		"move": return "Move (M) - Move to target position"
		"stop": return "Stop (S) - Cancel current action"
		"attack": return "Attack (A) - Attack a target"
		"patrol": return "Patrol (P) - Patrol between points"
		"hold": return "Hold (H) - Hold position, attack nearby"
		"gather": return "Gather (G) - Gather resources"
		"build": return "Build (B) - Build a structure"
		"train": return "Train (T) - Train a unit"
		_: return aid_str

# ── Signal Handlers ──────────────────────────────────────────────────────────

func _on_selection_changed(selection: Dictionary) -> void:
	selected_count = selection.size()
	selected_type = ""
	selected_building_type = ""
	selected_hp = 0.0
	selected_max_hp = 0.0
	selected_energy = 0.0
	selected_max_energy = 0.0

	if selected_count == 0:
		return

	var primary_id: String = ""
	if _selection_manager and _selection_manager.has_method("get_highest_selected_id"):
		primary_id = _selection_manager.highest_selected_id
	elif not selection.is_empty():
		primary_id = str(selection.keys()[0])

	if primary_id != "" and _entity_data_provider.is_valid():
		var data: Dictionary = _entity_data_provider.call(primary_id)
		if not data.is_empty():
			selected_type = str(data.get("type", data.get("entity_type", "")))
			selected_building_type = str(data.get("building_type", ""))
			selected_hp = float(data.get("health", 0))
			selected_max_hp = float(data.get("max_health", 0))
			selected_energy = float(data.get("energy", 0))
			selected_max_energy = float(data.get("max_energy", 0))

func _on_abilities_changed() -> void:
	_update_ability_display()

func _on_ability_button_pressed(idx: int) -> void:
	if idx < _ability_ids.size() and _ability_ids[idx] != &"":
		var aid: StringName = _ability_ids[idx]
		if aid == &"build":
			_toggle_build_panel()
		else:
			ability_clicked.emit(aid)

func _on_build_option_clicked(building_type: String) -> void:
	build_clicked.emit(building_type)
	_build_panel.visible = false
	_build_visible = false

func _toggle_build_panel() -> void:
	_build_visible = not _build_visible
	_build_panel.visible = _build_visible

# ── Public API ───────────────────────────────────────────────────────────────

func set_entity_data_provider(provider: Callable) -> void:
	_entity_data_provider = provider

func update_resources(m: int, g: int, su: int, sc: int) -> void:
	minerals = m
	gas = g
	supply_used = su
	supply_cap = sc

func is_build_panel_visible() -> bool:
	return _build_visible

func show_build_panel() -> void:
	_build_visible = true
	_build_panel.visible = true

func hide_build_panel() -> void:
	_build_visible = false
	_build_panel.visible = false