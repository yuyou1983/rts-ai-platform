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
const CombatVisualControllerScript = preload("res://scripts/combat_visual_controller.gd")
const SpriteLoaderScript = preload("res://scripts/sprite_loader.gd")
const TerrainRendererScript = preload("res://scripts/terrain_renderer.gd")
const SC1TilesetRendererScript = preload("res://scripts/sc1_tileset_renderer.gd")
const InputFeedbackControllerScript = preload("res://scripts/input_feedback_controller.gd")
const InputIntentRouterScript = preload("res://scripts/input_intent_router.gd")
const FeelMetricsRecorderScript = preload("res://scripts/feel_metrics_recorder.gd")
const PRESENTATION_MANIFEST_PATH := "res://resources/presentation_manifest.json"

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

# ─── Legacy HP-delta VFX (disabled: combat events drive VFX now) ───
const LEGACY_HP_DELTA_VFX_ENABLED := false
# Entity cache
var _ents: Array = []
var _prev_hp: Dictionary = {}
var _prev_entities: Dictionary = {}

# ─── Time tracking (shared: APM + overlay sin animations) ──
var _game_time: float = 0.0
# ─── Attack flash detection (compares previous target IDs) ──
var _prev_attack_targets: Dictionary = {}

# ─── Drag-select ───────────────────────────────────────────
var _dragging := false
var _drag_start := Vector2.ZERO
var _drag_end := Vector2.ZERO
const SELECT_RADIUS := 1.5
const PYLON_POWER_RADIUS: float = 8.0
var _test_gallery: TestModeGallery = null
var _test_label_layer: TestModeLabelLayer = null
var _test_ui_ctrl: TestModeUIController = null
var _elev_btn: Button = null
var _zoom_in_btn: Button = null
var _zoom_out_btn: Button = null
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
# _elevation_dirty kept for backward compat but no longer drives _draw();
# TerrainRenderer handles its own cache invalidation.
var _elevation_dirty: bool = false
var _show_elevation: bool = false   # toggle via debug button → TerrainRenderer visibility

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

# ─── Construction ghost fade ──────────────────────────────
var _construction_fade: Dictionary = {}  # entity_id → current_alpha (fading to 1.0)
var _construction_cfg: Dictionary = {}   # loaded from feel config

# ─── Jitter monitor ────────────────────────────────────────
var _jitter_count: int = 0
var _total_jitter_px: float = 0.0

# ─── Hover detection ─────────────────────────────────────
var _hover_check_timer: float = 0.0
const HOVER_CHECK_INTERVAL := 0.1
var _hovered_entity_id: String = ""

# ─── Control group double-tap ──────────────────────────────
var _last_group_key: int = -1
var _last_group_time: float = 0.0

# ─── Minimap ───────────────────────────────────────────────
var _mm_size := Vector2(152, 136)  # minimap inner drawing area
var _mm_margin := Vector2(12, 28)  # bottom-right float: x=8+4, y=8+20
var _mm_rect_node: Control = null  # ref to MinimapRect node
var _mm_panel_node: PanelContainer = null  # ref to Minimap panel wrapper

# ─── Integrated Pattern References ─────────────────────────
var _selection: Node  # SelectionManager autoload
var _event_bus: Node  # EventBus autoload
var _ability_mgr: Node  # AbilityManager autoload

	# ─── Sprite textures ───────────────────────────────────────
var _unit_textures: Dictionary = {}
var _building_textures: Dictionary = {}
var _player_races: Dictionary = {}  # {"1": "1", "2": "2"} — maps player ID → race ID (1=Terran, 2=Zerg, 3=Protoss)
var _resource_textures: Dictionary = {}  # cached Texture2D: path → Texture2D
var _resource_visual_cfg: Dictionary = {}  # loaded from control_feel_config.json
var _sprite_pool: Dictionary = {}  # entity_id -> Sprite2D
var _sprite_container: Node2D = null  # parent for all entity sprites
var _vfx_manager: VFXManager = null
var _combat_visual_controller: CombatVisualController = null
var _sprite_loader: SpriteLoader = null
var _presentation_manifest: Dictionary = {}
var _map_texture: Texture2D = null
var _terrain_renderer: Node2D = null  # TerrainRenderer — procedural terrain

# ─── Sprint 4 Components ──────────────────────────────────
var _cam_ctrl: Node = null  # CameraController
var _hud: Control = null    # HUD
var _ui_layer: CanvasLayer = null  # UI layer for HUD, minimap, replay overlay
var _rally_indicators: Dictionary = {}  # {building_id: RallyPointIndicator}

var _hud_overlay: HUDOverlayRenderer = null  # Delegated HUD overlay renderer
var _input_feedback_ctrl: InputFeedbackController = null  # Local input feedback
var _input_intent_router: RefCounted = InputIntentRouterScript.new()
var _attack_move_targeting: bool = false
var _feel_metrics: Node = null

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

