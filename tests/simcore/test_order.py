"""Tests for Order and OrderQueue — entity-level command queuing."""
import pytest

from simcore.order import Order, OrderQueue


class TestOrderFields:
    """Basic Order construction and serialization."""

    def test_order_fields(self):
        """Order stores all fields with defaults."""
        o = Order(action="move", target_x=10.0, target_y=20.0)
        assert o.action == "move"
        assert o.target_id == ""
        assert o.target_x == 10.0
        assert o.target_y == 20.0
        assert o.metadata == {}

    def test_order_with_target_id(self):
        """Order can target an entity."""
        o = Order(action="attack", target_id="enemy_1")
        assert o.target_id == "enemy_1"

    def test_order_with_metadata(self):
        """Order carries optional metadata."""
        o = Order(action="gather", target_id="mineral_0", metadata={"priority": 1})
        assert o.metadata == {"priority": 1}

    def test_order_to_dict_roundtrip(self):
        """Order serializes and deserializes correctly."""
        o = Order(action="attack", target_id="e1", target_x=5.0, target_y=6.0,
                  metadata={"reason": "auto"})
        d = o.to_dict()
        o2 = Order.from_dict(d)
        assert o2 == o


class TestOrderQueueReplace:
    """replace() clears everything and sets a new current order."""

    def test_queue_replace(self):
        q = OrderQueue()
        q.append(Order(action="move", target_x=1.0, target_y=2.0))
        q.append(Order(action="move", target_x=3.0, target_y=4.0))
        q.replace(Order(action="attack", target_id="enemy"))
        assert q.current() is not None
        assert q.current().action == "attack"
        assert q.current().target_id == "enemy"
        # Only one order in queue now
        q.complete_current()
        assert q.is_idle

    def test_queue_replace_clears_interrupted(self):
        """replace() also clears the interrupted stack."""
        q = OrderQueue()
        q.replace(Order(action="gather", target_id="mineral_0"))
        q.interrupt(Order(action="attack", target_id="enemy"))
        # interrupted stack has the gather order
        assert q.current().action == "attack"
        q.replace(Order(action="move", target_x=10.0, target_y=20.0))
        assert q.current().action == "move"
        q.complete_current()
        assert q.is_idle  # interrupted gather is gone


class TestOrderQueueAppend:
    """append() adds orders to the FIFO queue without interrupting current."""

    def test_queue_append(self):
        q = OrderQueue()
        q.append(Order(action="move", target_x=1.0, target_y=2.0))
        q.append(Order(action="move", target_x=3.0, target_y=4.0))
        # First is active
        assert q.current().target_x == 1.0
        q.complete_current()
        assert q.current().target_x == 3.0

    def test_queue_multiple_append(self):
        """Multiple appends queue up in order."""
        q = OrderQueue()
        for i in range(5):
            q.append(Order(action="move", target_x=float(i), target_y=0.0))
        for i in range(5):
            assert q.current().target_x == float(i)
            q.complete_current()
        assert q.is_idle


class TestOrderQueueAutoResume:
    """complete_current() advances through the queue."""

    def test_queue_auto_resume(self):
        q = OrderQueue()
        q.append(Order(action="move", target_x=1.0, target_y=2.0))
        q.append(Order(action="gather", target_id="mineral_0"))
        # Current is move
        assert q.current().action == "move"
        q.complete_current()
        # Advances to gather
        assert q.current().action == "gather"
        assert q.current().target_id == "mineral_0"
        q.complete_current()
        assert q.is_idle


