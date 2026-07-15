"""Validate the VFX profile system across vfx_catalog, presentation manifest, and units data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

VFX_CATALOG = REPO_ROOT / "godot" / "resources" / "vfx" / "vfx_catalog.json"
PRESENTATION_MANIFEST = REPO_ROOT / "godot" / "resources" / "presentation_manifest.json"
UNITS_DATA = REPO_ROOT / "data" / "units" / "units.json"
FEEL_CONFIG = REPO_ROOT / "godot" / "resources" / "feel" / "control_feel_config.json"
VFX_MANAGER = REPO_ROOT / "godot" / "scripts" / "vfx_manager.gd"
COMBAT_VISUAL_CONTROLLER = REPO_ROOT / "godot" / "scripts" / "combat_visual_controller.gd"

REQUIRED_PROFILE_KEYS = {"attack", "hit", "death", "projectile", "tracer", "priority"}
VALID_PROJECTILE_TYPES = {"hitscan", "ballistic", "melee", "stream", "psi", "none"}
VALID_VFX_PROFILE_VALUES = VALID_PROJECTILE_TYPES | {"none"}  # "none" is a sentinel

# Phase 3 additions — timing keys required for projectile-carrying profiles
TIMING_KEYS = {"projectile_speed_tiles_per_second", "muzzle_offset_tiles", "impact_offset_tiles"}
PROJECTILE_TYPES_WITH_SPEED = {"hitscan", "ballistic", "stream"}

# Required 8 core profiles per Phase 3 spec
REQUIRED_CORE_PROFILES = {
    "terran_ballistic",
    "terran_explosive",
    "terran_flame",
    "zerg_melee",
    "zerg_acid",
    "zerg_spore",
    "protoss_psi",
    "protoss_phase",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict[str, Any]:
    assert path.exists(), f"Required file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _combat_units(units_data: dict[str, Any]) -> set[str]:
    """Return unit names with attackType >= 0 across all races."""
    names: set[str] = set()
    for race_key in ("terran", "zerg", "protoss"):
        race_units = units_data.get(race_key, {})
        for unit_name, unit_def in race_units.items():
            if unit_def.get("attackType", -1) >= 0:
                names.add(unit_name)
    return names


def _manifest_vfx_profiles(manifest: dict[str, Any]) -> dict[str, str]:
    """Map every asset name → its vfx_profile across unit_visuals and building_visuals."""
    result: dict[str, str] = {}
    for section_key in ("unit_visuals", "building_visuals"):
        section = manifest.get(section_key, {})
        for asset_name, asset_def in section.items():
            profile = asset_def.get("vfx_profile")
            if profile is not None:
                result[asset_name] = profile
    return result


# ---------------------------------------------------------------------------
# Tests — vfx_catalog.json profiles
# ---------------------------------------------------------------------------


def test_vfx_catalog_has_profiles_key() -> None:
    """vfx_catalog.json must contain a top-level 'profiles' key."""
    catalog = _load_json(VFX_CATALOG)
    assert "profiles" in catalog, "vfx_catalog.json missing top-level 'profiles' key"


def test_vfx_catalog_profiles_has_at_least_10_entries() -> None:
    """The profiles section must contain at least 10 profile definitions."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    assert len(profiles) >= 10, (
        f"Expected >= 10 profiles, found {len(profiles)}"
    )


def test_each_profile_has_all_required_keys() -> None:
    """Every profile must define: attack, hit, death, projectile, tracer, priority."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        missing = REQUIRED_PROFILE_KEYS - set(profile.keys())
        assert not missing, f"Profile '{name}' missing keys: {missing}"


def test_profile_effect_refs_are_valid() -> None:
    """Profile 'attack', 'hit', 'death' values (when not 'none') must exist in effects."""
    catalog = _load_json(VFX_CATALOG)
    effects = set(catalog.get("effects", {}).keys())
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        for effect_key in ("attack", "hit", "death"):
            value = profile[effect_key]
            if value == "none":
                continue
            assert value in effects, (
                f"Profile '{name}' .{effect_key}='{value}' not found in effects"
            )


def test_profile_projectile_values_are_valid() -> None:
    """Each profile's 'projectile' must be one of the allowed types."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        projectile = profile["projectile"]
        assert projectile in VALID_PROJECTILE_TYPES, (
            f"Profile '{name}' has invalid projectile='{projectile}', "
            f"expected one of {sorted(VALID_PROJECTILE_TYPES)}"
        )


