class_name InputIntentRouter
extends RefCounted

## Converts pointer context into an RTS command intent. This class is pure:
## it never submits commands or reads scene state.

enum Intent {
	NONE,
	MOVE,
	ATTACK,
	ATTACK_MOVE,
	GATHER,
	BUILD,
	RALLY,
}


func resolve_right_click(
		has_units: bool,
		has_buildings: bool,
		has_workers: bool,
		clicked: Dictionary,
		local_owner: int = 1
) -> Intent:
	if has_buildings and not has_units:
		return Intent.RALLY
	if clicked.is_empty():
		return Intent.MOVE if has_units else Intent.NONE

	var clicked_type: String = str(clicked.get("type", ""))
	var clicked_owner: int = int(clicked.get("owner", 0))
	if clicked_owner != 0 and clicked_owner != local_owner and clicked_type != "resource":
		return Intent.ATTACK if has_units else Intent.NONE
	if has_workers and clicked_type == "resource":
		return Intent.GATHER
	return Intent.MOVE if has_units else Intent.NONE


static func intent_name(intent: Intent) -> String:
	match intent:
		Intent.MOVE:
			return "move"
		Intent.ATTACK:
			return "attack"
		Intent.ATTACK_MOVE:
			return "attack_move"
		Intent.GATHER:
			return "gather"
		Intent.BUILD:
			return "build"
		Intent.RALLY:
			return "rally"
		_:
			return "none"
