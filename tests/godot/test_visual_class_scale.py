from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCALE_CONFIG = REPO_ROOT / "tools" / "sc1_assets" / "visual_class_scale_config.json"
GENERATED_MANIFEST = REPO_ROOT / "godot" / "assets" / "sc1_generated" / "generated_manifest.json"


def test_scale_config_schema() -> None:
    cfg = json.loads(SCALE_CONFIG.read_text())
    assert cfg["schema_version"] == 2
    assert len(cfg["visual_classes"]) >= 5
    for vc, entry in cfg["visual_classes"].items():
        assert "body_world_min" in entry, f"{vc} missing body_world_min"
        assert "body_world_max" in entry, f"{vc} missing body_world_max"
        assert entry["body_world_min"] < entry["body_world_max"], f"{vc} min >= max"


def test_p1a_units_in_scale_range() -> None:
    if not GENERATED_MANIFEST.exists():
        return  # Skip if not yet generated locally
    cfg = json.loads(SCALE_CONFIG.read_text())
    manifest = json.loads(GENERATED_MANIFEST.read_text())
    ranges = cfg["visual_classes"]
    for asset_id, entry in manifest["assets"].items():
        if entry["kind"] != "unit":
            continue
        vc = entry.get("visual_class", "")
        if vc not in ranges:
            continue
        body_world = entry["content_extent"] * float(entry["render_scale"])
        lo = ranges[vc]["body_world_min"]
        hi = ranges[vc]["body_world_max"]
        assert lo <= body_world <= hi, (
            f"{asset_id} ({vc}) body_world={body_world:.3f} "
            f"outside [{lo}, {hi}]"
        )


def test_all_generated_units_use_configured_visual_class() -> None:
    cfg = json.loads(SCALE_CONFIG.read_text())
    manifest = json.loads(GENERATED_MANIFEST.read_text())
    ranges = cfg["visual_classes"]
    for asset_id, entry in manifest["assets"].items():
        if entry["kind"] != "unit":
            continue
        visual_class = entry.get("visual_class", "")
        assert visual_class in ranges, (
            f"{asset_id}: unconfigured visual_class '{visual_class}'"
        )