def test_profile_priority_is_int_between_1_and_3() -> None:
    """Each profile's 'priority' must be an integer in [1, 3]."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        priority = profile["priority"]
        assert isinstance(priority, int), (
            f"Profile '{name}' priority is {type(priority).__name__}, expected int"
        )
        assert 1 <= priority <= 3, (
            f"Profile '{name}' priority={priority} out of range [1, 3]"
        )


# ---------------------------------------------------------------------------
# Tests — Phase 3: timing fields
# ---------------------------------------------------------------------------


def test_each_profile_has_timing_fields() -> None:
    """Every profile must have projectile_speed_tiles_per_second, muzzle_offset_tiles,
    and impact_offset_tiles."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        missing = TIMING_KEYS - set(profile.keys())
        assert not missing, f"Profile '{name}' missing timing keys: {missing}"


def test_projectile_profiles_have_positive_speed() -> None:
    """Profiles whose projectile type implies a visible projectile must have
    projectile_speed_tiles_per_second > 0.0."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        proj_type = profile["projectile"]
        speed = float(profile["projectile_speed_tiles_per_second"])
        if proj_type in PROJECTILE_TYPES_WITH_SPEED:
            assert speed > 0.0, (
                f"Profile '{name}' has projectile='{proj_type}' but "
                f"projectile_speed_tiles_per_second={speed} (must be > 0)"
            )


def test_melee_and_none_profiles_have_zero_speed() -> None:
    """Profiles with projectile='melee' or 'none' must have
    projectile_speed_tiles_per_second == 0.0."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        proj_type = profile["projectile"]
        if proj_type in ("melee", "none"):
            speed = float(profile["projectile_speed_tiles_per_second"])
            assert speed == 0.0, (
                f"Profile '{name}' has projectile='{proj_type}' but "
                f"projectile_speed_tiles_per_second={speed} (must be 0.0)"
            )


def test_muzzle_offset_is_non_negative() -> None:
    """muzzle_offset_tiles must be >= 0.0 for all profiles."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        offset = float(profile["muzzle_offset_tiles"])
        assert offset >= 0.0, (
            f"Profile '{name}' muzzle_offset_tiles={offset} (must be >= 0.0)"
        )


def test_impact_offset_is_non_negative() -> None:
    """impact_offset_tiles must be >= 0.0 for all profiles."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    for name, profile in profiles.items():
        offset = float(profile["impact_offset_tiles"])
        assert offset >= 0.0, (
            f"Profile '{name}' impact_offset_tiles={offset} (must be >= 0.0)"
        )


def test_all_8_core_profiles_exist() -> None:
    """The 8 core weapon profiles required by Phase 3 must all exist."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    missing = REQUIRED_CORE_PROFILES - set(profiles.keys())
    assert not missing, f"Missing core profiles: {sorted(missing)}"


def test_core_profiles_have_distinct_priorities() -> None:
    """Among the 8 core profiles, there must be at least 2 distinct priority values
    to allow the VFX cap system to meaningfully differentiate."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    core_priorities = {
        profiles[p]["priority"]
        for p in REQUIRED_CORE_PROFILES
        if p in profiles
    }
    assert len(core_priorities) >= 2, (
        f"Core profiles must have at least 2 distinct priority values, found: {core_priorities}"
    )


# ---------------------------------------------------------------------------
# Tests — presentation_manifest.json
# ---------------------------------------------------------------------------


def test_presentation_manifest_exists_and_is_valid_json() -> None:
    """presentation_manifest.json must exist and parse as valid JSON."""
    _load_json(PRESENTATION_MANIFEST)  # will raise on missing / bad JSON


def test_manifest_vfx_profiles_reference_valid_catalog_profiles() -> None:
    """Every vfx_profile value in the manifest must exist in vfx_catalog profiles (or be 'none')."""
    catalog = _load_json(VFX_CATALOG)
    valid_profiles = set(catalog.get("profiles", {}).keys()) | {"none"}
    manifest = _load_json(PRESENTATION_MANIFEST)
    manifest_profiles = _manifest_vfx_profiles(manifest)
    for asset_name, profile_name in manifest_profiles.items():
        assert profile_name in valid_profiles, (
            f"Asset '{asset_name}' references unknown vfx_profile '{profile_name}'"
        )


# ---------------------------------------------------------------------------
# Tests — cross-referencing units.json ↔ presentation manifest
# ---------------------------------------------------------------------------


def test_every_combat_unit_has_vfx_profile_in_manifest() -> None:
    """Every combat unit (attackType >= 0) in units.json must appear in the presentation manifest."""
    units_data = _load_json(UNITS_DATA)
    manifest = _load_json(PRESENTATION_MANIFEST)
    combat_units = _combat_units(units_data)
    manifest_unit_names = set(manifest.get("unit_visuals", {}).keys())
    missing = combat_units - manifest_unit_names
    assert not missing, (
        f"Combat units missing from presentation manifest: {sorted(missing)}"
    )


