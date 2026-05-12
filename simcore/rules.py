"""Rule engine: resolves game rules per tick — deterministic, no I/O, no randomness.

Resolution order per tick:
1. Parse and validate commands
2. Execute movement (including worker return-to-base and attack chase)
3. Resolve combat (explicit attack + auto-attack with priority scoring)
4. Process resource gathering (and deposit when worker reaches base)
5. Handle construction/production (with real timers)
6. Update fog-of-war
7. Check win/loss conditions
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from simcore.state import GameState

# ─── Constants ───────────────────────────────────────────────

COMBAT_PRIORITY_RANGE = 6.0
GATHER_RATE = 5.0
BUILD_PROGRESS_PER_TICK = 10  # % per tick for construction
PRODUCTION_TICKS = {
    "worker": 10,
    "soldier": 15,
    "scout": 12,
}
WORKER_RETURN_SPEED = 3.0  # slightly faster when carrying

# Auto-attack priority weights (lower score = higher priority)
PRIORITY_WEIGHT_HEALTH = 0.6   # prefer low-health targets
PRIORITY_WEIGHT_DIST = 0.3     # prefer nearby targets
PRIORITY_WEIGHT_THREAT = 0.1   # prefer high-damage targets

# ─── Damage Matrix ──────────────────────────────────────────

_DAMAGE_MATRIX_DATA: dict | None = None

# Weapon type to attack type index mapping (from data/combat.json attackTypes)
_WEAPON_TYPE_MAP: dict[str, int] = {
    "normal": 2,      # WAVE → 100% to all
    "explosive": 1,   # BURST → 50% small, 75% medium, 100% large
    "concussive": 0,  # NORMAL → 100% small, 50% medium, 25% large
    "spells": 2,      # WAVE → 100% to all (spells ignore armor type)
    "splash": 2,      # WAVE → 100% to all
    "melee": 2,       # WAVE → 100% to all (melee does full damage)
}

# Armor type to unit type index mapping (from data/combat.json unitTypes)
_ARMOR_TYPE_MAP: dict[str, int] = {
    "light": 0,   # SMALL
    "medium": 1,  # MIDDLE
    "heavy": 2,   # BIG
}


def _load_damage_matrix() -> dict:
    """Load damage matrix from data/combat.json (cached)."""
    global _DAMAGE_MATRIX_DATA
    if _DAMAGE_MATRIX_DATA is None:
        path = Path(__file__).resolve().parent.parent / "data" / "combat.json"
        with open(path) as f:
            _DAMAGE_MATRIX_DATA = json.load(f)
    return _DAMAGE_MATRIX_DATA


def calculate_damage(
    base_damage: float,
    weapon_type: str,
    target_armor: int,
    target_armor_type: str,
) -> float:
    """Calculate final damage using the damage matrix.

    Formula: final = (base_damage × damageMatrix[attackType][unitType] - armor) × 0.01
    Minimum: 0.5 (from combat.json minDamage)

    Args:
        base_damage: Base damage value of the attack.
        weapon_type: One of "normal", "explosive", "concussive", "spells", "splash", "melee".
        target_armor: Target's armor value.
        target_armor_type: One of "light", "medium", "heavy".

    Returns:
        Final damage value (minimum 0.5).
    """
    data = _load_damage_matrix()
    matrix = data.get("damageMatrix", [[100, 50, 25], [50, 75, 100], [100, 100, 100]])
    min_damage = data.get("minDamage", 0.5)

    attack_idx = _WEAPON_TYPE_MAP.get(weapon_type, 2)  # default: normal (full damage)
    armor_idx = _ARMOR_TYPE_MAP.get(target_armor_type, 1)  # default: medium

    # Get multiplier percentage from matrix
    if 0 <= attack_idx < len(matrix) and 0 <= armor_idx < len(matrix[attack_idx]):
        multiplier_pct = matrix[attack_idx][armor_idx]
    else:
        multiplier_pct = 100

    # Apply formula: (base_damage × multiplier% / 100 - armor)
    raw_damage = base_damage * multiplier_pct / 100.0 - target_armor

    # Minimum damage
    return max(min_damage, raw_damage)


def get_armor_type(entity: dict[str, Any]) -> str:
    """Determine armor type for an entity based on its unit/building type.

    Default mapping follows StarCraft conventions:
      - light: workers, small units (Zergling, Marine, Ghost, etc.)
      - medium: mid-size units (Hydralisk, Vulture, Dragoon, etc.)
      - heavy: large units (Tank, Ultralisk, BattleCruiser, buildings, etc.)
    """
    etype = entity.get("entity_type", "")
    utype = entity.get("unit_type", "").lower() if entity.get("unit_type") else ""

    # Buildings are heavy
    if etype == "building":
        return "heavy"

    light_units = {"worker", "soldier", "scout", "zergling", "marine", "ghost",
                   "firebat", "medic", "scourge", "broodling", "larva",
                   "probe", "zealot", "darktemplar", "observer",
                   "scv", "drone"}
    medium_units = {"hydralisk", "vulture", "goliath", "wraith", "valkyrie",
                    "mutalisk", "queen", "defiler", "corsair", "dropship",
                    "shuttle", "lurker", "infestedterran", "overlord"}
    heavy_units = {"tank", "ultralisk", "battlecruiser", "carrier", "arbitr",
                   "archon", "darkarchon", "reaver", "guardian", "devourer",
                   "vessel", "behemoth"}

    if utype in light_units or etype in light_units:
        return "light"
    elif utype in medium_units:
        return "medium"
    elif utype in heavy_units:
        return "heavy"

    # Default: workers and small infantry are light, everything else medium
    if etype in ("worker", "scout"):
        return "light"

    return "medium"


# ─── Combat Kill Tracking ───────────────────────────────────

class KillFeed:
    """Lightweight combat statistics tracked per game."""
    def __init__(self) -> None:
        self.kills: dict[int, int] = {1: 0, 2: 0}
        self.deaths: dict[int, int] = {1: 0, 2: 0}
        self.damage_dealt: dict[int, float] = {1: 0.0, 2: 0.0}

    def record_kill(self, killer_owner: int, victim_owner: int) -> None:
        self.kills[killer_owner] = self.kills.get(killer_owner, 0) + 1
        self.deaths[victim_owner] = self.deaths.get(victim_owner, 0) + 1

    def record_damage(self, dealer_owner: int, amount: float) -> None:
        self.damage_dealt[dealer_owner] = self.damage_dealt.get(dealer_owner, 0.0) + amount

    def to_dict(self) -> dict:
        return {
            "kills": dict(self.kills),
            "deaths": dict(self.deaths),
            "damage_dealt": dict(self.damage_dealt),
        }


# ─── Command Validation ────────────────────────────────────

def validate_commands(state: GameState, commands: list[dict]) -> list[dict]:
    """Filter out invalid commands, return only valid ones."""
    valid: list[dict] = []
    entities = state.entities

    for cmd in commands:
        entity_id = (
            cmd.get("entity_id") or cmd.get("attacker_id")
            or cmd.get("builder_id") or cmd.get("worker_id")
            or cmd.get("unit_id") or cmd.get("building_id")
        )
        if entity_id and entity_id in entities:
            entity = entities[entity_id]
            if entity.get("owner") == cmd.get("issuer"):
                valid.append(cmd)
    return valid


# ─── Movement ───────────────────────────────────────────────

def apply_movement(entities: dict[str, Any], commands: list[dict], tick: int) -> dict[str, Any]:
    """Move units toward their target positions.

    Three sources of movement:
    - Explicit 'move' commands
    - Workers returning to base (returning_to_base = True)
    - Units chasing attack target (attack_target_id set, not yet in range)
    """
    moved = dict(entities)

    # 1. Explicit move commands — clear attack/gather state
    for cmd in commands:
        if cmd.get("action") != "move":
            continue
        uid = cmd.get("unit_id", "")
        if uid not in moved:
            continue
        e = moved[uid]
        if e.get("entity_type") not in ("worker", "soldier", "scout"):
            continue
        moved[uid] = {**e,
                      "target_x": cmd.get("target_x", e["pos_x"]),
                      "target_y": cmd.get("target_y", e["pos_y"]),
                      "is_idle": False,
                      "returning_to_base": False,
                      "attack_target_id": ""}

    # 2. Workers returning to base — target = nearest friendly base
    for uid, e in list(moved.items()):
        if e.get("entity_type") != "worker" or not e.get("returning_to_base"):
            continue
        base = _find_nearest_base(moved, e.get("owner", 0), e["pos_x"], e["pos_y"])
        if base is None:
            moved[uid] = {**e, "returning_to_base": False, "is_idle": True}
            continue
        moved[uid] = {**e, "target_x": base["pos_x"], "target_y": base["pos_y"]}

    # 3. Units with attack_target_id — chase the target (update position each tick)
    for uid, e in list(moved.items()):
        target_id = e.get("attack_target_id", "")
        if not target_id:
            continue
        if target_id not in moved:
            # Target died or was removed — clear attack state, become idle
            moved[uid] = {**e, "attack_target_id": "", "is_idle": True,
                          "target_x": None, "target_y": None}
            continue
        target = moved[target_id]
        moved[uid] = {**e, "target_x": target["pos_x"], "target_y": target["pos_y"]}

    # 4. Execute movement for all units that have a target
    for uid, e in list(moved.items()):
        if e.get("entity_type") not in ("worker", "soldier", "scout"):
            continue
        # Skip units still following A* paths — move_entities handles them
        if e.get("path"):
            continue
        tx = e.get("target_x")
        ty = e.get("target_y")
        if tx is None or ty is None:
            continue

        cx, cy = e["pos_x"], e["pos_y"]
        dx, dy = tx - cx, ty - cy
        dist = math.sqrt(dx * dx + dy * dy)

        speed = WORKER_RETURN_SPEED if e.get("returning_to_base") else e.get("speed", 2.0)

        if dist <= speed:
            # Arrived at target position
            updates: dict[str, Any] = {"pos_x": tx, "pos_y": ty}

            # Worker arrived at base → mark deposit
            if e.get("returning_to_base"):
                base = _find_nearest_base(moved, e.get("owner", 0), tx, ty)
                if base and math.hypot(tx - base["pos_x"], ty - base["pos_y"]) < 2.0:
                    updates["deposit_pending"] = True
                    updates["returning_to_base"] = False
                    updates["target_x"] = None
                    updates["target_y"] = None
                    updates["is_idle"] = True
                else:
                    # Near target but not at base — idle
                    updates["is_idle"] = True
                    updates["target_x"] = None
                    updates["target_y"] = None

            # Attacker arrived at attack target position
            elif e.get("attack_target_id"):
                target_id = e["attack_target_id"]
                if target_id in moved:
                    target = moved[target_id]
                    d_to_target = math.hypot(tx - target["pos_x"], ty - target["pos_y"])
                    if d_to_target <= e.get("attack_range", 6.0):
                        # In range — combat will resolve, stay here
                        updates["is_idle"] = False
                    else:
                        # Target moved away — keep chasing (target_x updated in step 3 next tick)
                        updates["is_idle"] = False
                else:
                    # Target gone — clear attack
                    updates["attack_target_id"] = ""
                    updates["is_idle"] = True
                    updates["target_x"] = None
                    updates["target_y"] = None

            else:
                # Normal move arrival — but not idle if gathering
                if e.get("gather_target_id", ""):
                    updates["is_idle"] = False
                else:
                    updates["is_idle"] = True
                    # Keep target_x/y intact so AI/auto-attack can still reference them

            moved[uid] = {**e, **updates}
        else:
            # Move toward target
            new_x = cx + dx / dist * speed
            new_y = cy + dy / dist * speed
            atk_range = e.get("attack_range", 6.0)
            # When reaching target position (or overshooting), snap to target
            # and become idle so auto-attack can trigger
            if dist <= speed:
                is_arrived = True
                moved[uid] = {**e,
                              "pos_x": tx,
                              "pos_y": ty,
                              "is_idle": is_arrived}
            else:
                # Check if new position is within attack range
                remaining = math.sqrt((tx - new_x) ** 2 + (ty - new_y) ** 2)
                is_arrived = remaining <= atk_range and not e.get("gather_target_id", "")
                moved[uid] = {**e,
                              "pos_x": new_x,
                              "pos_y": new_y,
                              "is_idle": is_arrived}

    return moved


# ─── Combat ─────────────────────────────────────────────────

def resolve_combat(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
    kill_feed: KillFeed | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Resolve all combat: explicit attack commands + auto-attack with priority.

    Priority scoring for auto-attack:
      score = health_frac * W_HEALTH + dist_frac * W_DIST + threat * W_THREAT
    Lower score = higher priority.

    Returns (updated_entities, updated_resources).
    """
    fought = dict(entities)
    res = dict(resources)
    to_remove: set[str] = set()
    if kill_feed is None:
        kill_feed = KillFeed()

    # 1. Process explicit attack commands → set attack_target_id on units
    for cmd in commands:
        if cmd.get("action") != "attack":
            continue
        attacker_id = cmd.get("attacker_id", "")
        target_id = cmd.get("target_id", "")
        if attacker_id not in fought or target_id not in fought:
            continue
        attacker = fought[attacker_id]
        if attacker.get("entity_type") not in ("worker", "soldier", "scout"):
            continue
        fought[attacker_id] = {**attacker, "attack_target_id": target_id, "is_idle": False}

    # 2. For each unit with attack_target_id, if in range → deal damage
    for uid, e in list(fought.items()):
        tid = e.get("attack_target_id", "")
        if not tid or tid not in fought:
            continue
        target = fought[tid]
        # Don't attack buildings under construction
        if target.get("is_constructing"):
            continue
        dx = e["pos_x"] - target["pos_x"]
        dy = e["pos_y"] - target["pos_y"]
        d = math.sqrt(dx * dx + dy * dy)
        if d <= e.get("attack_range", 6.0):
            base_dmg = e.get("attack", 0)
            weapon_type = e.get("weapon_type", "normal")
            target_armor = target.get("armor", 0)
            target_armor_type = get_armor_type(target)
            dmg = calculate_damage(base_dmg, weapon_type, target_armor, target_armor_type)
            new_health = target["health"] - dmg
            fought[tid] = {**target, "health": new_health}
            kill_feed.record_damage(e.get("owner", 0), dmg)
            if new_health <= 0:
                to_remove.add(tid)
                kill_feed.record_kill(e.get("owner", 0), target.get("owner", 0))
                # Clear any units targeting the dead entity
                for uid2, e2 in list(fought.items()):
                    if e2.get("attack_target_id") == tid:
                        fought[uid2] = {**e2, "attack_target_id": "", "is_idle": True}

    # 3. Auto-attack: idle units in range of enemy → pick best target by priority
    entity_list = list(fought.items())
    for eid, e in entity_list:
        if eid in to_remove:
            continue
        # Skip resources, dead entities, and buildings under construction
        if e.get("entity_type") == "resource":
            continue
        if e.get("is_constructing"):
            continue
        if e.get("health", 0) <= 0:
            to_remove.add(eid)
            continue

        # Only auto-attack if idle and no explicit target
        if (e.get("is_idle") and e.get("attack", 0) > 0
                and not e.get("attack_target_id")
                and e.get("entity_type") in ("worker", "soldier", "scout")):
            best_target = None
            best_score = float("inf")
            attack_range = e.get("attack_range", 6.0)

            for tid, t in entity_list:
                if tid == eid or tid in to_remove:
                    continue
                # Skip friendly, neutral (owner=0), and resources
                t_owner = t.get("owner", 0)
                if t_owner == e.get("owner") or t_owner == 0:
                    continue
                if t.get("entity_type") == "resource":
                    continue
                if t.get("health", 0) <= 0:
                    continue

                d = math.hypot(e["pos_x"] - t["pos_x"], e["pos_y"] - t["pos_y"])
                if d > attack_range:
                    continue

                # Priority score: lower = more attractive target
                health_frac = t.get("health", 0) / max(t.get("max_health", 1), 1)
                dist_frac = d / max(attack_range, 0.1)
                threat = t.get("attack", 0) / 50.0  # normalize to 0..~1

                score = (health_frac * PRIORITY_WEIGHT_HEALTH
                         + dist_frac * PRIORITY_WEIGHT_DIST
                         - threat * PRIORITY_WEIGHT_THREAT)  # minus: prefer high threat

                if score < best_score:
                    best_score = score
                    best_target = tid

            if best_target and best_target in fought:
                target = fought[best_target]
                base_dmg = e.get("attack", 0)
                weapon_type = e.get("weapon_type", "normal")
                target_armor = target.get("armor", 0)
                target_armor_type = get_armor_type(target)
                dmg = calculate_damage(base_dmg, weapon_type, target_armor, target_armor_type)
                new_health = target["health"] - dmg
                fought[best_target] = {**target, "health": new_health}
                kill_feed.record_damage(e.get("owner", 0), dmg)
                if new_health <= 0:
                    to_remove.add(best_target)
                    kill_feed.record_kill(e.get("owner", 0), target.get("owner", 0))

    # 4. Deposit carried resources for dead workers
    for eid in to_remove:
        e = fought.get(eid)
        if e and e.get("entity_type") == "worker" and e.get("carry_amount", 0) > 0:
            pkey = f"p{e['owner']}_mineral"
            res[pkey] = res.get(pkey, 0) + int(e["carry_amount"])

    for eid in to_remove:
        fought.pop(eid, None)

    return fought, res


