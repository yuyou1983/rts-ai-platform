class_name TestModeGallery
extends Node2D
## Standalone Test Mode gallery — extracted from GameView.
##
## Manages the asset-preview gallery, filter UI, catalog, animation state,
## and save/restore of game state. Emits signals so that GameView can react
## (swap entity arrays, update sprites, redraw, etc.).

signal entities_rebuilt(new_ents: Array)
signal state_changed()

const UNIT_TYPE_CATALOG_PATH := "res://resources/unit_type_catalog.json"
const ANIM_FPS := 8.0  # frames per second for walk cycle
const ATTACK_FLASH_DURATION: float = 0.1

# ─── Internal state ────────────────────────────────────────
var _active: bool = false
var _test_ents: Array = []
var _test_section_headers: Array = []

# ─── UI elements ───────────────────────────────────────────
var _test_btn: Button = null
var _test_filter_panel: PanelContainer = null
var _test_race_filter: OptionButton = null   # Kept for batch compat
var _test_kind_filter: OptionButton = null   # Kept for batch compat
var _test_batch_filter: OptionButton = null
var _elev_btn: Button = null
var _zoom_in_btn: Button = null
var _zoom_out_btn: Button = null

# ─── Filter state ──────────────────────────────────────────
var _test_filter_race: String = ""    # "" = all, "terran"/"zerg"/"protoss"
var _test_filter_kind: String = ""    # "" = all, "unit"/"building"
var _test_filter_domain: String = ""  # "" = all, "ground"/"air"
var _test_filter_role: String = ""    # "" = all
var _test_filter_tier: String = ""    # "" = all
var _test_preview_mode: String = "idle"  # "idle"/"move"/"attack"
var _test_filter_batch: String = "all"

# ─── Filter button groups ──────────────────────────────────
var _race_buttons: Dictionary = {}   # { value: Button }
var _kind_buttons: Dictionary = {}   # { value: Button }
var _domain_buttons: Dictionary = {}  # { value: Button }
var _role_buttons: Dictionary = {}   # { value: Button }
var _tier_buttons: Dictionary = {}   # { value: Button }
var _preview_buttons: Dictionary = {}  # { value: Button }

# ─── Unit type catalog ─────────────────────────────────────
var _unit_type_catalog: Dictionary = {}  # Loaded from unit_type_catalog.json

# ─── Saved game state (for restoring) ───────────────────────
var _saved_ents: Array = []
var _saved_player_races: Dictionary = {}
var _saved_fog_tiles: PackedInt32Array = []
var _saved_fog_w: int = 0
var _saved_fog_h: int = 0

# ─── Animation state ───────────────────────────────────────
var _anim_frame: int = 0
var _anim_tick: float = 0.0
var _attack_flash_timers: Dictionary = {}  # entity_id → remaining flash seconds

# ─── External references (injected via setup) ───────────────
var _ui_layer: CanvasLayer = null
var _sprite_loader: Node = null      # SpriteLoader
var _default_font: Font = null
var _entity_cache_by_id: Dictionary = {}
var _sprite_pool: Dictionary = {}    # Injected via setup()
var _cam_ctrl: Node = null           # CameraController (optional)
var _show_elevation: bool = false


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────

func is_active() -> bool:
	return _active