def test_every_combat_unit_manifest_entry_has_vfx_profile() -> None:
    """Every combat unit entry in the manifest must have a vfx_profile field."""
    units_data = _load_json(UNITS_DATA)
    manifest = _load_json(PRESENTATION_MANIFEST)
    combat_units = _combat_units(units_data)
    unit_visuals = manifest.get("unit_visuals", {})
    for unit_name in sorted(combat_units):
        assert unit_name in unit_visuals, f"Unit '{unit_name}' not in unit_visuals"
        entry = unit_visuals[unit_name]
        assert "vfx_profile" in entry, f"Unit '{unit_name}' missing vfx_profile field"


# ---------------------------------------------------------------------------
# Tests — orphan detection
# ---------------------------------------------------------------------------


def test_no_orphan_profiles() -> None:
    """Every profile in vfx_catalog must be referenced by at least one manifest asset
    (or be a runtime-only profile like 'shield_hit' that is dynamically selected)."""
    catalog = _load_json(VFX_CATALOG)
    manifest = _load_json(PRESENTATION_MANIFEST)
    defined_profiles = set(catalog.get("profiles", {}).keys())
    referenced_profiles = {
        name for name in _manifest_vfx_profiles(manifest).values()
        if name != "none"
    }
    # Runtime-only profiles: dynamically selected at runtime, not statically referenced
    RUNTIME_ONLY_PROFILES = {"shield_hit"}
    orphans = defined_profiles - referenced_profiles - RUNTIME_ONLY_PROFILES
    assert not orphans, (
        f"Orphan profiles (not referenced by any manifest asset): {sorted(orphans)}"
    )


# ---------------------------------------------------------------------------
# Tests — cap system & control_feel_config integration
# ---------------------------------------------------------------------------


def test_control_feel_config_has_vfx_limits() -> None:
    """control_feel_config.json must contain a 'vfx_limits' top-level key
    with sub-keys max_active_effects, max_death_effects, max_projectiles,
    all positive integers."""
    cfg = _load_json(FEEL_CONFIG)
    assert "vfx_limits" in cfg, (
        "control_feel_config.json missing top-level 'vfx_limits' key"
    )
    limits = cfg["vfx_limits"]
    required = ("max_active_effects", "max_death_effects", "max_projectiles")
    for key in required:
        assert key in limits, f"'vfx_limits' missing sub-key '{key}'"
        value = limits[key]
        assert isinstance(value, int), (
            f"vfx_limits.{key} is {type(value).__name__}, expected int"
        )
        assert value > 0, f"vfx_limits.{key}={value} must be a positive integer"


def test_vfx_limits_values_are_reasonable() -> None:
    """VFX limit values must fall within reasonable bounds."""
    cfg = _load_json(FEEL_CONFIG)
    limits = cfg["vfx_limits"]

    max_active = limits["max_active_effects"]
    assert 16 <= max_active <= 256, (
        f"max_active_effects={max_active} outside reasonable range [16, 256]"
    )

    max_death = limits["max_death_effects"]
    assert 4 <= max_death <= 64, (
        f"max_death_effects={max_death} outside reasonable range [4, 64]"
    )

    max_proj = limits["max_projectiles"]
    assert 8 <= max_proj <= 128, (
        f"max_projectiles={max_proj} outside reasonable range [8, 128]"
    )


def test_profiles_have_priority_values() -> None:
    """Every profile in vfx_catalog['profiles'] must have a 'priority' key
    with an integer value between 1 and 3 (inclusive)."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    assert profiles, "vfx_catalog has no profiles to validate"
    for name, profile in profiles.items():
        assert "priority" in profile, f"Profile '{name}' missing 'priority' key"
        priority = profile["priority"]
        assert isinstance(priority, int), (
            f"Profile '{name}' priority is {type(priority).__name__}, expected int"
        )
        assert 1 <= priority <= 3, (
            f"Profile '{name}' priority={priority} outside range [1, 3]"
        )


def test_priority_distribution_has_low_and_high() -> None:
    """Among the profiles, there must be at least one with priority == 1
    and at least one with priority >= 3 to ensure meaningful cap
    differentiation (effects can be sorted by importance)."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    priorities = {p["priority"] for p in profiles.values() if "priority" in p}
    assert any(p == 1 for p in priorities), (
        "No profile with priority == 1 found — cap system cannot differentiate low-priority effects"
    )
    assert any(p >= 3 for p in priorities), (
        "No profile with priority >= 3 found — cap system cannot differentiate high-priority effects"
    )