class TestOrderQueueInterrupt:
    """interrupt() pushes on top and saves current for resume."""

    def test_queue_interrupt(self):
        q = OrderQueue()
        q.replace(Order(action="gather", target_id="mineral_0"))
        q.interrupt(Order(action="attack", target_id="enemy"))
        # Attack is now current
        assert q.current().action == "attack"
        assert q.current().target_id == "enemy"
        # Complete attack → resume gather
        q.complete_current()
        assert q.current().action == "gather"
        assert q.current().target_id == "mineral_0"
        q.complete_current()
        assert q.is_idle

    def test_queue_interrupt_stack(self):
        """Multiple interrupts resume in reverse (LIFO)."""
        q = OrderQueue()
        q.replace(Order(action="move", target_x=0.0, target_y=0.0))
        q.interrupt(Order(action="attack", target_id="e1"))
        q.interrupt(Order(action="attack", target_id="e2"))
        # Current = e2
        assert q.current().target_id == "e2"
        q.complete_current()
        assert q.current().target_id == "e1"
        q.complete_current()
        assert q.current().action == "move"
        q.complete_current()
        assert q.is_idle

    def test_interrupt_on_idle(self):
        """Interrupting an idle queue just sets the order."""
        q = OrderQueue()
        assert q.is_idle
        q.interrupt(Order(action="attack", target_id="e1"))
        assert q.current().action == "attack"
        q.complete_current()
        assert q.is_idle


class TestOrderQueueIdle:
    """is_idle returns True when no orders remain."""

    def test_queue_idle(self):
        q = OrderQueue()
        assert q.is_idle
        assert q.current() is None

    def test_not_idle_when_has_orders(self):
        q = OrderQueue()
        q.append(Order(action="move"))
        assert not q.is_idle


class TestOrderQueueSerialization:
    """to_list / from_list round-trip."""

    def test_queue_serialize_deserialize(self):
        q = OrderQueue()
        q.append(Order(action="move", target_x=1.0, target_y=2.0))
        q.append(Order(action="gather", target_id="mineral_0"))
        q.interrupt(Order(action="attack", target_id="enemy"))

        data = q.to_list()
        q2 = OrderQueue.from_list(data)
        # Same active order
        assert q2.current().action == "attack"
        assert q2.current().target_id == "enemy"
        # Complete attack → resume
        q2.complete_current()
        assert q2.current().action == "move"
        q2.complete_current()
        assert q2.current().action == "gather"
        q2.complete_current()
        assert q2.is_idle

    def test_serialize_empty_queue(self):
        q = OrderQueue()
        data = q.to_list()
        assert data == []
        q2 = OrderQueue.from_list(data)
        assert q2.is_idle

    def test_serialize_interrupted_stack(self):
        """Multiple interrupted orders survive round-trip."""
        q = OrderQueue()
        q.replace(Order(action="move", target_x=0.0, target_y=0.0))
        q.interrupt(Order(action="attack", target_id="e1"))
        q.interrupt(Order(action="attack", target_id="e2"))

        data = q.to_list()
        q2 = OrderQueue.from_list(data)
        assert q2.current().target_id == "e2"
        q2.complete_current()
        assert q2.current().target_id == "e1"
        q2.complete_current()
        assert q2.current().action == "move"
        q2.complete_current()
        assert q2.is_idle


# ─── Integration tests: OrderQueue inside SimCore ───────────────────────


class TestEntityOrderQueueFlagOff:
    """When enable_order_queue=False, no order_queue field appears."""

    def test_entity_order_queue_with_flag_off(self):
        from simcore.engine import SimCore

        engine = SimCore(enable_order_queue=False)
        engine.initialize(map_seed=42)
        state = engine.step(commands=[])
        # Pick a worker entity
        for eid, e in state.entities.items():
            if e.get("entity_type") == "worker":
                assert "order_queue" not in e
                break


class TestEntityOrderQueueFlagOn:
    """When enable_order_queue=True, order_queue field is present."""

    def test_entity_order_queue_with_flag_on(self):
        from simcore.engine import SimCore

        engine = SimCore(enable_order_queue=True)
        engine.initialize(map_seed=42)
        # After init, workers should have order_queue field
        found = False
        for eid, e in engine.state.entities.items():
            if e.get("entity_type") == "worker":
                found = True
                assert "order_queue" in e
                assert isinstance(e["order_queue"], list)
        assert found, "Expected at least one worker entity"


