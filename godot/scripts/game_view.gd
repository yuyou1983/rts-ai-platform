extends Node2D

## RTS Game View — Full interactive RTS prototype.
## Sprint 4: Integrates CameraController, HUD, RallyPointIndicator,
## enhanced SelectionManager (caps, double-click, formation),
## enhanced FogRenderer (gradient edges), enhanced Minimap (fog, attack indicators).
##
## Controls:
##   WASD / Arrow keys     Move camera
##   Mouse edge scroll     Move camera
##   Scroll wheel          Zoom (0.5x - 2.0x)
##   Middle-click drag     Pan camera
##   F key                 Camera follow selected group
##   Left click / drag     Select units
##   Shift+click           Add to selection
##   Ctrl+click / Double-click  Select all same-type on screen
##   1-9                   Recall control group
##   Ctrl+1-9              Create control group
##   Shift+1-9             Add to control group
##   Double-tap 1-9        Jump camera to group
##   Right click           Context action (move / attack / gather / build / rally)
##   M / S / A / P / H     Ability hotkeys (move/stop/attack/patrol/hold)
##   G + click             Gather (workers)
##   B                     Toggle build menu (with worker selected)
##   T                     Train worker/soldier (with building selected)
##   Esc                   Deselect all

const GrpcBridgeScript := preload("res://scripts/grpc_bridge.gd")
const CallableStateMachine = preload("res://scripts/callable_state_machine.gd")
const CameraControllerScript = preload("res://scripts/camera_controller.gd")
const HUDScene := preload("res://scenes/hud.tscn")
const VictoryScene := preload("res://scenes/victory_screen.tscn")
const RallyPointIndicatorScript = preload("res://scripts/rally_point_indicator.gd")
const VFXManagerScript = preload("res://scripts/vfx_manager.gd")
const SpriteLoaderScript = preload("res://scripts/sprite_loader.gd")
const PRESENTATION_MANIFEST_PATH := "res://resources/presentation_manifest.json"
const UNIT_TYPE_CATALOG_PATH := "res://resources/unit_type_catalog.json"
const HUD_FULL_HEIGHT := 480

# ─── Config ────────────────────────────────────────────────
@onready var _camera: Camera2D = $Camera2D
var _cell: float = 1.0
var _map_w: float = 64.0
var _map_h: float = 64.0

# ─── State ─────────────────────────────────────────────────
var _bridge
var _frame: int = 0
var _default_font: Font
var _analysis_written := false
var _feel_config: Dictionary = {}

# Entity cache
var _ents: Array = []
var _prev_hp: Dictionary = {}
var _prev_entities: Dictionary = {}
var _dmg_floats: Array = []

# ─── Combat visual feedback ───────────────────────────────
var _attack_flash_timers: Dictionary = {}  # entity_id → remaining flash seconds
var _dead_effects: Array = []  # [{pos: Vector2, age: float, lifetime: float, color: Color, owner: int, entity_type: String}]
var _hovered_entity_id: String = ""  # ID of entity currently under mouse cursor
var _hover_check_timer: float = 0.0  # throttle hover detection
var _game_time: float = 0.0  # accumulated time for sin-based animations
var _prev_attack_targets: Dictionary = {}  # entity_id → previous attack_target_id
const ATTACK_FLASH_DURATION: float = 0.1
const DEATH_EFFECT_DURATION: float = 0.5
const HOVER_CHECK_INTERVAL: float = 0.05  # check hover every 50ms
const SELECTION_BREATHE_SPEED: float = 3.0  # radians/sec for selection ring pulse
const SELECTION_BREATHE_MIN: float = 0.55  # min alpha for breathing
const SELECTION_BREATHE_MAX: float = 1.0  # max alpha for breathing

# ─── Drag-select ───────────────────────────────────────────
var _dragging := false
var _drag_start := Vector2.ZERO
var _drag_end := Vector2.ZERO
const SELECT_RADIUS := 1.5
const PYLON_POWER_RADIUS: float = 8.0

# ─── Command ping feedback ──────────────────────────────────
var _command_pings: Array = []  # [{pos: Vector2, age: float, duration: float, color: Color, type: String}]
var _control_group_hints: Array = []  # [{text: String, age: float, duration: float}]
var _ground_ping_duration: float = 0.32
var _ground_ping_color: Color = Color(0.267, 1.0, 0.533)  # #44ff88
var _attack_ping_duration: float = 0.38
var _attack_ping_color: Color = Color(1.0, 0.267, 0.267)  # #ff4444
var _invalid_ping_duration: float = 0.22
var _invalid_ping_color: Color = Color(0.667, 0.4, 0.4)  # #aa6666
var _assign_flash_duration: float = 0.5
var _empty_group_hint_duration: float = 0.8
var _test_mode: bool = false
var _test_ents: Array = []
var _test_btn: Button = null
var _test_filter_panel: PanelContainer = null
var _test_race_filter: OptionButton = null  # Kept for batch compat
var _test_kind_filter: OptionButton = null  # Kept for batch compat
var _race_buttons: Dictionary = {}  # { value: Button } for race filter
var _kind_buttons: Dictionary = {}  # { value: Button } for kind filter
var _domain_buttons: Dictionary = {}  # { value: Button } for domain filter
var _role_buttons: Dictionary = {}  # { value: Button } for role filter
var _tier_buttons: Dictionary = {}  # { value: Button } for tier filter
var _preview_buttons: Dictionary = {}  # { value: Button } for preview mode
var _elev_btn: Button = null
var _zoom_in_btn: Button = null
var _zoom_out_btn: Button = null
var _saved_ents: Array = []
var _saved_player_races: Dictionary = {}
var _saved_fog_tiles: PackedInt32Array = []
var _saved_fog_w: int = 0
var _saved_fog_h: int = 0
var _test_filter_race: String = ""  # "" = all, "terran"/"zerg"/"protoss"
var _test_filter_kind: String = ""  # "" = all, "unit"/"building"
var _test_filter_domain: String = ""  # "" = all, "ground"/"air"
var _test_filter_role: String = ""  # "" = all
var _test_filter_tier: String = ""  # "" = all
var _test_preview_mode: String = "idle"  # "idle"/"move"/"attack"
var _test_filter_batch: String = "all"
var _test_section_headers: Array = []
var _test_batch_filter: OptionButton = null
var _unit_type_catalog: Dictionary = {}  # Loaded from unit_type_catalog.json
# Animation state
var _anim_frame: int = 0
var _anim_tick: float = 0.0
const ANIM_FPS := 8.0  # frames per second for walk cycle
# Unit animation layout: row, cols, frame_width, frame_height per unit per owner
var _unit_anim_info: Dictionary = {}

# Phase D: Elevation
var _height_map: Array = []        # 2D array [y][x] → int 0..8
var _height_map_w: int = 64
var _height_map_h: int = 64
var _elevation_dirty: bool = false  # redraw flag
var _show_elevation: bool = false   # default OFF — toggle via debug button

# ─── Build mode ────────────────────────────────────────────
var _build_mode := false
var _build_type: String = ""   # Which building the player selected in HUD

# ─── Game state ────────────────────────────────────────────
var _game_active := false
var _game_over_shown := false
var _replay_mode := false
var _replay_player: ReplayPlayer
var _replay_overlay: Control
var _victory_screen: CanvasLayer

# ─── APM counter ───────────────────────────────────────────
var _apm_action_times: Array = []  # timestamps of effective actions
var _apm_value: int = 0  # computed APM, updated every second
var _apm_label: Label
var _apm_timer: float = 0.0
var _total_actions: int = 0  # lifetime count for end-of-game stats

# ─── Fog of war ────────────────────────────────────────────
var _fog_tiles: PackedInt32Array = []
var _fog_w: int = 0
var _fog_h: int = 0
# Smooth fog: per-tile rendered alpha, fades out over FOG_FADE_FRAMES frames
var _fog_alpha: PackedFloat32Array = []
var _fog_prev_tiles: PackedInt32Array = []  # previous tick's raw fog state
const FOG_FADE_FRAMES := 15  # ~0.5s at 30fps before fully fading

# ─── Jitter monitor ────────────────────────────────────────
var _jitter_count: int = 0
var _total_jitter_px: float = 0.0

# ─── Control group double-tap ──────────────────────────────
var _last_group_key: int = -1
var _last_group_time: float = 0.0

# ─── Minimap ───────────────────────────────────────────────
var _mm_size := Vector2(152, 136)  # minimap inner drawing area
var _mm_margin := Vector2(12, 28)  # bottom-right float: x=8+4, y=8+20
var _mm_rect_node: Control = null  # ref to MinimapRect node

# ─── Integrated Pattern References ─────────────────────────
var _selection: Node  # SelectionManager autoload
var _event_bus: Node  # EventBus autoload
var _ability_mgr: Node  # AbilityManager autoload

	# ─── Sprite textures ───────────────────────────────────────
var _unit_textures: Dictionary = {}
var _building_textures: Dictionary = {}
var _player_races: Dictionary = {}  # {"1": "1", "2": "2"} — maps player ID → race ID (1=Terran, 2=Zerg, 3=Protoss)
var _sprite_pool: Dictionary = {}  # entity_id -> Sprite2D
var _sprite_container: Node2D = null  # parent for all entity sprites
var _vfx_manager: VFXManager = null
var _sprite_loader: SpriteLoader = null
var _presentation_manifest: Dictionary = {}
var _map_texture: Texture2D = null

# ─── Sprint 4 Components ──────────────────────────────────
var _cam_ctrl: Node = null  # CameraController
var _hud: Control = null    # HUD
var _ui_layer: CanvasLayer = null  # UI layer for HUD, minimap, replay overlay
var _rally_indicators: Dictionary = {}  # {building_id: RallyPointIndicator}

# ─── Entity Data Provider ──────────────────────────────────
var _entity_cache_by_id: Dictionary = {}

# ─── Resources state ──────────────────────────────────────
var _p1_minerals: int = 0
var _p1_gas: int = 0
var _p1_supply_used: int = 0
var _p1_supply_cap: int = 0

func _get_entity_data(entity_id: String) -> Dictionary:
	return _entity_cache_by_id.get(entity_id, {})

func _get_entity_type(entity_id: String) -> String:
	var data := _get_entity_data(entity_id)
	if data.is_empty():
		return ""
	return str(data.get("entity_type", data.get("type", "")))

func _load_texture_or_fallback(primary_path: String, fallback_path: String) -> Texture2D:
	if ResourceLoader.exists(primary_path):
		var primary := ResourceLoader.load(primary_path, "Texture2D") as Texture2D
		if primary:
			return primary
	elif FileAccess.file_exists(primary_path):
		var image := Image.new()
		if image.load(primary_path) == OK:
			return ImageTexture.create_from_image(image)
	return load(fallback_path)

