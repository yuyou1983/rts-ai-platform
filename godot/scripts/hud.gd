extends Control

## Bottom HUD panel for the RTS game.
## Shows: resource bar, selected unit info, ability buttons (3×3 grid),
## build menu (for workers), train menu (for buildings), and unit portrait area.
## Race-aware: filters build/train catalogs based on player faction.

# ── Signals ──────────────────────────────────────────────────────────────────
signal ability_clicked(ability_id: StringName)
signal build_clicked(building_type: String)
signal train_clicked(unit_type: String)
signal upgrade_clicked(upgrade_type: String, entity_id: String)
signal research_clicked(tech_name: String, entity_id: String)
signal build_panel_closed
signal merge_clicked(unit_type: String)

# ── Layout Constants ─────────────────────────────────────────────────────────
const HUD_HEIGHT := 140
const RESOURCE_BAR_HEIGHT := 28
const PORTRAIT_SIZE := 96
const ABILITY_BTN_SIZE := 36
const ABILITY_PADDING := 4
const ABILITY_COLS := 3
const ABILITY_ROWS := 3

# ── Build Catalog: [key, display, mineral, gas, prereq_key, races] ───────────
# races: array of race IDs that can build this — [] = all races
const BUILD_CATALOG := [
	# Terran
	["base",          "Command Center", 400, 0,   "",       ["1"]],
	["supply_depot",  "Supply Depot",   100, 0,   "",       ["1"]],
	["refinery",      "Refinery",       100, 0,   "",       ["1"]],
	["barracks",      "Barracks",       150, 0,   "",       ["1"]],
	["factory",       "Factory",        200, 100, "barracks", ["1"]],
	["starport",      "Starport",       200, 150, "factory", ["1"]],
	# Terran — Tier 1 defense / tech
	["defense_turret", "Missile Turret", 75, 0,   "",       ["1"]],
	["bunker",        "Bunker",          100, 0,   "",       ["1"]],
	["tech_infantry",  "Academy",       150, 0,   "",       ["1"]],
	["tech_armor",    "Engineering Bay", 125, 0,  "",       ["1"]],
	# Terran — Tier 2 tech
	["armory",       "Armory",          100, 50,  "factory", ["1"]],
	["science",      "Science Facility", 100, 150, "armory", ["1"]],
	# Zerg (Overlord is a unit trained from Hatchery, NOT a building)
	["base",          "Hatchery",       400, 0,   "",       ["2"]],
	["refinery",      "Extractor",      100, 0,   "",       ["2"]],
	["barracks",      "Spawning Pool",  150, 0,   "",       ["2"]],
	["factory",       "Hydralisk Den",  200, 100, "barracks", ["2"]],
	["starport",      "Spire",          200, 150, "factory", ["2"]],
	# Zerg — Tier 1 defense / tech / morphs
	["defense",      "Creep Colony",    75, 0,   "",       ["2"]],
	["defense_air",  "Spore Colony",    75, 0,   "defense", ["2"]],
	["defense_ground", "Sunken Colony", 50, 50,  "defense", ["2"]],
	["tech_basic",   "Evolution Chamber", 75, 0, "",       ["2"]],
	["morph_base",   "Lair",           150, 100, "",       ["2"]],
	["morph_base2",  "Hive",           200, 150, "morph_base", ["2"]],
	# Zerg — Tier 2 tech (requires Lair)
	["queen_nest",   "Queen Nest",      100, 100, "morph_base", ["2"]],
	["defiler_mound", "Defiler Mound",  100, 100, "morph_base", ["2"]],
	["nydus",        "Nydus Canal",     150, 100, "morph_base", ["2"]],
	["ultra_cavern", "Ultralisk Cavern", 200, 200, "morph_base", ["2"]],
	# Protoss
	["base",          "Nexus",          400, 0,   "",       ["3"]],
	["supply_depot",  "Pylon",          100, 0,   "",       ["3"]],
	["refinery",      "Assimilator",    100, 0,   "",       ["3"]],
	["barracks",      "Gateway",        150, 0,   "",       ["3"]],
	["factory",       "Robotics Facility", 200, 100, "barracks", ["3"]],
	["starport",      "Stargate",       200, 150, "factory", ["3"]],
	# Protoss — Tier 1 defense / tech
	["defense",      "Photon Cannon",  150, 0,   "tech_basic", ["3"]],
	["shield_station", "Shield Battery", 100, 0, "barracks", ["3"]],
	["tech_basic",   "Forge",          100, 0,   "",       ["3"]],
	["tech_cyber",   "Cybernetics Core", 200, 0,  "barracks", ["3"]],
	# Protoss — Tier 2 tech
	["tech_infantry", "Citadel of Adun", 150, 100, "tech_cyber", ["3"]],
	["tech_templar", "Templar Archives", 150, 200, "tech_infantry", ["3"]],
	["tech_robotics", "Robotics Support Bay", 100, 50, "factory", ["3"]],
	["tech_fleet",   "Fleet Beacon",   300, 200, "starport", ["3"]],
	["tech_observatory", "Observatory", 50, 100, "factory", ["3"]],
	["tech_arbiter", "Arbiter Tribunal", 200, 300, "starport", ["3"]],
]

