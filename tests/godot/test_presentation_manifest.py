import json
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
