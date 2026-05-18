extends Control

## Overlay script that wires the replay control panel UI to a ReplayPlayer node.
## Expects a ReplayPlayer (or node with ReplayPlayer script) at /root/ReplayPlayer,
## or assign it via `player` before use.

const SPEEDS := [0.5, 1.0, 2.0, 4.0]
var _speed_index: int = 1  # start at 1x

@onready var _player: ReplayPlayer = get_node_or_null("/root/ReplayPlayer")

@onready var _slider: HSlider = $VBoxContainer/HSlider
@onready var _btn_play_pause: Button = $VBoxContainer/ButtonRow/BtnPlayPause
@onready var _speed_label: Label = $VBoxContainer/ButtonRow/SpeedLabel
@onready var _tick_label: Label = $VBoxContainer/ButtonRow/TickLabel
@onready var _match_id_edit: LineEdit = $VBoxContainer/MatchIdRow/MatchIdEdit


func _ready() -> void:
	if _player:
		_player.replay_tick.connect(_on_replay_tick)
		_player.replay_finished.connect(_on_replay_finished)


func set_player(player: ReplayPlayer) -> void:
	_player = player
	_player.replay_tick.connect(_on_replay_tick)
	_player.replay_finished.connect(_on_replay_finished)


# ─── UI Callbacks ─────────────────────────────────────────────

func _on_slider_value_changed(value: float) -> void:
	if not _player or _player.get_total_ticks() == 0:
		return
	var index := int(value / 100.0 * (_player.get_total_ticks() - 1))
	_player.seek_to(index)
	_update_tick_label()


func _on_start_pressed() -> void:
	if _player:
		_player.seek_to(0)
		_update_tick_label()


func _on_step_back_pressed() -> void:
	if _player:
		_player.step_backward()
		_update_tick_label()


func _on_play_pause_pressed() -> void:
	if not _player:
		return
	if _player._play_state == ReplayPlayer.PlayState.PLAYING:
		_player.pause()
		_btn_play_pause.text = "▶"
	else:
		_player.play()
		_btn_play_pause.text = "⏸"


func _on_step_fwd_pressed() -> void:
	if _player:
		_player.step_forward()
		_update_tick_label()


func _on_end_pressed() -> void:
	if _player and _player.get_total_ticks() > 0:
		_player.seek_to(_player.get_total_ticks() - 1)
		_update_tick_label()


func _on_speed_clicked(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_speed_index = (_speed_index + 1) % SPEEDS.size()
		var new_speed: float = SPEEDS[_speed_index]
		if _player:
			_player.set_speed(new_speed)
		_speed_label.text = "%gx" % new_speed


func _on_load_replay_pressed() -> void:
	var match_id := _match_id_edit.text.strip_edges()
	if match_id.is_empty():
		return
	# Delegate to GrpcBridge to fetch replay data
	var bridge: GrpcBridge = get_node_or_null("/root/GrpcBridge")
	if bridge:
		bridge.fetch_replay(match_id)


# ─── ReplayPlayer Callbacks ──────────────────────────────────

func _on_replay_tick(_tick_data: Dictionary) -> void:
	_update_tick_label()


func _on_replay_finished() -> void:
	_btn_play_pause.text = "▶"


func _update_tick_label() -> void:
	if _player:
		_tick_label.text = "%d/%d" % [_player.get_current_tick(), _player.get_total_ticks()]