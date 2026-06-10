import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "godot/resources/presentation_manifest.json"
VFX_PATH = ROOT / "godot/resources/vfx/vfx_catalog.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _race_values(data: dict) -> list[dict]:
    values: list[dict] = []
    for race in ("terran", "zerg", "protoss"):
        race_data = data.get(race, {})
        if isinstance(race_data, dict):
            values.extend(race_data.values())
        else:
            values.extend(race_data)
    return values


def _res_path_exists(path: str) -> bool:
    if not path:
        return False
    if not path.startswith("res://"):
        return False
    return (ROOT / "godot" / path.removeprefix("res://")).exists()


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    return struct.unpack(">II", header[16:24])


def _visual_id(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("unit", "building", "visual", "sprite", "name"):
            mapped = value.get(key)
            if isinstance(mapped, str):
                return mapped
    return None


def test_presentation_manifest_covers_units_buildings_and_spells() -> None:
    manifest = _load_json(MANIFEST_PATH)
    units = _race_values(_load_json(ROOT / "data/units/units.json"))
    buildings = _race_values(_load_json(ROOT / "data/buildings/buildings.json"))
    spells = _load_json(ROOT / "data/spells/spells.json")["spells"]

    unit_visuals = manifest["unit_visuals"]
    building_visuals = manifest["building_visuals"]
    spell_visuals = manifest["spell_visuals"]

    assert {u["name"] for u in units} <= set(unit_visuals)
    assert {b["name"] for b in buildings} <= set(building_visuals)
    assert {s["name"] for s in spells} <= set(spell_visuals)


def test_vfx_catalog_covers_attack_capable_units() -> None:
    units = _race_values(_load_json(ROOT / "data/units/units.json"))
    vfx = _load_json(VFX_PATH)
    mapped_units = set(vfx["unit_effects"])
    attack_units = {
        u["name"]
        for u in units
        if max(u.get("damage", [0])) > 0
    }

    assert attack_units <= mapped_units


def test_manifest_assets_exist_and_scales_are_positive() -> None:
    manifest = _load_json(MANIFEST_PATH)

    for visual in manifest["unit_visuals"].values():
        assert _res_path_exists(visual["asset"])
        assert visual["render_scale"] > 0

    for visual in manifest["building_visuals"].values():
        assert _res_path_exists(visual["asset"])
        assert visual["render_scale"] > 0


def test_vfx_references_resolve_to_known_effects() -> None:
    vfx = _load_json(VFX_PATH)
    known_effects = set(vfx["effects"])

    for mapping in vfx["unit_effects"].values():
        assert set(mapping.values()) <= known_effects

    for mapping in vfx["spell_effects"].values():
        assert mapping["effect"] in known_effects


def test_default_unit_sprite_frame_is_inside_texture() -> None:
    config = _load_json(ROOT / "godot/resources/sprite_frames_config.json")

    for unit_name, info in config["units"].items():
        texture_path = ROOT / "godot" / info["file"].removeprefix("res://")
        width, height = _png_size(texture_path)
        frame_width = int(info["frame_width"])
        frame_height = int(info["frame_height"])

        assert frame_width <= width, unit_name
        assert frame_height <= height, unit_name


# ─── P1 Manifest extension tests ──────────────────────────────

REQUIRED_BUILDING_KEYS = [
    "atlas_rect", "pivot", "health_bar_offset", "fallback",
    "selection_ring_offset", "render_scale", "selection_radius",
]

REQUIRED_UNIT_KEYS = [
    "pivot", "health_bar_offset", "fallback",
    "selection_ring_offset", "render_scale", "selection_radius",
]


def test_building_visuals_have_required_keys() -> None:
    manifest = _load_json(MANIFEST_PATH)
    for bname, bdata in manifest["building_visuals"].items():
        for k in REQUIRED_BUILDING_KEYS:
            assert k in bdata, f"building {bname} missing {k}"


def test_unit_visuals_have_required_keys() -> None:
    manifest = _load_json(MANIFEST_PATH)
    for uname, udata in manifest["unit_visuals"].items():
        for k in REQUIRED_UNIT_KEYS:
            assert k in udata, f"unit {uname} missing {k}"


def test_atlas_rect_is_valid_format() -> None:
    manifest = _load_json(MANIFEST_PATH)
    for bname, bdata in manifest["building_visuals"].items():
        ar = bdata.get("atlas_rect", [])
        assert isinstance(ar, list), f"{bname} atlas_rect not list"
        assert len(ar) == 4, f"{bname} atlas_rect length {len(ar)} != 4"
        assert all(isinstance(v, (int, float)) for v in ar), f"{bname} atlas_rect non-numeric"


def test_pivot_is_valid_format() -> None:
    manifest = _load_json(MANIFEST_PATH)
    for bname, bdata in manifest["building_visuals"].items():
        p = bdata.get("pivot", [])
        assert isinstance(p, list), f"{bname} pivot not list"
        assert len(p) == 2, f"{bname} pivot length {len(p)} != 2"
    for uname, udata in manifest["unit_visuals"].items():
        p = udata.get("pivot", [])
        assert isinstance(p, list), f"{uname} pivot not list"
        assert len(p) == 2, f"{uname} pivot length {len(p)} != 2"


def test_health_bar_offset_is_valid() -> None:
    manifest = _load_json(MANIFEST_PATH)
    for section in ("building_visuals", "unit_visuals"):
        for name, data in manifest[section].items():
            hbo = data.get("health_bar_offset", [])
            assert isinstance(hbo, list), f"{name} health_bar_offset not list"
            assert len(hbo) == 2, f"{name} health_bar_offset length != 2"


def test_fallback_has_required_keys() -> None:
    manifest = _load_json(MANIFEST_PATH)
    for bname, bdata in manifest["building_visuals"].items():
        fb = bdata.get("fallback", {})
        assert "atlas_rect" in fb, f"{bname} fallback missing atlas_rect"
        assert "render_scale" in fb, f"{bname} fallback missing render_scale"
    for uname, udata in manifest["unit_visuals"].items():
        fb = udata.get("fallback", {})
        assert "asset" in fb, f"{uname} fallback missing asset"
        assert "render_scale" in fb, f"{uname} fallback missing render_scale"


def test_rendering_global_params_present() -> None:
    manifest = _load_json(MANIFEST_PATH)
    r = manifest.get("_rendering", {})
    assert "selection_ring" in r, "_rendering missing selection_ring"
    assert "health_bar" in r, "_rendering missing health_bar"
    assert "building_selection_transform" in r, "_rendering missing building_selection_transform"
    assert "unit_selection_transform" in r, "_rendering missing unit_selection_transform"


def test_selection_ring_params_valid() -> None:
    manifest = _load_json(MANIFEST_PATH)
    sr = manifest["_rendering"]["selection_ring"]
    assert sr["line_width"] > 0
    assert sr["segments"] >= 8
    assert len(sr["color"]) == 4


def test_abstract_buildings_match_visual_ids() -> None:
    """Every abstract building mapping should resolve to a known building_visual."""
    manifest = _load_json(MANIFEST_PATH)
    building_visuals = set(manifest["building_visuals"])
    for owner, mappings in manifest.get("abstract_buildings", {}).items():
        for abstract_type, sc_name in mappings.items():
            assert sc_name in building_visuals, (
                f"abstract_buildings owner={owner} type={abstract_type} -> {sc_name} not in building_visuals"
            )


def test_abstract_units_match_visual_ids() -> None:
    """Every abstract unit mapping should resolve to a known unit_visual."""
    manifest = _load_json(MANIFEST_PATH)
    unit_visuals = set(manifest["unit_visuals"])
    for owner, mappings in manifest.get("abstract_units", {}).items():
        for abstract_type, mapping_value in mappings.items():
            visual_id = _visual_id(mapping_value)
            assert visual_id in unit_visuals, (
                f"abstract_units owner={owner} type={abstract_type} -> {mapping_value} not in unit_visuals"
            )
