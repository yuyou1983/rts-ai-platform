class_name VFXManager
extends Node2D

## Lightweight data-driven 2D VFX layer for combat feedback.
## Effects are intentionally short and high-contrast, matching RTS readability.

const CATALOG_PATH := "res://resources/vfx/vfx_catalog.json"
const WEAPON_VISUAL_CATALOG_PATH := "res://resources/vfx/weapon_visual_catalog.json"
const FEEL_CONFIG_PATH := "res://resources/feel/control_feel_config.json"
const PRESENTATION_MANIFEST_PATH := "res://resources/presentation_manifest.json"

var _catalog: Dictionary = {}
var _weapon_visuals: Dictionary = {}
var _effects: Array[Dictionary] = []
var _projectiles: Array[Dictionary] = []
var _textures: Dictionary = {}
var _max_active_effects: int = 64
var _max_death_effects: int = 16
var _max_projectiles: int = 32
var _profiles: Dictionary = {}
var _unit_profiles: Dictionary = {}  # Maps unit_name → profile name (loaded from presentation manifest)
var _death_count: int = 0

# ── Effect defaults (loaded from feel config) ──
var _eff_lifetime: float = 0.2
var _eff_radius: float = 0.5
var _eff_scale: float = 1.0
var _eff_rings: int = 1
var _eff_color: Array = [1.0, 1.0, 1.0, 1.0]
var _eff_secondary_color: Array = [1.0, 0.2, 0.1, 0.7]
var _eff_priority: int = 1

# ── Tracer defaults (loaded from feel config) ──
var _tr_default_lifetime: float = 0.08
var _tr_arc_lifetime: float = 0.25
var _tr_beam_lifetime: float = 0.25
var _tr_cone_lifetime: float = 0.15
var _tr_default_color: Array = [1.0, 1.0, 1.0, 1.0]

# ── Other tunables ──
var _muzzle_offset: float = 0.55
var _shell_impact_dmg_threshold: float = 18.0


func _ready() -> void:
	z_index = 20
	_load_catalog()
	_load_weapon_visual_catalog()
	_load_feel_config()
	_load_unit_profiles()


func _load_weapon_visual_catalog() -> void:
	if not FileAccess.file_exists(WEAPON_VISUAL_CATALOG_PATH):
		push_warning("[VFXManager] Missing weapon visual catalog: %s" % WEAPON_VISUAL_CATALOG_PATH)
		_weapon_visuals = {}
		return
	var text := FileAccess.get_file_as_string(WEAPON_VISUAL_CATALOG_PATH)
	var parsed = JSON.parse_string(text)
	if parsed is Dictionary:
		# Top-level may include a "_meta" key; store only weapon entries.
		for key in parsed:
			if key.begins_with("_"):
				continue
			_weapon_visuals[key] = parsed[key]
	else:
		push_warning("[VFXManager] Invalid weapon visual catalog JSON: %s" % WEAPON_VISUAL_CATALOG_PATH)
		_weapon_visuals = {}


func _process(delta: float) -> void:
	# Age and cull point effects
	for i in range(_effects.size() - 1, -1, -1):
		var effect: Dictionary = _effects[i]
		effect["age"] = float(effect.get("age", 0.0)) + delta
		if float(effect.get("age", 0.0)) >= float(effect.get("lifetime", _eff_lifetime)):
			if effect.get("is_death", false):
				_death_count = maxi(_death_count - 1, 0)
			_effects.remove_at(i)
		else:
			_effects[i] = effect

	# Age and cull projectile tracers
	for i in range(_projectiles.size() - 1, -1, -1):
		var tracer: Dictionary = _projectiles[i]
		tracer["age"] = float(tracer.get("age", 0.0)) + delta
		var lifetime: float = float(tracer.get("lifetime", _tr_default_lifetime))
		if float(tracer["age"]) >= lifetime:
			_projectiles.remove_at(i)
		else:
			tracer["progress"] = float(tracer["age"]) / lifetime
			_projectiles[i] = tracer

	if (not _effects.is_empty()) or (not _projectiles.is_empty()):
		queue_redraw()


