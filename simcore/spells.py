"""Spell system: process spell commands, apply effects, manage energy.

Spell types:
  - TARGETED: cast on a specific unit (Yamato Gun, Lockdown, Parasite)
  - SELF_BUFF: buffs the caster (Stim Pack, Defensive Matrix)
  - AREA: affects all units in radius (Psionic Storm, EMP, Plague, Ensnare)
  - SUMMON: creates units (Spawn Broodlings, Hallucination, Recall)
  - TRANSFORM: changes unit state (Siege Mode, Burrow, Cloak)

Energy regenerates at 0.75/tick for casters with energy.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from simcore.state import GameState

# ─── Constants ───────────────────────────────────────────────

ENERGY_REGEN_RATE = 0.75  # per tick

# ─── Data Loading ────────────────────────────────────────────

_SPELL_DATA: list[dict] | None = None


def _load_spell_data() -> list[dict]:
    global _SPELL_DATA
    if _SPELL_DATA is None:
        path = Path(__file__).resolve().parent.parent / "data" / "spells" / "spells.json"
        with open(path) as f:
            raw = json.load(f)
        _SPELL_DATA = raw.get("spells", [])
    return _SPELL_DATA


def get_spell_data(spell_name: str) -> dict | None:
    """Look up a spell by name from spells.json."""
    for s in _load_spell_data():
        if s.get("name", "").lower() == spell_name.lower():
            return s
    return None


# ─── Spell Classifications ──────────────────────────────────

SPELL_CATEGORIES: dict[str, str] = {
    # Zerg
    "burrow": "TRANSFORM",
    "unburrow": "TRANSFORM",
    "parasite": "TARGETED",
    "spawnbroodling": "SUMMON",
    "ensnare": "AREA",
    "consume": "SELF_BUFF",
    "darkswarm": "AREA",
    "plague": "AREA",
    # Terran
    "stimpack": "SELF_BUFF",
    "cloaking": "TRANSFORM",
    "personalcloaking": "TRANSFORM",
    "lockdown": "TARGETED",
    "healing": "TARGETED",
    "restoration": "TARGETED",
    "opticalflare": "TARGETED",
    "empshockwave": "AREA",
    "defensivematrix": "SELF_BUFF",
    "yamatogun": "TARGETED",
    "nuclearstrike": "AREA",
    "siegemode": "TRANSFORM",
    "tankmode": "TRANSFORM",
    "spidermines": "SELF_BUFF",
    # Protoss
    "psionicstorm": "AREA",
    "hallucination": "SUMMON",
    "recall": "SUMMON",
    "stasisfield": "AREA",
    "archonwarp": "SUMMON",
    "disruptionweb": "AREA",
}

# Spell effects configuration: cost, cooldown (ticks), duration (ticks), radius for AOE
SPELL_CONFIG: dict[str, dict] = {
    "stimpack":        {"cost_hp": 10, "cooldown": 0,  "duration": 75,  "radius": 0,   "damage": 0},
    "siegemode":       {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "tankmode":        {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "psionicstorm":    {"cost_mp": 75, "cooldown": 60, "duration": 50,  "radius": 5.0, "damage": 112},
    "empshockwave":    {"cost_mp": 100,"cooldown": 60, "duration": 0,   "radius": 5.0, "damage": 0,   "drain_energy": 100, "drain_shield": 100},
    "defensivematrix": {"cost_mp": 100,"cooldown": 0,  "duration": 90,  "radius": 0,   "damage": 0,   "shield": 250},
    "yamatogun":       {"cost_mp": 150,"cooldown": 90, "duration": 0,   "radius": 0,   "damage": 260},
    "lockdown":         {"cost_mp": 50, "cooldown": 0,  "duration": 120, "radius": 0,   "damage": 0},
    "plague":          {"cost_mp": 150,"cooldown": 0,  "duration": 150, "radius": 6.0, "damage": 300},
    "ensnare":         {"cost_mp": 75, "cooldown": 0,  "duration": 150, "radius": 5.0, "damage": 0},
    "darkswarm":       {"cost_mp": 100,"cooldown": 0,  "duration": 120, "radius": 6.0, "damage": 0},
    "spawnbroodling":  {"cost_mp": 150,"cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "parasite":        {"cost_mp": 75, "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "consume":         {"cost_hp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0,   "gain_mp": 50},
    "cloaking":        {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "personalcloaking":{"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "burrow":          {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "unburrow":        {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "healing":         {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0,   "heal": 200},
    "restoration":     {"cost_mp": 50, "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "opticalflare":    {"cost_mp": 75, "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "nuclearstrike":   {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 8.0, "damage": 0},
    "spidermines":     {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "hallucination":   {"cost_mp": 100,"cooldown": 0,  "duration": 300, "radius": 0,   "damage": 0},
    "recall":          {"cost_mp": 150,"cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "stasisfield":     {"cost_mp": 100,"cooldown": 0,  "duration": 120, "radius": 5.0, "damage": 0},
    "archonwarp":      {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "disruptionweb":   {"cost_mp": 125,"cooldown": 0,  "duration": 90,  "radius": 5.0, "damage": 0},
}

# ─── Energy Regeneration ─────────────────────────────────────

def regen_energy(entities: dict[str, Any], tick: int) -> dict[str, Any]:
    """Regenerate energy for all casters with energy stat."""
    result = dict(entities)
    for eid, e in list(result.items()):
        mp = e.get("mp", e.get("energy", 0))
        max_mp = e.get("max_mp", e.get("max_energy", 250))
        if max_mp > 0 and mp < max_mp:
            new_mp = min(max_mp, mp + ENERGY_REGEN_RATE)
            result[eid] = {**e, "mp": new_mp, "energy": new_mp}
    return result


# ─── Buff Duration Tracking ─────────────────────────────────

def process_buffs(entities: dict[str, Any], tick: int) -> dict[str, Any]:
    """Tick down active buffs; remove expired ones."""
    result = dict(entities)
    for eid, e in list(result.items()):
        buffs = list(e.get("buffs", []))
        if not buffs:
            continue
        new_buffs = []
        for b in buffs:
            remaining = b.get("remaining", 0) - 1
            if remaining > 0:
                new_buffs.append({**b, "remaining": remaining})
            else:
                # Buff expired — revert effects
                btype = b.get("type", "")
                if btype == "stimpack":
                    # Revert stim: restore normal attack speed
                    result[eid] = {**result.get(eid, e),
                                   "attack_cooldown_modifier": 1.0,
                                   "speed_modifier": 1.0}
                elif btype == "defensive_matrix":
                    result[eid] = {**result.get(eid, e),
                                   "bonus_shield": 0}
        if new_buffs != buffs:
            result[eid] = {**result.get(eid, e), "buffs": new_buffs}
    return result


# ─── Spell Processing ────────────────────────────────────────

def process_spells(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process spell commands for this tick.

    Returns (updated_entities, updated_resources).
    """
    result = dict(entities)
    res = dict(resources)
    new_entities: dict[str, Any] = {}
    to_remove: set[str] = set()

    # Regen energy first
    result = regen_energy(result, tick)

    # Process active buffs
    result = process_buffs(result, tick)

    for cmd in commands:
        if cmd.get("action") != "spell":
            continue

        spell_name = cmd.get("spell", "").lower()
        if spell_name not in SPELL_CATEGORIES:
            continue

        caster_id = cmd.get("caster_id", "") or cmd.get("entity_id", "") or cmd.get("unit_id", "")
        if caster_id not in result:
            continue

        caster = result[caster_id]
        owner = caster.get("owner", 0)
        config = SPELL_CONFIG.get(spell_name, {})

        # Check energy cost
        cost_mp = config.get("cost_mp", 0)
        current_mp = caster.get("mp", caster.get("energy", 0))
        if cost_mp > 0 and current_mp < cost_mp:
            continue

        # Check HP cost (Stim Pack)
        cost_hp = config.get("cost_hp", 0)
        current_hp = caster.get("health", 0)
        if cost_hp > 0 and current_hp <= cost_hp:
            continue

        # Check cooldown
        cooldown_remaining = caster.get(f"cooldown_{spell_name}", 0)
        if cooldown_remaining > 0:
            continue

        # Deduct cost
        updates: dict[str, Any] = {}
        if cost_mp > 0:
            new_mp = current_mp - cost_mp
            updates["mp"] = new_mp
            updates["energy"] = new_mp
        if cost_hp > 0:
            updates["health"] = current_hp - cost_hp

        # Apply spell cooldown
        cooldown = config.get("cooldown", 0)
        if cooldown > 0:
            updates[f"cooldown_{spell_name}"] = cooldown

        category = SPELL_CATEGORIES.get(spell_name, "")

        # ─── SELF_BUFF ─────────────────────────────────────
        if category == "SELF_BUFF":
            if spell_name == "stimpack":
                duration = config.get("duration", 75)
                buffs = list(caster.get("buffs", []))
                buffs.append({"type": "stimpack", "remaining": duration})
                updates["buffs"] = buffs
                updates["attack_cooldown_modifier"] = 0.5  # attacks 2x faster
                updates["speed_modifier"] = 1.5  # move faster
                result[caster_id] = {**caster, **updates}
            elif spell_name == "defensivematrix":
                duration = config.get("duration", 90)
                shield = config.get("shield", 250)
                buffs = list(caster.get("buffs", []))
                buffs.append({"type": "defensive_matrix", "remaining": duration})
                updates["buffs"] = buffs
                updates["bonus_shield"] = shield
                result[caster_id] = {**caster, **updates}
            elif spell_name == "consume":
                # Kill a friendly unit and gain energy
                target_id = cmd.get("target_id", "")
                if target_id and target_id in result:
                    t = result[target_id]
                    if t.get("owner") == owner:
                        to_remove.add(target_id)
                        gain = config.get("gain_mp", 50)
                        new_mp = min(
                            caster.get("max_mp", 250),
                            current_mp + gain
                        )
                        updates["mp"] = new_mp
                        updates["energy"] = new_mp
                        result[caster_id] = {**caster, **updates}
            elif spell_name == "spidermines":
                # Lay a mine near the caster
                mine_id = f"mine_{tick}_{caster_id}"
                new_entities[mine_id] = {
                    "id": mine_id,
                    "owner": owner,
                    "entity_type": "unit",
                    "unit_type": "SpiderMine",
                    "pos_x": caster["pos_x"] + 1.0,
                    "pos_y": caster["pos_y"],
                    "health": 20,
                    "max_health": 20,
                    "speed": 0,
                    "attack": 125,
                    "attack_range": 3.0,
                    "is_idle": True,
                    "carry_amount": 0,
                    "carry_capacity": 0,
                    "target_x": None,
                    "target_y": None,
                    "returning_to_base": False,
                    "attack_target_id": "",
                    "deposit_pending": False,
                }
                result[caster_id] = {**caster, **updates}
            else:
                result[caster_id] = {**caster, **updates}

        # ─── TRANSFORM ─────────────────────────────────────
        elif category == "TRANSFORM":
            if spell_name == "siegemode":
                updates["siege_mode"] = True
                updates["attack"] = 70
                updates["attack_range"] = 12.0
                updates["speed"] = 0
                result[caster_id] = {**caster, **updates}
            elif spell_name == "tankmode":
                updates["siege_mode"] = False
                updates["attack"] = 30
                updates["attack_range"] = 6.0
                updates["speed"] = 2.5
                result[caster_id] = {**caster, **updates}
            elif spell_name in ("cloaking", "personalcloaking"):
                updates["cloaked"] = True
                result[caster_id] = {**caster, **updates}
            elif spell_name == "burrow":
                updates["burrowed"] = True
                updates["is_idle"] = True
                result[caster_id] = {**caster, **updates}
            elif spell_name == "unburrow":
                updates["burrowed"] = False
                result[caster_id] = {**caster, **updates}

        # ─── TARGETED ─────────────────────────────────────
        elif category == "TARGETED":
            target_id = cmd.get("target_id", "")
            if target_id not in result:
                continue
            target = result[target_id]

            if spell_name == "yamatogun":
                new_health = target["health"] - config.get("damage", 260)
                result[target_id] = {**target, "health": new_health}
                if new_health <= 0:
                    to_remove.add(target_id)
                result[caster_id] = {**caster, **updates}
            elif spell_name == "lockdown":
                if target.get("entity_type") in ("unit",) and target.get("is_mechanical", True):
                    duration = config.get("duration", 120)
                    buffs = list(target.get("buffs", []))
                    buffs.append({"type": "lockdown", "remaining": duration})
                    result[target_id] = {**target, "buffs": buffs, "is_idle": True,
                                         "attack_target_id": "", "speed": 0}
                    result[caster_id] = {**caster, **updates}
            elif spell_name == "parasite":
                result[target_id] = {**target, "parasited_by": owner}
                result[caster_id] = {**caster, **updates}
            elif spell_name == "healing":
                heal = config.get("heal", 200)
                max_h = target.get("max_health", 9999)
                new_h = min(max_h, target["health"] + heal)
                result[target_id] = {**target, "health": new_h}
                result[caster_id] = {**caster, **updates}
            elif spell_name == "restoration":
                # Remove negative buffs
                buffs = [b for b in target.get("buffs", [])
                         if b.get("type") not in ("lockdown", "plague", "ensnare", "optical_flare")]
                result[target_id] = {**target, "buffs": buffs}
                result[caster_id] = {**caster, **updates}
            elif spell_name == "opticalflare":
                duration = 99999  # permanent until restored
                buffs = list(target.get("buffs", []))
                buffs.append({"type": "optical_flare", "remaining": duration})
                result[target_id] = {**target, "buffs": buffs, "sight": 1}
                result[caster_id] = {**caster, **updates}

        # ─── AREA ─────────────────────────────────────────
        elif category == "AREA":
            target_x = cmd.get("target_x", caster["pos_x"])
            target_y = cmd.get("target_y", caster["pos_y"])
            radius = config.get("radius", 5.0)

            if spell_name == "psionicstorm":
                damage = config.get("damage", 112)
                duration = config.get("duration", 50)
                damage_per_tick = damage / duration
                # Apply damage to all entities in radius
                for eid, e in list(result.items()):
                    if e.get("owner", 0) == 0:
                        continue
                    d = math.hypot(e["pos_x"] - target_x, e["pos_y"] - target_y)
                    if d <= radius:
                        new_health = e["health"] - damage_per_tick
                        result[eid] = {**e, "health": new_health}
                        if new_health <= 0:
                            to_remove.add(eid)
                # Create storm effect marker
                storm_id = f"storm_{tick}_{caster_id}"
                new_entities[storm_id] = {
                    "id": storm_id,
                    "owner": owner,
                    "entity_type": "effect",
                    "effect_type": "psionic_storm",
                    "pos_x": target_x,
                    "pos_y": target_y,
                    "tick_created": tick,
                    "duration": duration,
                    "damage_per_tick": damage_per_tick,
                    "radius": radius,
                }
                result[caster_id] = {**caster, **updates}

            elif spell_name == "empshockwave":
                for eid, e in list(result.items()):
                    d = math.hypot(e["pos_x"] - target_x, e["pos_y"] - target_y)
                    if d <= radius:
                        eu = {**e}
                        # Drain energy
                        drain_e = config.get("drain_energy", 100)
                        eu["mp"] = max(0, e.get("mp", 0) - drain_e)
                        eu["energy"] = eu["mp"]
                        # Drain shields
                        drain_s = config.get("drain_shield", 100)
                        eu["shield"] = max(0, e.get("shield", 0) - drain_s)
                        result[eid] = eu
                result[caster_id] = {**caster, **updates}

            elif spell_name == "plague":
                total_damage = config.get("damage", 300)
                duration = config.get("duration", 150)
                damage_per_tick = total_damage / duration
                for eid, e in list(result.items()):
                    if e.get("owner", 0) == owner:
                        continue
                    d = math.hypot(e["pos_x"] - target_x, e["pos_y"] - target_y)
                    if d <= radius:
                        # Plague doesn't kill — stops at 1 HP
                        new_health = max(1, e["health"] - damage_per_tick)
                        buffs = list(e.get("buffs", []))
                        buffs.append({"type": "plague", "remaining": duration})
                        result[eid] = {**e, "health": new_health, "buffs": buffs}
                result[caster_id] = {**caster, **updates}

            elif spell_name == "ensnare":
                duration = config.get("duration", 150)
                for eid, e in list(result.items()):
                    if e.get("owner", 0) == owner:
                        continue
                    d = math.hypot(e["pos_x"] - target_x, e["pos_y"] - target_y)
                    if d <= radius:
                        buffs = list(e.get("buffs", []))
                        buffs.append({"type": "ensnare", "remaining": duration})
                        result[eid] = {**e, "buffs": buffs, "speed_modifier": 0.5}
                # Reveal cloaked units in area
                result[caster_id] = {**caster, **updates}

            elif spell_name == "darkswarm":
                duration = config.get("duration", 120)
                ds_id = f"darkswarm_{tick}_{caster_id}"
                new_entities[ds_id] = {
                    "id": ds_id,
                    "owner": owner,
                    "entity_type": "effect",
                    "effect_type": "dark_swarm",
                    "pos_x": target_x,
                    "pos_y": target_y,
                    "tick_created": tick,
                    "duration": duration,
                    "radius": radius,
                }
                result[caster_id] = {**caster, **updates}

            elif spell_name == "stasisfield":
                duration = config.get("duration", 120)
                for eid, e in list(result.items()):
                    d = math.hypot(e["pos_x"] - target_x, e["pos_y"] - target_y)
                    if d <= radius:
                        buffs = list(e.get("buffs", []))
                        buffs.append({"type": "stasis", "remaining": duration})
                        result[eid] = {**e, "buffs": buffs, "stasis": True,
                                       "speed": 0, "attack": 0}
                result[caster_id] = {**caster, **updates}

            elif spell_name == "disruptionweb":
                duration = config.get("duration", 90)
                dw_id = f"disruptionweb_{tick}_{caster_id}"
                new_entities[dw_id] = {
                    "id": dw_id,
                    "owner": owner,
                    "entity_type": "effect",
                    "effect_type": "disruption_web",
                    "pos_x": target_x,
                    "pos_y": target_y,
                    "tick_created": tick,
                    "duration": duration,
                    "radius": radius,
                }
                result[caster_id] = {**caster, **updates}

            elif spell_name == "nuclearstrike":
                # Simplified: deals massive damage after a delay
                nuke_id = f"nuke_{tick}_{caster_id}"
                new_entities[nuke_id] = {
                    "id": nuke_id,
                    "owner": owner,
                    "entity_type": "effect",
                    "effect_type": "nuclear_strike",
                    "pos_x": target_x,
                    "pos_y": target_y,
                    "tick_created": tick,
                    "duration": 100,  # delay before impact
                    "radius": radius,
                    "damage": 800,
                }
                result[caster_id] = {**caster, **updates}

        # ─── SUMMON ──────────────────────────────────────
        elif category == "SUMMON":
            if spell_name == "spawnbroodling":
                target_id = cmd.get("target_id", "")
                if target_id in result and result[target_id].get("entity_type") != "building":
                    # Kill the target
                    to_remove.add(target_id)
                    # Spawn 2 Broodlings
                    for i in range(2):
                        bid = f"broodling_{tick}_{caster_id}_{i}"
                        offset_x = (i - 0.5) * 2.0
                        new_entities[bid] = {
                            "id": bid,
                            "owner": owner,
                            "entity_type": "unit",
                            "unit_type": "Broodling",
                            "pos_x": result[target_id]["pos_x"] + offset_x,
                            "pos_y": result[target_id]["pos_y"],
                            "health": 30,
                            "max_health": 30,
                            "speed": 5.0,
                            "attack": 4,
                            "attack_range": 1.0,
                            "is_idle": True,
                            "carry_amount": 0,
                            "carry_capacity": 0,
                            "target_x": None,
                            "target_y": None,
                            "returning_to_base": False,
                            "attack_target_id": "",
                            "deposit_pending": False,
                            "buffs": [],
                        }
                    result[caster_id] = {**caster, **updates}

            elif spell_name == "hallucination":
                target_id = cmd.get("target_id", "")
                if target_id in result:
                    target = result[target_id]
                    for i in range(2):
                        hid = f"hallucination_{tick}_{caster_id}_{i}"
                        new_entities[hid] = {
                            **target,
                            "id": hid,
                            "is_hallucination": True,
                            "health": target.get("health", 0) * 0.5,
                            "buffs": [],
                        }
                    result[caster_id] = {**caster, **updates}

            elif spell_name == "recall":
                # Teleport units near caster to target location
                target_x = cmd.get("target_x", caster["pos_x"])
                target_y = cmd.get("target_y", caster["pos_y"])
                for eid, e in list(result.items()):
                    if e.get("owner") == owner and eid != caster_id:
                        d = math.hypot(e["pos_x"] - caster["pos_x"],
                                       e["pos_y"] - caster["pos_y"])
                        if d <= 5.0:
                            result[eid] = {**e, "pos_x": target_x, "pos_y": target_y}
                result[caster_id] = {**caster, **updates}

            elif spell_name == "archonwarp":
                # Create an Archon at caster's location
                aid = f"archon_{tick}_{caster_id}"
                new_entities[aid] = {
                    "id": aid,
                    "owner": owner,
                    "entity_type": "unit",
                    "unit_type": "Archon",
                    "pos_x": caster["pos_x"],
                    "pos_y": caster["pos_y"],
                    "health": 10,
                    "max_health": 10,
                    "shield": 350,
                    "max_shield": 350,
                    "speed": 2.0,
                    "attack": 30,
                    "attack_range": 2.0,
                    "is_idle": True,
                    "carry_amount": 0,
                    "carry_capacity": 0,
                    "target_x": None,
                    "target_y": None,
                    "returning_to_base": False,
                    "attack_target_id": "",
                    "deposit_pending": False,
                    "buffs": [],
                }
                result[caster_id] = {**caster, **updates}

    # Process active storm/darkswarm effects
    for eid, e in list(result.items()):
        if e.get("entity_type") != "effect":
            continue
        etype = e.get("effect_type", "")
        age = tick - e.get("tick_created", tick)
        if age >= e.get("duration", 0):
            # Effect expired
            to_remove.add(eid)
            continue

        if etype == "psionic_storm":
            dpt = e.get("damage_per_tick", 0)
            radius = e.get("radius", 5.0)
            px, py = e["pos_x"], e["pos_y"]
            for tid, t in list(result.items()):
                if t.get("owner", 0) == 0:
                    continue
                d = math.hypot(t["pos_x"] - px, t["pos_y"] - py)
                if d <= radius:
                    new_health = t["health"] - dpt
                    result[tid] = {**t, "health": new_health}
                    if new_health <= 0:
                        to_remove.add(tid)

        elif etype == "nuclear_strike":
            # When age reaches duration, boom
            if age >= e.get("duration", 100) - 1:
                dmg = e.get("damage", 800)
                radius = e.get("radius", 8.0)
                px, py = e["pos_x"], e["pos_y"]
                for tid, t in list(result.items()):
                    if t.get("owner", 0) == 0 and t.get("entity_type") == "resource":
                        continue
                    d = math.hypot(t["pos_x"] - px, t["pos_y"] - py)
                    if d <= radius:
                        new_health = t["health"] - dmg
                        result[tid] = {**t, "health": new_health}
                        if new_health <= 0:
                            to_remove.add(tid)

    # Remove dead entities
    for eid in to_remove:
        result.pop(eid, None)

    # Add new entities
    result.update(new_entities)

    # Tick down spell cooldowns on all entities
    for eid, e in list(result.items()):
        keys_to_update = {}
        for k, v in e.items():
            if k.startswith("cooldown_") and isinstance(v, int) and v > 0:
                keys_to_update[k] = v - 1
        if keys_to_update:
            result[eid] = {**e, **keys_to_update}

    return result, res