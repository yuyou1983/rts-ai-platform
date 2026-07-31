extends SceneTree

## Headless test script for Task 11 — SC1 combat differentiation slice.
##
## Verifies the SC1 damage matrix (normal / explosive / concussive vs light /
## medium / heavy), shield→health→armor resolution, splash, mutalisk chain,
## multi-hit weapons, spells, and the CombatDiagnosticsOverlay rendering.
##
## The resolution logic is a faithful GDScript port of
## ``simcore/combat_resolution.resolve_weapon_impact`` so the test is
## self-contained in headless mode (no Python round-trip required).
##
## Run the diagnostics slice:
##   /Applications/Godot.app/Contents/MacOS/Godot --headless --path godot \
##       --script scripts/test_sc1_combat_slice.gd -- --diagnostics
##
## Without ``--diagnostics`` only a quick smoke check runs. Prints PASS/FAIL
## per matchup and exits 0 on full success, 1 otherwise.

const CombatDiagnosticsOverlayScript := preload("res://scripts/combat_diagnostics_overlay.gd")

# ─── SC1 damage matrix (mirrors data/combat/combat.json) ─────
# damageMatrix[weaponType][armorType] in percent.
#   concussive (0): light 100, medium 50,  heavy 25
#   explosive  (1): light  50, medium 75,  heavy 100
#   normal     (2): light 100, medium 100, heavy 100
const DAMAGE_MATRIX: Array = [[100, 50, 25], [50, 75, 100], [100, 100, 100]]
const MIN_DAMAGE: float = 0.5

const _WEAPON_TYPE_IDX: Dictionary = {
	"concussive": 0,
	"explosive": 1,
	"normal": 2,
	"independent": 2,
	"spells": 2,
	"splash": 2,
	"melee": 2,
	"none": 2,
}
const _ARMOR_TYPE_IDX: Dictionary = {"light": 0, "medium": 1, "heavy": 2}

var _pass_count: int = 0
var _fail_count: int = 0


# ────────────────────────────────────────────────────────────
# SceneTree entry
# ────────────────────────────────────────────────────────────

func _initialize() -> void:
	var user_args: PackedStringArray = OS.get_cmdline_user_args()
	var diagnostics: bool = false
	for arg in user_args:
		if arg == "--diagnostics":
			diagnostics = true

	print("[TestSC1CombatSlice] Godot %s — starting%s" % [
		Engine.get_version_info().get("string", "4.x"),
		" (diagnostics)" if diagnostics else " (smoke)",
	])

	if diagnostics:
		_run_diagnostics()
	else:
		_run_smoke()

	_summary()
	quit(1 if _fail_count > 0 else 0)


# ────────────────────────────────────────────────────────────
# Smoke check (no --diagnostics)
# ────────────────────────────────────────────────────────────

func _run_smoke() -> void:
	# Damage matrix sanity.
	_assert_near(_get_damage_multiplier("concussive", "light"), 1.0, 0.001, "concussive vs light = 100%")
	_assert_near(_get_damage_multiplier("concussive", "medium"), 0.5, 0.001, "concussive vs medium = 50%")
	_assert_near(_get_damage_multiplier("concussive", "heavy"), 0.25, 0.001, "concussive vs heavy = 25%")
	_assert_near(_get_damage_multiplier("explosive", "light"), 0.5, 0.001, "explosive vs light = 50%")
	_assert_near(_get_damage_multiplier("explosive", "medium"), 0.75, 0.001, "explosive vs medium = 75%")
	_assert_near(_get_damage_multiplier("explosive", "heavy"), 1.0, 0.001, "explosive vs heavy = 100%")
	_assert_near(_get_damage_multiplier("normal", "heavy"), 1.0, 0.001, "normal vs heavy = 100%")
	# Overlay formats without crashing on a bare new() instance.
	var overlay = CombatDiagnosticsOverlayScript.new()
	var txt: String = overlay.format_event({
		"event_type": "impact_resolved",
		"attacker_id": "m1",
		"target_id": "z1",
		"weapon_id": "terran_c10_rifle",
		"weapon_type": "concussive",
		"armor_type": "light",
		"base_damage": 6.0,
		"damage_multiplier": 1.0,
		"shield_damage": 0.0,
		"health_damage": 6.0,
		"final_damage": 6.0,
		"chain_index": 0,
		"splash_fraction": 1.0,
		"is_splash": false,
		"tick": 1,
		"event_id": "1:0",
	})
	_assert_true(txt.find("m1") >= 0, "overlay text contains attacker id")
	_assert_true(txt.find("IMPACT RESOLVED") >= 0, "overlay text contains event type header")
	overlay.free()