# ── Train Catalog: [key, display, mineral, gas, from_building_key, races] ────
const TRAIN_CATALOG := [
	# Terran — Base
	["worker",   "SCV",           50,   0,   "base",       ["1"]],
	# Terran — Barracks
	["Marine",   "Marine",        50,   0,   "barracks",   ["1"]],
	["Firebat",  "Firebat",       50,  25,   "barracks",   ["1"]],
	["Ghost",    "Ghost",         25,  75,   "barracks",   ["1"]],
	["Medic",    "Medic",         50,  25,   "barracks",   ["1"]],
	# Terran — Factory
	["Vulture",  "Vulture",       75,   0,   "factory",    ["1"]],
	["Tank",     "Siege Tank",   150, 100,   "factory",    ["1"]],
	["Goliath",  "Goliath",      100,  50,   "factory",    ["1"]],
	# Terran — Starport
	["Wraith",   "Wraith",       150, 100,   "starport",   ["1"]],
	["Dropship", "Dropship",     100, 100,   "starport",   ["1"]],
	["Vessel",   "Vessel",       100, 225,   "starport",   ["1"]],
	["Valkyrie", "Valkyrie",     250, 125,   "starport",   ["1"]],
	["BattleCruiser", "BattleCruiser", 400, 300, "starport", ["1"]],
	# Zerg — Base / Hatchery
	["Drone",    "Drone",         50,   0,   "base",       ["2"]],
	["Overlord", "Overlord",     100,   0,   "base",       ["2"]],
	# Zerg — Barracks proxy
	["Zergling", "Zergling",      50,   0,   "barracks",   ["2"]],
	["Hydralisk","Hydralisk",     75,  25,   "barracks",   ["2"]],
	["Ultralisk","Ultralisk",    200, 200,   "factory",    ["2"]],
	# Zerg — Starport proxy
	["Mutalisk", "Mutalisk",     100, 100,   "starport",   ["2"]],
	["Queen",    "Queen",        100, 100,   "starport",   ["2"]],
	# Zerg — Starport proxy (cont.)
	["Defiler",  "Defiler",       50, 150,   "starport",   ["2"]],
	["Scourge",  "Scourge",       25,  75,   "starport",   ["2"]],
	# Protoss — Base / Nexus
	["Probe",    "Probe",         50,   0,   "base",       ["3"]],
	# Protoss — Barracks / Gateway
	["Zealot",   "Zealot",       100,   0,   "barracks",   ["3"]],
	["Dragoon",  "Dragoon",      125,  50,   "barracks",   ["3"]],
	["Templar",  "Templar",       50, 150,   "barracks",   ["3"]],
	["DarkTemplar", "Dark Templar", 125, 100, "barracks",  ["3"]],
	# Protoss — Factory / Robotics
	["Reaver",   "Reaver",       200, 100,   "factory",    ["3"]],
	["Shuttle",  "Shuttle",      200,   0,   "factory",    ["3"]],
	# Protoss — Starport / Stargate
	["Scout_ship", "Scout",      250, 150,   "starport",   ["3"]],
	["Carrier",  "Carrier",     350, 250,   "starport",   ["3"]],
	["Arbiter",  "Arbiter",     350, 300,   "starport",   ["3"]],
	["Corsair",  "Corsair",     150, 100,   "starport",   ["3"]],
	# Protoss — Factory / Robotics (cont.)
	["Observer", "Observer",    25,  75,   "factory",    ["3"]],
]

