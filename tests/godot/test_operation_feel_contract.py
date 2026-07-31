from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[2]
GAME_VIEW = ROOT / "godot/scripts/game_view.gd"
CAMERA_CONTROLLER = ROOT / "godot/scripts/camera_controller.gd"
INPUT_FEEDBACK = ROOT / "godot/scripts/input_feedback_controller.gd"
FEEL_CONFIG = ROOT / "godot/resources/feel/control_feel_config.json"
INTENT_ROUTER = ROOT / "godot/scripts/input_intent_router.gd"
SELECTION_MANAGER = ROOT / "godot/scripts/selection_manager.gd"
METRICS_RECORDER = ROOT / "godot/scripts/feel_metrics_recorder.gd"
PROJECT_FILE = ROOT / "godot/project.godot"


def test_game_view_routes_plain_number_to_group_recall() -> None:
    text = GAME_VIEW.read_text(encoding="utf-8")
    assert "func _handle_control_group_key" in text
    assert "_selection.select_hotkey_group(group_idx)" in text


def test_ground_right_click_is_not_attack_nearest() -> None:
    text = GAME_VIEW.read_text(encoding="utf-8")
    assert 'action = "attack_nearest"' not in text


def test_runtime_does_not_load_baseline_as_config() -> None:
    for path in (CAMERA_CONTROLLER, INPUT_FEEDBACK):
        text = path.read_text(encoding="utf-8")
        assert "_load_baseline_config" not in text


def test_input_intent_router_is_wired_into_game_view() -> None:
    assert INTENT_ROUTER.exists()
    router_text = INTENT_ROUTER.read_text(encoding="utf-8")
    game_text = GAME_VIEW.read_text(encoding="utf-8")
    assert "class_name InputIntentRouter" in router_text
    assert "InputIntentRouterScript" in game_text
    assert "resolve_right_click" in game_text


def test_attack_move_has_explicit_targeting_state() -> None:
    text = GAME_VIEW.read_text(encoding="utf-8")
    assert "_attack_move_targeting" in text
    assert "_handle_attack_move_click" in text
    assert "show_attack_move_ping" in text


def test_ui_hit_testing_precedes_attack_move_targeting() -> None:
    text = GAME_VIEW.read_text(encoding="utf-8")
    input_block = text[text.index("func _input("):text.index("func _handle_control_group_key")]
    hud_index = input_block.index("_hud.get_global_rect().has_point")
    attack_move_index = input_block.index("_handle_attack_move_click")
    assert hud_index < attack_move_index


def test_camera_uses_visible_world_width_presets() -> None:
    config = json.loads(FEEL_CONFIG.read_text(encoding="utf-8"))
    camera = config["camera"]
    assert camera["gameplay_visible_world_width"] > 0
    assert camera["inspection_visible_world_width"] > 0
    assert camera["overview_visible_world_width"] > camera["gameplay_visible_world_width"]
    text = CAMERA_CONTROLLER.read_text(encoding="utf-8")
    assert "func calculate_zoom_for_visible_width" in text
    assert "dynamic_min" not in text


def test_gameplay_visible_width_is_reachable_at_full_hd() -> None:
    config = json.loads(FEEL_CONFIG.read_text(encoding="utf-8"))
    camera = config["camera"]
    required_zoom = 1920.0 / camera["gameplay_visible_world_width"]
    assert camera["min_zoom"] <= required_zoom <= camera["max_zoom"]


def test_camera_map_size_is_set_before_setup() -> None:
    text = GAME_VIEW.read_text(encoding="utf-8")
    size_index = text.index("_cam_ctrl.set_map_size(_map_w, _map_h)")
    setup_index = text.index("_cam_ctrl.setup(_camera)")
    assert size_index < setup_index


def test_selection_manager_owns_pointer_release_classification() -> None:
    text = SELECTION_MANAGER.read_text(encoding="utf-8")
    assert "func classify_pointer_release" in text
    assert "func click_hit_radius_world" in text
    assert "func choose_best_hit" in text
    assert "func filter_owned_in_rect" in text
    game_text = GAME_VIEW.read_text(encoding="utf-8")
    assert "_selection.classify_pointer_release(_drag_start, _drag_end)" in game_text
    assert "_drag_start.distance_to(_drag_end) < 5.0" not in game_text


def test_single_click_uses_manifest_selection_radius() -> None:
    text = GAME_VIEW.read_text(encoding="utf-8")
    assert "func _ent_at_world_pos_for_selection" in text
    single_click = text[text.index("func _handle_single_click"):text.index("func _handle_drag_select")]
    assert "_ent_at_world_pos_for_selection" in single_click
    assert "_visual_radius" in text[text.index("func _ent_at_world_pos_for_selection"):]


def test_shift_click_toggles_existing_selection() -> None:
    text = GAME_VIEW.read_text(encoding="utf-8")
    single_click = text[text.index("func _handle_single_click"):text.index("func _handle_drag_select")]
    assert "_selection.remove_from_selection" in single_click


def test_feel_metrics_recorder_is_default_off_and_wired() -> None:
    assert METRICS_RECORDER.exists()
    recorder_text = METRICS_RECORDER.read_text(encoding="utf-8")
    assert "class_name FeelMetricsRecorder" in recorder_text
    assert "user://feel_metrics.jsonl" in recorder_text
    assert "func begin_event" in recorder_text
    assert "func mark_feedback" in recorder_text
    assert "func mark_command" in recorder_text
    project_text = PROJECT_FILE.read_text(encoding="utf-8")
    assert "feel_metrics_enabled=false" in project_text
    game_text = GAME_VIEW.read_text(encoding="utf-8")
    assert "FeelMetricsRecorderScript" in game_text
    assert "_feel_metrics.begin_event" in game_text
    drag_block = game_text[game_text.index("func _handle_drag_select"):game_text.index("func _handle_train")]
    assert 'begin_event("drag_selection"' in drag_block


def test_feel_metrics_exposes_gate_summary() -> None:
    text = METRICS_RECORDER.read_text(encoding="utf-8")
    for metric in (
        "input_to_feedback_frames_p95",
        "empty_command_rate",
        "control_group_recall_success",
    ):
        assert metric in text