## Load a single resource texture with caching support.
func _load_resource_texture(path: String) -> Texture2D:
	if _resource_textures.has(path):
		return _resource_textures[path]
	var tex: Texture2D = null
	if ResourceLoader.exists(path):
		tex = ResourceLoader.load(path, "Texture2D") as Texture2D
	if tex == null and FileAccess.file_exists(path):
		var image := Image.new()
		if image.load(path) == OK:
			tex = ImageTexture.create_from_image(image)
	if tex == null and path.begins_with("res://"):
		var globalized: String = ProjectSettings.globalize_path(path)
		if globalized != "" and FileAccess.file_exists(globalized):
			var image := Image.new()
			if image.load(globalized) == OK:
				tex = ImageTexture.create_from_image(image)
	if tex:
		_resource_textures[path] = tex
	else:
		push_warning("[GameView] Resource texture not found: %s" % path)
	return tex

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
	# ─── Load construction ghost config ───
	if _feel_config.has("construction"):
		_construction_cfg = _feel_config["construction"]
	else:
		_construction_cfg = {
			"ghost_alpha": 0.45,
			"breath_speed": 3.0,
			"breath_amplitude": 0.1,
			"fade_in_speed": 3.0,
		}
	# ─── Load resource visuals config ───
	if _feel_config.has("resource_visuals"):
		_resource_visual_cfg = _feel_config["resource_visuals"]
	else:
		_resource_visual_cfg = {
			"mineral_textures": [
				"res://assets/sc1_generated/MineralFieldType1.png",
				"res://assets/sc1_generated/MineralFieldType2.png",
				"res://assets/sc1_generated/MineralFieldType3.png",
			],
			"gas_texture": "res://assets/sc1_generated/VespeneGeyser.png",
			"resource_scale": 0.022,
		}
	# ─── Pre-load resource textures (cached in _resource_textures) ───
	var mineral_paths: Array = _resource_visual_cfg.get("mineral_textures", [])
	for path in mineral_paths:
		var p: String = str(path)
		if not _resource_textures.has(p):
			var tex: Texture2D = _load_resource_texture(p)
			if tex:
				_resource_textures[p] = tex
	var gas_path: String = str(_resource_visual_cfg.get("gas_texture", ""))
	if gas_path != "" and not _resource_textures.has(gas_path):
		var tex: Texture2D = _load_resource_texture(gas_path)
		if tex:
			_resource_textures[gas_path] = tex
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
	_cam_ctrl.set_map_size(_map_w, _map_h)
	_cam_ctrl.setup(_camera)
	_cam_ctrl.set_entity_data_provider(_get_entity_data)
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

	# ─── Combat VFX layer ───
	_vfx_manager = VFXManagerScript.new()
	_vfx_manager.name = "VFXManager"
	add_child(_vfx_manager)

	# ─── Combat visual controller (event-driven) ───
	_combat_visual_controller = CombatVisualControllerScript.new()
	_combat_visual_controller.name = "CombatVisualController"
	add_child(_combat_visual_controller)
	_combat_visual_controller.set_vfx_manager(_vfx_manager)

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
	# ─── Terrain renderer: choose based on terrain_mode config ───
	var terrain_mode: String = str(_feel_config.get("terrain_mode", "height_debug"))
	if terrain_mode == "sc1_tileset":
		_terrain_renderer = SC1TilesetRendererScript.new()
		_terrain_renderer.name = "SC1TilesetRenderer"
	else:
		_terrain_renderer = TerrainRendererScript.new()
		_terrain_renderer.name = "TerrainRenderer"
	_terrain_renderer.z_index = -5  # below fog, below everything else
	_terrain_renderer.visible = false  # hidden until data arrives
	add_child(_terrain_renderer)

	# ─── CanvasLayer for floating UI (above fullscreen game map) ───
	_ui_layer.layer = 10

	var vp_size := get_viewport().get_visible_rect().size

	# ─── Minimap: floating panel at bottom-right ───
	var mm_size := Vector2(160, 160)
	var mm_margin := 8
	var _mm_panel := PanelContainer.new()
	_mm_panel_node = _mm_panel
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

	# ─── HUDOverlayRenderer delegation wire-up ───
	_hud_overlay = HUDOverlayRenderer.new()
	_hud_overlay.name = "HUDOverlayRenderer"
	add_child(_hud_overlay)
	_hud_overlay.setup(_camera, _default_font)
	_hud_overlay.set_visual_helpers(
		_visual_radius, _visual_scale, _resolve_visual_id,
		_is_building_entity_visual, _screen_to_world, _world_to_screen, _is_in_fog,
		_get_ent_by_id, _get_entity_data, _to_f, _ent_at_world_pos
	)
	_hud_overlay.pings_updated.connect(func(): queue_redraw())
	_hud_overlay.set_data_refs(_player_races, _rally_indicators, _selection)
	_hud_overlay.set_map_size(_map_w, _map_h)
	# ─── Forward feel_config ping settings to HUDOverlayRenderer ───
	if _feel_config.has("command_feedback"):
		var cf: Dictionary = _feel_config["command_feedback"]
		_hud_overlay.update_ping_config(
			float(cf.get("ground_ping_duration", 0.32)),
			Color.from_string(str(cf.get("ground_ping_color", "#44ff88")), Color(0.267, 1.0, 0.533)),
			float(cf.get("attack_ping_duration", 0.38)),
			Color.from_string(str(cf.get("attack_ping_color", "#ff4444")), Color(1.0, 0.267, 0.267)),
			float(cf.get("invalid_ping_duration", 0.22)),
			Color.from_string(str(cf.get("invalid_ping_color", "#aa6666")), Color(0.667, 0.4, 0.4)),
			0.5, 0.8
		)
	if _feel_config.has("control_group_feedback"):
		var cg: Dictionary = _feel_config["control_group_feedback"]
		_hud_overlay._assign_flash_duration = float(cg.get("assign_flash_duration", 0.5))
		_hud_overlay._empty_group_hint_duration = float(cg.get("empty_group_hint_duration", 0.8))

	# ─── Input Feedback Controller (local input feedback only) ───
	_input_feedback_ctrl = InputFeedbackControllerScript.new()
	_input_feedback_ctrl.name = "InputFeedbackController"
	add_child(_input_feedback_ctrl)
	_input_feedback_ctrl.pings_updated.connect(func(): queue_redraw())
	_feel_metrics = FeelMetricsRecorderScript.new()
	_feel_metrics.name = "FeelMetricsRecorder"
	add_child(_feel_metrics)

	# ─── Test Mode Gallery ───
	_test_gallery = TestModeGallery.new()
	_test_gallery.name = "TestModeGallery"
	add_child(_test_gallery)
	_test_gallery.setup(_ui_layer, _sprite_loader, _default_font, _entity_cache_by_id)
	_test_gallery.entities_rebuilt.connect(_on_test_entities_rebuilt)
	_test_gallery.state_changed.connect(_on_test_state_changed)
	# Bug 4 fix: instantiate TestModeLabelLayer, add as child of _ui_layer
	_test_label_layer = TestModeLabelLayer.new()
	_test_label_layer.name = "TestModeLabelLayer"
	_test_label_layer.setup(_camera, _default_font)
	_ui_layer.add_child(_test_label_layer)
	_test_label_layer.visible = false
	# Bug 5 fix: instantiate TestModeUIController, add as child of _ui_layer
	_test_ui_ctrl = TestModeUIController.new()
	_test_ui_ctrl.name = "TestModeUIController"
	_ui_layer.add_child(_test_ui_ctrl)
	_test_ui_ctrl.setup()
	_test_ui_ctrl.mode_selected.connect(_test_gallery.set_gallery_mode)
	_test_ui_ctrl.filter_changed.connect(_test_gallery.set_filter)
	_test_ui_ctrl.visible = false
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

	if _test_gallery and _test_gallery.is_active():
		_test_gallery.advance_animation(delta)
	# CameraController handles all camera movement now

	# ── Delegation: push entity data + advance timers into HUDOverlayRenderer ──
	if _hud_overlay:
		_hud_overlay.provide_entity_data(_ents, _selected, _entity_cache_by_id)
		_hud_overlay.advance_timers(delta)

	# ── Advance input feedback controller timers ──
	if _input_feedback_ctrl:
		_input_feedback_ctrl.advance_timers(delta)

	# Hover detection (throttled)
	_hover_check_timer -= delta
	if _hover_check_timer <= 0.0:
		_hover_check_timer = HOVER_CHECK_INTERVAL
		var mouse_world: Vector2 = _screen_to_world(get_viewport().get_mouse_position())
		var hovered_ent: Dictionary = _ent_at_world_pos(mouse_world, SELECT_RADIUS)
		_hovered_entity_id = "" if hovered_ent.is_empty() else str(hovered_ent.get("id", ""))

	# ── Construction fade: lerp completed buildings to full alpha ──
	if not _construction_fade.is_empty():
		var fade_speed: float = float(_construction_cfg.get("fade_in_speed", 3.0))
		var to_remove: Array = []
		for eid in _construction_fade:
			var cur_alpha: float = float(_construction_fade[eid])
			cur_alpha = move_toward(cur_alpha, 1.0, fade_speed * delta)
			if cur_alpha >= 0.999:
				cur_alpha = 1.0
				to_remove.append(eid)
			_construction_fade[eid] = cur_alpha
			if _sprite_pool.has(eid):
				var node: Node2D = _sprite_pool[eid]
				if node.visible:
					node.modulate.a = cur_alpha
		for eid in to_remove:
			_construction_fade.erase(eid)

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


