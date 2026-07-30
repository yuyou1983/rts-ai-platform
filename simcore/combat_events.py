"""Combat event system for SimCore — authoritative per-tick combat events.

All combat rules, projectile resolution, and spell resolution paths must emit
events through ``append_combat_event()``.  Modules must NOT maintain their own
sequence counters — the list index IS the sequence.

Event types (string constants, matching proto enum names):
    ATTACK_STARTED      — unit passed cooldown gate and is in range
    PROJECTILE_SPAWNED  — projectile entity created for delayed delivery
    IMPACT_RESOLVED     — damage applied to a target (hit or miss)
    UNIT_DESTROYED      — target health reached 0
    SPELL_RESOLVED      — spell effect applied
"""
from __future__ import annotations

# ─── Event Type Constants ────────────────────────────────────
ATTACK_STARTED = "attack_started"
PROJECTILE_SPAWNED = "projectile_spawned"
IMPACT_RESOLVED = "impact_resolved"
UNIT_DESTROYED = "unit_destroyed"
SPELL_RESOLVED = "spell_resolved"

_VALID_TYPES = frozenset({
    ATTACK_STARTED,
    PROJECTILE_SPAWNED,
    IMPACT_RESOLVED,
    UNIT_DESTROYED,
    SPELL_RESOLVED,
})

# Fields that every event must have (besides event_id, tick, event_type)
_REQUIRED_FIELDS = frozenset({"event_id", "tick", "event_type"})


def make_combat_event(*, tick: int, sequence: int, event_type: str, **fields) -> dict:
    """Construct a combat event dict with a deterministic event_id.

    Args:
        tick: Current simulation tick.
        sequence: Per-tick sequence number (use ``len(events)`` before append).
        event_type: One of the ``*_STARTED`` / ``*_RESOLVED`` constants above.
        **fields: Event-specific data (attacker_id, target_id, weapon_id, …).

    Returns:
        Event dict with ``event_id`` = ``f"{tick}:{sequence}"``.
    """
    event = {"event_id": f"{tick}:{sequence}", "tick": tick, "event_type": event_type, **fields}
    validate_combat_event(event)
    return event


def append_combat_event(
    events: list[dict],
    *,
    tick: int,
    event_type: str,
    **fields,
) -> dict:
    """Create, validate, and append a combat event in one call.

    The sequence number is derived from the current list length, ensuring
    stable, unique IDs within a tick without manual counters.

    Args:
        events: The append-only combat event list for this tick.
        tick: Current simulation tick.
        event_type: One of the combat event type constants.
        **fields: Event-specific data.

    Returns:
        The event dict that was appended.
    """
    event = make_combat_event(
        tick=tick,
        sequence=len(events),
        event_type=event_type,
        **fields,
    )
    events.append(event)
    return event


def validate_combat_event(event: dict) -> None:
    """Validate a combat event dict.  Raises ``ValueError`` on invalid data.

    Checks:
        - ``event_type`` is a known constant.
        - ``weapon_id`` is non-empty (except for ``unit_destroyed`` events).
        - ``chain_index`` is non-negative.
        - ``hit_count`` >= 1 and ``hit_index`` < ``hit_count`` (when present).
    """
    et = event.get("event_type")
    if et not in _VALID_TYPES:
        raise ValueError(f"Unknown combat event type: {et!r}")

    # weapon_id must be non-empty except for pure death events
    if et != UNIT_DESTROYED:
        wid = event.get("weapon_id", "")
        if not wid:
            raise ValueError(f"combat event {event.get('event_id')} missing weapon_id")

    chain_idx = event.get("chain_index", 0)
    if chain_idx < 0:
        raise ValueError(f"combat event {event.get('event_id')} has negative chain_index: {chain_idx}")

    hit_count = event.get("hit_count")
    if hit_count is not None:
        if hit_count < 1:
            raise ValueError(f"combat event {event.get('event_id')} has hit_count < 1: {hit_count}")
        hit_index = event.get("hit_index", 0)
        if hit_index >= hit_count:
            raise ValueError(
                f"combat event {event.get('event_id')} has hit_index {hit_index} >= hit_count {hit_count}"
            )
