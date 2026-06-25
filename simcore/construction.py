"""Construction system: build, train, upgrade with tech tree validation.

Pipeline per tick:
  1. process_construction(state, commands) — handle build/train/upgrade commands
  2. Advance construction progress, production timers, upgrade timers
  3. Validate tech tree prerequisites before allowing actions
  4. Apply race-specific mechanics (Terran worker-builds, Zerg morph, Protoss warp-in)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from simcore.state import GameState
from simcore.economy import (
    _load_building_data,
    _load_unit_data,
    _dist,
    _find_nearest_base,
    _is_pylon_powered,
    check_pylon_power,
)

# ─── Constants ───────────────────────────────────────────────

BUILD_PROGRESS_PER_TICK = 10  # % progress per tick for construction
GATHER_INTERACT_RANGE = 1.5  # reuse from economy

# Mapping from simplified building types used in mapgen to JSON names
_BUILDING_TYPE_MAP = {
    "base": "CommandCenter",
    "barracks": "Barracks",
    "factory": "Factory",
    "starport": "Starport",
    "supply_depot": "SupplyDepot",
    "refinery": "Refinery",
    # Terran
    "CommandCenter": "CommandCenter",
    "SupplyDepot": "SupplyDepot",
    "Refinery": "Refinery",
    "Barracks": "Barracks",
    "EngineeringBay": "EngineeringBay",
    "MissileTurret": "MissileTurret",
    "Academy": "Academy",
    "Bunker": "Bunker",
    "Factory": "Factory",
    "Starport": "Starport",
    "ScienceFacility": "ScienceFacility",
    "Armory": "Armory",
    # Zerg
    "Hatchery": "Hatchery",
    "Lair": "Lair",
    "Hive": "Hive",
    "Extractor": "Extractor",
    "SpawningPool": "SpawningPool",
    "EvolutionChamber": "EvolutionChamber",
    "HydraliskDen": "HydraliskDen",
    "Spire": "Spire",
    "GreaterSpire": "GreaterSpire",
    "QueenNest": "QueenNest",
    "NydusCanal": "NydusCanal",
    "UltraliskCavern": "UltraliskCavern",
    "DefilerMound": "DefilerMound",
    "CreepColony": "CreepColony",
    "SunkenColony": "SunkenColony",
    "SporeColony": "SporeColony",
    # Protoss
    "Nexus": "Nexus",
    "Pylon": "Pylon",
    "Assimilator": "Assimilator",
    "Gateway": "Gateway",
    "Forge": "Forge",
    "PhotonCannon": "PhotonCannon",
    "CyberneticsCore": "CyberneticsCore",
    "ShieldBattery": "ShieldBattery",
    "RoboticsFacility": "RoboticsFacility",
    "Stargate": "Stargate",
    "CitadelOfAdun": "CitadelOfAdun",
    "RoboticsSupportBay": "RoboticsSupportBay",
    "FleetBeacon": "FleetBeacon",
    "TemplarArchives": "TemplarArchives",
    "Observatory": "Observatory",
    "ArbiterTribunal": "ArbiterTribunal",
}

# Reverse: JSON name → simplified (for internal compatibility)
_REVERSE_BTYPE = {}
for _k, _v in _BUILDING_TYPE_MAP.items():
    if _v not in _REVERSE_BTYPE:
        _REVERSE_BTYPE[_v] = _k

# Simplified unit type mapping
_UNIT_TYPE_MAP = {
    # Terran
    "SCV": "SCV", "worker": "SCV",
    "Marine": "Marine", "soldier": "Marine",
    "Firebat": "Firebat", "firebat": "Firebat",
    "Ghost": "Ghost", "ghost": "Ghost",
    "Medic": "Medic", "medic": "Medic",
    "Vulture": "Vulture", "vulture": "Vulture",
    "Tank": "Tank", "tank": "Tank",
    "Goliath": "Goliath", "goliath": "Goliath",
    "Wraith": "Wraith", "scout": "Wraith",
    "Dropship": "Dropship", "dropship": "Dropship",
    "Vessel": "Vessel", "vessel": "Vessel",
    "BattleCruiser": "BattleCruiser", "battlecruiser": "BattleCruiser",
    "Valkyrie": "Valkyrie", "valkyrie": "Valkyrie",
    # Zerg
    "Drone": "Drone", "drone": "Drone",
    "Zergling": "Zergling", "zergling": "Zergling",
    "Hydralisk": "Hydralisk", "hydralisk": "Hydralisk",
    "Lurker": "Lurker", "lurker": "Lurker",
    "Ultralisk": "Ultralisk", "ultralisk": "Ultralisk",
    "Overlord": "Overlord", "overlord": "Overlord",
    "Queen": "Queen", "queen": "Queen",
    "Defiler": "Defiler", "defiler": "Defiler",
    "Mutalisk": "Mutalisk", "mutalisk": "Mutalisk",
    "Guardian": "Guardian", "guardian": "Guardian",
    "Devourer": "Devourer", "devourer": "Devourer",
    "Scourge": "Scourge", "scourge": "Scourge",
    "Larva": "Larva", "larva": "Larva",
    "Broodling": "Broodling", "broodling": "Broodling",
    "InfestedTerran": "InfestedTerran", "infestedterran": "InfestedTerran",
    # Protoss
    "Probe": "Probe", "probe": "Probe",
    "Zealot": "Zealot", "zealot": "Zealot",
    "Dragoon": "Dragoon", "dragoon": "Dragoon",
    "Templar": "Templar", "templar": "Templar",
    "DarkTemplar": "DarkTemplar", "darktemplar": "DarkTemplar",
    "Archon": "Archon", "archon": "Archon",
    "DarkArchon": "DarkArchon", "darkarchon": "DarkArchon",
    "Reaver": "Reaver", "reaver": "Reaver",
    "Shuttle": "Shuttle", "shuttle": "Shuttle",
    "Observer": "Observer", "observer": "Observer",
    "Arbiter": "Arbiter", "arbiter": "Arbiter",
    "Scout": "Scout",
    "Carrier": "Carrier", "carrier": "Carrier",
    "Corsair": "Corsair", "corsair": "Corsair",
    "scout_unit": "Probe",  # internal type → real name
}

# ─── Unit Stats Loader (JSON-backed) ─────────────────────────

_UNIT_STATS_CACHE: dict[str, dict] | None = None


def _load_unit_stats() -> dict[str, dict]:
    """Load unit stats from simcore/data/unit_stats.json with caching.

    Same pattern as _load_building_data() in economy.py.
    """
    global _UNIT_STATS_CACHE
    if _UNIT_STATS_CACHE is None:
        path = Path(__file__).resolve().parent / "data" / "unit_stats.json"
        with open(path) as f:
            raw = json.load(f)
        _UNIT_STATS_CACHE = {}
        for key, val in raw.items():
            if key == "_meta":
                continue
            if isinstance(val, dict) and "health" in val:
                _UNIT_STATS_CACHE[key] = val
    return _UNIT_STATS_CACHE


def _resolve_unit_stats(utype: str) -> dict[str, Any]:
    """Resolve unit stats: prefer unit_stats.json, fall back to _DEFAULT_UNIT_STATS."""
    json_stats = _load_unit_stats().get(utype, {})
    if json_stats:
        # JSON is authoritative; carry_capacity is an engine field not in JSON
        stats = dict(json_stats)
        # Add engine-only fields with defaults if absent
        if "carry_capacity" not in stats:
            stats["carry_capacity"] = _DEFAULT_UNIT_STATS.get(utype, {}).get(
                "carry_capacity", 0
            )
        return stats
    # Fallback to legacy dict for units absent from JSON
    return dict(_DEFAULT_UNIT_STATS.get(utype, _DEFAULT_UNIT_STATS["SCV"]))


def _build_unit_entity(
    uid: str,
    utype: str,
    owner: int,
    simplified_etype: str,
    pos_x: float,
    pos_y: float,
    *,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a unit entity dict from resolved stats, including all new fields.

    New fields from unit_stats.json:
      shields / max_shields, armor,
      attack_ground / attack_air (replaces 'attack'),
      attack_range_ground / attack_range_air (replaces 'attack_range'),
      weapon_type_ground / weapon_type_air,
      cooldown_ground / cooldown_air,
      cooldown_timer (init 0),
      domain, supply_cost, is_spellcaster, energy
    Backward compat: legacy 'attack' and 'attack_range' are populated
    from attack_ground / attack_range_ground when present.
    """
    if stats is None:
        stats = _resolve_unit_stats(utype)

    # Map JSON keys → entity keys
    health = stats.get("health", stats.get("max_health", 60))
    max_health = stats.get("max_health", health)
    speed = stats.get("speed", 2.5)
    shields = stats.get("shields", 0)
    max_shields = shields  # same source value
    armor = stats.get("armor", 0)
    attack_ground = stats.get("attack_ground", stats.get("attack", 0))
    attack_air = stats.get("attack_air", 0)
    attack_range_ground = stats.get("attack_range_ground", stats.get("attack_range", 1.5))
    attack_range_air = stats.get("attack_range_air", 0)
    weapon_type_ground = stats.get("weapon_type_ground", "normal")
    weapon_type_air = stats.get("weapon_type_air", "none")
    cooldown_ground = stats.get("cooldown_ground", stats.get("cooldown", 10))
    cooldown_air = stats.get("cooldown_air", 0)
    domain = stats.get("domain", "ground")
    supply_cost = stats.get("supply_cost", 1)
    is_spellcaster = stats.get("is_spellcaster", False)
    energy = stats.get("energy", 0)
    carry_capacity = stats.get("carry_capacity", 0)

    # Protoss: shields come from JSON, max_shields == shields for init
    # But if the old _load_unit_data() path provides "sp", prefer that
    # for shield initial value (same number anyway).
    unit: dict[str, Any] = {
        "id": uid,
        "owner": owner,
        "entity_type": simplified_etype,
        "unit_type": utype,
        "pos_x": pos_x,
        "pos_y": pos_y,
        "health": health,
        "max_health": max_health,
        "speed": speed,
        # Legacy fields (backward compat)
        "attack": attack_ground,
        "attack_range": attack_range_ground,
        # New split attack fields
        "attack_ground": attack_ground,
        "attack_air": attack_air,
        "attack_range_ground": attack_range_ground,
        "attack_range_air": attack_range_air,
        "weapon_type_ground": weapon_type_ground,
        "weapon_type_air": weapon_type_air,
        "cooldown_ground": cooldown_ground,
        "cooldown_air": cooldown_air,
        "cooldown_timer": cooldown_ground,  # ready to fire on first tick
        # Defense fields
        "shields": shields,
        "max_shields": max_shields,
        "armor": armor,
        # Domain & supply
        "domain": domain,
        "supply_cost": supply_cost,
        # Spellcaster
        "is_spellcaster": is_spellcaster,
        "energy": energy,
        # Common unit fields
        "is_idle": True,
        "carry_amount": 0,
        "carry_capacity": carry_capacity,
        "target_x": None,
        "target_y": None,
        "returning_to_base": False,
        "attack_target_id": "",
        "deposit_pending": False,
        "is_flying": domain == "air",
    }

    return unit


