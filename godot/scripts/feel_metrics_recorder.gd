class_name FeelMetricsRecorder
extends Node

const DEFAULT_OUTPUT_PATH := "user://feel_metrics.jsonl"

var enabled: bool = false
var output_path: String = DEFAULT_OUTPUT_PATH
var _next_event_id: int = 1
var _active_events: Dictionary = {}
var _completed_events: Array[Dictionary] = []


func _ready() -> void:
	enabled = bool(ProjectSettings.get_setting("debug/feel_metrics_enabled", false))


func configure(is_enabled: bool, path: String = DEFAULT_OUTPUT_PATH) -> void:
	enabled = is_enabled
	output_path = path


func begin_event(event_name: String, selected_count: int, expects_command: bool = false) -> int:
	if not enabled:
		return -1
	var event_id: int = _next_event_id
	_next_event_id += 1
	_active_events[event_id] = {
		"event_name": event_name,
		"input_frame": Engine.get_process_frames(),
		"feedback_frame": -1,
		"command_frame": -1,
		"selected_count": selected_count,
		"expects_command": expects_command,
		"result": "pending",
	}
	return event_id


func mark_feedback(event_id: int) -> void:
	if not _active_events.has(event_id):
		return
	_active_events[event_id]["feedback_frame"] = Engine.get_process_frames()


func mark_command(event_id: int) -> void:
	if not _active_events.has(event_id):
		return
	_active_events[event_id]["command_frame"] = Engine.get_process_frames()


func complete_event(event_id: int, result: String) -> void:
	if not _active_events.has(event_id):
		return
	var record: Dictionary = _active_events[event_id]
	_active_events.erase(event_id)
	record["result"] = result
	_completed_events.append(record)
	_append_jsonl(record)


func get_summary() -> Dictionary:
	var feedback_latencies: Array[float] = []
	var expected_commands: int = 0
	var empty_commands: int = 0
	var control_group_total: int = 0
	var control_group_success: int = 0
	for record in _completed_events:
		var input_frame: int = int(record.get("input_frame", -1))
		var feedback_frame: int = int(record.get("feedback_frame", -1))
		if input_frame >= 0 and feedback_frame >= input_frame:
			feedback_latencies.append(float(feedback_frame - input_frame))
		if bool(record.get("expects_command", false)):
			expected_commands += 1
			if int(record.get("command_frame", -1)) < 0:
				empty_commands += 1
		if str(record.get("event_name", "")).begins_with("control_group_recall"):
			control_group_total += 1
			if str(record.get("result", "")) == "success":
				control_group_success += 1

	feedback_latencies.sort()
	var p95: float = 0.0
	if not feedback_latencies.is_empty():
		var p95_index: int = clampi(int(ceil(feedback_latencies.size() * 0.95)) - 1, 0, feedback_latencies.size() - 1)
		p95 = feedback_latencies[p95_index]
	return {
		"input_to_feedback_frames_p95": p95,
		"empty_command_rate": float(empty_commands) / float(expected_commands) if expected_commands > 0 else 0.0,
		"control_group_recall_success": float(control_group_success) / float(control_group_total) if control_group_total > 0 else 1.0,
		"sample_count": _completed_events.size(),
	}


func get_completed_events() -> Array[Dictionary]:
	return _completed_events.duplicate(true)


func _append_jsonl(record: Dictionary) -> void:
	if not enabled:
		return
	var file: FileAccess = FileAccess.open(output_path, FileAccess.READ_WRITE)
	if file == null:
		file = FileAccess.open(output_path, FileAccess.WRITE)
	if file == null:
		push_warning("[FeelMetricsRecorder] Cannot open %s" % output_path)
		return
	file.seek_end()
	file.store_line(JSON.stringify(record))
	file.close()
