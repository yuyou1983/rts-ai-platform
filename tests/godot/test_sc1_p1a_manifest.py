from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
P1A_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p1a_resource_manifest.json"
P0_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p0_resource_manifest.json"
SCALE_CONFIG = REPO_ROOT / "tools" / "sc1_assets" / "visual_class_scale_config.json"


def test_p1a_schema_version() -> None:
    m = json.loads(P1A_MANIFEST.read_text())
    assert m["schema_version"] == 2


def test_p1a_has_12_assets() -> None:
    m = json.loads(P1A_MANIFEST.read_text())
    assert len(m["assets"]) == 12


def test_p1a_no_id_overlap_with_p0() -> None:
    p0 = json.loads(P0_MANIFEST.read_text())
    p1a = json.loads(P1A_MANIFEST.read_text())
    p0_ids = {a["id"] for a in p0["assets"]}
    p1a_ids = {a["id"] for a in p1a["assets"]}
    overlap = p0_ids & p1a_ids
    assert not overlap, f"P0/P1A ID overlap: {overlap}"


def test_p1a_visual_classes_valid() -> None:
    cfg = json.loads(SCALE_CONFIG.read_text())
    valid_classes = set(cfg["visual_classes"].keys())
    m = json.loads(P1A_MANIFEST.read_text())
    for asset in m["assets"]:
        vc = asset.get("visual_class", "")
        assert vc in valid_classes, f"{asset['id']}: invalid visual_class '{vc}'"


def test_p1a_pending_assets_marked() -> None:
    m = json.loads(P1A_MANIFEST.read_text())
    for asset in m["assets"]:
        if asset["mpq_path"].upper() == "PENDING":
            assert asset.get("mpq_source", "") != ""


def test_p1a_all_units_have_visual_class() -> None:
    m = json.loads(P1A_MANIFEST.read_text())
    for asset in m["assets"]:
        if asset["kind"] == "unit":
            assert "visual_class" in asset and asset["visual_class"], (
                f"{asset['id']}: unit missing visual_class"
            )


def test_p1a_godot_asset_paths_valid() -> None:
    m = json.loads(P1A_MANIFEST.read_text())
    for asset in m["assets"]:
        ga = asset["godot_asset"]
        assert ga.startswith("res://"), f"{asset['id']}: bad godot_asset '{ga}'"
        assert ga.endswith(".png"), f"{asset['id']}: not PNG '{ga}'"


GENERATED_MANIFEST = REPO_ROOT / "godot" / "assets" / "sc1_generated" / "generated_manifest.json"


def test_generated_manifest_matches_p0_plus_extractable_p1a() -> None:
    generated = json.loads(GENERATED_MANIFEST.read_text())
    p0 = json.loads(P0_MANIFEST.read_text())
    p1a = json.loads(P1A_MANIFEST.read_text())

    p0_ids = {asset["id"] for asset in p0["assets"]}
    p1a_extractable_ids = {
        asset["id"]
        for asset in p1a["assets"]
        if asset.get("mpq_path", "").upper() != "PENDING"
    }
    p1a_pending_ids = {
        asset["id"]
        for asset in p1a["assets"]
        if asset.get("mpq_path", "").upper() == "PENDING"
    }

    actual_ids = set(generated["assets"])
    expected_ids = p0_ids | p1a_extractable_ids

    assert actual_ids == expected_ids, (
        f"Expected {sorted(expected_ids)}, got {sorted(actual_ids)}. "
        f"Extra: {sorted(actual_ids - expected_ids)}, Missing: {sorted(expected_ids - actual_ids)}"
    )
    assert not (actual_ids & p1a_pending_ids), (
        f"PENDING assets leaked into generated: {sorted(actual_ids & p1a_pending_ids)}"
    )
