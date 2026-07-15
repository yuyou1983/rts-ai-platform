"""RTS SimCore — Headless deterministic game engine."""
from simcore.engine import SimCore
from simcore.entities import Building, Entity, Resource, Unit
from simcore.rules import RuleEngine, calculate_damage, get_armor_type
from simcore.state import GameState
from simcore.hash import fnv1a_64
from simcore.map import TileMap, generate_tile_map
from simcore.pathfinder import find_path, smooth_path
from simcore.movement import move_entities, collision_separate, is_at_target
from simcore.commands import (
    validate_command, apply_command,
    MOVE, STOP, ATTACK, PATROL, HOLD, GATHER, BUILD, TRAIN,
)
from simcore.projectile import process_projectiles, create_projectile
from simcore.spells import process_spells, regen_energy
from simcore.transport import process_transport, process_nydus
from simcore.upgrades import apply_upgrade_effects

from simcore.order import Order, OrderQueue
from simcore.replay import ReplayRecorder, ReplayV2
from simcore.wrappers import FlattenRTSObs, NormalizeRTSReward, ActionMaskRTS
from simcore.hierarchical_env import ActionMasker as HierarchicalActionMasker
from simcore.reward_shaping import (
    RewardShapingConfig, SubgoalTracker, compute_dense_reward, get_subgoal_info,
)

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
    "process_transport",
    "process_nydus",
    "apply_upgrade_effects",
    "fnv1a_64",
    "Order",
    "OrderQueue",
    "ReplayRecorder",
    "ReplayV2",
    "FlattenRTSObs",
    "NormalizeRTSReward",
    "ActionMaskRTS",
    "HierarchicalActionMasker",
    "RewardShapingConfig",
    "SubgoalTracker",
    "compute_dense_reward",
    "get_subgoal_info",
]