"""Projectile system: advance, track, and resolve projectile hits each tick.

Projectile types:
  - bullet:  instant hit-scan (Marine, Vulture)
  - missile: tracking projectile (Goliath, Missile Turret)
  - laser:   instant line (Dragoon)
  - plasma:  arcing projectile (Reaver scarab)
  - spore:   seeking spore (Spore Colony)

On hit: apply damage, check kill, spawn effect marker.
Projectiles with no valid target self-destruct after 30 ticks.
"""
from __future__ import annotations

import math
from typing import Any

# ─── Constants ───────────────────────────────────────────────

PROJECTILE_SELF_DESTRUCT_TICKS = 30
PROJECTILE_HIT_DISTANCE = 1.5  # world units to count as "arrived"

# ─── Creation ────────────────────────────────────────────────

_next_proj_id: int = 0


def create_projectile(
    owner: str,
    target_id: str,
    pos_x: float,
    pos_y: float,
    speed: float,
    damage: float,
    damage_type: str,
    projectile_type: str = "bullet",
) -> dict[str, Any]:
    """Create a new projectile entity dict."""
    global _next_proj_id
    _next_proj_id += 1
    return {
        "id": f"proj_{_next_proj_id}",
        "owner": owner,
        "pos_x": pos_x,
        "pos_y": pos_y,
        "target_id": target_id,
        "speed": speed,
        "damage": damage,
        "damage_type": damage_type,
        "projectile_type": projectile_type,
        "age": 0,
        "alive": True,
        "effect": "",
    }


# ─── Processing ──────────────────────────────────────────────

def process_projectiles(
    entities: dict[str, Any],
    tick: int,
) -> dict[str, Any]:
    """Advance all projectiles, resolve hits, remove spent/old projectiles.

    Returns updated entities dict (including any new effect markers and
    with dead targets removed).
    """
    result = dict(entities)
    to_remove: set[str] = set()
    new_effects: dict[str, Any] = {}

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

        # For instant types (bullet, laser), immediately hit
        ptype = proj.get("projectile_type", "bullet")
        if ptype in ("bullet", "laser"):
            # Instant hit
            new_health = target["health"] - proj["damage"]
            result[target_id] = {**target, "health": new_health}
            if new_health <= 0:
                to_remove.add(target_id)
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
            # Hit the target
            new_health = target["health"] - proj["damage"]
            result[target_id] = {**target, "health": new_health}
            if new_health <= 0:
                to_remove.add(target_id)
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