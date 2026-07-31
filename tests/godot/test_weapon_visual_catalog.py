"""Validate the weapon visual catalog for the 12 representative SC1 weapons.

This test cross-references:
  - data/combat/weapons.json            (source of the 12 weapon IDs)
  - godot/resources/vfx/weapon_visual_catalog.json  (per-weapon visual mapping)
  - godot/resources/vfx/vfx_catalog.json (effect definitions referenced by the catalog)
  - godot/scripts/vfx_manager.gd        (must expose spawn_weapon_event)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

WEAPONS_DATA = REPO_ROOT / "data" / "combat" / "weapons.json"
WEAPON_VISUAL_CATALOG = REPO_ROOT / "godot" / "resources" / "vfx" / "weapon_visual_catalog.json"
VFX_CATALOG = REPO_ROOT / "godot" / "resources" / "vfx" / "vfx_catalog.json"
VFX_MANAGER = REPO_ROOT / "godot" / "scripts" / "vfx_manager.gd"

# Expected 12 weapon IDs (used for explicit assertions + cross-checks with weapons.json)
EXPECTED_WEAPON_IDS = {
    "terran_c10_rifle",
    "terran_flame_thrower",
    "terran_fragmentation_grenade",
    "terran_arclite_cannon",
    "zerg_claws",
    "zerg_needle_spines",
    "zerg_glave_wurm",
    "zerg_kaiser_blades",
    "protoss_psi_blades",
    "protoss_phase_disruptor",
    "protoss_psionic_storm",
    "protoss_scarab",
}

REQUIRED_FIELDS = {
    "animation_action",
    "launch_effect",
    "projectile_style",
    "impact_effect",
    "shield_impact_effect",
    "death_effect",
    "audio_cue",
    "priority",
}

VALID_PROJECTILE_STYLES = {
    "hitscan_tracer",
    "flame_cone",
    "grenade_arc",
    "tank_shell",
    "needle_spine",
    "glave_chain",
    "phase_orb",
    "storm_area",
    "scarab_tracking",
    "melee_slash",
    "heavy_melee_arc",
    "none",
}

# Weapon → unit mapping for the differentiation assertions
MARINE_WEAPON = "terran_c10_rifle"
VULTURE_WEAPON = "terran_fragmentation_grenade"
TANK_WEAPON = "terran_arclite_cannon"
TEMPLAR_WEAPON = "protoss_psionic_storm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict[str, Any]:
    assert path.exists(), f"Required file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _weapon_ids_from_weapons_json(weapons_data: dict[str, Any]) -> set[str]:
    """Extract all weapon_id values from data/combat/weapons.json, skipping _meta."""
    ids: set[str] = set()
    for key, entry in weapons_data.items():
        if key.startswith("_"):
            continue
        if isinstance(entry, dict) and "weapon_id" in entry:
            ids.add(str(entry["weapon_id"]))
    return ids


# ---------------------------------------------------------------------------
# Tests — file presence & structure
# ---------------------------------------------------------------------------

def test_weapon_visual_catalog_exists_and_is_valid_json() -> None:
    """weapon_visual_catalog.json must exist and parse as valid JSON."""
    _load_json(WEAPON_VISUAL_CATALOG)  # raises on missing / bad JSON


def test_weapons_json_exists_and_is_valid_json() -> None:
    """data/combat/weapons.json must exist and parse as valid JSON."""
    _load_json(WEAPONS_DATA)


def test_weapon_visual_catalog_has_meta() -> None:
    """The catalog should carry a _meta block describing its purpose."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    assert "_meta" in catalog, "weapon_visual_catalog.json missing '_meta' key"


# ---------------------------------------------------------------------------
# Tests — all 12 weapon IDs present
# ---------------------------------------------------------------------------

def test_weapons_json_has_exactly_12_expected_weapons() -> None:
    """data/combat/weapons.json must contain exactly the 12 expected weapon IDs."""
    weapons_data = _load_json(WEAPONS_DATA)
    ids = _weapon_ids_from_weapons_json(weapons_data)
    assert ids == EXPECTED_WEAPON_IDS, (
        f"weapons.json weapon IDs mismatch.\n"
        f"  missing: {sorted(EXPECTED_WEAPON_IDS - ids)}\n"
        f"  extra:   {sorted(ids - EXPECTED_WEAPON_IDS)}"
    )