func setup(ui_layer: CanvasLayer, sprite_loader: Node, default_font: Font,
		entity_cache_by_id: Dictionary, sprite_pool: Dictionary = {},
		cam_ctrl: Node = null) -> void:
	_ui_layer = ui_layer
	_sprite_loader = sprite_loader
	_default_font = default_font
	_entity_cache_by_id = entity_cache_by_id
	_sprite_pool = sprite_pool
	_cam_ctrl = cam_ctrl
	_load_unit_type_catalog()

	# ── Test Mode button ──
	_test_btn = Button.new()
	_test_btn.text = "🧪 Test Mode"
	_test_btn.tooltip_text = "Click to preview all sprites on map"
	_test_btn.position = Vector2(8, 8)
	_test_btn.size = Vector2(120, 32)
	_test_btn.modulate = Color(0.8, 1.0, 0.8)
	_ui_layer.add_child(_test_btn)
	_test_btn.pressed.connect(toggle)

	_create_test_filter_panel()

	# ── Elevation toggle button (below test button) ──
	_elev_btn = Button.new()
	_elev_btn.text = "⛰ Elev"
	_elev_btn.tooltip_text = "Toggle terrain elevation overlay"
	_elev_btn.position = Vector2(8, 42)
	_elev_btn.size = Vector2(120, 24)
	_elev_btn.modulate = Color(0.7, 0.85, 0.7)
	_ui_layer.add_child(_elev_btn)
	_elev_btn.pressed.connect(_toggle_elevation)

	# ── Zoom buttons ──
	_zoom_in_btn = Button.new()
	_zoom_in_btn.text = "🔍+"
	_zoom_in_btn.position = Vector2(4, 30)
	_zoom_in_btn.size = Vector2(40, 24)
	_zoom_in_btn.modulate = Color(0.9, 0.95, 1.0)
	_ui_layer.add_child(_zoom_in_btn)
	_zoom_in_btn.pressed.connect(func(): _cam_ctrl._zoom_in() if _cam_ctrl else null)

	_zoom_out_btn = Button.new()
	_zoom_out_btn.text = "🔍-"
	_zoom_out_btn.position = Vector2(46, 30)
	_zoom_out_btn.size = Vector2(40, 24)
	_zoom_out_btn.modulate = Color(0.9, 0.95, 1.0)
	_ui_layer.add_child(_zoom_out_btn)
	_zoom_out_btn.pressed.connect(func(): _cam_ctrl._zoom_out() if _cam_ctrl else null)


func set_sprite_pool(sprite_pool: Dictionary) -> void:
	_sprite_pool = sprite_pool


func toggle_elevation() -> void:
	_toggle_elevation()


func is_elevation_active() -> bool:
	return _show_elevation


func toggle() -> void:
	_active = not _active
	if _active:
		_build_test_entities()
		if _test_filter_panel:
			_test_filter_panel.visible = true
		if _test_btn:
			_test_btn.text = "Back"
			_test_btn.modulate = Color(1.0, 0.8, 0.8)
		print("[TEST MODE] ON — generated asset gallery")
	else:
		_clear_test_sprites()
		_test_ents.clear()
		_test_section_headers.clear()
		if _test_filter_panel:
			_test_filter_panel.visible = false
		if _test_btn:
			_test_btn.text = "🧪 Test Mode"
			_test_btn.modulate = Color(0.8, 1.0, 0.8)
		print("[TEST MODE] OFF — back to normal game")
	state_changed.emit()


func build() -> void:
	_build_test_entities()


func clear() -> void:
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()


func save_state(ents: Array, player_races: Dictionary, fog_tiles: PackedInt32Array,
		fog_w: int, fog_h: int) -> void:
	_saved_ents = ents.duplicate(true)
	_saved_player_races = player_races.duplicate(true)
	_saved_fog_tiles = fog_tiles
	_saved_fog_w = fog_w
	_saved_fog_h = fog_h


func get_saved_state() -> Dictionary:
	return {
		"ents": _saved_ents.duplicate(true),
		"player_races": _saved_player_races.duplicate(true),
		"fog_tiles": _saved_fog_tiles,
		"fog_w": _saved_fog_w,
		"fog_h": _saved_fog_h,
	}


func draw_labels(canvas: CanvasItem) -> void:
	var font: Font = _default_font
	if not font:
		return
	var title_size := 1.2
	var label_size := 0.8
	var vc_label_size := 0.55
	for header in _test_section_headers:
		canvas.draw_string(
			font,
			header.get("pos", Vector2.ZERO),
			str(header.get("text", "")),
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			title_size,
			header.get("color", Color.WHITE)
		)
	for e in _test_ents:
		if not str(e.get("id", "")).begins_with("test_"):
			continue
		if bool(e.get("preview_hidden", false)):
			continue
		var full_label = str(e.get("label", ""))
		if full_label == "":
			continue
		canvas.draw_string(
			font,
			Vector2(float(e.get("px", 0.0)) + 1.3, float(e.get("py", 0.0)) - 0.3),
			full_label,
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			label_size,
			Color(1, 1, 1, 0.9)
		)
		# Visual class grouping label below the sprite
		var vc = str(e.get("visual_class", ""))
		if vc != "":
			var entity_type = str(e.get("entity_type", ""))
			var vc_y_offset = 2.5 if entity_type == "unit" else 4.2 if entity_type == "building" else 2.5
			canvas.draw_string(
				font,
				Vector2(float(e.get("px", 0.0)) + 1.3, float(e.get("py", 0.0)) + vc_y_offset),
				vc,
				HORIZONTAL_ALIGNMENT_LEFT,
				-1,
				vc_label_size,
				Color(0.7, 0.9, 1.0, 0.7)
			)


