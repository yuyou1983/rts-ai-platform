class_name VFXManager
extends Node2D

## Lightweight data-driven 2D VFX layer for combat feedback.
## Effects are intentionally short and high-contrast, matching RTS readability.

const CATALOG_PATH := "res://resources/vfx/vfx_catalog.json"

var _catalog: Dictionary = {}
var _effects: Array[Dictionary] = []
var _textures: Dictionary = {}


func _ready() -> void:
	z_index = 20
	_load_catalog()


func _process(delta: float) -> void:
	for i in range(_effects.size() - 1, -1, -1):
		var effect: Dictionary = _effects[i]
		effect["age"] = float(effect.get("age", 0.0)) + delta
		if float(effect.get("age", 0.0)) >= float(effect.get("lifetime", 0.2)):
			_effects.remove_at(i)
		else:
			_effects[i] = effect
	if not _effects.is_empty():
		queue_redraw()


func _draw() -> void:
	for effect in _effects:
		_draw_effect(effect)


func spawn_attack(unit_name: String, owner: int, from_pos: Vector2, target_pos: Vector2 = Vector2.INF) -> void:
	var effect_name := _lookup_unit_effect(unit_name, "attack", "muzzle_flash_small")
	var pos := from_pos
	if target_pos != Vector2.INF:
		var dir := target_pos - from_pos
		if dir.length_squared() > 0.001:
			pos = from_pos + dir.normalized() * 0.55
	_spawn_effect(effect_name, pos, owner)


func spawn_hit(unit_name: String, owner: int, pos: Vector2, damage: float = 0.0) -> void:
	var fallback := "shield_hit" if _is_protoss_like(unit_name) else "acid_hit" if _is_zerg_like(unit_name) else "hit_spark"
	var effect_name := _lookup_unit_effect(unit_name, "hit", fallback)
	var effect := _make_effect(effect_name, pos, owner)
	if damage >= 18.0 and effect_name == "hit_spark":
		effect = _make_effect("shell_impact", pos, owner)
	_effects.append(effect)
	queue_redraw()


func spawn_death(unit_name: String, entity_type: String, owner: int, pos: Vector2) -> void:
	var key := "building" if entity_type == "building" else unit_name
	var fallback := "building_burst" if entity_type == "building" else "hit_spark"
	var effect_name := _lookup_unit_effect(key, "death", fallback)
	_spawn_effect(effect_name, pos, owner)


func clear() -> void:
	_effects.clear()
	queue_redraw()


func _load_catalog() -> void:
	if not FileAccess.file_exists(CATALOG_PATH):
		push_warning("[VFXManager] Missing catalog: %s" % CATALOG_PATH)
		_catalog = {}
		return
	var text := FileAccess.get_file_as_string(CATALOG_PATH)
	var parsed = JSON.parse_string(text)
	if parsed is Dictionary:
		_catalog = parsed
	else:
		push_warning("[VFXManager] Invalid catalog JSON: %s" % CATALOG_PATH)
		_catalog = {}


func _lookup_unit_effect(unit_name: String, action: String, fallback: String) -> String:
	var unit_effects: Dictionary = _catalog.get("unit_effects", {})
	var key := unit_name
	if not unit_effects.has(key):
		key = _normalize_unit_key(unit_name)
	var mapping: Dictionary = unit_effects.get(key, {})
	return str(mapping.get(action, fallback))


func _normalize_unit_key(unit_name: String) -> String:
	var lower := unit_name.to_lower()
	if lower.find("marine") >= 0 or lower == "soldier":
		return "Marine"
	if lower.find("ghost") >= 0 or lower == "scout":
		return "Ghost"
	if lower.find("tank") >= 0:
		return "Tank"
	if lower.find("zerg") >= 0:
		return "Zergling"
	if lower.find("hydra") >= 0:
		return "Hydralisk"
	if lower.find("zealot") >= 0:
		return "Zealot"
	if lower == "building" or lower.find("building") >= 0:
		return "building"
	return unit_name


func _spawn_effect(effect_name: String, pos: Vector2, owner: int) -> void:
	_effects.append(_make_effect(effect_name, pos, owner))
	queue_redraw()


func _make_effect(effect_name: String, pos: Vector2, owner: int) -> Dictionary:
	var defaults: Dictionary = _catalog.get("defaults", {})
	var effects: Dictionary = _catalog.get("effects", {})
	var spec: Dictionary = defaults.duplicate()
	var override: Dictionary = effects.get(effect_name, {})
	for key in override:
		spec[key] = override[key]
	return {
		"name": effect_name,
		"pos": pos,
		"owner": owner,
		"age": 0.0,
		"lifetime": float(spec.get("lifetime", 0.2)),
		"radius": float(spec.get("radius", 0.5)),
		"scale": float(spec.get("scale", 1.0)),
		"rings": int(spec.get("rings", 1)),
		"texture": str(spec.get("texture", "")),
		"color": _array_to_color(spec.get("color", [1.0, 1.0, 1.0, 1.0])),
		"secondary_color": _array_to_color(spec.get("secondary_color", [1.0, 0.2, 0.1, 0.7])),
	}


func _draw_effect(effect: Dictionary) -> void:
	var lifetime := maxf(float(effect.get("lifetime", 0.2)), 0.01)
	var t := clampf(float(effect.get("age", 0.0)) / lifetime, 0.0, 1.0)
	var alpha := 1.0 - t
	var pos: Vector2 = effect.get("pos", Vector2.ZERO)
	var radius := float(effect.get("radius", 0.5)) * (0.65 + t * 0.75)
	var color: Color = effect.get("color", Color.WHITE)
	var secondary: Color = effect.get("secondary_color", Color.ORANGE)
	color.a *= alpha
	secondary.a *= alpha * 0.85

	var texture_path := str(effect.get("texture", ""))
	var texture := _get_texture(texture_path)
	if texture:
		var base_size := texture.get_size() * float(effect.get("scale", 0.03)) * (0.85 + t * 0.35)
		var rect := Rect2(pos - base_size * 0.5, base_size)
		draw_texture_rect(texture, rect, false, color)

	var rings := int(effect.get("rings", 1))
	for ring in rings:
		var ring_t := clampf(t + float(ring) * 0.16, 0.0, 1.0)
		var ring_alpha := alpha * (1.0 - float(ring) * 0.22)
		var ring_color := secondary if ring % 2 == 1 else color
		ring_color.a *= ring_alpha
		draw_arc(pos, radius * (1.0 + ring_t + float(ring) * 0.25), 0.0, TAU, 18, ring_color, 0.045, true)


func _get_texture(path: String) -> Texture2D:
	if path.is_empty():
		return null
	if _textures.has(path):
		return _textures[path]
	var loaded := load(path)
	if loaded is Texture2D:
		_textures[path] = loaded
		return loaded
	push_warning("[VFXManager] Could not load texture: %s" % path)
	_textures[path] = null
	return null


func _array_to_color(value) -> Color:
	if value is Array and value.size() >= 4:
		return Color(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
	return Color.WHITE


func _is_zerg_like(unit_name: String) -> bool:
	var lower := unit_name.to_lower()
	return lower.find("zerg") >= 0 or lower.find("hydra") >= 0 or lower.find("mutalisk") >= 0


func _is_protoss_like(unit_name: String) -> bool:
	var lower := unit_name.to_lower()
	return lower.find("zealot") >= 0 or lower.find("dragoon") >= 0 or lower.find("probe") >= 0
