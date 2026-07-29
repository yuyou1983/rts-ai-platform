extends SceneTree

const CameraControllerScript = preload("res://scripts/camera_controller.gd")
const InputFeedbackControllerScript = preload("res://scripts/input_feedback_controller.gd")
const InputIntentRouterScript = preload("res://scripts/input_intent_router.gd")
const SelectionManagerScript = preload("res://scripts/selection_manager.gd")
const FeelMetricsRecorderScript = preload("res://scripts/feel_metrics_recorder.gd")

var _pass_count: int = 0
var _fail_count: int = 0


func _init() -> void:
	print("[TestOperationFeel] Starting headless behavior tests...")
	_test_intent_router()
	_test_camera_math()
	_test_selection_geometry()
	_test_three_race_selection_matrix()
	_test_feel_metrics()
	_test_attack_move_feedback()
	_summary()
	quit(1 if _fail_count > 0 else 0)


func _test_intent_router() -> void:
	var router: RefCounted = InputIntentRouterScript.new()
	_assert_equal(router.resolve_right_click(true, false, false, {}), InputIntentRouterScript.Intent.MOVE, "units + ground resolves move")
	_assert_equal(router.resolve_right_click(true, false, false, {"type": "soldier", "owner": 2}), InputIntentRouterScript.Intent.ATTACK, "units + enemy resolves attack")
	_assert_equal(router.resolve_right_click(true, false, true, {"type": "resource", "owner": 0}), InputIntentRouterScript.Intent.GATHER, "worker + resource resolves gather")
	_assert_equal(router.resolve_right_click(false, true, false, {}), InputIntentRouterScript.Intent.RALLY, "building + ground resolves rally")
	_assert_equal(router.resolve_right_click(false, false, false, {}), InputIntentRouterScript.Intent.NONE, "empty selection resolves none")
	_assert_equal(InputIntentRouterScript.intent_name(InputIntentRouterScript.Intent.ATTACK_MOVE), "attack_move", "attack-move intent has stable name")


func _test_camera_math() -> void:
	var zoom_720p: float = CameraControllerScript.calculate_zoom_for_visible_width(1280.0, 32.0)
	var zoom_1080p: float = CameraControllerScript.calculate_zoom_for_visible_width(1920.0, 32.0)
	_assert_near(1280.0 / zoom_720p, 32.0, 0.001, "720p visible width is stable")
	_assert_near(1920.0 / zoom_1080p, 32.0, 0.001, "1080p visible width is stable")
	var horizontal: Vector2 = CameraControllerScript.normalize_movement_direction(Vector2.RIGHT)
	var diagonal: Vector2 = CameraControllerScript.normalize_movement_direction(Vector2(1.0, 1.0))
	_assert_near(horizontal.length(), diagonal.length(), 0.001, "diagonal camera speed is normalized")


func _test_selection_geometry() -> void:
	var selection: Node = SelectionManagerScript.new()
	selection.drag_threshold_px = 5.0
	selection.click_slop_px = 6.0
	_assert_equal(selection.classify_pointer_release(Vector2.ZERO, Vector2(4.9, 0.0)), "click", "4.9px release is click")
	_assert_equal(selection.classify_pointer_release(Vector2.ZERO, Vector2(5.1, 0.0)), "drag", "5.1px release is drag")
	_assert_near(selection.click_hit_radius_world(0.05, 60.0), 0.1, 0.001, "6px minimum hit radius converts to world units")
	_assert_near(selection.click_hit_radius_world(0.7, 60.0), 0.7, 0.001, "manifest radius remains authoritative when larger")
	selection.set_selection(["unit-a"])
	selection.remove_from_selection("unit-a")
	_assert_equal(selection.get_selected_ids().size(), 0, "selected entity can be toggled off")
	selection.free()


