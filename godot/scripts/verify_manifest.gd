@tool
class_name VerifyManifest
extends RefCounted

## Godot 端 presentation_manifest.json 校验工具。
##
## 在编辑器中执行: var v = load("res://scripts/verify_manifest.gd").new(); v.run()
## 或从 game_view.gd _ready() 调用 VerifyManifest.run()

const MANIFEST_PATH := "res://resources/presentation_manifest.json"

var _errors: PackedStringArray = []
var _warnings: PackedStringArray = []


func run() -> bool:
	_errors.clear()
	_warnings.clear()
	print("\n=== VerifyManifest ===")

	var manifest := _load_manifest()
	if manifest.is_empty():
		_print_result()
		return false

	_check_required_keys(manifest)
	_check_building_visuals(manifest)
	_check_unit_visuals(manifest)
	_check_abstract_mappings(manifest)
	_check_rendering_params(manifest)

	_print_result()
	return _errors.is_empty()


# ─── Checks ────────────────────────────────────────────────────────────────────

func _check_required_keys(m: Dictionary) -> void:
	for k in ["building_visuals", "unit_visuals", "abstract_buildings", "abstract_units", "_rendering"]:
		if not m.has(k):
			_errors.append("missing top-level key: %s" % k)


func _check_building_visuals(m: Dictionary) -> void:
	var required := ["atlas_rect", "pivot", "health_bar_offset", "fallback",
					 "selection_ring_offset", "render_scale", "selection_radius", "race"]
	for bname: String in m.get("building_visuals", {}):
		var bdata: Dictionary = m["building_visuals"][bname]
		for k in required:
			if not bdata.has(k):
				_errors.append("building %s missing %s" % [bname, k])

		# atlas_rect format
		var ar: Array = bdata.get("atlas_rect", [])
		if ar.size() != 4 or not _all_numeric(ar):
			_errors.append("building %s atlas_rect bad: %s" % [bname, ar])
		else:
			_check_atlas_in_bounds(bname, ar, bdata.get("asset", ""))

		# positive values
		if bdata.get("render_scale", 0.0) <= 0.0:
			_errors.append("building %s render_scale <= 0" % bname)
		if bdata.get("selection_radius", 0.0) <= 0.0:
			_errors.append("building %s selection_radius <= 0" % bname)

		# fallback
		var fb: Dictionary = bdata.get("fallback", {})
		if not fb.has("atlas_rect") or not fb.has("render_scale"):
			_errors.append("building %s fallback incomplete" % bname)
		else:
			_check_asset_exists("building %s fallback" % bname, "")


func _check_unit_visuals(m: Dictionary) -> void:
	var required := ["pivot", "health_bar_offset", "fallback",
					 "selection_ring_offset", "render_scale", "selection_radius", "race"]
	for uname: String in m.get("unit_visuals", {}):
		var udata: Dictionary = m["unit_visuals"][uname]
		for k in required:
			if not udata.has(k):
				_errors.append("unit %s missing %s" % [uname, k])

		if udata.get("render_scale", 0.0) <= 0.0:
			_errors.append("unit %s render_scale <= 0" % uname)
		if udata.get("selection_radius", 0.0) <= 0.0:
			_errors.append("unit %s selection_radius <= 0" % uname)

		var fb: Dictionary = udata.get("fallback", {})
		if not fb.has("asset") or not fb.has("render_scale"):
			_errors.append("unit %s fallback incomplete" % uname)
		else:
			_check_asset_exists("unit %s fallback" % uname, fb.get("asset", ""))


func _check_abstract_mappings(m: Dictionary) -> void:
	var bvs: Dictionary = m.get("building_visuals", {})
	var uvs: Dictionary = m.get("unit_visuals", {})

	for owner: String in m.get("abstract_buildings", {}):
		for atype: String in m["abstract_buildings"][owner]:
			var sc_name: String = m["abstract_buildings"][owner][atype]
			if not bvs.has(sc_name):
				_errors.append("abstract_buildings %s/%s → %s not in building_visuals" % [owner, atype, sc_name])

	for owner: String in m.get("abstract_units", {}):
		for atype: String in m["abstract_units"][owner]:
			var sc_name: String = m["abstract_units"][owner][atype]
			if not uvs.has(sc_name):
				_errors.append("abstract_units %s/%s → %s not in unit_visuals" % [owner, atype, sc_name])


