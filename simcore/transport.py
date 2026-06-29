"""Transport system — load/unload units into Dropship, Shuttle, Overlord, Bunker.

SC1 rules:
- Transport has cargo_capacity slots (8 for Dropship/Shuttle/Overlord, 4 for Bunker)
- Load: passenger must be same team, within pickup range, on ground (flying units can't load)
- Unload: drop passengers at transport's position; they appear on ground
- Transport death → all loaded passengers die
- Overlord requires "transport" ability (Ventral Sacs upgrade)
- Bunker: only infantry (not massive), loaded units can fire out
"""
from __future__ import annotations
import math
from typing import Any

_MAP_TILE_SIZE = 32.0
_PICKUP_RANGE = 3.0 * _MAP_TILE_SIZE   # 3 tiles — generous SC1 pickup range
_CARGO_CAPACITY = {
    "Dropship": 8,
    "Shuttle": 8,
    "Overlord": 8,
    "Bunker": 4,
}

# Units too large to fit in Bunker (massive / large ground)
_BUNKER_EXCLUDED = {"SiegeTank", "Ultralisk", "Archon", "DarkArchon", "Reaver", "Dragoon"}


def process_transport(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process load and unload commands for transport units and bunkers."""
    result = dict(entities)
    res = dict(resources)
    to_remove: set[str] = set()

    for cmd in commands:
        action = cmd.get("action", "")

        # ─── LOAD ─────────────────────────────────────────
        if action == "load":
            transport_id = cmd.get("transport_id", "")
            unit_ids = cmd.get("unit_ids", [])
            if transport_id not in result:
                continue
            transport = result[transport_id]

            # Validate transport is a transport-capable entity
            if not _is_transport(transport):
                continue
            # Overlord needs "transport" ability
            if transport.get("unit_type") == "Overlord":
                if "transport" not in transport.get("abilities", []):
                    continue

            loaded = list(transport.get("loaded_units", []))
            capacity = transport.get("cargo_capacity",
                                     _CARGO_CAPACITY.get(transport.get("unit_type", ""), 8))

            for uid in unit_ids:
                if uid not in result:
                    continue
                if len(loaded) >= capacity:
                    break  # full
                passenger = result[uid]

                # Same team
                if passenger.get("owner", 0) != transport.get("owner", 0):
                    continue
                # Can't load flying units (SC1 rule)
                if passenger.get("domain") == "air":
                    continue
                # Can't load stasis'd units
                if passenger.get("stasis"):
                    continue
                # Bunker: infantry only, exclude massive
                if transport.get("entity_type") == "building":
                    if passenger.get("unit_type", "") in _BUNKER_EXCLUDED:
                        continue

                # Range check — passenger must be near transport
                d = math.hypot(passenger["pos_x"] - transport["pos_x"],
                               passenger["pos_y"] - transport["pos_y"])
                if d > _PICKUP_RANGE:
                    continue

                # Load: remove from map, add to loaded_units
                loaded.append({
                    "id": uid,
                    "unit_type": passenger.get("unit_type", ""),
                    "owner": passenger.get("owner", 0),
                    "health": passenger["health"],
                    "max_health": passenger.get("max_health", passenger["health"]),
                    "shields": passenger.get("shields", 0),
                    "max_shields": passenger.get("max_shields", 0),
                    "attack_ground": passenger.get("attack_ground", 0),
                    "attack_air": passenger.get("attack_air", 0),
                    "attack_range_ground": passenger.get("attack_range_ground", 0),
                    "weapon_type_ground": passenger.get("weapon_type_ground", "normal"),
                    "cooldown_ground": passenger.get("cooldown_ground", 10),
                    "armor": passenger.get("armor", 0),
                    "armor_type": passenger.get("armor_type", "medium"),
                    "supply_cost": passenger.get("supply_cost", 1),
                    "domain": passenger.get("domain", "ground"),
                })
                to_remove.add(uid)

            if loaded != transport.get("loaded_units", []):
                result[transport_id] = {**result.get(transport_id, transport),
                                        "loaded_units": loaded,
                                        "cargo_used": len(loaded)}

        # ─── UNLOAD ───────────────────────────────────────
        elif action == "unload":
            transport_id = cmd.get("transport_id", "")
            if transport_id not in result:
                continue
            transport = result[transport_id]
            if not _is_transport(transport):
                continue

            loaded = list(transport.get("loaded_units", []))
            target_x = cmd.get("target_x", transport["pos_x"])
            target_y = cmd.get("target_y", transport["pos_y"])
            specific_ids = cmd.get("unit_ids", [])  # empty = unload all

            to_spawn: list[dict] = []
            remaining = []
            for p in loaded:
                if specific_ids and p["id"] not in specific_ids:
                    remaining.append(p)
                    continue
                # Reconstruct a unit entity at the unload position
                spawn = {
                    "id": p["id"],
                    "entity_id": p["id"],
                    "owner": p["owner"],
                    "entity_type": "unit",
                    "unit_type": p["unit_type"],
                    "pos_x": target_x,
                    "pos_y": target_y,
                    "health": p["health"],
                    "max_health": p["max_health"],
                    "shields": p["shields"],
                    "max_shields": p.get("max_shields", 0),
                    "attack_ground": p.get("attack_ground", 0),
                    "attack_air": p.get("attack_air", 0),
                    "attack_range_ground": p.get("attack_range_ground", 0),
                    "weapon_type_ground": p.get("weapon_type_ground", "normal"),
                    "cooldown_ground": p.get("cooldown_ground", 10),
                    "cooldown_timer": 0,
                    "armor": p.get("armor", 0),
                    "armor_type": p.get("armor_type", "medium"),
                    "supply_cost": p.get("supply_cost", 1),
                    "domain": p.get("domain", "ground"),
                    "is_idle": True,
                    "attack_target_id": "",
                    "base_speed": 3.0,
                    "buffs": [],
                }
                to_spawn.append(spawn)

            for s in to_spawn:
                result[s["id"]] = s

            result[transport_id] = {**result.get(transport_id, transport),
                                     "loaded_units": remaining,
                                     "cargo_used": len(remaining)}

    # ─── Transport death: kill all loaded passengers ───────
    for eid in list(to_remove):
        result.pop(eid, None)

    # Also check for transports that were killed this tick (health<=0)
    dead_transports: set[str] = set()
    for eid, e in list(result.items()):
        if e.get("health", 1) <= 0 and _is_transport(e):
            dead_transports.add(eid)
            # Kill all passengers
            for p in e.get("loaded_units", []):
                # passenger is off-map, just forget them (they die with transport)
                pass
    for eid in dead_transports:
        result.pop(eid, None)

    return result, res


def _is_transport(entity: dict[str, Any]) -> bool:
    """Check if entity is a transport unit or bunker."""
    if entity.get("is_transport"):
        return True
    if entity.get("unit_type", "") in ("Dropship", "Shuttle", "Overlord"):
        return True
    if entity.get("entity_type") == "building" and entity.get("unit_type", "") == "Bunker":
        return True
    return False
