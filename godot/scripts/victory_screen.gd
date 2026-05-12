extends CanvasLayer

## Victory/Defeat screen overlay.
## Shown when the game ends (is_terminal == true from SimCore).

signal play_again
signal quit_game

var _result: String = ""  # "VICTORY" or "DEFEAT"
var _stats: Dictionary = {}
var _alpha: float = 0.0

@onready var _panel: Panel = $Panel
@onready var _title: Label = $Panel/VBox/Title
@onready var _stats_label: Label = $Panel/VBox/Stats
@onready var _btn_again: Button = $Panel/VBox/HBox/BtnAgain
@onready var _btn_quit: Button = $Panel/VBox/HBox/BtnQuit


func _ready() -> void:
	visible = false
	_btn_again.pressed.connect(func(): play_again.emit())
	_btn_quit.pressed.connect(func(): quit_game.emit())


func show_result(winner: int, player_id: int, stats: Dictionary) -> void:
	_result = "VICTORY" if winner == player_id else "DEFEAT"
	_stats = stats
	_title.text = _result
	if _result == "VICTORY":
		_title.add_theme_color_override("font_color", Color.GREEN)
	else:
		_title.add_theme_color_override("font_color", Color.RED)
	var tick_val: int = stats.get("tick", 0)
	var kills_val: int = stats.get("kills", 0)
	var mineral_val: int = stats.get("mineral_gathered", 0)
	_stats_label.text = "Tick: %d\nUnits killed: %d\nMinerals gathered: %d" % [tick_val, kills_val, mineral_val]
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
	elif event is InputEventKey and event.keycode == KEY_R:
		play_again.emit()