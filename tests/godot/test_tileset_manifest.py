"""Tests for godot/resources/terrain/tileset_manifest.json — Phase 4 SC1 tileset."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "godot" / "resources" / "terrain" / "tileset_manifest.json"
FEEL_CONFIG_PATH = ROOT / "godot" / "resources" / "feel" / "control_feel_config.json"


def _load_json(path: Path) -> dict:
    assert path.exists(), f"File not found: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ── tileset_manifest.json ────────────────────────────────────


def test_tileset_manifest_exists() -> None:
    assert MANIFEST_PATH.exists(), f"tileset_manifest.json missing: {MANIFEST_PATH}"


def test_tileset_manifest_is_valid_json() -> None:
    data = _load_json(MANIFEST_PATH)
    assert isinstance(data, dict)


REQUIRED_MANIFEST_KEYS = [
    "tileset_id",
    "tile_size_px",
    "atlas",
    "tile_index_to_rect",
    "default_tile",
]


def test_tileset_manifest_has_required_keys() -> None:
    data = _load_json(MANIFEST_PATH)
    for key in REQUIRED_MANIFEST_KEYS:
        assert key in data, f"tileset_manifest missing key: {key}"


def test_tileset_id_is_string() -> None:
    data = _load_json(MANIFEST_PATH)
    assert isinstance(data["tileset_id"], str)
    assert len(data["tileset_id"]) > 0


def test_tile_size_px_is_positive_int() -> None:
    data = _load_json(MANIFEST_PATH)
    val = data["tile_size_px"]
    assert isinstance(val, int)
    assert val > 0


def test_atlas_is_res_path() -> None:
    data = _load_json(MANIFEST_PATH)
    atlas = data["atlas"]
    assert isinstance(atlas, str)
    assert atlas.startswith("res://"), f"atlas path should start with res://: {atlas}"


def test_tile_index_to_rect_is_dict() -> None:
    """tile_index_to_rect may be empty (no SC1 tiles extracted yet)."""
    data = _load_json(MANIFEST_PATH)
    assert isinstance(data["tile_index_to_rect"], dict)


def test_tile_index_to_rect_entries_are_valid_when_present() -> None:
    """If tile_index_to_rect has entries, each must be [x, y, w, h]."""
    data = _load_json(MANIFEST_PATH)
    mapping = data["tile_index_to_rect"]
    for key, val in mapping.items():
        assert isinstance(val, list), f"key {key} value is not a list: {val}"
        assert len(val) == 4, f"key {key} rect length != 4: {val}"
        assert all(isinstance(v, (int, float)) for v in val), f"key {key} rect non-numeric: {val}"


def test_default_tile_is_int() -> None:
    data = _load_json(MANIFEST_PATH)
    assert isinstance(data["default_tile"], int)


# ── control_feel_config.json terrain_mode ───────────────────


def test_feel_config_has_terrain_mode() -> None:
    config = _load_json(FEEL_CONFIG_PATH)
    assert "terrain_mode" in config, "control_feel_config missing terrain_mode"


def test_terrain_mode_is_valid_value() -> None:
    config = _load_json(FEEL_CONFIG_PATH)
    val = config["terrain_mode"]
    assert val in ("height_debug", "sc1_tileset"), f"invalid terrain_mode: {val}"


# ── fog_renderer.gd three-state alpha values ────────────────


def test_fog_renderer_has_three_state_alphas() -> None:
    """Verify fog_renderer.gd contains the three-state alpha constants."""
    fog_path = ROOT / "godot" / "scripts" / "fog_renderer.gd"
    assert fog_path.exists(), f"fog_renderer.gd missing: {fog_path}"
    text = fog_path.read_text(encoding="utf-8")

    # Check base alpha values for three states
    assert "0.92" in text, "fog_renderer missing unexplored alpha (0.92)"
    assert "0.55" in text, "fog_renderer missing explored alpha (0.55)"

    # Check blend_factor reduced from 0.35 to 0.15
    assert "0.15" in text, "fog_renderer missing reduced blend_factor (0.15)"
    # Ensure old 0.35 is NOT present
    assert "0.35" not in text, "fog_renderer still has old blend_factor 0.35"

    # Check three-state color values
    assert "0.0, 0.0, 0.0" in text, "fog_renderer missing unexplored black color"


# ── sc1_tileset_renderer.gd exists and has API ─────────────


def test_sc1_tileset_renderer_exists() -> None:
    renderer_path = ROOT / "godot" / "scripts" / "sc1_tileset_renderer.gd"
    assert renderer_path.exists(), f"sc1_tileset_renderer.gd missing: {renderer_path}"


def test_sc1_tileset_renderer_has_required_api() -> None:
    renderer_path = ROOT / "godot" / "scripts" / "sc1_tileset_renderer.gd"
    text = renderer_path.read_text(encoding="utf-8")

    # Public API
    assert "func update_terrain" in text, "sc1_tileset_renderer missing update_terrain()"
    assert "func clear" in text, "sc1_tileset_renderer missing clear()"
    assert "func set_visible_flag" in text, "sc1_tileset_renderer missing set_visible_flag()"

    # z_index
    assert "z_index = -5" in text, "sc1_tileset_renderer missing z_index = -5"

    # nearest filtering
    assert "TEXTURE_FILTER_NEAREST" in text, "sc1_tileset_renderer missing nearest filtering"

    # Fallback
    assert "_fallback_texture" in text, "sc1_tileset_renderer missing fallback texture"

    # Manifest loading
    assert "tileset_manifest.json" in text, "sc1_tileset_renderer missing manifest path"
    assert "tile_index_to_rect" in text, "sc1_tileset_renderer missing tile_index_to_rect"


# ── game_view.gd terrain mode dispatch ─────────────────────


def test_game_view_references_both_renderers() -> None:
    gv_path = ROOT / "godot" / "scripts" / "game_view.gd"
    assert gv_path.exists(), f"game_view.gd missing: {gv_path}"
    text = gv_path.read_text(encoding="utf-8")

    assert "SC1TilesetRendererScript" in text, "game_view missing SC1TilesetRenderer preload"
    assert "TerrainRendererScript" in text, "game_view missing TerrainRendererScript preload"
    assert "sc1_tileset" in text, "game_view missing sc1_tileset terrain_mode branch"
