"""Combat runtime — attack cycle routing based on delivery type.

This module provides ``execute_attack_cycle()``, the single entry point for
resolving a unit's attack against a target.  It routes to different resolution
paths based on the weapon's ``delivery_type``:

  melee / hitscan → immediate damage via ``resolve_weapon_impact()``
  projectile / tracking → spawn projectile entity, damage on arrival
  chain → spawn primary projectile, bounces on arrival
  area_periodic → handled by spell lifecycle (Task 7)

The caller (``resolve_combat``) is responsible for target validation,
range checks, cooldown gating, and high-ground miss rolls.  This function
handles only the damage/projectile routing and event emission.
"""
from __future__ import annotations

from typing import Any

from simcore.combat_events import (
    ATTACK_STARTED,
    PROJECTILE_SPAWNED,
    append_combat_event,
)
from simcore.combat_catalog import load_weapon_catalog, weapon_spec_for_target
from simcore.combat_resolution import resolve_weapon_impact, KillFeed
from simcore.projectile import create_projectile

# Delivery types that require a projectile entity (delayed damage)
_PROJECTILE_DELIVERY_TYPES = frozenset({"projectile", "tracking", "chain"})


def get_delivery_type(entity: dict[str, Any], weapon_id: str) -> str:
    """Look up the delivery_type for an entity's weapon from the catalog."""
    catalog = load_weapon_catalog()
    spec = catalog.get(weapon_id, {})
    return spec.get("delivery_type", "hitscan")


def execute_attack_cycle(
    entities: dict[str, Any],
    *,
    attacker_id: str,
    target_id: str,
    tick: int,
    combat_events: list[dict] | None = None,
    kill_feed: KillFeed | None = None,
    weapon_id: str = "",
    weapon_type: str = "normal",
    base_damage: float = 0.0,
    attack_range: float = 6.0,
    hit_count: int = 1,
    delivery_type: str = "hitscan",
    attacker_pos: tuple[float, float] = (0.0, 0.0),
    target_pos: tuple[float, float] = (0.0, 0.0),
    missed: bool = False,
    seq: int = 0,
) -> tuple[dict[str, Any], set[str]]:
    """Route a single attack cycle based on delivery type.

    For melee/hitscan: emit attack_started, resolve damage immediately.
    For projectile/tracking/chain: emit attack_started + projectile_spawned,
        create a projectile entity, and return without applying damage.

    Returns (updated_entities, set_of_removed_ids).
    """
    fought = entities
    to_remove: set[str] = set()

    # ── Emit attack_started event ──
    if combat_events is not None:
        append_combat_event(
            combat_events,
            tick=tick,
            event_type=ATTACK_STARTED,
            attacker_id=attacker_id,
            target_id=target_id,
            weapon_id=weapon_id,
            source_x=attacker_pos[0],
            source_y=attacker_pos[1],
            target_x=target_pos[0],
            target_y=target_pos[1],
            delivery_type=delivery_type,
            weapon_type=weapon_type,
            base_damage=float(base_damage),
            hit_count=hit_count,
        )

    # ── Route based on delivery type ──
    if delivery_type in _PROJECTILE_DELIVERY_TYPES:
        # Spawn a projectile entity — damage will be applied on arrival
        catalog = load_weapon_catalog()
        spec = catalog.get(weapon_id, {})
        proj_speed = spec.get("projectile_speed_world_per_tick", 5.0)

        # Determine projectile type
        if delivery_type == "tracking":
            proj_type = "missile"
        elif delivery_type == "chain":
            proj_type = "bullet"  # chain uses bullet, bounces handled on impact
        else:
            proj_type = "bullet"

        proj = create_projectile(
            owner=str(fought.get(attacker_id, {}).get("owner", 0)),
            target_id=target_id,
            pos_x=attacker_pos[0],
            pos_y=attacker_pos[1],
            speed=proj_speed,
            damage=base_damage,
            damage_type=weapon_type,
            projectile_type=proj_type,
            tick=tick,
            seq=seq,
            weapon_id=weapon_id,
            weapon_type=weapon_type,
            attacker_id=attacker_id,
        )

        # Add projectile to entities
        fought[proj["id"]] = proj

        # Emit projectile_spawned event
        if combat_events is not None:
            append_combat_event(
                combat_events,
                tick=tick,
                event_type=PROJECTILE_SPAWNED,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon_id,
                projectile_id=proj["id"],
                source_x=attacker_pos[0],
                source_y=attacker_pos[1],
                target_x=target_pos[0],
                target_y=target_pos[1],
                delivery_type=delivery_type,
            )
        # No damage applied — projectile will deliver it on arrival
        return fought, to_remove

    # ── Melee / hitscan: immediate resolution ──
    if missed:
        # Emit a miss event
        if combat_events is not None:
            from simcore.combat_resolution import get_armor_type
            target = fought.get(target_id, {})
            append_combat_event(
                combat_events,
                tick=tick,
                event_type="impact_resolved",
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon_id,
                source_x=attacker_pos[0],
                source_y=attacker_pos[1],
                target_x=target_pos[0],
                target_y=target_pos[1],
                delivery_type=delivery_type,
                weapon_type=weapon_type,
                base_damage=float(base_damage),
                final_damage=0.0,
                damage_multiplier=1.0,
                shield_damage=0.0,
                health_damage=0.0,
                chain_index=0,
                is_splash=False,
                splash_fraction=1.0,
                killed=False,
                missed=True,
                armor_type=get_armor_type(target) if target else "medium",
                armor_value=float(target.get("armor", 0)) if target else 0.0,
                shield_armor_value=0.0,
                hit_index=0,
                hit_count=hit_count,
            )
        return fought, to_remove

    # Resolve via the unified damage path
    per_hit_dmg = base_damage / hit_count if hit_count > 0 else base_damage
    for hit_idx in range(hit_count):
        target = fought.get(target_id)
        if target is None or target.get("health", 0) <= 0:
            break

        fought, hit_removed = resolve_weapon_impact(
            fought,
            attacker_id=attacker_id,
            target_id=target_id,
            weapon_id=weapon_id,
            weapon_type=weapon_type,
            base_damage=per_hit_dmg,
            tick=tick,
            combat_events=combat_events,
            kill_feed=kill_feed,
            delivery_type=delivery_type,
            attacker_pos=attacker_pos,
            target_pos=target_pos,
            hit_index=hit_idx,
            hit_count=hit_count,
        )
        to_remove.update(hit_removed)
        if target_id in to_remove:
            break

    return fought, to_remove
