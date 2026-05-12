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
    "StarGate": "StarGate",
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
    "Firebat": "Firebat", "Ghost": "Ghost", "Medic": "Medic",
    "Vulture": "Vulture", "Tank": "Tank", "Goliath": "Goliath",
    "Wraith": "Wraith", "Dropship": "Dropship", "Vessel": "Vessel",
    "BattleCruiser": "BattleCruiser", "Valkyrie": "Valkyrie",
    # Zerg
    "Drone": "Drone", "Zergling": "Zergling", "Hydralisk": "Hydralisk",
    "Lurker": "Lurker", "Ultralisk": "Ultralisk", "Overlord": "Overlord",
    "Queen": "Queen", "Defiler": "Defiler", "Mutalisk": "Mutalisk",
    "Guardian": "Guardian", "Devourer": "Devourer", "Scourge": "Scourge",
    "Larva": "Larva", "Broodling": "Broodling", "InfestedTerran": "InfestedTerran",
    # Protoss
    "Probe": "Probe", "Zealot": "Zealot", "Dragoon": "Dragoon",
    "Templar": "Templar", "DarkTemplar": "DarkTemplar",
    "Archon": "Archon", "DarkArchon": "DarkArchon",
    "Reaver": "Reaver", "Shuttle": "Shuttle", "Observer": "Observer",
    "Arbiter": "Arbiter", "Scout": "Scout", "Carrier": "Carrier",
    "Corsair": "Corsair",
    "scout_unit": "Probe",  # internal type → real name
}

# Default unit stats for spawning
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

# Simplified building types: base can train workers, barracks trains soldiers/scouts
    simplified_train = {
        "base": ["worker", "soldier", "scout",
                  # Zerg from base/Hatchery
                  "Drone", "Overlord", "Zergling", "Hydralisk", "Lurker",
                  "Ultralisk", "Queen", "Defiler", "Mutalisk", "Guardian",
                  "Devourer", "Scourge", "Broodling", "InfestedTerran",
                  # Protoss from base/Nexus
                  "Probe", "Zealot", "Dragoon", "HighTemplar", "DarkTemplar",
                  "Reaver", "Shuttle", "Observer", "Arbiter", "Scout_ship",
                  "Carrier", "Corsair", "Archon", "DarkArchon",
                  # Terran from base/CommandCenter
                  "SCV", "Marine", "Firebat", "Ghost", "Medic",
                  "Vulture", "Tank", "Goliath", "Wraith", "Dropship",
                  "Vessel", "BattleCruiser", "Valkyrie"],
        "barracks": ["soldier", "scout", "worker",
                     "Marine", "Firebat", "Ghost", "Medic",
                     "Zealot", "Dragoon", "HighTemplar", "DarkTemplar",
                     "Zergling", "Hydralisk", "Drone", "Overlord"],
        "factory": ["soldier", "scout"],
        "starport": ["scout"],
        # Zerg buildings (JSON names)
        "Hatchery": ["Drone", "Overlord", "Zergling", "Hydralisk", "Lurker", "Ultralisk", "Queen", "Defiler", "Mutalisk", "Guardian", "Devourer", "Scourge", "Broodling", "InfestedTerran"],
        "Lair": ["Drone", "Overlord", "Zergling", "Hydralisk", "Lurker", "Ultralisk", "Queen", "Defiler", "Mutalisk", "Guardian", "Devourer", "Scourge", "Broodling", "InfestedTerran"],
        "Hive": ["Drone", "Overlord", "Zergling", "Hydralisk", "Lurker", "Ultralisk", "Queen", "Defiler", "Mutalisk", "Guardian", "Devourer", "Scourge", "Broodling", "InfestedTerran"],
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
        # Protoss buildings (JSON names)
        "Nexus": ["Probe", "Zealot", "Dragoon", "HighTemplar", "DarkTemplar", "Reaver", "Shuttle", "Observer", "Arbiter", "Scout", "Carrier", "Corsair", "Archon", "DarkArchon"],
        "Gateway": ["Zealot", "Dragoon", "HighTemplar", "DarkTemplar"],
        "CyberneticsCore": ["SingularityCharge", "AirWeapons", "AirArmor"],
        "Forge": ["GroundWeapons", "GroundArmor", "PlasmaShields"],
        "RoboticsFacility": ["Reaver", "Shuttle"],
        "StarGate": ["Scout", "Carrier", "Corsair", "Arbiter"],
        "CitadelOfAdun": ["LegEnhancement"],
        "TemplarArchives": ["HighTemplar", "PsionicStorm", "Hallucination", "KhaydarinAmulet"],
        "RoboticsSupportBay": ["Reaver", "ScarabDamage"],
        "FleetBeacon": ["Carrier", "CarrierCapacity", "ScoutSpeed", "CorsairDisruptionWeb"],
        "Observatory": ["Observer", "ObserverSpeed", "ObserverSight"],
        "ArbiterTribunal": ["Arbiter", "StasisField", "Recall"],
        "Pylon": [],
        "Assimilator": [],
        "PhotonCannon": [],
        "ShieldBattery": [],
        # Terran buildings (JSON names)
        "CommandCenter": ["SCV", "Marine", "Firebat", "Ghost", "Medic", "Vulture", "Tank", "Goliath", "Wraith", "Dropship", "Vessel", "BattleCruiser", "Valkyrie"],
        "Barracks": ["Marine", "Firebat", "Ghost", "Medic"],
        "Factory": ["Vulture", "Tank", "Goliath"],
        "Starport": ["Wraith", "Dropship", "Vessel", "BattleCruiser", "Valkyrie"],
        "Academy": ["StimPack", "U238Shells", "Medic"],
        "EngineeringBay": ["InfantryWeapons", "InfantryArmor"],
        "Armory": ["VehicleWeapons", "VehiclePlating", "ShipWeapons", "ShipPlating"],
        "ScienceFacility": ["Vessel", "EMPShockwave", "Irradiate", "TitanReactor", "ApolloReactor"],
        "SupplyDepot": [],
        "Refinery": [],
        "MissileTurret": [],
        "Bunker": [],
        "ComstatStation": ["ComsatScan"],
        "MachineShop": ["SpiderMines", "IonThrusters", "SiegeTech"],
        "NuclearSilo": ["NuclearStrike"],
    }

    if bt in simplified_train:
        if unit_type not in simplified_train[bt]:
            return False
    elif bdata and "train" in bdata:
        trainable = bdata["train"]
        json_unit = _UNIT_TYPE_MAP.get(unit_type, unit_type)
        if json_unit not in trainable and unit_type not in trainable:
            return False

    return True


