extends SceneTree

## Headless test script for Task 11 — SC1 combat differentiation slice.
##
## Verifies the SC1 combat event fixtures (produced by the headless SimCore
## resolver) are well-formed and consumable by the Godot-side combat visual
## pipeline (CombatDiagnosticsOverlay + CombatVisualController).
##
## Damage is NO LONGER computed in GDScript — all expected events come from
## the authoritative JSON fixture at res://resources/test/sc1_combat_presets.json,
## eliminating the "no damage formulas in Godot" violation.
##
## Run the diagnostics slice:
##   /Applications/Godot.app/Contents/MacOS/Godot --headless --path godot \
##       --script scripts/test_sc1_combat_slice.gd -- --diagnostics
##
## Without ``--diagnostics`` only a quick smoke check runs. Prints PASS/FAIL
## per matchup and exits 0 on full success, 1 otherwise.

const CombatDiagnosticsOverlayScript := preload("res://scripts/combat_diagnostics_overlay.gd")
const CombatVisualControllerScript := preload("res://scripts/combat_visual_controller.gd")
const PRESETS_PATH := "res://resources/test/sc1_combat_presets.json"
const EXPECTED_PRESET_COUNT := 10

var _pass_count: int = 0
var _fail_count: int = 0
var _dispatched_count: int = 0  # Counter for CombatVisualController signal


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
# Fixture loading
# ────────────────────────────────────────────────────────────

## Load and return the presets array from the JSON fixture. Returns an empty
## array (and increments _fail_count) on any load/parse error.
func _load_presets() -> Array:
	if not FileAccess.file_exists(PRESETS_PATH):
		push_error("  [FAIL] fixture not found: %s" % PRESETS_PATH)
		_fail_count += 1
		return []
	var raw_text: String = FileAccess.get_file_as_string(PRESETS_PATH)
	var parsed = JSON.parse_string(raw_text)
	if not parsed is Dictionary or not parsed.has("presets"):
		push_error("  [FAIL] invalid fixture (expected {\"presets\": [...]})")
		_fail_count += 1
		return []
	return parsed.get("presets", [])


## Return the first impact_resolved event dictionary from a preset, or {}.
func _first_impact(preset: Dictionary) -> Dictionary:
	for ev in preset.get("combat_events", []):
		if ev is Dictionary and str(ev.get("event_type", "")) == "impact_resolved":
			return ev
	return {}


# ────────────────────────────────────────────────────────────
# Smoke check (no --diagnostics)
# ────────────────────────────────────────────────────────────

func _run_smoke() -> void:
	var presets := _load_presets()
	_assert_equal(presets.size(), EXPECTED_PRESET_COUNT,
		"fixture has %d presets" % EXPECTED_PRESET_COUNT)
	if presets.is_empty():
		return

	# Overlay formats a fixture impact_resolved event without crashing.
	var overlay = CombatDiagnosticsOverlayScript.new()
	var p0: Dictionary = presets[0] if presets[0] is Dictionary else {}
	var sample_ev: Dictionary = _first_impact(p0)
	_assert_true(not sample_ev.is_empty(), "preset 0 has an impact_resolved event")
	if sample_ev.is_empty():
		overlay.free()
		return
	var txt: String = overlay.format_event(sample_ev)
	_assert_true(txt.find(str(sample_ev.get("attacker_id", ""))) >= 0,
		"overlay text contains attacker id")
	_assert_true(txt.find("IMPACT RESOLVED") >= 0,
		"overlay text contains event type header")
	overlay.free()

	# CombatVisualController processes a preset's events without errors.
	# Added to root so get_node_or_null() doesn't warn about absolute paths.
	var ctrl: CombatVisualController = CombatVisualControllerScript.new()
	root.add_child(ctrl)
	_dispatched_count = 0
	ctrl.combat_event_emitted.connect(_on_combat_event_emitted)
	ctrl.process_combat_events(p0.get("combat_events", []))
	ctrl.combat_event_emitted.disconnect(_on_combat_event_emitted)
	_assert_true(_dispatched_count > 0, "controller dispatches events for preset 0")
	ctrl.free()


# ────────────────────────────────────────────────────────────
# Diagnostics — all 10 matchup presets from the JSON fixture
# ────────────────────────────────────────────────────────────

func _run_diagnostics() -> void:
	var presets := _load_presets()
	if presets.is_empty():
		return
	_assert_equal(presets.size(), EXPECTED_PRESET_COUNT,
		"fixture has %d presets" % EXPECTED_PRESET_COUNT)

	# Build the overlay once and add it to a CanvasLayer so _ready fires
	# (proves UI construction works headless).
	var overlay = CombatDiagnosticsOverlayScript.new()
	overlay.test_mode_active = true
	var canvas := CanvasLayer.new()
	root.add_child(canvas)
	canvas.add_child(overlay)
	_assert_true(overlay.test_mode_active, "overlay test_mode_active setter works")

	# CombatVisualController for event-processing checks (no VFXManager —
	# events are still dispatched via the combat_event_emitted signal).
	# Added to root so get_node_or_null() doesn't warn about absolute paths.
	var ctrl: CombatVisualController = CombatVisualControllerScript.new()
	root.add_child(ctrl)

	for i in range(presets.size()):
		var preset: Dictionary = presets[i] if presets[i] is Dictionary else {}
		_test_preset(i, preset, overlay, ctrl)
		print("[PASS] Preset %d (%s) — fixture events verified" % [
			i + 1, str(preset.get("id", ""))])

	ctrl.free()
	overlay.free()
	canvas.free()


