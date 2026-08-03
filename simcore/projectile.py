"""Projectile system: advance, track, and resolve projectile hits each tick.

Projectile types:
  - bullet:  instant hit-scan (Marine, Vulture)
  - missile: tracking projectile (Goliath, Missile Turret)
  - laser:   instant line (Dragoon)
  - plasma:  arcing projectile (Reaver scarab)
  - spore:   seeking spore (Spore Colony)

On hit: resolve damage via combat_resolution.resolve_weapon_impact(), check kill,
emit combat events.  Projectiles with no valid target self-destruct after 30 ticks.

Deterministic IDs: ``proj_{tick}_{seq}`` — no global counter, reproducible across
runs and replay-safe.
"""
from __future__ import annotations

import math
from typing import Any

from simcore.combat_events import (
    PROJECTILE_SPAWNED,
    append_combat_event,
    IMPACT_RESOLVED,
)
from simcore.combat_resolution import (
    KillFeed,
    resolve_weapon_impact,
)
from simcore.combat_catalog import load_weapon_catalog

# ─── Constants ───────────────────────────────────────────────

PROJECTILE_SELF_DESTRUCT_TICKS = 30
PROJECTILE_HIT_DISTANCE = 1.5  # world units to count as "arrived"


def _apply_chain_bounce(
    result: dict[str, Any],
    *,
    attacker_id: str,
    primary_target_id: str,
    weapon_id: str,
    weapon_type: str,
    base_damage: float,
    tick: int,
    combat_events: list[dict] | None,
    kill_feed: KillFeed,
    attacker_owner: str,
) -> tuple[dict[str, Any], set[str]]:
    """Apply chain (bounce) damage after primary target is hit.

    Uses the weapon catalog's chain_fractions and chain_radius to find
    nearby enemies and resolve bounce damage via resolve_weapon_impact().
    """
    catalog = load_weapon_catalog()
    wspec = catalog.get(weapon_id, {})
    fractions = wspec.get("chain_fractions")
    if not fractions or len(fractions) <= 1:
        return result, set()

    radius = wspec.get("chain_radius", 3)
    max_targets = wspec.get("chain_max_targets", 3)
    to_remove: set[str] = set()
    already_hit = {primary_target_id}
    primary = result.get(primary_target_id)
    if primary is None:
        return result, set()

    bounce_origin_x = primary.get("pos_x", 0.0)
    bounce_origin_y = primary.get("pos_y", 0.0)

    for chain_idx in range(1, min(len(fractions), max_targets + 1)):
        frac = fractions[chain_idx]
        bounce_dmg = base_damage * frac

        # Find nearest enemy not yet hit
        best_dist = float("inf")
        best_id = None
        best_ent = None
        for eid, ent in result.items():
            if eid in already_hit or eid == attacker_id:
                continue
            if ent.get("entity_type") in ("resource", "projectile", "effect"):
                continue
            if ent.get("health", 0) <= 0:
                continue
            e_owner = str(ent.get("owner", 0))
            if e_owner == attacker_owner or e_owner == "0":
                continue
            dx = ent.get("pos_x", 0.0) - bounce_origin_x
            dy = ent.get("pos_y", 0.0) - bounce_origin_y
            d = math.sqrt(dx * dx + dy * dy)
            if d <= radius and d < best_dist:
                best_dist = d
                best_id = eid
                best_ent = ent

        if best_id is None:
            break

        already_hit.add(best_id)
        result, hit_removed = resolve_weapon_impact(
            result,
            attacker_id=attacker_id,
            target_id=best_id,
            weapon_id=weapon_id,
            weapon_type=weapon_type,
            base_damage=bounce_dmg,
            tick=tick,
            combat_events=combat_events,
            kill_feed=kill_feed,
            delivery_type="chain",
            attacker_pos=(bounce_origin_x, bounce_origin_y),
            target_pos=(best_ent.get("pos_x", 0.0), best_ent.get("pos_y", 0.0)),
            chain_index=chain_idx,
            splash_fraction=frac,
        )
        to_remove.update(hit_removed)

    return result, to_remove


# ─── Creation ────────────────────────────────────────────────


def create_projectile(
    owner: str,
    target_id: str,
    pos_x: float,
    pos_y: float,
    speed: float,
    damage: float,
    damage_type: str,
    projectile_type: str = "bullet",
    *,
    tick: int = 0,
    seq: int = 0,
    weapon_id: str = "",
    weapon_type: str = "normal",
    attacker_id: str = "",
) -> dict[str, Any]:
    """Create a new projectile entity dict with a deterministic ID.

    Args:
        tick: Current simulation tick (for deterministic ID).
        seq: Per-tick sequence number (for deterministic ID).
        weapon_id: Weapon identifier for combat event emission.
        weapon_type: Damage type for size multiplier lookup.
        attacker_id: ID of the firing unit (for kill attribution).

    Returns:
        Projectile entity dict.
    """
    proj_id = f"proj_{tick}_{seq}" if tick > 0 else f"proj_{seq}"
    return {
        "id": proj_id,
        "owner": owner,
        "entity_type": "projectile",
        "pos_x": pos_x,
        "pos_y": pos_y,
        "target_id": target_id,
        "speed": speed,
        "damage": damage,
        "damage_type": damage_type,
        "projectile_type": projectile_type,
        "weapon_id": weapon_id,
        "weapon_type": weapon_type,
        "attacker_id": attacker_id,
        "age": 0,
        "alive": True,
        "effect": "",
    }


# ─── Processing ──────────────────────────────────────────────


