"""Comprehensive validation tests for the unit type catalog.

Ensures structural integrity, referential consistency, and value-domain
correctness of unit_type_catalog.json and its cross-references to
units.json, presentation_manifest.json, and vfx_catalog.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

UNIT_TYPE_CATALOG = REPO_ROOT / "godot" / "resources" / "unit_type_catalog.json"
UNITS_JSON = REPO_ROOT / "data" / "units" / "units.json"
PRESENTATION_MANIFEST = REPO_ROOT / "godot" / "resources" / "presentation_manifest.json"
VFX_CATALOG = REPO_ROOT / "godot" / "resources" / "vfx" / "vfx_catalog.json"

REQUIRED_FIELDS = {
    "unit_id",
    "race",
    "domain",
    "kind",
    "role",
    "tier",
    "production_building",
    "presentation_key",
    "vfx_profile",
    "selection_class",
    "test_mode_group",
}

VALID_RACES = {"terran", "zerg", "protoss"}
VALID_DOMAINS = {"ground", "air"}
VALID_KINDS = {"unit", "building"}
VALID_ROLES = {
    "worker", "infantry", "vehicle", "air", "caster", "siege", "support",
    "production", "defense", "tech", "supply", "special",
}
VALID_TIERS = {"basic", "advanced", "tech"}
VALID_SELECTION_CLASSES = {"small", "large", "building", "air"}
WORKER_NAMES = {"SCV", "Drone", "Probe"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict[str, Any]:
    assert path.exists(), f"Required file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_entries(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return only data entries (skip _meta)."""
    return {k: v for k, v in catalog.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Tests — file-level
# ---------------------------------------------------------------------------


def test_catalog_file_exists_and_valid_json() -> None:
    """unit_type_catalog.json must exist and load as a valid JSON dict."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    assert isinstance(catalog, dict), "Catalog root must be a dict"


# ---------------------------------------------------------------------------
# Tests — required fields
# ---------------------------------------------------------------------------


def test_required_fields_present() -> None:
    """Every catalog entry must contain all 11 required fields."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        missing = REQUIRED_FIELDS - set(entry.keys())
        assert not missing, (
            f"Entry '{key}' missing required fields: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Tests — value domains
# ---------------------------------------------------------------------------


def test_race_values() -> None:
    """Every entry race must be one of 'terran', 'zerg', 'protoss'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        race = entry["race"]
        assert race in VALID_RACES, (
            f"Entry '{key}' has invalid race='{race}', "
            f"expected one of {sorted(VALID_RACES)}"
        )


def test_domain_values() -> None:
    """Every entry domain must be one of 'ground', 'air'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        domain = entry["domain"]
        assert domain in VALID_DOMAINS, (
            f"Entry '{key}' has invalid domain='{domain}', "
            f"expected one of {sorted(VALID_DOMAINS)}"
        )


def test_kind_values() -> None:
    """Every entry kind must be one of 'unit', 'building'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        kind = entry["kind"]
        assert kind in VALID_KINDS, (
            f"Entry '{key}' has invalid kind='{kind}', "
            f"expected one of {sorted(VALID_KINDS)}"
        )


def test_role_values() -> None:
    """Every entry role must be one of the allowed role values."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        role = entry["role"]
        assert role in VALID_ROLES, (
            f"Entry '{key}' has invalid role='{role}', "
            f"expected one of {sorted(VALID_ROLES)}"
        )


def test_tier_values() -> None:
    """Every entry tier must be one of 'basic', 'advanced', 'tech'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        tier = entry["tier"]
        assert tier in VALID_TIERS, (
            f"Entry '{key}' has invalid tier='{tier}', "
            f"expected one of {sorted(VALID_TIERS)}"
        )


# ---------------------------------------------------------------------------
# Tests — internal consistency
# ---------------------------------------------------------------------------


def test_unit_ids_match_keys() -> None:
    """Each entry's unit_id must match its dict key."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        unit_id = entry["unit_id"]
        assert unit_id == key, (
            f"Entry key='{key}' has unit_id='{unit_id}', expected match"
        )


# ---------------------------------------------------------------------------
# Tests — cross-reference: units.json coverage
# ---------------------------------------------------------------------------


def test_units_json_coverage() -> None:
    """Every unit name in units.json (all races) must have a catalog entry
    with kind='unit'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    units_data = _load_json(UNITS_JSON)

    # Collect all unit names from units.json across all races
    units_json_names: set[str] = set()
    for race_key in ("terran", "zerg", "protoss"):
        race_units = units_data.get(race_key, {})
        units_json_names.update(race_units.keys())

    # Check each units.json name has a catalog entry with kind="unit"
    missing: list[str] = []
    wrong_kind: list[str] = []
    for name in sorted(units_json_names):
        if name not in entries:
            missing.append(name)
        elif entries[name]["kind"] != "unit":
            wrong_kind.append(
                f"{name} (kind={entries[name]['kind']})"
            )

    assert not missing, (
        f"Units in units.json missing from catalog: {missing}"
    )
    assert not wrong_kind, (
        f"Units in units.json with wrong kind in catalog: {wrong_kind}"
    )


# ---------------------------------------------------------------------------
# Tests — cross-reference: presentation_manifest.json
# ---------------------------------------------------------------------------


def test_presentation_key_resolvable() -> None:
    """Every entry's presentation_key must exist in either unit_visuals or
    building_visuals of presentation_manifest.json (based on kind)."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    manifest = _load_json(PRESENTATION_MANIFEST)

    unit_visuals = set(manifest.get("unit_visuals", {}).keys())
    building_visuals = set(manifest.get("building_visuals", {}).keys())

    for key, entry in entries.items():
        pk = entry["presentation_key"]
        kind = entry["kind"]
        if kind == "unit":
            assert pk in unit_visuals, (
                f"Entry '{key}' (kind=unit) presentation_key='{pk}' "
                f"not found in presentation_manifest unit_visuals"
            )
        elif kind == "building":
            assert pk in building_visuals, (
                f"Entry '{key}' (kind=building) presentation_key='{pk}' "
                f"not found in presentation_manifest building_visuals"
            )


# ---------------------------------------------------------------------------
# Tests — cross-reference: vfx_catalog.json
# ---------------------------------------------------------------------------


def test_vfx_profile_resolvable() -> None:
    """For entries where vfx_profile != 'none', the profile must exist in
    vfx_catalog.json['profiles']."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    vfx = _load_json(VFX_CATALOG)

    valid_profiles = set(vfx.get("profiles", {}).keys())

    for key, entry in entries.items():
        profile = entry["vfx_profile"]
        if profile == "none":
            continue
        assert profile in valid_profiles, (
            f"Entry '{key}' vfx_profile='{profile}' "
            f"not found in vfx_catalog profiles"
        )


# ---------------------------------------------------------------------------
# Tests — selection_class
# ---------------------------------------------------------------------------


def test_selection_class_values() -> None:
    """Every entry selection_class must be one of 'small', 'large',
    'building', 'air'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)
    for key, entry in entries.items():
        sc = entry["selection_class"]
        assert sc in VALID_SELECTION_CLASSES, (
            f"Entry '{key}' has invalid selection_class='{sc}', "
            f"expected one of {sorted(VALID_SELECTION_CLASSES)}"
        )


# ---------------------------------------------------------------------------
# Tests — test_mode_group format
# ---------------------------------------------------------------------------


def test_test_mode_group_format() -> None:
    """Every entry test_mode_group must match '{race}_{kind}s' pattern."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)

    pattern = re.compile(r"^(terran|zerg|protoss)_(unit|building)s$")

    for key, entry in entries.items():
        tmg = entry["test_mode_group"]
        assert pattern.match(tmg), (
            f"Entry '{key}' test_mode_group='{tmg}' "
            f"does not match '{{race}}_{{kind}}s' pattern"
        )

        # Also verify it is consistent with the entry's own race and kind
        race = entry["race"]
        kind = entry["kind"]
        expected = f"{race}_{kind}s"
        assert tmg == expected, (
            f"Entry '{key}' test_mode_group='{tmg}' "
            f"does not match expected '{expected}' "
            f"(race='{race}', kind='{kind}')"
        )


# ---------------------------------------------------------------------------
# Tests — semantic constraints
# ---------------------------------------------------------------------------


def test_building_entries_have_ground_domain() -> None:
    """All entries with kind='building' must have domain='ground'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)

    violations: list[str] = []
    for key, entry in entries.items():
        if entry["kind"] == "building" and entry["domain"] != "ground":
            violations.append(
                f"{key} (domain={entry['domain']})"
            )

    assert not violations, (
        f"Buildings with non-ground domain: {violations}"
    )


def test_worker_entries_have_worker_role() -> None:
    """Units with names SCV/Drone/Probe must have role='worker'."""
    catalog = _load_json(UNIT_TYPE_CATALOG)
    entries = _catalog_entries(catalog)

    for name in WORKER_NAMES:
        if name not in entries:
            continue
        role = entries[name]["role"]
        assert role == "worker", (
            f"Worker unit '{name}' has role='{role}', expected 'worker'"
        )
