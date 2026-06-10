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
                "stdout": "wrote CommandCenter.png from CommandCenter.grp frames=6 frame_size=128x160",
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
