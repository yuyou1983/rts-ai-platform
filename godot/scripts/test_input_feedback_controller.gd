extends SceneTree

## Headless smoke test for InputFeedbackController.
## Validates: instantiation, config loading, ping creation, timer aging, and cleanup.
##
## Run: /path/to/Godot --headless --path godot --script scripts/test_input_feedback_controller.gd

const InputFeedbackControllerScript = preload("res://scripts/input_feedback_controller.gd")

var _controller: InputFeedbackController = null
var _pass_count: int = 0
var _fail_count: int = 0


func _init() -> void:
	print("[TestInputFeedbackController] Starting headless smoke test...")
	_run_tests()
	_summary()
	quit()


func _run_tests() -> void:
	# 1. Instantiate
	_controller = InputFeedbackControllerScript.new()
	_assert(_controller != null, "Controller instantiation")

	# 2. Confirm default ping durations loaded
	_assert(_controller.right_click_ping_seconds > 0.0, "right_click_ping_seconds > 0")
	_assert(_controller.attack_ping_seconds > 0.0, "attack_ping_seconds > 0")
	_assert(_controller.invalid_ping_seconds > 0.0, "invalid_ping_seconds > 0")
	_assert(_controller.control_group_assign_flash_seconds > 0.0, "control_group_assign_flash_seconds > 0")
	_assert(_controller.control_group_empty_hint_seconds > 0.0, "control_group_empty_hint_seconds > 0")

	# 3. Add a ground ping and verify _active_pings is non-empty
	var world_pos := Vector2(10.0, 20.0)
	_controller.show_ground_ping(world_pos)
	_assert(not _controller._active_pings.is_empty(), "_active_pings non-empty after show_ground_ping")

	# 4. Add an attack ping
	_controller.show_attack_ping(Vector2(5.0, 5.0))
	_assert(_controller._active_pings.size() == 2, "_active_pings has 2 entries after two pings")
	_controller.show_attack_move_ping(Vector2(6.0, 6.0))
	_assert(_controller._active_pings.size() == 3, "_active_pings has 3 entries after attack-move ping")

	# 5. Add an invalid ping
	_controller.show_invalid_ping(Vector2(0.0, 0.0))
	_assert(_controller._active_pings.size() == 4, "_active_pings has 4 entries after four pings")

	# 6. Add a control group hint and verify _active_hints is non-empty
	_controller.show_control_group_flash(1, true)
	_assert(not _controller._active_hints.is_empty(), "_active_hints non-empty after show_control_group_flash")

	# 7. Advance timers beyond all durations and verify cleanup
	var long_delta: float = 10.0  # well beyond any ping/hint duration
	_controller.advance_timers(long_delta)
	_assert(_controller._active_pings.is_empty(), "_active_pings empty after timeout")
	_assert(_controller._active_hints.is_empty(), "_active_hints empty after timeout")

	# 8. Test clear_all
	_controller.show_ground_ping(Vector2(1.0, 1.0))
	_controller.show_attack_ping(Vector2(2.0, 2.0))
	_controller.show_control_group_flash(2, false)
	_assert(_controller._active_pings.size() == 2, "pings before clear_all")
	_assert(_controller._active_hints.size() == 1, "hints before clear_all")
	_controller.clear_all()
	_assert(_controller._active_pings.is_empty(), "_active_pings empty after clear_all")
	_assert(_controller._active_hints.is_empty(), "_active_hints empty after clear_all")

	# Cleanup
	if _controller:
		_controller.queue_free()


func _assert(condition: bool, description: String) -> void:
	if condition:
		_pass_count += 1
		print("  [PASS] %s" % description)
	else:
		_fail_count += 1
		push_error("  [FAIL] %s" % description)


func _summary() -> void:
	var total: int = _pass_count + _fail_count
	print("\n[TestInputFeedbackController] Results: %d/%d passed, %d failed" % [_pass_count, total, _fail_count])
	if _fail_count > 0:
		push_error("[TestInputFeedbackController] SOME TESTS FAILED")
	else:
		print("[TestInputFeedbackController] ALL TESTS PASSED")
