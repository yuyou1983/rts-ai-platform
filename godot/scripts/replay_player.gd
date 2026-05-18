class_name ReplayPlayer
extends Node

signal replay_tick(tick_data: Dictionary)
signal replay_finished()

enum PlayState { STOPPED, PLAYING, PAUSED }

var _ticks: Array = []
var _current_index: int = 0
var _play_state: PlayState = PlayState.STOPPED
var _playback_speed: float = 1.0
var _tick_timer: Timer


func _ready() -> void:
	_tick_timer = Timer.new()
	_tick_timer.one_shot = false
	_tick_timer.timeout.connect(_advance_tick)
	add_child(_tick_timer)
	_tick_timer.stop()


func load_replay(data: Dictionary) -> void:
	_ticks = data.get("ticks", [])
	_current_index = 0
	_play_state = PlayState.STOPPED
	_tick_timer.stop()
	# Show first frame
	if _ticks.size() > 0:
		replay_tick.emit(_ticks[0])


func play() -> void:
	if _ticks.is_empty():
		return
	_play_state = PlayState.PLAYING
	_tick_timer.wait_time = 0.05 / _playback_speed  # 20 tps base
	_tick_timer.start()


func pause() -> void:
	_play_state = PlayState.PAUSED
	_tick_timer.stop()


func step_forward() -> void:
	if _current_index < _ticks.size() - 1:
		_current_index += 1
		replay_tick.emit(_ticks[_current_index])


func step_backward() -> void:
	if _current_index > 0:
		_current_index -= 1
		replay_tick.emit(_ticks[_current_index])


func seek_to(index: int) -> void:
	index = clampi(index, 0, _ticks.size() - 1)
	_current_index = index
	replay_tick.emit(_ticks[_current_index])


func set_speed(speed: float) -> void:
	_playback_speed = speed
	if _play_state == PlayState.PLAYING:
		_tick_timer.wait_time = 0.05 / _playback_speed


func get_progress() -> float:
	if _ticks.is_empty():
		return 0.0
	return float(_current_index) / float(_ticks.size() - 1)


func get_current_tick() -> int:
	return _current_index


func get_total_ticks() -> int:
	return _ticks.size()


func _advance_tick() -> void:
	if _current_index < _ticks.size() - 1:
		_current_index += 1
		replay_tick.emit(_ticks[_current_index])
	else:
		_play_state = PlayState.STOPPED
		_tick_timer.stop()
		replay_finished.emit()