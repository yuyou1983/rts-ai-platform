extends Control

## Main menu — bridge between player and SimCore gRPC backend.


func _on_start_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/game_view.tscn")


func _on_replay_pressed() -> void:
	# TODO(#M1): implement replay file picker
	push_warning("Replay mode not yet implemented")


func _on_quit_pressed() -> void:
	get_tree().quit()