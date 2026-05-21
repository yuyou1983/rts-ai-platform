"""Order queue — entity-level command queuing for RTS unit control.

Semantics:
  - replace(order): clear everything, set new current (right-click behavior)
  - append(order): add to end of FIFO queue (shift-queue behavior)
  - interrupt(order): push on top, save current for auto-resume
  - complete_current(): finish current, advance to next or resume interrupted

The active order is the front of _queue (index 0), or the top of
_interrupted if _queue is empty.  When complete_current() is called
and _queue becomes empty, the most recently interrupted order is
resumed (popped from _interrupted and inserted at front of _queue).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Order:
    """A single order issued to a unit.

    Attributes:
        action: Command type (move, attack, gather, stop, patrol, hold).
        target_id: Entity ID of the target (for attack/gather), or empty.
        target_x: X coordinate of the target position.
        target_y: Y coordinate of the target position.
        metadata: Extra key-value pairs for future use (e.g. build type).
    """

    action: str
    target_id: str = ""
    target_x: float = 0.0
    target_y: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for state snapshots."""
        return {
            "action": self.action,
            "target_id": self.target_id,
            "target_x": self.target_x,
            "target_y": self.target_y,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Order:
        """Deserialize from a plain dict."""
        return cls(
            action=data["action"],
            target_id=data.get("target_id", ""),
            target_x=data.get("target_x", 0.0),
            target_y=data.get("target_y", 0.0),
            metadata=data.get("metadata", {}),
        )


class OrderQueue:
    """FIFO order queue with interrupt/resume semantics.

    Internal structure:
      _queue: list[Order] — FIFO, index 0 = current active order
      _interrupted: list[Order] — LIFO stack for interrupted orders

    When ``interrupt()`` is called, the current active order AND any
    remaining queued orders are saved to the ``_interrupted`` stack so
    that they resume in their original order after the interrupt
    completes.  This models the common RTS behaviour where a unit
    that is interrupted (e.g. attacked while gathering) returns to its
    previous task once the interrupting order is done.

    current() returns the active order: front of _queue, or top of
    _interrupted if _queue is empty.  Returns None when idle.
    """

    def __init__(self) -> None:
        self._queue: list[Order] = []
        self._interrupted: list[Order] = []

    def current(self) -> Order | None:
        """Return the active order, or None if idle."""
        if self._queue:
            return self._queue[0]
        if self._interrupted:
            return self._interrupted[-1]
        return None

    def replace(self, order: Order) -> None:
        """Clear both _queue and _interrupted, set *order* as the new current.

        This models the default right-click behavior: issuing a new command
        cancels everything the unit was doing (or planning to do).
        """
        self._queue = [order]
        self._interrupted = []

    def append(self, order: Order) -> None:
        """Append *order* to the end of the FIFO queue.

        The currently active order (if any) is **not** interrupted.
        This models shift-queue: the new order will execute after the
        current one finishes.
        """
        self._queue.append(order)

    def interrupt(self, order: Order) -> None:
        """Push *order* on top, saving current work for auto-resume.

        The current active order and all remaining queued orders are
        saved to the ``_interrupted`` stack so they resume in their
        original order after the interrupting order completes.

        This models the common RTS pattern where a worker that is
        attacked while gathering will fight back (or flee), then
        automatically return to gathering.
        """
        # Collect all current work
        all_orders: list[Order] = []
        if self._queue:
            all_orders = list(self._queue)
        elif self._interrupted:
            all_orders = [self._interrupted.pop()]

        # Replace queue with just the new order
        self._queue = [order]

        if not all_orders:
            return

        # Push saved orders onto _interrupted stack so they resume
        # in their original order.
        # _interrupted is LIFO (top = last element).
        # We want: after interrupt completes → current, then remaining[0], remaining[1], …
        # So we push in reverse: remaining[n-1], …, remaining[0], current
        # Popping gives: current, remaining[0], remaining[1], …, remaining[n-1] ✓
        current_saved = all_orders[0]
        rest = all_orders[1:]
        for item in reversed(rest):
            self._interrupted.append(item)
        self._interrupted.append(current_saved)

    def complete_current(self) -> Order | None:
        """Finish the current active order and advance to the next.

        Returns the completed order, or None if already idle.
        After completion:
          - If more orders remain in _queue, next one becomes active.
          - If _queue is empty but _interrupted has entries, the most
            recently interrupted order resumes (popped from the stack
            and inserted at front of _queue so subsequent completions
            continue through the remaining interrupted orders).
        """
        cur = self.current()
        if cur is None:
            return None
        if self._queue:
            self._queue.pop(0)
        else:
            self._interrupted.pop()
        # Resume interrupted if queue is now empty
        if not self._queue and self._interrupted:
            resumed = self._interrupted.pop()
            self._queue.insert(0, resumed)
        return cur

    @property
    def is_idle(self) -> bool:
        """True when there are no pending or interrupted orders."""
        return not self._queue and not self._interrupted

    def to_list(self) -> list[dict]:
        """Serialize to a list of dicts for state snapshots.

        Layout:  [active_order, *remaining_queue, *interrupted_newest_first]
        Interrupted entries are tagged with ``metadata._interrupted = True``
        so that :meth:`from_list` can reconstruct the two internal lists.
        """
        result: list[dict] = []
        # Active order first
        cur = self.current()
        if cur is not None:
            result.append(cur.to_dict())
        # Remaining queued orders (after the active one)
        for order in self._queue[1:]:
            result.append(order.to_dict())
        # Interrupted stack (newest first for LIFO reconstruction)
        for order in reversed(self._interrupted):
            d = order.to_dict()
            d["metadata"] = {**d.get("metadata", {}), "_interrupted": True}
            result.append(d)
        return result

    @classmethod
    def from_list(cls, data: list[dict]) -> OrderQueue:
        """Deserialize from a list of dicts produced by to_list().

        Entries tagged with ``metadata._interrupted = True`` are placed
        in the ``_interrupted`` stack; all others go into ``_queue``.
        The ``_interrupted`` marker is stripped during reconstruction.
        """
        q = cls()
        if not data:
            return q

        queue_entries: list[dict] = []
        interrupted_entries: list[dict] = []

        for entry in data:
            md = entry.get("metadata", {})
            if md.get("_interrupted", False):
                # Remove the marker before creating Order
                clean_md = {k: v for k, v in md.items() if k != "_interrupted"}
                entry = {**entry, "metadata": clean_md}
                interrupted_entries.append(entry)
            else:
                queue_entries.append(entry)

        q._queue = [Order.from_dict(d) for d in queue_entries]
        # interrupted_entries are newest-first (from to_list), but _interrupted
        # stack top is [-1], so we reverse to put oldest-first in the list
        q._interrupted = [Order.from_dict(d) for d in reversed(interrupted_entries)]
        return q