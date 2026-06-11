import re
from pathlib import Path

from PIL import Image

from scripts.sc1_extract_manifest import build_generated_manifest


def test_generated_manifest_marks_buildings_and_resources_runtime_enabled() -> None:
    records = [
        {
            "id": "Marine",
            "kind": "unit",
            "race": "terran",
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
            "race": "terran",
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
            "race": "neutral",
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
    assert generated["assets"]["Marine"]["race"] == "terran"
    assert generated["assets"]["CommandCenter"]["runtime_enabled"] is True
    assert generated["assets"]["CommandCenter"]["race"] == "terran"
    assert generated["assets"]["CommandCenter"]["asset"] == "res://assets/sc1_generated/p0/CommandCenter.png"
    assert generated["assets"]["CommandCenter"]["atlas_rect"] == [0, 0, 128, 160]
    assert generated["assets"]["CommandCenter"]["frame_count"] == 6
    assert generated["assets"]["MineralFieldType1"]["runtime_enabled"] is True
    assert generated["assets"]["MineralFieldType1"]["race"] == "neutral"


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


def _write_padded_unit_sheet(
    path: Path,
    frame_width: int,
    frame_height: int,
    extents: list[int],
) -> None:
    image = Image.new("RGBA", (frame_width * len(extents), frame_height), (0, 0, 0, 0))
    for index, extent in enumerate(extents):
        patch = Image.new("RGBA", (extent, extent), (255, 255, 255, 255))
        x = index * frame_width + (frame_width - extent) // 2
        y = (frame_height - extent) // 2
        image.alpha_composite(patch, (x, y))
    image.save(path)


def test_generated_manifest_adds_normalized_unit_render_scales(tmp_path: Path) -> None:
    scv_path = tmp_path / "SCV.png"
    marine_path = tmp_path / "Marine.png"
    probe_path = tmp_path / "Probe.png"
    _write_padded_unit_sheet(scv_path, 72, 72, [39, 40, 40, 41, 42])
    _write_padded_unit_sheet(marine_path, 64, 64, [26, 26, 27, 26, 58])
    _write_padded_unit_sheet(probe_path, 32, 32, [26, 27, 27, 28, 30])

    records = [
        {
            "id": "SCV",
            "kind": "unit",
            "race": "terran",
            "mpq_path": "unit\\terran\\scv.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(scv_path),
                "stdout": "wrote SCV.png from scv.grp frames=5 frame_size=72x72",
            },
        },
        {
            "id": "Marine",
            "kind": "unit",
            "race": "terran",
            "mpq_path": "unit\\terran\\marine.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(marine_path),
                "stdout": "wrote Marine.png from marine.grp frames=5 frame_size=64x64",
            },
        },
        {
            "id": "Probe",
            "kind": "unit",
            "race": "protoss",
            "mpq_path": "unit\\protoss\\probe.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(probe_path),
                "stdout": "wrote Probe.png from probe.grp frames=5 frame_size=32x32",
            },
        },
    ]

    generated = build_generated_manifest(records, Path("/repo/godot/assets/sc1_generated/p0"))

    scv = generated["assets"]["SCV"]
    marine = generated["assets"]["Marine"]
    probe = generated["assets"]["Probe"]

    assert scv["content_extent"] == 40
    assert marine["content_extent"] == 26
    assert probe["content_extent"] == 27
    assert scv["render_scale"] == 0.0212
    assert marine["render_scale"] == 0.0277
    assert probe["render_scale"] == 0.0352
    assert scv["scale_basis"] == "content_median_extent"
    assert 0.8 <= scv["content_extent"] * scv["render_scale"] <= 0.9
    assert 0.68 <= marine["content_extent"] * marine["render_scale"] <= 0.75
    assert 0.9 <= probe["content_extent"] * probe["render_scale"] <= 1.0


def test_generated_manifest_scales_units_from_visual_class(tmp_path: Path) -> None:
    firebat_path = tmp_path / "Firebat.png"
    reaver_path = tmp_path / "Reaver.png"
    wraith_path = tmp_path / "Wraith.png"
    _write_padded_unit_sheet(firebat_path, 32, 32, [28, 29, 29, 30, 31])
    _write_padded_unit_sheet(reaver_path, 84, 84, [82, 84, 84, 84, 84])
    _write_padded_unit_sheet(wraith_path, 64, 64, [62, 64, 64, 64, 64])

    records = [
        {
            "id": "Firebat",
            "kind": "unit",
            "race": "terran",
            "mpq_path": "unit\\terran\\firebat.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(firebat_path),
                "stdout": "wrote Firebat.png from firebat.grp frames=5 frame_size=32x32",
            },
        },
        {
            "id": "Reaver",
            "kind": "unit",
            "race": "protoss",
            "mpq_path": "unit\\protoss\\trilob.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(reaver_path),
                "stdout": "wrote Reaver.png from trilob.grp frames=5 frame_size=84x84",
            },
        },
        {
            "id": "Wraith",
            "kind": "unit",
            "race": "terran",
            "mpq_path": "unit\\terran\\phoenix.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(wraith_path),
                "stdout": "wrote Wraith.png from phoenix.grp frames=5 frame_size=64x64",
            },
        },
    ]
    input_manifest = {
        "assets": [
            {"id": "Firebat", "visual_class": "small_ground"},
            {"id": "Reaver", "visual_class": "large_ground"},
            {"id": "Wraith", "visual_class": "small_air"},
        ]
    }

    generated = build_generated_manifest(
        records,
        Path("/repo/godot/assets/sc1_generated/p1a_core_units"),
        batch="p1a_core_units",
        input_manifest=input_manifest,
    )

    firebat = generated["assets"]["Firebat"]
    reaver = generated["assets"]["Reaver"]
    wraith = generated["assets"]["Wraith"]

    assert firebat["content_extent"] == 29
    assert reaver["content_extent"] == 84
    assert wraith["content_extent"] == 64
    assert firebat["scale_basis"] == "content_median_extent"
    assert reaver["scale_basis"] == "content_median_extent"
    assert wraith["scale_basis"] == "content_median_extent"
    assert 0.68 <= firebat["content_extent"] * firebat["render_scale"] <= 0.72
    assert 1.52 <= reaver["content_extent"] * reaver["render_scale"] <= 1.58
    assert 1.03 <= wraith["content_extent"] * wraith["render_scale"] <= 1.07


def test_game_view_prefers_generated_probe_strip_for_protoss_worker() -> None:
    source = (Path(__file__).resolve().parents[2] / "godot/scripts/game_view.gd").read_text()

    assert "res://assets/sc1_generated/p0/Probe.png" in source
    assert re.search(
        r'_unit_anim_info\["worker_3"\]\s*=\s*\{'
        r'"rows":\s*1,\s*"cols":\s*\[17\],\s*"fw":\s*\[32\],\s*"fh":\s*\[32\],\s*"south":\s*\[8\]',
        source,
    )