func _ent_at_world_pos_for_selection(world_pos: Vector2) -> Dictionary:
	var camera_zoom: float = _camera.zoom.x if _camera else 1.0
	if _selection:
		return _selection.choose_best_hit(_ents, world_pos, camera_zoom, _visual_radius)
	return _ent_at_world_pos(world_pos)

func _is_in_fog(e: Dictionary) -> bool:
	var px: float = float(e.get("px", 0.0))
	var py: float = float(e.get("py", 0.0))
	var gx: int = clampi(int(px * float(_fog_w) / _map_w) if _map_w > 0.0 else 0, 0, _fog_w - 1)
	var gy: int = clampi(int(py * float(_fog_h) / _map_h) if _map_h > 0.0 else 0, 0, _fog_h - 1)
	var idx: int = gy * _fog_w + gx
	if idx < 0 or idx >= _fog_tiles.size():
		return false
	return _fog_tiles[idx] < 2

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
		if _attack_move_targeting:
			_attack_move_targeting = false
			return
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
		if _attack_move_targeting:
			_handle_attack_move_click(_screen_to_world(mpos))
			return
		_dragging = true
		_drag_start = mpos
		_drag_end = mpos
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and not event.pressed:
		if _dragging:
			_dragging = false
			var pointer_kind: String = _selection.classify_pointer_release(_drag_start, _drag_end) if _selection else ("click" if _drag_start.distance_to(_drag_end) <= 5.0 else "drag")
			if pointer_kind == "click":
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
			_handle_control_group_key(group_idx, event)
			return

	# Explicit SC1-style attack-move targeting. It must run before AbilityManager
	# because normal left-click selection consumes mouse presses in this view.
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_A:
		if _has_selected_mobile_units():
			_attack_move_targeting = true
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
			_attack_move_targeting = false
			if _selection:
				_selection.remove_all_selection()
			else:
				_selected.clear()
			if _hud:
				_hud.hide_build_panel()
			_build_mode = false
			_build_type = ""


