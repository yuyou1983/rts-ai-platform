from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
P1B_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p1b_building_manifest.json"
SCALE_CONFIG = REPO_ROOT / "tools" / "sc1_assets" / "visual_class_scale_config.json"


def test_p1b_manifest_schema() -> None:
    manifest = json.loads(P1B_MANIFEST.read_text())
    assert manifest["schema_version"] == 2
    assert manifest["batch"] == "p1b_tech_buildings"
    assert len(manifest["assets"]) == 11


def test_p1b_assets_have_discovery_candidates() -> None:
    manifest = json.loads(P1B_MANIFEST.read_text())
    for asset in manifest["assets"]:
        assert asset["kind"] == "building"
        assert asset["mpq_path"] == "PENDING"
        assert asset["candidate_names"], f"{asset['id']}: missing candidate_names"
        assert asset["visual_class"] in {"small_building", "medium_building", "large_building"}


def test_p1b_candidate_names_match_listfile() -> None:
    """Verify candidate_names come from PyMS Listfile and can be probed."""
    import subprocess
    extractor = REPO_ROOT / "tools" / "mpq" / "bin" / "storm_extract"
    stardat = Path("/Users/yuyou/code/StarCraft/StarDat.mpq")
    if not extractor.exists() or not stardat.exists():
        pytest.skip("storm_extract or StarDat.mpq not available")
    manifest = json.loads(P1B_MANIFEST.read_text())
    tmp = Path("/tmp/_p1b_probe.tmp")
    for asset in manifest["assets"]:
        race = asset["race"].lower()
        for alias in asset["candidate_names"]:
            path = "unit\\" + race + "\\" + alias + ".grp"
            r = subprocess.run(
                [str(extractor), "extract-one", str(stardat), path, str(tmp)],
                capture_output=True, timeout=10,
            )
            if r.returncode == 0:
                tmp.unlink(missing_ok=True)
                break
        else:
            pytest.fail(
                f"{asset['id']}: no candidate found in StarDat.mpq"
            )


def test_p1b_visual_classes_in_scale_config() -> None:
    cfg = json.loads(SCALE_CONFIG.read_text())
    valid_classes = set(cfg["visual_classes"].keys())
    manifest = json.loads(P1B_MANIFEST.read_text())
    for asset in manifest["assets"]:
        vc = asset.get("visual_class", "")
        assert vc in valid_classes, f"{asset['id']}: invalid visual_class '{vc}'"


def test_p1b_no_id_overlap_with_p0_or_p1a() -> None:
    p0 = json.loads((REPO_ROOT / "tools/sc1_assets/p0_resource_manifest.json").read_text())
    p1a = json.loads((REPO_ROOT / "tools/sc1_assets/p1a_resource_manifest.json").read_text())
    p1b = json.loads(P1B_MANIFEST.read_text())
    existing = {a["id"] for a in p0["assets"]} | {a["id"] for a in p1a["assets"]}
    overlap = {a["id"] for a in p1b["assets"]} & existing
    assert not overlap, f"P1B ID overlap with P0/P1A: {overlap}"


def test_p1b_races_are_terran_zerg_protoss() -> None:
    manifest = json.loads(P1B_MANIFEST.read_text())
    valid_races = {"terran", "zerg", "protoss"}
    for asset in manifest["assets"]:
        assert asset["race"] in valid_races, f"{asset['id']}: invalid race '{asset['race']}'"