# Default unit stats for spawning
# DEPRECATED: Prefer _load_unit_stats() / unit_stats.json for unit creation.
# Kept as fallback for units not yet in the JSON and for carry_capacity defaults.
_DEFAULT_UNIT_STATS = {
    # Workers — melee
    "SCV":      {"health": 60,  "max_health": 60,  "speed": 2.5, "attack": 5,  "attack_range": 1.5, "carry_capacity": 10.0},
    "Drone":    {"health": 40,  "max_health": 40,  "speed": 2.5, "attack": 5,  "attack_range": 1.5, "carry_capacity": 10.0},
    "Probe":    {"health": 20,  "max_health": 20,  "speed": 2.5, "attack": 5,  "attack_range": 1.5, "carry_capacity": 10.0},
    # Terran army
    "Marine":   {"health": 40,  "max_health": 40,  "speed": 3.0, "attack": 6,  "attack_range": 5.0, "carry_capacity": 0},
    "Firebat":  {"health": 50,  "max_health": 50,  "speed": 3.0, "attack": 16, "attack_range": 1.5, "carry_capacity": 0},
    "Ghost":    {"health": 45,  "max_health": 45,  "speed": 3.0, "attack": 10, "attack_range": 8.0, "carry_capacity": 0},
    "Medic":    {"health": 60,  "max_health": 60,  "speed": 3.0, "attack": 0,  "attack_range": 0,   "carry_capacity": 0},
    "Vulture":  {"health": 80,  "max_health": 80,  "speed": 5.0, "attack": 20, "attack_range": 5.0, "carry_capacity": 0},
    "Tank":     {"health": 150, "max_health": 150, "speed": 2.5, "attack": 30, "attack_range": 10.0, "carry_capacity": 0},
    "Goliath":  {"health": 125, "max_health": 125, "speed": 3.0, "attack": 12, "attack_range": 7.0, "carry_capacity": 0},
 # Zerg army — Zerglings spawn in pairs, need stat buff for simplified combat
    "Zergling": {"health": 40,  "max_health": 40,  "speed": 4.0, "attack": 7,   "attack_range": 1.5, "carry_capacity": 0},
    "Hydralisk":{"health": 80,  "max_health": 80,  "speed": 3.0, "attack": 15, "attack_range": 6.0, "carry_capacity": 0},
    "Lurker":   {"health": 125, "max_health": 125, "speed": 2.5, "attack": 20, "attack_range": 8.0, "carry_capacity": 0},
    "Ultralisk":{"health": 400, "max_health": 400, "speed": 2.5, "attack": 40, "attack_range": 1.5, "carry_capacity": 0},
    "Overlord": {"health": 200, "max_health": 200, "speed": 1.5, "attack": 0,  "attack_range": 0,   "carry_capacity": 0},
    # Protoss army
    "Zealot":   {"health": 100, "max_health": 100, "speed": 3.0, "attack": 12, "attack_range": 1.5, "carry_capacity": 0},
    "Dragoon":  {"health": 100, "max_health": 100, "speed": 2.5, "attack": 20, "attack_range": 6.0, "carry_capacity": 0},
}


# ─── Tech Tree Validation ────────────────────────────────────