# ─── Economy ────────────────────────────────────────────────

def process_gathering(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process resource gathering commands.

    Workers at a resource node gather GATHER_RATE per tick.
    When carry_amount reaches carry_capacity, they are flagged to return to base.
    Workers that arrived at base with deposit_pending=True deposit their cargo.
    """
    gathered = dict(entities)
    res = dict(resources)
    to_remove: set[str] = set()

    for uid, e in list(gathered.items()):
        # 1. Deposit pending (worker arrived at base)
        if e.get("deposit_pending"):
            carried = e.get("carry_amount", 0)
            if carried > 0:
                pkey = f"p{e['owner']}_mineral"
                res[pkey] = res.get(pkey, 0) + int(carried)
            gathered[uid] = {**e, "carry_amount": 0, "deposit_pending": False, "is_idle": True}
            continue

    # 2. Process active gathering: workers near resources auto-gather until full
    for uid, e in list(gathered.items()):
        if e.get("entity_type") != "worker":
            continue
        if e.get("returning_to_base") or e.get("deposit_pending"):
            continue
        if e.get("carry_amount", 0) >= e.get("carry_capacity", 10.0):
            # Full — start returning
            gathered[uid] = {**e, "is_idle": False, "returning_to_base": True}
            continue
        # If already carrying something but not full, auto-continue
        if e.get("carry_amount", 0) > 0 and not e.get("is_idle", True):
            for rid, node in gathered.items():
                if node.get("entity_type") != "resource" or node.get("resource_amount", 0) <= 0:
                    continue
                dx = e["pos_x"] - node["pos_x"]
                dy = e["pos_y"] - node["pos_y"]
                if math.sqrt(dx*dx + dy*dy) <= 1.5:
                    amount = min(GATHER_RATE, node.get("resource_amount", 0))
                    carry = e.get("carry_amount", 0) + amount
                    cap = e.get("carry_capacity", 10.0)
                    if carry >= cap:
                        gathered[uid] = {**e, "carry_amount": cap, "is_idle": False, "returning_to_base": True}
                    else:
                        gathered[uid] = {**e, "carry_amount": carry, "is_idle": False}
                    new_amount = node.get("resource_amount", 0) - amount
                    if new_amount <= 0:
                        to_remove.add(rid)
                    else:
                        gathered[rid] = {**node, "resource_amount": new_amount}
                    break

    # 3. Process new gather commands (assign idle workers to resources)
    for cmd in commands:
        if cmd.get("action") != "gather":
            continue
        wid = cmd.get("worker_id", "")
        if wid not in gathered:
            continue
        worker = gathered[wid]
        if worker.get("entity_type") != "worker":
            continue
        if worker.get("returning_to_base"):
            continue
        # Only assign if worker is idle (not already gathering)
        if not worker.get("is_idle", True):
            continue

        rid = cmd.get("resource_id", "")
        if rid not in gathered:
            continue
        node = gathered[rid]
        if node.get("entity_type") != "resource":
            continue

        # Check proximity
        dx = worker["pos_x"] - node["pos_x"]
        dy = worker["pos_y"] - node["pos_y"]
        if math.sqrt(dx * dx + dy * dy) > 1.5:
            # Not at node yet — set target to move there
            gathered[wid] = {**worker,
                             "target_x": node["pos_x"],
                             "target_y": node["pos_y"],
                             "is_idle": False}
            continue

        # At node — gather
        amount = min(GATHER_RATE, node.get("resource_amount", 0))
        carry = worker.get("carry_amount", 0) + amount
        cap = worker.get("carry_capacity", 10.0)

        if carry >= cap:
            gathered[wid] = {**worker, "carry_amount": cap, "is_idle": False,
                             "returning_to_base": True}
        else:
            gathered[wid] = {**worker, "carry_amount": carry, "is_idle": False}

        # Deplete node
        new_amount = node.get("resource_amount", 0) - amount
        if new_amount <= 0:
            to_remove.add(rid)
        else:
            gathered[rid] = {**node, "resource_amount": new_amount}

    for eid in to_remove:
        gathered.pop(eid, None)

    return gathered, res


# ─── Construction & Production ──────────────────────────────

def process_construction(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process build and train commands with real timers."""
    built = dict(entities)
    res = dict(resources)

    # 1. Process build commands
    for cmd in commands:
        if cmd.get("action") == "build":
            bid = cmd.get("builder_id", "")
            if bid not in built:
                continue
            builder = built[bid]
            if builder.get("entity_type") != "worker":
                continue

            btype = cmd.get("building_type", "barracks")
            cost_mineral = 100 if btype == "barracks" else 50
            pkey = f"p{builder['owner']}_mineral"
            if res.get(pkey, 0) >= cost_mineral:
                res[pkey] -= cost_mineral
                new_id = f"{btype}_{tick}_{bid}"
                built[new_id] = {
                    "id": new_id,
                    "owner": builder["owner"],
                    "entity_type": "building",
                    "building_type": btype,
                    "pos_x": cmd.get("pos_x", builder["pos_x"]),
                    "pos_y": cmd.get("pos_y", builder["pos_y"]),
                    "health": 100,
                    "max_health": 100,
                    "is_constructing": True,
                    "build_progress": 0,
                    "production_queue": [],
                    "production_timers": [],
                }
                built[bid] = {**builder, "is_idle": False,
                              "target_x": cmd.get("pos_x", builder["pos_x"]),
                              "target_y": cmd.get("pos_y", builder["pos_y"])}

        elif cmd.get("action") == "train":
            building_id = cmd.get("building_id", "")
            if building_id not in built:
                continue
            building = built[building_id]
            if building.get("entity_type") != "building":
                continue
            if building.get("is_constructing"):
                continue
            utype = cmd.get("unit_type", "worker")
            cost_map = {"worker": 50, "soldier": 100, "scout": 75}
            cost = cost_map.get(utype, 50)
            pkey = f"p{building['owner']}_mineral"
            if res.get(pkey, 0) >= cost:
                res[pkey] -= cost
                queue = list(building.get("production_queue", []))
                timers = list(building.get("production_timers", []))
                queue.append(utype)
                timers.append(PRODUCTION_TICKS.get(utype, 10))
                built[building_id] = {**building, "production_queue": queue, "production_timers": timers}

    # 2. Advance construction progress
    for eid, e in list(built.items()):
        if e.get("entity_type") != "building" or not e.get("is_constructing"):
            continue
        progress = e.get("build_progress", 0) + BUILD_PROGRESS_PER_TICK
        if progress >= 100:
            built[eid] = {**e, "build_progress": 100, "is_constructing": False}
        else:
            built[eid] = {**e, "build_progress": progress}

    # 3. Advance production timers and spawn units
    new_entities: dict[str, Any] = {}
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
            stats = _unit_stats(utype, e["owner"], e["pos_x"] + 1.0, e["pos_y"] + 1.0)
            new_entities[uid] = stats
            built[eid] = {**e, "production_queue": queue, "production_timers": timers}
        else:
            built[eid] = {**e, "production_timers": timers}

    built.update(new_entities)
    return built, res


def _unit_stats(utype: str, owner: int, px: float, py: float) -> dict:
    """Return entity dict for a newly spawned unit."""
    stats_map = {
        "worker":  {"health": 50,  "max_health": 50,  "speed": 2.5, "attack": 5,  "attack_range": 1.5,  "carry_capacity": 10.0},
        "soldier": {"health": 80,  "max_health": 80,  "speed": 3.0, "attack": 15, "attack_range": 6.0,  "carry_capacity": 0},
        "scout":   {"health": 40,  "max_health": 40,  "speed": 4.0, "attack": 8,  "attack_range": 6.0,  "carry_capacity": 0},
    }
    s = stats_map.get(utype, stats_map["worker"])
    return {
        "id": f"{utype}_{owner}_{px:.0f}",
        "owner": owner,
        "entity_type": utype,
        "pos_x": px,
        "pos_y": py,
        "health": s["health"],
        "max_health": s["max_health"],
        "speed": s["speed"],
        "attack": s["attack"],
        "attack_range": s["attack_range"],
        "is_idle": True,
        "carry_amount": 0,
        "carry_capacity": s["carry_capacity"],
        "target_x": None,
        "target_y": None,
        "returning_to_base": False,
        "attack_target_id": "",
        "deposit_pending": False,
    }


# ─── Fog of War ─────────────────────────────────────────────

def update_fog_of_war(entities: dict[str, Any], fog: dict[str, Any], tick: int) -> dict[str, Any]:
    """Update per-player fog-of-war grids based on unit/building visibility.

    Fog states: 0=unexplored, 1=explored (last-known), 2=currently visible.
    Each tick: all '2' → '1' (expire visibility), then re-illuminate around
    each friendly unit/building.
    """
    fog_data = dict(fog)
    # Ensure per-player structure
    for pid in ("1", "2"):
        if pid not in fog_data:
            w, h = fog_data.get("width", 16), fog_data.get("height", 16)
            fog_data[pid] = {"tiles": [0] * w * h, "width": w, "height": h}

    vision_radius_base = 3  # fog-grid tiles
    for pid_str in ("1", "2"):
        pf = fog_data[pid_str]
        tiles = list(pf.get("tiles", []))
        w = pf.get("width", 16)
        h = pf.get("height", 16)
        if not tiles:
            continue
        # Expire: 2→1
        tiles = [1 if t == 2 else t for t in tiles]
        # Illuminate around each friendly unit/building
        player_id = int(pid_str)
        for eid, e in entities.items():
            if e.get("owner") != player_id:
                continue
            etype = e.get("entity_type", "")
            if etype not in ("worker", "soldier", "scout", "building"):
                continue
            if e.get("is_constructing"):
                continue
            vr = vision_radius_base + (1 if etype == "scout" else 0)
            if etype == "building":
                vr = vision_radius_base - 1  # buildings have slightly less vision
            fx = int(e["pos_x"] / 64 * w)
            fy = int(e["pos_y"] / 64 * h)
            for dy in range(-vr, vr + 1):
                for dx in range(-vr, vr + 1):
                    gx, gy = fx + dx, fy + dy
                    if (0 <= gx < w and 0 <= gy < h
                            and dx * dx + dy * dy <= vr * vr):
                        idx = gy * w + gx
                        if 0 <= idx < len(tiles):
                            tiles[idx] = 2
        fog_data[pid_str] = {**pf, "tiles": tiles}
    return fog_data


# ─── Terminal State Check ───────────────────────────────────

def check_terminal(entities: dict[str, Any], tick: int, max_ticks: int) -> tuple[bool, int, str]:
    """Check if game has ended."""
    bases_p1 = [
        e for e in entities.values()
        if e.get("owner") == 1
        and e.get("building_type") == "base"
        and e.get("health", 0) > 0
    ]
    bases_p2 = [
        e for e in entities.values()
        if e.get("owner") == 2
        and e.get("building_type") == "base"
        and e.get("health", 0) > 0
    ]

    if not bases_p1 and not bases_p2:
        return True, 0, "both_bases_destroyed"
    if not bases_p1:
        return True, 2, "p1_base_destroyed"
    if not bases_p2:
        return True, 1, "p2_base_destroyed"
    if tick >= max_ticks:
        return True, 0, "max_ticks_reached"
    return False, 0, ""


# ─── Main Rule Engine ──────────────────────────────────────

class RuleEngine:
    """Applies game rules to advance state by one tick."""

    def __init__(self) -> None:
        self.kill_feed = KillFeed()

    def apply(self, state: GameState, commands: list[dict], tick: int) -> GameState:
        """Full rule resolution pipeline for one tick."""
        # 1. Validate commands
        valid = validate_commands(state, commands)

        # 2. Movement
        entities = apply_movement(state.entities, valid, tick)

        # 3. Combat (with kill tracking)
        entities, resources = resolve_combat(
            entities, state.resources, valid, tick, kill_feed=self.kill_feed,
        )

        # 4. Gathering
        entities, resources = process_gathering(entities, resources, valid, tick)

        # 5. Construction & production
        entities, resources = process_construction(entities, resources, valid, tick)

        # 6. Fog-of-war
        fog = update_fog_of_war(entities, state.fog_of_war, tick)

        # 7. Terminal check
        is_terminal, winner, reason = check_terminal(entities, tick, self.max_ticks)

        return GameState(
            tick=tick,
            entities=entities,
            fog_of_war=fog,
            resources=resources,
            is_terminal=is_terminal,
            winner=winner,
        )

    @property
    def max_ticks(self) -> int:
        return 10_000


# ─── Helpers ────────────────────────────────────────────────

def _find_nearest_base(entities: dict[str, Any], owner: int, px: float, py: float) -> dict | None:
    """Find the nearest friendly base for the given owner."""
    best = None
    best_dist = float("inf")
    for eid, e in entities.items():
        if e.get("owner") == owner and e.get("building_type") == "base" and e.get("health", 0) > 0:
            d = math.hypot(px - e["pos_x"], py - e["pos_y"])
            if d < best_dist:
                best_dist = d
                best = e
    return best