def test_all_12_weapon_ids_exist_in_visual_catalog() -> None:
    """Every weapon ID from weapons.json must have an entry in the visual catalog."""
    weapons_data = _load_json(WEAPONS_DATA)
    weapon_ids = _weapon_ids_from_weapons_json(weapons_data)
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    catalog_keys = {
        k for k in catalog.keys() if not k.startswith("_")
    }
    missing = weapon_ids - catalog_keys
    assert not missing, (
        f"Weapon IDs missing from visual catalog: {sorted(missing)}"
    )


def test_visual_catalog_has_no_extra_weapon_entries() -> None:
    """The visual catalog must not contain weapon entries beyond the 12 expected."""
    weapons_data = _load_json(WEAPONS_DATA)
    weapon_ids = _weapon_ids_from_weapons_json(weapons_data)
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    catalog_keys = {
        k for k in catalog.keys() if not k.startswith("_")
    }
    extra = catalog_keys - weapon_ids
    assert not extra, (
        f"Unexpected extra weapon entries in visual catalog: {sorted(extra)}"
    )


# ---------------------------------------------------------------------------
# Tests — required fields per entry
# ---------------------------------------------------------------------------

def test_every_weapon_entry_has_all_required_fields() -> None:
    """Each of the 12 weapon entries must define all 8 required fields."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        assert weapon_id in catalog, f"Weapon '{weapon_id}' not in catalog"
        entry = catalog[weapon_id]
        assert isinstance(entry, dict), (
            f"Weapon '{weapon_id}' entry is {type(entry).__name__}, expected dict"
        )
        missing = REQUIRED_FIELDS - set(entry.keys())
        assert not missing, (
            f"Weapon '{weapon_id}' missing required fields: {sorted(missing)}"
        )


def test_every_weapon_entry_has_no_unexpected_extra_fields() -> None:
    """Each weapon entry must contain only the 8 required fields (no extras)."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        entry = catalog[weapon_id]
        extra = set(entry.keys()) - REQUIRED_FIELDS
        assert not extra, (
            f"Weapon '{weapon_id}' has unexpected extra fields: {sorted(extra)}"
        )


# ---------------------------------------------------------------------------
# Tests — field value validity
# ---------------------------------------------------------------------------

def test_projectile_styles_are_valid() -> None:
    """Every projectile_style must be one of the 12 allowed values."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        style = catalog[weapon_id]["projectile_style"]
        assert style in VALID_PROJECTILE_STYLES, (
            f"Weapon '{weapon_id}' has invalid projectile_style='{style}', "
            f"expected one of {sorted(VALID_PROJECTILE_STYLES)}"
        )


def test_priority_is_int_in_range_1_to_5() -> None:
    """Every priority must be an integer in [1, 5]."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        priority = catalog[weapon_id]["priority"]
        assert isinstance(priority, int), (
            f"Weapon '{weapon_id}' priority is {type(priority).__name__}, expected int"
        )
        assert 1 <= priority <= 5, (
            f"Weapon '{weapon_id}' priority={priority} out of range [1, 5]"
        )


def test_animation_action_is_string() -> None:
    """Every animation_action must be a non-empty string."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        action = catalog[weapon_id]["animation_action"]
        assert isinstance(action, str), (
            f"Weapon '{weapon_id}' animation_action is {type(action).__name__}, expected str"
        )
        assert action, f"Weapon '{weapon_id}' animation_action is empty"


def test_audio_cue_is_non_empty_string() -> None:
    """Every audio_cue must be a non-empty string."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        cue = catalog[weapon_id]["audio_cue"]
        assert isinstance(cue, str), (
            f"Weapon '{weapon_id}' audio_cue is {type(cue).__name__}, expected str"
        )
        assert cue, f"Weapon '{weapon_id}' audio_cue is empty"


def test_effect_fields_are_non_empty_strings() -> None:
    """launch_effect, impact_effect, shield_impact_effect, death_effect must be
    non-empty strings."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    effect_fields = (
        "launch_effect",
        "impact_effect",
        "shield_impact_effect",
        "death_effect",
    )
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        for field in effect_fields:
            value = catalog[weapon_id][field]
            assert isinstance(value, str), (
                f"Weapon '{weapon_id}' {field} is {type(value).__name__}, expected str"
            )
            assert value, f"Weapon '{weapon_id}' {field} is empty"


# ---------------------------------------------------------------------------
# Tests — effect references resolve in vfx_catalog
# ---------------------------------------------------------------------------

def test_launch_impact_death_effects_exist_in_vfx_catalog() -> None:
    """launch_effect, impact_effect, and death_effect must reference entries in
    vfx_catalog.json's 'effects' section."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    vfx_catalog = _load_json(VFX_CATALOG)
    effects = set(vfx_catalog.get("effects", {}).keys())
    assert effects, "vfx_catalog.json has no 'effects' section"
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        entry = catalog[weapon_id]
        for field in ("launch_effect", "impact_effect", "death_effect"):
            ref = entry[field]
            assert ref in effects, (
                f"Weapon '{weapon_id}' {field}='{ref}' not found in "
                f"vfx_catalog.effects"
            )