def _get_completed_buildings(entities: dict[str, Any], owner: int) -> set[str]:
    """Get set of completed building type names owned by a player."""
    completed = set()
    for eid, e in entities.items():
        if e.get("owner") == owner and e.get("entity_type") == "building":
            if not e.get("is_constructing", False) and e.get("health", 0) > 0:
                bt = e.get("building_type", "")
                # Normalize to JSON name
                json_name = _BUILDING_TYPE_MAP.get(bt, bt)
                completed.add(json_name)
    return completed


def check_prerequisites(
    entities: dict[str, Any],
    owner: int,
    building_type: str,
) -> bool:
    """Check if all prerequisites for building_type are met.

    Looks up the building in buildings.json, checks if its prerequisites
    are all in the set of completed buildings for that owner.
    Also handles simplified building types (base, barracks, etc.).
    """
    # Map simplified types to JSON names for lookup
    simplified_to_json = {
        "base": "CommandCenter",
        "barracks": "Barracks",
        "factory": "Factory",
        "starport": "Starport",
        "supply_depot": "SupplyDepot",
        "refinery": "Refinery",
    }
    json_name = simplified_to_json.get(building_type, _BUILDING_TYPE_MAP.get(building_type, building_type))
    bdata = _load_building_data().get(json_name)
    if bdata is None:
        # Unknown building — allow by default (simplified types)
        return True

    prereqs = bdata.get("prerequisites", [])
    if not prereqs:
        return True

    completed = _get_completed_buildings(entities, owner)
    # Also map completed simplified types to JSON names
    completed_json = set()
    for c in completed:
        cj = simplified_to_json.get(c, c)
        completed_json.add(cj)
        completed_json.add(c)

    for prereq in prereqs:
        prereq_json = _BUILDING_TYPE_MAP.get(prereq, prereq)
        prereq_simplified = _REVERSE_BTYPE.get(prereq, prereq)
        if prereq not in completed and prereq_json not in completed_json and prereq_simplified not in completed:
            return False
    return True


def check_train_prerequisites(
    entities: dict[str, Any],
    owner: int,
    building_id: str,
    unit_type: str,
) -> bool:
    """Check if a building can train a given unit type.

    Validates:
      - Building exists and is completed
      - Building's 'train' list includes the unit type (or building type is a known simplified type)
      - Supply allows it (checked separately via check_supply)
    """
    building = entities.get(building_id)
    if building is None:
        return False
    if building.get("entity_type") != "building":
        return False
    if building.get("is_constructing", False):
        return False
    if building.get("owner") != owner:
        return False

    bt = building.get("building_type", "")
    json_name = _BUILDING_TYPE_MAP.get(bt, bt)
    bdata = _load_building_data().get(json_name)

# Simplified building types: restricted to correct unit routing per buildings.json
    simplified_train = {
        # Simplified types (for backward compat with simplified mode)
        "base": ["worker"],
        "barracks": ["soldier"],
        "factory": [],
        "starport": ["scout"],
        # Zerg buildings — bases only train Drone/Overlord, others via larva morph
        "Hatchery": ["Drone", "Overlord"],
        "Lair": ["Drone", "Overlord"],
        "Hive": ["Drone", "Overlord"],
        "SpawningPool": ["ZerglingSpeed", "ZerglingAdrenalGlands"],
        "EvolutionChamber": ["MeleeAttacks", "MissileAttacks", "Carapace"],
        "HydraliskDen": ["Hydralisk", "GroovedSpines", "HydraliskSpeed", "LurkerAspect"],
        "Spire": ["Mutalisk", "Guardian", "Devourer", "Scourge", "FlyerAttacks", "FlyerArmor"],
        "QueenNest": ["Queen"],
        "DefilerMound": ["Defiler", "Plague", "Consume"],
        "UltraliskCavern": ["Ultralisk", "UltraliskSpeed", "UltraliskArmor"],
        "CreepColony": [],
        "SunkenColony": [],
        "SporeColony": [],
        "Extractor": [],
        # Protoss buildings — Nexus only trains Probe
        "Nexus": ["Probe"],
        "Gateway": ["Zealot", "Dragoon", "Templar", "DarkTemplar"],
        "CyberneticsCore": ["SingularityCharge", "AirWeapons", "AirArmor"],
        "Forge": ["GroundWeapons", "GroundArmor", "PlasmaShields"],
        "RoboticsFacility": ["Shuttle", "Reaver", "Observer"],
        "Stargate": ["Scout", "Carrier", "Corsair", "Arbiter"],
        "CitadelOfAdun": ["LegEnhancement"],
        "TemplarArchives": ["HighTemplar", "PsionicStorm", "Hallucination", "KhaydarinAmulet"],
        "RoboticsSupportBay": ["ScarabDamage"],
        "FleetBeacon": ["CarrierCapacity", "ScoutSpeed", "CorsairDisruptionWeb"],
        "Observatory": ["ObserverSpeed", "ObserverSight"],
        "ArbiterTribunal": ["StasisField", "Recall"],
        "Pylon": [],
        "Assimilator": [],
        "PhotonCannon": [],
        "ShieldBattery": [],
        # Terran buildings — CommandCenter only trains SCV
        "CommandCenter": ["SCV"],
        "Barracks": ["Marine", "Firebat", "Ghost", "Medic"],
        "Factory": ["Vulture", "Tank", "Goliath"],
        "Starport": ["Wraith", "Dropship", "Vessel", "BattleCruiser", "Valkyrie"],
        "Academy": ["StimPack", "U238Shells", "Medic"],
        "EngineeringBay": ["InfantryWeapons", "InfantryArmor"],
        "Armory": ["VehicleWeapons", "VehiclePlating", "ShipWeapons", "ShipPlating"],
        "ScienceFacility": ["EMPShockwave", "Irradiate", "TitanReactor", "ApolloReactor"],
        "SupplyDepot": [],
        "Refinery": [],
        "MissileTurret": [],
        "Bunker": [],
        "ComstatStation": ["ComsatScan"],
        "MachineShop": ["SpiderMines", "IonThrusters", "SiegeTech"],
        "NuclearSilo": ["NuclearStrike"],
    }

    # Route: JSON data (authoritative) first, simplified fallback second
    if bdata and "train" in bdata:
        trainable = bdata["train"]
        json_unit = _UNIT_TYPE_MAP.get(unit_type, unit_type)
        if json_unit not in trainable and unit_type not in trainable:
            return False
    elif bt in simplified_train:
        if unit_type not in simplified_train[bt]:
            return False

    return True


def check_supply(
    resources: dict[str, int],
    owner: int,
    unit_type: str,
) -> bool:
    """Check if training this unit would exceed supply cap.

    Enforces supply strictly: no unit may be trained if supply_used + cost > cap.
    """
    json_unit = _UNIT_TYPE_MAP.get(unit_type, unit_type)
    udata = _load_unit_data().get(json_unit)

    supply_cost = 1  # default
    if udata and "cost" in udata:
        supply_cost = udata["cost"].get("man", 1)
    else:
        # Fallback for simplified types
        supply_map = {"worker": 1, "soldier": 2, "scout": 1}
        supply_cost = supply_map.get(unit_type, supply_cost)

    supply_used = resources.get(f"p{owner}_supply_used", 0)
    supply_cap = resources.get(f"p{owner}_supply_cap", 0)

    if supply_cap <= 0:
        return True  # No supply system active — don't block

    return supply_used + supply_cost <= supply_cap


