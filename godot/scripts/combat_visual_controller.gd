class_name CombatVisualController
extends Node

## Derives combat events from per-frame entity state deltas and dispatches
## them to VFXManager. Event source priority:
##   1. SimCore explicit fields (attack_cooldown, attack_target_id, shield)
##   2. HP / shield delta + attack_target inference
##   3. Command input feedback fallback (never fakes a hit confirmation)

signal combat_event_emitted(event: Dictionary)

const VFX_MANAGER_PATH := "/root/VFXManager"
const CATALOG_PATH := "res://resources/vfx/vfx_catalog.json"

## Per-entity previous-frame snapshot: { hp, shield, pos, attack_target_id, attack_cooldown }
var _prev_state: Dictionary = {}
## VFX profile cache: entity_id → profile_name
var _profile_cache: Dictionary = {}
## Reference to VFXManager (resolved lazily)
var _vfx_manager: VFXManager = null
## Catalog profiles (loaded once)
var _catalog_profiles: Dictionary = {}

# ── Event type constants ──
const EVENT_ATTACK_STARTED := "attack_started"
const EVENT_PROJECTILE_FIRED := "projectile_fired"
const EVENT_HIT_CONFIRMED := "hit_confirmed"
const EVENT_SHIELD_HIT := "shield_hit"
const EVENT_UNIT_DIED := "unit_died"
const EVENT_BUILDING_DAMAGED := "building_damaged"


func _ready() -> void:
	_load_catalog_profiles()


## Main entry point: feed current entity array, derive events, dispatch VFX.
func process_entities(entities: Array[Dictionary]) -> void:
	var vfx := _get_vfx_manager()
	if vfx == null:
		return

	var current_map: Dictionary = {}
	var old_ids: Array = _prev_state.keys()
	var removed_ids: Array = []

	# Build current entity map
	for e in entities:
		var eid: String = str(e.get("id", ""))
		if eid == "":
			continue
		current_map[eid] = e

	# Detect removed entities (died this frame)
	for old_id in old_ids:
		if not current_map.has(old_id):
			removed_ids.append(old_id)

	# Process each current entity for delta events
	for eid in current_map:
		var cur: Dictionary = current_map[eid]
		var prev: Dictionary = _prev_state.get(eid, {})
		_derive_events(eid, cur, prev, vfx)

	# Process removed entities (death events)
	for dead_id in removed_ids:
		var prev: Dictionary = _prev_state.get(dead_id, {})
		_emit_death_event(dead_id, prev, vfx)

	# Update prev_state for next frame
	_prev_state.clear()
	for e in entities:
		var eid: String = str(e.get("id", ""))
		if eid != "":
			_prev_state[eid] = _snapshot(e)


## Invalidate caches when presentation manifest reloads.
func invalidate_profile_cache() -> void:
	_profile_cache.clear()


func _get_vfx_manager() -> VFXManager:
	if _vfx_manager != null and is_instance_valid(_vfx_manager):
		return _vfx_manager
	_vfx_manager = get_node_or_null(VFX_MANAGER_PATH)
	return _vfx_manager


func _load_catalog_profiles() -> void:
	if not FileAccess.file_exists(CATALOG_PATH):
		_catalog_profiles = {}
		return
	var text := FileAccess.get_file_as_string(CATALOG_PATH)
	var parsed = JSON.parse_string(text)
	if parsed is Dictionary:
		_catalog_profiles = parsed.get("profiles", {})
	else:
		_catalog_profiles = {}


## Snapshot relevant fields from an entity dict.
func _snapshot(e: Dictionary) -> Dictionary:
	return {
		"hp": float(e.get("health", 0.0)),
		"shield": float(e.get("shield", 0.0)),
		"px": float(e.get("px", 0.0)),
		"py": float(e.get("py", 0.0)),
		"attack_target_id": str(e.get("attack_target_id", "")),
		"attack_cooldown": float(e.get("attack_cooldown", 0.0)),
		"type": str(e.get("type", e.get("entity_type", ""))),
		"owner": int(e.get("owner", 0)),
	}


