#!/usr/bin/env python3
"""验证 presentation manifest + sprite 加载一致性。

用法: python3 scripts/verify_presentation_scene.py [--fix]

检查项:
1. manifest JSON 合法且所有 required key 存在
2. atlas_rect 不超出 PNG 实际尺寸
3. 所有 abstract_* 映射 resolve 到已知的 visual
4. fallback 资源存在
5. selection_radius / render_scale > 0
6. sprite_frames_config 中 frame_width/height <= PNG 实际尺寸
7. manifest 与 game_view.gd 硬编码一致性（如果有偏差则报告）
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "godot/resources/presentation_manifest.json"
FRAMES_CFG = ROOT / "godot/resources/sprite_frames_config.json"
GODOT_ASSETS = ROOT / "godot/assets"

# game_view.gd 中硬编码的建筑 atlas_rect（抽象类型,owner -> [x,y,w,h,scale]）
HARDCODED_BUILDINGS: dict[tuple[str, int], list] = {
    ("base", 1): [205, 190, 145, 95, 0.040],
    ("barracks", 1): [573, 197, 191, 69, 0.0319],
    ("factory", 1): [409, 466, 164, 47, 0.0426],
    ("refinery", 1): [382, 189, 191, 77, 0.026],
    ("starport", 1): [573, 446, 191, 86, 0.0256],
    ("base", 2): [30, 301, 121, 128, 0.033],
    ("barracks", 2): [1478, 688, 83, 85, 0.048],
    ("lair", 2): [10, 627, 210, 132, 0.019],
    ("hive", 2): [11, 1184, 141, 124, 0.028],
}

REQUIRED_B_KEYS = ["atlas_rect", "pivot", "health_bar_offset", "fallback",
                   "selection_ring_offset", "render_scale", "selection_radius"]
REQUIRED_U_KEYS = ["pivot", "health_bar_offset", "fallback",
                   "selection_ring_offset", "render_scale", "selection_radius"]


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    return struct.unpack(">II", header[16:24])


def _res_path(rel: str) -> Path:
    return GODOT_ASSETS / rel.removeprefix("res://assets/")


def _visual_id(value) -> str | None:
    """Resolve abstract mapping values to visual ids.

    Most mappings are plain strings, while morph entries can be dicts such as
    {"unit": "Guardian", "morph": true, "morph_from": "Mutalisk"}.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("unit", "building", "visual", "sprite", "name"):
            mapped = value.get(key)
            if isinstance(mapped, str):
                return mapped
    return None


def check_manifest() -> list[str]:
    issues: list[str] = []
    m = json.loads(MANIFEST.read_text())

    # required keys per entry
    for bname, bdata in m.get("building_visuals", {}).items():
        for k in REQUIRED_B_KEYS:
            if k not in bdata:
                issues.append(f"building {bname} missing {k}")
    for uname, udata in m.get("unit_visuals", {}).items():
        for k in REQUIRED_U_KEYS:
            if k not in udata:
                issues.append(f"unit {uname} missing {k}")

    # atlas_rect format
    for bname, bdata in m.get("building_visuals", {}).items():
        ar = bdata.get("atlas_rect", [])
        if not isinstance(ar, list) or len(ar) != 4:
            issues.append(f"building {bname} atlas_rect bad: {ar}")

    # positive values
    for bname, bdata in m.get("building_visuals", {}).items():
        if bdata.get("render_scale", 0) <= 0:
            issues.append(f"building {bname} render_scale <= 0")
        if bdata.get("selection_radius", 0) <= 0:
            issues.append(f"building {bname} selection_radius <= 0")
    for uname, udata in m.get("unit_visuals", {}).items():
        if udata.get("render_scale", 0) <= 0:
            issues.append(f"unit {uname} render_scale <= 0")
        if udata.get("selection_radius", 0) <= 0:
            issues.append(f"unit {uname} selection_radius <= 0")

    # fallback
    for bname, bdata in m.get("building_visuals", {}).items():
        fb = bdata.get("fallback", {})
        if "atlas_rect" not in fb or "render_scale" not in fb:
            issues.append(f"building {bname} fallback incomplete")
    for uname, udata in m.get("unit_visuals", {}).items():
        fb = udata.get("fallback", {})
        if "asset" not in fb or "render_scale" not in fb:
            issues.append(f"unit {uname} fallback incomplete")
        else:
            p = _res_path(fb["asset"])
            if not p.exists():
                issues.append(f"unit {uname} fallback asset missing: {p}")

    # abstract -> visual consistency
    bvs = set(m.get("building_visuals", {}))
    uvs = set(m.get("unit_visuals", {}))
    for owner, mappings in m.get("abstract_buildings", {}).items():
        for atype, mapping_value in mappings.items():
            visual_id = _visual_id(mapping_value)
            if visual_id not in bvs:
                issues.append(f"abstract_buildings {owner}/{atype} -> {mapping_value} not in building_visuals")
    for owner, mappings in m.get("abstract_units", {}).items():
        for atype, mapping_value in mappings.items():
            visual_id = _visual_id(mapping_value)
            if visual_id not in uvs:
                issues.append(f"abstract_units {owner}/{atype} -> {mapping_value} not in unit_visuals")

    # _rendering section
    r = m.get("_rendering", {})
    for k in ["selection_ring", "health_bar"]:
        if k not in r:
            issues.append(f"_rendering missing {k}")

    return issues