# ── Upgrade Catalog: [key, display, mineral, gas, from_building_key, races] ───
# from_building_key: the building_type of the building that can morph into this
const UPGRADE_CATALOG := [
	# Zerg morph upgrades
	["morph_base",  "Upgrade to Lair",     150, 100, "base",       ["2"]],
	["morph_base2", "Upgrade to Hive",     200, 150, "morph_base", ["2"]],
]

# ── Research Catalog: [tech_name, display, mineral, gas, prereq_building_key, races] ──
# prereq_building_key: the building_type that must be selected to show this research
const RESEARCH_CATALOG := [
	# Terran Academy
	["Stimpack",    "Stim Pack",      100, 100, "tech_infantry", ["1"]],
	["U238Shells",  "U-238 Shells",   150, 150, "tech_armor",    ["1"]],
	# Protoss Forge
	["GroundWeapons",  "Ground Weapons +1", 100, 100, "tech_basic", ["3"]],
	["GroundArmor",    "Ground Armor +1",   100, 100, "tech_basic", ["3"]],
	["PlasmaShields",  "Plasma Shields +1",  100, 100, "tech_basic", ["3"]],
	# Zerg Evolution Chamber
	["MeleeAttacks",  "Melee Attacks +1",  100, 100, "tech_basic", ["2"]],
	["Carapace",      "Carapace +1",       150, 150, "tech_basic", ["2"]],
]

# ── Resource Data ────────────────────────────────────────────────────────────
var minerals: int = 0
var gas: int = 0
var supply_used: int = 0
var supply_cap: int = 0

# ── Race ─────────────────────────────────────────────────────────────────────
var _player_race: String = "1"   # "1"=Terran, "2"=Zerg, "3"=Protoss

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
var _upgrade_panel: PanelContainer = null
var _research_panel: PanelContainer = null
var _build_visible: bool = false
var _train_visible: bool = false
var _upgrade_visible: bool = false
var _research_visible: bool = false
var _selected_entity_id: String = ""

# ── Merge button ────────────────────────────────────────────────────────
var _merge_panel: PanelContainer = null
var _merge_visible: bool = false

# ── Completed buildings cache (for prereq checks) ───────────────────────────
var _completed_buildings: PackedStringArray = []

# ── References ──────────────────────────────────────────────────────────────
var _selection_manager: Node = null
var _ability_manager: Node = null
var _entity_data_provider: Callable

# ── Sub-controls ────────────────────────────────────────────────────────────
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


func set_player_race(race_id: String) -> void:
	"""Set the player's race for catalog filtering. Accepts '1'/'terran', '2'/'zerg', '3'/'protoss'."""
	var r: String = race_id.to_lower()
	match r:
		"terran", "1":
			_player_race = "1"
		"zerg", "2":
			_player_race = "2"
		"protoss", "3":
			_player_race = "3"
		_:
			_player_race = "1"


func _race_matches(entry_races: Array) -> bool:
	"""Check if current player race is in the entry's allowed races list."""
	if entry_races.is_empty():
		return true
	return _player_race in entry_races


