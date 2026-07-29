"""Tests for godot/resources/feel/control_feel_config.json — Phase 1 unified feel config."""

import json
import re
from pathlib import Path

import pytest

CONFIG_PATH = Path(__file__).resolve().parents[2] / "godot" / "resources" / "feel" / "control_feel_config.json"

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@pytest.fixture()
def config() -> dict:
    """Load and return the feel config JSON."""
    assert CONFIG_PATH.exists(), f"Config file not found: {CONFIG_PATH}"
    text = CONFIG_PATH.read_text(encoding="utf-8")
    return json.loads(text)


# ── 1. File exists & is valid JSON ──────────────────────────────────────────

def test_config_file_exists():
    assert CONFIG_PATH.exists(), f"Config file missing: {CONFIG_PATH}"


def test_config_is_valid_json(config: dict):
    assert isinstance(config, dict)


# ── 2. schema_version ──────────────────────────────────────────────────────

def test_schema_version(config: dict):
    assert config["schema_version"] == 1


# ── 3. camera required fields ───────────────────────────────────────────────

CAMERA_REQUIRED_FIELDS = [
    "keyboard_speed",
    "edge_scroll_margin",
    "edge_scroll_speed",
    "min_zoom",
    "max_zoom",
    "zoom_step",
    "zoom_lerp_speed",
]


def test_camera_required_fields_exist(config: dict):
    camera = config["camera"]
    for field in CAMERA_REQUIRED_FIELDS:
        assert field in camera, f"camera missing required field: {field}"


# ── 4. camera value ranges ──────────────────────────────────────────────────

CAMERA_RANGES = {
    "keyboard_speed": (100.0, 2000.0),
    "edge_scroll_margin": (5.0, 100.0),
    "min_zoom": (1.0, 20.0),
    "max_zoom": (40.0, 128.0),
    "zoom_step": (0.5, 12.0),
    "zoom_lerp_speed": (1.0, 30.0),
}


@pytest.mark.parametrize("field,lo,hi", [
    ("keyboard_speed", 100.0, 2000.0),
    ("edge_scroll_margin", 5.0, 100.0),
    ("min_zoom", 1.0, 20.0),
    ("max_zoom", 40.0, 128.0),
    ("zoom_step", 0.5, 12.0),
    ("zoom_lerp_speed", 1.0, 30.0),
], ids=list(CAMERA_RANGES.keys()))
def test_camera_value_ranges(config: dict, field: str, lo: float, hi: float):
    val = config["camera"][field]
    assert lo <= val <= hi, f"camera.{field}={val} not in [{lo}, {hi}]"


def test_camera_max_zoom_greater_than_min_zoom(config: dict):
    assert config["camera"]["max_zoom"] > config["camera"]["min_zoom"]


# ── 5. selection required fields ────────────────────────────────────────────

SELECTION_REQUIRED_FIELDS = [
    "drag_threshold_px",
    "click_slop_px",
    "double_click_interval",
    "max_selection_size",
]


def test_selection_required_fields_exist(config: dict):
    sel = config["selection"]
    for field in SELECTION_REQUIRED_FIELDS:
        assert field in sel, f"selection missing required field: {field}"


# ── 6. selection value ranges ───────────────────────────────────────────────

@pytest.mark.parametrize("field,lo,hi", [
    ("drag_threshold_px", 1.0, 20.0),
    ("click_slop_px", 1.0, 20.0),
    ("double_click_interval", 0.1, 1.0),
    ("max_selection_size", 1, 200),
], ids=["drag_threshold_px", "click_slop_px", "double_click_interval", "max_selection_size"])
def test_selection_value_ranges(config: dict, field: str, lo, hi):
    val = config["selection"][field]
    assert lo <= val <= hi, f"selection.{field}={val} not in [{lo}, {hi}]"


# ── 7. command_feedback required fields ─────────────────────────────────────

COMMAND_FEEDBACK_REQUIRED_FIELDS = [
    "ground_ping_duration",
    "ground_ping_color",
    "attack_ping_duration",
    "attack_ping_color",
    "invalid_ping_duration",
    "invalid_ping_color",
]


def test_command_feedback_required_fields_exist(config: dict):
    cf = config["command_feedback"]
    for field in COMMAND_FEEDBACK_REQUIRED_FIELDS:
        assert field in cf, f"command_feedback missing required field: {field}"


# ── 8. control_group_feedback fields ────────────────────────────────────────

CONTROL_GROUP_FEEDBACK_REQUIRED_FIELDS = [
    "assign_flash_duration",
    "empty_group_hint_duration",
]


def test_control_group_feedback_fields_exist(config: dict):
    cg = config["control_group_feedback"]
    for field in CONTROL_GROUP_FEEDBACK_REQUIRED_FIELDS:
        assert field in cg, f"control_group_feedback missing field: {field}"


# ── 9. all colors are #RRGGBB ───────────────────────────────────────────────

def test_all_colors_are_hex_rrggbb(config: dict):
    """Every value whose key ends with '_color' must match #RRGGBB format."""
    color_fields = [
        ("command_feedback", "ground_ping_color"),
        ("command_feedback", "attack_ping_color"),
        ("command_feedback", "invalid_ping_color"),
    ]
    for section, field in color_fields:
        color = config[section][field]
        assert HEX_COLOR_RE.match(color), (
            f"{section}.{field}='{color}' does not match #RRGGBB"
        )


# ── 10. test_mode config section ───────────────────────────────────────────

TEST_MODE_REQUIRED_FIELDS = [
    "hide_game_hud",
    "force_fog_visible",
    "neutral_team_tint",
    "show_minimap",
    "show_world_grid",
]


def test_test_mode_config_exists(config: dict) -> None:
    """The test_mode section must exist with all required boolean fields."""
    assert "test_mode" in config, "Config missing 'test_mode' section"
    test_mode = config["test_mode"]
    for field in TEST_MODE_REQUIRED_FIELDS:
        assert field in test_mode, f"test_mode missing required field: {field}"


def test_test_mode_config_values(config: dict) -> None:
    """test_mode values must match the spec (booleans)."""
    test_mode = config["test_mode"]
    assert test_mode["hide_game_hud"] is True
    assert test_mode["force_fog_visible"] is True
    assert test_mode["neutral_team_tint"] is True
    assert test_mode["show_minimap"] is False
    assert test_mode["show_world_grid"] is False


def test_gallery_has_tint_toggle() -> None:
    """test_mode_gallery.gd must contain tint toggle UI code."""
    gallery_path = Path(__file__).resolve().parents[2] / "godot" / "scripts" / "test_mode_gallery.gd"
    text = gallery_path.read_text(encoding="utf-8")
    assert "_tint_btn" in text or "_toggle_tint" in text, \
        "Gallery missing tint toggle button variable or callback"
    assert "neutral_team_tint" in text, \
        "Gallery missing 'neutral_team_tint' key in entity data"


def test_entity_visual_respects_neutral_tint() -> None:
    """entity_visual.gd must check for neutral_team_tint flag."""
    visual_path = Path(__file__).resolve().parents[2] / "godot" / "scripts" / "entity_visual.gd"
    text = visual_path.read_text(encoding="utf-8")
    assert "neutral_team_tint" in text, \
        "EntityVisual does not check for neutral_team_tint flag"