class TestOrderQueueReplaceSemantics:
    """Default command (no queued flag) replaces the queue."""

    def test_order_queue_replace_semantics(self):
        from simcore.engine import SimCore

        engine = SimCore(enable_order_queue=True)
        engine.initialize(map_seed=42)
        # Find a worker
        wid = None
        for eid, e in engine.state.entities.items():
            if e.get("entity_type") == "worker" and e.get("owner") == 1:
                wid = eid
                break
        assert wid is not None

        # Issue a move command (no queued flag → replace)
        cmd = {"action": "move", "issuer": 1, "unit_id": wid,
               "target_x": 10.0, "target_y": 10.0}
        state = engine.step(commands=[cmd])
        oq = state.entities[wid].get("order_queue", [])
        assert len(oq) >= 1
        assert oq[0]["action"] == "move"

        # Issue another move (replace) → should only have the new one
        cmd2 = {"action": "move", "issuer": 1, "unit_id": wid,
                "target_x": 20.0, "target_y": 20.0}
        state = engine.step(commands=[cmd2])
        oq = state.entities[wid].get("order_queue", [])
        # Should only have the latest move (replace clears queue)
        assert oq[0]["action"] == "move"
        assert oq[0]["target_x"] == 20.0
        # No extra orders in queue
        assert len(oq) == 1


class TestOrderQueueQueuedSemantics:
    """queued=true appends to the queue."""

    def test_order_queue_queued_semantics(self):
        from simcore.engine import SimCore

        engine = SimCore(enable_order_queue=True)
        engine.initialize(map_seed=42)
        wid = None
        for eid, e in engine.state.entities.items():
            if e.get("entity_type") == "worker" and e.get("owner") == 1:
                wid = eid
                break
        assert wid is not None

        # First move (replace)
        cmd1 = {"action": "move", "issuer": 1, "unit_id": wid,
                "target_x": 10.0, "target_y": 10.0}
        state = engine.step(commands=[cmd1])

        # Second move with queued=True → append
        cmd2 = {"action": "move", "issuer": 1, "unit_id": wid,
                "target_x": 20.0, "target_y": 20.0, "queued": True}
        state = engine.step(commands=[cmd2])
        oq = state.entities[wid].get("order_queue", [])
        assert len(oq) == 2
        assert oq[0]["target_x"] == 10.0
        assert oq[1]["target_x"] == 20.0


class TestOrderQueueInterruptOnAttack:
    """ATTACK on a gathering/moving unit → interrupt + resume."""

    def test_order_queue_interrupt_on_attack(self):
        from simcore.engine import SimCore

        engine = SimCore(enable_order_queue=True)
        engine.initialize(map_seed=42)
        wid = None
        for eid, e in engine.state.entities.items():
            if e.get("entity_type") == "worker" and e.get("owner") == 1:
                wid = eid
                break
        assert wid is not None

        # Find a mineral and an enemy unit for targeting
        mineral_id = None
        enemy_id = None
        for eid, e in engine.state.entities.items():
            if e.get("entity_type") == "resource" and e.get("resource_type") == "mineral" and mineral_id is None:
                mineral_id = eid
            if e.get("owner") == 2 and e.get("entity_type") == "worker" and enemy_id is None:
                enemy_id = eid
        assert mineral_id is not None, "Need a mineral patch"
        assert enemy_id is not None, "Need an enemy worker"

        # Issue gather command (replace)
        cmd_gather = {"action": "gather", "issuer": 1, "unit_id": wid,
                      "resource_id": mineral_id}
        state = engine.step(commands=[cmd_gather])
        oq = state.entities[wid].get("order_queue", [])
        assert len(oq) >= 1
        assert oq[0]["action"] == "gather"

        # Issue attack command (should interrupt, not replace)
        cmd_attack = {"action": "attack", "issuer": 1, "attacker_id": wid,
                       "target_id": enemy_id}
        state = engine.step(commands=[cmd_attack])
        oq = state.entities[wid].get("order_queue", [])

        # Active order should be attack
        assert oq[0]["action"] == "attack"
        # Gather should be in the queue (interrupted, marked for resume)
        has_interrupted_gather = any(
            e["action"] == "gather" and e.get("metadata", {}).get("_interrupted", False)
            for e in oq
        )
        assert has_interrupted_gather, f"Expected interrupted gather in queue, got {oq}"