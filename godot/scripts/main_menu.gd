extends Control

## Main menu — bridge between player and SimCore gRPC backend.

var _replay_dialog: ConfirmationDialog
var _match_id_edit: LineEdit
var _difficulty_button: OptionButton
var _p1_race_button: OptionButton
var _p2_race_button: OptionButton

func _ready() -> void:
	_build_replay_dialog()
	_build_difficulty_selector()
	_build_race_selectors()


func _on_start_pressed() -> void:
	# Store difficulty so game_view/bridge can pick it up
	var diff := _get_selected_difficulty()
	Engine.set_meta("ai_difficulty", diff)
	# Store race selections
	Engine.set_meta("p1_race", _get_selected_p1_race())
	Engine.set_meta("p2_race", _get_selected_p2_race())
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
	var container := _find_or_create_vbox()
	var label := Label.new()
	label.text = "AI Difficulty:"
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", 16)
	container.add_child(label)
	container.add_child(_difficulty_button)


# ─── Race Selectors ──────────────────────────────────────────
func _build_race_selectors() -> void:
	var container := _find_or_create_vbox()

	# ── Player 1 Race ──
	_p1_race_button = OptionButton.new()
	_p1_race_button.add_item("Terran 🔵", 0)
	_p1_race_button.add_item("Zerg 🟣", 1)
	_p1_race_button.add_item("Protoss 🟡", 2)
	_p1_race_button.selected = 0  # default terran
	var p1_label := Label.new()
	p1_label.text = "Your Race (P1):"
	p1_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	p1_label.add_theme_font_size_override("font_size", 16)
	container.add_child(p1_label)
	container.add_child(_p1_race_button)

	# ── Player 2 (AI) Race ──
	_p2_race_button = OptionButton.new()
	_p2_race_button.add_item("Terran 🔵", 0)
	_p2_race_button.add_item("Zerg 🟣", 1)
	_p2_race_button.add_item("Protoss 🟡", 2)
	_p2_race_button.selected = 0  # default terran
	var p2_label := Label.new()
	p2_label.text = "Enemy Race (P2):"
	p2_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	p2_label.add_theme_font_size_override("font_size", 16)
	container.add_child(p2_label)
	container.add_child(_p2_race_button)


func _get_selected_p1_race() -> String:
	if not _p1_race_button:
		return "terran"
	match _p1_race_button.selected:
		0: return "terran"
		1: return "zerg"
		2: return "protoss"
		_: return "terran"


func _get_selected_p2_race() -> String:
	if not _p2_race_button:
		return "terran"
	match _p2_race_button.selected:
		0: return "terran"
		1: return "zerg"
		2: return "protoss"
		_: return "terran"


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
