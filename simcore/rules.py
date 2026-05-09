"""Rule engine: resolves game rules per tick — deterministic, no I/O, no randomness.

Resolution order per tick:
1. Parse and validate commands
2. Execute movement
3. Resolve combat
4. Process resource gathering
5. Handle construction/production
6. Update fog-of-war
7. Check win/loss conditions
"""
from __future__ import annotations

import math
from typing import Any

from simcore.state import GameState

# ─── Constants ───────────────────────────────────────────────

COMBAT_PRIORITY_RANGE = 6.0  # units within this range can fight each tick
GATHER_RATE = 5.0            # resources gathered per tick per worker
BUILD_PROGRESS_PER_TICK = 10 # % per tick for construction
PRODUCTION_TICKS = {
    "worker": 10,
    "soldier": 15,
    "scout": 12,
}


# ─── Command Validation ────────────────────────────────────

def validate_commands(state: GameState, commands: list[dict]) -> list[dict]:
    """Filter out invalid commands, return only valid ones.

    A command is invalid if:
    - The referenced entity doesn't exist
    - The entity doesn't belong to the command issuer
    - The action is impossible (e.g., attack out of range — soft fail, just skip)
    """
    valid: list[dict] = []
    entities = state.entities

    for cmd in commands:
        entity_id = (
            cmd.get("entity_id") or cmd.get("attacker_id")
            or cmd.get("builder_id") or cmd.get("worker_id")
            or cmd.get("unit_id")
        )
        if entity_id and entity_id in entities:
            entity = entities[entity_id]
            if entity.get("owner") == cmd.get("issuer"):
                valid.append(cmd)
    return valid


# ─── Movement ───────────────────────────────────────────────

def apply_movement(entities: dict[str, Any], commands: list[dict], tick: int) -> dict[str, Any]:
    """Move units toward their target positions.

    Units move at their speed per tick toward the target.
    If they reach the target, they stop (is_idle = True).
    """
    moved = dict(entities)

    for cmd in commands:
        if cmd.get("action") != "move":
            continue
        uid = cmd.get("unit_id", "")
        if uid not in moved:
            continue

        e = moved[uid]
        if e.get("entity_type") not in ("worker", "soldier", "scout"):
            continue

        speed = e.get("speed", 2.0)
        tx, ty = cmd.get("target_x", 0.0), cmd.get("target_y", 0.0)
        cx, cy = e["pos_x"], e["pos_y"]
        dx, dy = tx - cx, ty - cy
        dist = math.sqrt(dx * dx + dy * dy)

        if dist <= speed:
            # Arrived
            moved[uid] = {**e, "pos_x": tx, "pos_y": ty, "is_idle": True}
        else:
            # Move toward target
            moved[uid] = {**e,
                          "pos_x": cx + dx / dist * speed,
                          "pos_y": cy + dy / dist * speed,
                          "is_idle": False}
    return moved


# ─── Combat ─────────────────────────────────────────────────

def resolve_combat(entities: dict[str, Any], tick: int) -> dict[str, Any]:
    """Resolve all combat encounters within attack range.

    For each attack command, if attacker is in range of target, deal damage.
    Remove destroyed entities.
    """
    fought = dict(entities)
    to_remove: set[str] = set()

    # Collect attack commands from entity states (set by previous step)
    # Actually, attacks are handled inline from commands, but we also
    # auto-attack nearest enemy if idle and in range
    entity_list = list(fought.items())

    for eid, e in entity_list:
        if eid in to_remove:
            continue
        if e.get("health", 0) <= 0:
            to_remove.add(eid)
            continue

        # Auto-attack: if unit is idle and enemy in range
        if (e.get("is_idle") and e.get("attack", 0) > 0
                and e.get("entity_type") in ("worker", "soldier", "scout")):
            best_target = None
            best_dist = float("inf")
            for tid, t in entity_list:
                if tid == eid or tid in to_remove:
                    continue
                if t.get("owner") == e.get("owner"):
                    continue
                if t.get("health", 0) <= 0:
                    continue
                dx = e["pos_x"] - t["pos_x"]
                dy = e["pos_y"] - t["pos_y"]
                d = math.sqrt(dx*dx + dy*dy)
                if d < best_dist and d <= e.get("attack_range", 1.0):
                    best_dist = d
                    best_target = tid

            if best_target and best_target in fought:
                target = fought[best_target]
                new_health = target["health"] - e["attack"]
                fought[best_target] = {**target, "health": new_health}
                if new_health <= 0:
                    to_remove.add(best_target)

    for eid in to_remove:
        fought.pop(eid, None)

    return fought


# ─── Economy ────────────────────────────────────────────────