# ───────────────────────────────────────────────────────────
func _ready() -> void:
	_default_font = ThemeDB.fallback_font

	# Check if entering in replay mode (set by main_menu)
	var _replay_match_id: String = ""
	if Engine.has_meta("replay_match_id"):
		_replay_match_id = Engine.get_meta("replay_match_id")
		Engine.remove_meta("replay_match_id")

	# ─── CanvasLayer for ALL UI (must be created before any Control children) ───
	_ui_layer = CanvasLayer.new()
	_ui_layer.layer = 10
	add_child(_ui_layer)

	_bridge = GrpcBridgeScript.new()
	_bridge.ai_player = 2
	# Pick difficulty from main menu metadata (default "medium")
	var _ai_diff: String = "medium"
	if Engine.has_meta("ai_difficulty"):
		_ai_diff = Engine.get_meta("ai_difficulty")
	_bridge.ai_difficulty = _ai_diff
	# Phase D: elevation flag (default true)
	_bridge.enable_elevation = true
	add_child(_bridge)
	_feel_config = _load_feel_config()
	if _feel_config.has("command_feedback"):
		var cf: Dictionary = _feel_config["command_feedback"]
		_ground_ping_duration = float(cf.get("ground_ping_duration", _ground_ping_duration))
		_ground_ping_color = Color.from_string(str(cf.get("ground_ping_color", "#44ff88")), _ground_ping_color)
		_attack_ping_duration = float(cf.get("attack_ping_duration", _attack_ping_duration))
		_attack_ping_color = Color.from_string(str(cf.get("attack_ping_color", "#ff4444")), _attack_ping_color)
		_invalid_ping_duration = float(cf.get("invalid_ping_duration", _invalid_ping_duration))
		_invalid_ping_color = Color.from_string(str(cf.get("invalid_ping_color", "#aa6666")), _invalid_ping_color)
	if _feel_config.has("control_group_feedback"):
		var cg: Dictionary = _feel_config["control_group_feedback"]
		_assign_flash_duration = float(cg.get("assign_flash_duration", _assign_flash_duration))
		_empty_group_hint_duration = float(cg.get("empty_group_hint_duration", _empty_group_hint_duration))
	_bridge.game_started.connect(_on_start)
	_bridge.state_updated.connect(_on_state)
	_bridge.game_over.connect(_on_game_over)
	_bridge.replay_loaded.connect(_on_replay_loaded)

	# Replay system — ReplayPlayer as child of game_view (Node), overlay in CanvasLayer
	_replay_player = ReplayPlayer.new()
	add_child(_replay_player)
	_replay_player.replay_tick.connect(_on_state)
	_replay_player.replay_finished.connect(_on_replay_finished)

	var _replay_overlay_scene := preload("res://scenes/replay_overlay.tscn")
	_replay_overlay = _replay_overlay_scene.instantiate()
	_replay_overlay.set_player(_replay_player)
	_ui_layer.add_child(_replay_overlay)

	if _replay_match_id != "":
		# Replay mode: don't start a new game, fetch replay instead
		_replay_mode = true
		_game_active = false
		_replay_overlay.visible = true
		_bridge.fetch_replay(_replay_match_id)
		print("[GameView] Replay mode: fetching %s" % _replay_match_id)
	else:
		# Normal game mode
		_bridge.start_game(42)
		_game_active = true
		_replay_overlay.visible = false

	# Connect to autoloads
	_event_bus = get_node_or_null("/root/EventBus")
	_selection = get_node_or_null("/root/SelectionManager")
	_ability_mgr = get_node_or_null("/root/AbilityManager")

	# Wire up SelectionManager data providers
	if _selection:
		_selection.entity_data_provider = _get_entity_data
		_selection.entity_type_provider = _get_entity_type
		_selection.selection_changed.connect(_on_selection_changed)
		_selection.camera_focus_requested.connect(_on_camera_focus_requested)

	# Wire up AbilityManager
	if _ability_mgr:
		_ability_mgr.set_entity_data_provider(_get_entity_data)

	# ─── Sprint 4: Create CameraController ───
	_cam_ctrl = CameraControllerScript.new()
	add_child(_cam_ctrl)
	_cam_ctrl.setup(_camera)
	_cam_ctrl.set_entity_data_provider(_get_entity_data)
	_cam_ctrl.set_map_size(_map_w, _map_h)
	# Set initial camera position to map center immediately
	_camera.position = Vector2(_map_w / 2.0, _map_h / 2.0)

	# ─── Container for entity Sprite2D nodes ───
	_sprite_container = Node2D.new()
	_sprite_container.name = "EntitySprites"
	_sprite_container.z_index = 1  # Above map bg (z=-100)
	z_index = 5  # game_view _draw() renders above entity sprites
	add_child(_sprite_container)
	_sprite_loader = SpriteLoaderScript.new()
	_load_presentation_manifest()
	_load_unit_type_catalog()

	# ─── Combat VFX layer ───
	_vfx_manager = VFXManagerScript.new()
	_vfx_manager.name = "VFXManager"
	add_child(_vfx_manager)

	# ─── Preload sprite textures (by race ID: 1=Terran, 2=Zerg, 3=Protoss) ───
	# Terran units
	_unit_textures["worker_1"] = load("res://assets/units/SCV.png")
	_unit_textures["soldier_1"] = load("res://assets/units/Marine.png")
	_unit_textures["scout_1"] = load("res://assets/units/Ghost.png")
	# Zerg units
	_unit_textures["worker_2"] = load("res://assets/units/Drone.png")
	_unit_textures["soldier_2"] = load("res://assets/units/Zergling.png")
	_unit_textures["scout_2"] = load("res://assets/units/Hydralisk.png")
	# Protoss units
	_unit_textures["worker_3"] = _load_texture_or_fallback("res://assets/sc1_generated/p0/Probe.png", "res://assets/units/Probe.png")
	_unit_textures["soldier_3"] = load("res://assets/units/Zealot.png")
	_unit_textures["scout_3"] = load("res://assets/units/Dragoon.png")
	_building_textures[1] = load("res://assets/buildings/TerranBuilding.png")
	_building_textures[2] = load("res://assets/buildings/ZergBuilding.png")
	_building_textures[3] = load("res://assets/buildings/ProtossBuilding.png")
	# ─── Unit animation metadata (row, total_cols, frame_w, frame_h, south_col) ───
	# SCV: 8-dir, row0 walk, row1 carry, row2 attack, row3 gather
	_unit_anim_info["worker_1"] = {"rows": 4, "cols": [8,8,8,4], "fw": [33,41,42,46], "fh": [41,40,40,48], "south": [4,4,4,2]}
	# Drone: 17-dir, 11 rows (walk×8, carry, attack, death). Rows spaced ~102px apart.
	_unit_anim_info["worker_2"] = {"rows": 11, "cols": [18,18,18,18,18,18,18,18,18,18,27], "fw": [37,37,34,40,42,40,34,38,38,38,34], "fh": [27,27,26,26,26,27,28,26,27,28,25], "south": [9,9,9,9,9,9,9,9,9,9,5], "row_gap": 102, "first_row_y": 52}
	# Probe: generated MPQ strip has 17 directional frames in one row.
	_unit_anim_info["worker_3"] = {"rows": 1, "cols": [17], "fw": [32], "fh": [32], "south": [8]}
	# Marine: 17-dir, many rows
	_unit_anim_info["soldier_1"] = {"rows": 14, "cols": [18,18,18,18,18,18,18,18,18,18,18,18,18,7], "fw": [20,18,16,16,21,22,22,23,23,24,23,23,23,41], "fh": [28,28,28,34,28,27,29,27,28,29,31,30,29,37], "south": [9,9,9,9,9,9,9,9,9,9,9,9,9,3]}
	# Zergling: same structure as Marine (will refine later)
	_unit_anim_info["soldier_2"] = _unit_anim_info.get("soldier_1", {})
	# Zealot: 17-dir
	_unit_anim_info["soldier_3"] = {"rows": 14, "cols": [18,18,18,18,18,18,18,18,18,18,16,18,14,6], "fw": [19,21,26,21,19,21,26,22,22,19,18,23,27,33], "fh": [33,33,32,33,36,35,35,34,34,37,39,38,40,36], "south": [9,9,9,9,9,9,9,9,9,9,8,9,7,3]}
	# Ghost: 17-dir
	_unit_anim_info["scout_1"] = {"rows": 13, "cols": [18,18,18,18,18,18,18,18,18,18,18,16,3], "fw": [22,21,20,21,23,23,24,24,24,14,11,17,107], "fh": [28,29,29,28,28,28,29,29,27,28,28,109,101], "south": [9,9,9,9,9,9,9,9,9,9,9,8,1]}
	# Hydralisk: same structure as Ghost (will refine later)
	_unit_anim_info["scout_2"] = _unit_anim_info.get("scout_1", {})
	# Dragoon (reuse Zealot info for now — will need its own sprite)
	_unit_anim_info["scout_3"] = _unit_anim_info.get("soldier_3", {})
	_map_texture = load("res://assets/maps/(2)Switchback.jpg")

	# ─── CanvasLayer for floating UI (above fullscreen game map) ───
	_ui_layer.layer = 10

	var vp_size := get_viewport().get_visible_rect().size

	# ─── Minimap: floating panel at bottom-right ───
	var mm_size := Vector2(160, 160)
	var mm_margin := 8
	var _mm_panel := PanelContainer.new()
	_mm_panel.anchor_left = 1.0
	_mm_panel.anchor_top = 1.0
	_mm_panel.anchor_right = 1.0
	_mm_panel.anchor_bottom = 1.0
	_mm_panel.offset_left = -mm_size.x - mm_margin
	_mm_panel.offset_top = -mm_size.y - mm_margin
	_mm_panel.offset_right = -mm_margin
	_mm_panel.offset_bottom = -mm_margin
	_ui_layer.add_child(_mm_panel)

	# MinimapRect: actual drawing area — CHILD of panel, not sibling
	var mm_rect := ColorRect.new()
	mm_rect.name = "MinimapRect"
	mm_rect.color = Color.BLACK
	mm_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	mm_rect.offset_left = 4
	mm_rect.offset_top = 20
	mm_rect.offset_right = -4
	mm_rect.offset_bottom = -4
	var mm_script := load("res://scripts/minimap_rect.gd")
	if mm_script:
		mm_rect.set_script(mm_script)
	_mm_panel.add_child(mm_rect)  # child of panel, not ui_layer!
	_mm_rect_node = mm_rect  # store reference

	# ─── HUD: top-right horizontal info bar ───
	_hud = HUDScene.instantiate()
	_ui_layer.add_child(_hud)
	_hud.set_entity_data_provider(_get_entity_data)
	_hud.ability_clicked.connect(_on_hud_ability_clicked)
	_hud.build_clicked.connect(_on_hud_build_clicked)
	_hud.train_clicked.connect(_on_hud_train_clicked)
	_hud.merge_clicked.connect(_on_hud_merge_clicked)
	_hud.upgrade_clicked.connect(_on_hud_upgrade_clicked)
	_hud.research_clicked.connect(_on_hud_research_clicked)
	_hud.build_panel_closed.connect(func(): _build_mode = false; _build_type = "")
	_hud.anchor_left = 1.0
	_hud.anchor_right = 1.0
	_hud.anchor_top = 0.0
	_hud.anchor_bottom = 0.0
	_hud.offset_left = -420
	_hud.offset_right = 0
	_hud.offset_top = 0
	_hud.offset_bottom = HUD_FULL_HEIGHT

	# ─── Test Mode Button (bottom-left corner) ───
	_test_btn = Button.new()
	_test_btn.text = "🧪 Test Mode"
	_test_btn.tooltip_text = "Click to preview all sprites on map"
	_test_btn.position = Vector2(8, 8)
	_test_btn.size = Vector2(120, 32)
	_test_btn.modulate = Color(0.8, 1.0, 0.8)
	_ui_layer.add_child(_test_btn)
	_test_btn.pressed.connect(_toggle_test_mode)
	_create_test_filter_panel()
	# Elevation toggle button (below test button)
	_elev_btn = Button.new()
	_elev_btn.text = "⛰ Elev"
	_elev_btn.tooltip_text = "Toggle terrain elevation overlay"
	_elev_btn.position = Vector2(8, 42)
	_elev_btn.size = Vector2(120, 24)
	_elev_btn.modulate = Color(0.7, 0.85, 0.7)
	_ui_layer.add_child(_elev_btn)
	_elev_btn.pressed.connect(_toggle_elevation)
	# Zoom buttons
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

	# ─── Victory Screen (in CanvasLayer, hidden by default) ───
	_victory_screen = VictoryScene.instantiate()
	_victory_screen.visible = false
	_ui_layer.add_child(_victory_screen)
	_victory_screen.play_again.connect(_on_victory_play_again)
	_victory_screen.quit_game.connect(_on_victory_back_to_menu)
	_victory_screen.watch_replay.connect(_on_victory_watch_replay)

	# ─── APM label (top-right HUD corner) ───
	_apm_label = Label.new()
	_apm_label.name = "APMLabel"
	_apm_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_apm_label.add_theme_font_size_override("font_size", 14)
	_apm_label.add_theme_color_override("font_color", Color(0.7, 0.9, 1.0))
	_apm_label.anchor_left = 1.0
	_apm_label.anchor_top = 0.0
	_apm_label.anchor_right = 1.0
	_apm_label.anchor_bottom = 0.0
	_apm_label.offset_left = -100
	_apm_label.offset_right = -4
	_apm_label.offset_top = 38
	_apm_label.offset_bottom = 56
	_apm_label.text = "APM: 0"
	_apm_label.visible = true
	_ui_layer.add_child(_apm_label)

	print("===== GameView ready (Human P1 vs AI P2) Sprint 4 path=", get_path())

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


func _on_race_filter_btn(value: String) -> void:
	_test_filter_race = value
	if _test_mode:
		_build_test_entities()


func _on_kind_filter_btn(value: String) -> void:
	_test_filter_kind = value
	if _test_mode:
		_build_test_entities()


func _on_domain_filter_btn(value: String) -> void:
	_test_filter_domain = value
	if _test_mode:
		_build_test_entities()


func _on_role_filter_btn(value: String) -> void:
	_test_filter_role = value
	if _test_mode:
		_build_test_entities()


func _on_tier_filter_btn(value: String) -> void:
	_test_filter_tier = value
	if _test_mode:
		_build_test_entities()


func _on_preview_mode_btn(value: String) -> void:
	_test_preview_mode = value
	if _test_mode:
		_build_test_entities()


func _add_filter_item(option: OptionButton, label: String, value: String) -> void:
	option.add_item(label)
	option.set_item_metadata(option.item_count - 1, value)


func _on_test_batch_filter_selected(index: int) -> void:
	if _test_batch_filter == null:
		return
	_test_filter_batch = str(_test_batch_filter.get_item_metadata(index))
	if _test_mode:
		_build_test_entities()
# ─── Bridge between old _selected and new SelectionManager ──
var _selected: Dictionary = {}

func _sync_selected_from_manager() -> void:
	if _selection:
		_selected = _selection.selection.duplicate()

func _on_selection_changed(selection: Dictionary) -> void:
	_sync_selected_from_manager()
	if _ability_mgr:
		_ability_mgr.on_selection_changed(selection)
	# Update camera follow entities
	if _cam_ctrl:
		_cam_ctrl.set_follow_entities(_selection.get_selected_ids() if _selection else [])
	# Update rally point indicators visibility
	_update_rally_indicator_visibility()
	# Forward selection to HUD so it can show train/upgrade/research panels
	if _hud and selection.size() > 0:
		var primary_id: String = ""
		if _selection and _selection.has_method("get_highest_selected_id"):
			primary_id = _selection.highest_selected_id
		elif not selection.is_empty():
			primary_id = str(selection.keys()[0])
		var data := _get_entity_data(primary_id)
		if not data.is_empty():
			_hud.selected_count = selection.size()
			_hud.selected_type = str(data.get("type", data.get("entity_type", "")))
			_hud.selected_building_type = str(data.get("building_type", ""))
			_hud.selected_hp = float(data.get("health", 0.0))
			_hud.selected_max_hp = float(data.get("max_health", 0.0))
			_hud.selected_energy = float(data.get("energy", 0.0))
			_hud.selected_max_energy = float(data.get("max_energy", 0.0))
			_hud._selected_entity_id = primary_id
	elif _hud:
		_hud.selected_count = 0
		_hud.selected_type = ""
		_hud.selected_building_type = ""

func _on_camera_focus_requested(center: Vector2) -> void:
	if _cam_ctrl:
		_cam_ctrl.move_to_world_position(center)

# ─── Sprint 4: HUD Signal Handlers ──────────────────────────
func _on_hud_ability_clicked(ability_id: StringName) -> void:
	if _ability_mgr:
		var sel := _selected.duplicate()
		var mpos := _screen_to_world(get_viewport().get_mouse_position())
		_ability_mgr.process_ability_input(
			InputEventKey.new(), sel, mpos
		)

func _on_hud_build_clicked(building_type: String) -> void:
	_build_mode = true
	_build_type = building_type
	print("[Build] Selected: %s → right-click to place" % building_type)

func _on_hud_train_clicked(unit_type: String) -> void:
	_handle_train(unit_type)

func _on_hud_merge_clicked(unit_type: String) -> void:
	_handle_merge(unit_type)

func _on_hud_upgrade_clicked(upgrade_key: String, building_id: String) -> void:
	# Zerg building morph: morph_base (Hatchery→Lair), morph_base2 (Lair→Hive)
	# Other races: standard building upgrade
	if upgrade_key == "morph_base" or upgrade_key == "morph_base2":
		_bridge.submit_commands([{
			"action": "morph_building",
			"building_id": building_id,
			"morph_target": upgrade_key,
			"issuer": 1,
		}])
	else:
		_bridge.submit_commands([{
			"action": "upgrade",
			"building_id": building_id,
			"upgrade_name": upgrade_key,
			"issuer": 1,
		}])
	print("[HUD] Upgrade clicked: %s on building %s" % [upgrade_key, building_id])
	_record_apm_action()

func _on_hud_research_clicked(tech_name: String, building_id: String) -> void:
	_bridge.submit_commands([{
		"action": "research",
		"building_id": building_id,
		"tech_name": tech_name,
		"issuer": 1,
	}])
	print("[HUD] Research clicked: %s on building %s" % [tech_name, building_id])
	_record_apm_action()

# ───────────────────────────────────────────────────────────
func _process(delta: float) -> void:
	_frame += 1
	_game_time += delta

	# ── APM tracking: prune actions older than 60s, recompute every 1s ──
	_apm_timer += delta
	if _apm_timer >= 1.0:
		_apm_timer -= 1.0
		var cutoff: float = _game_time - 60.0
		_apm_action_times = _apm_action_times.filter(func(t): return t > cutoff)
		_apm_value = _apm_action_times.size()
		if _apm_label:
			_apm_label.text = "APM: %d" % _apm_value

	# Advance animation frame for test mode
	if _test_mode:
		_anim_tick += delta
		if _anim_tick >= 1.0 / ANIM_FPS:
			_anim_tick -= 1.0 / ANIM_FPS
			_anim_frame = (_anim_frame + 1) % 17
			for e in _test_ents:
				if str(e.get("preview_action", "")) == "attack":
					_attack_flash_timers[str(e.get("id", ""))] = ATTACK_FLASH_DURATION
			_update_entity_sprites()
	# CameraController handles all camera movement now

	# Decay damage floaters
	for f in _dmg_floats:
		f.ttl -= 1
		f.y -= 0.5
	_dmg_floats = _dmg_floats.filter(func(f): return f.ttl > 0)

	# Decay attack flash timers
	var flash_ids: Array = _attack_flash_timers.keys()
	for eid in flash_ids:
		var remaining: float = float(_attack_flash_timers[eid]) - delta
		if remaining <= 0.0:
			_attack_flash_timers.erase(eid)
		else:
			_attack_flash_timers[eid] = remaining

	# Age and prune death explosion effects
	for effect in _dead_effects:
		effect["age"] = float(effect.get("age", 0.0)) + delta
	_dead_effects = _dead_effects.filter(func(eff): return float(eff.get("age", 0.0)) < float(eff.get("lifetime", DEATH_EFFECT_DURATION)))

	# Age and prune command pings
	for ping in _command_pings:
		ping["age"] = float(ping.get("age", 0.0)) + delta
	_command_pings = _command_pings.filter(func(p): return float(p.get("age", 0.0)) < float(p.get("duration", 0.32)))

	# Age and prune control group hints
	for hint in _control_group_hints:
		hint["age"] = float(hint.get("age", 0.0)) + delta
	_control_group_hints = _control_group_hints.filter(func(h): return float(h.get("age", 0.0)) < float(h.get("duration", 0.5)))

	# Hover detection (throttled)
	_hover_check_timer -= delta
	if _hover_check_timer <= 0.0:
		_hover_check_timer = HOVER_CHECK_INTERVAL
		var mouse_world: Vector2 = _screen_to_world(get_viewport().get_mouse_position())
		var hovered_ent: Dictionary = _ent_at_world_pos(mouse_world, SELECT_RADIUS)
		_hovered_entity_id = "" if hovered_ent.is_empty() else str(hovered_ent.get("id", ""))

	# Tick minimap attack indicators and redraw minimap
	if _mm_rect_node and _mm_rect_node.has_method("tick_attack_indicators"):
		_mm_rect_node.tick_attack_indicators()
		_mm_rect_node.queue_redraw()

	queue_redraw()