func _test_three_race_selection_matrix() -> void:
	var selection: Node = SelectionManagerScript.new()
	selection.click_slop_px = 6.0
	var entities: Array = []
	var races: Array[String] = ["terran", "zerg", "protoss"]
	for race_index in range(races.size()):
		for unit_index in range(10):
			entities.append({
				"id": "%s-%d" % [races[race_index], unit_index],
				"race": races[race_index],
				"owner": 1,
				"px": float(unit_index * 3),
				"py": float(race_index * 5),
				"selection_radius": 0.5 + float(race_index) * 0.05,
			})
	var click_successes: int = 0
	for entity in entities:
		var click_pos := Vector2(float(entity.px) + 0.1, float(entity.py))
		var hit: Dictionary = selection.choose_best_hit(entities, click_pos, 60.0, _qa_radius)
		if str(hit.get("id", "")) == str(entity.id):
			click_successes += 1
	_assert_near(float(click_successes) / float(entities.size()), 1.0, 0.001, "three-race 30-target click success meets gate")

	var box_successes: int = 0
	for box_index in range(10):
		var target_id: String = "terran-%d" % box_index
		var box := Rect2(Vector2(float(box_index * 3) - 0.4, -0.4), Vector2(0.8, 0.8))
		var ids: Array = selection.filter_owned_in_rect(entities, box, 1)
		if ids == [target_id]:
			box_successes += 1
	_assert_near(float(box_successes) / 10.0, 1.0, 0.001, "10-scenario box selection accuracy meets gate")
	selection.free()


func _qa_radius(entity: Dictionary) -> float:
	return float(entity.get("selection_radius", 0.5))


func _test_feel_metrics() -> void:
	var metrics: Node = FeelMetricsRecorderScript.new()
	metrics.configure(true, "user://feel_metrics_test.jsonl")
	var move_id: int = metrics.begin_event("right_click", 3, true)
	metrics.mark_feedback(move_id)
	metrics.mark_command(move_id)
	metrics.complete_event(move_id, "move")
	var assign_id: int = metrics.begin_event("control_group_assign_1", 3)
	metrics.mark_feedback(assign_id)
	metrics.complete_event(assign_id, "success")
	var group_id: int = metrics.begin_event("control_group_recall_1", 3)
	metrics.mark_feedback(group_id)
	metrics.complete_event(group_id, "success")
	var empty_group_id: int = metrics.begin_event("control_group_recall_2", 0)
	metrics.mark_feedback(empty_group_id)
	metrics.complete_event(empty_group_id, "empty")
	var summary: Dictionary = metrics.get_summary()
	_assert_near(float(summary["input_to_feedback_frames_p95"]), 0.0, 0.001, "immediate feedback records zero-frame latency")
	_assert_near(float(summary["empty_command_rate"]), 0.0, 0.001, "submitted command is not counted empty")
	_assert_near(float(summary["control_group_recall_success"]), 0.5, 0.001, "only recall events contribute to group success")
	_assert_equal(int(summary["sample_count"]), 4, "metrics summary counts completed samples")
	metrics.free()


func _test_attack_move_feedback() -> void:
	var feedback: InputFeedbackController = InputFeedbackControllerScript.new()
	feedback.show_attack_move_ping(Vector2(10.0, 12.0))
	_assert_equal(feedback._active_pings.size(), 1, "attack-move creates one ping")
	_assert_equal(str(feedback._active_pings[0].get("type", "")), "attack_move", "attack-move ping keeps intent type")
	feedback.free()


func _assert_equal(actual: Variant, expected: Variant, description: String) -> void:
	if actual == expected:
		_pass_count += 1
		print("  [PASS] %s" % description)
	else:
		_fail_count += 1
		push_error("  [FAIL] %s: expected=%s actual=%s" % [description, str(expected), str(actual)])


func _assert_near(actual: float, expected: float, tolerance: float, description: String) -> void:
	if absf(actual - expected) <= tolerance:
		_pass_count += 1
		print("  [PASS] %s" % description)
	else:
		_fail_count += 1
		push_error("  [FAIL] %s: expected=%.4f actual=%.4f" % [description, expected, actual])


func _summary() -> void:
	var total: int = _pass_count + _fail_count
	print("[TestOperationFeel] Results: %d/%d passed, %d failed" % [_pass_count, total, _fail_count])