func _draw() -> void:
	for effect in _effects:
		_draw_effect(effect)
	for projectile in _projectiles:
		_draw_tracer(projectile)


func spawn_attack(unit_name: String, owner: int, from_pos: Vector2, target_pos: Vector2 = Vector2.INF, vfx_profile: String = "") -> void:
	var effect_name: String = ""
	if vfx_profile != "":
		effect_name = _lookup_profile_effect(vfx_profile, "attack", "muzzle_flash_small")
	else:
		effect_name = _lookup_unit_effect(unit_name, "attack", "muzzle_flash_small")
	var pos := from_pos
	var tracer_from := from_pos
	if target_pos != Vector2.INF:
		var dir := target_pos - from_pos
		if dir.length_squared() > 0.001:
			pos = from_pos + dir.normalized() * _muzzle_offset
			tracer_from = from_pos + dir.normalized() * _muzzle_offset
	_spawn_effect(effect_name, pos, owner, false)
	# Spawn tracer after muzzle flash
	spawn_tracer(vfx_profile if vfx_profile != "" else _unit_profiles.get(unit_name, ""), owner, tracer_from, target_pos)


func spawn_hit(unit_name: String, owner: int, pos: Vector2, damage: float = 0.0, vfx_profile: String = "") -> void:
	var fallback := "shield_hit" if _is_protoss_like(unit_name) else "acid_hit" if _is_zerg_like(unit_name) else "hit_spark"
	var effect_name: String = ""
	if vfx_profile != "":
		effect_name = _lookup_profile_effect(vfx_profile, "hit", fallback)
	else:
		effect_name = _lookup_unit_effect(unit_name, "hit", fallback)
	var is_death := false
	if damage >= _shell_impact_dmg_threshold and effect_name == "hit_spark":
		effect_name = "shell_impact"
	var effect := _make_effect(effect_name, pos, owner, is_death)
	_enforce_cap(effect)
	_effects.append(effect)
	queue_redraw()


func spawn_death(unit_name: String, entity_type: String, owner: int, pos: Vector2, vfx_profile: String = "") -> void:
	var key := "building" if entity_type == "building" else unit_name
	var fallback := "building_burst" if entity_type == "building" else "hit_spark"
	var effect_name: String = ""
	if vfx_profile != "":
		effect_name = _lookup_profile_effect(vfx_profile, "death", fallback)
	else:
		effect_name = _lookup_unit_effect(key, "death", fallback)
	var is_death := true
	if effect_name.to_lower().find("burst") >= 0 or effect_name.to_lower().find("death") >= 0:
		is_death = true
	_spawn_effect(effect_name, pos, owner, is_death)


