class_name CombatVisualController
extends Node

## Event-driven combat visual pipeline.
##
## Accepts authoritative combat events from SimCore, deduplicates them so
## HTTP-retry replays don't double-fire VFX, and dispatches visuals via
## VFXManager. Also exposes the current short-lived per-entity "action"
## (e.g. "attack") so GameView can pick the right animation frame.
##
## The controller is purely event-driven: it no longer infers combat
## activity from per-frame entity HP/shield deltas or attack cooldowns.

signal combat_event_emitted(event: Dictionary)

const VFX_MANAGER_PATH := "/root/VFXManager"

## Bounded dedup cache. event_id -> true. When the cache is full the oldest
## entries are evicted, protecting against HTTP-retry replay without leaking
## memory over a long session.
const SEEN_EVENT_MAX := 4096
var _seen_event_ids: Dictionary = {}
var _seen_event_order: Array = []  # insertion order, used for eviction

## Short-lived per-entity action with a decay timer.
## entity_id -> { "action": String, "expires_at_msec": int }
const ATTACK_ACTION_DECAY_MSEC := 300
var _entity_actions: Dictionary = {}

## Reference to VFXManager (resolved lazily, or injected by GameView).
var _vfx_manager: VFXManager = null

# ── Normalized event vocabulary dispatched to VFXManager.spawn_combat_event ──
const EVENT_ATTACK_STARTED := "attack_started"
const EVENT_PROJECTILE_FIRED := "projectile_fired"
const EVENT_HIT_CONFIRMED := "hit_confirmed"
const EVENT_SHIELD_HIT := "shield_hit"
const EVENT_UNIT_DIED := "unit_died"
const EVENT_BUILDING_DAMAGED := "building_damaged"
const EVENT_SPELL_RESOLVED := "spell_resolved"


## Inject the VFXManager explicitly. Used by GameView when the manager is a
## sibling node rather than living at /root/VFXManager.
func set_vfx_manager(vfx: VFXManager) -> void:
	_vfx_manager = vfx


## Main entry point: feed authoritative combat events from SimCore.
## Iterates events, dedupes by event_id, and dispatches VFX + signal.
func process_combat_events(events: Array) -> void:
	if events == null or events.is_empty():
		return
	for ev in events:
		if not ev is Dictionary:
			continue
		var eid: String = str(ev.get("event_id", ""))
		if eid != "" and _seen_event_ids.has(eid):
			continue
		if eid != "":
			_mark_seen(eid)
		_dispatch_event(ev)


## Returns "attack" if the entity has a recent attack_started action,
## "" otherwise (or if the action has decayed).
func current_action_for(entity_id: String) -> String:
	if entity_id == "" or not _entity_actions.has(entity_id):
		return ""
	var entry: Dictionary = _entity_actions[entity_id]
	if int(entry.get("expires_at_msec", 0)) <= _now_msec():
		_entity_actions.erase(entity_id)
		return ""
	return str(entry.get("action", ""))


## Clears the dedup cache and the per-entity action cache.
func clear_seen_events() -> void:
	_seen_event_ids.clear()
	_seen_event_order.clear()
	_entity_actions.clear()


func _get_vfx_manager() -> VFXManager:
	if _vfx_manager != null and is_instance_valid(_vfx_manager):
		return _vfx_manager
	_vfx_manager = get_node_or_null(VFX_MANAGER_PATH)
	return _vfx_manager


## Dispatch one (already-deduped) combat event to VFX + signal.
func _dispatch_event(ev: Dictionary) -> void:
	var event_type: String = str(ev.get("event_type", ""))
	match event_type:
		"attack_started":
			_handle_attack_started(ev)
		"impact_resolved":
			_handle_impact_resolved(ev)
		"unit_destroyed":
			_handle_unit_destroyed(ev)
		"projectile_spawned":
			_handle_projectile_spawned(ev)
		"spell_resolved":
			_handle_spell_resolved(ev)
		_:
			push_warning("[CombatVisualController] Unknown event_type: %s" % event_type)


func _handle_attack_started(ev: Dictionary) -> void:
	var attacker_id: String = str(ev.get("attacker_id", ""))
	if attacker_id != "":
		_entity_actions[attacker_id] = {
			"action": "attack",
			"expires_at_msec": _now_msec() + ATTACK_ACTION_DECAY_MSEC,
		}
	var source_pos := Vector2(float(ev.get("source_x", 0.0)), float(ev.get("source_y", 0.0)))
	var target_pos := Vector2(float(ev.get("target_x", source_pos.x)), float(ev.get("target_y", source_pos.y)))
	_emit({
		"event_type": EVENT_ATTACK_STARTED,
		"vfx_profile": _profile_for_event(ev),
		"source_pos": source_pos,
		"target_pos": target_pos,
		"owner": int(ev.get("owner", 0)),
		"weapon_id": str(ev.get("weapon_id", "")),
	})