func _handle_control_group_key(group_idx: int, event: InputEventKey) -> void:
	if _selection == null:
		return
	var metrics_name: String = "control_group_recall_%d" % group_idx
	if event.ctrl_pressed:
		metrics_name = "control_group_assign_%d" % group_idx
	elif event.shift_pressed:
		metrics_name = "control_group_add_%d" % group_idx
	var metrics_id: int = _feel_metrics.begin_event(metrics_name, _selection.get_selected_ids().size()) if _feel_metrics else -1
	if event.ctrl_pressed:
		_selection.create_hotkey_group(group_idx)
		if _input_feedback_ctrl:
			_input_feedback_ctrl.show_control_group_flash(group_idx, true)
		if _feel_metrics:
			_feel_metrics.mark_feedback(metrics_id)
			_feel_metrics.complete_event(metrics_id, "success")
		return
	if event.shift_pressed:
		_selection.add_to_hotkey_group(group_idx)
		if _input_feedback_ctrl:
			_input_feedback_ctrl.show_control_group_flash(group_idx, true)
		if _feel_metrics:
			_feel_metrics.mark_feedback(metrics_id)
			_feel_metrics.complete_event(metrics_id, "success")
		return

	var now: float = Time.get_ticks_msec() / 1000.0
	if _last_group_key == group_idx and now - _last_group_time <= 0.30:
		_selection.jump_to_hotkey_group(group_idx)
		_last_group_key = -1
		_last_group_time = 0.0
	else:
		_selection.select_hotkey_group(group_idx)
		if _selection.get_selected_ids().is_empty() and _input_feedback_ctrl:
			_input_feedback_ctrl.show_control_group_flash(group_idx, false)
		_last_group_key = group_idx
		_last_group_time = now
	if _feel_metrics:
		_feel_metrics.mark_feedback(metrics_id)
		_feel_metrics.complete_event(metrics_id, "success" if not _selection.get_selected_ids().is_empty() else "empty")


func _has_selected_mobile_units() -> bool:
	var selected_ids: Array = _selection.get_selected_ids() if _selection else _selected.keys()
	for entity_id in selected_ids:
		var entity: Dictionary = _get_ent_by_id(str(entity_id))
		if str(entity.get("type", "")) in ["worker", "soldier", "scout"]:
			return true
	return false