def process_gathering(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process resource gathering commands.

    Workers at a resource node gather GATHER_RATE per tick.
    When carry_amount reaches carry_capacity, they auto-return to base.
    """
    gathered = dict(entities)
    res = dict(resources)
    to_remove: set[str] = set()

    for cmd in commands:
        if cmd.get("action") != "gather":
            continue
        wid = cmd.get("worker_id", "")
        if wid not in gathered:
            continue
        worker = gathered[wid]
        if worker.get("entity_type") != "worker":
            continue

        rid = cmd.get("resource_id", "")
        if rid not in gathered:
            continue
        node = gathered[rid]
        if node.get("entity_type") != "resource":
            continue

        # Check proximity (must be within 1.5 tiles)
        dx = worker["pos_x"] - node["pos_x"]
        dy = worker["pos_y"] - node["pos_y"]
        if math.sqrt(dx*dx + dy*dy) > 1.5:
            continue

        # Gather
        amount = min(GATHER_RATE, node.get("resource_amount", 0))
        carry = worker.get("carry_amount", 0) + amount
        cap = worker.get("carry_capacity", 10.0)

        if carry >= cap:
            # Return to base — add to player resources
            delivered = cap - worker.get("carry_amount", 0)
            rtype = node.get("resource_type", "mineral")
            player_key = f"p{worker['owner']}_{rtype}"
            res[player_key] = res.get(player_key, 0) + int(delivered)
            gathered[wid] = {**worker, "carry_amount": 0, "is_idle": True}
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
    """Process build and train commands."""
    built = dict(entities)
    res = dict(resources)

    for cmd in commands:
        if cmd.get("action") == "build":
            bid = cmd.get("builder_id", "")
            if bid not in built:
                continue
            builder = built[bid]
            if builder.get("entity_type") != "worker":
                continue

            btype = cmd.get("building_type", "barracks")
            # Deduct resources (simplified cost model)
            cost_mineral = 100 if btype == "barracks" else 50
            pkey = f"p{builder['owner']}_mineral"
            if res.get(pkey, 0) >= cost_mineral:
                res[pkey] -= cost_mineral
                # Create building at target position
                new_id = f"{btype}_{tick}"
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
                    "production_queue": [],
                }
                built[bid] = {**builder, "is_idle": True}

        elif cmd.get("action") == "train":
            building_id = cmd.get("building_id", "")
            if building_id not in built:
                continue
            building = built[building_id]
            if building.get("entity_type") != "building":
                continue
            utype = cmd.get("unit_type", "worker")
            cost_map = {"worker": 50, "soldier": 100, "scout": 75}
            cost = cost_map.get(utype, 50)
            pkey = f"p{building['owner']}_mineral"
            if res.get(pkey, 0) >= cost:
                res[pkey] -= cost
                queue = list(building.get("production_queue", []))
                queue.append(utype)
                built[building_id] = {**building, "production_queue": queue}

    # Advance production queues
    new_entities: dict[str, Any] = {}
    for eid, e in built.items():
        if e.get("entity_type") != "building":
            continue
        queue = list(e.get("production_queue", []))
        if not queue:
            continue

        # First item in queue progresses
        # Spawn unit after PRODUCTION_TICKS (simplified: just spawn next tick)
        if len(queue) > 0:
            utype = queue.pop(0)
            uid = f"{utype}_{tick}_{eid}"
            new_entities[uid] = {
                "id": uid,
                "owner": e["owner"],
                "entity_type": utype,
                "pos_x": e["pos_x"] + 1.0,
                "pos_y": e["pos_y"] + 1.0,
                "health": 50 if utype == "worker" else 80,
                "max_health": 50 if utype == "worker" else 80,
                "speed": 2.0 if utype == "worker" else 3.0,
                "attack": 5 if utype == "worker" else 15,
                "attack_range": 1.0,
                "is_idle": True,
                "carry_amount": 0,
                "carry_capacity": 10.0,
            }
            built[eid] = {**e, "production_queue": queue}

    built.update(new_entities)
    return built, res


# ─── Fog of War ─────────────────────────────────────────────

def update_fog_of_war(entities: dict[str, Any], fog: dict[str, Any], tick: int) -> dict[str, Any]:
    """Update fog-of-war grid per player based on unit visibility.

    Simplified: each unit reveals a radius of 5 tiles around it.
    """
    # TODO: implement proper fog-of-war grid updates
    return fog


# ─── Terminal State Check ───────────────────────────────────

def check_terminal(entities: dict[str, Any], tick: int, max_ticks: int) -> tuple[bool, int, str]:
    """Check if game has ended.

    Returns (is_terminal, winner, reason).
    Winner: 0=draw, 1=player1, 2=player2
    """
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
    """Applies game rules to advance state by one tick.

    Pure function of (state, commands, tick) → new_state.
    No randomness (deterministic), no I/O, no side effects.
    """

    def apply(self, state: GameState, commands: list[dict], tick: int) -> GameState:
        """Full rule resolution pipeline for one tick."""
        # 1. Validate commands
        valid = validate_commands(state, commands)

        # 2. Movement
        entities = apply_movement(state.entities, valid, tick)

        # 3. Combat
        entities = resolve_combat(entities, tick)

        # 4. Gathering
        entities, resources = process_gathering(entities, state.resources, valid, tick)

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