func _handle_impact_resolved(ev: Dictionary) -> void:
	# Misses produce no impact VFX.
	if bool(ev.get("missed", false)):
		return
	var shield_damage: float = float(ev.get("shield_damage", 0.0))
	var is_splash: bool = bool(ev.get("is_splash", false))
	var target_pos := Vector2(float(ev.get("target_x", 0.0)), float(ev.get("target_y", 0.0)))
	var source_pos := Vector2(float(ev.get("source_x", target_pos.x)), float(ev.get("source_y", target_pos.y)))
	var final_damage: float = float(ev.get("final_damage", 0.0))
	# Splash impacts use an explosive profile when we have no explicit one.
	var profile := _profile_for_event(ev)
	if is_splash and profile == "":
		profile = "terran_explosive"
	var out := {
		"vfx_profile": profile,
		"source_pos": source_pos,
		"target_pos": target_pos,
		"owner": int(ev.get("owner", 0)),
		"damage": final_damage,
		"weapon_id": str(ev.get("weapon_id", "")),
		"is_splash": is_splash,
	}
	# shield_damage > 0 → shield hit; otherwise a regular health hit.
	if shield_damage > 0.0:
		out["event_type"] = EVENT_SHIELD_HIT
	else:
		out["event_type"] = EVENT_HIT_CONFIRMED
	_emit(out)


func _handle_unit_destroyed(ev: Dictionary) -> void:
	var target_pos := Vector2(float(ev.get("target_x", 0.0)), float(ev.get("target_y", 0.0)))
	_emit({
		"event_type": EVENT_UNIT_DIED,
		"vfx_profile": _profile_for_event(ev),
		"source_pos": target_pos,
		"target_pos": target_pos,
		"owner": int(ev.get("owner", 0)),
		"entity_id": str(ev.get("target_id", "")),
	})


func _handle_projectile_spawned(ev: Dictionary) -> void:
	var source_pos := Vector2(float(ev.get("source_x", 0.0)), float(ev.get("source_y", 0.0)))
	var target_pos := Vector2(float(ev.get("target_x", source_pos.x)), float(ev.get("target_y", source_pos.y)))
	_emit({
		"event_type": EVENT_PROJECTILE_FIRED,
		"vfx_profile": _profile_for_event(ev),
		"source_pos": source_pos,
		"target_pos": target_pos,
		"owner": int(ev.get("owner", 0)),
		"weapon_id": str(ev.get("weapon_id", "")),
	})


func _handle_spell_resolved(ev: Dictionary) -> void:
	var target_pos := Vector2(float(ev.get("target_x", 0.0)), float(ev.get("target_y", 0.0)))
	var source_pos := Vector2(float(ev.get("source_x", target_pos.x)), float(ev.get("source_y", target_pos.y)))
	_emit({
		"event_type": EVENT_SPELL_RESOLVED,
		"vfx_profile": _profile_for_event(ev),
		"source_pos": source_pos,
		"target_pos": target_pos,
		"owner": int(ev.get("owner", 0)),
		"spell_id": str(ev.get("spell_id", ev.get("weapon_id", ""))),
		"damage": float(ev.get("final_damage", 0.0)),
	})


## Emit a normalized combat event to the signal and to VFXManager (if present).
func _emit(out: Dictionary) -> void:
	combat_event_emitted.emit(out)
	var vfx := _get_vfx_manager()
	if vfx != null and is_instance_valid(vfx):
		vfx.spawn_combat_event(out)


## Record an event_id as seen, evicting the oldest entries when the cache is full.
func _mark_seen(eid: String) -> void:
	_seen_event_ids[eid] = true
	_seen_event_order.append(eid)
	if _seen_event_order.size() > SEEN_EVENT_MAX:
		var overflow: int = _seen_event_order.size() - SEEN_EVENT_MAX
		for _i in range(overflow):
			var old_id: String = _seen_event_order[0]
			_seen_event_order.pop_front()
			_seen_event_ids.erase(old_id)


func _now_msec() -> int:
	return Time.get_ticks_msec()


## Resolve a VFX profile name from an event's weapon_id hint. VFXManager
## falls back to default effects for unknown/empty profiles, so a miss here
## is always safe.
func _profile_for_event(ev: Dictionary) -> String:
	var weapon_id: String = str(ev.get("weapon_id", "")).to_lower()
	if weapon_id == "":
		return ""
	if weapon_id.find("flame") >= 0 or weapon_id.find("firebat") >= 0:
		return "terran_flame"
	if weapon_id.find("c10") >= 0 or weapon_id.find("rifle") >= 0 or weapon_id.find("ghost") >= 0:
		return "terran_ballistic"
	if weapon_id.find("tank") >= 0 or weapon_id.find("siege") >= 0 or weapon_id.find("arc") >= 0:
		return "terran_explosive"
	if weapon_id.find("vulture") >= 0 or weapon_id.find("grenade") >= 0:
		return "terran_ballistic"
	if weapon_id.find("melee") >= 0 or weapon_id.find("zergling") >= 0 or weapon_id.find("claw") >= 0:
		return "zerg_melee"
	if weapon_id.find("acid") >= 0 or weapon_id.find("hydra") >= 0 or weapon_id.find("spit") >= 0:
		return "zerg_acid"
	if weapon_id.find("spore") >= 0 or weapon_id.find("muta") >= 0:
		return "zerg_spore"
	if weapon_id.find("psi") >= 0 or weapon_id.find("zealot") >= 0 or weapon_id.find("dark") >= 0:
		return "protoss_psi"
	if weapon_id.find("phase") >= 0 or weapon_id.find("dragoon") >= 0:
		return "protoss_phase"
	return ""