func _handle_attack_move_click(world_pos: Vector2) -> void:
	_attack_move_targeting = false
	var selected_ids: Array = _selection.get_selected_ids() if _selection else _selected.keys()
	var metrics_id: int = _feel_metrics.begin_event("attack_move", selected_ids.size(), true) if _feel_metrics else -1
	var moving_ids: Array = []
	for entity_id in selected_ids:
		var entity: Dictionary = _get_ent_by_id(str(entity_id))
		if str(entity.get("type", "")) in ["worker", "soldier", "scout"]:
			moving_ids.append(str(entity_id))
	if moving_ids.is_empty():
		if _input_feedback_ctrl:
			_input_feedback_ctrl.show_invalid_ping(world_pos)
		if _feel_metrics:
			_feel_metrics.mark_feedback(metrics_id)
			_feel_metrics.complete_event(metrics_id, "empty")
		return

	# SimCore currently has no attack-move command. Preserve the correct input
	# semantics and visual language while degrading explicitly to formation move.
	var formation: Array = _selection.calculate_formation_positions(world_pos, moving_ids.size()) if _selection else _calc_formation_fallback(world_pos, moving_ids.size())
	var commands: Array = []
	for index in range(moving_ids.size()):
		var target: Vector2 = formation[index] if index < formation.size() else world_pos
		commands.append({
			"action": "move",
			"unit_id": moving_ids[index],
			"target_x": target.x,
			"target_y": target.y,
			"issuer": 1,
		})
	_bridge.submit_commands(commands)
	if _feel_metrics:
		_feel_metrics.mark_command(metrics_id)
	if _event_bus:
		for command in commands:
			_event_bus.emit_command_issued(command)
	if _input_feedback_ctrl:
		_input_feedback_ctrl.show_attack_move_ping(world_pos)
	if _feel_metrics:
		_feel_metrics.mark_feedback(metrics_id)
		_feel_metrics.complete_event(metrics_id, "success")
	_record_apm_action()

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
				if abs(_replay_player._playback_speed - speeds[i]) < 0.01:
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
				if abs(_replay_player._playback_speed - speeds[i]) < 0.01:
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
	var metrics_id: int = _feel_metrics.begin_event("right_click", selected_ids.size(), true) if _feel_metrics else -1

	var screen_pos := get_viewport().get_mouse_position()
	var world_pos := _screen_to_world(screen_pos)
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
				if _input_feedback_ctrl:
					_input_feedback_ctrl.show_ground_ping(world_pos)
				if _feel_metrics:
					_feel_metrics.mark_feedback(metrics_id)
					_feel_metrics.mark_command(metrics_id)
					_feel_metrics.complete_event(metrics_id, "rally")
				return

	var intent: int = _input_intent_router.resolve_right_click(
		workers_selected or combat_selected,
		buildings_selected,
		workers_selected,
		clicked_ent,
		1,
	)
	action = InputIntentRouterScript.intent_name(intent)

	# Smart context details
	if not clicked_ent.is_empty():
		if action == "attack":
			if _input_feedback_ctrl:
				_input_feedback_ctrl.show_attack_ping(Vector2(float(clicked_ent.px), float(clicked_ent.py)))
		elif action == "gather":
			# Gas geyser without refinery → auto-build refinery on it
			if clicked_ent.resource_type == "gas" and not _has_refinery_on_geyser(clicked_ent.id):
				action = "build"
				_build_type = "refinery"
				_build_mode = true
			else:
				action = "gather"
				if _input_feedback_ctrl:
					_input_feedback_ctrl.show_ground_ping(Vector2(float(clicked_ent.px), float(clicked_ent.py)))

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
						if _input_feedback_ctrl:
							_input_feedback_ctrl.show_ground_ping(Vector2(float(build_x), float(build_y)))
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
		if _input_feedback_ctrl:
			_input_feedback_ctrl.show_ground_ping(world_pos)
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
		if _feel_metrics:
			_feel_metrics.mark_command(metrics_id)
		_record_apm_action()

	# Also emit via EventBus
	if _event_bus and cmds.size() > 0:
		for cmd in cmds:
			_event_bus.emit_command_issued(cmd)

	# Invalid command feedback — selected units but no valid action
	if cmds.is_empty() and not selected_ids.is_empty():
		if _input_feedback_ctrl:
			_input_feedback_ctrl.show_invalid_ping(world_pos)
	if _feel_metrics:
		_feel_metrics.mark_feedback(metrics_id)
		_feel_metrics.complete_event(metrics_id, action if not cmds.is_empty() else "empty")

	# Hide build panel after placing
	if _build_mode and _hud:
		_hud.hide_build_panel()
	_build_mode = false
	_build_type = ""

func _handle_single_click() -> void:
	var wp := _screen_to_world(_drag_start)
	var clicked_ent := _ent_at_world_pos_for_selection(wp)
	var metrics_id: int = _feel_metrics.begin_event("click_selection", 0) if _feel_metrics else -1

	if _selection:
		if clicked_ent.is_empty():
			if not Input.is_key_pressed(KEY_SHIFT):
				_selection.remove_all_selection()
			if _feel_metrics:
				_feel_metrics.mark_feedback(metrics_id)
				_feel_metrics.complete_event(metrics_id, "empty")
			return
		var shift_pressed: bool = Input.is_key_pressed(KEY_SHIFT)
		if not shift_pressed:
			_selection.remove_all_selection()
		elif _selection.selection.has(str(clicked_ent.id)):
			_selection.remove_from_selection(str(clicked_ent.id))
			_record_apm_action()
			if _feel_metrics:
				_feel_metrics.mark_feedback(metrics_id)
				_feel_metrics.complete_event(metrics_id, "toggle_off")
			return
		# Sprint 4: Double-click detection
		var was_double: bool = _selection.handle_click_with_double_select(clicked_ent.id)
		if not was_double:
			# Ctrl+click = select all same type on screen
			if Input.is_key_pressed(KEY_CTRL):
				_selection.select_all_similar_on_screen(clicked_ent.id)
			else:
				_selection.add_to_selection_bulk([clicked_ent.id])
		_record_apm_action()
		if _feel_metrics:
			_feel_metrics.mark_feedback(metrics_id)
			_feel_metrics.complete_event(metrics_id, "success")
	else:
		# Fallback without SelectionManager
		if clicked_ent.is_empty():
			if not Input.is_key_pressed(KEY_SHIFT):
				_selected.clear()
			if _feel_metrics:
				_feel_metrics.mark_feedback(metrics_id)
				_feel_metrics.complete_event(metrics_id, "empty")
			return
		var shift_pressed: bool = Input.is_key_pressed(KEY_SHIFT)
		if not shift_pressed:
			_selected.clear()
		elif _selected.has(clicked_ent.id):
			_selected.erase(clicked_ent.id)
			_record_apm_action()
			if _feel_metrics:
				_feel_metrics.mark_feedback(metrics_id)
				_feel_metrics.complete_event(metrics_id, "toggle_off")
			return
		_selected[clicked_ent.id] = true
		_record_apm_action()
		if _feel_metrics:
			_feel_metrics.mark_feedback(metrics_id)
			_feel_metrics.complete_event(metrics_id, "success")