def test_shield_impact_effect_exists_in_vfx_catalog() -> None:
    """shield_impact_effect must reference an entry in vfx_catalog.effects."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    vfx_catalog = _load_json(VFX_CATALOG)
    effects = set(vfx_catalog.get("effects", {}).keys())
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        ref = catalog[weapon_id]["shield_impact_effect"]
        assert ref in effects, (
            f"Weapon '{weapon_id}' shield_impact_effect='{ref}' not found in "
            f"vfx_catalog.effects"
        )


def test_all_referenced_effects_have_minimum_fields() -> None:
    """Every effect referenced by the weapon catalog must define at minimum:
    texture, lifetime, color, and size-ish (radius/scale)."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    vfx_catalog = _load_json(VFX_CATALOG)
    effects = vfx_catalog.get("effects", {})
    referenced: set[str] = set()
    for weapon_id in EXPECTED_WEAPON_IDS:
        entry = catalog[weapon_id]
        referenced.add(entry["launch_effect"])
        referenced.add(entry["impact_effect"])
        referenced.add(entry["death_effect"])
        referenced.add(entry["shield_impact_effect"])
    for name in sorted(referenced):
        assert name in effects, f"Referenced effect '{name}' missing from vfx_catalog.effects"
        spec = effects[name]
        for required in ("texture", "lifetime", "color"):
            assert required in spec, (
                f"Effect '{name}' missing required field '{required}'"
            )
        # size: allow either radius or scale as the "size" indicator
        assert "radius" in spec or "scale" in spec, (
            f"Effect '{name}' missing size field (needs 'radius' or 'scale')"
        )


# ---------------------------------------------------------------------------
# Tests — animation_action rules
# ---------------------------------------------------------------------------

def test_templar_weapon_uses_cast_animation() -> None:
    """protoss_psionic_storm (Templar) must use 'cast' animation_action."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    assert TEMPLAR_WEAPON in catalog, f"{TEMPLAR_WEAPON} missing from catalog"
    assert catalog[TEMPLAR_WEAPON]["animation_action"] == "cast", (
        f"Templar weapon '{TEMPLAR_WEAPON}' animation_action="
        f"{catalog[TEMPLAR_WEAPON]['animation_action']!r}, expected 'cast'"
    )


def test_other_11_weapons_use_attack_animation() -> None:
    """All weapons except protoss_psionic_storm must use 'attack' animation_action."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    others = EXPECTED_WEAPON_IDS - {TEMPLAR_WEAPON}
    for weapon_id in sorted(others):
        assert weapon_id in catalog, f"Weapon '{weapon_id}' missing from catalog"
        action = catalog[weapon_id]["animation_action"]
        assert action == "attack", (
            f"Weapon '{weapon_id}' animation_action={action!r}, expected 'attack'"
        )


def test_animation_action_values_are_only_attack_or_cast() -> None:
    """No weapon may use an animation_action other than 'attack' or 'cast'."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    valid = {"attack", "cast"}
    for weapon_id in sorted(EXPECTED_WEAPON_IDS):
        action = catalog[weapon_id]["animation_action"]
        assert action in valid, (
            f"Weapon '{weapon_id}' animation_action={action!r}, "
            f"expected one of {sorted(valid)}"
        )


# ---------------------------------------------------------------------------
# Tests — Marine / Vulture / Tank differentiation
# ---------------------------------------------------------------------------

def test_marine_vulture_tank_have_different_projectile_styles() -> None:
    """Marine, Vulture, and Tank must NOT share the same projectile_style."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    styles = {
        "Marine": catalog[MARINE_WEAPON]["projectile_style"],
        "Vulture": catalog[VULTURE_WEAPON]["projectile_style"],
        "Tank": catalog[TANK_WEAPON]["projectile_style"],
    }
    unique = set(styles.values())
    assert len(unique) == 3, (
        f"Marine/Vulture/Tank must have 3 distinct projectile_styles, "
        f"got {styles} (only {len(unique)} unique)"
    )