## Verify a single preset from the fixture: structural integrity, event field
## consistency, overlay rendering, and CombatVisualController dispatch.
func _test_preset(idx: int, preset: Dictionary, overlay: CombatDiagnosticsOverlay,
		ctrl: CombatVisualController) -> void:
	var preset_id: String = str(preset.get("id", "preset_%d" % (idx + 1)))
	var label: String = "Preset %d (%s)" % [idx + 1, preset_id]

	# ── Structural assertions ──
	_assert_true(not preset_id.is_empty(), "%s: has id" % label)
	_assert_true(not str(preset.get("attacker", "")).is_empty(), "%s: has attacker" % label)
	_assert_true(preset.has("targets"), "%s: has targets" % label)
	_assert_true(preset.has("initial_entities"), "%s: has initial_entities" % label)
	_assert_true(preset.has("final_entities"), "%s: has final_entities" % label)
	_assert_true(preset.has("ticks"), "%s: has ticks" % label)
	_assert_true(int(preset.get("ticks", 0)) > 0, "%s: ticks > 0" % label)

	var events: Array = preset.get("combat_events", [])
	_assert_true(events.size() > 0, "%s: has combat_events" % label)

	# ── Event field + internal-consistency assertions ──
	# For every impact_resolved event: final_damage ≈ shield_damage + health_damage.
	# This cross-checks the fixture's internal consistency without computing
	# damage locally.
	var has_impact := false
	var has_attack := false
	var first_attacker: String = ""
	var first_damage: float = -1.0
	for ev in events:
		if not ev is Dictionary:
			_fail_count += 1
			push_error("  [FAIL] %s: non-dict event in combat_events" % label)
			continue
		var etype: String = str(ev.get("event_type", ""))
		_assert_true(not etype.is_empty(), "%s: event has event_type" % label)
		_assert_true(ev.has("event_id"), "%s: event has event_id" % label)
		_assert_true(ev.has("weapon_id"), "%s: event has weapon_id" % label)
		match etype:
			"impact_resolved":
				has_impact = true
				if first_attacker == "":
					first_attacker = str(ev.get("attacker_id", ""))
				if first_damage < 0.0:
					first_damage = float(ev.get("final_damage", 0.0))
				var fd: float = float(ev.get("final_damage", 0.0))
				var sd: float = float(ev.get("shield_damage", 0.0))
				var hd: float = float(ev.get("health_damage", 0.0))
				_assert_near(fd, sd + hd, 0.01,
					"%s: final_damage == shield + health (%s)" % [label, str(ev.get("event_id", ""))])
				_assert_true(ev.has("attacker_id"), "%s: impact has attacker_id" % label)
				_assert_true(ev.has("target_id"), "%s: impact has target_id" % label)
				_assert_true(ev.has("armor_type"), "%s: impact has armor_type" % label)
			"attack_started":
				has_attack = true
				if first_attacker == "":
					first_attacker = str(ev.get("attacker_id", ""))
	_assert_true(has_impact, "%s: has at least one impact_resolved event" % label)
	_assert_true(has_attack, "%s: has at least one attack_started event" % label)

	# ── Overlay rendering ──
	# Feed the preset's events into the overlay and verify the formatted text
	# contains the first attacker id and a damage token.
	overlay.display_events(events, label)
	var txt: String = overlay.get_last_text()
	if first_attacker != "":
		_assert_true(txt.find(first_attacker) >= 0,
			"%s: overlay text contains attacker '%s'" % [label, first_attacker])
	if first_damage >= 0.0:
		var token: String = "%.2f" % first_damage
		_assert_true(txt.find(token) >= 0,
			"%s: overlay text contains damage token '%s'" % [label, token])

	# ── CombatVisualController event processing ──
	# The controller should dispatch at least one normalized event per preset.
	ctrl.clear_seen_events()
	_dispatched_count = 0
	ctrl.combat_event_emitted.connect(_on_combat_event_emitted)
	ctrl.process_combat_events(events)
	ctrl.combat_event_emitted.disconnect(_on_combat_event_emitted)
	_assert_true(_dispatched_count > 0, "%s: controller dispatched events" % label)


func _on_combat_event_emitted(_event: Dictionary) -> void:
	_dispatched_count += 1


# ────────────────────────────────────────────────────────────
# Assertion helpers
# ────────────────────────────────────────────────────────────

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

func _summary() -> void:
	var total: int = _pass_count + _fail_count
	print("[TestSC1CombatSlice] Results: %d/%d passed, %d failed" % [_pass_count, total, _fail_count])
