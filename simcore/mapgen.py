"""Procedural map generation — deterministic from seed."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from simcore.state import GameState
from simcore.map import TileMap, generate_tile_map

# ─── Lazy imports from sibling modules (with inline fallback) ────────────

try:
    from simcore.construction import _resolve_unit_stats, _build_unit_entity
except ImportError:
    # Lightweight inline fallback if construction.py is unavailable
    _UNIT_STATS_CACHE: dict[str, dict] | None = None

    def _load_unit_stats_inline() -> dict[str, dict]:
        global _UNIT_STATS_CACHE
        if _UNIT_STATS_CACHE is None:
            path = Path(__file__).resolve().parent / "data" / "unit_stats.json"
            try:
                with open(path) as f:
                    raw = json.load(f)
                _UNIT_STATS_CACHE = {}
                for key, val in raw.items():
                    if key == "_meta":
                        continue
                    if isinstance(val, dict) and "health" in val:
                        _UNIT_STATS_CACHE[key] = val
            except (FileNotFoundError, json.JSONDecodeError):
                _UNIT_STATS_CACHE = {}
        return _UNIT_STATS_CACHE

    _FALLBACK_WORKER_STATS = {
        "SCV":   {"health": 60,  "shields": 0,  "armor": 0, "speed": 2.5, "attack_ground": 5, "attack_air": 0, "attack_range_ground": 1.5, "attack_range_air": 0, "weapon_type_ground": "normal", "weapon_type_air": "none", "cooldown_ground": 10, "cooldown_air": 0, "armor_type": "light", "domain": "ground", "supply_cost": 1, "is_spellcaster": False, "energy": 0, "carry_capacity": 10.0},
        "Drone": {"health": 40,  "shields": 0,  "armor": 0, "speed": 2.5, "attack_ground": 5, "attack_air": 0, "attack_range_ground": 1.5, "attack_range_air": 0, "weapon_type_ground": "normal", "weapon_type_air": "none", "cooldown_ground": 10, "cooldown_air": 0, "armor_type": "light", "domain": "ground", "supply_cost": 1, "is_spellcaster": False, "energy": 0, "carry_capacity": 10.0},
        "Probe": {"health": 20,  "shields": 20, "armor": 0, "speed": 2.5, "attack_ground": 5, "attack_air": 0, "attack_range_ground": 1.5, "attack_range_air": 0, "weapon_type_ground": "normal", "weapon_type_air": "none", "cooldown_ground": 10, "cooldown_air": 0, "armor_type": "light", "domain": "ground", "supply_cost": 1, "is_spellcaster": False, "energy": 0, "carry_capacity": 10.0},
    }

    def _resolve_unit_stats(utype: str) -> dict[str, Any]:  # type: ignore[misc]
        stats = _load_unit_stats_inline().get(utype, {})
        if stats:
            result = dict(stats)
            if "carry_capacity" not in result:
                result["carry_capacity"] = _FALLBACK_WORKER_STATS.get(utype, {}).get("carry_capacity", 0)
            return result
        return dict(_FALLBACK_WORKER_STATS.get(utype, _FALLBACK_WORKER_STATS["SCV"]))

    def _build_unit_entity(  # type: ignore[misc]
        uid: str, utype: str, owner: int, simplified_etype: str,
        pos_x: float, pos_y: float, *, stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if stats is None:
            stats = _resolve_unit_stats(utype)
        health = stats.get("health", stats.get("max_health", 60))
        max_health = stats.get("max_health", health)
        speed = stats.get("speed", 2.5)
        shields = stats.get("shields", 0)
        max_shields = shields
        armor = stats.get("armor", 0)
        ag = stats.get("attack_ground", stats.get("attack", 0))
        aa = stats.get("attack_air", 0)
        arg = stats.get("attack_range_ground", stats.get("attack_range", 1.5))
        ara = stats.get("attack_range_air", 0)
        wtg = stats.get("weapon_type_ground", "normal")
        wta = stats.get("weapon_type_air", "none")
        cdg = stats.get("cooldown_ground", stats.get("cooldown", 10))
        cda = stats.get("cooldown_air", 0)
        domain = stats.get("domain", "ground")
        supply_cost = stats.get("supply_cost", 1)
        is_spellcaster = stats.get("is_spellcaster", False)
        energy = stats.get("energy", 0)
        carry_capacity = stats.get("carry_capacity", 0)
        return {
            "id": uid, "owner": owner, "entity_type": simplified_etype,
            "unit_type": utype, "pos_x": pos_x, "pos_y": pos_y,
            "health": health, "max_health": max_health, "speed": speed,
            "attack": ag, "attack_range": arg,
            "attack_ground": ag, "attack_air": aa,
            "attack_range_ground": arg, "attack_range_air": ara,
            "weapon_type_ground": wtg, "weapon_type_air": wta,
            "cooldown_ground": cdg, "cooldown_air": cda,
            "cooldown_timer": cdg,
            "shields": shields, "max_shields": max_shields, "armor": armor,
            "domain": domain, "supply_cost": supply_cost,
            "is_spellcaster": is_spellcaster, "energy": energy,
            "is_idle": True, "carry_amount": 0, "carry_capacity": carry_capacity,
            "target_x": None, "target_y": None, "returning_to_base": False,
            "attack_target_id": "", "deposit_pending": False,
            "is_flying": domain == "air",
            "is_transport": utype in ("Dropship", "Shuttle", "Overlord"),
            "loaded_units": [], "cargo_capacity": 0, "cargo_used": 0,
        }

# Building data helper (with fallback)
try:
    from simcore.economy import _load_building_data
except ImportError:
    _BUILDING_DATA_CACHE: dict[str, dict] | None = None

    def _load_building_data() -> dict[str, dict]:  # type: ignore[misc]
        global _BUILDING_DATA_CACHE
        if _BUILDING_DATA_CACHE is None:
            path = Path(__file__).resolve().parent.parent / "data" / "buildings" / "buildings.json"
            try:
                with open(path) as f:
                    raw = json.load(f)
                _BUILDING_DATA_CACHE = {}
                for race_data in raw.values():
                    if isinstance(race_data, dict):
                        for bname, bdata in race_data.items():
                            if isinstance(bdata, dict) and "name" in bdata:
                                _BUILDING_DATA_CACHE[bname] = bdata
            except (FileNotFoundError, json.JSONDecodeError):
                _BUILDING_DATA_CACHE = {}
        return _BUILDING_DATA_CACHE


def _seeded_random(seed: int) -> float:
    """Simple LCG-based pseudo-random for deterministic generation.

    Not cryptographically secure — only for game determinism.
    """
    state = seed
    def next_val() -> float:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    return next_val


def generate_map(seed: int = 42, config: dict | None = None) -> GameState:
    """Generate initial game state from seed and config.

    Standard layout:
    - 64x64 tile map
    - 2 bases at opposite corners (p1 bottom-left, p2 top-right)
    - 4 mineral patches near each base
    - 2 gas geysers near each base
    - 6 starting workers per player

    Args:
        seed: Random seed for deterministic generation.
        config: Override defaults (map_size, starting_workers, resource_density, etc.).

    Returns:
        Initial GameState with starting entities and resources.
    """
    cfg = config or {}
    map_size = cfg.get("map_size", 64)
    starting_workers = cfg.get("starting_workers", 6)
    resource_density = cfg.get("resource_density", 1.0)
    enable_elevation = cfg.get("enable_elevation", True)
    player_races: dict = cfg.get("player_races", {1: "terran", 2: "terran"})

    # Race-specific initial building info — real names with HP and shields from buildings.json
    _RACE_BASE_DEFAULTS: dict[str, dict[str, Any]] = {
        "terran":   {"name": "CommandCenter", "hp": 1500, "sp": 0,    "armor": 0, "race": "terran"},
        "zerg":     {"name": "Hatchery",      "hp": 1250, "sp": 0,    "armor": 0, "race": "zerg"},
        "protoss":  {"name": "Nexus",         "hp": 750,  "sp": 750,  "armor": 0, "race": "protoss"},
    }
    # Override defaults from buildings.json when available
    try:
        _bdata = _load_building_data()
        for _race, _info in _RACE_BASE_DEFAULTS.items():
            _bname = _info["name"]
            if _bname in _bdata:
                _bd = _bdata[_bname]
                _info["hp"] = _bd.get("hp", _info["hp"])
                _info["sp"] = _bd.get("sp", 0)
                _info["armor"] = _bd.get("armor", 0)
                _info["race"] = _bd.get("race", _race)
    except Exception:
        pass  # fall back to hardcoded defaults
    _RACE_BASE = _RACE_BASE_DEFAULTS
    _RACE_WORKER = {"terran": "SCV", "zerg": "Drone", "protoss": "Probe"}

    rng = _seeded_random(seed)

    # Phase D: generate tile map with elevation
    tile_map = generate_tile_map(seed=seed, config=cfg)

    entities: dict = {}
    resources: dict = {
        "p1_mineral": cfg.get("starting_mineral", 200),
        "p1_gas": cfg.get("starting_gas", 0),
        "p2_mineral": cfg.get("starting_mineral", 200),
        "p2_gas": cfg.get("starting_gas", 0),
    }

    # Player 1 base (bottom-left quadrant)
    p1_base_x, p1_base_y = map_size * 0.15, map_size * 0.15
    p1_race = player_races.get(1, "terran")
    p1_base_info = _RACE_BASE.get(p1_race, _RACE_BASE["terran"])
    p1_base_name = p1_base_info["name"]
    p1_base_hp = p1_base_info["hp"]
    p1_base_sp = p1_base_info.get("sp", 0)
    p1_base_armor = p1_base_info.get("armor", 0)
    p1_base_race = p1_base_info.get("race", p1_race)
    entities["base_p1"] = {
        "id": "base_p1",
        "owner": 1,
        "entity_type": "building",
        "building_type": "base",
        "unit_type": p1_base_name,
        "pos_x": p1_base_x,
        "pos_y": p1_base_y,
        "health": p1_base_hp,
        "max_health": p1_base_hp,
        "shields": p1_base_sp,
        "max_shields": p1_base_sp,
        "armor": p1_base_armor,
        "race": p1_base_race,
        "is_constructing": False,
        "is_powered": True,  # Nexus/CC/Hatchery always powered
        "production_queue": [],
    }

    # Player 2 base (top-right quadrant)
    p2_base_x, p2_base_y = map_size * 0.85, map_size * 0.85
    p2_race = player_races.get(2, "terran")
    p2_base_info = _RACE_BASE.get(p2_race, _RACE_BASE["terran"])
    p2_base_name = p2_base_info["name"]
    p2_base_hp = p2_base_info["hp"]
    p2_base_sp = p2_base_info.get("sp", 0)
    p2_base_armor = p2_base_info.get("armor", 0)
    p2_base_race = p2_base_info.get("race", p2_race)
    entities["base_p2"] = {
        "id": "base_p2",
        "owner": 2,
        "entity_type": "building",
        "building_type": "base",
        "unit_type": p2_base_name,
        "pos_x": p2_base_x,
        "pos_y": p2_base_y,
        "health": p2_base_hp,
        "max_health": p2_base_hp,
        "shields": p2_base_sp,
        "max_shields": p2_base_sp,
        "armor": p2_base_armor,
        "race": p2_base_race,
        "is_constructing": False,
        "is_powered": True,  # Nexus/CC/Hatchery always powered
        "production_queue": [],
    }

    # Mineral patches near each base
    for pid, bx, by in [(1, p1_base_x, p1_base_y), (2, p2_base_x, p2_base_y)]:
        for i in range(4):
            rid = f"mineral_p{pid}_{i}"
            angle = i * math.pi / 2 + rng() * 0.3
            offset = 4 + rng() * 2
            entities[rid] = {
                "id": rid,
                "owner": 0,  # neutral
                "entity_type": "resource",
                "resource_type": "mineral",
                "pos_x": bx + math.cos(angle) * offset,
                "pos_y": by + math.sin(angle) * offset,
                "resource_amount": int(1500 * resource_density),
            }

        # Gas geysers
        for i in range(2):
            gid = f"gas_p{pid}_{i}"
            angle = math.pi / 4 + i * math.pi / 2 + rng() * 0.3
            offset = 5 + rng() * 2
            entities[gid] = {
                "id": gid,
                "owner": 0,
                "entity_type": "resource",
                "resource_type": "gas",
                "pos_x": bx + math.cos(angle) * offset,
                "pos_y": by + math.sin(angle) * offset,
                "resource_amount": int(2000 * resource_density),
            }

    # Starting workers — race-aware, using real stats from unit_stats.json
    for pid, bx, by in [(1, p1_base_x, p1_base_y), (2, p2_base_x, p2_base_y)]:
        race = player_races.get(pid, "terran")
        worker_name = _RACE_WORKER.get(race, "SCV")
        for i in range(starting_workers):
            uid = f"worker_p{pid}_{i}"
            angle = i * 2 * math.pi / starting_workers
            offset = 2.0
            wx = bx + math.cos(angle) * offset
            wy = by + math.sin(angle) * offset
            try:
                entity = _build_unit_entity(uid, worker_name, pid, "worker", wx, wy)
            except Exception:
                # Fallback: hardcoded minimal worker entity
                fallback_hp = {"SCV": 60, "Drone": 40, "Probe": 20}.get(worker_name, 50)
                fallback_sp = {"SCV": 0, "Drone": 0, "Probe": 20}.get(worker_name, 0)
                entity = {
                    "id": uid,
                    "owner": pid,
                    "entity_type": "worker",
                    "unit_type": worker_name,
                    "pos_x": wx,
                    "pos_y": wy,
                    "health": fallback_hp,
                    "max_health": fallback_hp,
                    "shields": fallback_sp,
                    "max_shields": fallback_sp,
                    "speed": 2.5,
                    "attack": 5,
                    "attack_range": 1.5,
                    "is_idle": True,
                    "carry_amount": 0,
                    "carry_capacity": 10.0,
                    "target_x": None,
                    "target_y": None,
                    "returning_to_base": False,
                    "attack_target_id": "",
                    "deposit_pending": False,
                }
            entities[uid] = entity

    # Central mineral patches (contested)
    center = map_size / 2
    for i in range(4):
        rid = f"mineral_center_{i}"
        angle = i * math.pi / 2 + rng() * 0.5
        offset = 5 + rng() * 3
        entities[rid] = {
            "id": rid,
            "owner": 0,
            "entity_type": "resource",
            "resource_type": "mineral",
            "pos_x": center + math.cos(angle) * offset,
            "pos_y": center + math.sin(angle) * offset,
            "resource_amount": int(2000 * resource_density),
        }

    # Fog-of-war: per-player, start unexplored (0) except near own base
    fog_width = map_size // 4  # downsampled grid
    fog_height = map_size // 4
    total_tiles = fog_width * fog_height
    reveal_radius = 4  # in fog-grid tiles

    fog_of_war: dict[str, Any] = {}
    for player_id, bx, by in [(1, p1_base_x, p1_base_y), (2, p2_base_x, p2_base_y)]:
        tiles = [0] * total_tiles  # 0=unexplored
        fg_x = int(bx / map_size * fog_width)
        fg_y = int(by / map_size * fog_height)
        for dy in range(-reveal_radius, reveal_radius + 1):
            for dx in range(-reveal_radius, reveal_radius + 1):
                gx, gy = fg_x + dx, fg_y + dy
                if (0 <= gx < fog_width and 0 <= gy < fog_height
                        and dx*dx + dy*dy <= reveal_radius*reveal_radius):
                    tiles[gy * fog_width + gx] = 2  # visible
        fog_of_war[str(player_id)] = {
            "tiles": tiles,
            "width": fog_width,
            "height": fog_height,
        }

    # Build simplified elevation grid for GameState (0=low, 1=high)
    elevation_grid = None
    if enable_elevation and tile_map and tile_map.height_map:
        elevation_grid = tile_map.get_elevation_grid()

    return GameState(
        tick=0,
        entities=entities,
        fog_of_war=fog_of_war,
        resources=resources,
        is_terminal=False,
        height_map=tile_map.height_map if tile_map else None,
        map_width=map_size,
        map_height=map_size,
        player_races={str(k): v for k, v in player_races.items()},
        elevation_grid=elevation_grid,
    )
