"""Event log system for SimCore — produces events_this_tick in state snapshots.

Event types follow ADR CP-4: SimCore produces events_this_tick: list[dict]
in state snapshot. L2 Agents consume via obs/replay. Never direct callback.
"""
from __future__ import annotations

# ─── Event Type Constants ────────────────────────────────────

UNIT_CREATED = "unit_created"
UNIT_DESTROYED = "unit_destroyed"
BUILDING_COMPLETED = "building_completed"
RESOURCE_DEPLETED = "resource_depleted"
COMBAT_HIT = "combat_hit"
ORDER_COMPLETED = "order_completed"


def make_event(event_type: str, tick: int, **data) -> dict:
    """Create an event dict.

    Args:
        event_type: One of the event type constants.
        tick: Current tick number when the event occurred.
        **data: Additional event-specific data fields.

    Returns:
        Event dict with ``type``, ``tick``, and any additional data.
    """
    return {"type": event_type, "tick": tick, **data}