func _build_ui() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_top = 0
	offset_bottom = 0
	offset_left = 0
	offset_right = 0

	var bg := Panel.new()
	bg.set_anchors_preset(Control.PRESET_TOP_LEFT)
	bg.offset_right = 0
	bg.offset_bottom = RESOURCE_BAR_HEIGHT
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

	# ── Build Panel (overlay, hidden by default — built dynamically on open) ──
	_build_panel = PanelContainer.new()
	_build_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_build_panel.visible = false
	add_child(_build_panel)

	# ── Train Panel (overlay, hidden by default — built dynamically on open) ──
	_train_panel = PanelContainer.new()
	_train_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_train_panel.visible = false
	add_child(_train_panel)

	# ── Upgrade Panel (overlay, hidden by default — built dynamically on open) ──
	_upgrade_panel = PanelContainer.new()
	_upgrade_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_upgrade_panel.visible = false
	add_child(_upgrade_panel)

	# ── Research Panel (overlay, hidden by default — built dynamically on open) ──
	_research_panel = PanelContainer.new()
	_research_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_research_panel.visible = false
	add_child(_research_panel)

	# ── Merge Panel (overlay, hidden by default — shows merge buttons) ──
	_merge_panel = PanelContainer.new()
	_merge_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_merge_panel.visible = false
	add_child(_merge_panel)


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
		_hide_train_panel()
		_hide_upgrade_panel()
		_hide_research_panel()
		_hide_merge_panel()
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

	# Show appropriate panels when a single building is selected
	if selected_count == 1 and selected_type == "building":
		_show_train_panel_for(selected_building_type)
		_show_upgrade_panel_for(selected_building_type)
		_show_research_panel_for(selected_building_type)
		_hide_merge_panel()
	elif selected_count >= 2:
		_hide_train_panel()
		_hide_upgrade_panel()
		_hide_research_panel()
		_try_show_merge_panel({})


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
	_selected_entity_id = ""

	if selected_count == 0:
		_hide_train_panel()
		_hide_upgrade_panel()
		_hide_research_panel()
		return

	var primary_id: String = ""
	if _selection_manager and _selection_manager.has_method("get_highest_selected_id"):
		primary_id = _selection_manager.highest_selected_id
	elif not selection.is_empty():
		primary_id = str(selection.keys()[0])

	_selected_entity_id = primary_id

	if primary_id != "" and _entity_data_provider.is_valid():
		var data: Dictionary = _entity_data_provider.call(primary_id)
		if not data.is_empty():
			selected_type = str(data.get("type", data.get("entity_type", "")))
			selected_building_type = str(data.get("building_type", ""))
			selected_hp = _safe_float(data.get("health"), 0.0)
			selected_max_hp = _safe_float(data.get("max_health"), 0.0)
			selected_energy = _safe_float(data.get("energy"), 0.0)
			selected_max_energy = _safe_float(data.get("max_energy"), 0.0)

	# If a single building is selected, show its train / upgrade / research panels
	if selected_count == 1 and selected_type == "building":
		_show_train_panel_for(selected_building_type)
		_show_upgrade_panel_for(selected_building_type)
		_show_research_panel_for(selected_building_type)
		_hide_merge_panel()
	else:
		_hide_train_panel()
		_hide_upgrade_panel()
		_hide_research_panel()
		# Check if we can show a merge button (2+ same-type Templar)
		_try_show_merge_panel(selection)


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


func _on_upgrade_option_clicked(upgrade_key: String) -> void:
	upgrade_clicked.emit(upgrade_key, _selected_entity_id)
	_upgrade_panel.visible = false
	_upgrade_visible = false


func _on_research_option_clicked(tech_name: String) -> void:
	research_clicked.emit(tech_name, _selected_entity_id)
	_research_panel.visible = false
	_research_visible = false