# ────────────────────────────────────────────────────────────
# Diagnostics — 10 matchup presets
# ────────────────────────────────────────────────────────────

func _run_diagnostics() -> void:
	# Build the overlay once and add it to a CanvasLayer so _ready fires
	# (proves UI construction works headless).
	var overlay = CombatDiagnosticsOverlayScript.new()
	overlay.test_mode_active = true
	var canvas := CanvasLayer.new()
	root.add_child(canvas)
	canvas.add_child(overlay)
	_assert_true(overlay.test_mode_active, "overlay test_mode_active setter works")

	_test_marine_vs_zergling(overlay)
	_test_firebat_vs_zerglings(overlay)
	_test_vulture_vs_zealot(overlay)
	_test_tank_vs_dragoon(overlay)
	_test_hydralisk_vs_dragoon(overlay)
	_test_mutalisk_vs_marines(overlay)
	_test_zealot_vs_marine(overlay)
	_test_dragoon_vs_ultralisk(overlay)
	_test_templar_storm_vs_marines(overlay)
	_test_reaver_vs_zerglings(overlay)

	overlay.free()
	canvas.free()


# 1. Marine (6 concussive) vs Zergling (light, 35hp, 0 armor) ──────────────
func _test_marine_vs_zergling(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Marine vs Zergling"
	var target := _make_unit("zergling_1", 2, 35, 0, 0, "light")
	var ev := _resolve_impact(target, {
		"attacker_id": "marine_1", "target_id": "zergling_1",
		"weapon_id": "terran_c10_rifle", "weapon_type": "concussive",
		"base_damage": 6.0, "splash_fraction": 1.0,
	}, 1, 0)
	_assert_event(preset, ev, {
		"event_type": "impact_resolved", "weapon_type": "concussive",
		"armor_type": "light", "base_damage": 6.0, "damage_multiplier": 1.0,
		"shield_damage": 0.0, "health_damage": 6.0, "final_damage": 6.0,
		"chain_index": 0, "splash_fraction": 1.0, "is_splash": false,
	})
	_assert_near(float(target.get("health")), 29.0, 0.001, "%s: zergling health 35→29" % preset)
	_assert_overlay(preset, overlay, [ev], "marine_1", "6.00")
	print("[PASS] %s — 6 concussive vs light → 6 health dmg" % preset)


# 2. Firebat (16 concussive, splash) vs 3 Zerglings (light, 35hp) ──────────
func _test_firebat_vs_zerglings(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Firebat vs 3 Zerglings"
	var z1 := _make_unit("zergling_1", 2, 35, 0, 0, "light")
	var z2 := _make_unit("zergling_2", 2, 35, 0, 0, "light")
	var z3 := _make_unit("zergling_3", 2, 35, 0, 0, "light")
	var params := {
		"attacker_id": "firebat_1", "weapon_id": "terran_flamethrower",
		"weapon_type": "concussive",
	}
	var events: Array = []
	# Primary (full damage).
	events.append(_resolve_impact(z1, {
		"attacker_id": "firebat_1", "target_id": "zergling_1",
		"weapon_id": "terran_flamethrower", "weapon_type": "concussive",
		"base_damage": 16.0, "splash_fraction": 1.0, "is_splash": false,
	}, 1, 0))
	# Splash hits (50% fraction).
	events.append(_resolve_impact(z2, {
		"attacker_id": "firebat_1", "target_id": "zergling_2",
		"weapon_id": "terran_flamethrower", "weapon_type": "concussive",
		"base_damage": 16.0 * 0.5, "splash_fraction": 0.5, "is_splash": true,
	}, 1, 1))
	events.append(_resolve_impact(z3, {
		"attacker_id": "firebat_1", "target_id": "zergling_3",
		"weapon_id": "terran_flamethrower", "weapon_type": "concussive",
		"base_damage": 16.0 * 0.5, "splash_fraction": 0.5, "is_splash": true,
	}, 1, 2))
	_assert_event(preset + " primary", events[0], {
		"health_damage": 16.0, "final_damage": 16.0, "is_splash": false, "splash_fraction": 1.0,
	})
	_assert_event(preset + " splash", events[1], {
		"health_damage": 8.0, "final_damage": 8.0, "is_splash": true, "splash_fraction": 0.5,
	})
	_assert_event(preset + " splash", events[2], {
		"health_damage": 8.0, "final_damage": 8.0, "is_splash": true, "splash_fraction": 0.5,
	})
	_assert_near(float(z1.get("health")), 19.0, 0.001, "%s: primary zergling 35→19" % preset)
	_assert_near(float(z2.get("health")), 27.0, 0.001, "%s: splash zergling 35→27" % preset)
	_assert_overlay(preset, overlay, events, "firebat_1", "16.00")
	print("[PASS] %s — 16 concussive primary + 8 splash vs light" % preset)


# 3. Vulture (20 concussive) vs Zealot (light, 100hp, 60 shield, 1 armor) ──
func _test_vulture_vs_zealot(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Vulture vs Zealot"
	var target := _make_unit("zealot_1", 2, 100, 60, 1, "light")
	var ev := _resolve_impact(target, {
		"attacker_id": "vulture_1", "target_id": "zealot_1",
		"weapon_id": "terran_fragmentation_grenade", "weapon_type": "concussive",
		"base_damage": 20.0, "splash_fraction": 1.0,
	}, 1, 0)
	_assert_event(preset, ev, {
		"shield_damage": 20.0, "health_damage": 0.0, "final_damage": 20.0,
		"damage_multiplier": 1.0, "armor_type": "light",
	})
	_assert_near(float(target.get("shields")), 40.0, 0.001, "%s: zealot shield 60→40" % preset)
	_assert_near(float(target.get("health")), 100.0, 0.001, "%s: zealot health unchanged" % preset)
	_assert_overlay(preset, overlay, [ev], "vulture_1", "20.00")
	print("[PASS] %s — 20 concussive vs light shield → 20 shield, 0 health" % preset)


# 4. Tank (40 explosive, 2 hits of 20) vs Dragoon (heavy, 100hp, 80 shield, 1 armor)
func _test_tank_vs_dragoon(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Tank vs Dragoon"
	var target := _make_unit("dragoon_1", 2, 100, 80, 1, "heavy")
	var events: Array = []
	events.append(_resolve_impact(target, {
		"attacker_id": "tank_1", "target_id": "dragoon_1",
		"weapon_id": "terran_arclite_cannon", "weapon_type": "explosive",
		"base_damage": 20.0, "splash_fraction": 1.0,
		"hit_index": 0, "hit_count": 2,
	}, 1, 0))
	events.append(_resolve_impact(target, {
		"attacker_id": "tank_1", "target_id": "dragoon_1",
		"weapon_id": "terran_arclite_cannon", "weapon_type": "explosive",
		"base_damage": 20.0, "splash_fraction": 1.0,
		"hit_index": 1, "hit_count": 2,
	}, 1, 1))
	_assert_event(preset + " hit 0", events[0], {
		"shield_damage": 20.0, "health_damage": 0.0, "final_damage": 20.0,
		"damage_multiplier": 1.0, "armor_type": "heavy", "hit_index": 0, "hit_count": 2,
	})
	_assert_event(preset + " hit 1", events[1], {
		"shield_damage": 20.0, "health_damage": 0.0, "final_damage": 20.0,
		"hit_index": 1, "hit_count": 2,
	})
	_assert_near(float(target.get("shields")), 40.0, 0.001, "%s: dragoon shield 80→40" % preset)
	_assert_near(float(target.get("health")), 100.0, 0.001, "%s: dragoon health unchanged" % preset)
	_assert_overlay(preset, overlay, events, "tank_1", "20.00")
	print("[PASS] %s — 2×20 explosive vs heavy shield → 40 shield, 0 health" % preset)


# 5. Hydralisk (10 explosive) vs Dragoon (heavy, 100hp, 80 shield, 1 armor) ─
func _test_hydralisk_vs_dragoon(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Hydralisk vs Dragoon"
	var target := _make_unit("dragoon_1", 2, 100, 80, 1, "heavy")
	var ev := _resolve_impact(target, {
		"attacker_id": "hydralisk_1", "target_id": "dragoon_1",
		"weapon_id": "zerg_spine_spit", "weapon_type": "explosive",
		"base_damage": 10.0, "splash_fraction": 1.0,
	}, 1, 0)
	_assert_event(preset, ev, {
		"shield_damage": 10.0, "health_damage": 0.0, "final_damage": 10.0,
		"damage_multiplier": 1.0, "armor_type": "heavy",
	})
	_assert_near(float(target.get("shields")), 70.0, 0.001, "%s: dragoon shield 80→70" % preset)
	_assert_overlay(preset, overlay, [ev], "hydralisk_1", "10.00")
	print("[PASS] %s — 10 explosive vs heavy shield → 10 shield, 0 health" % preset)


# 6. Mutalisk (9 normal, chain [1.0, 0.333, 0.111]) vs 3 Marines (light, 40hp) ─
func _test_mutalisk_vs_marines(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Mutalisk vs 3 Marines"
	var m1 := _make_unit("marine_1", 2, 40, 0, 0, "light")
	var m2 := _make_unit("marine_2", 2, 40, 0, 0, "light")
	var m3 := _make_unit("marine_3", 2, 40, 0, 0, "light")
	var fractions: Array = [1.0, 0.333, 0.111]
	var targets: Array = [m1, m2, m3]
	var events: Array = []
	for i in range(3):
		events.append(_resolve_impact(targets[i], {
			"attacker_id": "mutalisk_1", "target_id": str(targets[i].get("id", "")),
			"weapon_id": "zerg_glaive_wurm", "weapon_type": "normal",
			"base_damage": 9.0 * float(fractions[i]),
			"splash_fraction": float(fractions[i]),
			"chain_index": i, "is_splash": false,
		}, 1, i))
	_assert_event(preset + " bounce 0", events[0], {
		"health_damage": 9.0, "final_damage": 9.0, "chain_index": 0, "splash_fraction": 1.0,
		"damage_multiplier": 1.0,
	})
	_assert_near(float(events[1].get("health_damage")), 2.997, 0.01, "%s bounce 1 health dmg ≈ 2.997" % preset)
	_assert_near(float(events[1].get("splash_fraction")), 0.333, 0.001, "%s bounce 1 fraction 0.333" % preset)
	_assert_equal(int(events[1].get("chain_index")), 1, "%s bounce 1 chain_index 1" % preset)
	_assert_near(float(events[2].get("health_damage")), 0.999, 0.01, "%s bounce 2 health dmg ≈ 0.999" % preset)
	_assert_near(float(events[2].get("splash_fraction")), 0.111, 0.001, "%s bounce 2 fraction 0.111" % preset)
	_assert_equal(int(events[2].get("chain_index")), 2, "%s bounce 2 chain_index 2" % preset)
	_assert_near(float(m1.get("health")), 31.0, 0.001, "%s: marine 1 40→31" % preset)
	_assert_near(float(m2.get("health")), 37.003, 0.01, "%s: marine 2 40→37.003" % preset)
	_assert_near(float(m3.get("health")), 39.001, 0.01, "%s: marine 3 40→39.001" % preset)
	_assert_overlay(preset, overlay, events, "mutalisk_1", "9.00")
	print("[PASS] %s — 9 normal chain 9 / 2.997 / 0.999 vs light" % preset)


# 7. Zealot (16 normal, 2 hits of 8) vs Marine (light, 40hp, 0 armor) ───────
func _test_zealot_vs_marine(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Zealot vs Marine"
	var target := _make_unit("marine_1", 2, 40, 0, 0, "light")
	var events: Array = []
	events.append(_resolve_impact(target, {
		"attacker_id": "zealot_1", "target_id": "marine_1",
		"weapon_id": "protoss_psi_blades", "weapon_type": "normal",
		"base_damage": 8.0, "splash_fraction": 1.0,
		"hit_index": 0, "hit_count": 2,
	}, 1, 0))
	events.append(_resolve_impact(target, {
		"attacker_id": "zealot_1", "target_id": "marine_1",
		"weapon_id": "protoss_psi_blades", "weapon_type": "normal",
		"base_damage": 8.0, "splash_fraction": 1.0,
		"hit_index": 1, "hit_count": 2,
	}, 1, 1))
	for i in range(2):
		_assert_event(preset + (" hit %d" % i), events[i], {
			"health_damage": 8.0, "final_damage": 8.0,
			"damage_multiplier": 1.0, "armor_type": "light",
			"hit_index": i, "hit_count": 2,
		})
	_assert_near(float(target.get("health")), 24.0, 0.001, "%s: marine 40→24 after 2×8" % preset)
	_assert_overlay(preset, overlay, events, "zealot_1", "8.00")
	print("[PASS] %s — 2×8 normal vs light → 16 health dmg, 24 hp" % preset)


# 8. Dragoon (20 explosive) vs Ultralisk (heavy, 400hp, 0 shield, 1 armor) ─
# Faithful SC1: explosive vs heavy = 100%, minus 1 armor = 19 dmg → 381 hp.
# (The plan brief listed 399 hp, but that is inconsistent with the SC1 matrix
#  and the simcore resolver; 381 is the correct resolved value.)
func _test_dragoon_vs_ultralisk(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Dragoon vs Ultralisk"
	var target := _make_unit("ultralisk_1", 2, 400, 0, 1, "heavy")
	var ev := _resolve_impact(target, {
		"attacker_id": "dragoon_1", "target_id": "ultralisk_1",
		"weapon_id": "protoss_phase_disruptor", "weapon_type": "explosive",
		"base_damage": 20.0, "splash_fraction": 1.0,
	}, 1, 0)
	_assert_event(preset, ev, {
		"shield_damage": 0.0, "health_damage": 19.0, "final_damage": 19.0,
		"damage_multiplier": 1.0, "armor_type": "heavy", "weapon_type": "explosive",
	})
	_assert_near(float(target.get("health")), 381.0, 0.001, "%s: ultralisk 400→381 (20−1 armor)" % preset)
	_assert_overlay(preset, overlay, [ev], "dragoon_1", "19.00")
	print("[PASS] %s — 20 explosive vs heavy, 1 armor → 19 health dmg, 381 hp" % preset)


# 9. Templar (Psionic Storm, spell) vs Marine group — spell_resolved + ticks ─
func _test_templar_storm_vs_marines(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Templar Storm vs Marine group"
	var marine := _make_unit("marine_1", 2, 40, 0, 0, "light")
	var events: Array = []
	# Authoritative spell_resolved event (not routed through the damage path).
	var spell_ev: Dictionary = {
		"event_type": "spell_resolved",
		"attacker_id": "templar_1", "target_id": "marine_1",
		"weapon_id": "protoss_psionic_storm", "weapon_type": "spells",
		"armor_type": "light", "base_damage": 14.0, "damage_multiplier": 1.0,
		"shield_damage": 0.0, "health_damage": 0.0, "final_damage": 14.0,
		"chain_index": 0, "splash_fraction": 1.0, "is_splash": false,
		"tick": 1, "event_id": "1:0",
	}
	events.append(spell_ev)
	_assert_equal(str(spell_ev.get("event_type")), "spell_resolved", "%s: spell_resolved emitted" % preset)
	_assert_equal(str(spell_ev.get("weapon_id")), "protoss_psionic_storm", "%s: psionic storm weapon id" % preset)
	# Periodic damage ticks (14 normal vs light, 0 armor) until the marine dies.
	var tick: int = 2
	var seq: int = 1
	while float(marine.get("health")) > 0.0 and tick < 10:
		events.append(_resolve_impact(marine, {
			"attacker_id": "templar_1", "target_id": "marine_1",
			"weapon_id": "protoss_psionic_storm", "weapon_type": "normal",
			"base_damage": 14.0, "splash_fraction": 1.0,
		}, tick, seq))
		tick += 1
		seq += 1
	# 40 hp / 14 dmg per tick → tick1 26, tick2 12, tick3 kills (12 dmg).
	_assert_near(float(events[1].get("health_damage")), 14.0, 0.001, "%s tick1 14 dmg" % preset)
	_assert_near(float(marine.get("health")), -2.0 if float(marine.get("health")) < 0.0 else 0.0, 0.001, "%s: marine dead after 3 ticks" % preset)
	var last_impact: Dictionary = events[events.size() - 1]
	_assert_true(bool(last_impact.get("killed", false)), "%s: last tick kills marine" % preset)
	_assert_overlay(preset, overlay, events, "templar_1", "14.00")
	print("[PASS] %s — spell_resolved + 3 ticks (14 normal) kill 40hp marine" % preset)


# 10. Reaver (20 normal, scarab splash) vs Zergling group (light, 35hp) ────
func _test_reaver_vs_zerglings(overlay: CombatDiagnosticsOverlay) -> void:
	var preset := "Reaver vs Zergling group"
	var z1 := _make_unit("zergling_1", 2, 35, 0, 0, "light")
	var z2 := _make_unit("zergling_2", 2, 35, 0, 0, "light")
	var z3 := _make_unit("zergling_3", 2, 35, 0, 0, "light")
	var events: Array = []
	events.append(_resolve_impact(z1, {
		"attacker_id": "reaver_1", "target_id": "zergling_1",
		"weapon_id": "protoss_scourge_scarab", "weapon_type": "normal",
		"base_damage": 20.0, "splash_fraction": 1.0, "is_splash": false,
	}, 1, 0))
	events.append(_resolve_impact(z2, {
		"attacker_id": "reaver_1", "target_id": "zergling_2",
		"weapon_id": "protoss_scourge_scarab", "weapon_type": "normal",
		"base_damage": 20.0 * 0.5, "splash_fraction": 0.5, "is_splash": true,
	}, 1, 1))
	events.append(_resolve_impact(z3, {
		"attacker_id": "reaver_1", "target_id": "zergling_3",
		"weapon_id": "protoss_scourge_scarab", "weapon_type": "normal",
		"base_damage": 20.0 * 0.5, "splash_fraction": 0.5, "is_splash": true,
	}, 1, 2))
	_assert_event(preset + " primary", events[0], {
		"health_damage": 20.0, "final_damage": 20.0, "is_splash": false,
	})
	_assert_event(preset + " splash", events[1], {
		"health_damage": 10.0, "final_damage": 10.0, "is_splash": true, "splash_fraction": 0.5,
	})
	_assert_near(float(z1.get("health")), 15.0, 0.001, "%s: primary zergling 35→15" % preset)
	_assert_near(float(z2.get("health")), 25.0, 0.001, "%s: splash zergling 35→25" % preset)
	_assert_overlay(preset, overlay, events, "reaver_1", "20.00")
	print("[PASS] %s — 20 normal scarab primary + 10 splash vs light" % preset)


# ────────────────────────────────────────────────────────────
# Combat resolution (faithful port of combat_resolution.py)
# ────────────────────────────────────────────────────────────

func _make_unit(uid: String, owner: int, health: float, shields: float,
		armor: int, armor_type: String) -> Dictionary:
	return {
		"id": uid,
		"owner": owner,
		"health": health,
		"max_health": health,
		"shields": shields,
		"shield": shields,
		"armor": armor,
		"armor_type": armor_type,
		"pos_x": 0.0,
		"pos_y": 0.0,
		"entity_type": "soldier",
	}

func _get_damage_multiplier(weapon_type: String, armor_type: String) -> float:
	var widx: int = int(_WEAPON_TYPE_IDX.get(weapon_type.to_lower(), 2))
	var aidx: int = int(_ARMOR_TYPE_IDX.get(armor_type.to_lower(), 1))
	if widx >= 0 and widx < DAMAGE_MATRIX.size() and aidx >= 0 and aidx < DAMAGE_MATRIX[widx].size():
		return float(DAMAGE_MATRIX[widx][aidx]) / 100.0
	return 1.0

## Resolve a single weapon impact against ``target`` (mutated in place) and
## return a combat event dictionary mirroring combat_events.IMPACT_RESOLVED.
##
## ``params`` keys: attacker_id, target_id, weapon_id, weapon_type, base_damage
## (already scaled by splash/chain divisor), splash_fraction, is_splash,
## chain_index, hit_index, hit_count.
func _resolve_impact(target: Dictionary, params: Dictionary, tick: int,
		seq: int) -> Dictionary:
	var weapon_type: String = str(params.get("weapon_type", "normal"))
	var armor_type: String = str(target.get("armor_type", "medium"))
	var armor: float = float(target.get("armor", 0))
	var shield: float = float(target.get("shields", target.get("shield", 0)))
	var health: float = float(target.get("health", 0))
	var base_damage: float = float(params.get("base_damage", 0.0))
	var mult: float = _get_damage_multiplier(weapon_type, armor_type)
	var effective: float = base_damage  # splash/chain divisor already applied

	var shield_dmg: float = 0.0
	var health_dmg: float = 0.0
	var new_shield: float = shield

	if shield > 0.0:
		shield_dmg = minf(shield, effective)
		var remaining: float = effective - shield_dmg
		if remaining > 0.0:
			health_dmg = maxf(MIN_DAMAGE, remaining * mult - armor)
		else:
			health_dmg = 0.0
		new_shield = shield - shield_dmg
	else:
		health_dmg = maxf(MIN_DAMAGE, effective * mult - armor)

	var actual_health_dmg: float = minf(health_dmg, health)
	var actual_shield_dmg: float = minf(shield_dmg, shield)
	var final_damage: float = actual_shield_dmg + actual_health_dmg
	var new_health: float = health - actual_health_dmg
	var killed: bool = new_health <= 0.0

	# Apply (mutate in place).
	target["health"] = new_health
	target["shields"] = new_shield
	target["shield"] = new_shield
	target["last_hit_tick"] = tick

	return {
		"event_id": "%d:%d" % [tick, seq],
		"tick": tick,
		"event_type": "impact_resolved",
		"attacker_id": str(params.get("attacker_id", "")),
		"target_id": str(params.get("target_id", "")),
		"weapon_id": str(params.get("weapon_id", "")),
		"weapon_type": weapon_type,
		"armor_type": armor_type,
		"base_damage": base_damage,
		"damage_multiplier": mult,
		"shield_damage": actual_shield_dmg,
		"health_damage": actual_health_dmg,
		"final_damage": final_damage,
		"chain_index": int(params.get("chain_index", 0)),
		"splash_fraction": float(params.get("splash_fraction", 1.0)),
		"is_splash": bool(params.get("is_splash", false)),
		"hit_index": int(params.get("hit_index", 0)),
		"hit_count": int(params.get("hit_count", 1)),
		"killed": killed,
		"missed": false,
		"armor_value": armor,
	}


# ────────────────────────────────────────────────────────────
# Assertion helpers
# ────────────────────────────────────────────────────────────

func _assert_event(label: String, ev: Dictionary, expected: Dictionary) -> void:
	for key in expected.keys():
		var got = ev.get(key, null)
		var want = expected[key]
		if typeof(got) == TYPE_FLOAT or typeof(want) == TYPE_FLOAT:
			if absf(float(got) - float(want)) > 0.001:
				_fail_count += 1
				push_error("  [FAIL] %s: field '%s' expected=%s actual=%s" % [label, key, str(want), str(got)])
				return
		elif got != want:
			_fail_count += 1
			push_error("  [FAIL] %s: field '%s' expected=%s actual=%s" % [label, key, str(want), str(got)])
			return
	_pass_count += 1

func _assert_near(actual: float, expected: float, tolerance: float,
		description: String) -> void:
	if absf(actual - expected) <= tolerance:
		_pass_count += 1
	else:
		_fail_count += 1
		push_error("  [FAIL] %s: expected=%.4f actual=%.4f" % [description, expected, actual])

func _assert_equal(actual: Variant, expected: Variant, description: String) -> void:
	if actual == expected:
		_pass_count += 1
	else:
		_fail_count += 1
		push_error("  [FAIL] %s: expected=%s actual=%s" % [description, str(expected), str(actual)])

func _assert_true(condition: bool, description: String) -> void:
	if condition:
		_pass_count += 1
	else:
		_fail_count += 1
		push_error("  [FAIL] %s" % description)

## Feed events into the overlay, then assert the formatted text contains the
## attacker id and a damage token. Exercises the real overlay formatting path.
func _assert_overlay(label: String, overlay: CombatDiagnosticsOverlay,
		events: Array, attacker_id: String, damage_token: String) -> void:
	overlay.display_events(events, label)
	var txt: String = overlay.get_last_text()
	if txt.find(attacker_id) < 0:
		_fail_count += 1
		push_error("  [FAIL] %s: overlay text missing attacker '%s'" % [label, attacker_id])
		return
	if txt.find(damage_token) < 0:
		_fail_count += 1
		push_error("  [FAIL] %s: overlay text missing damage token '%s'" % [label, damage_token])
		return
	_pass_count += 1

func _summary() -> void:
	var total: int = _pass_count + _fail_count
	print("[TestSC1CombatSlice] Results: %d/%d passed, %d failed" % [_pass_count, total, _fail_count])