func spawn_combat_event(event: Dictionary) -> void:
	## Accept a normalized combat event from CombatVisualController
	## and dispatch to the appropriate visual effect.
	var profile_name: String = str(event.get("vfx_profile", "none"))
	var event_type: String = str(event.get("event_type", ""))
	var source_pos: Vector2 = event.get("source_pos", Vector2.ZERO)
	var target_pos: Vector2 = event.get("target_pos", Vector2.ZERO)
	var owner: int = int(event.get("owner", 0))
	var damage: float = float(event.get("damage", 0.0))

	# Map event_type → effect
	match event_type:
		"attack_started":
			var effect_name: String = _lookup_profile_effect(profile_name, "attack", "muzzle_flash_small")
			# Apply muzzle offset from profile timing
			var profile: Dictionary = _catalog.get("profiles", {}).get(profile_name, {})
			var muzzle_offset: float = float(profile.get("muzzle_offset_tiles", _muzzle_offset))
			var dir := target_pos - source_pos
			var muzzle_pos := source_pos
			if dir.length_squared() > 0.001:
				muzzle_pos = source_pos + dir.normalized() * muzzle_offset
			_spawn_effect(effect_name, muzzle_pos, owner, false)
			# Also spawn tracer for the attack
			spawn_tracer(profile_name, owner, muzzle_pos, target_pos)

		"projectile_fired":
			# For ballistic projectiles, the "fire" event creates a visible tracer
			var profile: Dictionary = _catalog.get("profiles", {}).get(profile_name, {})
			var muzzle_offset: float = float(profile.get("muzzle_offset_tiles", _muzzle_offset))
			var dir := target_pos - source_pos
			var fire_pos := source_pos
			if dir.length_squared() > 0.001:
				fire_pos = source_pos + dir.normalized() * muzzle_offset
			spawn_tracer(profile_name, owner, fire_pos, target_pos)

		"hit_confirmed":
			var fallback := "hit_spark"
			var effect_name: String = _lookup_profile_effect(profile_name, "hit", fallback)
			# Apply impact offset from profile timing
			var profile: Dictionary = _catalog.get("profiles", {}).get(profile_name, {})
			var impact_offset: float = float(profile.get("impact_offset_tiles", 0.0))
			var hit_pos := target_pos
			if impact_offset != 0.0:
				var dir := source_pos - target_pos
				if dir.length_squared() > 0.001:
					hit_pos = target_pos + dir.normalized() * impact_offset
			var is_death := false
			var effect := _make_effect(effect_name, hit_pos, owner, is_death)
			# Override priority from profile if available
			var priority: int = int(profile.get("priority", _eff_priority))
			effect["priority"] = priority
			_enforce_cap(effect)
			_effects.append(effect)
			queue_redraw()

		"shield_hit":
			var effect_name: String = _lookup_profile_effect(profile_name, "hit", "shield_hit")
			var profile: Dictionary = _catalog.get("profiles", {}).get(profile_name, {})
			var priority: int = int(profile.get("priority", _eff_priority))
			var effect := _make_effect(effect_name, target_pos, owner, false)
			effect["priority"] = priority
			_enforce_cap(effect)
			_effects.append(effect)
			queue_redraw()

		"unit_died":
			var profile: Dictionary = _catalog.get("profiles", {}).get(profile_name, {})
			var fallback := "hit_spark"
			var effect_name: String = _lookup_profile_effect(profile_name, "death", fallback)
			var is_death := true
			var priority: int = int(profile.get("priority", _eff_priority))
			var effect := _make_effect(effect_name, target_pos, owner, is_death)
			effect["priority"] = priority
			_enforce_cap(effect)
			_effects.append(effect)
			queue_redraw()

		"building_damaged":
			var effect_name: String = _lookup_profile_effect(profile_name, "hit", "shell_impact")
			var profile: Dictionary = _catalog.get("profiles", {}).get(profile_name, {})
			var priority: int = int(profile.get("priority", _eff_priority))
			var effect := _make_effect(effect_name, target_pos, owner, false)
			effect["priority"] = priority
			_enforce_cap(effect)
			_effects.append(effect)
			queue_redraw()

		_:  # Unknown event types silently ignored
			pass


