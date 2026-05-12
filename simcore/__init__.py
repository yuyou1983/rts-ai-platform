"""RTS SimCore — Headless deterministic game engine."""
from simcore.engine import SimCore
from simcore.entities import Building, Entity, Resource, Unit
from simcore.rules import RuleEngine, calculate_damage, get_armor_type
from simcore.state import GameState
from simcore.map import TileMap, generate_tile_map
from simcore.pathfinder import find_path, smooth_path
from simcore.movement import move_entities, collision_separate, is_at_target
from simcore.commands import (
    validate_command, apply_command,
    MOVE, STOP, ATTACK, PATROL, HOLD, GATHER, BUILD, TRAIN,
)
from simcore.projectile import process_projectiles, create_projectile
from simcore.spells import process_spells, regen_energy
from simcore.upgrades import apply_upgrade_effects

__all__ = [
    "SimCore",
    "GameState",
    "RuleEngine",
    "Entity",
    "Unit",
    "Building",
    "Resource",
    "TileMap",
    "generate_tile_map",
    "find_path",
    "smooth_path",
    "move_entities",
    "collision_separate",
    "is_at_target",
    "validate_command",
    "apply_command",
    "MOVE",
    "STOP",
    "ATTACK",
    "PATROL",
    "HOLD",
    "GATHER",
    "BUILD",
    "TRAIN",
    "calculate_damage",
    "get_armor_type",
    "process_projectiles",
    "create_projectile",
    "process_spells",
    "regen_energy",
    "apply_upgrade_effects",
]