func _handle_drag_select() -> void:
	var metrics_id: int = _feel_metrics.begin_event("drag_selection", 0) if _feel_metrics else -1
	var tl := _screen_to_world(Vector2(minf(_drag_start.x, _drag_end.x), minf(_drag_start.y, _drag_end.y)))
	var br := _screen_to_world(Vector2(maxf(_drag_start.x, _drag_end.x), maxf(_drag_start.y, _drag_end.y)))
	var rect := Rect2(tl, br - tl)

	var selected_ents := _ents_in_world_rect(rect)
	var own_ids: Array = _selection.filter_owned_in_rect(selected_ents, rect, 1) if _selection else []
	if _selection == null:
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
	if _feel_metrics:
		_feel_metrics.mark_feedback(metrics_id)
		_feel_metrics.complete_event(metrics_id, "success" if not own_ids.is_empty() else "empty")

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

# ─── Formation Fallback ────────────────────────────────────
static func _calc_formation_fallback(center: Vector2, count: int, spacing: float = 0.8) -> Array:
	var positions: Array = []
	if count == 0:
		return positions
	var cols: int = int(ceil(sqrt(float(count))))
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
	if _test_gallery and _test_gallery.is_active():
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
		# Feed height_map to procedural terrain renderer
		if _terrain_renderer and _terrain_renderer.has_method("update_terrain"):
			_terrain_renderer.update_terrain(_height_map)
			_terrain_renderer.visible = _show_elevation
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
	if _hud_overlay:
		_hud_overlay.clear_all_effects()
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
		var params: Dictionary = _sprite_loader.get_visual_params(visual_id, is_building)
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
		var params: Dictionary = _sprite_loader.get_visual_params(visual_id, is_building)
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
	# Event-driven action takes priority over target/HP-delta inference.
	if _combat_visual_controller != null:
		var event_action := _combat_visual_controller.current_action_for(str(e.get("id", "")))
		if event_action != "":
			var ekey: String = _sprite_loader.get_animation_key(event_action, 0)
			if frames.has_animation(ekey):
				return ekey
	var base := "idle"
	if str(e.get("attack_target_id", "")) != "":
		base = "attack"
	elif not bool(e.get("is_idle", true)):
		base = "moving"
	var key: String = _sprite_loader.get_animation_key(base, 0)
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

	# ─── Dispatch authoritative combat events to the visual controller ───
	if _combat_visual_controller != null:
		_combat_visual_controller.process_combat_events(state.get("combat_events", []))

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
	# In Test Mode isolation: force all fog alpha to 0.0 so fog is invisible.
	var _test_iso: bool = _test_gallery != null and _test_gallery.is_active()
	var tile_count := _fog_w * _fog_h
	if _fog_alpha.size() != tile_count:
		_fog_alpha.resize(tile_count)
		if _test_iso:
			for i in range(tile_count):
				_fog_alpha[i] = 0.0
		else:
			for i in range(tile_count):
				var initial: int = _fog_tiles[i] if i < _fog_tiles.size() else 0
				match initial:
					2: _fog_alpha[i] = 0.0
					1: _fog_alpha[i] = 0.50
					_: _fog_alpha[i] = 0.88
	if _test_iso:
		for i in range(tile_count):
			_fog_alpha[i] = 0.0
	else:
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

	# Push fog data to HUDOverlayRenderer
	if _hud_overlay:
		_hud_overlay.set_fog_data(_fog_w, _fog_h, _fog_alpha)

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
				if _hud_overlay:
					_hud_overlay.add_damage_float("-%d" % int(dmg), Vector2(e.px, e.py - 1.2), int(e.owner))
			if LEGACY_HP_DELTA_VFX_ENABLED and _vfx_manager:
				_vfx_manager.spawn_hit(_visual_unit_name(e), e.owner, Vector2(e.px, e.py), dmg, _vfx_profile_for(e))
				_emit_attack_indicator(Vector2(e.px, e.py))

	# ─── Attack flash detection: delegate to HUD overlay ───
	if _hud_overlay:
		for e in _ents:
			var eid_str: String = e.id
			var cur_target: String = str(e.get("attack_target_id", ""))
			var prev_target: String = str(_prev_attack_targets.get(eid_str, ""))
			if cur_target != "" and cur_target != prev_target:
				_hud_overlay.add_attack_flash(eid_str)
			var cooldown: float = _to_f(e.get("attack_cooldown"), 0.0)
			var prev_cooldown: float = _to_f(_prev_hp.get(eid_str + "_cd", 0.0), 0.0)
			if cooldown > 0.0 and prev_cooldown <= 0.0 and cur_target != "":
				_hud_overlay.add_attack_flash(eid_str)

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
				# Also add death explosion effect to HUD overlay for canvas drawing
				if _hud_overlay:
					_hud_overlay.add_death_effect(death_pos, death_owner, death_type, _hud_overlay._team_color(death_owner))

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
	# TerrainRenderer (child Node2D, z_index=-5) draws the procedural terrain.
	var co := Vector2.ZERO
	_draw_map_background(co)
	# Elevation is now handled by TerrainRenderer child node — no _draw_elevation here
	_draw_grid(co)
	_draw_entities(co)
	_draw_pylon_power_range(co)
	_draw_fog_of_war(co)
	if _hud_overlay:
		_hud_overlay.draw_all(self)
	if _input_feedback_ctrl:
		_input_feedback_ctrl.draw_all(self)
	if _test_gallery:
		_test_gallery.draw_labels(self)

