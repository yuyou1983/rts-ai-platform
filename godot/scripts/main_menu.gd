extends Control

## Main menu — bridge between player and SimCore gRPC backend.

var _replay_dialog: ConfirmationDialog
var _match_id_edit: LineEdit
var _difficulty_button: OptionButton

func _ready() -> void:
	_build_replay_dialog()
	_build_difficulty_selector()


func _on_start_pressed() -> void:
	# Store difficulty so game_view/bridge can pick it up
	var diff := _get_selected_difficulty()
	Engine.set_meta("ai_difficulty", diff)
	get_tree().change_scene_to_file("res://scenes/game_view.tscn")


func _on_replay_pressed() -> void:
	_replay_dialog.popup_centered()


func _on_quit_pressed() -> void:
	get_tree().quit()


# ─── Difficulty Selector ─────────────────────────────────────
func _build_difficulty_selector() -> void:
	_difficulty_button = OptionButton.new()
	_difficulty_button.add_item("Easy 🟢", 0)
	_difficulty_button.add_item("Medium 🟡", 1)
	_difficulty_button.add_item("Hard 🔴", 2)
	_difficulty_button.selected = 1  # default medium
	# Place it in the menu — look for existing VBox or create one
	var container := _find_or_create_vbox()
	# Insert before Start button (at top or after title)
	var label := Label.new()
	label.text = "AI Difficulty:"
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", 16)
	container.add_child(label)
	container.add_child(_difficulty_button)


func _find_or_create_vbox() -> VBoxContainer:
	# Try to find existing VBoxContainer in the menu scene
	for child in get_children():
		if child is VBoxContainer:
			return child
		for grandchild in child.get_children():
			if grandchild is VBoxContainer:
				return grandchild
	# Fallback: create new one
	var vbox := VBoxContainer.new()
	add_child(vbox)
	return vbox


func _get_selected_difficulty() -> String:
	if not _difficulty_button:
		return "medium"
	match _difficulty_button.selected:
		0: return "easy"
		1: return "medium"
		2: return "hard"
		_: return "medium"


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