func advance_animation(delta: float) -> void:
	if not _active:
		return
	_anim_tick += delta
	if _anim_tick >= 1.0 / ANIM_FPS:
		_anim_tick -= 1.0 / ANIM_FPS
		_anim_frame = (_anim_frame + 1) % 17
		for e in _test_ents:
			if str(e.get("preview_action", "")) == "attack":
				_attack_flash_timers[str(e.get("id", ""))] = ATTACK_FLASH_DURATION
		state_changed.emit()


func get_anim_frame() -> int:
	return _anim_frame


func get_attack_flash_timers() -> Dictionary:
	return _attack_flash_timers


func tick_attack_flash_timers(delta: float) -> void:
	var flash_ids: Array = _attack_flash_timers.keys()
	for eid in flash_ids:
		var remaining: float = float(_attack_flash_timers[eid]) - delta
		if remaining <= 0.0:
			_attack_flash_timers.erase(eid)
		else:
			_attack_flash_timers[eid] = remaining


# ────────────────────────────────────────────────────────────
# Filter panel creation
# ────────────────────────────────────────────────────────────

func _create_test_filter_panel() -> void:
	_test_filter_panel = PanelContainer.new()
	_test_filter_panel.visible = false
	_test_filter_panel.anchor_left = 0.0
	_test_filter_panel.anchor_top = 0.0
	_test_filter_panel.anchor_right = 0.0
	_test_filter_panel.anchor_bottom = 0.0
	_test_filter_panel.offset_left = 132
	_test_filter_panel.offset_top = 8
	_test_filter_panel.offset_right = 900
	_test_filter_panel.offset_bottom = 175
	_ui_layer.add_child(_test_filter_panel)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	_test_filter_panel.add_child(vbox)

	# Row 1: Race filter
	var row1 := HBoxContainer.new()
	row1.add_theme_constant_override("separation", 4)
	vbox.add_child(row1)
	_add_row_label(row1, "Race:")
	_race_buttons = _make_toggle_group(row1, ["All", "Terran", "Zerg", "Protoss"],
		["", "terran", "zerg", "protoss"], _test_filter_race, "_on_race_filter_btn")

	# Row 2: Kind filter
	var row2 := HBoxContainer.new()
	row2.add_theme_constant_override("separation", 4)
	vbox.add_child(row2)
	_add_row_label(row2, "Type:")
	_kind_buttons = _make_toggle_group(row2, ["All", "Units", "Buildings"],
		["", "unit", "building"], _test_filter_kind, "_on_kind_filter_btn")

	# Row 3: Domain filter
	var row3 := HBoxContainer.new()
	row3.add_theme_constant_override("separation", 4)
	vbox.add_child(row3)
	_add_row_label(row3, "Domain:")
	_domain_buttons = _make_toggle_group(row3, ["All", "Ground", "Air"],
		["", "ground", "air"], _test_filter_domain, "_on_domain_filter_btn")

	# Row 4: Role filter
	var row4 := HBoxContainer.new()
	row4.add_theme_constant_override("separation", 4)
	vbox.add_child(row4)
	_add_row_label(row4, "Role:")
	_role_buttons = _make_toggle_group(row4, ["All", "Worker", "Infantry", "Vehicle", "Air", "Caster", "Siege", "Support"],
		["", "worker", "infantry", "vehicle", "air", "caster", "siege", "support"], _test_filter_role, "_on_role_filter_btn")

	# Row 5: Tier filter
	var row5 := HBoxContainer.new()
	row5.add_theme_constant_override("separation", 4)
	vbox.add_child(row5)
	_add_row_label(row5, "Tier:")
	_tier_buttons = _make_toggle_group(row5, ["All", "Basic", "Advanced", "Tech"],
		["", "basic", "advanced", "tech"], _test_filter_tier, "_on_tier_filter_btn")

	# Row 6: Preview mode
	var row6 := HBoxContainer.new()
	row6.add_theme_constant_override("separation", 4)
	vbox.add_child(row6)
	_add_row_label(row6, "Preview:")
	_preview_buttons = _make_toggle_group(row6, ["Idle", "Move", "Attack"],
		["idle", "move", "attack"], _test_preview_mode, "_on_preview_mode_btn")

	# Keep batch filter as OptionButton (it has dynamic content)
	var batch_row := HBoxContainer.new()
	batch_row.add_theme_constant_override("separation", 4)
	vbox.add_child(batch_row)
	_add_row_label(batch_row, "Batch:")
	_test_batch_filter = OptionButton.new()
	_add_filter_item(_test_batch_filter, "All", "all")
	if _sprite_loader:
		var batches = _sprite_loader.get_batches()
		for b in batches:
			var b_str = str(b)
			_add_filter_item(_test_batch_filter, b_str.to_upper(), b_str.to_lower())
	_test_batch_filter.item_selected.connect(_on_test_batch_filter_selected)
	batch_row.add_child(_test_batch_filter)