## Derive and dispatch combat events for one entity by comparing
## current snapshot against previous snapshot.
func _derive_events(eid: String, cur: Dictionary, prev: Dictionary, vfx: VFXManager) -> void:
	if prev.is_empty():
		# First frame: no delta to compute, just record state.
		return

	var cur_hp: float = float(cur.get("health", 0.0))
	var prev_hp: float = prev.get("hp", 0.0)
	var cur_shield: float = float(cur.get("shield", 0.0))
	var prev_shield: float = prev.get("shield", 0.0)
	var cur_target: String = str(cur.get("attack_target_id", ""))
	var prev_target: String = prev.get("attack_target_id", "")
	var cur_cooldown: float = float(cur.get("attack_cooldown", 0.0))
	var prev_cooldown: float = prev.get("attack_cooldown", 0.0)

	var profile_name: String = _resolve_profile(eid, cur)
	var source_pos := Vector2(float(cur.get("px", 0.0)), float(cur.get("py", 0.0)))

	# ── Priority 1: SimCore explicit fields ──

	# Attack started: cooldown just started (went from <=0 to >0) with a target
	if cur_cooldown > 0.0 and prev_cooldown <= 0.0 and cur_target != "":
		var target_pos := _find_target_pos(cur_target)
		_dispatch(vfx, {
			"event_type": EVENT_ATTACK_STARTED,
			"vfx_profile": profile_name,
			"source_pos": source_pos,
			"target_pos": target_pos,
			"owner": int(cur.get("owner", 0)),
		})

	# Projectile fired: cooldown just crossed 0 (from >0 to <=0) with target
	#   This is the moment the sim "fires" the projectile.
	if prev_cooldown > 0.0 and cur_cooldown <= 0.0 and cur_target != "":
		var target_pos := _find_target_pos(cur_target)
		_dispatch(vfx, {
			"event_type": EVENT_PROJECTILE_FIRED,
			"vfx_profile": profile_name,
			"source_pos": source_pos,
			"target_pos": target_pos,
			"owner": int(cur.get("owner", 0)),
		})

	# New attack target acquired (target changed from empty/non-matching)
	if cur_target != "" and cur_target != prev_target:
		var target_pos := _find_target_pos(cur_target)
		_dispatch(vfx, {
			"event_type": EVENT_ATTACK_STARTED,
			"vfx_profile": profile_name,
			"source_pos": source_pos,
			"target_pos": target_pos,
			"owner": int(cur.get("owner", 0)),
		})

	# ── Priority 2: HP / shield delta inference ──

	# Shield hit: shield decreased but HP unchanged
	if cur_shield < prev_shield and cur_hp >= prev_hp and prev_shield > 0.0:
		_dispatch(vfx, {
			"event_type": EVENT_SHIELD_HIT,
			"vfx_profile": profile_name,
			"source_pos": source_pos,
			"target_pos": source_pos,
			"damage": prev_shield - cur_shield,
			"owner": int(cur.get("owner", 0)),
		})

	# Hit confirmed: HP decreased
	if cur_hp < prev_hp and prev_hp > 0.0:
		var dmg: float = prev_hp - cur_hp
		var entity_type: String = str(cur.get("type", cur.get("entity_type", "")))
		if entity_type == "building":
			_dispatch(vfx, {
				"event_type": EVENT_BUILDING_DAMAGED,
				"vfx_profile": profile_name,
				"source_pos": source_pos,
				"target_pos": source_pos,
				"damage": dmg,
				"owner": int(cur.get("owner", 0)),
			})
		else:
			# Distinguish shield_hit from hit_confirmed:
			# If shield also dropped, shield_hit was already emitted above.
			# If HP dropped without shield change, this is a regular hit.
			if cur_shield >= prev_shield:
				_dispatch(vfx, {
					"event_type": EVENT_HIT_CONFIRMED,
					"vfx_profile": profile_name,
					"source_pos": source_pos,
					"target_pos": source_pos,
					"damage": dmg,
					"owner": int(cur.get("owner", 0)),
				})

	# ── Priority 3: No further fallback — command input is handled by
	#    input_feedback_controller, not here. We never fake a hit. ──