# ─── Camera helpers (delegated to CameraController) ────────
func _screen_to_world(sp: Vector2) -> Vector2:
	# Convert screen position to world (local) position.
	# get_canvas_transform() maps local coords → viewport coords.
	# Its inverse maps viewport → local (= world with TILE_SIZE=1).
	# Use affine_inverse for numerical stability.
	return get_canvas_transform().affine_inverse() * sp

func _world_to_screen(wp: Vector2) -> Vector2:
	return get_canvas_transform() * wp

# ─── Entity helpers ────────────────────────────────────────
func _ent_at_world_pos(wp: Vector2, radius: float = SELECT_RADIUS) -> Dictionary:
	for e in _ents:
		if wp.distance_to(Vector2(e.px, e.py)) < radius:
			return e
	return {}

func _ents_in_world_rect(rect: Rect2) -> Array:
	var result: Array = []
	for e in _ents:
		if rect.has_point(Vector2(e.px, e.py)):
			result.append(e)
	return result

func _is_own_combat(e: Dictionary) -> bool:
	return e.owner == 1 and e.type in ["worker", "soldier", "scout"]

func _is_own_building(e: Dictionary) -> bool:
	return e.owner == 1 and e.type == "building"

func _has_refinery_on_geyser(geyser_id: String) -> bool:
	"""Check if there's a refinery built on or near this gas geyser."""
	var geyser := _get_ent_by_id(geyser_id)
	if geyser.is_empty():
		return false
	var gx: float = geyser.px
	var gy: float = geyser.py
	for e in _ents:
		if e.type == "building" and e.owner == 1:
			var bt: String = str(e.get("building_type", ""))
			if bt == "refinery" or bt == "Refinery" or bt == "Extractor" or bt == "Assimilator":
				var d: float = Vector2(gx, gy).distance_to(Vector2(e.px, e.py))
				if d < 5.0:
					return true
	return false

func _find_nearest_enemy(from_px: float, from_py: float) -> Dictionary:
	var best: Dictionary = {}
	var best_dist: float = 999999.0
	for e in _ents:
		if e.owner == 2 and e.type != "resource":
			var d: float = Vector2(from_px, from_py).distance_to(Vector2(e.px, e.py))
			if d < best_dist:
				best_dist = d
				best = e
	return best

# ─── Input ─────────────────────────────────────────────────
func _input(event: InputEvent) -> void:
	# Right-click: context action
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		if not _replay_mode and not _game_over_shown:
			_handle_right_click()
		return

	# Left-click: check minimap first, then selection
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var mpos := get_viewport().get_mouse_position()
		# Don't handle if clicking on HUD
		if _hud and _hud.get_global_rect().has_point(mpos):
			return
		if _is_minimap_click(mpos):
			_handle_minimap_click(mpos)
			return
		_dragging = true
		_drag_start = mpos
		_drag_end = mpos
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and not event.pressed:
		if _dragging:
			_dragging = false
			if _drag_start.distance_to(_drag_end) < 5.0:
				_handle_single_click()
			else:
				_handle_drag_select()
		return

	if event is InputEventMouseMotion and _dragging:
		_drag_end = get_viewport().get_mouse_position()

	# Control group hotkeys (1-9)
	if event is InputEventKey and event.pressed:
		var key: int = event.keycode
		if key >= KEY_1 and key <= KEY_9:
			var group_idx: int = key - KEY_1 + 1
			if _selection:
				if event.ctrl_pressed:
					_selection.create_hotkey_group(group_idx)
					_control_group_hints.append({"text": "Ctrl+%d → Group %d" % [group_idx, group_idx], "age": 0.0, "duration": _assign_flash_duration})
				elif event.shift_pressed:
					_selection.add_to_hotkey_group(group_idx)
					_control_group_hints.append({"text": "Shift+%d → Added to Group %d" % [group_idx, group_idx], "age": 0.0, "duration": _assign_flash_duration})
				else:
					# Double-tap detection: same key within 0.3s → jump camera
					var now: float = Time.get_ticks_msec() / 1000.0
					if _last_group_key == key and (now - _last_group_time) < 0.3:
						_selection.jump_to_hotkey_group(group_idx)
						_last_group_key = -1
						_last_group_time = 0.0
					else:
						_selection.select_hotkey_group(group_idx)
						var recalled_ids: Array = _selection.get_selected_ids() if _selection else []
						if recalled_ids.is_empty():
							_control_group_hints.append({"text": "Group %d (empty)" % group_idx, "age": 0.0, "duration": _empty_group_hint_duration})
						_last_group_key = key
						_last_group_time = now
			return

	# Ability hotkeys (if AbilityManager is loaded)
	if event is InputEventKey and event.pressed:
		if _ability_mgr:
			var consumed: bool = _ability_mgr.process_ability_input(event, _selected, _screen_to_world(get_viewport().get_mouse_position()))
			print("[GameView._input] KEY=%d ability_mgr consumed=%s selected=%d" % [event.keycode, str(consumed), _selected.size()])
			if consumed:
				return

	# Legacy keyboard shortcuts
	if event is InputEventKey and event.pressed:
		print("[GameView._input] KEY=%d → legacy handler" % event.keycode)
		if event.keycode == KEY_B:
			if _hud:
				print("[GameView] KEY_B pressed, build_panel_visible=%s" % str(_hud.is_build_panel_visible()))
				if _hud.is_build_panel_visible():
					_hud.hide_build_panel()
					_build_mode = false
					_build_type = ""
				else:
					_hud.show_build_panel()
					_build_mode = true
			else:
				push_warning("[GameView] KEY_B pressed but _hud is null!")
		elif event.keycode == KEY_T:
			# Determine unit_type based on selected building and player race
			var train_type := "worker"  # default for base
			var sel_ids: Array = []
			if _selection:
				sel_ids = _selection.get_selected_ids()
			else:
				sel_ids = _selected.keys()
			for uid in sel_ids:
				var e = _get_ent_by_id(uid)
				if e.is_empty(): continue
				if e.type == "building" and e.owner == 1:
					var btype = e.get("building_type", "base")
					var race_id: String = _player_races.get("1", "1")
					match btype:
						"barracks":
							match race_id:
								"1": train_type = "Marine"
								"2": train_type = "Zergling"
								"3": train_type = "Zealot"
								_: train_type = "Marine"
						"factory":
							match race_id:
								"1": train_type = "Vulture"
								"2": train_type = "Hydralisk"
								"3": train_type = "Dragoon"
								_: train_type = "Vulture"
						"starport":
							match race_id:
								"1": train_type = "Wraith"
								"2": train_type = "Mutalisk"
								"3": train_type = "Scout_ship"
								_: train_type = "Wraith"
						_:
							match race_id:
								"1": train_type = "SCV"
								"2": train_type = "Drone"
								"3": train_type = "Probe"
								_: train_type = "worker"
					break  # use first selected building
			_handle_train(train_type)
		elif event.keycode == KEY_ESCAPE:
			if _selection:
				_selection.remove_all_selection()
			else:
				_selected.clear()
			if _hud:
				_hud.hide_build_panel()
			_build_mode = false
			_build_type = ""

func _unhandled_input(event: InputEvent) -> void:
	if _game_over_shown and event is InputEventKey and event.pressed:
		if event.keycode == KEY_ESCAPE:
			_on_victory_back_to_menu()
	if _replay_mode and event is InputEventKey and event.pressed:
		if event.keycode == KEY_Q:
			get_tree().change_scene_to_file("res://scenes/main_menu.tscn")
		elif event.keycode == KEY_SPACE:
			if _replay_player._play_state == ReplayPlayer.PlayState.PLAYING:
				_replay_player.pause()
			else:
				_replay_player.play()
		elif event.keycode == KEY_LEFT:
			_replay_player.step_backward()
		elif event.keycode == KEY_RIGHT:
			_replay_player.step_forward()
		elif event.keycode == KEY_UP:
			# Speed up
			var speeds := [0.5, 1.0, 2.0, 4.0, 8.0]
			var cur_idx := 0
			for i in range(speeds.size()):
				if absf(_replay_player._playback_speed - speeds[i]) < 0.01:
					cur_idx = i
					break
			var new_idx := mini(cur_idx + 1, speeds.size() - 1)
			_replay_player.set_speed(speeds[new_idx])
			print("[Replay] Speed: %gx" % speeds[new_idx])
		elif event.keycode == KEY_DOWN:
			# Slow down
			var speeds := [0.5, 1.0, 2.0, 4.0, 8.0]
			var cur_idx := 0
			for i in range(speeds.size()):
				if absf(_replay_player._playback_speed - speeds[i]) < 0.01:
					cur_idx = i
					break
			var new_idx := maxi(cur_idx - 1, 0)
			_replay_player.set_speed(speeds[new_idx])
			print("[Replay] Speed: %gx" % speeds[new_idx])

func _handle_right_click() -> void:
	var selected_ids: Array = []
	if _selection:
		selected_ids = _selection.get_selected_ids()
	else:
		selected_ids = _selected.keys()

	if selected_ids.is_empty():
		return

	var screen_pos := get_viewport().get_mouse_position()
	var world_pos := _screen_to_world(screen_pos)
	# Diagnostic: compare manual calc vs transform
	var vp_half := get_viewport().get_visible_rect().size / 2.0
	var manual := (screen_pos - vp_half) / _camera.zoom + _camera.position
	var xform := get_canvas_transform().affine_inverse() * screen_pos
	print("[RIGHT-CLICK] screen=(%d,%d) manual=(%.2f,%.2f) xform=(%.2f,%.2f) cam=(%.2f,%.2f) zoom=%.1f" % [
		int(screen_pos.x), int(screen_pos.y),
		manual.x, manual.y, xform.x, xform.y,
		_camera.position.x, _camera.position.y, _camera.zoom.x])
	var tgt_world := world_pos  # TILE_SIZE=1, world coords ARE tile coords
	var clicked_ent := _ent_at_world_pos(world_pos, SELECT_RADIUS * 3.0)
	var cmds: Array = []

	# Determine action type
	var action := "move"
	var workers_selected := false
	var buildings_selected := false
	var combat_selected := false

	for uid in selected_ids:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue
		if e.type == "worker":
			workers_selected = true
			combat_selected = true
		elif e.type in ["soldier", "scout"]:
			combat_selected = true
		elif e.type == "building":
			buildings_selected = true

	# ─── Sprint 4: Rally point for buildings ───
	if buildings_selected and not workers_selected and not combat_selected:
		for uid in selected_ids:
			var e = _get_ent_by_id(uid)
			if e.is_empty():
				continue
			if e.type == "building" and e.owner == 1:
				_set_rally_point(uid, world_pos)
				_spawn_command_ping(world_pos, "move")
				return

	# Smart context
	if not clicked_ent.is_empty():
		if clicked_ent.owner != 1 and clicked_ent.owner != 0 and clicked_ent.type != "resource":
			action = "attack"
			_spawn_command_ping(Vector2(clicked_ent.px, clicked_ent.py), "attack")
		elif clicked_ent.type == "resource" and workers_selected:
			# Gas geyser without refinery → auto-build refinery on it
			if clicked_ent.resource_type == "gas" and not _has_refinery_on_geyser(clicked_ent.id):
				action = "build"
				_build_type = "refinery"
				_build_mode = true
			else:
				action = "gather"
				_spawn_command_ping(Vector2(clicked_ent.px, clicked_ent.py), "move")
		elif clicked_ent.type == "building" and clicked_ent.owner == 1 and workers_selected:
			action = "move"
	elif combat_selected and not workers_selected:
		action = "attack_nearest"

	if _build_mode and workers_selected:
		action = "build"

	# Generate commands per selected unit (with formation for moves)
	var moving_ids: Array = []
	for uid in selected_ids:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue

		match action:
			"attack":
				if _is_own_combat(e):
					cmds.append({
						"action": "attack",
						"attacker_id": uid,
						"target_id": clicked_ent.id,
						"issuer": 1,
					})
				if _vfx_manager:
					_vfx_manager.spawn_attack(_visual_unit_name(e), e.owner, Vector2(e.px, e.py), Vector2(clicked_ent.px, clicked_ent.py), _vfx_profile_for(e))
					_emit_attack_indicator(Vector2(e.px, e.py))
			"attack_nearest":
				if _is_own_combat(e):
					var nearest_enemy = _find_nearest_enemy(e.px, e.py)
					if not nearest_enemy.is_empty():
						_spawn_command_ping(Vector2(nearest_enemy.px, nearest_enemy.py), "attack")
						cmds.append({
							"action": "attack",
							"attacker_id": uid,
							"target_id": nearest_enemy.id,
							"issuer": 1,
						})
						if _vfx_manager:
						_vfx_manager.spawn_attack(_visual_unit_name(e), e.owner, Vector2(e.px, e.py), Vector2(nearest_enemy.px, nearest_enemy.py), _vfx_profile_for(e))
						_emit_attack_indicator(Vector2(e.px, e.py))
					else:
						moving_ids.append(uid)
			"gather":
				if e.type == "worker":
					cmds.append({
						"action": "gather",
						"worker_id": uid,
						"resource_id": clicked_ent.id,
						"issuer": 1,
					})
			"build":
				if e.type == "worker":
					# If building a refinery, snap position to the gas geyser
					var build_x := tgt_world.x
					var build_y := tgt_world.y
					if _build_type == "refinery" and not clicked_ent.is_empty() and clicked_ent.resource_type == "gas":
						build_x = clicked_ent.px
						build_y = clicked_ent.py
					_spawn_command_ping(Vector2(build_x, build_y), "move")
					cmds.append({
						"action": "build",
						"builder_id": uid,
						"building_type": _build_type if _build_type != "" else "barracks",
						"pos_x": build_x,
						"pos_y": build_y,
						"issuer": 1,
					})
			"move":
				if e.type in ["worker", "soldier", "scout"]:
					moving_ids.append(uid)

	# Formation-based move commands
	if not moving_ids.is_empty():
		_spawn_command_ping(world_pos, "move")
		var formation: Array = _selection.calculate_formation_positions(world_pos, moving_ids.size()) if _selection \
			else _calc_formation_fallback(world_pos, moving_ids.size())
		for i in range(moving_ids.size()):
			var fpos: Vector2 = formation[i] if i < formation.size() else world_pos
			var ftgt := fpos  # TILE_SIZE=1, world coords ARE tile coords
			cmds.append({
				"action": "move",
				"unit_id": moving_ids[i],
				"target_x": ftgt.x,
				"target_y": ftgt.y,
				"issuer": 1,
			})

	if cmds.size() > 0:
		_bridge.submit_commands(cmds)
		_record_apm_action()

	# Also emit via EventBus
	if _event_bus and cmds.size() > 0:
		for cmd in cmds:
			_event_bus.emit_command_issued(cmd)

	# Invalid command feedback — selected units but no valid action
	if cmds.is_empty() and not selected_ids.is_empty():
		_spawn_command_ping(world_pos, "invalid")

	# Hide build panel after placing
	if _build_mode and _hud:
		_hud.hide_build_panel()
	_build_mode = false
	_build_type = ""