func _toggle_build_panel() -> void:
	_build_visible = not _build_visible
	_build_panel.visible = _build_visible
	if _build_visible:
		_hide_train_panel()
		_rebuild_build_panel()
	else:
		build_panel_closed.emit()


func _rebuild_build_panel() -> void:
	"""Dynamically build the build panel based on current player race."""
	for child in _build_panel.get_children():
		child.free()

	var vbox := VBoxContainer.new()
	vbox.mouse_filter = Control.MOUSE_FILTER_STOP
	_build_panel.add_child(vbox)

	var title := Label.new()
	title.text = "🏗️ Build Menu"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 14)
	vbox.add_child(title)

	var shown_count: int = 0
	for binfo in BUILD_CATALOG:
		if not _race_matches(binfo[5]):
			continue
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
		bbtn.disabled = (minerals < bmine or gas < bgas)
		bbtn.pressed.connect(_on_build_option_clicked.bind(bkey))
		vbox.add_child(bbtn)
		shown_count += 1

	var close_btn := Button.new()
	close_btn.text = "Close (B)"
	close_btn.pressed.connect(_toggle_build_panel)
	vbox.add_child(close_btn)

	print("[HUD] Build panel rebuilt: race=%s shown=%d minerals=%d gas=%d" % [_player_race, shown_count, minerals, gas])


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
		child.free()

	var vbox := VBoxContainer.new()
	vbox.mouse_filter = Control.MOUSE_FILTER_STOP
	_train_panel.add_child(vbox)

	var title := Label.new()
	title.text = "🏭 Train — %s" % building_key.capitalize()
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 14)
	vbox.add_child(title)

	# Find matching train entries for this player's race
	var shown_any := false
	for tinfo in TRAIN_CATALOG:
		var tkey: String = tinfo[0]
		var tname: String = tinfo[1]
		var tmine: int = tinfo[2]
		var tgas: int = tinfo[3]
		var from: String = tinfo[4]
		var races: Array = tinfo[5] if tinfo.size() > 5 else []
		if from != building_key:
			continue
		if not _race_matches(races):
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


# ── Upgrade Panel — dynamic based on selected building ─────────────────────

func _show_upgrade_panel_for(building_key: String) -> void:
	print("[HUD] _show_upgrade_panel_for building_key='%s' race=%s" % [building_key, str(_player_race)])
	# Clear old children
	for child in _upgrade_panel.get_children():
		child.free()

	var vbox := VBoxContainer.new()
	vbox.mouse_filter = Control.MOUSE_FILTER_STOP
	_upgrade_panel.add_child(vbox)

	var title := Label.new()
	title.text = "⬆ Upgrade — %s" % building_key.capitalize()
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 14)
	vbox.add_child(title)

	# Find matching upgrade entries for this player's race
	var shown_any: bool = false
	for uinfo in UPGRADE_CATALOG:
		var ukey: String = uinfo[0]
		var uname: String = uinfo[1]
		var umine: int = uinfo[2]
		var ugas: int = uinfo[3]
		var from: String = uinfo[4]
		var races: Array = uinfo[5] if uinfo.size() > 5 else []
		print("[HUD] checking ukey=%s from='%s' == building_key='%s' races=%s" % [ukey, from, building_key, str(races)])
		if from != building_key:
			continue
		if not _race_matches(races):
			continue
		shown_any = true
		var ubtn := Button.new()
		ubtn.text = "%s (%d⛏" % [uname, umine]
		if ugas > 0:
			ubtn.text += " %d🛢" % ugas
		ubtn.text += ")"
		ubtn.custom_minimum_size = Vector2(200, 30)
		ubtn.disabled = (minerals < umine or gas < ugas)
		ubtn.pressed.connect(_on_upgrade_option_clicked.bind(ukey))
		vbox.add_child(ubtn)

	if not shown_any:
		var nolabel := Label.new()
		nolabel.text = "No upgrades available"
		nolabel.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		vbox.add_child(nolabel)

	var close_btn := Button.new()
	close_btn.text = "Close"
	close_btn.pressed.connect(func(): _upgrade_panel.visible = false; _upgrade_visible = false)
	vbox.add_child(close_btn)

	_upgrade_panel.visible = true
	_upgrade_visible = true