## Emit a death event for a removed entity.
func _emit_death_event(dead_id: String, prev: Dictionary, vfx: VFXManager) -> void:
	if prev.is_empty():
		return
	var profile_name: String = _resolve_profile(dead_id, prev)
	var death_pos := Vector2(float(prev.get("px", 0.0)), float(prev.get("py", 0.0)))
	var entity_type: String = str(prev.get("type", ""))
	_dispatch(vfx, {
		"event_type": EVENT_UNIT_DIED if entity_type != "building" else EVENT_BUILDING_DAMAGED,
		"vfx_profile": profile_name,
		"source_pos": death_pos,
		"target_pos": death_pos,
		"owner": int(prev.get("owner", 0)),
	})


## Dispatch a normalized combat event to VFXManager and emit signal.
func _dispatch(vfx: VFXManager, event: Dictionary) -> void:
	combat_event_emitted.emit(event)
	vfx.spawn_combat_event(event)


## Resolve the VFX profile name for an entity. Uses cache then falls back
## to presentation manifest lookup.
func _resolve_profile(eid: String, entity: Dictionary) -> String:
	if _profile_cache.has(eid):
		return _profile_cache[eid]

	var entity_type: String = str(entity.get("type", entity.get("entity_type", "")))
	var unit_name: String = _resolve_unit_name(entity)

	# Try catalog profiles directly
	if _catalog_profiles.has(unit_name):
		_profile_cache[eid] = unit_name
		return unit_name

	# Try presentation manifest
	var manifest_path := "res://resources/presentation_manifest.json"
	if FileAccess.file_exists(manifest_path):
		var text := FileAccess.get_file_as_string(manifest_path)
		var parsed = JSON.parse_string(text)
		if parsed is Dictionary:
			var section_key := "building_visuals" if entity_type == "building" else "unit_visuals"
			var section: Dictionary = parsed.get(section_key, {})
			var entry: Dictionary = section.get(unit_name, {})
			if entry.has("vfx_profile"):
				var pname: String = str(entry["vfx_profile"])
				_profile_cache[eid] = pname
				return pname

	# Fallback: try common profiles by entity type
	var fallback: String = _fallback_profile(entity_type, entity)
	_profile_cache[eid] = fallback
	return fallback


func _resolve_unit_name(entity: Dictionary) -> String:
	var entity_type: String = str(entity.get("type", entity.get("entity_type", "")))
	if entity_type == "building":
		return "building"
	var visual_id: String = str(entity.get("unit_type", entity.get("type", "")))
	if visual_id == "":
		visual_id = str(entity.get("entity_type", ""))
	return visual_id


func _fallback_profile(entity_type: String, entity: Dictionary) -> String:
	match entity_type:
		"building":
			return "building_hit"
		_:
			var unit_name: String = _resolve_unit_name(entity).to_lower()
			if unit_name.find("marine") >= 0 or unit_name.find("ghost") >= 0 or unit_name.find("vulture") >= 0:
				return "terran_ballistic"
			if unit_name.find("tank") >= 0 or unit_name.find("goliath") >= 0:
				return "terran_explosive"
			if unit_name.find("firebat") >= 0:
				return "terran_flame"
			if unit_name.find("zergling") >= 0:
				return "zerg_melee"
			if unit_name.find("hydra") >= 0:
				return "zerg_acid"
			if unit_name.find("mutalisk") >= 0 or unit_name.find("spore") >= 0:
				return "zerg_spore"
			if unit_name.find("zealot") >= 0 or unit_name.find("dark") >= 0:
				return "protoss_psi"
			if unit_name.find("dragoon") >= 0:
				return "protoss_phase"
			return "terran_ballistic"  # safe default


## Find the world position of a target entity by its ID.
func _find_target_pos(target_id: String) -> Vector2:
	# Look in prev_state first (target may still be there)
	if _prev_state.has(target_id):
		var ps: Dictionary = _prev_state[target_id]
		return Vector2(float(ps.get("px", 0.0)), float(ps.get("py", 0.0)))
	return Vector2.ZERO