func spawn_weapon_event(event: Dictionary, visual: Dictionary) -> void:
	## Dispatch VFX for a single combat event using a weapon-visual catalog entry.
	## `event` carries source_pos/target_pos/owner/event_type/damage/shielded just like
	## spawn_combat_event. `visual` is the per-weapon entry from
	## weapon_visual_catalog.json (animation_action, launch_effect, projectile_style,
	## impact_effect, shield_impact_effect, death_effect, audio_cue, priority).
	## Falls back to the legacy vfx_profile system when `visual` is empty.
	if visual.is_empty():
		spawn_combat_event(event)
		return

	var event_type: String = str(event.get("event_type", ""))
	var source_pos: Vector2 = event.get("source_pos", Vector2.ZERO)
	var target_pos: Vector2 = event.get("target_pos", Vector2.ZERO)
	var owner: int = int(event.get("owner", 0))
	var damage: float = float(event.get("damage", 0.0))
	var shielded: bool = bool(event.get("shielded", false))
	var projectile_style: String = str(visual.get("projectile_style", "none"))
	var priority: int = int(visual.get("priority", _eff_priority))

	# Compute muzzle position once for launch/tracer styles.
	var muzzle_pos := source_pos
	var dir := target_pos - source_pos
	if dir.length_squared() > 0.001:
		muzzle_pos = source_pos + dir.normalized() * _muzzle_offset

	match event_type:
		"attack_started", "projectile_fired", "launch":
			var launch_effect: String = str(visual.get("launch_effect", "muzzle_flash_small"))
			_spawn_effect(launch_effect, muzzle_pos, owner, false)
			_spawn_projectile_for_style(projectile_style, visual, owner, muzzle_pos, target_pos)

		"hit_confirmed":
			var impact_name: String
			if shielded:
				impact_name = str(visual.get("shield_impact_effect", "shield_hit"))
			else:
				impact_name = str(visual.get("impact_effect", "hit_spark"))
			if damage >= _shell_impact_dmg_threshold and impact_name == "hit_spark":
				impact_name = "shell_impact"
			var effect := _make_effect(impact_name, target_pos, owner, false)
			effect["priority"] = priority
			_enforce_cap(effect)
			_effects.append(effect)
			queue_redraw()

		"shield_hit":
			var shield_name: String = str(visual.get("shield_impact_effect", "shield_hit"))
			var effect := _make_effect(shield_name, target_pos, owner, false)
			effect["priority"] = priority
			_enforce_cap(effect)
			_effects.append(effect)
			queue_redraw()

		"unit_died":
			var death_name: String = str(visual.get("death_effect", "hit_spark"))
			var effect := _make_effect(death_name, target_pos, owner, true)
			effect["priority"] = priority
			_enforce_cap(effect)
			_effects.append(effect)
			queue_redraw()

		"spell_resolved":
			# Spell launch effect at the target tile (where the spell manifests).
			var spell_launch: String = str(visual.get("launch_effect", "psi_storm_cast"))
			_spawn_effect(spell_launch, target_pos, owner, false)
			_spawn_projectile_for_style(projectile_style, visual, owner, target_pos, target_pos)

		# Unknown event types silently ignored (legacy parity)


func get_weapon_visual(weapon_id: String) -> Dictionary:
	## Return the weapon-visual catalog entry for `weapon_id`, or an empty dict.
	return _weapon_visuals.get(weapon_id, {})


func _spawn_projectile_for_style(style: String, visual: Dictionary, owner: int, from_pos: Vector2, to_pos: Vector2) -> void:
	## Spawn the visible tracer/projectile appropriate to a weapon's projectile_style.
	## All 12 catalog styles are handled; "none" produces no tracer.
	match style:
		"hitscan_tracer":
			_append_tracer(from_pos, to_pos, "flicker", _tr_default_lifetime, [1.0, 0.9, 0.5, 0.9], owner)

		"flame_cone":
			_append_tracer(from_pos, to_pos, "cone", _tr_cone_lifetime, [1.0, 0.4, 0.1, 0.7], owner)

		"grenade_arc":
			_append_tracer(from_pos, to_pos, "arc", _tr_arc_lifetime, [1.0, 0.8, 0.4, 0.85], owner)

		"tank_shell":
			# Heavier, longer arc with a bigger impact flash at the muzzle.
			_append_tracer(from_pos, to_pos, "arc", _tr_arc_lifetime * 1.2, [1.0, 0.6, 0.2, 0.8], owner)
			_spawn_effect("shell_impact", from_pos, owner, false)

		"needle_spine":
			_append_tracer(from_pos, to_pos, "arc", _tr_arc_lifetime, [0.5, 1.0, 0.2, 0.8], owner)

		"glave_chain":
			# Chain weapon: primary arc plus a secondary bounce tracer toward an
			# offset point to suggest the glave ricocheting.
			_append_tracer(from_pos, to_pos, "arc", _tr_arc_lifetime, [0.6, 1.0, 0.4, 0.85], owner)
			var bounce_to := to_pos + Vector2(0.6, -0.3)
			_append_tracer(to_pos, bounce_to, "arc", _tr_arc_lifetime * 0.6, [0.5, 0.9, 0.3, 0.7], owner)

		"phase_orb":
			_append_tracer(from_pos, to_pos, "beam", _tr_beam_lifetime, [0.5, 0.8, 1.0, 0.9], owner)

		"storm_area":
			# Area spell: no tracer, instead a lingering tick effect at the target tile.
			_spawn_effect(str(visual.get("impact_effect", "psi_storm_tick")), to_pos, owner, false)

		"scarab_tracking":
			# Tracking ground projectile: slow arc toward target.
			_append_tracer(from_pos, to_pos, "arc", _tr_arc_lifetime * 1.3, [1.0, 0.7, 0.3, 0.85], owner)

		"melee_slash":
			_append_tracer(from_pos, to_pos, "slash", _tr_default_lifetime, [1.0, 1.0, 1.0, 0.9], owner)

		"heavy_melee_arc":
			# Bigger melee swing with an extra impact spark at the target.
			_append_tracer(from_pos, to_pos, "slash", _tr_default_lifetime * 1.5, [0.5, 1.0, 0.3, 0.9], owner)
			_spawn_effect(str(visual.get("impact_effect", "kaiser_impact")), to_pos, owner, false)

		"none":
			pass  # No projectile / tracer for weapons with no visible delivery.

		_:
			# Unknown style falls back to a generic hitscan tracer.
			_append_tracer(from_pos, to_pos, "flicker", _tr_default_lifetime, _tr_default_color, owner)


