from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
P1A_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p1a_resource_manifest.json"
P1B_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p1b_building_manifest.json"
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


def test_generated_manifest_matches_p0_plus_extractable_p1a_p1b() -> None:
    """All extractable assets from every manifest must appear in generated; no untracked assets."""
    generated = json.loads(GENERATED_MANIFEST.read_text())
    p0 = json.loads(P0_MANIFEST.read_text())
    p1a = json.loads(P1A_MANIFEST.read_text())
    p1b = json.loads(P1B_MANIFEST.read_text())
    p1c = json.loads((REPO_ROOT / "tools" / "sc1_assets" / "p1c_building_manifest.json").read_text())
    p2 = json.loads((REPO_ROOT / "tools" / "sc1_assets" / "p2_unit_manifest.json").read_text())

    all_manifests = [p0, p1a, p1b, p1c, p2]

    # Every non-PENDING asset across all manifests must exist in generated
    all_extractable: set[str] = set()
    for m in all_manifests:
        all_extractable |= {
            asset["id"]
            for asset in m["assets"]
            if asset.get("mpq_path", "").upper() != "PENDING"
        }

    gen_ids = set(generated["assets"])
    missing = all_extractable - gen_ids
    assert not missing, f"Extractable assets missing from generated: {sorted(missing)}"

    # Every generated asset must be declared in at least one manifest
    all_declared: set[str] = set()
    for m in all_manifests:
        all_declared |= {asset["id"] for asset in m["assets"]}

    untracked = gen_ids - all_declared
    assert not untracked, f"Generated assets not in any manifest: {sorted(untracked)}"

    # PENDING assets must not leak into generated manifest
    all_pending: set[str] = set()
    for m in all_manifests:
        all_pending |= {
            asset["id"]
            for asset in m["assets"]
            if asset.get("mpq_path", "").upper() == "PENDING"
        }
    leaked = gen_ids & all_pending
    assert not leaked, f"PENDING assets leaked into generated: {sorted(leaked)}"


def test_p1a_generated_manifest_path_is_top_level_contract() -> None:
    generated = json.loads(GENERATED_MANIFEST.read_text())
    assert "assets" in generated
    assert generated["assets"]["Firebat"]["asset"] == (
        "res://assets/sc1_generated/p1a_core_units/Firebat.png"
    )
