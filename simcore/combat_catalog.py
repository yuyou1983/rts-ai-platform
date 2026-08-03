"""Combat mechanics catalog — single source of truth for weapon stats.

Provides load_weapon_catalog() and weapon_spec_for_target() for the runtime
to resolve weapon mechanics by semantic weapon_id. The catalog is loaded
from data/combat/weapons.json and cached.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[1]
WEAPONS_PATH = REPO / "data/combat/weapons.json"


@lru_cache(maxsize=1)
def load_weapon_catalog() -> Mapping[str, Mapping[str, Any]]:
    """Load and cache the weapon mechanics catalog."""
    with open(WEAPONS_PATH) as f:
        return json.load(f)


def weapon_id_for_target(entity: Mapping[str, Any], target_domain: str) -> str | None:
    """Get the semantic weapon_id for attacking a given domain (ground/air)."""
    key = "weapon_id_air" if target_domain == "air" else "weapon_id_ground"
    value = entity.get(key)
    return str(value) if value else None


def weapon_spec_for_target(entity: Mapping[str, Any], target_domain: str) -> Mapping[str, Any]:
    """Get the full weapon spec for attacking a given domain.

    Raises ValueError if the entity has no weapon for the domain or
    the semantic weapon_id is not in the catalog.
    """
    weapon_id = weapon_id_for_target(entity, target_domain)
    if not weapon_id:
        raise ValueError(f"{entity.get('unit_type')} has no weapon for {target_domain}")
    catalog = load_weapon_catalog()
    if weapon_id not in catalog:
        raise ValueError(f"unknown semantic weapon_id: {weapon_id}")
    return catalog[weapon_id]