func _append_tracer(from_pos: Vector2, to_pos: Vector2, style: String, lifetime: float, color_array: Array, owner: int) -> void:
	## Helper: build and append a tracer dict directly (bypasses profile lookup).
	var tracer: Dictionary = {
		"from": from_pos,
		"to": to_pos,
		"age": 0.0,
		"lifetime": lifetime,
		"style": style,
		"color": _array_to_color(color_array),
		"owner": owner,
		"progress": 0.0,
	}
	_projectiles.append(tracer)
	if _projectiles.size() >= _max_projectiles:
		_projectiles.remove_at(0)
	queue_redraw()


func spawn_tracer(vfx_profile: String, owner: int, from_pos: Vector2, to_pos: Vector2) -> void:
	var profiles: Dictionary = _catalog.get("profiles", {})
	if not profiles.has(vfx_profile):
		return
	var profile: Dictionary = profiles[vfx_profile]
	var tracer_style: String = str(profile.get("tracer_style", "none"))
	if tracer_style.casecmp_to("none") == 0:
		return
	var tracer_color = profile.get("tracer_color", _tr_default_color)

	# Determine lifetime based on style
	var lifetime: float = _tr_default_lifetime
	if tracer_style.casecmp_to("arc") == 0:
		lifetime = _tr_arc_lifetime
	elif tracer_style.casecmp_to("beam") == 0:
		lifetime = _tr_beam_lifetime
	elif tracer_style.casecmp_to("cone") == 0:
		lifetime = _tr_cone_lifetime

	var tracer: Dictionary = {
		"from": from_pos,
		"to": to_pos,
		"age": 0.0,
		"lifetime": lifetime,
		"style": tracer_style,
		"color": _array_to_color(tracer_color),
		"owner": owner,
		"progress": 0.0,
	}
	_projectiles.append(tracer)
	# Enforce projectile cap
	if _projectiles.size() >= _max_projectiles:
		_projectiles.remove_at(0)


func clear() -> void:
	_effects.clear()
	_projectiles.clear()
	_death_count = 0
	queue_redraw()


func clear_projectiles() -> void:
	_projectiles.clear()
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


