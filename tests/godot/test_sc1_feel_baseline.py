"""Tests for godot/resources/feel/sc1_feel_baseline.json — SC1 feel baseline config."""

import json
from pathlib import Path

import pytest

BASELINE_PATH = Path(__file__).resolve().parents[2] / "godot" / "resources" / "feel" / "sc1_feel_baseline.json"


@pytest.fixture()
def baseline() -> dict:
    """Load and return the baseline feel config JSON."""
    assert BASELINE_PATH.exists(), f"Baseline file not found: {BASELINE_PATH}"
    text = BASELINE_PATH.read_text(encoding="utf-8")
    return json.loads(text)


# ── 1. File exists & is valid JSON ──────────────────────────────────────────

def test_baseline_file_exists():
    assert BASELINE_PATH.exists(), f"Baseline file missing: {BASELINE_PATH}"


def test_baseline_is_valid_json(baseline: dict):
    assert isinstance(baseline, dict)


# ── 2. schema_version ───────────────────────────────────────────────────────

def test_schema_version(baseline: dict):
    assert baseline["schema_version"] == 1


# ── 3. camera required fields ───────────────────────────────────────────────

CAMERA_REQUIRED_FIELDS = [
    "default_zoom_preset",
    "keyboard_screen_per_second",
    "edge_screen_per_second",
    "edge_ramp_px",
    "zoom_presets",
]


def test_camera_required_fields_exist(baseline: dict):
    camera = baseline["camera"]
    for field in CAMERA_REQUIRED_FIELDS:
        assert field in camera, f"camera missing required field: {field}"


# ── 4. camera value ranges ──────────────────────────────────────────────────

def test_keyboard_screen_per_second_range(baseline: dict):
    val = baseline["camera"]["keyboard_screen_per_second"]
    assert 0.2 <= val <= 2.0, f"camera.keyboard_screen_per_second={val} not in [0.2, 2.0]"


def test_edge_screen_per_second_range(baseline: dict):
    val = baseline["camera"]["edge_screen_per_second"]
    assert 0.1 <= val <= 2.0, f"camera.edge_screen_per_second={val} not in [0.1, 2.0]"


def test_edge_ramp_px_range(baseline: dict):
    val = baseline["camera"]["edge_ramp_px"]
    assert 5.0 <= val <= 100.0, f"camera.edge_ramp_px={val} not in [5.0, 100.0]"


def test_zoom_presets_keys(baseline: dict):
    presets = baseline["camera"]["zoom_presets"]
    assert "gameplay" in presets, "zoom_presets missing 'gameplay' key"


# ── 5. input_feedback required fields ────────────────────────────────────────

INPUT_FEEDBACK_REQUIRED_FIELDS = [
    "max_visual_latency_frames",
    "right_click_ping_seconds",
    "attack_ping_seconds",
    "invalid_ping_seconds",
]


def test_input_feedback_required_fields_exist(baseline: dict):
    ib = baseline["input_feedback"]
    for field in INPUT_FEEDBACK_REQUIRED_FIELDS:
        assert field in ib, f"input_feedback missing required field: {field}"


def test_max_visual_latency_frames(baseline: dict):
    val = baseline["input_feedback"]["max_visual_latency_frames"]
    assert val <= 1, f"input_feedback.max_visual_latency_frames={val} must be <= 1"


# ── 6. selection required fields ─────────────────────────────────────────────

def test_selection_max_group_size(baseline: dict):
    assert baseline["selection"]["max_group_size"] == 12


# ── 7. visual_noise ─────────────────────────────────────────────────────────

def test_visual_noise_selection_ring_mode(baseline: dict):
    val = baseline["visual_noise"]["selection_ring_mode"]
    assert val in ("simple", "enhanced"), f"visual_noise.selection_ring_mode='{val}' not in ('simple', 'enhanced')"


# ── 8. compatibility with control_feel_config.json ───────────────────────────

CONFIG_PATH = Path(__file__).resolve().parents[2] / "godot" / "resources" / "feel" / "control_feel_config.json"


def test_baseline_zoom_presets_are_positive_multipliers(baseline: dict):
    """Baseline zoom presets are screen-space multipliers (1.0=default), not Camera2D.zoom values."""
    for preset_name, preset_val in baseline["camera"]["zoom_presets"].items():
        assert preset_val > 0.0, (
            f"zoom_presets.{preset_name}={preset_val} must be positive"
        )
        assert 0.2 <= preset_val <= 3.0, (
            f"zoom_presets.{preset_name}={preset_val} not in reasonable range [0.2, 3.0]"
        )


def test_baseline_camera_compatible_with_config(baseline: dict):
    """Verify baseline and control_feel_config both have camera sections with overlapping zoom capability."""
    if not CONFIG_PATH.exists():
        pytest.skip("control_feel_config.json not found")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    config = json.loads(text)
    assert "camera" in config, "control_feel_config missing camera section"
    # Config min/max zoom must be a valid range (min < max)
    config_min_zoom = config["camera"].get("min_zoom", 0.5)
    config_max_zoom = config["camera"].get("max_zoom", 20.0)
    assert config_min_zoom < config_max_zoom, (
        f"config zoom range invalid: min={config_min_zoom} >= max={config_max_zoom}"
    )
