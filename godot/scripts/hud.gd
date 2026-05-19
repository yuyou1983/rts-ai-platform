extends Control

## Bottom HUD panel for the RTS game.
## Shows: resource bar, selected unit info, ability buttons (3×3 grid),
## build menu (for workers), train menu (for buildings), and unit portrait area.

# ── Signals ──────────────────────────────────────────────────────────────────
signal ability_clicked(ability_id: StringName)
signal build_clicked(building_type: String)
signal train_clicked(unit_type: String)
signal build_panel_closed

# ── Layout Constants ─────────────────────────────────────────────────────────
const HUD_HEIGHT := 140
const RESOURCE_BAR_HEIGHT := 28
const PORTRAIT_SIZE := 96
const ABILITY_BTN_SIZE := 36
const ABILITY_PADDING := 4
const ABILITY_COLS := 3
const ABILITY_ROWS := 3

# ── Build Catalog: [key, display, mineral, gas, prereq_key] ──────────────────
const BUILD_CATALOG := [
	["base",          "Command Center", 400, 0,   ""],
	["supply_depot",  "Supply Depot",  100, 0,   ""],
	["refinery",      "Refinery",      100, 0,   ""],
	["barracks",      "Barracks",      150, 0,   ""],
	["factory",       "Factory",       200, 100, "barracks"],
	["starport",      "Starport",      200, 150, "factory"],
]

# ── Train Catalog: [key, display, mineral, gas, from_building_key] ───────────
const TRAIN_CATALOG := [
	# Terran — Base
	["worker",   "SCV",           50,   0,   "base"],
	# Terran — Barracks
	["Marine",   "Marine",        50,   0,   "barracks"],
	["Firebat",  "Firebat",       50,  25,   "barracks"],
	["Ghost",    "Ghost",         25,  75,   "barracks"],
	["Medic",    "Medic",         50,  25,   "barracks"],
	# Terran — Factory
	["Vulture",  "Vulture",       75,   0,   "factory"],
	["Tank",     "Siege Tank",   150, 100,   "factory"],
	["Goliath",  "Goliath",      100,  50,   "factory"],
	# Terran — Starport
	["Wraith",   "Wraith",       150, 100,   "starport"],
	["Dropship", "Dropship",     100, 100,   "starport"],
	["Vessel",   "Vessel",       100, 225,   "starport"],
	["Valkyrie", "Valkyrie",     250, 125,   "starport"],
	["BattleCruiser", "BattleCruiser", 400, 300, "starport"],
	# Zerg — Base / Hatchery
	["Drone",    "Drone",         50,   0,   "base"],
	["Overlord", "Overlord",     100,   0,   "base"],
	# Zerg — Barracks proxy (SpawningPool → Zergling, HydraliskDen → Hydralisk)
	["Zergling", "Zergling",      50,   0,   "barracks"],
	["Hydralisk","Hydralisk",     75,  25,   "barracks"],
	["Ultralisk","Ultralisk",    200, 200,   "factory"],
	# Zerg — Starport proxy (Spire → Mutalisk, QueenNest → Queen)
	["Mutalisk", "Mutalisk",     100, 100,   "starport"],
	["Queen",    "Queen",        100, 100,   "starport"],
]

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
var _train_panel: PanelContainer = null
var _build_visible: bool = false
var _train_visible: bool = false

# ── Completed buildings cache (for prereq checks) ───────────────────────────
var _completed_buildings: PackedStringArray = []

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
	set_anchors_preset(Control.PRESET_FULL_RECT)
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
	_minerals_label.custom_minimum_size = Vector2(130, 24)
	_minerals_label.add_theme_color_override("font_color", Color.CYAN)
	_minerals_label.add_theme_font_size_override("font_size", 14)
	_resource_bar.add_child(_minerals_label)

	_gas_label = Label.new()
	_gas_label.custom_minimum_size = Vector2(130, 24)
	_gas_label.add_theme_color_override("font_color", Color.GREEN)
	_gas_label.add_theme_font_size_override("font_size", 14)
	_resource_bar.add_child(_gas_label)

	_supply_label = Label.new()
	_supply_label.custom_minimum_size = Vector2(130, 24)
	_supply_label.add_theme_color_override("font_color", Color.WHITE)
	_supply_label.add_theme_font_size_override("font_size", 14)
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
	_info_panel.custom_minimum_size = Vector2(220, 0)
	_info_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_child(_info_panel)

	_type_label = Label.new()
	_type_label.add_theme_color_override("font_color", Color.WHITE)
	_type_label.add_theme_font_size_override("font_size", 13)
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
	build_title.text = "🏗️ Build Menu"
	build_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	build_title.add_theme_font_size_override("font_size", 14)
	build_vbox.add_child(build_title)

	for binfo in BUILD_CATALOG:
		var bkey: String = binfo[0]
		var bname: String = binfo[1]
		var bmine: int = binfo[2]
		var bgas: int = binfo[3]
		var bbtn := Button.new()
		bbtn.text = "%s (%d⛏" % [bname, bmine]
		if bgas > 0:
			bbtn.text += " %d🛢" % bgas
		bbtn.text += ")"
		bbtn.custom_minimum_size = Vector2(200, 30)
		bbtn.pressed.connect(_on_build_option_clicked.bind(bkey))
		build_vbox.add_child(bbtn)

	var close_btn := Button.new()
	close_btn.text = "Close (B)"
	close_btn.pressed.connect(_toggle_build_panel)
	build_vbox.add_child(close_btn)

	# ── Train Panel (overlay, hidden by default) ──
	_train_panel = PanelContainer.new()
	_train_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_train_panel.visible = false
	add_child(_train_panel)

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
		_hide_train_panel()
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
			selected_hp = _safe_float(data.get("health"), 0.0)
			selected_max_hp = _safe_float(data.get("max_health"), 0.0)
			selected_energy = _safe_float(data.get("energy"), 0.0)
			selected_max_energy = _safe_float(data.get("max_energy"), 0.0)

	# If a single building is selected, show its train panel
	if selected_count == 1 and selected_type == "building":
		_show_train_panel_for(selected_building_type)
	else:
		_hide_train_panel()