func _add_row_label(row: HBoxContainer, text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.custom_minimum_size.x = 60
	row.add_child(lbl)


func _make_toggle_group(
	row: HBoxContainer,
	labels: Array,
	values: Array,
	current: String,
	callback: String
) -> Dictionary:
	# Returns { value: Button } dictionary for highlight management
	var buttons: Dictionary = {}
	for i in range(labels.size()):
		var btn := Button.new()
		btn.text = labels[i]
		btn.toggle_mode = true
		# Highlight active button
		var val: String = values[i]
		if val == current:
			btn.button_pressed = true
			btn.modulate = Color(0.5, 1.0, 0.5)
		else:
			btn.modulate = Color(0.85, 0.85, 0.85)
		btn.pressed.connect(_on_filter_btn_pressed.bind(val, callback, buttons))
		row.add_child(btn)
		buttons[val] = btn
	return buttons


func _on_filter_btn_pressed(value: String, callback: String, buttons: Dictionary) -> void:
	# Update button highlights
	for btn_val in buttons:
		var btn: Button = buttons[btn_val]
		if btn_val == value:
			btn.button_pressed = true
			btn.modulate = Color(0.5, 1.0, 0.5)
		else:
			btn.button_pressed = false
			btn.modulate = Color(0.85, 0.85, 0.85)
	# Dispatch to specific handler
	call(callback, value)


# ────────────────────────────────────────────────────────────
# Filter callbacks
# ────────────────────────────────────────────────────────────

func _on_race_filter_btn(value: String) -> void:
	_test_filter_race = value
	if _active:
		_build_test_entities()


func _on_kind_filter_btn(value: String) -> void:
	_test_filter_kind = value
	if _active:
		_build_test_entities()


func _on_domain_filter_btn(value: String) -> void:
	_test_filter_domain = value
	if _active:
		_build_test_entities()


func _on_role_filter_btn(value: String) -> void:
	_test_filter_role = value
	if _active:
		_build_test_entities()


func _on_tier_filter_btn(value: String) -> void:
	_test_filter_tier = value
	if _active:
		_build_test_entities()


func _on_preview_mode_btn(value: String) -> void:
	_test_preview_mode = value
	if _active:
		_build_test_entities()


func _add_filter_item(option: OptionButton, label: String, value: String) -> void:
	option.add_item(label)
	option.set_item_metadata(option.item_count - 1, value)


func _on_test_batch_filter_selected(index: int) -> void:
	if _test_batch_filter == null:
		return
	_test_filter_batch = str(_test_batch_filter.get_item_metadata(index))
	if _active:
		_build_test_entities()


# ────────────────────────────────────────────────────────────
# Toggle elevation
# ────────────────────────────────────────────────────────────

func _toggle_elevation() -> void:
	_show_elevation = not _show_elevation
	if _elev_btn:
		_elev_btn.text = "⛰ Elev ON" if _show_elevation else "⛰ Elev"
		_elev_btn.modulate = Color(0.5, 1.0, 0.5) if _show_elevation else Color(0.7, 0.85, 0.7)
	state_changed.emit()


# ────────────────────────────────────────────────────────────
# Catalog loading & filtering
# ────────────────────────────────────────────────────────────

func _load_unit_type_catalog() -> void:
	if not FileAccess.file_exists(UNIT_TYPE_CATALOG_PATH):
		push_warning("[TestModeGallery] Missing unit type catalog: %s — falling back to unfiltered test mode" % UNIT_TYPE_CATALOG_PATH)
		_unit_type_catalog = {}
		return
	var raw_text: String = FileAccess.get_file_as_string(UNIT_TYPE_CATALOG_PATH)
	var parsed = JSON.parse_string(raw_text)
	if parsed is Dictionary:
		# Strip _meta key — it's not a unit entry
		_unit_type_catalog = {}
		for key in parsed.keys():
			if key.nocasecmp_to("_meta") != 0:
				var entry: Dictionary = parsed[key]
				if entry is Dictionary:
					_unit_type_catalog[key] = entry
		if _unit_type_catalog.size() > 0:
			print("[TestModeGallery] Unit type catalog loaded: %d entries" % _unit_type_catalog.size())
		else:
			push_warning("[TestModeGallery] Unit type catalog was empty after stripping _meta")
			_unit_type_catalog = {}
	else:
		push_warning("[TestModeGallery] Invalid unit type catalog: %s" % UNIT_TYPE_CATALOG_PATH)
		_unit_type_catalog = {}


## Check whether a unit_type passes all current filter state using the catalog.
## Returns true if the unit should be shown, false if filtered out.
## When catalog is empty (failed to load), always returns true (backward compat).
func _catalog_passes_filters(unit_id: String) -> bool:
	if _unit_type_catalog.is_empty():
		return true  # Backward compatibility: show all if no catalog
	var entry: Dictionary = _unit_type_catalog.get(unit_id, {})
	if entry.is_empty():
		# Unit not in catalog — still show it (backward compat)
		return true
	# Race filter
	if _test_filter_race != "":
		var race: String = str(entry.get("race", "")).to_lower()
		if race != _test_filter_race:
			return false
	# Kind filter
	if _test_filter_kind != "":
		var kind: String = str(entry.get("kind", "")).to_lower()
		if kind != _test_filter_kind:
			return false
	# Domain filter
	if _test_filter_domain != "":
		var domain: String = str(entry.get("domain", "")).to_lower()
		if domain != _test_filter_domain:
			return false
	# Role filter
	if _test_filter_role != "":
		var role: String = str(entry.get("role", "")).to_lower()
		if role != _test_filter_role:
			return false
	# Tier filter
	if _test_filter_tier != "":
		var tier: String = str(entry.get("tier", "")).to_lower()
		if tier != _test_filter_tier:
			return false
	return true


# ────────────────────────────────────────────────────────────
# Build / clear test entities
# ────────────────────────────────────────────────────────────

func _build_test_entities() -> void:
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()

	var assets: Dictionary = _sprite_loader.get_generated_assets() if _sprite_loader else {}
	# Apply batch filter first — use SpriteLoader batch API if active
	if _test_filter_batch != "all" and _sprite_loader:
		var batch_assets = _sprite_loader.get_assets_by_batch(_test_filter_batch)
		assets = batch_assets
	var kind_x: Dictionary = {"building": 5.0, "unit": 26.0, "resource": 53.0}
	var kind_title: Dictionary = {"building": "Buildings", "unit": "Units", "resource": "Resources"}
	var race_order: Array = ["terran", "zerg", "protoss", "neutral"]
	var kind_order: Array = ["building", "unit", "resource"]

	for kind in kind_order:
		# Kind filter: if catalog is loaded, filter uses "" for "all"
		var kind_filter_val: String = _test_filter_kind if _unit_type_catalog.is_empty() else _test_filter_kind
		if kind_filter_val != "" and kind_filter_val != kind:
			continue
		# Legacy compat: old filter used "all" for all
		if _unit_type_catalog.is_empty() and _test_filter_kind != "" and _test_filter_kind != kind:
			continue
		var x: float = float(kind_x[kind])
		var y: float = 4.0
		_add_test_header(kind_title[kind], Vector2(x, 2.5), Color(0.75, 0.9, 1.0))
		for race in race_order:
			var race_filter_val: String = _test_filter_race
			if race_filter_val != "" and race_filter_val != race:
				continue
			var ids: Array = []
			for asset_id in assets.keys():
				var entry: Dictionary = assets[asset_id]
				if str(entry.get("kind", "")) != kind:
					continue
				# Use catalog for additional filtering (domain, role, tier)
				if not _catalog_passes_filters(str(asset_id)):
					continue
				if _test_asset_race(str(asset_id), entry) != race:
					continue
				ids.append(str(asset_id))
			# Sort buildings by (race, tech_tier); sort units by (race, visual_class)
			if kind == "building":
				ids.sort_custom(func(a, b):
					var ea = assets.get(a, {})
					var eb = assets.get(b, {})
					var ta = int(ea.get("tech_tier", 1))
					var tb = int(eb.get("tech_tier", 1))
					if ta != tb:
						return ta < tb
					return a.nocasecmp_to(b) < 0
				)
			elif kind == "unit":
				ids.sort_custom(func(a, b):
					var ea = assets.get(a, {})
					var eb = assets.get(b, {})
					var vca = str(ea.get("visual_class", ""))
					var vcb = str(eb.get("visual_class", ""))
					if vca != vcb:
						return vca.nocasecmp_to(vcb) < 0
					return a.nocasecmp_to(b) < 0
				)
			else:
				ids.sort()
			if ids.is_empty():
				continue

			_add_test_header(
				"%s %s" % [_test_race_label(race), kind_title[kind]],
				Vector2(x, y),
				_test_race_color(race)
			)
			y += 2.0

			for asset_id in ids:
				var entry: Dictionary = assets[asset_id]
				if kind == "unit":
					# Preview mode controls which unit poses are shown
					match _test_preview_mode:
						"idle":
							_test_ents.append(_make_test_asset_entity(asset_id, entry, race, "unit", Vector2(x, y), ""))
							y += 3.2
						"move":
							_test_ents.append(_make_test_asset_entity(asset_id, entry, race, "unit", Vector2(x, y), "moving"))
							y += 3.2
						"attack":
							_add_test_unit_pair(asset_id, entry, race, Vector2(x, y))
							y += 3.2
						_:
							# Fallback: show all three (legacy behavior)
							_add_test_unit_pair(asset_id, entry, race, Vector2(x, y))
							y += 3.2
				else:
					_test_ents.append(_make_test_asset_entity(asset_id, entry, race, kind, Vector2(x, y)))
					y += 4.6 if kind == "building" else 3.0

	entities_rebuilt.emit(_test_ents)


func _clear_test_entities() -> void:
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()


func _clear_test_sprites() -> void:
	var to_remove: Array = []
	for eid in _sprite_pool:
		if str(eid).begins_with("test_"):
			_sprite_pool[eid].queue_free()
			to_remove.append(eid)
	for eid in to_remove:
		_sprite_pool.erase(eid)


# ────────────────────────────────────────────────────────────
# Test entity helpers
# ────────────────────────────────────────────────────────────

func _add_test_header(text: String, pos: Vector2, color: Color) -> void:
	_test_section_headers.append({"text": text, "pos": pos, "color": color})


func _add_test_unit_pair(asset_id: String, entry: Dictionary, race: String, pos: Vector2) -> void:
	var move_entity := _make_test_asset_entity(asset_id, entry, race, "unit", pos, "moving")
	_test_ents.append(move_entity)

	var attack_pos := pos + Vector2(6.0, 0.0)
	var attack_entity := _make_test_asset_entity(asset_id, entry, race, "unit", attack_pos, "attack")
	var target_id := "%s_target" % str(attack_entity["id"])
	attack_entity["attack_target_id"] = target_id
	_test_ents.append(attack_entity)
	_test_ents.append({
		"id": target_id,
		"owner": attack_entity["owner"],
		"type": "marker",
		"entity_type": "marker",
		"unit_type": "",
		"building_type": "",
		"resource_type": "",
		"preview_hidden": true,
		"px": attack_pos.x + 2.0,
		"py": attack_pos.y,
		"health": 0,
		"max_health": 0,
		"is_idle": true,
		"carry_amount": 0,
		"carry_capacity": 0,
		"attack": 0,
		"attack_range": 0,
		"speed": 0,
		"resource_amount": 0,
		"attack_target_id": "",
		"target_x": 0,
		"target_y": 0,
		"energy": 0,
		"max_energy": 0,
	})


func _make_test_asset_entity(
	asset_id: String,
	entry: Dictionary,
	race: String,
	kind: String,
	pos: Vector2,
	action: String = ""
) -> Dictionary:
	var owner := _test_owner_for_race(race)
	var entity_type := "building" if kind == "building" else ("resource" if kind == "resource" else "unit")
	var visual_class = str(entry.get("visual_class", ""))
	var label := asset_id
	if kind == "unit":
		var action_tag = "atk" if action == "attack" else "move"
		if "air" in visual_class:
			label = "✈%s %s" % [asset_id, action_tag]
		else:
			label = "%s %s" % [asset_id, action_tag]
	var entity := {
		"id": "test_%s_%s_%s" % [kind, asset_id, action if action != "" else "idle"],
		"owner": owner,
		"type": entity_type,
		"entity_type": entity_type,
		"unit_type": asset_id if kind == "unit" else "",
		"building_type": asset_id if kind == "building" else "",
		"resource_type": asset_id if kind == "resource" else "",
		"generated_asset_id": asset_id,
		"preview_action": action,
		"label": label,
		"visual_class": visual_class,
		"tech_tier": int(entry.get("tech_tier", 1)) if kind == "building" else -1,
		"uses_sprite": kind == "resource",
		"render_scale": float(entry.get("render_scale", 0.018)),
		"px": pos.x,
		"py": pos.y,
		"health": 1000 if kind == "building" else 100,
		"max_health": 1000 if kind == "building" else 100,
		"is_idle": action == "",
		"carry_amount": 0,
		"carry_capacity": 0,
		"attack": 10 if kind == "unit" else 0,
		"attack_range": 5 if kind == "unit" else 0,
		"speed": 3 if kind == "unit" else 0,
		"resource_amount": 0,
		"attack_target_id": "",
		"target_x": pos.x + 2.0 if action == "moving" else 0,
		"target_y": pos.y if action == "moving" else 0,
		"energy": 0,
		"max_energy": 0,
	}
	return entity


func _test_asset_race(asset_id: String, entry: Dictionary) -> String:
	var race := str(entry.get("race", "")).to_lower()
	if race != "":
		return race
	match asset_id:
		"SCV", "Marine", "CommandCenter", "Barracks", "Refinery":
			return "terran"
		"Drone", "Zergling", "Hatchery", "SpawningPool", "Extractor":
			return "zerg"
		"Probe", "Zealot", "Nexus", "Gateway", "Pylon", "Assimilator":
			return "protoss"
		_:
			return "neutral"


func _test_owner_for_race(race: String) -> int:
	match race:
		"terran":
			return 1
		"zerg":
			return 2
		"protoss":
			return 3
		_:
			return 0


func _test_race_label(race: String) -> String:
	match race:
		"terran":
			return "Terran"
		"zerg":
			return "Zerg"
		"protoss":
			return "Protoss"
		_:
			return "Neutral"


func _test_race_color(race: String) -> Color:
	match race:
		"terran":
			return Color(0.45, 0.65, 1.0)
		"zerg":
			return Color(1.0, 0.45, 0.35)
		"protoss":
			return Color(1.0, 0.85, 0.25)
		_:
			return Color(0.75, 0.75, 0.75)