def check_supply(
    resources: dict[str, int],
    owner: int,
    unit_type: str,
) -> bool:
    """Check if training this unit would exceed supply cap.

    Supply enforcement is lenient for backward compatibility:
    - If no dedicated supply buildings exist (supply from base only), don't block
    - Only enforce when player has built supply structures (SupplyDepot, Pylon, Overlord)
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

    # If supply cap hasn't been calculated (0) or only comes from bases (10),
    # allow training for backward compatibility with simplified mode
    if supply_cap <= 0:
        return True

    # Check if the player has any dedicated supply buildings beyond the base
    # The base provides 10 supply. If supply_cap > 10, they have supply structures.
    # In simplified mode, base provides 10, so only enforce when cap > 10
    base_supply = 10  # starting supply from base
    if supply_cap <= base_supply:
        return True  # No dedicated supply buildings — don't block

    return supply_used + supply_cost <= supply_cap or supply_used >= supply_cap


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
                    "RoboticsFacility", "StarGate", "CitadelOfAdun", "FleetBeacon",
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
        new_building = {
            "id": new_id,
            "owner": owner,
            "entity_type": "building",
            "building_type": btype,
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
        utype = cmd.get("unit_type", "worker")
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
            uid = f"{utype}_{tick}_{eid}"
            stats = _DEFAULT_UNIT_STATS.get(utype, _DEFAULT_UNIT_STATS["SCV"])
            owner = e["owner"]
            race = get_race(owner)

            # Protoss: check pylon power for Gateway etc.
            if race == "protoss":
                if not check_pylon_power(built, eid):
                    # Building unpowered — cannot produce
                    built[eid] = {**e, "production_queue": queue, "production_timers": timers}
                    continue

            # Determine simplified entity_type for the spawned unit
            simplified_etype = json_to_simplified_unit.get(utype, "unit")
            # For simplified unit types (worker/soldier/scout), use them directly
            if utype in ("worker", "soldier", "scout"):
                simplified_etype = utype

            unit = {
                "id": uid,
                "owner": owner,
                "entity_type": simplified_etype,
                "unit_type": utype,
                "pos_x": e["pos_x"] + 1.0,
                "pos_y": e["pos_y"] + 1.0,
                "health": stats["health"],
                "max_health": stats["max_health"],
                "speed": stats["speed"],
                "attack": stats["attack"],
                "attack_range": stats["attack_range"],
                "is_idle": True,
                "carry_amount": 0,
                "carry_capacity": stats["carry_capacity"],
                "target_x": None,
                "target_y": None,
                "returning_to_base": False,
                "attack_target_id": "",
                "deposit_pending": False,
                "is_flying": False,
            }

            # Add shield for Protoss
            if race == "protoss":
                udata = _load_unit_data().get(utype, {})
                sp = udata.get("sp", 0) if udata else 0
                unit["shield"] = sp
                unit["max_shield"] = sp

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
            uid = f"{utype}_{tick}_{eid}"
            stats = _DEFAULT_UNIT_STATS.get(utype, _DEFAULT_UNIT_STATS["Zergling"])
            simplified_etype = json_to_simplified_unit.get(utype, "unit")

            unit = {
                "id": uid,
                "owner": e["owner"],
                "entity_type": simplified_etype,
                "unit_type": utype,
                "pos_x": e["pos_x"],
                "pos_y": e["pos_y"],
                "health": stats["health"],
                "max_health": stats["max_health"],
                "speed": stats["speed"],
                "attack": stats["attack"],
                "attack_range": stats["attack_range"],
                "is_idle": True,
                "carry_amount": 0,
                "carry_capacity": stats["carry_capacity"],
                "target_x": None,
                "target_y": None,
                "returning_to_base": False,
                "attack_target_id": "",
                "deposit_pending": False,
                "is_flying": False,
            }
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

    # ─── 6. Process UPGRADE commands ─────────────────────────
    for cmd in commands:
        if cmd.get("action") != "upgrade":
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

            built[eid] = {**e, "upgrade_queue": upgrade_queue, "upgrade_timers": upgrade_timers}
        else:
            built[eid] = {**e, "upgrade_timers": upgrade_timers}

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
    """Apply an upgrade globally to all relevant entities of the player."""
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

    # Apply weapon/armor upgrades
    if "Infantry Weapons" in name:
        for eid, e in entities.items():
            if e.get("owner") == owner and e.get("entity_type") in ("unit", "worker", "soldier", "scout"):
                utype = e.get("unit_type", e.get("entity_type", ""))
                if utype in ("Marine", "Ghost", "Firebat", "soldier", "Medic"):
                    entities[eid] = {**e, "attack": e.get("attack", 0) + 1}
    elif "Infantry Armor" in name:
        for eid, e in entities.items():
            if e.get("owner") == owner and e.get("entity_type") in ("unit", "worker", "soldier", "scout"):
                utype = e.get("unit_type", e.get("entity_type", ""))
                if utype in ("Marine", "Ghost", "Firebat", "soldier", "Medic", "worker", "SCV"):
                    entities[eid] = {**e, "armor": e.get("armor", 0) + 1}
    elif "Vehicle Weapons" in name:
        for eid, e in entities.items():
            if e.get("owner") == owner and e.get("entity_type") in ("unit",):
                utype = e.get("unit_type", "")
                if utype in ("Vulture", "Tank", "Goliath"):
                    entities[eid] = {**e, "attack": e.get("attack", 0) + 1}
    elif "Vehicle Armor" in name or "Vehicle Plating" in name:
        for eid, e in entities.items():
            if e.get("owner") == owner and e.get("entity_type") in ("unit",):
                utype = e.get("unit_type", "")
                if utype in ("Vulture", "Tank", "Goliath"):
                    entities[eid] = {**e, "armor": e.get("armor", 0) + 1}
    elif "Ship Weapons" in name:
        for eid, e in entities.items():
            if e.get("owner") == owner and e.get("entity_type") in ("unit",):
                utype = e.get("unit_type", "")
                if utype in ("Wraith", "BattleCruiser", "Valkyrie"):
                    entities[eid] = {**e, "attack": e.get("attack", 0) + 1}
    elif "Ship Armor" in name or "Ship Plating" in name:
        for eid, e in entities.items():
            if e.get("owner") == owner and e.get("entity_type") in ("unit",):
                utype = e.get("unit_type", "")
                if utype in ("Wraith", "BattleCruiser", "Valkyrie"):
                    entities[eid] = {**e, "armor": e.get("armor", 0) + 1}

    # Tag the upgrade on all owned entities
    for eid, e in entities.items():
        if e.get("owner") == owner:
            ups = dict(e.get("upgrades", {}))
            ups[name] = ups.get(name, 0) + 1
            entities[eid] = {**e, "upgrades": ups}


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