def test_marine_vulture_tank_have_distinct_launch_effects() -> None:
    """Marine, Vulture, and Tank must have distinguishable launch effects."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    launches = {
        "Marine": catalog[MARINE_WEAPON]["launch_effect"],
        "Vulture": catalog[VULTURE_WEAPON]["launch_effect"],
        "Tank": catalog[TANK_WEAPON]["launch_effect"],
    }
    unique = set(launches.values())
    assert len(unique) == 3, (
        f"Marine/Vulture/Tank must have 3 distinct launch_effects, "
        f"got {launches} (only {len(unique)} unique)"
    )


def test_marine_vulture_tank_have_distinct_impact_effects() -> None:
    """Marine, Vulture, and Tank must have distinguishable impact effects."""
    catalog = _load_json(WEAPON_VISUAL_CATALOG)
    impacts = {
        "Marine": catalog[MARINE_WEAPON]["impact_effect"],
        "Vulture": catalog[VULTURE_WEAPON]["impact_effect"],
        "Tank": catalog[TANK_WEAPON]["impact_effect"],
    }
    unique = set(impacts.values())
    assert len(unique) == 3, (
        f"Marine/Vulture/Tank must have 3 distinct impact_effects, "
        f"got {impacts} (only {len(unique)} unique)"
    )


# ---------------------------------------------------------------------------
# Tests — VFXManager integration
# ---------------------------------------------------------------------------

def test_vfx_manager_has_spawn_weapon_event_function() -> None:
    """vfx_manager.gd must define a spawn_weapon_event(event, visual) function."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    text = VFX_MANAGER.read_text(encoding="utf-8")
    pattern = r"func\s+spawn_weapon_event\s*\(\s*event\s*:\s*Dictionary\s*,\s*visual\s*:\s*Dictionary\s*\)\s*->\s*void"
    assert re.search(pattern, text), (
        "vfx_manager.gd missing spawn_weapon_event(event: Dictionary, visual: Dictionary) -> void"
    )


def test_vfx_manager_handles_all_12_projectile_styles() -> None:
    """spawn_weapon_event (via _spawn_projectile_for_style) must handle all 12
    catalog projectile_styles."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    text = VFX_MANAGER.read_text(encoding="utf-8")
    for style in sorted(VALID_PROJECTILE_STYLES):
        # Each style should appear as a match case string literal in the GDScript.
        assert f'"{style}"' in text, (
            f"vfx_manager.gd does not handle projectile_style '{style}'"
        )


def test_vfx_manager_preserves_legacy_spawn_combat_event() -> None:
    """The legacy spawn_combat_event must remain as a fallback."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    text = VFX_MANAGER.read_text(encoding="utf-8")
    assert re.search(r"func\s+spawn_combat_event\s*\(\s*event\s*:\s*Dictionary\s*\)", text), (
        "vfx_manager.gd missing legacy spawn_combat_event(event: Dictionary)"
    )


def test_vfx_manager_falls_back_to_spawn_combat_event_when_visual_empty() -> None:
    """spawn_weapon_event must delegate to spawn_combat_event when visual is empty."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    text = VFX_MANAGER.read_text(encoding="utf-8")
    # Find the spawn_weapon_event body and check it calls spawn_combat_event on empty visual.
    assert "spawn_combat_event(event)" in text, (
        "spawn_weapon_event should call spawn_combat_event(event) as a fallback"
    )


def test_vfx_manager_loads_weapon_visual_catalog() -> None:
    """vfx_manager.gd must load the weapon visual catalog at _ready."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    text = VFX_MANAGER.read_text(encoding="utf-8")
    assert "weapon_visual_catalog.json" in text, (
        "vfx_manager.gd does not reference weapon_visual_catalog.json"
    )
    assert "_load_weapon_visual_catalog" in text, (
        "vfx_manager.gd missing _load_weapon_visual_catalog function"
    )