func _handle_single_click() -> void:
	var wp := _screen_to_world(_drag_start)
	var clicked_ent := _ent_at_world_pos(wp)

	if _selection:
		if clicked_ent.is_empty():
			if not Input.is_key_pressed(KEY_SHIFT):
				_selection.remove_all_selection()
			return
		if not Input.is_key_pressed(KEY_SHIFT):
			_selection.remove_all_selection()
		# Sprint 4: Double-click detection
		var was_double: bool = _selection.handle_click_with_double_select(clicked_ent.id)
		if not was_double:
			# Ctrl+click = select all same type on screen
			if Input.is_key_pressed(KEY_CTRL):
				_selection.select_all_similar_on_screen(clicked_ent.id)
			else:
				_selection.add_to_selection_bulk([clicked_ent.id])
		_record_apm_action()
	else:
		# Fallback without SelectionManager
		if clicked_ent.is_empty():
			if not Input.is_key_pressed(KEY_SHIFT):
				_selected.clear()
			return
		if not Input.is_key_pressed(KEY_SHIFT):
			_selected.clear()
		_selected[clicked_ent.id] = true
		_record_apm_action()

func _handle_drag_select() -> void:
	var tl := _screen_to_world(Vector2(minf(_drag_start.x, _drag_end.x), minf(_drag_start.y, _drag_end.y)))
	var br := _screen_to_world(Vector2(maxf(_drag_start.x, _drag_end.x), maxf(_drag_start.y, _drag_end.y)))
	var rect := Rect2(tl, br - tl)

	var selected_ents := _ents_in_world_rect(rect)
	var own_ids: Array = []
	for e in selected_ents:
		if e.owner == 1:
			own_ids.append(e.id)

	if _selection:
		if not Input.is_key_pressed(KEY_SHIFT):
			_selection.remove_all_selection()
		_selection.add_to_selection_bulk(own_ids)
	else:
		if not Input.is_key_pressed(KEY_SHIFT):
			_selected.clear()
		for e in selected_ents:
			if e.owner == 1:
				_selected[e.id] = true

	if own_ids.size() > 0:
		_record_apm_action()

	# Update selectables_on_screen for SelectionManager
	if _selection:
		var screen_ids: Dictionary = {}
		for e in _ents:
			screen_ids[e.id] = true
		_selection.selectables_on_screen = screen_ids

func _handle_train(unit_type: String = "worker") -> void:
	var cmds: Array = []
	var selected_ids: Array = []
	if _selection:
		selected_ids = _selection.get_selected_ids()
	else:
		selected_ids = _selected.keys()

	for uid in selected_ids:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue
		if e.type == "building" and e.owner == 1:
			cmds.append({
				"action": "train",
				"building_id": uid,
				"unit_type": unit_type,
				"issuer": 1,
			})
	if cmds.size() > 0:
		_bridge.submit_commands(cmds)
		_record_apm_action()

func _handle_merge(unit_type: String) -> void:
	## Collect entity_ids for 2 same-type Templar from the current selection,
	## then send a merge command to SimCore.
	var selected_ids: Array = []
	if _selection:
		selected_ids = _selection.get_selected_ids()
	else:
		selected_ids = _selected.keys()

	# Determine which source unit types can merge into the target
	var source_types: Array = []
	if unit_type == "Archon":
		source_types = ["Templar", "HighTemplar"]
	elif unit_type == "DarkArchon":
		source_types = ["DarkTemplar"]
	else:
		return  # unknown merge target

	# Find up to 2 matching entities in the selection
	var merge_ids: Array = []
	for uid in selected_ids:
		var e = _get_ent_by_id(uid)
		if e.is_empty():
			continue
		var utype: String = str(e.get("unit_type", e.get("entity_type", "")))
		if utype in source_types:
			merge_ids.append(uid)
			if merge_ids.size() >= 2:
				break

	if merge_ids.size() < 2:
		push_warning("[Merge] Need 2 same-type Templar, only found %d" % merge_ids.size())
		return

	var cmds: Array = [{
		"action": "merge",
		"entity_ids": merge_ids,
		"unit_type": unit_type,
		"issuer": 1,
	}]
	_bridge.submit_commands(cmds)
	if _event_bus:
		for cmd in cmds:
			_event_bus.emit_command_issued(cmd)

func _get_ent_by_id(eid: String) -> Dictionary:
	for e in _ents:
		if e.id == eid:
			return e
	return {}

func _visual_unit_name(e: Dictionary) -> String:
	var entity_type := str(e.get("type", e.get("entity_type", "")))
	if entity_type == "building":
		return "building"
	return _resolve_visual_id(e)


func _vfx_profile_for(e: Dictionary) -> String:
	"""Look up vfx_profile from presentation manifest for a given entity."""
	var visual_id := _visual_unit_name(e)
	var is_building := str(e.get("type", e.get("entity_type", ""))) == "building"
	var section_name := "building_visuals" if is_building else "unit_visuals"
	var section: Dictionary = _presentation_manifest.get(section_name, {})
	var entry: Dictionary = section.get(visual_id, {})
	if entry.has("vfx_profile"):
		return str(entry["vfx_profile"])
	return ""

# ─── Sprint 4: Rally Point System ──────────────────────────
func _set_rally_point(building_id: String, world_pos: Vector2) -> void:
	if not _rally_indicators.has(building_id):
		var indicator = RallyPointIndicatorScript.new()
		add_child(indicator)
		_rally_indicators[building_id] = indicator
		var e = _get_ent_by_id(building_id)
		if not e.is_empty():
			indicator.set_building_position(Vector2(e.px, e.py))
	var indicator = _rally_indicators[building_id]
	indicator.set_rally_point(world_pos)
	indicator.show_indicator()

	# Submit rally point command to SimCore
	var tgt_world := world_pos  # TILE_SIZE=1, world coords ARE tile coords
	var cmds: Array = [{
		"action": "set_rally",
		"building_id": building_id,
		"target_x": tgt_world.x,
		"target_y": tgt_world.y,
		"issuer": 1,
	}]
	_bridge.submit_commands(cmds)
	if _event_bus:
		_event_bus.emit_rally_point_set(building_id, world_pos)

func _clear_rally_point(building_id: String) -> void:
	if _rally_indicators.has(building_id):
		var indicator = _rally_indicators[building_id]
		indicator.clear_rally_point()
		indicator.hide_indicator()
	if _event_bus:
		_event_bus.emit_rally_point_cleared(building_id)

func _update_rally_indicator_visibility() -> void:
	# Show rally indicators only for selected buildings
	for bid in _rally_indicators:
		var indicator = _rally_indicators[bid]
		if _selection and _selection.is_selected(bid):
			indicator.show_indicator()
		else:
			indicator.hide_indicator()
		# Update building position from current entity data
		var e = _get_ent_by_id(bid)
		if not e.is_empty():
			indicator.set_building_position(Vector2(e.px, e.py))

# ─── Sprint 4: Attack Indicators on Minimap ─────────────────
func _emit_attack_indicator(world_pos: Vector2) -> void:
	if _mm_rect_node and _mm_rect_node.has_method("add_attack_indicator"):
		_mm_rect_node.add_attack_indicator(world_pos)
	if _event_bus:
		_event_bus.emit_attack_occurred(world_pos, 1)

# ─── Feel config loading ──────────────────────────────────
func _load_feel_config() -> Dictionary:
	var path: String = "res://resources/feel/control_feel_config.json"
	if not ResourceLoader.exists(path):
		push_warning("control_feel_config.json not found — using defaults")
		return {}
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("Failed to open control_feel_config.json")
		return {}
	var text: String = f.get_as_text()
	f.close()
	var json: JSON = JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		push_warning("JSON parse error in control_feel_config.json: " + json.get_error_message())
		return {}
	return json.data

# ─── Command ping spawning ────────────────────────────────
func _spawn_command_ping(world_pos: Vector2, ping_type: String) -> void:
	var duration: float = _ground_ping_duration
	var color: Color = _ground_ping_color
	match ping_type:
		"attack":
			duration = _attack_ping_duration
			color = _attack_ping_color
		"invalid":
			duration = _invalid_ping_duration
			color = _invalid_ping_color
	_command_pings.append({
		"pos": world_pos,
		"age": 0.0,
		"duration": duration,
		"color": color,
		"type": ping_type,
	})

# ─── Formation Fallback ────────────────────────────────────
static func _calc_formation_fallback(center: Vector2, count: int, spacing: float = 0.8) -> Array:
	var positions: Array = []
	if count == 0:
		return positions
	var cols: int = int(ceilf(sqrt(float(count))))
	for i in range(count):
		var row: int = i / cols
		var col: int = i % cols
		var offset := Vector2(
			(float(col) - float(cols - 1) * 0.5) * spacing,
			(float(row) - float(count / cols - 1) * 0.5) * spacing
		)
		positions.append(center + offset)
	return positions

# ─── Bridge callbacks ──────────────────────────────────────
func _on_start(state: Dictionary) -> void:
	_apply_start_state(state)


func _on_state(state: Dictionary) -> void:
	if _test_mode:
		return
	# Also apply start state on first tick if _on_start was missed
	if _player_races.is_empty() and state.has("player_races"):
		_apply_start_state(state)
	_parse(state)


func _apply_start_state(state: Dictionary) -> void:
	_map_w = _to_f(state.get("map_width"), 64.0)
	_map_h = _to_f(state.get("map_height"), 64.0)
	if _map_w <= 0.0:
		_map_w = 64.0
	if _map_h <= 0.0:
		_map_h = 64.0
	# Store player races for race-aware visual lookup
	# Convert race names → IDs (1=Terran, 2=Zerg, 3=Protoss) for manifest lookups
	var _RACE_NAME_TO_ID: Dictionary = {"terran": "1", "zerg": "2", "protoss": "3"}
	var pr = state.get("player_races", {})
	if pr is Dictionary:
		for pid in pr.keys():
			var rname: String = str(pr[pid]).to_lower()
			_player_races[str(pid)] = _RACE_NAME_TO_ID.get(rname, "1")
	# Propagate P1 race to HUD so build/train menus filter correctly
	var p1_race: String = "1"
	if _player_races.has("1"):
		p1_race = str(_player_races["1"])
	if _hud and _hud.has_method("set_player_race"):
		_hud.set_player_race(p1_race)
	print("[GameView] _apply_start_state: map=%0.0fx%0.0f player_races=%s" % [_map_w, _map_h, str(_player_races)])
	# Phase D: parse height_map (sent once at game start)
	var hm = state.get("height_map", [])
	if hm.size() > 0:
		_height_map = hm
		_height_map_w = _map_w
		_height_map_h = _map_h
		_elevation_dirty = true
	if _cam_ctrl:
		_cam_ctrl.set_map_size(_map_w, _map_h)
	_parse(state)


func _on_game_over(winner: int, tick: int) -> void:
	_game_active = false
	_game_over_shown = true

	# Compute end-of-game stats
	var duration_sec: float = tick / 20.0
	var kills_val: int = 0
	var losses_val: int = 0
	var mineral_gathered: int = 0
	var gas_gathered: int = 0
	# Count kills/losses from entity changes
	for old_id in _prev_entities:
		var old_e: Dictionary = _prev_entities[old_id]
		if old_e.get("owner", 0) == 2 and float(old_e.get("health", 0)) > 0:
			kills_val += 1  # enemy entity disappeared = we killed it
		if old_e.get("owner", 0) == 1 and float(old_e.get("health", 0)) > 0:
			losses_val += 1  # own entity disappeared = we lost it

	var stats := {
		"tick": tick,
		"kills": kills_val,
		"losses": losses_val,
		"mineral_gathered": mineral_gathered,
		"gas_gathered": gas_gathered,
		"apm": _apm_value,
		"total_actions": _total_actions,
	}

	if _victory_screen:
		_victory_screen.show_result(winner, 1, stats)

	print("===== GAME OVER: P%d wins at tick %d (APM=%d)" % [winner, tick, _apm_value])

func _restart_game() -> void:
	_game_over_shown = false
	_game_active = true
	if _victory_screen:
		_victory_screen.visible = false
	if _selection:
		_selection.remove_all_selection()
	else:
		_selected.clear()
	_bridge._pending_commands.clear()
	_ents.clear()
	_entity_cache_by_id.clear()
	_prev_hp.clear()
	_prev_entities.clear()
	_prev_attack_targets.clear()
	_attack_flash_timers.clear()
	_dead_effects.clear()
	if _vfx_manager:
		_vfx_manager.clear()
	# Clear rally indicators
	for bid in _rally_indicators:
		_rally_indicators[bid].queue_free()
	_rally_indicators.clear()
	var new_seed := randi() % 100000
	_bridge.start_game(new_seed)

# ─── Victory Screen Callbacks ───────────────────────────────
func _on_victory_play_again() -> void:
	_restart_game()

func _on_victory_back_to_menu() -> void:
	get_tree().change_scene_to_file("res://scenes/main_menu.tscn")

func _on_victory_watch_replay() -> void:
	_request_latest_replay()

func _to_f(value, fallback: float = 0.0) -> float:
	if value == null:
		return fallback
	return value + 0.0

## Record an effective player action for APM tracking (selection + commands).
func _record_apm_action() -> void:
	if not _game_active or _game_over_shown:
		return
	_apm_action_times.append(_game_time)
	_total_actions += 1

func _load_presentation_manifest() -> void:
	if not FileAccess.file_exists(PRESENTATION_MANIFEST_PATH):
		push_warning("[GameView] Missing presentation manifest: %s" % PRESENTATION_MANIFEST_PATH)
		_presentation_manifest = {}
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(PRESENTATION_MANIFEST_PATH))
	if parsed is Dictionary:
		_presentation_manifest = parsed
	else:
		push_warning("[GameView] Invalid presentation manifest: %s" % PRESENTATION_MANIFEST_PATH)
		_presentation_manifest = {}


func _load_unit_type_catalog() -> void:
	if not FileAccess.file_exists(UNIT_TYPE_CATALOG_PATH):
		push_warning("[GameView] Missing unit type catalog: %s — falling back to unfiltered test mode" % UNIT_TYPE_CATALOG_PATH)
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
			print("[GameView] Unit type catalog loaded: %d entries" % _unit_type_catalog.size())
		else:
			push_warning("[GameView] Unit type catalog was empty after stripping _meta")
			_unit_type_catalog = {}
	else:
		push_warning("[GameView] Invalid unit type catalog: %s" % UNIT_TYPE_CATALOG_PATH)
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

