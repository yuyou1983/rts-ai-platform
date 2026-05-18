extends Control

## Main menu — bridge between player and SimCore gRPC backend.

var _replay_dialog: ConfirmationDialog
var _match_id_edit: LineEdit

func _ready() -> void:
	_build_replay_dialog()


func _on_start_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/game_view.tscn")


func _on_replay_pressed() -> void:
	_replay_dialog.popup_centered()


func _on_quit_pressed() -> void:
	get_tree().quit()


# ─── Replay Dialog ───────────────────────────────────────────
func _build_replay_dialog() -> void:
	_replay_dialog = ConfirmationDialog.new()
	_replay_dialog.title = "Watch Replay"
	_replay_dialog.min_size = Vector2i(400, 160)
	_replay_dialog.ok_button_text = "Load"
	_replay_dialog.confirmed.connect(_on_replay_confirmed)

	var vbox := VBoxContainer.new()
	_replay_dialog.add_child(vbox)

	var label := Label.new()
	label.text = "Enter Match ID:"
	vbox.add_child(label)

	_match_id_edit = LineEdit.new()
	_match_id_edit.placeholder_text = "e.g. tvz-seed42"
	_match_id_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vbox.add_child(_match_id_edit)

	# Pre-fill default
	_match_id_edit.text = "tvz-seed42"

	add_child(_replay_dialog)


func _on_replay_confirmed() -> void:
	var match_id := _match_id_edit.text.strip_edges()
	if match_id.is_empty():
		return
	# Store match_id in a global autoload so game_view can pick it up
	_replay_bridge(match_id)


func _replay_bridge(match_id: String) -> void:
	# Use SceneSwitcher metadata pattern: set meta before scene change
	Engine.set_meta("replay_match_id", match_id)
	get_tree().change_scene_to_file("res://scenes/game_view.tscn")