func _check_rendering_params(m: Dictionary) -> void:
	var r: Dictionary = m.get("_rendering", {})
	if r.is_empty():
		_errors.append("_rendering section empty")
		return

	# selection_ring
	var sr: Dictionary = r.get("selection_ring", {})
	if sr.is_empty():
		_errors.append("_rendering.selection_ring missing")
	elif sr.get("line_width", 0.0) <= 0.0:
		_errors.append("selection_ring line_width <= 0")
	if sr.get("segments", 0) < 8:
		_warnings.append("selection_ring segments < 8: %d" % sr.get("segments", 0))
	var sr_color: Array = sr.get("color", [])
	if sr_color.size() != 4:
		_errors.append("selection_ring color size != 4")

	# health_bar
	var hb: Dictionary = r.get("health_bar", {})
	if hb.is_empty():
		_errors.append("_rendering.health_bar missing")
	elif hb.get("height", 0.0) <= 0.0:
		_errors.append("health_bar height <= 0")


# ─── Helpers ────────────────────────────────────────────────────────────────────

func _load_manifest() -> Dictionary:
	if not FileAccess.file_exists(MANIFEST_PATH):
		_errors.append("manifest not found: %s" % MANIFEST_PATH)
		return {}
	var f := FileAccess.open(MANIFEST_PATH, FileAccess.READ)
	if not f:
		_errors.append("cannot open manifest")
		return {}
	var text := f.get_as_text()
	f.close()
	var json := JSON.new()
	if json.parse(text) != OK:
		_errors.append("manifest JSON parse error: %s" % json.get_error_message())
		return {}
	return json.data


func _check_atlas_in_bounds(label: String, atlas_rect: Array, asset_path: String) -> void:
	if atlas_rect.size() != 4:
		return
	var tex: Texture2D = null
	if asset_path != "" and ResourceLoader.exists(asset_path):
		tex = ResourceLoader.load(asset_path, "Texture2D") as Texture2D
	if tex == null:
		_warnings.append("%s: cannot load texture for atlas bounds check: %s" % [label, asset_path])
		return
	var tw := tex.get_width()
	var th := tex.get_height()
	var x := int(atlas_rect[0])
	var y := int(atlas_rect[1])
	var w := int(atlas_rect[2])
	var h := int(atlas_rect[3])
	if x + w > tw or y + h > th:
		_errors.append("%s: atlas_rect [%d,%d,%d,%d] exceeds texture [%dx%d]" % [label, x, y, w, h, tw, th])


func _check_asset_exists(label: String, res_path: String) -> void:
	if res_path == "":
		return
	if not res_path.begins_with("res://"):
		_warnings.append("%s: asset path missing res:// prefix: %s" % [label, res_path])
		return
	if not ResourceLoader.exists(res_path):
		# 可能是图片路径而非 Resource
		var file_path := res_path.trim_prefix("res://")
		if not FileAccess.file_exists(res_path):
			_warnings.append("%s: asset file not found: %s" % [label, res_path])


func _all_numeric(arr: Array) -> bool:
	for v in arr:
		if not v is int and not v is float:
			return false
	return true


func _print_result() -> void:
	if _errors.is_empty() and _warnings.is_empty():
		print("  ✅ OK — manifest valid")
	else:
		if not _warnings.is_empty():
			print("  ⚠ Warnings (%d):" % _warnings.size())
			for w in _warnings:
				print("    %s" % w)
		if not _errors.is_empty():
			print("  ❌ Errors (%d):" % _errors.size())
			for e in _errors:
				print("    %s" % e)
		print("  FAIL — %d error(s), %d warning(s)" % [_errors.size(), _warnings.size()])
