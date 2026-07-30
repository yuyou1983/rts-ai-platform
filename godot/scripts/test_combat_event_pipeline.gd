extends SceneTree

## Headless test for the event-driven combat visual pipeline.
##
## Verifies that CombatVisualController dispatches each unique combat event
## exactly once to the VFX sink, and that replaying the same event_id (e.g.
## from an HTTP retry) does NOT produce a duplicate.
##
## Run with:
##   godot --headless --script res://scripts/test_combat_event_pipeline.gd
##
## Prints "PASS" and exits 0 on success, "FAIL: <reason>" and exits 1 otherwise.

const CombatVisualControllerScript := preload("res://scripts/combat_visual_controller.gd")


## Minimal fake VFX sink. Subclasses VFXManager so it satisfies the
## controller's typed _vfx_manager slot, but overrides spawn_combat_event to
## just record the dispatched events (no rendering, no catalog access).
class FakeVFXSink extends VFXManager:
	var received: Array = []

	func spawn_combat_event(event: Dictionary) -> void:
		received.append(event)


func _initialize() -> void:
	var passed: bool = _run_tests()
	if passed:
		print("PASS")
		quit(0)
	else:
		quit(1)


func _run_tests() -> bool:
	var ctrl: CombatVisualController = CombatVisualControllerScript.new()
	var sink: FakeVFXSink = FakeVFXSink.new()
	ctrl.set_vfx_manager(sink)

	var test_event: Dictionary = {
		"event_id": "12:0",
		"tick": 12,
		"event_type": "impact_resolved",
		"attacker_id": "m1",
		"target_id": "z1",
		"weapon_id": "terran_c10_rifle",
		"source_x": 2.0,
		"source_y": 3.0,
		"target_x": 5.0,
		"target_y": 3.0,
		"delivery_type": "hitscan",
		"final_damage": 6.0,
	}

	# First feed: the sink should receive exactly one event.
	ctrl.process_combat_events([test_event])
	if sink.received.size() != 1:
		_fail("expected 1 event after first feed, got %d" % sink.received.size(), ctrl, sink)
		return false

	# Sanity: the dispatched event should be a hit (not shield, not missed-skip).
	var dispatched: Dictionary = sink.received[0]
	if str(dispatched.get("event_type", "")) != "hit_confirmed":
		_fail("expected hit_confirmed, got %s" % str(dispatched.get("event_type", "")), ctrl, sink)
		return false

	# Replay the same event_id: dedup must prevent a duplicate dispatch.
	ctrl.process_combat_events([test_event])
	if sink.received.size() != 1:
		_fail("expected 1 event after replay (dedup), got %d" % sink.received.size(), ctrl, sink)
		return false

	# A different event_id should be dispatched (sanity for the dedup logic).
	var second_event: Dictionary = test_event.duplicate()
	second_event["event_id"] = "12:1"
	ctrl.process_combat_events([second_event])
	if sink.received.size() != 2:
		_fail("expected 2 events after a new event_id, got %d" % sink.received.size(), ctrl, sink)
		return false

	ctrl.free()
	sink.free()
	return true


func _fail(reason: String, ctrl: Node, sink: Node) -> void:
	print("FAIL: %s" % reason)
	if ctrl:
		ctrl.free()
	if sink:
		sink.free()