func _resolve_visual_id(e: Dictionary) -> String:
	var etype := str(e.get("type", e.get("entity_type", "")))
	var owner_key := str(int(e.get("owner", 0)))
	# Map player ID → race ID for manifest lookup
	var race_key: String = str(_player_races.get(owner_key, "1"))  # default "1"=Terran
	if etype == "building":
		var btype := str(e.get("building_type", ""))
		if _is_known_building_visual(btype):
			return btype
		var abstract_buildings: Dictionary = _presentation_manifest.get("abstract_buildings", {})
		var race_buildings: Dictionary = abstract_buildings.get(race_key, {})
		return str(race_buildings.get(btype, btype))

	var unit_type := str(e.get("unit_type", ""))
	if unit_type != "" and unit_type != "unit" and _is_known_unit_visual(unit_type):
		return unit_type
	if unit_type != "" and unit_type != etype and unit_type != "unit":
		return unit_type

	var abstract_units: Dictionary = _presentation_manifest.get("abstract_units", {})
	var race_units: Dictionary = abstract_units.get(race_key, {})
	return str(race_units.get(etype, etype))

func _is_known_unit_visual(visual_id: String) -> bool:
	if visual_id == "":
		return false
	var unit_visuals: Dictionary = _presentation_manifest.get("unit_visuals", {})
	return unit_visuals.has(visual_id) or (_sprite_loader != null and _sprite_loader.is_unit(visual_id))

func _is_known_building_visual(visual_id: String) -> bool:
	if visual_id == "":
		return false
	var building_visuals: Dictionary = _presentation_manifest.get("building_visuals", {})
	return building_visuals.has(visual_id) or (_sprite_loader != null and _sprite_loader.is_building(visual_id))

func _is_building_entity_visual(e: Dictionary, visual_id: String) -> bool:
	return str(e.get("type", e.get("entity_type", ""))) == "building" or _is_known_building_visual(visual_id)

func _visual_scale(visual_id: String, is_building: bool) -> Vector2:
	var fallback := 0.018 if is_building else 0.022
	if _sprite_loader:
		var params := _sprite_loader.get_visual_params(visual_id, is_building)
		var loader_scale := float(params.get("render_scale", fallback))
		return Vector2(loader_scale, loader_scale)
	var section_name := "building_visuals" if is_building else "unit_visuals"
	var section: Dictionary = _presentation_manifest.get(section_name, {})
	var visual: Dictionary = section.get(visual_id, {})
	var scale := float(visual.get("render_scale", fallback))
	return Vector2(scale, scale)

func _visual_radius(e: Dictionary) -> float:
	var visual_id := _resolve_visual_id(e)
	var is_building := _is_building_entity_visual(e, visual_id)
	if _sprite_loader:
		var params := _sprite_loader.get_visual_params(visual_id, is_building)
		return float(params.get("selection_radius", 1.5 if is_building else 0.55))
	var section_name := "building_visuals" if is_building else "unit_visuals"
	var section: Dictionary = _presentation_manifest.get(section_name, {})
	var visual: Dictionary = section.get(visual_id, {})
	var fallback := 1.5 if is_building else 0.55
	var radius := float(visual.get("selection_radius", fallback))
	if is_building:
		return clampf(radius * 0.34, 0.95, 1.65)
	return clampf(radius * 0.78, 0.38, 0.72)

func _unit_animation_key(e: Dictionary, frames: SpriteFrames) -> String:
	var base := "idle"
	if str(e.get("attack_target_id", "")) != "":
		base = "attack"
	elif not bool(e.get("is_idle", true)):
		base = "moving"
	var key := _sprite_loader.get_animation_key(base, 0)
	if frames.has_animation(key):
		return key
	key = _sprite_loader.get_animation_key("idle", 0)
	if frames.has_animation(key):
		return key
	var names := frames.get_animation_names()
	return str(names[0]) if names.size() > 0 else ""

func _parse(state: Dictionary) -> void:
	var old_entities := _prev_entities.duplicate(true)
	_ents.clear()
	_entity_cache_by_id.clear()
	var entities: Dictionary = state.get("entities", {})
	if entities.is_empty():
		print("[GameView] _parse: entities dict is EMPTY")
	else:
		print("[GameView] _parse: entities dict size=%d" % entities.size())
	for eid in entities:
		var e: Dictionary = entities[eid]
		var etype: String = str(e.get("entity_type", ""))
		var utype: String = str(e.get("unit_type", etype))
		var btype: String = str(e.get("building_type", ""))
		var rtype: String = str(e.get("resource_type", ""))
		var ent_dict := {
			"id": str(eid),
			"owner": int(e.get("owner") if e.get("owner") != null else 0),
			"type": etype,
			"entity_type": etype,
			"unit_type": utype,
			"building_type": btype,
			"resource_type": rtype,
			"resource_amount": _to_f(e.get("resource_amount"), 0.0),
			"px": _to_f(e.get("pos_x"), 0.0),  # TILE_SIZE=1, world=tile
			"py": _to_f(e.get("pos_y"), 0.0),
			"pos_x": _to_f(e.get("pos_x"), 0.0),
			"pos_y": _to_f(e.get("pos_y"), 0.0),
			"health": _to_f(e.get("health"), 0.0),
			"max_health": _to_f(e.get("max_health"), 0.0),
			"is_idle": bool(e.get("is_idle", true) if e.get("is_idle") != null else true),
			"carry_amount": _to_f(e.get("carry_amount"), 0.0),
			"carry_cap": _to_f(e.get("carry_capacity"), 0.0),
			"attack": _to_f(e.get("attack"), 0.0),
			"attack_range": _to_f(e.get("attack_range"), 16.0),
			"attack_target_id": str(e.get("attack_target_id", "")),
			"target_x": _to_f(e.get("target_x"), 0.0),
			"target_y": _to_f(e.get("target_y"), 0.0),
			"speed": _to_f(e.get("speed"), 0.0),
			"energy": _to_f(e.get("energy"), 0.0),
			"max_energy": _to_f(e.get("max_energy"), 0.0),
			"production_queue": e.get("production_queue", []),
			"production_timers": e.get("production_timers", []),
			"attack_cooldown": _to_f(e.get("attack_cooldown"), 0.0),
			"is_constructing": bool(e.get("is_constructing", false) if e.get("is_constructing") != null else false),
			"build_progress": _to_f(e.get("build_progress"), 0.0),
		}
		_ents.append(ent_dict)
		_entity_cache_by_id[str(eid)] = ent_dict

	# Parse fog-of-war for P1
	var fog: Dictionary = state.get("fog_of_war", {})
	var p1_fog: Dictionary = fog.get("1", fog)
	_fog_w = int(p1_fog.get("width", 0))
	_fog_h = int(p1_fog.get("height", 0))
	var raw_tiles: Array = p1_fog.get("tiles", [])
	_fog_prev_tiles = _fog_tiles.duplicate()
	_fog_tiles.clear()
	for t in raw_tiles:
		_fog_tiles.append(int(t))
	# Update smooth fog alpha: state=2 → alpha=0 instantly, state=0→alpha target=0.88,
	# state=1 → target=0.50, but only fade toward target (never snap).
	# Tiles that were 2 last tick and are now 1: keep alpha near 0 for FOG_FADE_FRAMES.
	var tile_count := _fog_w * _fog_h
	if _fog_alpha.size() != tile_count:
		_fog_alpha.resize(tile_count)
		for i in range(tile_count):
			var initial: int = _fog_tiles[i] if i < _fog_tiles.size() else 0
			match initial:
				2: _fog_alpha[i] = 0.0
				1: _fog_alpha[i] = 0.50
				_: _fog_alpha[i] = 0.88
	for i in range(tile_count):
		var cur: int = _fog_tiles[i] if i < _fog_tiles.size() else 0
		var prev: int = _fog_prev_tiles[i] if i < _fog_prev_tiles.size() else 0
		var target: float
		match cur:
			0: target = 0.88
			1: target = 0.50
			2: target = 0.0
			_: target = 0.88
		# Current vision should be clear immediately; fade only when leaving vision.
		if cur == 2:
			_fog_alpha[i] = 0.0
		elif prev == 2:
			_fog_alpha[i] = 0.0  # keep fully clear
		else:
			# Smoothly approach target
			var speed := 1.0 / float(FOG_FADE_FRAMES)
			if _fog_alpha[i] < target:
				_fog_alpha[i] = minf(_fog_alpha[i] + (target - _fog_alpha[i]) * speed * 3.0, target)
			elif _fog_alpha[i] > target:
				_fog_alpha[i] = maxf(_fog_alpha[i] - (_fog_alpha[i] - target) * speed * 2.0, target)

	# Parse resources for P1
	var resources: Dictionary = state.get("resources", {})
	var p1_res: Dictionary = resources.get("1", {})
	if p1_res.is_empty() and resources.has("p1_mineral"):
		# Fallback: engine raw format p1_mineral -> normalize
		p1_res = {
			"minerals": resources.get("p1_mineral", 0),
			"gas": resources.get("p1_gas", 0),
			"supply_used": resources.get("p1_supply_used", 0),
			"supply_cap": resources.get("p1_supply_cap", 0),
		}
	_p1_minerals = int(_to_f(p1_res.get("minerals"), 0.0))
	_p1_gas = int(_to_f(p1_res.get("gas"), 0.0))
	_p1_supply_used = int(_to_f(p1_res.get("supply_used"), 0.0))
	_p1_supply_cap = int(_to_f(p1_res.get("supply_cap"), 0.0))

	if _hud:
		_hud.update_resources(_p1_minerals, _p1_gas, _p1_supply_used, _p1_supply_cap)
		var completed: PackedStringArray = []
		for e in _ents:
			if e.type == "building" and e.owner == 1 and e.health > 0:
				var bt: String = str(e.get("building_type", ""))
				if bt != "":
					completed.append(bt)
		_hud.update_completed_buildings(completed)

	_update_entity_sprites()

	for e in _ents:
		var eid_str: String = e.id
		var hp: float = e.health
		if _prev_hp.has(eid_str):
			var prev: float = _prev_hp[eid_str]
			if hp < prev and prev > 0:
				var dmg: float = prev - hp
				_dmg_floats.append({
					"id": eid_str,
					"x": e.px,
					"y": e.py - 1.2,
					"amount": dmg,
					"ttl": 30,
			})
				if _vfx_manager:
					_vfx_manager.spawn_hit(_visual_unit_name(e), e.owner, Vector2(e.px, e.py), dmg, _vfx_profile_for(e))
					_emit_attack_indicator(Vector2(e.px, e.py))

	# ─── Attack flash detection: detect when a unit starts attacking or switches target ───
	for e in _ents:
		var eid_str: String = e.id
		var cur_target: String = str(e.get("attack_target_id", ""))
		var prev_target: String = str(_prev_attack_targets.get(eid_str, ""))
		# Flash when unit begins attacking (empty → non-empty) or switches targets
		if cur_target != "" and cur_target != prev_target:
			_attack_flash_timers[eid_str] = ATTACK_FLASH_DURATION
		# Also flash if attack_cooldown just started (shot just fired)
		var cooldown: float = _to_f(e.get("attack_cooldown"), 0.0)
		var prev_cooldown: float = _to_f(_prev_hp.get(eid_str + "_cd", 0.0), 0.0)
		if cooldown > 0.0 and prev_cooldown <= 0.0 and cur_target != "":
			_attack_flash_timers[eid_str] = ATTACK_FLASH_DURATION

	for old_id in old_entities:
		if not _entity_cache_by_id.has(old_id):
			var old_e: Dictionary = old_entities[old_id]
			if float(old_e.get("health", 0.0)) > 0.0:
				var death_pos := Vector2(float(old_e.get("px", 0.0)), float(old_e.get("py", 0.0)))
				var death_owner: int = int(old_e.get("owner", 0))
				var death_type: String = str(old_e.get("type", old_e.get("entity_type", "")))
				# Spawn VFXManager death effect
				if _vfx_manager:
					_vfx_manager.spawn_death(
						_visual_unit_name(old_e),
						death_type,
						death_owner,
						death_pos,
						_vfx_profile_for(old_e)
					)
				# Also add to local death explosion effects for canvas drawing
				var death_color: Color = _team_color(death_owner)
				_dead_effects.append({
					"pos": death_pos,
					"age": 0.0,
					"lifetime": DEATH_EFFECT_DURATION,
					"color": death_color,
					"owner": death_owner,
					"entity_type": death_type,
				})

	_prev_hp.clear()
	_prev_entities.clear()
	_prev_attack_targets.clear()
	for e in _ents:
		_prev_hp[e.id] = e.health
		_prev_entities[e.id] = e.duplicate(true)
		_prev_attack_targets[e.id] = str(e.get("attack_target_id", ""))

	var valid_ids: Array = []
	for e in _ents:
		valid_ids.append(e.id)
	if _selection:
		_selection.purge_invalid_ids(valid_ids)
		_selection.selectables_on_screen = _entity_cache_by_id.duplicate()

	for bid in _rally_indicators:
		var indicator = _rally_indicators[bid]
		var e = _get_ent_by_id(bid)
		if not e.is_empty():
			indicator.set_building_position(Vector2(e.px, e.py))

# ───────────────────────────────────────────────────────────
# ─── DRAWING ───────────────────────────────────────────────
# ───────────────────────────────────────────────────────────
func _draw() -> void:
	# NO camera offset needed — Camera2D handles canvas transform automatically.
	# _draw() local coordinates ARE world coordinates.
	var co := Vector2.ZERO
	_draw_map_background(co)
	if _show_elevation:
		_draw_elevation(co)
	_draw_grid(co)
	_draw_entities(co)
	_draw_pylon_power_range(co)
	_draw_fog_of_war(co)
	_draw_attack_flashes(co)
	_draw_death_explosions(co)
	_draw_hover_highlight(co)
	_draw_health_bars(co)
	_draw_build_progress_bars(co)
	_draw_production_bars(co)
	_draw_status_icons(co)
	_draw_selection_rings(co)
	_draw_rally_lines(co)
	_draw_drag_box()
	_draw_damage_floats(co)
	_draw_command_pings(co)
	_draw_control_group_hints(co)
	_draw_game_over_overlay()
	if _test_mode:
		_draw_test_labels()

func _draw_map_background(_co: Vector2) -> void:
	# Map fills from world origin (0,0) to (_map_w, _map_h)
	var map_rect := Rect2(Vector2.ZERO, Vector2(_map_w, _map_h))
	if _map_texture:
		draw_texture_rect(_map_texture, map_rect, false)
	else:
		draw_rect(map_rect, Color(0.15, 0.18, 0.12, 1.0))