def process_projectiles(
    entities: dict[str, Any],
    tick: int,
    *,
    combat_events: list[dict] | None = None,
    kill_feed: KillFeed | None = None,
) -> dict[str, Any]:
    """Advance all projectiles, resolve hits, remove spent/old projectiles.

    Damage resolution is delegated to ``resolve_weapon_impact`` — this function
    does NOT apply damage directly.  This ensures shield, armor, size multiplier,
    and combat event emission all go through the single unified path.

    Args:
        entities: Entity dict (mutated via copy-on-write).
        tick: Current simulation tick.
        combat_events: Event list to append to (or None to skip events).
        kill_feed: KillFeed tracker (or None to skip).

    Returns:
        Updated entities dict (including any new effect markers and
        with dead targets removed).
    """
    result = dict(entities)
    to_remove: set[str] = set()
    new_effects: dict[str, Any] = {}

    if kill_feed is None:
        kill_feed = KillFeed()

    # Collect all projectile entities
    projectiles = {
        eid: e for eid, e in result.items()
        if e.get("projectile_type") and e.get("alive", True)
    }

    for pid, proj in projectiles.items():
        age = proj.get("age", 0) + 1
        proj = {**proj, "age": age}

        target_id = proj.get("target_id", "")
        target = result.get(target_id)

        # Self-destruct if target is gone or too old
        if target is None or target.get("health", 0) <= 0 or age > PROJECTILE_SELF_DESTRUCT_TICKS:
            to_remove.add(pid)
            # Spawn a fizz effect marker
            new_effects[f"fx_{pid}"] = {
                "id": f"fx_{pid}",
                "owner": 0,
                "pos_x": proj["pos_x"],
                "pos_y": proj["pos_y"],
                "entity_type": "effect",
                "effect_type": "projectile_fizz",
                "tick_created": tick,
                "duration": 5,
            }
            continue

        attacker_id = proj.get("attacker_id", "")
        weapon_id = proj.get("weapon_id", "") or proj.get("damage_type", "unknown")
        weapon_type = proj.get("weapon_type", "normal")
        base_damage = proj.get("damage", 0)
        proj_type = proj.get("projectile_type", "bullet")

        # For instant types (bullet, laser), immediately resolve impact
        if proj_type in ("bullet", "laser"):
            result, hit_removed = resolve_weapon_impact(
                result,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon_id,
                weapon_type=weapon_type,
                base_damage=base_damage,
                tick=tick,
                combat_events=combat_events,
                kill_feed=kill_feed,
                delivery_type="projectile",
                attacker_pos=(proj.get("pos_x", 0.0), proj.get("pos_y", 0.0)),
                target_pos=(target.get("pos_x", 0.0), target.get("pos_y", 0.0)),
            )
            to_remove.update(hit_removed)
            # Chain bounce if weapon has chain properties
            result, chain_removed = _apply_chain_bounce(
                result,
                attacker_id=attacker_id,
                primary_target_id=target_id,
                weapon_id=weapon_id,
                weapon_type=weapon_type,
                base_damage=base_damage,
                tick=tick,
                combat_events=combat_events,
                kill_feed=kill_feed,
                attacker_owner=str(proj.get("owner", "0")),
            )
            to_remove.update(chain_removed)
            # Effect marker on target
            new_effects[f"fx_{pid}"] = {
                "id": f"fx_{pid}",
                "owner": 0,
                "pos_x": target["pos_x"],
                "pos_y": target["pos_y"],
                "entity_type": "effect",
                "effect_type": "hit",
                "tick_created": tick,
                "duration": 3,
            }
            to_remove.add(pid)
            continue

        # For tracking/arc types, move toward target
        tx, ty = target["pos_x"], target["pos_y"]
        dx = tx - proj["pos_x"]
        dy = ty - proj["pos_y"]
        dist = math.sqrt(dx * dx + dy * dy)

        if dist <= PROJECTILE_HIT_DISTANCE:
            # Hit the target — resolve via unified path
            result, hit_removed = resolve_weapon_impact(
                result,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon_id,
                weapon_type=weapon_type,
                base_damage=base_damage,
                tick=tick,
                combat_events=combat_events,
                kill_feed=kill_feed,
                delivery_type="projectile",
                attacker_pos=(proj.get("pos_x", 0.0), proj.get("pos_y", 0.0)),
                target_pos=(target.get("pos_x", 0.0), target.get("pos_y", 0.0)),
            )
            to_remove.update(hit_removed)
            new_effects[f"fx_{pid}"] = {
                "id": f"fx_{pid}",
                "owner": 0,
                "pos_x": target["pos_x"],
                "pos_y": target["pos_y"],
                "entity_type": "effect",
                "effect_type": "hit",
                "tick_created": tick,
                "duration": 3,
            }
            to_remove.add(pid)
            continue

        speed = proj.get("speed", 10.0)
        if dist > 0:
            move_x = dx / dist * speed
            move_y = dy / dist * speed
        else:
            move_x, move_y = 0.0, 0.0

        result[pid] = {
            **proj,
            "pos_x": proj["pos_x"] + move_x,
            "pos_y": proj["pos_y"] + move_y,
        }

    # Remove spent projectiles and dead targets
    for eid in to_remove:
        result.pop(eid, None)

    # Add effect markers
    result.update(new_effects)

    # Expire old effect markers
    expired: set[str] = set()
    for eid, e in result.items():
        if e.get("entity_type") == "effect":
            age = tick - e.get("tick_created", tick)
            if age >= e.get("duration", 5):
                expired.add(eid)
    for eid in expired:
        result.pop(eid, None)

    return result