func _draw_map_background(_co: Vector2) -> void:
	# Procedural terrain renderer (child TerrainRenderer, z_index=-5) handles
	# the real terrain.  This draws a dark fallback rect beneath everything
	# so the map area is always defined even before height_map data arrives.
	var map_rect := Rect2(Vector2.ZERO, Vector2(_map_w, _map_h))
	draw_rect(map_rect, Color(0.15, 0.18, 0.12, 1.0))

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
	# Bug 6 fix: early-out when Test Mode is active (fog should be invisible)
	if _test_gallery != null and _test_gallery.is_active():
		return
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
					if abs(n_alpha - base_alpha) > 0.1:
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
		var is_generated_resource_preview: bool = _test_gallery != null and _test_gallery.is_active() and str(e.get("type", "")) == "resource" and str(e.get("generated_asset_id", "")) != ""
		var is_generated_unit_preview: bool = _test_gallery != null and _test_gallery.is_active() and str(e.get("type", "")) == "unit" and str(e.get("generated_asset_id", "")) != ""
		var is_resource: bool = str(e.get("type", "")) == "resource" and not is_generated_resource_preview
		var has_unit_override := _has_unit_region_override(e)
		var node: Node2D = _sprite_pool.get(eid, null)
		var needs_animated := not is_building and not is_resource and not has_unit_override and not is_generated_resource_preview
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
				var atlas: Texture2D = _sprite_loader.get_building_atlas(visual_id) if _sprite_loader else null
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
		elif is_resource:
			var sprite := node as Sprite2D
			var resource_type: String = str(e.get("resource_type", ""))
			var tex: Texture2D = null
			if resource_type == "mineral":
				var mineral_paths: Array = _resource_visual_cfg.get("mineral_textures", [])
				if mineral_paths.size() > 0:
					var idx: int = absi(hash(eid)) % mineral_paths.size()
					var chosen_path: String = str(mineral_paths[idx])
					tex = _resource_textures.get(chosen_path, null)
					if tex == null:
						tex = _load_resource_texture(chosen_path)
			elif resource_type == "gas":
				var gas_path: String = str(_resource_visual_cfg.get("gas_texture", ""))
				if gas_path != "":
					tex = _resource_textures.get(gas_path, null)
					if tex == null:
						tex = _load_resource_texture(gas_path)
			if tex:
				sprite.texture = tex
				sprite.region_enabled = false
				var res_scale: float = float(_resource_visual_cfg.get("resource_scale", 0.022))
				sprite.scale = Vector2(res_scale, res_scale)
				sprite.visible = true
				sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_DISABLED
				sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			else:
				sprite.texture = null
				sprite.visible = false
		elif is_generated_resource_preview:
			var sprite := node as Sprite2D
			var asset_id := str(e.get("generated_asset_id", ""))
			var atlas: Texture2D = _sprite_loader.get_generated_asset_atlas(asset_id, "resource", true) if _sprite_loader else null
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
			# ── Construction ghost: semi-transparent breathing pulse for buildings under construction ──
			var is_constructing: bool = bool(e.get("is_constructing", false)) if e.get("is_constructing") != null else false
			if is_building and is_constructing:
				# Remove from fade dict if it was fading (building got re-selected for construction)
				_construction_fade.erase(eid)
				var ghost_alpha: float = float(_construction_cfg.get("ghost_alpha", 0.45))
				var breath_speed: float = float(_construction_cfg.get("breath_speed", 3.0))
				var breath_amp: float = float(_construction_cfg.get("breath_amplitude", 0.1))
				var breath_alpha: float = (ghost_alpha - breath_amp) + breath_amp * sin(_game_time * breath_speed)
				node.modulate = Color(1.0, 1.0, 1.0, breath_alpha)
			elif _construction_fade.has(eid):
				# Building completed — use fading alpha (lerped in _process)
				var fade_alpha: float = float(_construction_fade[eid])
				node.modulate = Color(1.0, 1.0, 1.0, fade_alpha)
			else:
				# Fully visible or not a constructing building — start fade if just completed
				if is_building and not is_constructing and _sprite_pool.has(eid):
					var prev_ent: Dictionary = _entity_cache_by_id.get(eid, {})
					var was_constructing: bool = bool(prev_ent.get("is_constructing", false)) if prev_ent.get("is_constructing") != null else false
					if was_constructing:
						# Transition: building just completed, start fade from current alpha
						var start_alpha: float = node.modulate.a if node.modulate.a < 1.0 else float(_construction_cfg.get("ghost_alpha", 0.45))
						_construction_fade[eid] = start_alpha
						node.modulate = Color(1.0, 1.0, 1.0, start_alpha)
					else:
						node.modulate = Color.WHITE
				else:
					node.modulate = Color.WHITE
		node.position = Vector2(e.px, e.py)

	# Hide sprites for entities that no longer exist
	for eid in _sprite_pool:
		if not active_ids.has(eid):
			_sprite_pool[eid].visible = false
			_construction_fade.erase(eid)

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

		# Resources are now rendered via Sprite2D in _update_entity_sprites()
		# using SC1 textures — no fallback color blocks needed

	# Attack / move target lines
	for e in _ents:
		if e.owner != 1 and not (_test_gallery and _test_gallery.is_active()):
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
	if abs(origin_x) > 2.0:
		_jitter_count += 1
		_total_jitter_px += abs(origin_x)
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