# ─── Race Detection ─────────────────────────────────────────

def _detect_race(entities: dict[str, Any], owner: int) -> str:
    """Detect player race from their buildings."""
    race_buildings = {
        "terran": {"CommandCenter", "SupplyDepot", "Barracks", "Factory", "Starport",
                   "EngineeringBay", "Academy", "Armory", "ScienceFacility",
                   "MissileTurret", "Bunker", "Refinery"},
        "zerg": {"Hatchery", "Lair", "Hive", "SpawningPool", "EvolutionChamber",
                 "HydraliskDen", "Spire", "GreaterSpire", "QueenNest", "UltraliskCavern",
                 "DefilerMound", "Extractor", "CreepColony", "SunkenColony", "SporeColony",
                 "NydusCanal"},
        "protoss": {"Nexus", "Pylon", "Gateway", "Forge", "CyberneticsCore",
                    "RoboticsFacility", "Stargate", "CitadelOfAdun", "FleetBeacon",
                    "TemplarArchives", "Observatory", "ArbiterTribunal",
                    "Assimilator", "PhotonCannon", "ShieldBattery"},
    }
    for eid, e in entities.items():
        if e.get("owner") == owner and e.get("entity_type") == "building":
            bt = e.get("building_type", "")
            for race, types in race_buildings.items():
                if bt in types:
                    return race
    # Check simplified types
    for eid, e in entities.items():
        if e.get("owner") == owner and e.get("entity_type") == "building":
            bt = e.get("building_type", "")
            if bt == "base":
                return "terran"  # default
    return "terran"  # default


# ─── Construction Processing ─────────────────────────────────