func _hide_upgrade_panel() -> void:
	_upgrade_panel.visible = false
	_upgrade_visible = false


# ── Research Panel — dynamic based on selected building ────────────────────

func _show_research_panel_for(building_key: String) -> void:
	# Clear old children
	for child in _research_panel.get_children():
		child.free()

	var vbox := VBoxContainer.new()
	vbox.mouse_filter = Control.MOUSE_FILTER_STOP
	_research_panel.add_child(vbox)

	var title := Label.new()
	title.text = "🔬 Research — %s" % building_key.capitalize()
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 14)
	vbox.add_child(title)

	# Find matching research entries for this player's race
	var shown_any: bool = false
	for rinfo in RESEARCH_CATALOG:
		var rkey: String = rinfo[0]
		var rname: String = rinfo[1]
		var rmine: int = rinfo[2]
		var rgas: int = rinfo[3]
		var prereq: String = rinfo[4]
		var races: Array = rinfo[5] if rinfo.size() > 5 else []
		if prereq != building_key:
			continue
		if not _race_matches(races):
			continue
		shown_any = true
		var rbtn := Button.new()
		rbtn.text = "%s (%d⛏" % [rname, rmine]
		if rgas > 0:
			rbtn.text += " %d🛢" % rgas
		rbtn.text += ")"
		rbtn.custom_minimum_size = Vector2(200, 30)
		rbtn.disabled = (minerals < rmine or gas < rgas)
		rbtn.pressed.connect(_on_research_option_clicked.bind(rkey))
		vbox.add_child(rbtn)

	if not shown_any:
		var nolabel := Label.new()
		nolabel.text = "No research available"
		nolabel.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		vbox.add_child(nolabel)

	var close_btn := Button.new()
	close_btn.text = "Close"
	close_btn.pressed.connect(func(): _research_panel.visible = false; _research_visible = false)
	vbox.add_child(close_btn)

	_research_panel.visible = true
	_research_visible = true


func _hide_research_panel() -> void:
	_research_panel.visible = false
	_research_visible = false


# ── Merge Panel — shown when 2+ same-type Templar are selected ───────────

const _MERGE_RULES := {
	"Templar": {"target": "Archon", "display": "Merge to Archon"},
	"HighTemplar": {"target": "Archon", "display": "Merge to Archon"},
	"DarkTemplar": {"target": "DarkArchon", "display": "Merge to Dark Archon"},
}


func _try_show_merge_panel(selection: Dictionary) -> void:
	if selection.size() < 2:
		_hide_merge_panel()
		return

	# Count how many of each merge-eligible unit type are selected
	var type_counts: Dictionary = {}  # unit_type → count
	for eid in selection:
		var data: Dictionary = {}
		if _entity_data_provider.is_valid():
			data = _entity_data_provider.call(str(eid))
		if data.is_empty():
			continue
		var utype: String = str(data.get("unit_type", data.get("entity_type", "")))
		if _MERGE_RULES.has(utype):
			type_counts[utype] = type_counts.get(utype, 0) + 1

	# Need at least 2 of the same type
	var merge_type: String = ""
	for utype in type_counts:
		if int(type_counts[utype]) >= 2:
			merge_type = utype
			break

	if merge_type.is_empty():
		_hide_merge_panel()
		return

	_show_merge_panel_for(merge_type)