def test_cap_contract_vfx_limits_match_vfx_manager_defaults() -> None:
    """The default integer values for _max_active_effects and
    _max_death_effects in vfx_manager.gd must match the values in
    control_feel_config.json so the fallback defaults stay in sync."""
    # Load JSON values
    cfg = _load_json(FEEL_CONFIG)
    limits = cfg["vfx_limits"]
    json_max_active = limits["max_active_effects"]
    json_max_death = limits["max_death_effects"]

    # Parse GDScript to extract default integers
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    gd_text = VFX_MANAGER.read_text(encoding="utf-8")

    m_active = re.search(r"_max_active_effects\s*:\s*int\s*=\s*(\d+)", gd_text)
    assert m_active, "Could not find '_max_active_effects: int = <N>' in vfx_manager.gd"
    gd_max_active = int(m_active.group(1))

    m_death = re.search(r"_max_death_effects\s*:\s*int\s*=\s*(\d+)", gd_text)
    assert m_death, "Could not find '_max_death_effects: int = <N>' in vfx_manager.gd"
    gd_max_death = int(m_death.group(1))

    assert gd_max_active == json_max_active, (
        f"_max_active_effects default ({gd_max_active}) != control_feel_config.json ({json_max_active})"
    )
    assert gd_max_death == json_max_death, (
        f"_max_death_effects default ({gd_max_death}) != control_feel_config.json ({json_max_death})"
    )


# ---------------------------------------------------------------------------
# Tests — tracer style & color
# ---------------------------------------------------------------------------


VALID_TRACER_STYLES = {"flicker", "arc", "cone", "slash", "flash", "beam", "none"}


def test_profiles_have_tracer_style() -> None:
    """Every profile in vfx_catalog['profiles'] must have a 'tracer_style' key
    with a string value that is one of the allowed styles."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    assert profiles, "vfx_catalog has no profiles to validate"
    for name, profile in profiles.items():
        assert "tracer_style" in profile, f"Profile '{name}' missing 'tracer_style' key"
        style = profile["tracer_style"]
        assert isinstance(style, str), (
            f"Profile '{name}' tracer_style is {type(style).__name__}, expected str"
        )
        assert style in VALID_TRACER_STYLES, (
            f"Profile '{name}' has invalid tracer_style='{style}', "
            f"expected one of {sorted(VALID_TRACER_STYLES)}"
        )


def test_profiles_have_tracer_color() -> None:
    """Every profile must have a 'tracer_color' key with an array of 4 floats (RGBA 0-1)."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    assert profiles, "vfx_catalog has no profiles to validate"
    for name, profile in profiles.items():
        assert "tracer_color" in profile, f"Profile '{name}' missing 'tracer_color' key"
        color = profile["tracer_color"]
        assert isinstance(color, list), (
            f"Profile '{name}' tracer_color is {type(color).__name__}, expected list"
        )
        assert len(color) == 4, (
            f"Profile '{name}' tracer_color has {len(color)} elements, expected 4"
        )
        for i, v in enumerate(color):
            assert isinstance(v, (int, float)), (
                f"Profile '{name}' tracer_color[{i}] is {type(v).__name__}, expected number"
            )


def test_tracer_color_values_in_range() -> None:
    """For each profile's tracer_color, all 4 values must be in [0.0, 1.0]."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    assert profiles, "vfx_catalog has no profiles to validate"
    for name, profile in profiles.items():
        color = profile["tracer_color"]
        for i, v in enumerate(color):
            assert 0.0 <= float(v) <= 1.0, (
                f"Profile '{name}' tracer_color[{i}]={v} outside range [0.0, 1.0]"
            )


def test_none_tracer_profiles_have_zero_color() -> None:
    """Profiles with tracer_style 'none' must have tracer_color [0.0, 0.0, 0.0, 0.0]."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    assert profiles, "vfx_catalog has no profiles to validate"
    zero_color = [0.0, 0.0, 0.0, 0.0]
    for name, profile in profiles.items():
        if profile["tracer_style"] == "none":
            assert profile["tracer_color"] == zero_color, (
                f"Profile '{name}' has tracer_style='none' but tracer_color={profile['tracer_color']}, "
                f"expected {zero_color}"
            )


# ---------------------------------------------------------------------------
# Tests — max_projectiles contract
# ---------------------------------------------------------------------------


