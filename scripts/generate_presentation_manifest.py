#!/usr/bin/env python3
"""Generate Godot presentation mappings from current design data and assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "godot/resources/presentation_manifest.json"
VFX_PATH = ROOT / "godot/resources/vfx/vfx_catalog.json"

RACES = ("terran", "zerg", "protoss")

ABSTRACT_UNITS = {
    "1": {"worker": "SCV", "soldier": "Marine", "scout": "Ghost"},
    "2": {"worker": "Drone", "soldier": "Zergling", "scout": "Hydralisk"},
    "3": {"worker": "Probe", "soldier": "Zealot", "scout": "Dragoon"},
}

ABSTRACT_BUILDINGS = {
    "1": {
        "base": "CommandCenter",
        "barracks": "Barracks",
        "factory": "Factory",
        "refinery": "Refinery",
        "starport": "Starport",
    },
    "2": {
        "base": "Hatchery",
        "barracks": "SpawningPool",
        "refinery": "Extractor",
        "lair": "Lair",
        "hive": "Hive",
    },
    "3": {
        "base": "Nexus",
        "barracks": "Gateway",
        "refinery": "Assimilator",
        "pylon": "Pylon",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def race_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for race in RACES:
        values = data.get(race, {})
        if isinstance(values, dict):
            items.extend(values.values())
        else:
            items.extend(values)
    return items


def vfx_profile_for_unit(unit: dict[str, Any]) -> str:
    name = str(unit["name"])
    race = str(unit.get("race", ""))
    lower = name.lower()

    if max(unit.get("damage", [0])) <= 0:
        return "none"
    if name in {"Marine", "Ghost", "SCV"}:
        return "terran_small_arms"
    if name in {"Firebat"}:
        return "terran_flame"
    if name in {"Tank", "Vulture", "Goliath"}:
        return "terran_ordnance"
    if name in {"Wraith", "Valkyrie", "BattleCruiser"}:
        return "terran_ship"
    if race == "zerg" or any(token in lower for token in ("zerg", "hydra", "mutalisk", "guardian", "devourer")):
        return "zerg_acid"
    if name in {"Zealot", "DarkTemplar", "Archon"}:
        return "protoss_psi_melee"
    if race == "protoss":
        return "protoss_energy"
    return "generic_hit"


def effect_mapping(profile: str) -> dict[str, str]:
    profiles = {
        "none": {"hit": "hit_spark", "death": "hit_spark"},
        "terran_small_arms": {"attack": "muzzle_flash_small", "hit": "hit_spark", "death": "hit_spark"},
        "terran_flame": {"attack": "flame_burst", "hit": "flame_burst", "death": "hit_spark"},
        "terran_ordnance": {"attack": "muzzle_flash_small", "hit": "shell_impact", "death": "shell_impact"},
        "terran_ship": {"attack": "muzzle_flash_small", "hit": "shell_impact", "death": "shell_impact"},
        "zerg_acid": {"attack": "acid_hit", "hit": "acid_hit", "death": "acid_hit"},
        "protoss_psi_melee": {"attack": "shield_hit", "hit": "shield_hit", "death": "shield_hit"},
        "protoss_energy": {"attack": "psi_flash", "hit": "shield_hit", "death": "shield_hit"},
        "generic_hit": {"attack": "muzzle_flash_small", "hit": "hit_spark", "death": "hit_spark"},
    }
    return dict(profiles[profile])


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def unit_render_scale(unit: dict[str, Any], sprite_config: dict[str, Any]) -> float:
    frame_size = max(float(sprite_config.get("frame_width", 40)), float(sprite_config.get("frame_height", 40)))
    design_size = max(float(unit.get("width", 40)), float(unit.get("height", 40)))
    target_world_size = clamp(design_size / 48.0, 0.75, 2.25)
    return round(target_world_size / max(frame_size, 1.0), 4)


def building_render_scale(sprite_config: dict[str, Any]) -> float:
    frame_size = max(float(sprite_config.get("frame_width", 160)), float(sprite_config.get("frame_height", 160)))
    target_world_size = clamp(frame_size / 64.0, 2.5, 5.2)
    return round(target_world_size / max(frame_size, 1.0), 4)


def spell_effect_for(spell: dict[str, Any]) -> str:
    race = str(spell.get("race", ""))
    target = str(spell.get("target", ""))
    name = str(spell["name"])
    if name in {"NuclearStrike", "YamatoGun"}:
        return "shell_impact"
    if name in {"Stimpack", "Repair", "Heal", "Restoration", "ScannerSweep"}:
        return "muzzle_flash_small"
    if race == "zerg":
        return "acid_hit"
    if race == "protoss" or target == "point":
        return "psi_flash"
    return "hit_spark"


def main() -> None:
    units_data = load_json(ROOT / "data/units/units.json")
    buildings_data = load_json(ROOT / "data/buildings/buildings.json")
    spells = load_json(ROOT / "data/spells/spells.json")["spells"]
    sprite_config = load_json(ROOT / "godot/resources/sprite_frames_config.json")
    vfx = load_json(VFX_PATH)

    unit_visuals: dict[str, Any] = {}
    for unit in race_items(units_data):
        sprite = str(unit.get("sprite", unit["name"]))
        unit_cfg = sprite_config.get("units", {}).get(sprite, {})
        profile = vfx_profile_for_unit(unit)
        unit_visuals[str(unit["name"])] = {
            "race": unit.get("race", ""),
            "sprite": sprite,
            "sprite_config": sprite,
            "asset": unit_cfg.get("file", ""),
            "vfx_profile": profile,
            "audio_prefix": unit["name"],
            "render_scale": unit_render_scale(unit, unit_cfg),
            "selection_radius": round(max(float(unit.get("width", 32)), float(unit.get("height", 32))) / 64.0, 3),
        }
        vfx.setdefault("unit_effects", {})[str(unit["name"])] = effect_mapping(profile)

    building_visuals: dict[str, Any] = {}
    for building in race_items(buildings_data):
        name = str(building["name"])
        cfg = sprite_config.get("buildings", {}).get(name, {})
        building_visuals[name] = {
            "race": building.get("race", ""),
            "sprite_config": name,
            "asset": cfg.get("file", ""),
            "vfx_profile": "building",
            "audio_prefix": name,
            "render_scale": building_render_scale(cfg),
            "selection_radius": round(max(float(cfg.get("frame_width", 128)), float(cfg.get("frame_height", 128))) / 64.0, 3),
        }

    spell_visuals = {
        str(spell["name"]): {
            "race": spell.get("race", ""),
            "target": spell.get("target", ""),
            "effect": spell_effect_for(spell),
            "sfx": str(spell["name"]),
        }
        for spell in spells
    }

    vfx.setdefault("effects", {}).setdefault(
        "flame_burst",
        {
            "texture": "res://assets/effects/Magic.png",
            "color": [1.0, 0.42, 0.08, 0.92],
            "secondary_color": [1.0, 0.12, 0.02, 0.7],
            "lifetime": 0.26,
            "radius": 0.72,
            "scale": 0.04,
            "rings": 2,
        },
    )
    vfx.setdefault("effects", {}).setdefault(
        "psi_flash",
        {
            "texture": "res://assets/effects/Magic.png",
            "color": [0.55, 0.85, 1.0, 0.9],
            "secondary_color": [0.95, 0.95, 1.0, 0.68],
            "lifetime": 0.3,
            "radius": 0.82,
            "scale": 0.04,
            "rings": 2,
        },
    )
    vfx["spell_effects"] = spell_visuals

    manifest = {
        "_meta": {
            "generated_by": "scripts/generate_presentation_manifest.py",
            "purpose": "Bridge design data, Godot assets, VFX, and runtime abstract entity ids.",
        },
        "abstract_units": ABSTRACT_UNITS,
        "abstract_buildings": ABSTRACT_BUILDINGS,
        "unit_visuals": unit_visuals,
        "building_visuals": building_visuals,
        "spell_visuals": spell_visuals,
    }
    write_json(MANIFEST_PATH, manifest)
    write_json(VFX_PATH, vfx)


if __name__ == "__main__":
    main()