def test_vfx_manager_spawn_weapon_event_handles_spell_resolved() -> None:
    """spawn_weapon_event must handle 'spell_resolved' event type for
    Templar's psionic storm."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    text = VFX_MANAGER.read_text(encoding="utf-8")
    assert '"spell_resolved"' in text, (
        "vfx_manager.gd spawn_weapon_event must handle 'spell_resolved' event type"
    )


# ---------------------------------------------------------------------------
# Tests — CombatVisualController integration
# ---------------------------------------------------------------------------

COMBAT_VISUAL_CONTROLLER = REPO_ROOT / "godot" / "scripts" / "combat_visual_controller.gd"


def test_combat_visual_controller_uses_spawn_weapon_event() -> None:
    """combat_visual_controller.gd must call spawn_weapon_event when a weapon
    visual is available, falling back to spawn_combat_event otherwise."""
    assert COMBAT_VISUAL_CONTROLLER.exists(), "combat_visual_controller.gd missing"
    text = COMBAT_VISUAL_CONTROLLER.read_text(encoding="utf-8")
    assert "spawn_weapon_event" in text, (
        "combat_visual_controller.gd must call spawn_weapon_event for weapon-specific visuals"
    )
    assert "get_weapon_visual" in text, (
        "combat_visual_controller.gd must look up weapon visuals via get_weapon_visual"
    )
    assert "spawn_combat_event" in text, (
        "combat_visual_controller.gd must retain spawn_combat_event as fallback"
    )


def test_combat_visual_controller_spell_event_includes_weapon_id() -> None:
    """_handle_spell_resolved must include weapon_id in the output so the
    weapon visual lookup succeeds for spells (e.g. psionic storm)."""
    assert COMBAT_VISUAL_CONTROLLER.exists(), "combat_visual_controller.gd missing"
    text = COMBAT_VISUAL_CONTROLLER.read_text(encoding="utf-8")
    spell_block = text[text.index("_handle_spell_resolved"):]
    assert '"weapon_id": spell_id' in spell_block or '"weapon_id":' in spell_block, (
        "_handle_spell_resolved must set weapon_id for weapon visual lookup"
    )


# ---------------------------------------------------------------------------
# Task 12 — 12-unit resource gate
#
# Verify that all 12 representative SC1 combat units have the full chain of
# resources wired end-to-end:
#   presentation_manifest.unit_visuals  → sprite_frames_config.units
#   → attack/cast animation frames     → on-disk asset PNGs
#   → weapon_visual_catalog weapon IDs ↔ data/combat/weapons.json
# ---------------------------------------------------------------------------

# The 12 representative SC1 combat units (display names used by presentation_manifest
# and sprite_frames_config).
COMBAT_UNIT_NAMES = {
    "Marine", "Firebat", "Vulture", "Tank",
    "Zergling", "Hydralisk", "Mutalisk", "Ultralisk",
    "Zealot", "Dragoon", "Templar", "Reaver",
}

# Weapon ID → unit display name (cross-reference catalog ↔ manifest ↔ assets).
WEAPON_TO_UNIT: dict[str, str] = {
    "terran_c10_rifle": "Marine",
    "terran_flame_thrower": "Firebat",
    "terran_fragmentation_grenade": "Vulture",
    "terran_arclite_cannon": "Tank",
    "zerg_claws": "Zergling",
    "zerg_needle_spines": "Hydralisk",
    "zerg_glave_wurm": "Mutalisk",
    "zerg_kaiser_blades": "Ultralisk",
    "protoss_psi_blades": "Zealot",
    "protoss_phase_disruptor": "Dragoon",
    "protoss_psionic_storm": "Templar",
    "protoss_scarab": "Reaver",
}

TEMPLAR_UNIT = "Templar"

PRESENTATION_MANIFEST = REPO_ROOT / "godot" / "resources" / "presentation_manifest.json"
SPRITE_FRAMES_CONFIG = REPO_ROOT / "godot" / "resources" / "sprite_frames_config.json"


class TestResourceGate:
    """Task 12 resource gate — all 12 combat units must have visual, sprite-frame,
    animation, and on-disk asset resources, and their weapon IDs must match
    weapons.json bijectively."""

    def test_presentation_manifest_has_all_12_combat_units(self) -> None:
        """presentation_manifest.unit_visuals must define entries for all 12 units."""
        manifest = _load_json(PRESENTATION_MANIFEST)
        unit_visuals = manifest.get("unit_visuals", {})
        assert isinstance(unit_visuals, dict), (
            "presentation_manifest.unit_visuals is not a dict"
        )
        missing = COMBAT_UNIT_NAMES - set(unit_visuals.keys())
        assert not missing, (
            f"presentation_manifest.unit_visuals missing combat units: {sorted(missing)}"
        )

    def test_sprite_frames_config_has_all_12_combat_units(self) -> None:
        """sprite_frames_config.units must define entries for all 12 units."""
        cfg = _load_json(SPRITE_FRAMES_CONFIG)
        units = cfg.get("units", {})
        assert isinstance(units, dict), "sprite_frames_config.units is not a dict"
        missing = COMBAT_UNIT_NAMES - set(units.keys())
        assert not missing, (
            f"sprite_frames_config.units missing combat units: {sorted(missing)}"
        )

    def test_non_templar_units_have_attack_animation_frames(self) -> None:
        """Each non-Templar combat unit must have an 'attack' animation with >0 frames."""
        cfg = _load_json(SPRITE_FRAMES_CONFIG)
        units = cfg["units"]
        non_templar = COMBAT_UNIT_NAMES - {TEMPLAR_UNIT}
        for unit in sorted(non_templar):
            assert unit in units, f"Unit '{unit}' missing from sprite_frames_config"
            anims = units[unit].get("animations", {})
            assert "attack" in anims, f"Unit '{unit}' has no 'attack' animation"
            assert anims["attack"] > 0, (
                f"Unit '{unit}' attack animation has {anims['attack']} frames "
                f"(expected >0)"
            )

    def test_templar_has_cast_animation_frames(self) -> None:
        """Templar must have a 'cast' animation with >0 frames (uses cast, not attack)."""
        cfg = _load_json(SPRITE_FRAMES_CONFIG)
        units = cfg["units"]
        assert TEMPLAR_UNIT in units, "Templar missing from sprite_frames_config"
        anims = units[TEMPLAR_UNIT].get("animations", {})
        assert "cast" in anims, "Templar has no 'cast' animation"
        assert anims["cast"] > 0, (
            f"Templar cast animation has {anims['cast']} frames (expected >0)"
        )

    def test_asset_files_for_all_12_units_exist_on_disk(self) -> None:
        """Every combat unit's asset (referenced via presentation_manifest) must
        exist on disk under godot/assets/."""
        manifest = _load_json(PRESENTATION_MANIFEST)
        unit_visuals = manifest["unit_visuals"]
        missing_assets: list[str] = []
        for unit in sorted(COMBAT_UNIT_NAMES):
            entry = unit_visuals.get(unit, {})
            asset = entry.get("asset", "")
            assert asset, f"Unit '{unit}' has no 'asset' path in presentation_manifest"
            # res://assets/... -> godot/assets/...
            asset_path = REPO_ROOT / "godot" / asset.removeprefix("res://")
            if not asset_path.exists():
                missing_assets.append(f"{unit}: {asset_path}")
        assert not missing_assets, (
            "Missing on-disk assets for combat units:\n  "
            + "\n  ".join(missing_assets)
        )

    def test_weapon_visual_catalog_ids_match_weapons_json(self) -> None:
        """All 12 weapon IDs in weapon_visual_catalog.json must match the weapon IDs
        in data/combat/weapons.json bijectively."""
        catalog = _load_json(WEAPON_VISUAL_CATALOG)
        catalog_keys = {k for k in catalog if not k.startswith("_")}
        weapons_data = _load_json(WEAPONS_DATA)
        weapon_ids = _weapon_ids_from_weapons_json(weapons_data)
        missing_in_catalog = weapon_ids - catalog_keys
        extra_in_catalog = catalog_keys - weapon_ids
        assert not missing_in_catalog, (
            f"Weapon IDs in weapons.json but missing from visual catalog: "
            f"{sorted(missing_in_catalog)}"
        )
        assert not extra_in_catalog, (
            f"Weapon IDs in visual catalog but not in weapons.json: "
            f"{sorted(extra_in_catalog)}"
        )

    def test_every_catalog_weapon_maps_to_a_manifest_unit(self) -> None:
        """Each weapon_id in the visual catalog must map to a unit_visuals entry
        carrying the same weapon_id (proves catalog ↔ manifest wiring)."""
        manifest = _load_json(PRESENTATION_MANIFEST)
        unit_visuals = manifest["unit_visuals"]
        for weapon_id, unit_name in sorted(WEAPON_TO_UNIT.items()):
            assert unit_name in unit_visuals, (
                f"Weapon '{weapon_id}' maps to unit '{unit_name}' which is not in "
                f"presentation_manifest.unit_visuals"
            )
            entry = unit_visuals[unit_name]
            assert entry.get("weapon_id") == weapon_id, (
                f"Unit '{unit_name}' weapon_id={entry.get('weapon_id')!r}, "
                f"expected {weapon_id!r}"
            )
