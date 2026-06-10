import re
from pathlib import Path

from scripts.sc1_extract_manifest import build_generated_manifest


def test_generated_manifest_marks_buildings_and_resources_runtime_enabled() -> None:
    records = [
        {
            "id": "Marine",
            "kind": "unit",
            "mpq_path": "unit\\terran\\marine.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": "/repo/godot/assets/sc1_generated/p0/Marine.png",
                "stdout": "wrote Marine.png from Marine.grp frames=229 frame_size=64x64",
            },
        },
        {
            "id": "CommandCenter",
            "kind": "building",
            "mpq_path": "unit\\terran\\control.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": "/repo/godot/assets/sc1_generated/p0/CommandCenter.png",
                "stdout": (
                    "wrote CommandCenter.png from CommandCenter.grp "
                    "frames=6 frame_size=128x160"
                ),
            },
        },
        {
            "id": "MineralFieldType1",
            "kind": "resource",
            "mpq_path": "unit\\neutral\\min01.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": "/repo/godot/assets/sc1_generated/p0/MineralFieldType1.png",
                "stdout": "wrote MineralFieldType1.png from min01.grp frames=4 frame_size=64x96",
            },
        },
    ]

    generated = build_generated_manifest(records, Path("/repo/godot/assets/sc1_generated/p0"))

    assert generated["schema_version"] == 1
    assert generated["assets"]["Marine"]["runtime_enabled"] is False
    assert generated["assets"]["CommandCenter"]["runtime_enabled"] is True
    assert generated["assets"]["CommandCenter"]["asset"] == "res://assets/sc1_generated/p0/CommandCenter.png"
    assert generated["assets"]["CommandCenter"]["atlas_rect"] == [0, 0, 128, 160]
    assert generated["assets"]["CommandCenter"]["frame_count"] == 6
    assert generated["assets"]["MineralFieldType1"]["runtime_enabled"] is True


def test_generated_manifest_adds_visual_scales_for_generated_buildings() -> None:
    records = [
        {
            "id": "CommandCenter",
            "kind": "building",
            "mpq_path": "unit\\terran\\control.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": "/repo/godot/assets/sc1_generated/p0/CommandCenter.png",
                "stdout": "wrote CommandCenter.png from control.grp frames=6 frame_size=128x160",
            },
        },
        {
            "id": "Nexus",
            "kind": "building",
            "mpq_path": "unit\\protoss\\nexus.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": "/repo/godot/assets/sc1_generated/p0/Nexus.png",
                "stdout": "wrote Nexus.png from nexus.grp frames=1 frame_size=192x224",
            },
        },
        {
            "id": "Gateway",
            "kind": "building",
            "mpq_path": "unit\\protoss\\gateway.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": "/repo/godot/assets/sc1_generated/p0/Gateway.png",
                "stdout": "wrote Gateway.png from gateway.grp frames=1 frame_size=128x160",
            },
        },
        {
            "id": "Pylon",
            "kind": "building",
            "mpq_path": "unit\\protoss\\pylon.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": "/repo/godot/assets/sc1_generated/p0/Pylon.png",
                "stdout": "wrote Pylon.png from pylon.grp frames=1 frame_size=64x64",
            },
        },
    ]

    generated = build_generated_manifest(records, Path("/repo/godot/assets/sc1_generated/p0"))

    command_center = generated["assets"]["CommandCenter"]
    nexus = generated["assets"]["Nexus"]
    gateway = generated["assets"]["Gateway"]
    pylon = generated["assets"]["Pylon"]

    assert command_center["render_scale"] == 0.035
    assert nexus["render_scale"] == 0.025
    assert gateway["render_scale"] == 0.03
    assert pylon["render_scale"] == 0.0281
    assert max(nexus["frame_width"], nexus["frame_height"]) * nexus["render_scale"] >= 5.5
    assert max(gateway["frame_width"], gateway["frame_height"]) * gateway["render_scale"] >= 4.7
    assert 1.6 <= max(pylon["frame_width"], pylon["frame_height"]) * pylon["render_scale"] <= 2.0


def test_game_view_prefers_generated_probe_strip_for_protoss_worker() -> None:
    source = (Path(__file__).resolve().parents[2] / "godot/scripts/game_view.gd").read_text()

    assert "res://assets/sc1_generated/p0/Probe.png" in source
    assert re.search(
        r'_unit_anim_info\["worker_3"\]\s*=\s*\{'
        r'"rows":\s*1,\s*"cols":\s*\[17\],\s*"fw":\s*\[32\],\s*"fh":\s*\[32\],\s*"south":\s*\[8\]',
        source,
    )