func _load_feel_config() -> void:
	# Defaults are already set on the member vars; we only override when
	# the config file is present and valid.
	if not FileAccess.file_exists(FEEL_CONFIG_PATH):
		return
	var text := FileAccess.get_file_as_string(FEEL_CONFIG_PATH)
	var parsed = JSON.parse_string(text)
	if not parsed is Dictionary:
		return

	# ── vfx_limits ──
	var limits: Dictionary = parsed.get("vfx_limits", {})
	_max_active_effects = int(limits.get("max_active_effects", _max_active_effects))
	_max_death_effects = int(limits.get("max_death_effects", _max_death_effects))
	_max_projectiles = int(limits.get("max_projectiles", _max_projectiles))

	# ── vfx_defaults ──
	var defaults: Dictionary = parsed.get("vfx_defaults", {})

	var effect: Dictionary = defaults.get("effect", {})
	_eff_lifetime = float(effect.get("lifetime", _eff_lifetime))
	_eff_radius = float(effect.get("radius", _eff_radius))
	_eff_scale = float(effect.get("scale", _eff_scale))
	_eff_rings = int(effect.get("rings", _eff_rings))
	_eff_color = effect.get("color", _eff_color)
	_eff_secondary_color = effect.get("secondary_color", _eff_secondary_color)
	_eff_priority = int(effect.get("priority", _eff_priority))

	var tracer: Dictionary = defaults.get("tracer", {})
	_tr_default_lifetime = float(tracer.get("default_lifetime", _tr_default_lifetime))
	_tr_arc_lifetime = float(tracer.get("arc_lifetime", _tr_arc_lifetime))
	_tr_beam_lifetime = float(tracer.get("beam_lifetime", _tr_beam_lifetime))
	_tr_cone_lifetime = float(tracer.get("cone_lifetime", _tr_cone_lifetime))
	_tr_default_color = tracer.get("default_color", _tr_default_color)

	_muzzle_offset = float(defaults.get("muzzle_offset", _muzzle_offset))
	_shell_impact_dmg_threshold = float(defaults.get("shell_impact_damage_threshold", _shell_impact_dmg_threshold))


func _load_unit_profiles() -> void:
	if not FileAccess.file_exists(PRESENTATION_MANIFEST_PATH):
		_unit_profiles = {}
		return
	var text := FileAccess.get_file_as_string(PRESENTATION_MANIFEST_PATH)
	var parsed = JSON.parse_string(text)
	if not parsed is Dictionary:
		_unit_profiles = {}
		return
	# Extract from unit_visuals
	var unit_visuals: Dictionary = parsed.get("unit_visuals", {})
	for unit_name in unit_visuals:
		var entry: Dictionary = unit_visuals[unit_name]
		if entry.has("vfx_profile"):
			_unit_profiles[unit_name] = str(entry["vfx_profile"])
	# Extract from building_visuals
	var building_visuals: Dictionary = parsed.get("building_visuals", {})
	for building_name in building_visuals:
		var entry: Dictionary = building_visuals[building_name]
		if entry.has("vfx_profile"):
			_unit_profiles[building_name] = str(entry["vfx_profile"])


func _lookup_unit_effect(unit_name: String, action: String, fallback: String) -> String:
	var unit_effects: Dictionary = _catalog.get("unit_effects", {})
	var mapping: Dictionary = unit_effects.get(unit_name, {})
	return str(mapping.get(action, fallback))


func _lookup_profile_effect(profile_name: String, action: String, fallback: String) -> String:
	var profiles: Dictionary = _catalog.get("profiles", {})
	if not profiles.has(profile_name):
		return fallback
	var profile: Dictionary = profiles[profile_name]
	if not profile.has(action):
		return fallback
	return str(profile[action])


func _spawn_effect(effect_name: String, pos: Vector2, owner: int, is_death: bool = false) -> void:
	var effect := _make_effect(effect_name, pos, owner, is_death)
	_enforce_cap(effect)
	_effects.append(effect)
	queue_redraw()