func _safe_float(value, fallback: float = 0.0) -> float:
	if value == null:
		return fallback
	return value + 0.0

func _on_abilities_changed() -> void:
	_update_ability_display()

func _on_ability_button_pressed(idx: int) -> void:
	if idx < _ability_ids.size() and _ability_ids[idx] != &"":
		var aid: StringName = _ability_ids[idx]
		if aid == &"build":
			_toggle_build_panel()
		elif aid == &"train":
			_toggle_train_panel()
		else:
			ability_clicked.emit(aid)

func _on_build_option_clicked(building_type: String) -> void:
	build_clicked.emit(building_type)
	_build_panel.visible = false
	_build_visible = false

func _on_train_option_clicked(unit_type: String) -> void:
	train_clicked.emit(unit_type)
	_train_panel.visible = false
	_train_visible = false

func _toggle_build_panel() -> void:
	_build_visible = not _build_visible
	_build_panel.visible = _build_visible
	if _build_visible:
		_hide_train_panel()
	else:
		build_panel_closed.emit()

func _toggle_train_panel() -> void:
	_train_visible = not _train_visible
	_train_panel.visible = _train_visible
	if _train_visible:
		_build_panel.visible = false
		_build_visible = false

# ── Train Panel — dynamic based on selected building ─────────────────────────

func _show_train_panel_for(building_key: String) -> void:
	# Clear old children
	for child in _train_panel.get_children():
		child.queue_free()

	var vbox := VBoxContainer.new()
	vbox.mouse_filter = Control.MOUSE_FILTER_STOP
	_train_panel.add_child(vbox)

	var title := Label.new()
	title.text = "🏭 Train — %s" % building_key.capitalize()
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 14)
	vbox.add_child(title)

	# Find matching train entries
	var shown_any := false
	for tinfo in TRAIN_CATALOG:
		var tkey: String = tinfo[0]
		var tname: String = tinfo[1]
		var tmine: int = tinfo[2]
		var tgas: int = tinfo[3]
		var from: String = tinfo[4]
		if from != building_key:
			continue
		# Check build prereqs (factory needs barracks, starport needs factory)
		if not _can_afford_and_prereq(tmine, tgas, from):
			continue
		shown_any = true
		var tbtn := Button.new()
		tbtn.text = "%s (%d⛏" % [tname, tmine]
		if tgas > 0:
			tbtn.text += " %d🛢" % tgas
		tbtn.text += ")"
		tbtn.custom_minimum_size = Vector2(200, 30)
		tbtn.disabled = (minerals < tmine or gas < tgas)
		tbtn.pressed.connect(_on_train_option_clicked.bind(tkey))
		vbox.add_child(tbtn)

	if not shown_any:
		var nolabel := Label.new()
		nolabel.text = "No units available"
		nolabel.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		vbox.add_child(nolabel)

	var close_btn := Button.new()
	close_btn.text = "Close"
	close_btn.pressed.connect(func(): _train_panel.visible = false; _train_visible = false)
	vbox.add_child(close_btn)

	_train_panel.visible = true
	_train_visible = true

func _hide_train_panel() -> void:
	_train_panel.visible = false
	_train_visible = false

func _can_afford_and_prereq(_mine: int, _gas: int, from_key: String) -> bool:
	# Prereq: factory needs barracks built, starport needs factory built
	match from_key:
		"factory":
			if "barracks" not in _completed_buildings and "Barracks" not in _completed_buildings:
				return false
		"starport":
			if "factory" not in _completed_buildings and "Factory" not in _completed_buildings:
				return false
	return true

# ── Public API ───────────────────────────────────────────────────────────────

func set_entity_data_provider(provider: Callable) -> void:
	_entity_data_provider = provider

func update_resources(m: int, g: int, su: int, sc: int) -> void:
	minerals = m
	gas = g
	supply_used = su
	supply_cap = sc

func update_completed_buildings(buildings: PackedStringArray) -> void:
	_completed_buildings = buildings

func is_build_panel_visible() -> bool:
	return _build_visible

func show_build_panel() -> void:
	_build_visible = true
	_build_panel.visible = true

func hide_build_panel() -> void:
	_build_visible = false
	_build_panel.visible = false
	build_panel_closed.emit()

func is_train_panel_visible() -> bool:
	return _train_visible