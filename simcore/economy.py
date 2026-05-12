"""Economy system: resource gathering, depositing, and player resource tracking.

Pipeline per tick:
  1. process_gathering(state, commands) — workers harvest minerals/gas, return to base
  2. process_resources(state) — update per-player mineral/gas/supply counters
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from simcore.state import GameState

# ─── Constants ───────────────────────────────────────────────

GATHER_RATE_MINERAL = 5.0   # amount gathered per tick at a mineral node
GATHER_RATE_GAS = 4.0       # amount gathered per tick at a refinery/extractor/assimilator
GATHER_INTERACT_RANGE = 3.0 # proximity needed to gather
WORKER_RETURN_SPEED = 3.0   # speed when returning to base (slightly faster)
BASE_DEPOSIT_RANGE = 2.0    # proximity to base to deposit
LARVA_SPAWN_INTERVAL = 30   # ticks between larva spawns
LARVA_MAX = 3               # max larva per Hatchery/Lair/Hive
PYLON_POWER_RANGE = 6.0     # range of pylon power field (in world units)
SHIELD_REGEN_RATE = 0.5     # shields regenerate per tick when not recently hit

# ─── Data Loading ────────────────────────────────────────────

_BUILDING_DATA: dict[str, dict] | None = None
_UNIT_DATA: dict[str, dict] | None = None


def _load_building_data() -> dict[str, dict]:
    global _BUILDING_DATA
    if _BUILDING_DATA is None:
        path = Path(__file__).resolve().parent.parent / "data" / "buildings" / "buildings.json"
        with open(path) as f:
            raw = json.load(f)
        _BUILDING_DATA = {}
        for race_data in raw.values():
            if isinstance(race_data, dict):
                for bname, bdata in race_data.items():
                    if isinstance(bdata, dict) and "name" in bdata:
                        _BUILDING_DATA[bname] = bdata
    return _BUILDING_DATA


def _load_unit_data() -> dict[str, dict]:
    global _UNIT_DATA
    if _UNIT_DATA is None:
        path = Path(__file__).resolve().parent.parent / "data" / "units" / "units.json"
        with open(path) as f:
            raw = json.load(f)
        _UNIT_DATA = {}
        for race_key, race_val in raw.items():
            if race_key == "_meta":
                continue
            if isinstance(race_val, dict):
                for uname, udata in race_val.items():
                    if isinstance(udata, dict) and "name" in udata:
                        _UNIT_DATA[uname] = udata
    return _UNIT_DATA


def get_building_data(building_type: str) -> dict | None:
    return _load_building_data().get(building_type)


def get_unit_data(unit_type: str) -> dict | None:
    return _load_unit_data().get(unit_type)


# ─── Helpers ─────────────────────────────────────────────────

def _dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x1 - x2, y1 - y2)


def _find_nearest_resource(entities: dict[str, Any], owner: int, px: float, py: float, rtype: str = "mineral") -> dict | None:
    """Find the nearest resource node of a given type."""
    best = None
    best_d = 999999.0
    for eid, e in entities.items():
        if e.get("entity_type") != "resource":
            continue
        if e.get("resource_type", "") != rtype:
            continue
        if e.get("resource_amount", 0) <= 0:
            continue
        d = _dist(px, py, e.get("pos_x", 0), e.get("pos_y", 0))
        if d < best_d:
            best_d = d
            best = {**e, "id": eid}
    return best


def _find_nearest_base(entities: dict[str, Any], owner: int, px: float, py: float) -> dict | None:
    """Find nearest friendly base (building_type='base' or 'CommandCenter' or 'Nexus' or 'Hatchery' etc.)."""
    base_types = {"base", "CommandCenter", "Nexus", "Hatchery", "Lair", "Hive"}
    best = None
    best_dist = float("inf")
    for eid, e in entities.items():
        if e.get("owner") == owner and e.get("entity_type") == "building":
            bt = e.get("building_type", "")
            if bt in base_types and e.get("health", 0) > 0:
                d = _dist(px, py, e["pos_x"], e["pos_y"])
                if d < best_dist:
                    best_dist = d
                    best = e
    return best


def _find_refinery_on_geyser(entities: dict[str, Any], owner: int, geyser_id: str) -> dict | None:
    """Find a refinery/extractor/assimilator on the given geyser for the given owner."""
    geyser = entities.get(geyser_id)
    if geyser is None:
        return None
    gx, gy = geyser["pos_x"], geyser["pos_y"]
    refinery_types = {"Refinery", "Extractor", "Assimilator", "refinery"}
    for eid, e in entities.items():
        if e.get("owner") == owner and e.get("entity_type") == "building":
            bt = e.get("building_type", "")
            if bt in refinery_types and e.get("health", 0) > 0:
                d = _dist(gx, gy, e["pos_x"], e["pos_y"])
                if d < 2.0:  # close enough = on the geyser
                    return e
    return None


def _is_pylon_powered(entities: dict[str, Any], owner: int, px: float, py: float) -> bool:
    """Check if position is within a friendly Pylon's power range."""
    for eid, e in entities.items():
        if (e.get("owner") == owner and e.get("entity_type") == "building"
                and e.get("building_type") == "Pylon"
                and e.get("health", 0) > 0
                and not e.get("is_constructing", False)):
            d = _dist(px, py, e["pos_x"], e["pos_y"])
            if d <= PYLON_POWER_RANGE:
                return True
    return False