func _enforce_cap(effect: Dictionary) -> void:
	# Check death cap
	if effect.get("is_death", false):
		_death_count += 1
		while _death_count > _max_death_effects and _effects.size() > 0:
			var oldest_death_idx := -1
			var oldest_death_age := -1.0
			for i in range(_effects.size()):
				if _effects[i].get("is_death", false):
					var age := float(_effects[i].get("age", 0.0))
					if oldest_death_idx == -1 or age > oldest_death_age:
						oldest_death_idx = i
						oldest_death_age = age
			if oldest_death_idx == -1:
				break
			_effects.remove_at(oldest_death_idx)
			_death_count -= 1
	# Check active cap
	while _effects.size() >= _max_active_effects:
		# Find oldest lowest-priority effect
		var lowest_priority: int = int(_effects[0].get("priority", _eff_priority))
		for e in _effects:
			var p: int = int(e.get("priority", _eff_priority))
			if p < lowest_priority:
				lowest_priority = p
		# Among lowest priority, find oldest
		var remove_idx := -1
		var oldest_age := -1.0
		for i in range(_effects.size()):
			var e: Dictionary = _effects[i]
			if int(e.get("priority", _eff_priority)) == lowest_priority:
				var age := float(e.get("age", 0.0))
				if age > oldest_age:
					oldest_age = age
					remove_idx = i
		if remove_idx == -1:
			remove_idx = 0
		if _effects[remove_idx].get("is_death", false):
			_death_count = maxi(_death_count - 1, 0)
		_effects.remove_at(remove_idx)


func _make_effect(effect_name: String, pos: Vector2, owner: int, is_death: bool = false) -> Dictionary:
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
		"lifetime": float(spec.get("lifetime", _eff_lifetime)),
		"radius": float(spec.get("radius", _eff_radius)),
		"scale": float(spec.get("scale", _eff_scale)),
		"rings": int(spec.get("rings", _eff_rings)),
		"texture": str(spec.get("texture", "")),
		"color": _array_to_color(spec.get("color", _eff_color)),
		"secondary_color": _array_to_color(spec.get("secondary_color", _eff_secondary_color)),
		"priority": int(spec.get("priority", _eff_priority)),
		"is_death": is_death,
	}


func _draw_effect(effect: Dictionary) -> void:
	var lifetime := maxf(float(effect.get("lifetime", _eff_lifetime)), 0.01)
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


func _draw_tracer(tracer: Dictionary) -> void:
	var lifetime := maxf(float(tracer.get("lifetime", _tr_default_lifetime)), 0.001)
	var t := clampf(float(tracer.get("progress", 0.0)), 0.0, 1.0)
	var alpha := 1.0 - t
	var from_pos: Vector2 = tracer.get("from", Vector2.ZERO)
	var to_pos: Vector2 = tracer.get("to", Vector2.ZERO)
	var color: Color = tracer.get("color", Color.WHITE)
	color.a *= alpha
	var style: String = str(tracer.get("style", "none"))

	if style.casecmp_to("flicker") == 0:
		# Instant hit-scan line
		draw_line(from_pos, to_pos, color, 2.0, true)
	elif style.casecmp_to("slash") == 0:
		# Melee arc
		draw_arc(from_pos, 0.4, 0.0, PI * 0.7, 8, color, 2.5, true)
	elif style.casecmp_to("flash") == 0:
		# Psi flash — expanding circle at midpoint
		var mid := from_pos + (to_pos - from_pos) * 0.5
		draw_circle(mid, 0.3 * alpha, color)
	elif style.casecmp_to("arc") == 0:
		# 3-segment polyline with upward arc
		var mid := (from_pos + to_pos) * 0.5 + Vector2(0, -0.5)
		var points := PackedVector2Array([from_pos, mid, to_pos])
		draw_polyline(points, color, 1.5, true)
	elif style.casecmp_to("beam") == 0:
		# Phase beam — thick line
		draw_line(from_pos, to_pos, color, 3.0, true)
	elif style.casecmp_to("cone") == 0:
		# Shotgun cone — 3 short lines fanning from from_pos
		var dir := (to_pos - from_pos).normalized()
		var base_angle := dir.angle()
		var length := 0.6
		# Center line
		draw_line(from_pos, from_pos + dir * length, color, 2.0, true)
		# +15°
		var dir_plus := Vector2.RIGHT.rotated(base_angle + deg_to_rad(15.0))
		draw_line(from_pos, from_pos + dir_plus * length, color, 2.0, true)
		# -15°
		var dir_minus := Vector2.RIGHT.rotated(base_angle - deg_to_rad(15.0))
		draw_line(from_pos, from_pos + dir_minus * length, color, 2.0, true)
	elif style.casecmp_to("none") == 0:
		pass
	# Unknown styles silently ignored


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