def process_construction(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
    player_races: dict[int, str] | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process build, train, and upgrade commands with tech tree validation.

    Build flow:
      - Terran: Worker moves to site, starts construction (HP 0→max over ticks). Worker stays at site.
      - Zerg: Drone moves to site, is consumed. Building starts at 0 HP and builds itself.
      - Protoss: Probe starts warp-in (HP 0→max), then probe is freed.

    Train flow:
      - Building queues unit, after train_time ticks, spawns near building (if supply allows).

    Upgrade flow:
      - Building starts research, after research_time ticks, upgrade is applied globally.

    Returns (updated_entities, updated_resources).
    """
    built = dict(entities)
    res = dict(resources)
    new_entities: dict[str, Any] = {}
    race_cache: dict[int, str] = {}

    def get_race(owner: int) -> str:
        if owner not in race_cache:
            # Prefer explicit player_races config over heuristic detection
            if player_races and owner in player_races:
                race_cache[owner] = player_races[owner]
            else:
                race_cache[owner] = _detect_race(built, owner)
        return race_cache[owner]

    # ─── Extract and remove transient meta-keys before processing ────
    _saved_completed_ups = built.pop("__completed_upgrades__", None)
    _saved_events = built.pop("__events__", None)

    # ─── 1. Process BUILD commands ──────────────────────────
    for cmd in commands:
        if cmd.get("action") != "build":
            continue

        bid = cmd.get("builder_id", "") or cmd.get("unit_id", "") or cmd.get("entity_id", "")
        if bid not in built:
            continue
        builder = built[bid]
        if builder.get("entity_type") != "worker":
            continue

        btype = cmd.get("building_type", "barracks")
        owner = builder.get("owner", 1)

        # Check prerequisites
        if not check_prerequisites(built, owner, btype):
            continue

        # Get cost from buildings.json
        json_name = _BUILDING_TYPE_MAP.get(btype, btype)
        bdata = _load_building_data().get(json_name)
        if bdata and "cost" in bdata:
            cost_mine = bdata["cost"].get("mine", 0)
            cost_gas = bdata["cost"].get("gas", 0)
        else:
            # Fallback costs for simplified types
            cost_map = {"barracks": 150, "factory": 200, "starport": 200,
                        "supply_depot": 100, "refinery": 100, "base": 400}
            cost_mine = cost_map.get(btype, 100)
            cost_gas = 0

        pkey_mine = f"p{owner}_mineral"
        pkey_gas = f"p{owner}_gas"
        if res.get(pkey_mine, 0) < cost_mine:
            continue
        if res.get(pkey_gas, 0) < cost_gas:
            continue

        # Check position
        target_x = cmd.get("pos_x", builder["pos_x"])
        target_y = cmd.get("pos_y", builder["pos_y"])

        # Deduct cost
        res[pkey_mine] = res.get(pkey_mine, 0) - cost_mine
        if cost_gas > 0:
            res[pkey_gas] = res.get(pkey_gas, 0) - cost_gas

        # Get max health from buildings.json
        max_health = 100
        if bdata:
            max_health = bdata.get("hp", 100)

        race = get_race(owner)

        # Create the building
        new_id = f"{btype}_{tick}_{bid}"
        json_name = _BUILDING_TYPE_MAP.get(btype, btype)
        new_building = {
            "id": new_id,
            "owner": owner,
            "entity_type": "building",
            "building_type": btype,
            "unit_type": json_name,
            "pos_x": target_x,
            "pos_y": target_y,
            "health": 1,  # starts at 1 so combat doesn't kill it; real HP fills via build_progress
            "max_health": max_health,
            "is_constructing": True,
            "build_progress": 0,
            "builder_id": bid if race == "terran" else "",
            "production_queue": [],
            "production_timers": [],
            "upgrade_queue": [],
            "upgrade_timers": [],
        }

        # Protoss: add shield
        if race == "protoss" and bdata:
            sp = bdata.get("sp", 0)
            new_building["shield"] = 0
            new_building["max_shield"] = sp

        new_entities[new_id] = new_building

        # Race-specific builder handling
        if race == "terran":
            # Worker stays at site building
            built[bid] = {**builder,
                          "is_idle": False,
                          "target_x": target_x,
                          "target_y": target_y,
                          "building_id": new_id,
                          "returning_to_base": False,
                          "attack_target_id": "",
                          "deposit_pending": False}
        elif race == "zerg":
            # Drone is consumed
            built.pop(bid, None)
        elif race == "protoss":
            # Probe starts warp then is freed
            built[bid] = {**builder, "is_idle": True,
                          "target_x": None, "target_y": None,
                          "returning_to_base": False,
                          "attack_target_id": "",
                          "deposit_pending": False}

    built.update(new_entities)

    # ─── 2. Advance construction progress ────────────────────
    for eid, e in list(built.items()):
        if e.get("entity_type") != "building" or not e.get("is_constructing"):
            continue

        race = get_race(e.get("owner", 0))

        # Terran: builder should ideally stay at site, but for compatibility
        # with existing tests/AI, we advance progress unconditionally once started
        # (the old system didn't check builder presence)
        progress = e.get("build_progress", 0) + BUILD_PROGRESS_PER_TICK
        if progress >= 100:
            built[eid] = {**e, "build_progress": 100, "is_constructing": False,
                          "health": e.get("max_health", 100)}
            # Free the builder (Terran)
            if race == "terran":
                builder_id = e.get("builder_id", "")
                if builder_id in built:
                    b = built[builder_id]
                    built[builder_id] = {**b, "is_idle": True,
                                         "building_id": "",
                                         "target_x": None, "target_y": None}
        else:
            built[eid] = {**e, "build_progress": progress}

    # ─── 3. Process TRAIN commands ───────────────────────────
    for cmd in commands:
        if cmd.get("action") != "train":
            continue
        building_id = cmd.get("building_id", "") or cmd.get("entity_id", "")
        if building_id not in built:
            continue
        building = built[building_id]
        if building.get("entity_type") != "building":
            continue
        if building.get("is_constructing"):
            continue
        owner = building.get("owner", 1)
        utype = cmd.get("unit_type", "")
        # Infer from building type if unit_type not specified
        if not utype:
            btype = building.get("building_type", "base")
            _building_default_unit = {
                "barracks": "Marine",
                "factory": "Vulture",
                "starport": "Wraith",
            }
            utype = _building_default_unit.get(btype, "worker")
        json_unit = _UNIT_TYPE_MAP.get(utype, utype)

        # Check train prerequisites
        if not check_train_prerequisites(built, owner, building_id, utype):
            continue

        # Check supply
        if not check_supply(res, owner, utype):
            continue

        # Get cost
        udata = _load_unit_data().get(json_unit)
        if udata and "cost" in udata:
            cost_mine = udata["cost"].get("mine", 50)
            cost_gas = udata["cost"].get("gas", 0)
            train_ticks = udata["cost"].get("time", 200) // 10  # convert SC ticks to our ticks
        else:
            cost_map = {"worker": 50, "soldier": 100, "scout": 75}
            cost_mine = cost_map.get(utype, 50)
            cost_gas = 0
            train_ticks = 10

        pkey_mine = f"p{owner}_mineral"
        pkey_gas = f"p{owner}_gas"
        if res.get(pkey_mine, 0) < cost_mine:
            continue
        if res.get(pkey_gas, 0) < cost_gas:
            continue

        # Zerg: morph from larva
        race = get_race(owner)
        if race == "zerg":
            # Find a larva belonging to this building
            larva_id = None
            for lid, le in built.items():
                if (le.get("entity_type") == "unit" and le.get("unit_type") == "Larva"
                        and le.get("spawned_from", "") == building_id
                        and not le.get("morph_target", "")):
                    larva_id = lid
                    break

            if larva_id is not None:
                # Standard path: morph from larva
                res[pkey_mine] = res.get(pkey_mine, 0) - cost_mine
                if cost_gas > 0:
                    res[pkey_gas] = res.get(pkey_gas, 0) - cost_gas
                built[larva_id] = {**built[larva_id],
                                   "morph_target": json_unit,
                                   "morph_timer": train_ticks,
                                   "is_idle": False}
            else:
                # Fallback: direct queue (no larva available yet)
                # This allows training even before larva spawn stabilizes
                if len(building.get("production_queue", [])) >= 5:
                    continue
                res[pkey_mine] = res.get(pkey_mine, 0) - cost_mine
                if cost_gas > 0:
                    res[pkey_gas] = res.get(pkey_gas, 0) - cost_gas
                queue = list(building.get("production_queue", []))
                timers = list(building.get("production_timers", []))
                queue.append(json_unit)
                timers.append(train_ticks)
                built[building_id] = {**building, "production_queue": queue, "production_timers": timers}
        else:
            # Terran/Protoss: add to production queue
            if len(building.get("production_queue", [])) >= 5:
                continue
            res[pkey_mine] = res.get(pkey_mine, 0) - cost_mine
            if cost_gas > 0:
                res[pkey_gas] = res.get(pkey_gas, 0) - cost_gas

            queue = list(building.get("production_queue", []))
            timers = list(building.get("production_timers", []))
            queue.append(json_unit)
            timers.append(train_ticks)
            built[building_id] = {**building, "production_queue": queue, "production_timers": timers}

    # ─── 4. Advance production timers and spawn units ────────
    # Reverse mapping: JSON unit name → simplified entity_type
    json_to_simplified_unit = {
        "SCV": "worker", "Drone": "worker", "Probe": "worker",
        "Marine": "soldier", "Firebat": "soldier", "Ghost": "soldier", "Medic": "soldier",
        "Zealot": "soldier", "Dragoon": "soldier", "DarkTemplar": "soldier",
        "Zergling": "soldier", "Hydralisk": "soldier", "Lurker": "soldier",
        "Vulture": "scout", "Wraith": "scout", "Dropship": "scout",
        "Valkyrie": "scout", "BattleCruiser": "scout", "Goliath": "scout",
        "Tank": "soldier",
        "Scout_ship": "scout", "Shuttle": "scout", "Reaver": "soldier",
        "Observer": "scout", "Arbiter": "scout", "Carrier": "scout", "Corsair": "scout",
        "Overlord": "worker", "Queen": "scout", "Defiler": "scout",
        "Mutalisk": "scout", "Guardian": "scout", "Devourer": "scout",
        "Scourge": "scout", "Broodling": "soldier", "InfestedTerran": "soldier",
        "Ultralisk": "soldier", "Templar": "soldier",
        "Archon": "soldier", "DarkArchon": "soldier",
    }

    spawn_entities: dict[str, Any] = {}
    for eid, e in list(built.items()):
        if e.get("entity_type") != "building":
            continue
        if e.get("is_constructing"):
            continue
        queue = list(e.get("production_queue", []))
        timers = list(e.get("production_timers", []))
        if not queue or not timers:
            continue

        timers[0] -= 1
        if timers[0] <= 0:
            utype = queue.pop(0)
            timers.pop(0)
            owner = e["owner"]
            race = get_race(owner)

            # Protoss: check pylon power
            if race == "protoss":
                if not check_pylon_power(built, eid):
                    built[eid] = {**e, "production_queue": queue, "production_timers": timers}
                    continue

            # Determine simplified entity_type
            simplified_etype = json_to_simplified_unit.get(utype, "unit")
            if utype in ("worker", "soldier", "scout"):
                simplified_etype = utype

            uid = f"{utype}_{tick}_{eid}"
            stats = _resolve_unit_stats(utype)
            unit = _build_unit_entity(
                uid, utype, owner, simplified_etype,
                e["pos_x"] + 1.0, e["pos_y"] + 1.0,
                stats=stats,
            )

            spawn_entities[uid] = unit

            # Zerg: Zergling spawns as a pair (2 for 50 minerals)
            if utype == "Zergling" and race == "zerg":
                uid2 = f"{utype}_{tick+1}_{eid}"
                unit2 = {**unit, "id": uid2, "pos_x": e["pos_x"] + 1.5, "pos_y": e["pos_y"] + 1.5}
                spawn_entities[uid2] = unit2

            built[eid] = {**e, "production_queue": queue, "production_timers": timers}
        else:
            built[eid] = {**e, "production_timers": timers}

    built.update(spawn_entities)

    # ─── 5. Process Zerg morph (larva → unit) ────────────────
    morph_entities: dict[str, Any] = {}
    for eid, e in list(built.items()):
        if e.get("entity_type") not in ("unit", "worker", "soldier", "scout"):
            continue
        if e.get("unit_type") != "Larva":
            continue
        if not e.get("morph_target"):
            continue

        timer = e.get("morph_timer", 0) - 1
        if timer <= 0:
            # Morph complete — spawn the unit, remove larva
            utype = e["morph_target"]
            simplified_etype = json_to_simplified_unit.get(utype, "unit")
            uid = f"{utype}_{tick}_{eid}"
            stats = _resolve_unit_stats(utype)
            unit = _build_unit_entity(
                uid, utype, e["owner"], simplified_etype,
                e["pos_x"], e["pos_y"],
                stats=stats,
            )
            morph_entities[uid] = unit

            # Zerg: Zergling spawns as a pair (2 for 50 minerals)
            if utype == "Zergling":
                uid2 = f"{utype}_{tick+1}_{eid}"
                unit2 = {**unit, "id": uid2, "pos_x": e["pos_x"] + 0.5, "pos_y": e["pos_y"] + 0.5}
                morph_entities[uid2] = unit2

            built.pop(eid, None)
        else:
            built[eid] = {**e, "morph_timer": timer}

    built.update(morph_entities)

    # ─── 6. Process UPGRADE/RESEARCH commands ─────────────────────
    for cmd in commands:
        action = cmd.get("action", "")
        if action not in ("upgrade", "research"):
            continue
        building_id = cmd.get("building_id", "") or cmd.get("entity_id", "")
        if building_id not in built:
            continue
        building = built[building_id]
        if building.get("entity_type") != "building":
            continue
        if building.get("is_constructing"):
            continue
        owner = building.get("owner", 1)
        upgrade_name = cmd.get("upgrade_name", "")

        # Load upgrade data
        upgrade_data = _load_upgrade_data()
        udata = None
        for u in upgrade_data:
            if u.get("name") == upgrade_name:
                udata = u
                break
        if udata is None:
            continue

        # Check prerequisite level
        prereq_level = udata.get("prerequisite_level", 0)
        current_level = _get_upgrade_level(built, owner, upgrade_name)
        if current_level != prereq_level:
            continue

        # Check cost
        cost_mine = udata.get("cost", {}).get("mine", 0)
        cost_gas = udata.get("cost", {}).get("gas", 0)
        pkey_mine = f"p{owner}_mineral"
        pkey_gas = f"p{owner}_gas"
        if res.get(pkey_mine, 0) < cost_mine:
            continue
        if res.get(pkey_gas, 0) < cost_gas:
            continue

        # Deduct cost
        res[pkey_mine] = res.get(pkey_mine, 0) - cost_mine
        if cost_gas > 0:
            res[pkey_gas] = res.get(pkey_gas, 0) - cost_gas

        # Add to upgrade queue
        upgrade_queue = list(building.get("upgrade_queue", []))
        upgrade_timers = list(building.get("upgrade_timers", []))
        research_ticks = udata.get("time", 800) // 10  # convert SC ticks
        upgrade_queue.append(upgrade_name)
        upgrade_timers.append(research_ticks)
        built[building_id] = {**building,
                              "upgrade_queue": upgrade_queue,
                              "upgrade_timers": upgrade_timers}

    # ─── 7. Advance upgrade timers and apply upgrades ────────
    for eid, e in list(built.items()):
        if e.get("entity_type") != "building":
            continue
        upgrade_queue = list(e.get("upgrade_queue", []))
        upgrade_timers = list(e.get("upgrade_timers", []))
        if not upgrade_queue or not upgrade_timers:
            continue

        upgrade_timers[0] -= 1
        if upgrade_timers[0] <= 0:
            completed_upgrade = upgrade_queue.pop(0)
            upgrade_timers.pop(0)
            owner = e.get("owner", 1)

            # Apply upgrade globally: tag all relevant entities
            _apply_upgrade(built, owner, completed_upgrade)

            # Record completed upgrade in _saved_completed_ups
            if _saved_completed_ups is None:
                _saved_completed_ups = {}
            owner_ups = list(_saved_completed_ups.get(str(owner), []))
            owner_ups.append(completed_upgrade)
            _saved_completed_ups[str(owner)] = owner_ups

            # Emit RESEARCH_COMPLETED event
            from simcore.events import make_event, RESEARCH_COMPLETED
            if _saved_events is None:
                _saved_events = []
            _saved_events.append(
                make_event(RESEARCH_COMPLETED, tick,
                           upgrade_name=completed_upgrade,
                           owner=owner,
                           building_id=eid)
            )

            built[eid] = {**built.get(eid, e), "upgrade_queue": upgrade_queue, "upgrade_timers": upgrade_timers}
        else:
            built[eid] = {**e, "upgrade_timers": upgrade_timers}


    # ─── 7b. Process Zerg building morph (Hatchery→Lair→Hive) ─────────
    # Morph command: {"action": "morph_building", "building_id": "xxx", "morph_target": "morph_base"}
    # Supported: morph_base (Hatchery→Lair), morph_base2 (Lair→Hive)
    _ZERG_MORPH_MAP = {
        "morph_base": {"from": "base", "to": "morph_base", "json": "Lair",
                       "hp": 1800, "cost_mine": 150, "cost_gas": 100, "ticks": 600},
        "morph_base2": {"from": "morph_base", "to": "morph_base2", "json": "Hive",
                        "hp": 2500, "cost_mine": 200, "cost_gas": 150, "ticks": 600},
    }
    for cmd in commands:
        if cmd.get("action") != "morph_building":
            continue
        building_id = cmd.get("building_id", "") or cmd.get("entity_id", "")
        morph_key = cmd.get("morph_target", "")
        if building_id not in built or morph_key not in _ZERG_MORPH_MAP:
            continue
        building = built[building_id]
        if building.get("entity_type") != "building":
            continue
        if building.get("is_constructing"):
            continue
        owner = building.get("owner", 1)
        race = get_race(owner)
        if race != "zerg":
            continue
        minfo = _ZERG_MORPH_MAP[morph_key]
        current_bt = building.get("building_type", "")
        # Verify the building is the correct source type
        if current_bt != minfo["from"]:
            continue
        pkey_mine = f"p{owner}_mineral"
        pkey_gas = f"p{owner}_gas"
        if res.get(pkey_mine, 0) < minfo["cost_mine"]:
            continue
        if res.get(pkey_gas, 0) < minfo["cost_gas"]:
            continue
        # Deduct cost and start morph
        res[pkey_mine] = res.get(pkey_mine, 0) - minfo["cost_mine"]
        res[pkey_gas] = res.get(pkey_gas, 0) - minfo["cost_gas"]
        built[building_id] = {
            **building,
            "morph_target": morph_key,
            "morph_json": minfo["json"],
            "morph_timer": minfo["ticks"] // 10,  # convert SC ticks
            "morph_hp_target": minfo["hp"],
        }

    # Advance morph timers
    for eid, e in list(built.items()):
        if not e.get("morph_target"):
            continue
        timer = e.get("morph_timer", 0) - 1
        if timer <= 0:
            # Morph complete — transform the building
            mkey = e["morph_target"]
            minfo = _ZERG_MORPH_MAP.get(mkey, {})
            built[eid] = {
                **e,
                "building_type": minfo.get("to", e.get("building_type", "")),
                "unit_type": minfo.get("json", e.get("unit_type", "")),
                "max_health": minfo.get("hp", e.get("max_health", 100)),
                "morph_target": "",
                "morph_json": "",
                "morph_timer": 0,
                "morph_hp_target": 0,
            }
        else:
            built[eid] = {**e, "morph_timer": timer}

    # ─── 8. Terran: SCV repair ───────────────────────────────
    for cmd in commands:
        if cmd.get("action") != "repair":
            continue
        wid = cmd.get("unit_id", "") or cmd.get("entity_id", "")
        if wid not in built:
            continue
        worker = built[wid]
        if worker.get("entity_type") != "worker":
            continue
        owner = worker.get("owner", 1)
        race = get_race(owner)
        if race != "terran":
            continue
        target_id = cmd.get("target_id", "")
        target = built.get(target_id)
        if target is None or target.get("entity_type") != "building":
            continue
        if target.get("owner") != owner:
            continue
        if target.get("health", 0) >= target.get("max_health", 1):
            continue

        # Repair: increment HP slightly, cost minerals
        repair_amount = 5
        repair_cost = 1  # 1 mineral per 5 HP
        pkey_mine = f"p{owner}_mineral"
        if res.get(pkey_mine, 0) >= repair_cost:
            res[pkey_mine] = res.get(pkey_mine, 0) - repair_cost
            new_health = min(target["health"] + repair_amount, target["max_health"])
            built[target_id] = {**target, "health": new_health}
            built[wid] = {**worker, "is_idle": False,
                          "target_x": target["pos_x"],
                          "target_y": target["pos_y"]}

    # ─── 9. Protoss: Pylon power check ───────────────────────
    for eid, e in list(built.items()):
        if e.get("entity_type") != "building":
            continue
        if e.get("is_constructing"):
            continue
        owner = e.get("owner", 1)
        race = get_race(owner)
        if race != "protoss":
            continue
        # Check if building is powered
        if not check_pylon_power(built, eid):
            built[eid] = {**e, "powered": False}
        else:
            built[eid] = {**e, "powered": True}

    # ─── Restore meta-keys into built dict before returning ────
    if _saved_completed_ups is not None:
        built["__completed_upgrades__"] = _saved_completed_ups
    if _saved_events is not None:
        built["__events__"] = _saved_events

    return built, res


# ─── Upgrade Helpers ─────────────────────────────────────────

_UPGRADE_DATA: list[dict] | None = None


def _load_upgrade_data() -> list[dict]:
    global _UPGRADE_DATA
    if _UPGRADE_DATA is None:
        path = Path(__file__).resolve().parent.parent / "data" / "upgrades" / "upgrades.json"
        with open(path) as f:
            raw = json.load(f)
        _UPGRADE_DATA = raw.get("upgrades", [])
    return _UPGRADE_DATA


def _get_upgrade_level(entities: dict[str, Any], owner: int, upgrade_name: str) -> int:
    """Get the current level of an upgrade for a player."""
    max_level = 0
    for eid, e in entities.items():
        if e.get("owner") == owner:
            level = e.get("upgrades", {}).get(upgrade_name, 0)
            max_level = max(max_level, level)
    return max_level


def _apply_upgrade(entities: dict[str, Any], owner: int, upgrade_name: str) -> None:
    """Apply an upgrade globally to all relevant entities of the player.

    Handles three categories:
    1. Weapon/armor upgrades: +1 per level to attack/armor stats
    2. Research — property mods: range, speed, cooldown, etc.
    3. Research — ability unlocks: tagged on entities for future use
    """
    upgrade_data = _load_upgrade_data()
    udata = None
    for u in upgrade_data:
        if u.get("name") == upgrade_name:
            udata = u
            break
    if udata is None:
        return

    level = udata.get("level", 1)
    name = udata["name"]

    # ── Weapon/armor stat upgrades ──────────────────────────
    # Terran
    if "Infantry Weapons" in name:
        _apply_stat(entities, owner, "attack", +1,
                    unit_types=("Marine", "Ghost", "Firebat", "Medic"))
    elif "Infantry Armor" in name:
        _apply_stat(entities, owner, "armor", +1,
                    unit_types=("Marine", "Ghost", "Firebat", "Medic", "SCV"))
    elif "Vehicle Weapons" in name:
        _apply_stat(entities, owner, "attack", +1,
                    unit_types=("Vulture", "Goliath", "Tank"))
    elif "Vehicle Armor" in name:
        _apply_stat(entities, owner, "armor", +1,
                    unit_types=("Vulture", "Goliath", "Tank"))
    elif "Ship Weapons" in name:
        _apply_stat(entities, owner, "attack", +1,
                    unit_types=("Wraith", "BattleCruiser", "Valkyrie", "Vessel"))
    elif "Ship Armor" in name:
        _apply_stat(entities, owner, "armor", +1,
                    unit_types=("Wraith", "BattleCruiser", "Valkyrie", "Vessel", "Dropship"))

    # Zerg
    elif "Melee Attacks" in name:
        _apply_stat(entities, owner, "attack", +1,
                    unit_types=("Zergling", "Ultralisk", "Broodling"))
    elif "Missile Attacks" in name:
        _apply_stat(entities, owner, "attack", +1,
                    unit_types=("Hydralisk", "Mutalisk", "Guardian", "Devourer",
                                "Queen", "Defiler", "Scourge", "InfestedTerran"))
    elif "Carapace" in name and "Pneumatized" not in name:
        _apply_stat(entities, owner, "armor", +1,
                    unit_types=("Zergling", "Hydralisk", "Ultralisk", "Queen",
                                "Defiler", "Mutalisk", "Guardian", "Devourer",
                                "Scourge", "Broodling", "InfestedTerran", "Drone"))

    # Protoss
    elif "Ground Weapons" in name:
        _apply_stat(entities, owner, "attack", +1,
                    unit_types=("Zealot", "Dragoon", "HighTemplar", "DarkTemplar",
                                "Reaver", "Archon", "DarkArchon"))
    elif "Ground Armor" in name:
        _apply_stat(entities, owner, "armor", +1,
                    unit_types=("Zealot", "Dragoon", "HighTemplar", "DarkTemplar",
                                "Reaver", "Shuttle", "Archon", "DarkArchon", "Probe"))
    elif "Plasma Shields" in name:
        # Shields affect ALL Protoss units and buildings
        for eid, e in entities.items():
            if e.get("owner") == owner:
                if e.get("race") == "protoss" or e.get("unit_type", "") in (
                    "Zealot", "Dragoon", "HighTemplar", "DarkTemplar",
                    "Reaver", "Shuttle", "Observer", "Corsair", "Scout",
                    "Carrier", "Arbiter", "Archon", "DarkArchon", "Probe",
                ):
                    entities[eid] = {**e, "shields": e.get("shields", 0) + 5}

    # ── Research — property modifications ───────────────────
    elif name == "U-238 Shells":
        _apply_stat(entities, owner, "attack_range", 32,
                    unit_types=("Marine",))
    elif name == "StimPack Tech":
        _apply_ability(entities, owner, "stimpack",
                       unit_types=("Marine", "Firebat"))
    elif name == "Siege Tech":
        _apply_ability(entities, owner, "siege_mode",
                       unit_types=("Tank",))
    elif name == "Spider Mines":
        _apply_stat(entities, owner, "spider_mines", 4,
                    unit_types=("Vulture",))
    elif name == "Ion Thrusters":
        _apply_stat(entities, owner, "speed", 0.5,
                    unit_types=("Vulture",))
    elif name == "Charon Boosters":
        _apply_stat(entities, owner, "attack_range", 64,
                    unit_types=("Goliath",))
    elif name == "Cloaking Field":
        _apply_ability(entities, owner, "cloaking",
                       unit_types=("Wraith",))
    elif name == "Personal Cloaking":
        _apply_ability(entities, owner, "cloaking",
                       unit_types=("Ghost",))
    elif name == "Yamato Gun":
        _apply_ability(entities, owner, "yamato_gun",
                       unit_types=("BattleCruiser",))
    elif name == "EMP Shockwave":
        _apply_ability(entities, owner, "emp",
                       unit_types=("Vessel",))
    elif name == "Irradiate":
        _apply_ability(entities, owner, "irradiate",
                       unit_types=("Vessel",))
    elif name == "Lockdown":
        _apply_ability(entities, owner, "lockdown",
                       unit_types=("Ghost",))
    elif name == "Restoration":
        _apply_ability(entities, owner, "restoration",
                       unit_types=("Medic",))
    elif name == "Optical Flare":
        _apply_ability(entities, owner, "optical_flare",
                       unit_types=("Medic",))
    elif name == "Caduceus Reactor":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Medic",))
    elif name == "Moebius Reactor":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Ghost",))
    elif name == "Apollo Reactor":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Vessel",))
    elif name == "Titan Reactor":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Vessel",))
    elif name == "Colossus Reactor":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("BattleCruiser",))
    elif name == "Ocular Implants":
        _apply_stat(entities, owner, "sight", 32,
                    unit_types=("Ghost",))
    # Zerg research
    elif name == "Burrow":
        _apply_ability(entities, owner, "burrow",
                       unit_types=("Drone", "Zergling", "Hydralisk", "Ultralisk",
                                    "Defiler", "Queen"))
    elif name == "Ventral Sacs":
        _apply_ability(entities, owner, "transport",
                       unit_types=("Overlord",))
    elif name == "Antennas":
        _apply_stat(entities, owner, "sight", 32,
                    unit_types=("Overlord",))
    elif name == "Pneumatized Carapace":
        _apply_stat(entities, owner, "speed", 0.5,
                    unit_types=("Overlord",))
    elif name == "Metabolic Boost":
        _apply_stat(entities, owner, "speed", 0.5,
                    unit_types=("Zergling",))
    elif name == "Adrenal Glands":
        _apply_stat(entities, owner, "attack_speed", -2,
                    unit_types=("Zergling",))
    elif name == "Muscular Augments":
        _apply_stat(entities, owner, "speed", 0.3,
                    unit_types=("Hydralisk",))
    elif name == "Grooved Spines":
        _apply_stat(entities, owner, "attack_range", 32,
                    unit_types=("Hydralisk",))
    elif name == "Lurker Aspect":
        _apply_ability(entities, owner, "lurker_morph",
                       unit_types=("Hydralisk",))
    elif name == "Chitinous Plating":
        _apply_stat(entities, owner, "armor", 2,
                    unit_types=("Ultralisk",))
    elif name == "Anabolic Synthesis":
        _apply_stat(entities, owner, "speed", 0.5,
                    unit_types=("Ultralisk",))
    elif name == "Gamete Meiosis":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Queen",))
    elif name == "Metasynaptic Node":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Defiler",))
    # Protoss research
    elif name == "Singularity Charge":
        _apply_stat(entities, owner, "attack_range", 64,
                    unit_types=("Dragoon",))
    elif name == "Leg Enhancements":
        _apply_stat(entities, owner, "speed", 0.5,
                    unit_types=("Zealot",))
    elif name == "Gravitic Drive":
        _apply_stat(entities, owner, "speed", 0.5,
                    unit_types=("Shuttle",))
    elif name == "Scarab Damage":
        _apply_stat(entities, owner, "attack", 25,
                    unit_types=("Reaver",))
    elif name == "Gravitic Boosters":
        _apply_stat(entities, owner, "speed", 0.5,
                    unit_types=("Observer",))
    elif name == "Sensor Array":
        _apply_stat(entities, owner, "sight", 40,
                    unit_types=("Observer",))
    elif name == "Gravitic Catapult":
        _apply_stat(entities, owner, "attack_range", 64,
                    unit_types=("Carrier",))
    elif name == "Apial Sensors":
        _apply_stat(entities, owner, "sight", 32,
                    unit_types=("Scout",))
    elif name == "Argus Jewel":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Corsair",))
    elif name == "Argus Talisman":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("DarkTemplar",))
    elif name == "Khaydarin Amulet":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("HighTemplar",))
    elif name == "Khaydarin Core":
        _apply_stat(entities, owner, "energy_bonus", 50,
                    unit_types=("Arbiter",))
    elif name == "Khaydarin Shield":
        _apply_stat(entities, owner, "shield_regen", 1,
                    unit_types=("Arbiter",))

    # Tag the upgrade on all owned entities (for prerequisite tracking)
    for eid, e in entities.items():
        if e.get("owner") == owner:
            ups = dict(e.get("upgrades", {}))
            ups[name] = ups.get(name, 0) + 1
            entities[eid] = {**e, "upgrades": ups}


def _apply_stat(
    entities: dict[str, Any],
    owner: int,
    stat: str,
    value: int | float,
    *,
    unit_types: tuple[str, ...],
) -> None:
    """Add *value* to *stat* on all owned units matching *unit_types*."""
    for eid, e in entities.items():
        if e.get("owner") != owner:
            continue
        utype = e.get("unit_type", e.get("entity_type", ""))
        if utype not in unit_types:
            continue
        old = e.get(stat, 0)
        entities[eid] = {**e, stat: old + value}


def _apply_ability(
    entities: dict[str, Any],
    owner: int,
    ability: str,
    *,
    unit_types: tuple[str, ...],
) -> None:
    """Tag *ability* as unlocked on all owned units matching *unit_types*."""
    for eid, e in entities.items():
        if e.get("owner") != owner:
            continue
        utype = e.get("unit_type", e.get("entity_type", ""))
        if utype not in unit_types:
            continue
        abils = list(e.get("abilities", []))
        if ability not in abils:
            abils.append(ability)
        entities[eid] = {**e, "abilities": abils}


# ─── Convenience: Full Construction Pipeline ──────────────────

def process_full_construction(
    state: GameState,
    commands: list[dict],
    tick: int,
) -> GameState:
    """Full construction pipeline for integration with engine.

    Returns a new GameState.
    """
    entities, resources = process_construction(
        state.entities, state.resources, commands, tick
    )
    return GameState(
        tick=state.tick,
        entities=entities,
        fog_of_war=state.fog_of_war,
        resources=resources,
        is_terminal=state.is_terminal,
        winner=state.winner,
    )