func _draw_elevation(_co: Vector2) -> void:
	"""Phase D: Render height_map as terrain coloring + contour lines + cliff markers."""
	if _height_map.is_empty():
		return
	var rows := _height_map.size()
	if rows == 0:
		return
	var cols: int = _height_map[0].size()
	# ── Height-based terrain tint (draw small rects per tile) ──
	for y in range(rows):
		var row = _height_map[y]
		for x in range(cols):
			var h: int = row[x] if x < row.size() else 0
			if h == 0:
				continue  # base level keeps default color
			# Gradient: low → dark green, high → bright yellow-green (subtle tint)
			var t := float(h) / 8.0
			var col := Color(0.05 + t * 0.15, 0.15 + t * 0.25, 0.05 + t * 0.03, 0.25)
			draw_rect(Rect2(x, y, 1.0, 1.0), col)
	# ── Contour lines (draw edge where height changes) ──
	var contour_color := Color(0.6, 0.45, 0.2, 0.5)  # brownish
	for y in range(rows):
		var row = _height_map[y]
		for x in range(cols):
			var h: int = row[x] if x < row.size() else 0
			# Right neighbor
			if x + 1 < cols:
				var hr: int = _height_map[y][x + 1] if (x + 1) < _height_map[y].size() else h
				if hr != h:
					draw_line(Vector2(x + 1, y), Vector2(x + 1, y + 1), contour_color, 0.08)
			# Bottom neighbor
			if y + 1 < rows:
				var hb: int = _height_map[y + 1][x] if x < _height_map[y + 1].size() else h
				if hb != h:
					draw_line(Vector2(x, y + 1), Vector2(x + 1, y + 1), contour_color, 0.08)
	# ── Cliff markers (Δh ≥ 3 = red thick line) ──
	var cliff_color := Color(0.9, 0.15, 0.1, 0.7)
	for y in range(rows):
		var row = _height_map[y]
		for x in range(cols):
			var h: int = row[x] if x < row.size() else 0
			# Right cliff
			if x + 1 < cols:
				var hr: int = _height_map[y][x + 1] if (x + 1) < _height_map[y].size() else h
				if abs(hr - h) >= 3:
					draw_line(Vector2(x + 1, y), Vector2(x + 1, y + 1), cliff_color, 0.25)
			# Bottom cliff
			if y + 1 < rows:
				var hb: int = _height_map[y + 1][x] if x < _height_map[y + 1].size() else h
				if abs(hb - h) >= 3:
					draw_line(Vector2(x, y + 1), Vector2(x + 1, y + 1), cliff_color, 0.25)

func _draw_grid(co: Vector2) -> void:
	var grid_color := Color(0.25, 0.28, 0.22, 0.3)
	var step := 8.0  # TILE_SIZE=1, grid every 8 tiles
	var map_px := _map_w
	var map_py := _map_h
	var x := step
	while x < map_px:
		draw_line(Vector2(x, 0), Vector2(x, map_py), grid_color, 0.06)
		x += step
	var y := step
	while y < map_py:
		draw_line(Vector2(0, y), Vector2(map_px, y), grid_color, 0.06)
		y += step

func _draw_fog_of_war(co: Vector2) -> void:
	# Smooth fog: uses _fog_alpha array (updated in _parse) for flicker-free rendering.
	# Boundary gradient smoothing uses alpha values directly for seamless transitions.
	if _fog_w <= 0 or _fog_h <= 0 or _fog_tiles.is_empty():
		return
	var map_px := _map_w  # TILE_SIZE=1
	var map_py := _map_h
	var tile_w := map_px / float(_fog_w)
	var tile_h := map_py / float(_fog_h)
	var tile_count := _fog_w * _fog_h

	# Pre-build alpha grid for neighbor smoothing
	var alpha_grid: Array = []
	alpha_grid.resize(_fog_h)
	for gy in range(_fog_h):
		alpha_grid[gy] = []
		alpha_grid[gy].resize(_fog_w)
		for gx in range(_fog_w):
			var idx := gy * _fog_w + gx
			alpha_grid[gy][gx] = _fog_alpha[idx] if idx < _fog_alpha.size() else 0.88

	for gy in range(_fog_h):
		for gx in range(_fog_w):
			var idx := gy * _fog_w + gx
			var base_alpha: float = _fog_alpha[idx] if idx < _fog_alpha.size() else 0.88

			if base_alpha < 0.01:
				continue

			# Gradient smoothing at boundaries using neighbor alphas
			var is_boundary := false
			var neighbor_sum: float = 0.0
			var neighbor_count: int = 0
			for dy in range(-1, 2):
				for dx in range(-1, 2):
					if dx == 0 and dy == 0:
						continue
					var nx: int = gx + dx
					var ny: int = gy + dy
					var n_alpha: float
					if nx < 0 or nx >= _fog_w or ny < 0 or ny >= _fog_h:
						n_alpha = 0.88
						neighbor_sum += n_alpha
						neighbor_count += 1
						if base_alpha < 0.87:
							is_boundary = true
						continue
					n_alpha = alpha_grid[ny][nx]
					neighbor_sum += n_alpha
					neighbor_count += 1
					if absf(n_alpha - base_alpha) > 0.1:
						is_boundary = true

			var alpha: float
			if is_boundary:
				var neighbor_avg := neighbor_sum / float(neighbor_count) if neighbor_count > 0 else base_alpha
				alpha = lerpf(base_alpha, neighbor_avg, 0.35)
			else:
				alpha = base_alpha

			alpha = clampf(alpha, 0.0, 1.0)
			if alpha < 0.01:
				continue

			var px: float = gx * tile_w
			var py: float = gy * tile_h

			# Color tint: unexplored=full dark, explored=medium, visible=clear
			var state_val: int = _fog_tiles[idx] if idx < _fog_tiles.size() else 0
			var color: Color
			match state_val:
				0: color = Color(0.02, 0.02, 0.05, alpha)
				1: color = Color(0.02, 0.02, 0.05, alpha * 0.55)
				2: color = Color(0.02, 0.02, 0.05, alpha * 0.15)
				_: color = Color(0.02, 0.02, 0.05, alpha)

			draw_rect(Rect2(px, py, tile_w + 1.0, tile_h + 1.0), color, true)

## Calculate unit sprite region from animation metadata.
func _calc_unit_region(utype: String, owner: int, row: int, frame: int) -> Rect2:
	var race_key: String = _player_races.get(str(owner), "1")
	var key := "%s_%s" % [utype, race_key]
	var info: Dictionary = _unit_anim_info.get(key, {})
	if info.is_empty():
		return Rect2(0, 0, 96, 96)
	
	var cols_arr: Array = info.get("cols", [17])
	var fw_arr: Array = info.get("fw", [38])
	var fh_arr: Array = info.get("fh", [40])
	var row_gap: int = int(info.get("row_gap", 10))  # configurable row spacing
	
	row = mini(row, cols_arr.size() - 1)
	var n_cols: int = cols_arr[row]
	var fh: int = fh_arr[row]
	
	# Cycle frame within available directions
	frame = frame % n_cols
	
	# Get texture to calculate column width
	var tex: Texture2D = _unit_textures.get(key, null)
	if not tex:
		return Rect2(0, 0, fw_arr[row], fh)
	
	# Approximate uniform spacing based on sheet width and column count
	var sheet_w: int = tex.get_width()
	var col_w: float = float(sheet_w) / float(maxi(n_cols, 1))
	var px: int = int(float(frame) * col_w)
	
	# Calculate y offset by accumulating row heights + gap
	var py: int = int(info.get("first_row_y", 0))
	for r in range(row):
		if r < fh_arr.size():
			py += fh_arr[r] + row_gap
		else:
			py += fh_arr[-1] + row_gap
	
	return Rect2(px, py, int(col_w), fh)

## Get the correct sprite region and scale for a building type.
## Use only the COMPLETE (fully built) form — single building, no tiling.
## Race-aware: maps owner (player ID) → race → sprite region.
func _get_building_region(btype: String, owner: int) -> Dictionary:
	var region := Rect2(1, 1, 128, 109)
	var scale_sz := Vector2(0.015, 0.015)
	var race_key: String = _player_races.get(str(owner), "1")  # "1"=Terran, "2"=Zerg, "3"=Protoss

	if race_key == "1":  # Terran
		match btype:
			"base":
				region = Rect2(205, 190, 145, 95)
				scale_sz = Vector2(0.040, 0.040)
			"barracks":
				region = Rect2(573, 197, 191, 69)
				scale_sz = Vector2(0.0319, 0.0319)
			"factory":
				region = Rect2(409, 466, 164, 47)
				scale_sz = Vector2(0.0426, 0.0426)
			"refinery":
				region = Rect2(382, 189, 191, 77)
				scale_sz = Vector2(0.026, 0.026)
			"starport":
				region = Rect2(573, 446, 191, 86)
				scale_sz = Vector2(0.0256, 0.0256)
			_:
				region = Rect2(1, 1, 128, 109)
				scale_sz = Vector2(0.015, 0.015)
	elif race_key == "2":  # Zerg
		match btype:
			"base":
				region = Rect2(30, 301, 121, 128)
				scale_sz = Vector2(0.033, 0.033)
			"barracks":
				region = Rect2(1478, 688, 83, 85)
				scale_sz = Vector2(0.048, 0.048)
			"lair":
				region = Rect2(10, 627, 210, 132)
				scale_sz = Vector2(0.019, 0.019)
			"hive":
				region = Rect2(11, 1184, 141, 124)
				scale_sz = Vector2(0.028, 0.028)
			_:
				region = Rect2(1475, 670, 89, 100)
				scale_sz = Vector2(0.045, 0.045)
	elif race_key == "3":  # Protoss
		match btype:
			"base":
				region = Rect2(14, 2, 128, 115)
				scale_sz = Vector2(0.035, 0.035)
			"barracks":
				region = Rect2(206, 198, 191, 69)
				scale_sz = Vector2(0.032, 0.032)
			_:
				region = Rect2(1, 1, 128, 109)
				scale_sz = Vector2(0.015, 0.015)

	return {"region": region, "scale": scale_sz}

func _has_building_region_override(_btype: String, _owner: int) -> bool:
	# All buildings now use manifest-based atlas via SpriteLoader.
	# Hardcoded overrides removed — they drifted out of sync with atlas images.
	return false

func _has_unit_region_override(e: Dictionary) -> bool:
	return str(e.get("type", e.get("entity_type", ""))) in ["worker", "soldier", "scout"]

func _get_unit_region_override(e: Dictionary) -> Dictionary:
	var etype := str(e.get("type", e.get("entity_type", "")))
	var owner := int(e.get("owner", 0))
	var race_key: String = _player_races.get(str(owner), "1")  # race ID: 1/2/3
	var texture_key := "%s_%s" % [etype, race_key]
	var row := 0
	var scale_sz := Vector2(0.022, 0.022)
	match etype:
		"worker":
			scale_sz = Vector2(0.026, 0.026)
		"soldier":
			scale_sz = Vector2(0.024, 0.024)
		"scout":
			scale_sz = Vector2(0.024, 0.024)
	return {
		"texture_key": texture_key,
		"region": _calc_unit_region(etype, owner, row, _anim_frame),
		"scale": scale_sz,
	}

## Sync sprite nodes with entity data each tick.
func _update_entity_sprites() -> void:
	if not _sprite_container:
		return
	var active_ids: Dictionary = {}
	var visible_count := 0

	for e in _ents:
		var eid: String = str(e.id)
		active_ids[eid] = true
		if bool(e.get("preview_hidden", false)):
			if _sprite_pool.has(eid):
				_sprite_pool[eid].visible = false
			continue

		# Skip entities in fog (non-own)
		if e.owner != 1 and _is_in_fog(e):
			if _sprite_pool.has(eid):
				_sprite_pool[eid].visible = false
			continue

		var visual_id := _resolve_visual_id(e)
		var is_building := _is_building_entity_visual(e, visual_id)
		var is_generated_resource_preview: bool = _test_mode and str(e.get("type", "")) == "resource" and str(e.get("generated_asset_id", "")) != ""
		var is_generated_unit_preview: bool = _test_mode and str(e.get("type", "")) == "unit" and str(e.get("generated_asset_id", "")) != ""
		var has_unit_override := _has_unit_region_override(e)
		var node: Node2D = _sprite_pool.get(eid, null)
		var needs_animated := not is_building and not has_unit_override and not is_generated_resource_preview
		if node == null or (needs_animated and not (node is AnimatedSprite2D)) or (not needs_animated and not (node is Sprite2D)):
			if node:
				node.queue_free()
			node = AnimatedSprite2D.new() if needs_animated else Sprite2D.new()
			node.name = "Ent_" + eid
			node.z_index = 1
			_sprite_container.add_child(node)
			_sprite_pool[eid] = node

		if is_building:
			var sprite := node as Sprite2D
			var btype := str(e.get("building_type", ""))
			var race_key: int = int(_player_races.get(str(int(e.get("owner", 0))), "1"))
			var override_texture: Texture2D = _building_textures.get(race_key, null)
			if _has_building_region_override(btype, int(e.owner)) and override_texture:
				var binfo: Dictionary = _get_building_region(btype, int(e.owner))
				sprite.texture = override_texture
				sprite.region_enabled = true
				sprite.region_rect = binfo["region"]
				sprite.scale = binfo["scale"]
				sprite.visible = true
				sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_DISABLED
				sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			else:
				var atlas := _sprite_loader.get_building_atlas(visual_id) if _sprite_loader else null
				if atlas:
					sprite.texture = atlas
					sprite.region_enabled = false
					sprite.scale = _visual_scale(visual_id, true)
					sprite.visible = true
					sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_DISABLED
					sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
				else:
					sprite.texture = null
					sprite.visible = false
		elif is_generated_resource_preview:
			var sprite := node as Sprite2D
			var asset_id := str(e.get("generated_asset_id", ""))
			var atlas := _sprite_loader.get_generated_asset_atlas(asset_id, "resource", true) if _sprite_loader else null
			if atlas:
				sprite.texture = atlas
				sprite.region_enabled = false
				var scale := float(e.get("render_scale", 0.018))
				sprite.scale = Vector2(scale, scale)
				sprite.visible = true
				sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_DISABLED
				sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			else:
				sprite.texture = null
				sprite.visible = false
		elif has_unit_override:
			var sprite := node as Sprite2D
			var uinfo: Dictionary = _get_unit_region_override(e)
			var texture: Texture2D = _unit_textures.get(str(uinfo["texture_key"]), null)
			if texture:
				sprite.texture = texture
				sprite.region_enabled = true
				sprite.region_rect = uinfo["region"]
				sprite.scale = uinfo["scale"]
				sprite.visible = true
				sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_DISABLED
				sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			else:
				sprite.texture = null
				sprite.visible = false
				if _bridge and _bridge._tick % 120 == 0:
					push_warning("[GameView] Building '%s' visual_id='%s': no override and no atlas" % [eid, visual_id])
		else:
			var anim_sprite := node as AnimatedSprite2D
			var frames: SpriteFrames = null
			if is_generated_unit_preview and _sprite_loader:
				frames = _sprite_loader.get_generated_unit_preview_frames(
					str(e.get("generated_asset_id", visual_id)),
					str(e.get("preview_action", "moving"))
				)
			elif _sprite_loader:
				frames = _sprite_loader.get_frames(visual_id)
			if frames:
				anim_sprite.sprite_frames = frames
				var anim_key := _unit_animation_key(e, frames)
				if anim_key != "":
					if anim_sprite.animation != anim_key:
						anim_sprite.animation = anim_key
					if not anim_sprite.is_playing():
						anim_sprite.play()
				if is_generated_unit_preview and e.has("render_scale"):
					var scale := float(e.get("render_scale", 0.022))
					anim_sprite.scale = Vector2(scale, scale)
				else:
					anim_sprite.scale = _visual_scale(visual_id, false)
				anim_sprite.visible = true
				anim_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			else:
				anim_sprite.sprite_frames = null
				anim_sprite.visible = false

		if node.visible:
			node.modulate = Color.WHITE
		node.position = Vector2(e.px, e.py)

	# Hide sprites for entities that no longer exist
	for eid in _sprite_pool:
		if not active_ids.has(eid):
			_sprite_pool[eid].visible = false

	if _bridge and _bridge._tick % 60 == 0:
		var vc := 0
		for eid in _sprite_pool:
			if _sprite_pool[eid].visible:
				vc += 1
		print("[GameView] tick=%d ents=%d sprites=%d visible=%d" % [_bridge._tick, _ents.size(), _sprite_pool.size(), vc])

