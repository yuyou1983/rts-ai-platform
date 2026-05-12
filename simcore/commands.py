"""Command system — validates and applies player commands to entities.

Command types: MOVE, STOP, ATTACK, PATROL, HOLD, GATHER, BUILD, TRAIN

Each command is a dict with at minimum:
  - action: str — one of the command type names
  - issuer: int — player ID issuing the command
"""
from __future__ import annotations

from typing import Any

from simcore.map import TileMap
from simcore.pathfinder import find_path


# ─── Command Type Constants ────────────────────────────────

MOVE = "move"
STOP = "stop"
ATTACK = "attack"
PATROL = "patrol"
HOLD = "hold"
GATHER = "gather"
BUILD = "build"
TRAIN = "train"

ALL_COMMANDS = {MOVE, STOP, ATTACK, PATROL, HOLD, GATHER, BUILD, TRAIN}


def validate_command(cmd: dict, entity: dict, state: Any) -> bool:
    """Validate that a command is legal for the given entity and state.

    Args:
        cmd: Command dict with 'action' and other fields.
        entity: Target entity dict.
        state: GameState (used for checking entity existence, etc.).

    Returns:
        True if the command is valid.
    """
    action = cmd.get("action", "")
    if action not in ALL_COMMANDS:
        return False

    # Issuer must own the entity
    if cmd.get("issuer") != entity.get("owner"):
        return False

    if action == MOVE:
        # Must be a unit
        if entity.get("entity_type") not in ("worker", "soldier", "scout"):
            return False
        # Target must be within map bounds
        tx = cmd.get("target_x")
        ty = cmd.get("target_y")
        if tx is None or ty is None:
            return False
        return True

    if action == STOP:
        # Any unit can stop
        if entity.get("entity_type") not in ("worker", "soldier", "scout"):
            return False
        return True

    if action == ATTACK:
        # Must be a combat-capable unit
        if entity.get("entity_type") not in ("worker", "soldier", "scout"):
            return False
        target_id = cmd.get("target_id", "")
        if not target_id:
            return False
        # Target must exist in state
        if hasattr(state, "entities") and target_id not in state.entities:
            return False
        return True

    if action == PATROL:
        if entity.get("entity_type") not in ("worker", "soldier", "scout"):
            return False
        tx = cmd.get("target_x")
        ty = cmd.get("target_y")
        if tx is None or ty is None:
            return False
        return True

    if action == HOLD:
        if entity.get("entity_type") not in ("worker", "soldier", "scout"):
            return False
        return True

    if action == GATHER:
        if entity.get("entity_type") != "worker":
            return False
        resource_id = cmd.get("resource_id", "")
        if not resource_id:
            return False
        if hasattr(state, "entities") and resource_id not in state.entities:
            return False
        return True

    if action == BUILD:
        if entity.get("entity_type") != "worker":
            return False
        building_type = cmd.get("building_type", "")
        if not building_type:
            return False
        return True

    if action == TRAIN:
        if entity.get("entity_type") != "building":
            return False
        if entity.get("is_constructing", False):
            return False
        unit_type = cmd.get("unit_type", "")
        if not unit_type:
            return False
        return True

    return False


def apply_command(
    cmd: dict,
    entity: dict,
    tile_map: TileMap | None = None,
) -> dict:
    """Apply a validated command to an entity, returning a new entity dict.

    Args:
        cmd: Validated command dict.
        entity: Current entity dict.
        tile_map: TileMap for pathfinding (required for MOVE, GATHER, BUILD).

    Returns:
        New entity dict with command applied.
    """
    action = cmd.get("action", "")

    if action == MOVE:
        tx = cmd.get("target_x", entity["pos_x"])
        ty = cmd.get("target_y", entity["pos_y"])
        path: list[tuple[int, int]] = []
        if tile_map is not None:
            start = tile_map.world_to_tile(entity["pos_x"], entity["pos_y"])
            end = tile_map.world_to_tile(tx, ty)
            is_flying = entity.get("is_flying", False)
            path = find_path(start, end, tile_map, is_flying=is_flying)
        return {
            **entity,
            "target_x": tx,
            "target_y": ty,
            "path": path,
            "is_idle": False,
            "returning_to_base": False,
            "attack_target_id": "",
            "deposit_pending": False,
        }

    if action == STOP:
        return {
            **entity,
            "target_x": None,
            "target_y": None,
            "path": [],
            "is_idle": True,
            "attack_target_id": "",
            "returning_to_base": False,
            "deposit_pending": False,
        }

    if action == ATTACK:
        return {
            **entity,
            "attack_target_id": cmd.get("target_id", ""),
            "is_idle": False,
            "returning_to_base": False,
            "deposit_pending": False,
        }

    if action == PATROL:
        tx = cmd.get("target_x", entity["pos_x"])
        ty = cmd.get("target_y", entity["pos_y"])
        path = []
        if tile_map is not None:
            start = tile_map.world_to_tile(entity["pos_x"], entity["pos_y"])
            end = tile_map.world_to_tile(tx, ty)
            is_flying = entity.get("is_flying", False)
            path = find_path(start, end, tile_map, is_flying=is_flying)
        return {
            **entity,
            "target_x": tx,
            "target_y": ty,
            "path": path,
            "is_idle": False,
            "patrol_origin_x": entity["pos_x"],
            "patrol_origin_y": entity["pos_y"],
        }

    if action == HOLD:
        return {
            **entity,
            "is_idle": True,
            "holding_position": True,
            "target_x": None,
            "target_y": None,
            "path": [],
            "attack_target_id": "",
        }

    if action == GATHER:
        resource_id = cmd.get("resource_id", "")
        # Set target to the resource's position; actual movement handled by engine
        target_x = entity.get("target_x")
        target_y = entity.get("target_y")
        path = []
        if tile_map is not None:
            start = tile_map.world_to_tile(entity["pos_x"], entity["pos_y"])
            # We'll compute path to resource in the engine when we know its position
        return {
            **entity,
            "gather_target_id": resource_id,
            "is_idle": False,
            "returning_to_base": False,
            "attack_target_id": "",
            "deposit_pending": False,
        }

    if action == BUILD:
        tx = cmd.get("pos_x", entity["pos_x"])
        ty = cmd.get("pos_y", entity["pos_y"])
        path = []
        if tile_map is not None:
            start = tile_map.world_to_tile(entity["pos_x"], entity["pos_y"])
            end = tile_map.world_to_tile(tx, ty)
            is_flying = entity.get("is_flying", False)
            path = find_path(start, end, tile_map, is_flying=is_flying)
        return {
            **entity,
            "target_x": tx,
            "target_y": ty,
            "path": path,
            "is_idle": False,
            "build_action": {
                "building_type": cmd.get("building_type", "barracks"),
                "pos_x": tx,
                "pos_y": ty,
            },
        }

    if action == TRAIN:
        queue = list(entity.get("production_queue", []))
        timers = list(entity.get("production_timers", []))
        unit_type = cmd.get("unit_type", "worker")
        from simcore.rules import PRODUCTION_TICKS
        queue.append(unit_type)
        timers.append(PRODUCTION_TICKS.get(unit_type, 10))
        return {
            **entity,
            "production_queue": queue,
            "production_timers": timers,
        }

    # Unknown action — return unchanged
    return entity