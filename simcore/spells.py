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

from simcore.combat_events import SPELL_RESOLVED, append_combat_event
from simcore.combat_resolution import KillFeed, resolve_weapon_impact
from simcore.state import GameState

# ─── Constants ───────────────────────────────────────────────

ENERGY_REGEN_RATE = 0.75  # per tick
_MAP_TILE_SIZE = 32.0      # game-units per tile


def _find_merge_partner(
    entities: dict[str, Any],
    caster_id: str,
    owner: int,
    unit_type: str,
    radius: float,
    *,
    exclude: set[str] | None = None,
) -> str | None:
    """Find nearest same-owner unit of *unit_type* within *radius* of caster."""
    if exclude is None:
        exclude = set()
    caster = entities.get(caster_id, {})
    cx, cy = caster.get("pos_x", 0), caster.get("pos_y", 0)
    best_id: str | None = None
    best_dist = radius + 1
    for eid, e in entities.items():
        if eid == caster_id or eid in exclude:
            continue
        if e.get("owner") != owner:
            continue
        ut = e.get("unit_type", "")
        if ut.lower().replace(" ", "") != unit_type.lower().replace(" ", ""):
            continue
        dx = e.get("pos_x", 0) - cx
        dy = e.get("pos_y", 0) - cy
        d = math.hypot(dx, dy)
        if d <= radius and d < best_dist:
            best_dist = d
            best_id = eid
    return best_id

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
    "irradiate": "TARGETED",
    # Protoss
    "psionicstorm": "AREA",
    "hallucination": "SUMMON",
    "recall": "SUMMON",
    "stasisfield": "AREA",
    "archonwarp": "SUMMON",
    "disruptionweb": "AREA",
    "feedback": "TARGETED",
    "mindcontrol": "TARGETED",
    "maelstrom": "AREA",
    # Zerg morph
    "lurker_morph": "TRANSFORM",
    "guardian_morph": "TRANSFORM",
    "devourer_morph": "TRANSFORM",
    # Protoss merge
    "meld": "SUMMON",
    "darkmeld": "SUMMON",
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
    "irradiate":       {"cost_mp": 75, "cooldown": 0,  "duration": 120, "radius": 0,   "damage": 0, "dot_total": 250},
    "feedback":        {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "mindcontrol":     {"cost_mp": 150,"cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0},
    "maelstrom":       {"cost_mp": 100,"cooldown": 0,  "duration": 60,  "radius": 5.0, "damage": 0},
    # Zerg morph (timed transformation — morph_timer in ticks)
    "lurker_morph":    {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0, "morph_ticks": 200},
    "guardian_morph":  {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0, "morph_ticks": 150},
    "devourer_morph":  {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 0,   "damage": 0, "morph_ticks": 150},
    # Protoss merge
    "meld":           {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 3.0, "damage": 0, "merge_ticks": 120},
    "darkmeld":       {"cost_mp": 0,  "cooldown": 0,  "duration": 0,   "radius": 3.0, "damage": 0, "merge_ticks": 120},
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
                elif btype == "stasis":
                    result[eid] = {**result.get(eid, e),
                                   "stasis": False}
                elif btype == "maelstrom":
                    result[eid] = {**result.get(eid, e),
                                   "stasis": False}
                elif btype == "irradiate":
                    pass  # irradiate DoT applied per-tick below
        if new_buffs != buffs:
            result[eid] = {**result.get(eid, e), "buffs": new_buffs}
    return result


def process_dots(entities: dict[str, Any], tick: int) -> dict[str, Any]:
    """Process per-tick damage-over-time effects (irradiate, plague)."""
    result = dict(entities)
    to_remove: set[str] = set()
    for eid, e in list(result.items()):
        for b in e.get("buffs", []):
            btype = b.get("type", "")
            if btype == "irradiate":
                # Damage the buff carrier
                dot = b.get("dot_per_tick", 0)
                new_h = e["health"] - dot
                result[eid] = {**result.get(eid, e), "health": new_h}
                if new_h <= 0:
                    to_remove.add(eid)
                # Also damage nearby organic enemies
                src_owner = b.get("source_owner", 0)
                for oid, o in list(result.items()):
                    if oid == eid:
                        continue
                    if o.get("owner", 0) == src_owner:
                        continue  # same team as caster — no friendly fire
                    d = math.hypot(o["pos_x"] - e["pos_x"], o["pos_y"] - e["pos_y"])
                    if d <= _MAP_TILE_SIZE and o.get("is_organic", True):
                        new_oh = o["health"] - dot
                        result[oid] = {**result.get(oid, o), "health": new_oh}
                        if new_oh <= 0:
                            to_remove.add(oid)
    for rid in to_remove:
        result.pop(rid, None)
    return result


# ─── Spell Processing ────────────────────────────────────────

def process_spells(
    entities: dict[str, Any],
    resources: dict[str, int],
    commands: list[dict],
    tick: int,
    *,
    combat_events: list[dict] | None = None,
    kill_feed: KillFeed | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Process spell commands for this tick.

    Returns (updated_entities, updated_resources).

    This is called every tick (even with an empty command list) so that
    persistent spell effects such as Psionic Storm can advance their
    per-tick damage schedule.

    Args:
        combat_events: Optional append-only combat event list.  Spell casts
            append a single ``SPELL_RESOLVED`` event; each damage tick of an
            area spell appends ``IMPACT_RESOLVED`` events via
            ``resolve_weapon_impact()``.  When ``None`` a throwaway list is
            used so spell logic still runs.
        kill_feed: Optional ``KillFeed`` tracker for damage/kill statistics.
    """
    result = dict(entities)
    res = dict(resources)
    new_entities: dict[str, Any] = {}
    to_remove: set[str] = set()

    # Local sinks when the caller (e.g. legacy unit tests) does not supply
    # them.  This preserves the old positional call signature while still
    # letting spell effects emit events internally.
    if combat_events is None:
        combat_events = []
    if kill_feed is None:
        kill_feed = KillFeed()

    # Check if there are any active spell effects to process
    has_active_effects = any(
        e.get("entity_type") == "effect" and e.get("effect_type") == "psionic_storm"
        for e in result.values()
    )

    # Only run regen/buff/dot when there are spell commands or active effects.
    # The engine already calls regen_energy at step 14 — calling it here too
    # would double-regen energy every tick.
    if commands or has_active_effects:
        # Regen energy first
        result = regen_energy(result, tick)

        # Process active buffs
        result = process_buffs(result, tick)

        # Process per-tick DoT effects
        result = process_dots(result, tick)

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
            # ─── Zerg morph (timed) ────────────────────────────
            elif spell_name in ("lurker_morph", "guardian_morph", "devourer_morph"):
                morph_target = {
                    "lurker_morph": "Lurker",
                    "guardian_morph": "Guardian",
                    "devourer_morph": "Devourer",
                }[spell_name]
                morph_ticks = config.get("morph_ticks", 150)
                updates["morph_target"] = morph_target
                updates["morph_timer"] = morph_ticks
                updates["morphing"] = True
                updates["is_idle"] = True
                updates["attack_target_id"] = ""
                # Freeze combat stats while morphing
                updates["attack_ground"] = 0
                updates["attack_air"] = 0
                updates["speed"] = 0
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
                # Remove negative buffs including parasite
                buffs = [b for b in target.get("buffs", [])
                         if b.get("type") not in ("lockdown", "plague", "ensnare",
                                                   "optical_flare", "irradiate",
                                                   "maelstrom")]
                result[target_id] = {**target, "buffs": buffs}
                if "parasited_by" in target:
                    target = {**target, "parasited_by": None}
                    result[target_id] = target
                result[caster_id] = {**caster, **updates}
            elif spell_name == "opticalflare":
                duration = 99999  # permanent until restored
                buffs = list(target.get("buffs", []))
                buffs.append({"type": "optical_flare", "remaining": duration})
                result[target_id] = {**target, "buffs": buffs, "sight": 1}
                result[caster_id] = {**caster, **updates}
            elif spell_name == "irradiate":
                # Bio-only DoT: 250 damage over 120 ticks, also damages nearby bio
                duration = config.get("duration", 120)
                dot_total = config.get("dot_total", 250)
                dot_per_tick = dot_total / duration
                buffs = list(target.get("buffs", []))
                buffs.append({"type": "irradiate", "remaining": duration,
                              "dot_per_tick": dot_per_tick, "source_owner": owner})
                result[target_id] = {**target, "buffs": buffs}
                result[caster_id] = {**caster, **updates}
            elif spell_name == "feedback":
                # Drain all energy from target, deal equal damage
                target_energy = target.get("energy", 0)
                if target_energy > 0 and target.get("is_spellcaster", False):
                    new_health = target["health"] - target_energy
                    result[target_id] = {**target, "health": new_health, "energy": 0}
                    if new_health <= 0:
                        to_remove.add(target_id)
                result[caster_id] = {**caster, **updates}
            elif spell_name == "mindcontrol":
                # Permanently change target's owner
                if target.get("owner", 0) != owner:
                    result[target_id] = {**target, "owner": owner,
                                         "attack_target_id": "", "is_idle": True}
                result[caster_id] = {**caster, **updates}

        # ─── AREA ─────────────────────────────────────────
        elif category == "AREA":
            target_x = cmd.get("target_x", caster["pos_x"])
            target_y = cmd.get("target_y", caster["pos_y"])
            radius = config.get("radius", 5.0)

            if spell_name == "psionicstorm":
                # SC1 Psionic Storm: 8 damage ticks × 14 damage = 112 total.
                # On the cast tick we ONLY create the effect entity and emit a
                # single SPELL_RESOLVED event — NO damage is applied here.
                # Damage is dealt on subsequent ticks by the effect processor
                # below, routed through resolve_weapon_impact().
                storm_id = f"storm_{tick}_{caster_id}"
                new_entities[storm_id] = {
                    "id": storm_id,
                    "effect_id": storm_id,
                    "caster_id": caster_id,
                    "owner": owner,
                    "entity_type": "effect",
                    "effect_type": "psionic_storm",
                    "pos_x": target_x,
                    "pos_y": target_y,
                    "start_tick": tick,
                    "tick_created": tick,  # legacy field for generic effect loop
                    "damage_per_tick": 14,
                    "max_damage_ticks": 8,
                    "damage_ticks_applied": 0,
                    "radius": radius,
                }
                # Cast emits exactly one SPELL_RESOLVED event (no impact).
                append_combat_event(
                    combat_events,
                    tick=tick,
                    event_type=SPELL_RESOLVED,
                    attacker_id=caster_id,
                    caster_id=caster_id,
                    weapon_id="protoss_psionic_storm",
                    target_x=target_x,
                    target_y=target_y,
                    radius=radius,
                    effect_id=storm_id,
                    delivery_type="area_periodic",
                )
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
                        eu["shields"] = max(0, e.get("shields", e.get("shield", 0)) - drain_s)
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

            elif spell_name == "maelstrom":
                # AoE stun: freezes organic units in radius for duration
                duration = config.get("duration", 60)
                for eid, e in list(result.items()):
                    if e.get("owner", 0) == owner:
                        continue  # friendly fire off
                    d = math.hypot(e["pos_x"] - target_x, e["pos_y"] - target_y)
                    if d <= radius and e.get("is_organic", True):
                        buffs = list(e.get("buffs", []))
                        buffs.append({"type": "maelstrom", "remaining": duration})
                        result[eid] = {**e, "buffs": buffs, "stasis": True,
                                       "speed": 0, "attack_ground": 0, "attack_air": 0}
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
                # Create an Archon at caster's location (legacy — free Archon)
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
                    "shields": 350,
                    "max_shields": 350,
                    "speed": 2.0,
                    "attack": 30,
                    "attack_ground": 30,
                    "attack_air": 30,
                    "weapon_type_ground": "normal",
                    "weapon_type_air": "normal",
                    "attack_range": 2.0,
                    "attack_range_ground": 2.0,
                    "attack_range_air": 2.0,
                    "cooldown_ground": 20,
                    "cooldown_air": 20,
                    "cooldown_timer": 20,
                    "armor": 0,
                    "armor_type": "heavy",
                    "domain": "ground",
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

            elif spell_name == "meld":
                # Merge 2 Templars into Archon: find nearby Templar of same owner
                merge_radius = config.get("radius", 3.0) * _MAP_TILE_SIZE
                merge_ticks = config.get("merge_ticks", 120)
                partner_id = _find_merge_partner(result, caster_id, owner, "Templar",
                                                  merge_radius, exclude=to_remove)
                if partner_id:
                    # Remove both templars, spawn morphing Archon cocoon
                    to_remove.add(caster_id)
                    to_remove.add(partner_id)
                    # Combined shields = sum of both templars' HP+shields
                    t1 = result[caster_id]
                    t2 = result[partner_id]
                    combined_shields = (t1.get("health", 0) + t1.get("shields", 0)
                                       + t2.get("health", 0) + t2.get("shields", 0))
                    combined_shields = min(combined_shields, 350)  # cap at Archon max
                    aid = f"archon_meld_{tick}_{caster_id}"
                    new_entities[aid] = {
                        "id": aid,
                        "owner": owner,
                        "entity_type": "unit",
                        "unit_type": "Archon",
                        "pos_x": t1["pos_x"],
                        "pos_y": t1["pos_y"],
                        "health": 10,
                        "max_health": 10,
                        "shields": combined_shields,
                        "max_shields": 350,
                        "speed": 0,
                        "attack_ground": 0,
                        "attack_air": 0,
                        "weapon_type_ground": "normal",
                        "weapon_type_air": "normal",
                        "attack_range_ground": 2.0,
                        "attack_range_air": 2.0,
                        "cooldown_ground": 20,
                        "cooldown_air": 20,
                        "cooldown_timer": 20,
                        "armor": 0,
                        "armor_type": "heavy",
                        "domain": "ground",
                        "is_idle": True,
                        "carry_amount": 0,
                        "carry_capacity": 0,
                        "target_x": None,
                        "target_y": None,
                        "returning_to_base": False,
                        "attack_target_id": "",
                        "deposit_pending": False,
                        "buffs": [],
                        # Morph state — will be activated by construction.py morph processor
                        "morphing": True,
                        "morph_target": "Archon",
                        "morph_timer": merge_ticks,
                    }

            elif spell_name == "darkmeld":
                # Merge 2 Dark Templars into Dark Archon
                merge_radius = config.get("radius", 3.0) * _MAP_TILE_SIZE
                merge_ticks = config.get("merge_ticks", 120)
                partner_id = _find_merge_partner(result, caster_id, owner, "DarkTemplar",
                                                  merge_radius, exclude=to_remove)
                if partner_id:
                    to_remove.add(caster_id)
                    to_remove.add(partner_id)
                    t1 = result[caster_id]
                    t2 = result[partner_id]
                    combined_shields = (t1.get("health", 0) + t1.get("shields", 0)
                                       + t2.get("health", 0) + t2.get("shields", 0))
                    combined_shields = min(combined_shields, 200)
                    daid = f"darkarchon_meld_{tick}_{caster_id}"
                    new_entities[daid] = {
                        "id": daid,
                        "owner": owner,
                        "entity_type": "unit",
                        "unit_type": "DarkArchon",
                        "pos_x": t1["pos_x"],
                        "pos_y": t1["pos_y"],
                        "health": 25,
                        "max_health": 25,
                        "shields": combined_shields,
                        "max_shields": 200,
                        "speed": 0,
                        "attack_ground": 0,
                        "attack_air": 0,
                        "weapon_type_ground": "none",
                        "weapon_type_air": "none",
                        "attack_range_ground": 0,
                        "attack_range_air": 0,
                        "cooldown_ground": 0,
                        "cooldown_air": 0,
                        "cooldown_timer": 0,
                        "armor": 1,
                        "armor_type": "heavy",
                        "domain": "ground",
                        "is_spellcaster": True,
                        "energy": 50,
                        "is_idle": True,
                        "carry_amount": 0,
                        "carry_capacity": 0,
                        "target_x": None,
                        "target_y": None,
                        "returning_to_base": False,
                        "attack_target_id": "",
                        "deposit_pending": False,
                        "buffs": [],
                        "morphing": True,
                        "morph_target": "DarkArchon",
                        "morph_timer": merge_ticks,
                    }

    # Process active storm/darkswarm effects
    for eid, e in list(result.items()):
        if e.get("entity_type") != "effect":
            continue
        etype = e.get("effect_type", "")

        if etype == "psionic_storm":
            # ── SC1 Psionic Storm lifecycle ─────────────────────
            # 8 damage ticks of 14 damage each, dealt on ticks AFTER the cast
            # tick. Damage is routed through resolve_weapon_impact() so that
            # shields/armor/size-multiplier and combat-event emission are
            # handled by the single authoritative damage path.
            start_tick = e.get("start_tick", e.get("tick_created", tick))
            dpt = e.get("damage_per_tick", 14)
            max_ticks = e.get("max_damage_ticks", 8)
            applied = e.get("damage_ticks_applied", 0)
            radius = e.get("radius", 5.0)
            px, py = e["pos_x"], e["pos_y"]
            caster_id = e.get("caster_id", "")
            effect_id = e.get("effect_id", eid)
            storm_owner = e.get("owner", 0)

            # Expire once all damage ticks have been applied.
            if applied >= max_ticks:
                to_remove.add(eid)
                continue
            # No damage on the cast tick itself — first hit lands on tick+1.
            if tick <= start_tick:
                continue

            for tid, t in list(result.items()):
                if tid == eid:
                    continue
                if t.get("entity_type") == "effect":
                    continue
                if t.get("owner", 0) == 0:
                    continue  # skip neutral / resources
                d = math.hypot(t["pos_x"] - px, t["pos_y"] - py)
                if d <= radius:
                    result, removed = resolve_weapon_impact(
                        result,
                        attacker_id=caster_id,
                        target_id=tid,
                        weapon_id="protoss_psionic_storm",
                        weapon_type="normal",
                        base_damage=dpt,
                        tick=tick,
                        combat_events=combat_events,
                        kill_feed=kill_feed,
                        projectile_id=effect_id,
                        delivery_type="area_periodic",
                    )
                    to_remove.update(removed)
            # Record that this damage tick fired.
            result[eid] = {**e, "damage_ticks_applied": applied + 1}
            continue

        # ── Generic effect expiry + remaining effect types ─────
        age = tick - e.get("tick_created", tick)
        if age >= e.get("duration", 0):
            # Effect expired
            to_remove.add(eid)
            continue

        if etype == "nuclear_strike":
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

    # Tick down spell cooldowns on all entities (but NOT attack cooldowns
    # like cooldown_timer / cooldown_ground — those are handled by
    # resolve_combat).
    _ATTACK_COOLDOWN_KEYS = frozenset({"cooldown_timer", "cooldown_ground", "cooldown_air"})
    for eid, e in list(result.items()):
        keys_to_update = {}
        for k, v in e.items():
            if k.startswith("cooldown_") and k not in _ATTACK_COOLDOWN_KEYS and isinstance(v, int) and v > 0:
                keys_to_update[k] = v - 1
        if keys_to_update:
            result[eid] = {**e, **keys_to_update}

    return result, res