# ─── Gathering ──────────────────────────────────────────────

def process_gathering(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process resource gathering: workers mine minerals or siphon gas.

    Flow:
      - Worker near mineral node → mines at GATHER_RATE_MINERAL per tick
      - Worker near gas geyser WITH refinery → mines at GATHER_RATE_GAS per tick
      - Gas without refinery: no gathering (Terran); Zerg needs Extractor; Protoss needs Assimilator
      - When carry_amount >= carry_capacity → flag returning_to_base
      - When worker arrives at base (deposit_pending) → add carry to player resources, reset carry

    Returns (updated_entities, updated_resources).
    """
    gathered = dict(entities)
    res = dict(resources)
    to_remove: set[str] = set()

    # 1. Deposit pending (worker arrived at base)
    for uid, e in list(gathered.items()):
        if e.get("deposit_pending"):
            carried = e.get("carry_amount", 0)
            if carried > 0:
                # Determine resource key based on carry_type
                carry_type = e.get("carry_type", "mineral")
                pkey = f"p{e['owner']}_{carry_type}"
                res[pkey] = res.get(pkey, 0) + int(carried)
            updates = {
                "carry_amount": 0,
                "carry_type": "mineral",
                "deposit_pending": False,
                "is_idle": True,
                "target_x": None,
                "target_y": None,
                "returning_to_base": False,
            }
            gathered[uid] = {**e, **updates}
            continue

    # 2. Process returning workers: check if they arrived at base
    for uid, e in list(gathered.items()):
        if e.get("entity_type") != "worker" or not e.get("returning_to_base"):
            continue
        base = _find_nearest_base(gathered, e.get("owner", 0), e["pos_x"], e["pos_y"])
        if base is None:
            # No base found — become idle
            gathered[uid] = {**e, "returning_to_base": False, "is_idle": True,
                             "target_x": None, "target_y": None}
            continue
        d = _dist(e["pos_x"], e["pos_y"], base["pos_x"], base["pos_y"])
        if d <= BASE_DEPOSIT_RANGE:
            # Arrived at base → deposit
            gathered[uid] = {**e, "deposit_pending": True, "returning_to_base": False}
        # else: still moving (handled by apply_movement)

    # 3. Active gathering: workers near resources auto-gather until full
    for uid, e in list(gathered.items()):
        if e.get("entity_type") != "worker":
            continue
        if e.get("returning_to_base") or e.get("deposit_pending"):
            continue
        if e.get("carry_amount", 0) >= e.get("carry_capacity", 10.0):
            # Full → start returning
            gathered[uid] = {**e, "is_idle": False, "returning_to_base": True}
            # Set target to nearest base
            base = _find_nearest_base(gathered, e.get("owner", 0), e["pos_x"], e["pos_y"])
            if base:
                gathered[uid] = {**gathered[uid], "target_x": base["pos_x"], "target_y": base["pos_y"]}
            continue

        # If worker is currently gathering (not idle, near target resource)
        if not e.get("is_idle", True) and e.get("gather_target_id", ""):
            # Find the resource they're near
            target_id = e.get("gather_target_id", "")
            if target_id and target_id in gathered:
                node = gathered[target_id]
                if node.get("entity_type") == "resource" and node.get("resource_amount", 0) > 0:
                    d_to_node = _dist(e["pos_x"], e["pos_y"], node["pos_x"], node["pos_y"])
                    if d_to_node > GATHER_INTERACT_RANGE:
                        continue  # not close enough yet
                    resource_type = node.get("resource_type", "mineral")
                    # Gas requires a refinery on the geyser
                    if resource_type == "gas":
                        refinery = _find_refinery_on_geyser(
                            gathered, e.get("owner", 0), target_id
                        )
                        if refinery is None:
                            continue  # can't gather gas without refinery
                    rate = GATHER_RATE_GAS if resource_type == "gas" else GATHER_RATE_MINERAL
                    amount = min(rate, node.get("resource_amount", 0))
                    carry = e.get("carry_amount", 0) + amount
                    cap = e.get("carry_capacity", 10.0)
                    carry_type = resource_type
                    if carry >= cap:
                        gathered[uid] = {
                            **e, "carry_amount": cap, "carry_type": carry_type,
                            "is_idle": False, "returning_to_base": True,
                        }
                        base = _find_nearest_base(gathered, e.get("owner", 0), e["pos_x"], e["pos_y"])
                        if base:
                            gathered[uid] = {**gathered[uid], "target_x": base["pos_x"], "target_y": base["pos_y"]}
                    else:
                        gathered[uid] = {**e, "carry_amount": carry, "carry_type": carry_type, "is_idle": False}
                    new_amount = node.get("resource_amount", 0) - amount
                    if new_amount <= 0:
                        to_remove.add(target_id)
                    else:
                        gathered[target_id] = {**node, "resource_amount": new_amount}

    # 4. Process new gather commands (assign idle workers to resources)
    for cmd in commands:
        if cmd.get("action") != "gather":
            continue
        wid = cmd.get("worker_id", "") or cmd.get("unit_id", "") or cmd.get("entity_id", "")
        if wid not in gathered:
            continue
        worker = gathered[wid]
        if worker.get("entity_type") != "worker":
            continue
        if worker.get("returning_to_base") or worker.get("deposit_pending"):
            continue
        # Allow re-assignment even if not idle (switch targets)
        # But if actively carrying, only allow if they want to return first

        rid = cmd.get("resource_id", "")
        if rid not in gathered:
            continue
        node = gathered[rid]
        if node.get("entity_type") != "resource":
            continue
        if node.get("resource_amount", 0) <= 0:
            continue

        resource_type = node.get("resource_type", "mineral")
        # Gas requires a refinery on the geyser
        if resource_type == "gas":
            refinery = _find_refinery_on_geyser(gathered, worker.get("owner", 0), rid)
            if refinery is None:
                continue  # can't gather gas without refinery

        # Check proximity
        d = _dist(worker["pos_x"], worker["pos_y"], node["pos_x"], node["pos_y"])
        if d > GATHER_INTERACT_RANGE:
            # Not at node yet → set target to move there
            gathered[wid] = {**worker,
                             "target_x": node["pos_x"],
                             "target_y": node["pos_y"],
                             "is_idle": False,
                             "gather_target_id": rid,
                             "returning_to_base": False,
                             "attack_target_id": ""}
            continue

        # At node — gather
        rate = GATHER_RATE_GAS if resource_type == "gas" else GATHER_RATE_MINERAL
        amount = min(rate, node.get("resource_amount", 0))
        carry = worker.get("carry_amount", 0) + amount
        cap = worker.get("carry_capacity", 10.0)

        if carry >= cap:
            gathered[wid] = {**worker, "carry_amount": cap, "carry_type": resource_type,
                             "is_idle": False, "returning_to_base": True,
                             "gather_target_id": rid}
            base = _find_nearest_base(gathered, worker.get("owner", 0), worker["pos_x"], worker["pos_y"])
            if base:
                gathered[wid] = {**gathered[wid], "target_x": base["pos_x"], "target_y": base["pos_y"]}
        else:
            gathered[wid] = {**worker, "carry_amount": carry, "carry_type": resource_type,
                             "is_idle": False, "gather_target_id": rid}

        # Deplete node
        new_amount = node.get("resource_amount", 0) - amount
        if new_amount <= 0:
            to_remove.add(rid)
        else:
            gathered[rid] = {**node, "resource_amount": new_amount}

    for eid in to_remove:
        gathered.pop(eid, None)

    # 5. Auto-assign idle workers to nearest mineral patch
    for uid, e in list(gathered.items()):
        if e.get("entity_type") != "worker":
            continue
        if not e.get("is_idle", True):
            continue
        if e.get("returning_to_base") or e.get("deposit_pending"):
            continue
        if e.get("carry_amount", 0) > 0:
            continue
        # Skip workers with explicit move/attack targets (player-assigned)
        if e.get("target_x") is not None or e.get("attack_target_id", ""):
            continue
        owner = e.get("owner", 0)
        nearest = _find_nearest_resource(gathered, owner, e["pos_x"], e["pos_y"], "mineral")
        if nearest is None:
            continue
        gathered[uid] = {**e, "target_x": nearest["pos_x"], "target_y": nearest["pos_y"],
                         "is_idle": False, "gather_target_id": nearest["id"],
                         "returning_to_base": False, "attack_target_id": ""}

    return gathered, res


# ─── Resource Tracking ──────────────────────────────────────

def process_resources(state: GameState) -> dict[str, int]:
    """Recompute per-player supply counts from entity state.

    Returns updated resources dict with:
      - pN_mineral, pN_gas (from existing resources, not modified here)
      - pN_supply_used: sum of supply cost for all owned units
      - pN_supply_cap: sum of supply provided by owned supply-providing buildings/units
    """
    entities = state.entities
    res = dict(state.resources)

    # Supply data from building/unit JSON
    building_data = _load_building_data()
    unit_data = _load_unit_data()

    # Mapping from simplified types to JSON names for lookup
    simplified_to_json = {
        "base": "CommandCenter",
        "barracks": "Barracks",
        "factory": "Factory",
        "starport": "Starport",
        "supply_depot": "SupplyDepot",
        "refinery": "Refinery",
    }

    for pid in (1, 2):
        supply_used = 0
        supply_cap = 0

        for eid, e in entities.items():
            if e.get("owner") != pid:
                continue

            etype = e.get("entity_type", "")
            btype = e.get("building_type", "")

            # Supply cap from buildings
            if etype == "building" and not e.get("is_constructing", False):
                # Normalize building type for JSON lookup
                json_name = simplified_to_json.get(btype, btype)
                bdata = building_data.get(json_name)
                if bdata:
                    supply_cap += bdata.get("manPlus", 0)
                else:
                    # Fallback for simplified types not in JSON
                    fallback_cap = {"base": 10, "barracks": 0, "factory": 0,
                                    "starport": 0, "supply_depot": 8, "refinery": 0}
                    supply_cap += fallback_cap.get(btype, 0)

            # Supply cap from Overlord (Zerg supply unit)
            if etype == "unit" and e.get("unit_type", "") == "Overlord":
                supply_cap += 8

            # Supply used from units
            if etype in ("worker", "soldier", "scout", "unit"):
                utype = e.get("unit_type", e.get("entity_type", ""))
                # Try JSON lookup first
                json_unit = simplified_to_json.get(utype, utype)
                # Also try direct mapping
                unit_map = {"worker": "SCV", "soldier": "Marine", "scout": "Firebat",
                            "SCV": "SCV", "Marine": "Marine", "Drone": "Drone", "Probe": "Probe",
                            "Zealot": "Zealot", "Zergling": "Zergling"}
                json_lookup = unit_map.get(utype, json_unit)
                udata = unit_data.get(json_lookup)
                if udata and "cost" in udata:
                    supply_used += udata["cost"].get("man", 1)
                else:
                    # Default supply cost based on simplified type
                    supply_map = {"worker": 1, "SCV": 1, "Drone": 1, "Probe": 1,
                                  "soldier": 2, "Marine": 1, "Zealot": 2, "Zergling": 1,
                                  "scout": 1, "Firebat": 1, "Ghost": 1, "Medic": 1,
                                  "Vulture": 2, "Tank": 2, "Goliath": 2,
                                  "Hydralisk": 1, "Dragoon": 2, "DarkTemplar": 2}
                    supply_used += supply_map.get(utype, 1)

        res[f"p{pid}_supply_used"] = supply_used
        res[f"p{pid}_supply_cap"] = supply_cap

    return res


# ─── Zerg Larva Spawning ────────────────────────────────────

def process_larva_spawn(
    entities: dict[str, Any],
    tick: int,
) -> dict[str, Any]:
    """Zerg: Hatcheries/Lairs/Hives spawn larva every LARVA_SPAWN_INTERVAL ticks (up to LARVA_MAX).

    Returns updated entities dict.
    """
    hatchery_types = {"Hatchery", "Lair", "Hive", "base"}
    result = dict(entities)

    for eid, e in list(result.items()):
        if e.get("entity_type") != "building":
            continue
        bt = e.get("building_type", "")
        # Only treat "base" as hatchery for Zerg players
        if bt not in hatchery_types:
            continue
        if bt == "base":
            # Detect if this is a Zerg player (has Zerg buildings or is configured as Zerg)
            owner = e.get("owner", 0)
            is_zerg = False
            for eid2, e2 in result.items():
                if e2.get("owner") == owner and e2.get("entity_type") == "building":
                    bt2 = e2.get("building_type", "")
                    if bt2 in {"SpawningPool", "HydraliskDen", "EvolutionChamber",
                               "CreepColony", "SunkenColony", "SporeColony", "Extractor"}:
                        is_zerg = True
                        break
            if not is_zerg:
                continue
        if e.get("is_constructing", False):
            continue
        if e.get("health", 0) <= 0:
            continue

        # Count existing larva for this hatchery
        hatchery_id = eid
        larva_count = 0
        for lid, le in result.items():
            if le.get("entity_type") == "unit" and le.get("unit_type", "") == "Larva":
                if le.get("spawned_from", "") == hatchery_id:
                    larva_count += 1

        # Check spawn timer
        last_spawn = e.get("last_larva_spawn_tick", 0)
        if tick - last_spawn >= LARVA_SPAWN_INTERVAL and larva_count < LARVA_MAX:
            # Spawn a new larva near the hatchery
            larva_id = f"larva_{tick}_{hatchery_id}"
            offset_x = 1.0 + (tick % 3) * 0.5  # slight offset to avoid stacking
            offset_y = -1.0 + ((tick // 3) % 3) * 0.5
            result[larva_id] = {
                "id": larva_id,
                "owner": e["owner"],
                "entity_type": "unit",
                "unit_type": "Larva",
                "pos_x": e["pos_x"] + offset_x,
                "pos_y": e["pos_y"] + offset_y,
                "health": 25,
                "max_health": 25,
                "speed": 0,
                "attack": 0,
                "attack_range": 0,
                "is_idle": True,
                "carry_amount": 0,
                "carry_capacity": 0,
                "target_x": None,
                "target_y": None,
                "returning_to_base": False,
                "attack_target_id": "",
                "deposit_pending": False,
                "spawned_from": hatchery_id,
                "morph_target": "",  # what it's morphing into
                "morph_timer": 0,
            }
            # Update hatchery's last spawn tick
            result[eid] = {**e, "last_larva_spawn_tick": tick}

    return result


# ─── Protoss Shield Regeneration ─────────────────────────────

def process_shield_regen(
    entities: dict[str, Any],
    tick: int,
) -> dict[str, Any]:
    """Protoss: Shields regenerate over time when not recently hit.

    Returns updated entities dict.
    """
    result = dict(entities)

    for eid, e in list(result.items()):
        if e.get("owner", 0) == 0:
            continue
        # Check race — Protoss units/buildings have shields
        if "shield" not in e and "sp" not in e:
            continue

        max_shield = e.get("max_shield", e.get("sp", 0))
        if max_shield <= 0:
            continue

        current_shield = e.get("shield", e.get("sp_current", max_shield))
        if current_shield < max_shield:
            last_hit_tick = e.get("last_hit_tick", 0)
            # Shields start regenerating 2 seconds (40 ticks at 20tps) after last hit
            if tick - last_hit_tick >= 40:
                new_shield = min(current_shield + SHIELD_REGEN_RATE, max_shield)
                result[eid] = {**e, "shield": new_shield}

    return result


# ─── Protoss Pylon Power ────────────────────────────────────

def check_pylon_power(
    entities: dict[str, Any],
    building_id: str,
) -> bool:
    """Check if a Protoss building is powered by a nearby Pylon.

    Returns True if:
      - The building is a Nexus or Pylon (always powered)
      - The building is within PYLON_POWER_RANGE of a friendly, completed Pylon
    """
    building = entities.get(building_id)
    if building is None:
        return False

    # Nexus and Pylons are always powered
    bt = building.get("building_type", "")
    if bt in ("Nexus", "Pylon", "Assimilator"):
        return True

    owner = building.get("owner", 0)
    px = building["pos_x"]
    py = building["pos_y"]

    return _is_pylon_powered(entities, owner, px, py)


# ─── Convenience: Full Economy Pipeline ─────────────────────

def process_economy(
    state: GameState,
    commands: list[dict],
    tick: int,
) -> GameState:
    """Full economy pipeline: gathering, larva spawning, shield regen, resource update.

    Returns a new GameState.
    """
    entities, resources = process_gathering(
        state.entities, state.resources, commands, tick
    )
    entities = process_larva_spawn(entities, tick)
    entities = process_shield_regen(entities, tick)
    resources = process_resources(
        GameState(tick=state.tick, entities=entities,
                  fog_of_war=state.fog_of_war, resources=resources,
                  is_terminal=state.is_terminal, winner=state.winner)
    )
    return GameState(
        tick=state.tick,
        entities=entities,
        fog_of_war=state.fog_of_war,
        resources=resources,
        is_terminal=state.is_terminal,
        winner=state.winner,
    )