extends CanvasLayer

## Victory/Defeat screen overlay.
## Shown when the game ends (is_terminal == true from SimCore).
##
## Buttons: R=Restart, Q=Quit, W=Watch Replay

signal play_again
signal quit_game
signal watch_replay

var _result: String = ""  # "VICTORY" or "DEFEAT"
var _stats: Dictionary = {}
var _alpha: float = 0.0
var _player_id: int = 1

@onready var _panel: PanelContainer = $Panel
@onready var _title: Label = $Panel/VBox/Title
@onready var _stats_label: Label = $Panel/VBox/Stats
@onready var _btn_again: Button = $Panel/VBox/HBox/BtnAgain
@onready var _btn_quit: Button = $Panel/VBox/HBox/BtnQuit
@onready var _btn_replay: Button = $Panel/VBox/HBox/BtnReplay

func _ready() -> void:
	visible = false
	_btn_again.pressed.connect(func(): play_again.emit())
	_btn_quit.pressed.connect(func(): quit_game.emit())
	_btn_replay.pressed.connect(func(): watch_replay.emit())

func show_result(winner: int, player_id: int, stats: Dictionary) -> void:
	_player_id = player_id
	_result = "VICTORY" if winner == player_id else "DEFEAT"
	_stats = stats
	_title.text = _result
	if _result == "VICTORY":
		_title.add_theme_color_override("font_color", Color.GREEN)
	else:
		_title.add_theme_color_override("font_color", Color.RED)

	# Build stats text
	var lines: PackedStringArray = []

	# Game duration
	var tick_val: int = stats.get("tick", 0)
	var duration_sec: float = tick_val / 20.0  # tick_rate=20 → 20 ticks/sec
	var minutes: int = int(duration_sec) / 60
	var seconds: int = int(duration_sec) % 60
	lines.append("Game Time: %d:%02d (%d ticks)" % [minutes, seconds, tick_val])

	# KDA
	var kills_val: int = stats.get("kills", 0)
	var deaths_val: int = stats.get("losses", 0)
	lines.append("Kills: %d  |  Losses: %d" % [kills_val, deaths_val])

	# Resources gathered
	var mineral_val: int = stats.get("mineral_gathered", 0)
	var gas_val: int = stats.get("gas_gathered", 0)
	lines.append("Minerals Mined: %d  |  Gas Harvested: %d" % [mineral_val, gas_val])

	# APM estimate
	var apm_val: int = stats.get("apm", 0)
	if apm_val > 0:
		lines.append("APM: %d" % apm_val)
	elif duration_sec > 0:
		var total_actions: int = stats.get("total_actions", 0)
		var estimated_apm: int = int(total_actions / (duration_sec / 60.0))
		lines.append("APM: ~%d" % maxi(estimated_apm, 0))

	_stats_label.text = "\n".join(lines)
	_alpha = 0.0
	visible = true
	set_process(true)


func _process(delta: float) -> void:
	if _alpha < 1.0:
		_alpha = minf(_alpha + delta * 0.8, 1.0)
		_panel.modulate.a = _alpha


func _input(event: InputEvent) -> void:
	if not visible:
		return
	if event.is_action_pressed("ui_cancel"):
		quit_game.emit()
	elif event is InputEventKey and event.pressed:
		if event.keycode == KEY_R:
			play_again.emit()
		elif event.keycode == KEY_Q:
			quit_game.emit()
		elif event.keycode == KEY_W:
			watch_replay.emit()