def check_atlas_vs_png() -> list[str]:
    """检查 atlas_rect 不超过 PNG 实际尺寸。"""
    issues: list[str] = []
    m = json.loads(MANIFEST.read_text())
    cfg = json.loads(FRAMES_CFG.read_text())

    # buildings: atlas_rect from sprite_frames_config
    for bname, bdata in m.get("building_visuals", {}).items():
        ar = bdata.get("atlas_rect", [])
        if len(ar) != 4:
            continue
        bcfg = cfg.get("buildings", {}).get(bname, {})
        fpath = bcfg.get("file", "")
        if not fpath:
            continue
        p = ROOT / "godot" / fpath.removeprefix("res://")
        if not p.exists():
            continue
        w, h = _png_size(p)
        x, y, rw, rh = ar
        if x + rw > w or y + rh > h:
            issues.append(f"building {bname} atlas_rect [{ar}] exceeds PNG size [{w}x{h}]")

    # units: sprite_frames_config frame_width/height
    for uname, udata in cfg.get("units", {}).items():
        fpath = udata.get("file", "")
        p = ROOT / "godot" / fpath.removeprefix("res://")
        if not p.exists():
            continue
        w, h = _png_size(p)
        fw = udata.get("frame_width", 0)
        fh = udata.get("frame_height", 0)
        if fw > w or fh > h:
            issues.append(f"unit {uname} frame {fw}x{fh} exceeds PNG {w}x{h}")

    return issues


def check_hardcode_drift() -> list[str]:
    """对比 manifest 和 game_view.gd 硬编码，报告偏差。"""
    issues: list[str] = []
    m = json.loads(MANIFEST.read_text())
    abstract_b = m.get("abstract_buildings", {})

    for (atype, owner), hw in HARDCODED_BUILDINGS.items():
        sc_name = abstract_b.get(str(owner), {}).get(atype)
        if not sc_name:
            continue
        bdata = m.get("building_visuals", {}).get(sc_name, {})
        ar = bdata.get("atlas_rect", [])
        rs = bdata.get("render_scale", 0)
        if len(ar) == 4:
            if ar != hw[:4]:
                issues.append(
                    f"DRIFT: {sc_name} (owner={owner} type={atype}): "
                    f"manifest atlas_rect={ar} vs hardcode={hw[:4]}"
                )
        if rs and abs(rs - hw[4]) > 0.005:
            issues.append(
                f"DRIFT: {sc_name} render_scale: manifest={rs:.4f} vs hardcode={hw[4]:.4f}"
            )

    return issues


def main() -> int:
    all_issues: list[str] = []
    all_issues.extend(check_manifest())
    all_issues.extend(check_atlas_vs_png())
    all_issues.extend(check_hardcode_drift())

    if all_issues:
        print(f"FAIL — {len(all_issues)} issue(s):")
        for i in all_issues:
            print(f"  • {i}")
        return 1

    print("OK — manifest structure valid, atlas in bounds, abstract→visual consistent")
    print("     (hardcode drift checks passed — no divergent overrides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
