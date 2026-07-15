extends SceneTree

## Headless smoke test: validates that vfx_catalog.json exists and contains
## all six required combat profiles.

const VFX_CATALOG_PATH := "res://resources/vfx/vfx_catalog.json"

func _init() -> void:
	var ok := true
	var text := FileAccess.get_file_as_string(VFX_CATALOG_PATH)
	if text == "":
		push_error("missing vfx catalog")
		ok = false
	var parsed = JSON.parse_string(text)
	if not (parsed is Dictionary):
		push_error("vfx catalog is not a dictionary")
		ok = false
	else:
		var profiles: Dictionary = parsed.get("profiles", {})
		for required in ["terran_ballistic", "terran_explosive", "terran_flame", "zerg_melee", "zerg_acid", "protoss_psi"]:
			if not profiles.has(required):
				push_error("missing profile: %s" % required)
				ok = false
	quit(0 if ok else 1)