func _show_merge_panel_for(source_type: String) -> void:
	# Clear old children
	for child in _merge_panel.get_children():
		child.free()

	var rule: Dictionary = _MERGE_RULES.get(source_type, {})
	if rule.is_empty():
		_hide_merge_panel()
		return

	var target_type: String = str(rule.get("target", ""))
	var display_text: String = str(rule.get("display", "Merge"))

	var vbox := VBoxContainer.new()
	vbox.mouse_filter = Control.MOUSE_FILTER_STOP
	_merge_panel.add_child(vbox)

	var title := Label.new()
	title.text = "⚡ Merge"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 14)
	vbox.add_child(title)

	var merge_btn := Button.new()
	merge_btn.text = "%s (0⛏ 0🛢)" % display_text
	merge_btn.custom_minimum_size = Vector2(200, 30)
	merge_btn.tooltip_text = "Sacrifice 2 %s to create 1 %s" % [source_type, target_type]
	merge_btn.pressed.connect(_on_merge_option_clicked.bind(target_type))
	vbox.add_child(merge_btn)

	var close_btn := Button.new()
	close_btn.text = "Close"
	close_btn.pressed.connect(func(): _merge_panel.visible = false; _merge_visible = false)
	vbox.add_child(close_btn)

	_merge_panel.visible = true
	_merge_visible = true


func _hide_merge_panel() -> void:
	_merge_panel.visible = false
	_merge_visible = false


func _on_merge_option_clicked(unit_type: String) -> void:
	merge_clicked.emit(unit_type)
	_merge_panel.visible = false
	_merge_visible = false


func _can_afford_and_prereq(_mine: int, _gas: int, from_key: String) -> bool:
	# Prereq checks: from_key is the BUILD_CATALOG prerequisite field
	match from_key:
		"barracks":
			# shield_station (Shield Battery) needs Gateway
			if "base" not in _completed_buildings and "Nexus" not in _completed_buildings and "CommandCenter" not in _completed_buildings and "Hatchery" not in _completed_buildings:
				return false
		"factory":
			# Terran Factory / Zerg Hydralisk Den / P Robotics needs barracks-line
			if "barracks" not in _completed_buildings and "Barracks" not in _completed_buildings and "Spawning Pool" not in _completed_buildings and "Gateway" not in _completed_buildings:
				return false
		"starport":
			# Terran Starport / Zerg Spire / P Stargate needs factory-line
			if "factory" not in _completed_buildings and "Factory" not in _completed_buildings and "Hydralisk Den" not in _completed_buildings and "Robotics Facility" not in _completed_buildings:
				return false
		"morph_base":
			# Zerg Lair + tier-2 tech buildings require Hatchery/Lair
			if "morph_base" not in _completed_buildings and "base" not in _completed_buildings and "Lair" not in _completed_buildings and "Hatchery" not in _completed_buildings:
				return false
		"tech_basic":
			# Protoss Photon Cannon needs Forge
			if "tech_basic" not in _completed_buildings and "Forge" not in _completed_buildings:
				return false
		"tech_cyber":
			# Protoss Citadel → needs Cybernetics Core
			if "tech_cyber" not in _completed_buildings and "CyberneticsCore" not in _completed_buildings and "Cybernetics Core" not in _completed_buildings:
				return false
		"tech_infantry":
			# Protoss Citadel of Adun needs Cybernetics Core
			if "tech_cyber" not in _completed_buildings and "CyberneticsCore" not in _completed_buildings and "Cybernetics Core" not in _completed_buildings:
				return false
		"armory":
			# Terran Armory needs Factory
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
	_rebuild_build_panel()
	_hide_train_panel()
	_hide_upgrade_panel()
	_hide_research_panel()


func hide_build_panel() -> void:
	_build_visible = false
	_build_panel.visible = false
	build_panel_closed.emit()


func is_train_panel_visible() -> bool:
	return _train_visible

func is_upgrade_panel_visible() -> bool:
	return _upgrade_visible

func is_research_panel_visible() -> bool:
	return _research_visible

func is_merge_panel_visible() -> bool:
	return _merge_visible