func _toggle_elevation() -> void:
	_show_elevation = not _show_elevation
	if _terrain_renderer:
		_terrain_renderer.set_visible_flag(_show_elevation)
	if _test_gallery:
		_test_gallery.toggle_elevation()

# ── TestModeGallery signal handlers ──

func _set_test_mode_isolation(enabled: bool) -> void:
	if _hud:
		_hud.visible = not enabled
	if _hud_overlay:
		_hud_overlay.set_test_mode_isolation(enabled)
	if _mm_rect_node:
		_mm_rect_node.visible = not enabled
	if _mm_panel_node:
		_mm_panel_node.visible = not enabled
	if _apm_label:
		_apm_label.visible = not enabled
	if _terrain_renderer:
		_terrain_renderer.visible = not enabled  # hide elevation debug
	# Bug 5 fix: toggle TestModeUIController visibility with test mode
	if _test_ui_ctrl:
		_test_ui_ctrl.visible = enabled
	# Force fog invisible in test mode by zeroing fog alpha
	if enabled:
		_fog_alpha.clear()
		for i in range(_fog_tiles.size()):
			_fog_alpha.append(0.0)
	queue_redraw()

func _on_test_entities_rebuilt(new_ents: Array) -> void:
	_ents = new_ents
	_update_entity_sprites()
	queue_redraw()

func _on_test_state_changed() -> void:
	var is_active: bool = _test_gallery != null and _test_gallery.is_active()
	# Bug 2 fix: save game state BEFORE entering test mode isolation
	if is_active and _test_gallery:
		_test_gallery.save_state(_ents, _player_races, _fog_tiles, _fog_w, _fog_h)
	_set_test_mode_isolation(is_active)
	if _test_gallery and not _test_gallery.is_active():
		var saved: Dictionary = _test_gallery.get_saved_state()
		if not saved.is_empty():
			_ents = Array(saved.get("ents", []))
			_player_races = Dictionary(saved.get("player_races", {}))
			_fog_tiles = PackedInt32Array(saved.get("fog_tiles", PackedInt32Array()))
			_fog_w = int(saved.get("fog_w", 0))
			_fog_h = int(saved.get("fog_h", 0))
			# Bug 3 fix: rebuild _fog_alpha from restored _fog_tiles
			var tile_count := _fog_w * _fog_h
			_fog_alpha.resize(tile_count)
			for i in range(tile_count):
				var fog_val: int = _fog_tiles[i] if i < _fog_tiles.size() else 0
				match fog_val:
					0: _fog_alpha[i] = 0.92
					1: _fog_alpha[i] = 0.55
					2: _fog_alpha[i] = 0.0
					_: _fog_alpha[i] = 0.92
	# Bug 4 fix: toggle TestModeLabelLayer visibility with test mode
	if _test_label_layer:
		if is_active:
			_test_label_layer.set_labels(_test_gallery.get_screen_labels())
			_test_label_layer.visible = true
		else:
			_test_label_layer.visible = false
	_update_entity_sprites()
	queue_redraw()


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
