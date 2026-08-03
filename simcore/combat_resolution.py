"""Unified combat resolution — single entry point for damage, shield, and kill logic.

This module is the **only** place that applies damage to entities. It replaces
the duplicated shield→health→armor logic that was previously inlined in
``rules.resolve_combat`` and ``rules._apply_splash``.

Resolution order follows OpenBW ``weapon_deal_damage()``:

1. Apply chain/splash divisor to base damage.
2. Shield absorbs first (no size multiplier on shield).
3. Remaining damage → health: subtract armor, apply size multiplier.
4. SC1 minimum damage rule after shield absorption.
5. Each hit produces one ``impact_resolved`` event.
6. Each death produces one ``unit_destroyed`` event.

``final_damage = shield_damage + health_damage`` (never the theoretical pre-truncation amount).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from simcore.combat_events import (
    IMPACT_RESOLVED,
    UNIT_DESTROYED,
    append_combat_event,
)

# ─── Damage Matrix ──────────────────────────────────────────

_DAMAGE_MATRIX_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "combat" / "combat.json"
)

_WEAPON_TYPE_MAP = {
    "concussive": 0,   # NORMAL → 100% small, 50% medium, 25% large
    "explosive": 1,    # BURST  → 50% small, 75% medium, 100% large
    "normal": 2,       # WAVE   → 100% to all sizes
    "independent": 2,  # same as normal (SC1 DAT type 0)
    "spells": 2,       # spells ignore armor type
    "splash": 2,       # splash uses the weapon's own type, but default to normal
    "melee": 2,        # melee does full damage
    "none": 2,
}

_ARMOR_TYPE_MAP = {
    "light": 0,
    "medium": 1,
    "heavy": 2,
}

_damage_cache: dict | None = None


def _load_damage_matrix() -> dict:
    global _damage_cache
    if _damage_cache is not None:
        return _damage_cache
    try:
        text = _DAMAGE_MATRIX_PATH.read_text(encoding="utf-8")
        _damage_cache = json.loads(text)
    except (FileNotFoundError, json.JSONDecodeError):
        _damage_cache = {}
    return _damage_cache


def get_damage_multiplier(weapon_type: str, target_armor_type: str) -> float:
    """Return the SC1 size multiplier (0.25–1.0) for weapon vs armor type.

    This is purely the damage-matrix percentage divided by 100 — it does NOT
    include armor reduction, shield absorption, or any other modifiers.
    """
    data = _load_damage_matrix()
    matrix = data.get("damageMatrix", [[100, 50, 25], [50, 75, 100], [100, 100, 100]])
    attack_idx = _WEAPON_TYPE_MAP.get(weapon_type, 2)
    armor_idx = _ARMOR_TYPE_MAP.get(target_armor_type, 1)
    if 0 <= attack_idx < len(matrix) and 0 <= armor_idx < len(matrix[attack_idx]):
        return matrix[attack_idx][armor_idx] / 100.0
    return 1.0


def calculate_damage(
    base_damage: float,
    weapon_type: str,
    target_armor: int,
    target_armor_type: str,
) -> float:
    """Calculate final health damage using the damage matrix.

    Formula: (base_damage × multiplier% / 100) - armor
    Minimum: minDamage from combat.json (default 0.5)

    Note: This does NOT account for shield absorption. Use
    ``resolve_weapon_impact`` for the full shield→health resolution.
    """
    data = _load_damage_matrix()
    matrix = data.get("damageMatrix", [[100, 50, 25], [50, 75, 100], [100, 100, 100]])
    min_damage = data.get("minDamage", 0.5)

    attack_idx = _WEAPON_TYPE_MAP.get(weapon_type, 2)
    armor_idx = _ARMOR_TYPE_MAP.get(target_armor_type, 1)

    if 0 <= attack_idx < len(matrix) and 0 <= armor_idx < len(matrix[attack_idx]):
        multiplier_pct = matrix[attack_idx][armor_idx]
    else:
        multiplier_pct = 100

    # OpenBW order: subtract armor BEFORE applying size multiplier
    after_armor = max(0.0, base_damage - target_armor)
    raw_damage = after_armor * multiplier_pct / 100.0
    return max(min_damage, raw_damage)


def get_armor_type(entity: dict[str, Any]) -> str:
    """Determine armor type for an entity.

    Priority:
      1. Entity's own 'armor_type' field (populated from unit_stats.json)
      2. Fallback: legacy unit-type mapping (buildings→heavy, etc.)
    """
    at = entity.get("armor_type", "")
    if at in ("light", "medium", "heavy"):
        return at

    etype = entity.get("entity_type", "")
    utype = entity.get("unit_type", "").lower() if entity.get("unit_type") else ""

    if etype == "building":
        return "heavy"

    light_units = {"worker", "soldier", "scout", "zergling", "marine", "ghost",
                   "firebat", "medic", "scourge", "broodling", "larva",
                   "probe", "zealot", "darktemplar", "observer",
                   "scv", "drone"}
    medium_units = {"hydralisk", "vulture", "goliath", "wraith", "valkyrie",
                    "mutalisk", "queen", "defiler", "corsair", "dropship",
                    "shuttle", "lurker", "infestedterran", "overlord"}
    heavy_units = {"tank", "ultralisk", "battlecruiser", "carrier", "arbitr",
                   "archon", "darkarchon", "reaver", "guardian", "devourer",
                   "vessel", "behemoth"}

    if utype in light_units or etype in light_units:
        return "light"
    elif utype in medium_units:
        return "medium"
    elif utype in heavy_units:
        return "heavy"

    if etype in ("worker", "scout"):
        return "light"

    return "medium"


# ─── KillFeed ───────────────────────────────────────────────


class KillFeed:
    """Lightweight combat statistics tracked per game."""
    def __init__(self) -> None:
        self.kills: dict[int, int] = {1: 0, 2: 0}
        self.deaths: dict[int, int] = {1: 0, 2: 0}
        self.damage_dealt: dict[int, float] = {1: 0.0, 2: 0.0}

    def record_kill(self, killer_owner: int, victim_owner: int) -> None:
        self.kills[killer_owner] = self.kills.get(killer_owner, 0) + 1
        self.deaths[victim_owner] = self.deaths.get(victim_owner, 0) + 1

    def record_damage(self, dealer_owner: int, amount: float) -> None:
        self.damage_dealt[dealer_owner] = self.damage_dealt.get(dealer_owner, 0.0) + amount

    def to_dict(self) -> dict:
        return {
            "kills": dict(self.kills),
            "deaths": dict(self.deaths),
            "damage_dealt": dict(self.damage_dealt),
        }


# ─── Unified Impact Resolution ─────────────────────────────


def resolve_weapon_impact(
    entities: dict[str, Any],
    *,
    attacker_id: str,
    target_id: str,
    weapon_id: str,
    weapon_type: str,
    base_damage: float,
    tick: int,
    combat_events: list[dict] | None = None,
    kill_feed: KillFeed | None = None,
    projectile_id: str = "",
    chain_index: int = 0,
    splash_fraction: float = 1.0,
    missed: bool = False,
    is_splash: bool = False,
    hit_index: int = 0,
    hit_count: int = 1,
    delivery_type: str = "hitscan",
    attacker_pos: tuple[float, float] = (0.0, 0.0),
    target_pos: tuple[float, float] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    """Resolve a single weapon impact: shield → health → armor → kill → events.

    This is the **sole** damage application path. It must be called once per
    hit-target pair (dual hits call it twice with different hit_index).

    Args:
        entities: Entity dict (mutated in-place via copy-on-write).
        attacker_id: ID of the attacking unit.
        target_id: ID of the target unit.
        weapon_id: Weapon identifier (e.g. "terran_c10_rifle").
        weapon_type: "normal", "explosive", "concussive", etc.
        base_damage: Pre-mitigation damage for this hit (after splash divisor).
        tick: Current simulation tick.
        combat_events: Event list to append to (or None to skip events).
        kill_feed: KillFeed tracker (or None to skip).
        projectile_id: ID of the projectile that delivered this hit (if any).
        chain_index: Chain bounce index (0 = primary, 1+ = bounces).
        splash_fraction: Fraction of base damage (1.0 for direct hit).
        missed: If True, no damage is applied; a miss event is emitted.
        is_splash: If True, this is a splash impact.
        hit_index: Index of this hit within a multi-hit attack (0-based).
        hit_count: Total hits in this attack cycle (e.g. 2 for Zealot).
        delivery_type: "hitscan", "projectile", "melee", "splash", etc.
        attacker_pos: (x, y) of the attacker at fire time.
        target_pos: (x, y) of the target at impact time (defaults to entity pos).

    Returns:
        (updated_entities, set_of_removed_ids)
    """
    fought = entities
    to_remove: set[str] = set()

    if kill_feed is None:
        kill_feed = KillFeed()

    target = fought.get(target_id)
    if target is None:
        # Target already removed — emit a miss
        missed = True

    if missed:
        if combat_events is not None and target is not None:
            _emit_impact_event(
                combat_events,
                tick=tick,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon_id,
                attacker_pos=attacker_pos,
                target_pos=target_pos or (target.get("pos_x", 0.0), target.get("pos_y", 0.0)),
                delivery_type=delivery_type,
                weapon_type=weapon_type,
                base_damage=base_damage,
                final_damage=0.0,
                shield_damage=0.0,
                health_damage=0.0,
                chain_index=chain_index,
                is_splash=is_splash,
                splash_fraction=splash_fraction,
                killed=False,
                missed=True,
                armor_type=get_armor_type(target),
                armor_value=float(target.get("armor", 0)),
                hit_index=hit_index,
                hit_count=hit_count,
            )
        return fought, to_remove

    assert target is not None  # narrowed after missed check

    target_armor = target.get("armor", 0)
    target_armor_type = get_armor_type(target)
    size_mult = get_damage_multiplier(weapon_type, target_armor_type)

    # ── Shield absorbs first (no size multiplier on shield) ──
    shield = target.get("shields", target.get("shield", 0))
    effective_damage = base_damage  # already has splash/chain divisor applied

    if shield > 0:
        shield_dmg = min(shield, effective_damage)
        remaining = effective_damage - shield_dmg
        # Remaining damage goes to health: apply armor and size multiplier
        if remaining > 0:
            # OpenBW order: armor before multiplier
            after_armor = max(0.0, remaining - target_armor)
            raw_health = after_armor * size_mult
            min_dmg = _load_damage_matrix().get("minDamage", 0.5)
            health_dmg = max(min_dmg, raw_health)
        else:
            health_dmg = 0.0
        new_shield = shield - shield_dmg
    else:
        shield_dmg = 0.0
        # No shield: full damage to health with armor and size multiplier
        after_armor = max(0.0, effective_damage - target_armor)
        raw_health = after_armor * size_mult
        min_dmg = _load_damage_matrix().get("minDamage", 0.5)
        health_dmg = max(min_dmg, raw_health)
        new_shield = shield

    # final_damage = shield_damage + health_damage (truncated by target HP)
    actual_health_dmg = min(health_dmg, float(target.get("health", 0)))
    actual_shield_dmg = min(shield_dmg, float(shield))
    final_damage = actual_shield_dmg + actual_health_dmg

    new_health = target.get("health", 0) - actual_health_dmg
    killed = new_health <= 0

    # Update entity
    fought[target_id] = {
        **target,
        "health": new_health,
        "shields": new_shield,
        "last_hit_tick": tick,
    }

    attacker = fought.get(attacker_id, {})
    attacker_owner = attacker.get("owner", 0)
    target_owner = target.get("owner", 0)

    kill_feed.record_damage(attacker_owner, final_damage)

    if killed:
        to_remove.add(target_id)
        kill_feed.record_kill(attacker_owner, target_owner)
        # Clear units targeting the dead entity
        for uid2, e2 in list(fought.items()):
            if e2.get("attack_target_id") == target_id:
                fought[uid2] = {**fought.get(uid2, e2), "attack_target_id": "", "is_idle": True}

    # ── Emit combat events ──
    if combat_events is not None:
        _emit_impact_event(
            combat_events,
            tick=tick,
            attacker_id=attacker_id,
            target_id=target_id,
            weapon_id=weapon_id,
            attacker_pos=attacker_pos,
            target_pos=target_pos or (target.get("pos_x", 0.0), target.get("pos_y", 0.0)),
            delivery_type=delivery_type,
            weapon_type=weapon_type,
            base_damage=base_damage,
            final_damage=round(final_damage, 4),
            shield_damage=round(actual_shield_dmg, 4),
            health_damage=round(actual_health_dmg, 4),
            chain_index=chain_index,
            is_splash=is_splash,
            splash_fraction=splash_fraction,
            killed=killed,
            missed=False,
            armor_type=target_armor_type,
            armor_value=float(target_armor),
            hit_index=hit_index,
            hit_count=hit_count,
        )
        if killed:
            append_combat_event(
                combat_events,
                tick=tick,
                event_type=UNIT_DESTROYED,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon_id,
            )

    return fought, to_remove


def _emit_impact_event(
    events: list[dict],
    *,
    tick: int,
    attacker_id: str,
    target_id: str,
    weapon_id: str,
    attacker_pos: tuple[float, float],
    target_pos: tuple[float, float],
    delivery_type: str,
    weapon_type: str,
    base_damage: float,
    final_damage: float,
    shield_damage: float,
    health_damage: float,
    chain_index: int,
    is_splash: bool,
    splash_fraction: float,
    killed: bool,
    missed: bool,
    armor_type: str,
    armor_value: float,
    hit_index: int,
    hit_count: int,
) -> None:
    """Append an impact_resolved combat event."""
    append_combat_event(
        events,
        tick=tick,
        event_type=IMPACT_RESOLVED,
        attacker_id=attacker_id,
        target_id=target_id,
        weapon_id=weapon_id,
        source_x=attacker_pos[0],
        source_y=attacker_pos[1],
        target_x=target_pos[0],
        target_y=target_pos[1],
        delivery_type=delivery_type,
        weapon_type=weapon_type,
        armor_type=armor_type,
        base_damage=base_damage,
        final_damage=final_damage,
        damage_multiplier=get_damage_multiplier(weapon_type, armor_type),
        shield_damage=shield_damage,
        health_damage=health_damage,
        chain_index=chain_index,
        is_splash=is_splash,
        splash_fraction=splash_fraction,
        killed=killed,
        missed=missed,
        armor_value=armor_value,
        shield_armor_value=0.0,
        hit_index=hit_index,
        hit_count=hit_count,
    )
