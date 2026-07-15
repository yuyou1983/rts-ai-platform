"""Tests for visual class scale calibration — Phase 2.

Validates:
- Worker render_scale difference ≤ 20%
- Townhall selection_radius difference ≤ 25%
- Building health_bar_offset must exist
- Building footprint must exist
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "godot" / "resources" / "presentation_manifest.json"
FEEL_PATH = ROOT / "godot" / "resources" / "feel" / "control_feel_config.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_feel() -> dict:
    return json.loads(FEEL_PATH.read_text(encoding="utf-8"))


# ── Worker render_scale calibration ─────────────────────────────────────────

WORKER_IDS = ["SCV", "Drone", "Probe"]
MAX_WORKER_RS_SPREAD_PCT = 20.0


def test_worker_render_scale_within_20pct() -> None:
    """The three workers' render_scale must not differ by more than 20%."""
    manifest = _load_manifest()
    uv = manifest.get("unit_visuals", {})

    rs_values: list[float] = []
    for wid in WORKER_IDS:
        assert wid in uv, f"Worker {wid} not in unit_visuals"
        rs = float(uv[wid].get("render_scale", 0))
        assert rs > 0, f"Worker {wid} has non-positive render_scale"
        rs_values.append(rs)

    max_rs = max(rs_values)
    min_rs = min(rs_values)
    spread_pct = (max_rs - min_rs) / min_rs * 100.0
    assert spread_pct <= MAX_WORKER_RS_SPREAD_PCT, (
        f"Worker render_scale spread {spread_pct:.1f}% > {MAX_WORKER_RS_SPREAD_PCT}% "
        f"(values: {dict(zip(WORKER_IDS, rs_values))})"
    )


# ── Townhall selection_radius calibration ─────────────────────────────────────

TOWNHALL_IDS = ["CommandCenter", "Hatchery", "Nexus"]
MAX_TOWNHALL_SR_SPREAD_PCT = 25.0


def test_townhall_selection_radius_within_25pct() -> None:
    """The three townhalls' selection_radius must not differ by more than 25%."""
    manifest = _load_manifest()
    bv = manifest.get("building_visuals", {})

    sr_values: list[float] = []
    for tid in TOWNHALL_IDS:
        assert tid in bv, f"Townhall {tid} not in building_visuals"
        sr = float(bv[tid].get("selection_radius", 0))
        assert sr > 0, f"Townhall {tid} has non-positive selection_radius"
        sr_values.append(sr)

    max_sr = max(sr_values)
    min_sr = min(sr_values)
    spread_pct = (max_sr - min_sr) / min_sr * 100.0
    assert spread_pct <= MAX_TOWNHALL_SR_SPREAD_PCT, (
        f"Townhall selection_radius spread {spread_pct:.1f}% > {MAX_TOWNHALL_SR_SPREAD_PCT}% "
        f"(values: {dict(zip(TOWNHALL_IDS, sr_values))})"
    )


# ── Building health_bar_offset must exist ─────────────────────────────────────


def test_all_buildings_have_health_bar_offset() -> None:
    """Every building_visuals entry must have a health_bar_offset field."""
    manifest = _load_manifest()
    bv = manifest.get("building_visuals", {})
    missing: list[str] = []
    for bname, bdata in bv.items():
        if "health_bar_offset" not in bdata:
            missing.append(bname)
    assert not missing, f"Buildings missing health_bar_offset: {missing}"


# ── Building footprint must exist ─────────────────────────────────────────────


def test_all_buildings_have_footprint() -> None:
    """Every building_visuals entry must have a footprint field."""
    manifest = _load_manifest()
    bv = manifest.get("building_visuals", {})
    missing: list[str] = []
    for bname, bdata in bv.items():
        if "footprint" not in bdata:
            missing.append(bname)
    assert not missing, f"Buildings missing footprint: {missing}"


def test_building_footprint_format() -> None:
    """Footprint must be either {w, h} dict or [w, h] array with positive values."""
    manifest = _load_manifest()
    bv = manifest.get("building_visuals", {})
    for bname, bdata in bv.items():
        fp = bdata.get("footprint")
        assert fp is not None, f"{bname}: footprint is None"
        if isinstance(fp, dict):
            assert "w" in fp and "h" in fp, f"{bname}: footprint dict missing w/h"
            assert float(fp["w"]) > 0, f"{bname}: footprint.w <= 0"
            assert float(fp["h"]) > 0, f"{bname}: footprint.h <= 0"
        elif isinstance(fp, list):
            assert len(fp) >= 2, f"{bname}: footprint array length < 2"
            assert float(fp[0]) > 0, f"{bname}: footprint[0] <= 0"
            assert float(fp[1]) > 0, f"{bname}: footprint[1] <= 0"
        else:
            pytest.fail(f"{bname}: footprint is neither dict nor array")


# ── Visual preset in control_feel_config ──────────────────────────────────────


def test_visual_preset_exists() -> None:
    """control_feel_config.json must have visual_preset section."""
    feel = _load_feel()
    assert "visual_preset" in feel, "visual_preset section missing from control_feel_config.json"


def test_visual_preset_selection_ring_style() -> None:
    """visual_preset.selection_ring_style must be 'simple' or 'enhanced'."""
    feel = _load_feel()
    vp = feel.get("visual_preset", {})
    style = str(vp.get("selection_ring_style", ""))
    assert style in ("simple", "enhanced"), (
        f"selection_ring_style='{style}' not in ('simple', 'enhanced')"
    )


def test_visual_preset_debug_defaults_off() -> None:
    """debug_grid_default and debug_elevation_default should be false."""
    feel = _load_feel()
    vp = feel.get("visual_preset", {})
    assert vp.get("debug_grid_default", True) is False, "debug_grid_default should be false"
    assert vp.get("debug_elevation_default", True) is False, "debug_elevation_default should be false"


def test_scale_anchor_units_exist_in_manifest() -> None:
    anchors = [
        "SCV", "Drone", "Probe",
        "Marine", "Zergling", "Zealot",
        "CommandCenter", "Hatchery", "Nexus",
        "Barracks", "SpawningPool", "Gateway",
    ]
    manifest = _load_manifest()
    sections = ["unit_visuals", "building_visuals"]
    found = set()
    for section in sections:
        for key in manifest.get(section, {}):
            found.add(key)
    for anchor in anchors:
        assert anchor in found, f"Scale anchor '{anchor}' missing from presentation_manifest.json"
