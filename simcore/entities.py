"""Entity types for the RTS game simulation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    """Base entity — all game objects are entities."""

    id: str
    owner: int  # player ID
    position: tuple[float, float] = (0.0, 0.0)
    health: float = 100.0
    max_health: float = 100.0


@dataclass(frozen=True)
class Unit(Entity):
    """Movable unit (worker, soldier, scout, etc.)."""

    unit_type: str = "worker"
    speed: float = 2.0
    attack: float = 10.0
    attack_range: float = 1.0
    carry_capacity: float = 10.0
    carry_amount: float = 0.0


@dataclass(frozen=True)
class Building(Entity):
    """Static building (base, barracks, factory, etc.)."""

    building_type: str = "base"
    production_queue: tuple[str, ...] = ()
    is_constructing: bool = False


@dataclass(frozen=True)
class Resource(Entity):
    """Harvestable resource node."""

    resource_type: str = "mineral"
    amount: float = 1000.0