def test_max_projectiles_in_feel_config() -> None:
    """control_feel_config.json vfx_limits must have a 'max_projectiles' key
    with a positive integer value."""
    cfg = _load_json(FEEL_CONFIG)
    assert "vfx_limits" in cfg, "control_feel_config.json missing 'vfx_limits' key"
    limits = cfg["vfx_limits"]
    assert "max_projectiles" in limits, "'vfx_limits' missing 'max_projectiles' key"
    value = limits["max_projectiles"]
    assert isinstance(value, int), (
        f"vfx_limits.max_projectiles is {type(value).__name__}, expected int"
    )
    assert value > 0, f"vfx_limits.max_projectiles={value} must be a positive integer"


def test_max_projectiles_in_vfx_manager_defaults() -> None:
    """The default value of _max_projectiles in vfx_manager.gd must match
    the value in control_feel_config.json."""
    cfg = _load_json(FEEL_CONFIG)
    json_max_proj = cfg["vfx_limits"]["max_projectiles"]

    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    gd_text = VFX_MANAGER.read_text(encoding="utf-8")

    m_proj = re.search(r"_max_projectiles\s*:\s*int\s*=\s*(\d+)", gd_text)
    assert m_proj, "Could not find '_max_projectiles: int = <N>' in vfx_manager.gd"
    gd_max_proj = int(m_proj.group(1))

    assert gd_max_proj == json_max_proj, (
        f"_max_projectiles default ({gd_max_proj}) != control_feel_config.json ({json_max_proj})"
    )


def test_spawn_tracer_exists_in_vfx_manager() -> None:
    """vfx_manager.gd must contain a function definition for spawn_tracer."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    gd_text = VFX_MANAGER.read_text(encoding="utf-8")
    assert re.search(r"func\s+spawn_tracer\s*\(", gd_text), (
        "vfx_manager.gd does not contain a definition for 'spawn_tracer'"
    )


def test_draw_tracer_exists_in_vfx_manager() -> None:
    """vfx_manager.gd must contain a function definition for _draw_tracer."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    gd_text = VFX_MANAGER.read_text(encoding="utf-8")
    assert re.search(r"func\s+_draw_tracer\s*\(", gd_text), (
        "vfx_manager.gd does not contain a definition for '_draw_tracer'"
    )


# ---------------------------------------------------------------------------
# Tests — Phase 3: combat_visual_controller.gd
# ---------------------------------------------------------------------------


def test_combat_visual_controller_file_exists() -> None:
    """combat_visual_controller.gd must exist."""
    assert COMBAT_VISUAL_CONTROLLER.exists(), (
        f"Required file missing: {COMBAT_VISUAL_CONTROLLER}"
    )


def test_combat_visual_controller_has_spawn_combat_event_caller() -> None:
    """combat_visual_controller.gd must call vfx_manager.spawn_combat_event."""
    assert COMBAT_VISUAL_CONTROLLER.exists(), f"Required file missing: {COMBAT_VISUAL_CONTROLLER}"
    gd_text = COMBAT_VISUAL_CONTROLLER.read_text(encoding="utf-8")
    assert "spawn_combat_event" in gd_text, (
        "combat_visual_controller.gd does not reference spawn_combat_event"
    )


def test_combat_visual_controller_has_event_types() -> None:
    """combat_visual_controller.gd must define all 6 required event types."""
    assert COMBAT_VISUAL_CONTROLLER.exists(), f"Required file missing: {COMBAT_VISUAL_CONTROLLER}"
    gd_text = COMBAT_VISUAL_CONTROLLER.read_text(encoding="utf-8")
    required_events = {
        "attack_started",
        "projectile_fired",
        "hit_confirmed",
        "shield_hit",
        "unit_died",
        "building_damaged",
    }
    for event_type in required_events:
        assert event_type in gd_text, (
            f"combat_visual_controller.gd missing event type: '{event_type}'"
        )


def test_spawn_combat_event_exists_in_vfx_manager() -> None:
    """vfx_manager.gd must contain a function definition for spawn_combat_event."""
    assert VFX_MANAGER.exists(), f"Required file missing: {VFX_MANAGER}"
    gd_text = VFX_MANAGER.read_text(encoding="utf-8")
    assert re.search(r"func\s+spawn_combat_event\s*\(", gd_text), (
        "vfx_manager.gd does not contain a definition for 'spawn_combat_event'"
    )


def test_required_combat_profiles_exist() -> None:
    """The six combat profiles used by _COMBAT_PAIRS must all exist in vfx_catalog.json."""
    catalog = _load_json(VFX_CATALOG)
    profiles = catalog.get("profiles", {})
    required = ["terran_ballistic", "terran_explosive", "terran_flame", "zerg_melee", "zerg_acid", "protoss_psi"]
    for name in required:
        assert name in profiles, f"VFX profile '{name}' missing from vfx_catalog.json"