func _draw_entities(co: Vector2) -> void:
	# Sprint 4: Entities in unexplored (state 0) or explored (state 1) fog are hidden
	# (explored shows terrain but not units from other players).
	for e in _ents:
		# Fog visibility check: hide non-own entities in non-visible fog
		if e.owner != 1 and _is_in_fog(e):
			continue

		var pos := Vector2(e.px, e.py) 

		# ─── Only draw circles for resources (no sprite) ───
		# Workers, soldiers, scouts, buildings use Sprite2D nodes instead
		if e.type == "resource":
			if bool(e.get("uses_sprite", false)):
				continue
			var radius := 0.4
			if e.resource_type == "mineral":
				draw_rect(Rect2(pos - Vector2(radius, radius), Vector2(radius * 2, radius * 2)), Color(1.0, 0.85, 0.0, 1.0), true)
			elif e.resource_type == "gas":
				draw_circle(pos, radius, Color(0.0, 0.8, 0.0, 1.0))
			else:
				draw_circle(pos, radius, Color.GRAY)

	# Attack / move target lines
	for e in _ents:
		if e.owner != 1 and not _test_mode:
			continue
		if e.attack_target_id != "" or not e.is_idle:
			var lpos := Vector2(e.px, e.py) 
			if e.attack_target_id != "":
				var tgt = _get_ent_by_id(e.attack_target_id)
				if not tgt.is_empty():
					var tpos := Vector2(tgt.px, tgt.py) 
					draw_line(lpos, tpos, Color(1.0, 0.3, 0.3, 0.5), 0.06, true)
			elif e.target_x != 0 or e.target_y != 0:
				var tpos := Vector2(e.target_x, e.target_y)   # TILE_SIZE=1, no _cell multiplier
				draw_line(lpos, tpos, Color(0.3, 1.0, 0.3, 0.3), 0.06, true)

func _is_in_fog(e: Dictionary) -> bool:
	"""Check if an entity is in non-visible fog (unexplored or explored but not currently visible).
	Uses smooth alpha: if fog is still fading out (alpha < 0.15), entity is considered visible."""
	if _fog_w <= 0 or _fog_h <= 0 or _fog_alpha.is_empty():
		return false
	var fog_x := int(e.px * float(_fog_w) / _map_w)
	var fog_y := int(e.py * float(_fog_h) / _map_h)
	fog_x = clampi(fog_x, 0, _fog_w - 1)
	fog_y = clampi(fog_y, 0, _fog_h - 1)
	var idx := fog_y * _fog_w + fog_x
	if idx < _fog_alpha.size():
		# If fog alpha is very low (still fading from visible), entity is visible
		return _fog_alpha[idx] > 0.15
	return true

func _draw_attack_flashes(_co: Vector2) -> void:
	## Draw white overlay on entities that just attacked (attack flash).
	## game_view z_index=5 renders ABOVE sprite_container z_index=1,
	## so this overlay appears on top of entity sprites.
	for eid in _attack_flash_timers:
		var remaining: float = float(_attack_flash_timers[eid])
		var flash_alpha: float = clampf(remaining / ATTACK_FLASH_DURATION, 0.0, 1.0)
		var e: Dictionary = _get_entity_data(str(eid))
		if e.is_empty():
			continue
		if e.owner != 1 and _is_in_fog(e):
			continue
		var pos := Vector2(float(e.get("px", 0.0)), float(e.get("py", 0.0)))
		var radius := _visual_radius(e)
		# White overlay circle that fades out
		var flash_color: Color = Color(1.0, 1.0, 1.0, flash_alpha * 0.75)
		draw_circle(pos, radius * 1.1, flash_color)
		# Bright white outline ring
		var ring_color: Color = Color(1.0, 1.0, 1.0, flash_alpha * 0.9)
		draw_arc(pos, radius * 1.15, 0.0, TAU, 20, ring_color, 0.06, true)

func _draw_death_explosions(_co: Vector2) -> void:
	## Draw expanding + fading circle explosion at entity death positions.
	## Duration: ~0.5 seconds (DEATH_EFFECT_DURATION).
	for effect in _dead_effects:
		var lifetime: float = maxf(float(effect.get("lifetime", DEATH_EFFECT_DURATION)), 0.01)
		var age: float = float(effect.get("age", 0.0))
		var t := clampf(age / lifetime, 0.0, 1.0)
		var alpha: float = 1.0 - t
		var pos: Vector2 = effect.get("pos", Vector2.ZERO)
		var base_color: Color = effect.get("color", Color.WHITE)
		var entity_type: String = str(effect.get("entity_type", ""))
		# Buildings have larger explosions
		var is_building: bool = entity_type == "building"
		var base_radius: float = 1.2 if is_building else 0.6
		var max_radius: float = 3.0 if is_building else 1.5
		var radius := lerpf(base_radius, max_radius, t)
		# Outer expanding ring (team color, fading)
		var ring_color: Color = base_color
		ring_color.a = alpha * 0.8
		draw_arc(pos, radius, 0.0, TAU, 24, ring_color, 0.08 if not is_building else 0.14, true)
		# Inner glow fill (fading faster)
		var fill_color: Color = Color(1.0, 0.85, 0.6, alpha * 0.35)
		draw_circle(pos, radius * 0.6, fill_color)
		# Secondary ring for buildings
		if is_building:
			var ring2_color: Color = Color(1.0, 0.4, 0.1, alpha * 0.5)
			draw_arc(pos, radius * 0.75, 0.0, TAU, 18, ring2_color, 0.10, true)

func _draw_hover_highlight(_co: Vector2) -> void:
	## Draw a bright outline on the entity currently under the mouse cursor.
	if _hovered_entity_id == "":
		return
	var e: Dictionary = _get_entity_data(_hovered_entity_id)
	if e.is_empty():
		return
	if e.owner != 1 and _is_in_fog(e):
		return
	var pos := Vector2(float(e.get("px", 0.0)), float(e.get("py", 0.0)))
	var radius := _visual_radius(e)
	# Bright white ring for hover feedback
	var hover_color: Color = Color(1.0, 1.0, 1.0, 0.65)
	draw_arc(pos, radius * 1.08, 0.0, TAU, 24, hover_color, 0.055, true)
	# Subtle glow fill
	var glow_color: Color = Color(1.0, 1.0, 1.0, 0.08)
	draw_circle(pos, radius * 1.05, glow_color)

func _draw_damage_floats(co: Vector2) -> void:
	for f in _dmg_floats:
		var alpha: float = clampf(f.ttl / 30.0, 0.0, 1.0)
		var pos := Vector2(f.x, f.y) 
		var txt := "-%d" % int(f.amount)
		draw_string(_default_font, pos, txt, HORIZONTAL_ALIGNMENT_CENTER, -1, 8, Color(1.0, 0.2, 0.2, alpha))

func _draw_health_bars(co: Vector2) -> void:
	for e in _ents:
		if e.max_health <= 0 or e.type == "resource":
			continue
		if e.owner != 1 and _is_in_fog(e):
			continue
		if not _selected.has(e.id) and e.health >= e.max_health:
			continue
		var pos := Vector2(e.px, e.py) 
		var radius := _visual_radius(e)
		var bar_w := clampf(radius * 1.45, 0.55, 2.8)
		var bar_h := 0.15
		var bar_y := pos.y - radius - 0.28
		var frac: float = e.health / e.max_health
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.3, 0.3, 0.3, 0.8), true)
		var hp_color := Color.GREEN if frac > 0.6 else Color.YELLOW if frac > 0.3 else Color.RED
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * frac, bar_h), hp_color, true)

# ─── Build Progress Bar ──────────────────────────────────
func _draw_build_progress_bars(_co: Vector2) -> void:
	## Draw yellow/orange progress bar above buildings that are under construction.
	## Positioned above the health bar for constructing buildings.
	for e in _ents:
		if e.type != "building":
			continue
		var is_constructing: bool = bool(e.get("is_constructing", false))
		if not is_constructing:
			continue
		if e.owner != 1 and _is_in_fog(e):
			continue
		var pos := Vector2(e.px, e.py)
		var radius := _visual_radius(e)
		var bar_w := clampf(radius * 1.45, 0.55, 2.8)
		var bar_h := 0.12
		# Position above the health bar (which is at radius + 0.28 above center)
		var bar_y := pos.y - radius - 0.28 - bar_h - 0.08
		# Build progress: 0.0 to 1.0 (if unavailable, show 0)
		var build_progress: float = clampf(_to_f(e.get("build_progress"), 0.0), 0.0, 1.0)
		# Background bar (dark)
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.25, 0.2, 0.1, 0.8), true)
		# Progress fill — yellow to orange gradient based on progress
		var fill_color: Color = Color(1.0, 0.85, 0.15, 0.9).lerp(Color(1.0, 0.55, 0.1, 0.9), build_progress)
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * build_progress, bar_h), fill_color, true)
		# Border outline
		draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.6, 0.5, 0.3, 0.5), false, 0.03)

# ─── Team Color Helper ────────────────────────────────────
func _team_color(owner: int) -> Color:
	## Return a team color for the given owner ID.
	match owner:
		1: return Color(0.2, 0.8, 0.3)   # green (player)
		2: return Color(0.9, 0.2, 0.2)   # red (enemy AI)
		3: return Color(0.9, 0.8, 0.2)   # yellow (Protoss)
		_: return Color(0.6, 0.6, 0.6)   # gray (neutral)

# ─── Phase B1: Production Queue Visualization ────────────────
func _unit_letter(unit_type: String) -> String:
	match unit_type.to_lower():
		"marine": return "M"
		"firebat": return "F"
		"ghost": return "G"
		"medic": return "D"
		"worker", "scv": return "W"
		"vulture": return "V"
		"tank", "siege_tank": return "T"
		"goliath": return "L"
		"wraith": return "R"
		"dropship": return "P"
		"vessel", "science_vessel": return "S"
		"zergling": return "Z"
		"hydralisk": return "H"
		"ultralisk": return "U"
		"overlord": return "O"
		"queen": return "Q"
		"mutalisk": return "Mu"
		_: return unit_type.left(1).to_upper()

func _draw_production_bars(_co: Vector2) -> void:
	for e in _ents:
		if e.type != "building":
			continue
		var queue: Array = e.get("production_queue", [])
		if queue.is_empty():
			continue
		if e.owner != 1 and _is_in_fog(e):
			continue
		var pos := Vector2(e.px, e.py)
		var radius := _visual_radius(e)
		var bar_w := radius * 1.4
		var bar_h := 0.12
		var base_y := pos.y - radius - 0.48
		var timers: Array = e.get("production_timers", [])
		for i in range(queue.size()):
			var bar_y := base_y - i * (bar_h + 0.04)
			var unit_type: String = str(queue[i])
			var letter := _unit_letter(unit_type)
			# Background bar
			draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w, bar_h), Color(0.2, 0.2, 0.2, 0.8), true)
			if i == 0 and timers.size() > 0:
				# First item: green progress bar
				var timer_val: float = _to_f(timers[0], 0.0)
				var max_timer: float = 20.0  # approximate if unknown
				var progress: float = clampf(1.0 - timer_val / max_timer, 0.0, 1.0)
				draw_rect(Rect2(pos.x - bar_w / 2, bar_y, bar_w * progress, bar_h), Color(0.2, 0.85, 0.2, 0.9), true)
			# Unit type letter above the bar
			var letter_y := bar_y - 0.14
			draw_string(_default_font, Vector2(pos.x - 0.1, letter_y), letter, HORIZONTAL_ALIGNMENT_CENTER, -1, 8, Color(0.9, 0.9, 0.9, 0.9))

# ─── Phase B5: Unit Status Icons ────────────────────────────
func _draw_status_icons(_co: Vector2) -> void:
	for e in _ents:
		if e.type == "resource" or e.type == "building":
			continue
		if e.owner != 1 and _is_in_fog(e):
			continue
		var pos := Vector2(e.px, e.py)
		var radius := _visual_radius(e)
		var icon_y := pos.y - radius - 0.50
		var icon_x := pos.x
		var has_target: bool = str(e.get("attack_target_id", "")) != ""
		var is_idle: bool = bool(e.get("is_idle", true))
		var speed: float = _to_f(e.get("speed", 0.0), 0.0)
		var is_moving: bool = not is_idle and not has_target and speed > 0.0
		var carry_amount: float = _to_f(e.get("carry_amount", 0.0), 0.0)
		var carry_cap: float = _to_f(e.get("carry_cap", 0.0), 0.0)
		var is_gathering: bool = carry_amount > 0 and carry_cap > 0
		if has_target:
			# Attacking: small red triangle (sword icon)
			var s := 0.12
			var pts := PackedVector2Array([
				Vector2(icon_x, icon_y + s),
				Vector2(icon_x - s, icon_y - s * 0.6),
				Vector2(icon_x + s, icon_y - s * 0.6),
			])
			draw_colored_polygon(pts, Color(1.0, 0.2, 0.2, 0.9))
		elif is_gathering:
			# Gathering: small yellow diamond (crystal icon)
			var s := 0.10
			var pts := PackedVector2Array([
				Vector2(icon_x, icon_y + s),
				Vector2(icon_x - s, icon_y),
				Vector2(icon_x, icon_y - s),
				Vector2(icon_x + s, icon_y),
			])
			draw_colored_polygon(pts, Color(1.0, 0.9, 0.2, 0.9))
		elif is_moving:
			# Moving: small blue chevron
			var s := 0.12
			var pts := PackedVector2Array([
				Vector2(icon_x - s, icon_y + s * 0.5),
				Vector2(icon_x, icon_y - s * 0.5),
				Vector2(icon_x + s, icon_y + s * 0.5),
			])
			draw_colored_polygon(pts, Color(0.3, 0.6, 1.0, 0.9))
		elif is_idle:
			# Idle: small white dot
			draw_circle(Vector2(icon_x, icon_y), 0.08, Color(1.0, 1.0, 1.0, 0.6))

func _draw_selection_rings(_co: Vector2) -> void:
	## Selected units: green ring with breathing (sinusoidal) glow pulse.
	var breathe_phase: float = sin(_game_time * SELECTION_BREATHE_SPEED)
	var breathe_alpha: float = lerpf(SELECTION_BREATHE_MIN, SELECTION_BREATHE_MAX, 0.5 + 0.5 * breathe_phase)
	for uid in _selected:
		var e := _get_ent_by_id(uid)
		if e.is_empty():
			continue
		var pos := Vector2(e.px, e.py)
		var radius := _visual_radius(e)
		# Main selection ring with breathing alpha
		var ring_color: Color = Color(0.2, 1.0, 0.2, breathe_alpha)
		draw_arc(pos, radius, 0.0, TAU, 24, ring_color, 0.055, true)
		# Outer glow ring (subtler, also breathing but offset phase)
		var glow_phase: float = sin(_game_time * SELECTION_BREATHE_SPEED + PI * 0.5)
		var glow_alpha: float = lerpf(0.0, 0.25, 0.5 + 0.5 * glow_phase)
		var glow_color: Color = Color(0.4, 1.0, 0.4, glow_alpha)
		draw_arc(pos, radius * 1.12, 0.0, TAU, 24, glow_color, 0.04, true)

# ─── Pylon Power Range Visualization ───────────────────────
func _draw_pylon_power_range(_co: Vector2) -> void:
	"""Render semi-transparent blue circles for Pylon power range.
	Only drawn for player 1's Pylons when player 1's race is Protoss (race ID '3').
	Power radius: PYLON_POWER_RADIUS (8 game-coordinate cells)."""
	# Only render if player 1's race is Protoss
	var p1_race: String = str(_player_races.get("1", "1"))
	if p1_race != "3":
		return

	# Semi-transparent blue fill (SC1-style Pylon aura)
	var fill_color: Color = Color(0.2, 0.4, 1.0, 0.10)
	# Slightly more opaque blue border ring
	var ring_color: Color = Color(0.3, 0.5, 1.0, 0.35)
	var ring_width: float = 0.08

	for e in _ents:
		if e.owner != 1:
			continue
		if e.type != "building":
			continue
		# Pylon is building_type "supply_depot" with unit_type "Pylon" for Protoss
		var btype: String = str(e.get("building_type", ""))
		var utype: String = str(e.get("unit_type", ""))
		if btype != "supply_depot" and utype != "Pylon":
			continue
		# If unit_type is present but not "Pylon", it's a Terran/Zerg supply depot — skip
		if utype != "" and utype != "Pylon":
			continue

		var pos := Vector2(e.px, e.py)
		# Filled semi-transparent blue circle
		draw_circle(pos, PYLON_POWER_RADIUS, fill_color)
		# Blue ring outline
		draw_arc(pos, PYLON_POWER_RADIUS, 0.0, TAU, 64, ring_color, ring_width, true)

# ─── Sprint 4: Draw Rally Point Lines ──────────────────────
func _draw_rally_lines(co: Vector2) -> void:
	for bid in _rally_indicators:
		var indicator = _rally_indicators[bid]
		if not indicator.has_rally():
			continue
		# Only draw if building is selected
		if _selection and not _selection.is_selected(bid):
			continue
		var bpos: Vector2 = indicator._building_pos 
		var rpos: Vector2 = indicator._rally_pos 

		# Dashed line
		var direction: Vector2 = rpos - bpos
		var length: float = direction.length()
		if length < 1.0:
			continue
		var dir_norm: Vector2 = direction / length
		var drawn: float = 0.0
		var is_dash: bool = true
		const DASH_LEN := 0.5
		const GAP_LEN := 0.4

		while drawn < length:
			var seg_len: float = DASH_LEN if is_dash else GAP_LEN
			var remaining: float = length - drawn
			seg_len = minf(seg_len, remaining)
			if is_dash:
				var start: Vector2 = bpos + dir_norm * drawn
				var end: Vector2 = bpos + dir_norm * (drawn + seg_len)
				draw_line(start, end, Color(0.2, 1.0, 0.2, 0.7), 0.06, true)
			drawn += seg_len
			is_dash = not is_dash

		# Flag at rally point — compact tile-space flag
		var pole_top: Vector2 = rpos - Vector2(0, 0.4)
		draw_line(rpos, pole_top, Color(1.0, 0.9, 0.2, 0.8), 0.04, true)
		var flag_pts := PackedVector2Array([
			pole_top,
			pole_top + Vector2(0.2, 0.07),
			pole_top + Vector2(0, 0.14)
		])
		draw_colored_polygon(flag_pts, Color(1.0, 0.9, 0.2, 0.7))

func _draw_drag_box() -> void:
	if not _dragging:
		return
	if _drag_start.distance_to(_drag_end) < 5.0:
		return
	# Convert screen-space drag coords to world space for drawing
	var ws := _screen_to_world(_drag_start)
	var we := _screen_to_world(_drag_end)
	var rect := Rect2(ws, we - ws).abs()
	draw_rect(rect, Color(0.3, 1.0, 0.3, 0.15), true)
	draw_rect(rect, Color(0.3, 1.0, 0.3, 0.7), false, 0.06)

func _draw_game_over_overlay() -> void:
	# Game over overlay is now handled by _victory_screen in CanvasLayer
	pass

# ─── Minimap ──────────────────────────────────────────────
# Minimap is now drawn by the MinimapRect child node.
func _minimap_rect() -> Rect2:
	if _mm_rect_node and _mm_rect_node is Control:
		return _mm_rect_node.get_global_rect()
	# Fallback: bottom-right floating position
	var vp := get_viewport().get_visible_rect().size
	var mm_pos := Vector2(vp.x - _mm_size.x - _mm_margin.x, vp.y - _mm_size.y - _mm_margin.y)
	return Rect2(mm_pos, _mm_size)

func _is_minimap_click(screen_pos: Vector2) -> bool:
	return _minimap_rect().has_point(screen_pos)

func _handle_minimap_click(screen_pos: Vector2) -> void:
	var mm := _minimap_rect()
	var local := screen_pos - mm.position
	var frac_x: float = local.x / mm.size.x
	var frac_y: float = local.y / mm.size.y
	var target_pos := Vector2(frac_x * _map_w, frac_y * _map_h)
	if _cam_ctrl:
		_cam_ctrl.move_to_world_position(target_pos)
	else:
		_camera.position = target_pos

func _draw_command_pings(_co: Vector2) -> void:
	for ping in _command_pings:
		var age: float = float(ping.get("age", 0.0))
		var duration: float = float(ping.get("duration", 0.32))
		var progress: float = clampf(age / duration, 0.0, 1.0)
		var alpha: float = 1.0 - progress
		var base_color: Color = Color(ping.get("color", _ground_ping_color))
		var pos: Vector2 = Vector2(ping.get("pos", Vector2.ZERO))
		var ping_type: String = str(ping.get("type", "move"))
		
		# Expanding ring
		var max_radius: float = 0.6 if ping_type != "invalid" else 0.35
		var radius: float = progress * max_radius
		var ring_color: Color = Color(base_color.r, base_color.g, base_color.b, alpha * 0.9)
		draw_arc(pos, radius, 0.0, TAU, 24, ring_color, 0.06, true)
		
		# Center dot (only for first 40% of duration)
		if progress < 0.4:
			var dot_alpha: float = alpha * (1.0 - progress / 0.4)
			var dot_color: Color = Color(base_color.r, base_color.g, base_color.b, dot_alpha)
			draw_circle(pos, 0.1, dot_color)

func _draw_control_group_hints(_co: Vector2) -> void:
	for hint in _control_group_hints:
		var age: float = float(hint.get("age", 0.0))
		var duration: float = float(hint.get("duration", 0.5))
		var progress: float = clampf(age / duration, 0.0, 1.0)
		var alpha: float = 1.0 - progress
		var text: String = str(hint.get("text", ""))
		
		var screen_center := get_viewport().get_visible_rect().size / 2.0
		var hint_pos := _screen_to_world(screen_center) + Vector2(0, _map_h * 0.4)
		var font_size: int = 16
		var font: Font = _default_font if _default_font else ThemeDB.fallback_font
		var text_size: Vector2 = font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size)
		var bg_rect := Rect2(hint_pos - text_size / 2.0 - Vector2(6, 3), text_size + Vector2(12, 6))
		
		var bg_alpha: float = alpha * 0.6
		draw_rect(bg_rect, Color(0.0, 0.0, 0.0, bg_alpha), true)
		draw_rect(bg_rect, Color(1.0, 1.0, 1.0, alpha * 0.3), false, 1.0)
		draw_string(font, hint_pos - text_size / 2.0 + Vector2(0, font_size * 0.35), text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color(1, 1, 1, alpha))

## Provides state data to the minimap_rect child node.
func _get_state_for_minimap() -> Dictionary:
	var entities_dict: Dictionary = {}
	for e in _ents:
		entities_dict[e.id] = {
			"owner": e.owner,
			"type": e.type,
				"px": e.px,
			"py": e.py,
			"resource_type": e.resource_type,
		}
	return {
		"entities": entities_dict,
		"map_width": _map_w,
		"map_height": _map_h,
		"cam_center": _camera.position,  # CENTER anchor: position IS center
		"vp_size": get_viewport().get_visible_rect().size / _camera.zoom,
		"cell_size": int(_cell),
		"fog_tiles": _fog_tiles,
		"fog_alpha": _fog_alpha,
		"fog_width": _fog_w,
		"fog_height": _fog_h,
	}

func _monitor_canvas_transform() -> void:
	var ct := get_viewport().get_canvas_transform()
	var origin_x: float = ct.get_origin().x
	if absf(origin_x) > 2.0:
		_jitter_count += 1
		_total_jitter_px += absf(origin_x)
		if _frame % 60 == 0 or _jitter_count <= 5:
			print("[Frame %d] ⚠️ CANVAS JITTER: origin_x=%.1f (count=%d)" % [_frame, origin_x, _jitter_count])

func _write_analysis() -> void:
	var positions: Array = []
	for e in _ents:
		positions.append("(%.1f, %.1f)" % [e.px, e.py])
	var pos_count: Dictionary = {}
	for p in positions:
		pos_count[p] = pos_count.get(p, 0) + 1
	var dupes: Array = []
	for p in pos_count:
		if pos_count[p] > 1:
			dupes.append(p)
	var verdict := {
		"pass": dupes.is_empty() and positions.size() == _ents.size(),
		"ents_parsed": _ents.size(),
		"unique_positions": pos_count.size(),
		"duplicates": dupes.size(),
		"tree_children": get_tree().root.get_child_count(),
		"jitter_frames": _jitter_count,
		"jitter_total_px": _total_jitter_px,
		"jitter_free": _jitter_count == 0,
		"camera_anchor": "DRAG_CENTER",
		"stretch_mode": "canvas_items",
	}
	var vf := FileAccess.open("user://render_verdict.json", FileAccess.WRITE)
	if vf:
		vf.store_string(JSON.stringify(verdict, "\t"))
		vf.close()
		print("[Verdict] ", "PASS" if verdict["pass"] else "FAIL",
				" jitter=", "NONE" if verdict["jitter_free"] else str(_jitter_count))

## ─── TEST MODE: Draw labels for test entities ───
func _draw_test_labels() -> void:
	var font: Font = _default_font
	if not font:
		return
	var title_size := 1.2
	var label_size := 0.8
	var vc_label_size := 0.55
	for header in _test_section_headers:
		draw_string(
			font,
			header.get("pos", Vector2.ZERO),
			str(header.get("text", "")),
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			title_size,
			header.get("color", Color.WHITE)
		)
	for e in _ents:
		if not str(e.id).begins_with("test_"):
			continue
		if bool(e.get("preview_hidden", false)):
			continue
		var full_label = str(e.get("label", ""))
		if full_label == "":
			continue
		draw_string(
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
			draw_string(
				font,
				Vector2(float(e.get("px", 0.0)) + 1.3, float(e.get("py", 0.0)) + vc_y_offset),
				vc,
				HORIZONTAL_ALIGNMENT_LEFT,
				-1,
				vc_label_size,
				Color(0.7, 0.9, 1.0, 0.7)
			)


func _toggle_test_mode() -> void:
	_test_mode = not _test_mode
	if _test_mode:
		_saved_ents = _ents.duplicate(true)
		_saved_player_races = _player_races.duplicate(true)
		_saved_fog_tiles = _fog_tiles
		_saved_fog_w = _fog_w
		_saved_fog_h = _fog_h
		_fog_tiles = PackedInt32Array()
		_fog_w = 0
		_fog_h = 0
		_player_races["1"] = "1"
		_player_races["2"] = "2"
		_player_races["3"] = "3"
		_build_test_entities()
		if _test_filter_panel:
			_test_filter_panel.visible = true
		if _test_btn:
			_test_btn.text = "Back"
			_test_btn.modulate = Color(1.0, 0.8, 0.8)
		print("[TEST MODE] ON — generated asset gallery")
	else:
		_clear_test_entities()
		if _test_filter_panel:
			_test_filter_panel.visible = false
		if _test_btn:
			_test_btn.text = "🧪 Test Mode"
			_test_btn.modulate = Color(0.8, 1.0, 0.8)
		print("[TEST MODE] OFF — back to normal game")
	queue_redraw()

func _toggle_elevation() -> void:
	_show_elevation = not _show_elevation
	if _elev_btn:
		_elev_btn.text = "⛰ Elev ON" if _show_elevation else "⛰ Elev"
		_elev_btn.modulate = Color(0.5, 1.0, 0.5) if _show_elevation else Color(0.7, 0.85, 0.7)
	queue_redraw()

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

	_ents = _test_ents
	_update_entity_sprites()
	queue_redraw()

func _clear_test_entities() -> void:
	_clear_test_sprites()
	_test_ents.clear()
	_test_section_headers.clear()
	_ents = _saved_ents.duplicate(true)
	_saved_ents.clear()
	_player_races = _saved_player_races.duplicate(true)
	_saved_player_races.clear()
	_fog_tiles = _saved_fog_tiles
	_fog_w = _saved_fog_w
	_fog_h = _saved_fog_h
	_update_entity_sprites()
	queue_redraw()


func _clear_test_sprites() -> void:
	var to_remove: Array = []
	for eid in _sprite_pool:
		if str(eid).begins_with("test_"):
			_sprite_pool[eid].queue_free()
			to_remove.append(eid)
	for eid in to_remove:
		_sprite_pool.erase(eid)


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


# ─── Replay Callbacks ──────────────────────────────────────
func _on_replay_loaded(replay_data: Dictionary) -> void:
	_replay_mode = true
	_game_active = false
	_replay_overlay.visible = true

	# Set map size + camera from first tick (same as _on_start does for live games)
	var first_tick: Dictionary = {}
	if replay_data.get("ticks", []).size() > 0:
		first_tick = replay_data["ticks"][0]
	_map_w = _to_f(first_tick.get("map_width"), 64.0)
	_map_h = _to_f(first_tick.get("map_height"), 64.0)
	if _map_w < 1.0:
		_map_w = 64.0
	if _map_h < 1.0:
		_map_h = 64.0
	if _cam_ctrl:
		_cam_ctrl.set_map_size(_map_w, _map_h)
	_camera.position = Vector2(_map_w / 2.0, _map_h / 2.0)

	_replay_player.load_replay(replay_data)
	print("[Replay] Loaded: %s (%d ticks, %s vs %s)" % [
		replay_data.get("match_id", "?"),
		replay_data.get("tick_count", 0),
		replay_data.get("player_races", {}).get("1", "?"),
		replay_data.get("player_races", {}).get("2", "?"),
	])
	# Auto-play the replay so it starts moving immediately
	_replay_player.play()

func _on_replay_finished() -> void:
	print("[Replay] Playback finished")
	_replay_mode = false

## Fetch the latest replay from the server and switch to replay mode.
func _request_latest_replay() -> void:
	if _bridge:
		_bridge.fetch_replay_list()

## Handle the replay list response from the server.
func _on_replay_list_loaded(data: Dictionary) -> void:
	var replays: Array = data.get("replays", [])
	if replays.is_empty():
		print("[Replay] No replays available")
		return
	# Pick the most recent (last in sorted list)
	var latest: Dictionary = replays[-1]
	var filename: String = latest.get("filename", "")
	if filename.is_empty():
		return
	print("[Replay] Loading latest: %s" % filename)
	if _bridge:
		_bridge.fetch_replay_download(filename)
