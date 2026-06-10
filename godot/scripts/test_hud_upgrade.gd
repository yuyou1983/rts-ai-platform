extends SceneTree
## Minimal test: verify HUD shows correct train/upgrade/research for all 3 races
## Run: /Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_hud_upgrade.gd

const HUDScript := preload("res://scripts/hud.gd")

var _pass := 0
var _fail := 0
var _hud: Control

func _init() -> void:
	_hud = Control.new()
	_hud.set_script(HUDScript)
	root.add_child(_hud)
	
	if _hud._upgrade_panel == null:
		_hud._build_ui()
		_hud._connect_signals()
	
	_hud.minerals = 9999
	_hud.gas = 9999
	# Give all prereq buildings so everything shows
	_hud._completed_buildings = PackedStringArray([
		"base", "barracks", "factory", "starport",
		"morph_base", "morph_base2",
		"supply_depot", "refinery", "defense",
		"tech_basic", "tech_cyber", "tech_infantry",
		"armory", "science",
	])
	
	# ── ZERG ──
	_hud.set_player_race("2")
	_test_upgrade("base", "Lair", true, "Zerg Hatchery → Lair")
	_test_upgrade("morph_base", "Hive", true, "Zerg Lair → Hive")
	
	# Terran base → no Zerg upgrades (re-call to clear old panel)
	_hud.set_player_race("1")
	_hud.selected_building_type = "base"
	_hud._show_upgrade_panel_for("base")  # forces rebuild for Terran
	_test_upgrade_check("base", "Lair", false, "Terran should NOT show Zerg upgrades")
	
	_hud.set_player_race("2")
	_test_train("base", ["Drone", "Overlord"], "Zerg Hatchery: Drone + Overlord")
	_test_train("barracks", ["Zergling", "Hydralisk"], "Zerg Spawning Pool: Zergling + Hydralisk")
	_test_train("factory", ["Ultralisk"], "Zerg Hydralisk Den: Ultralisk")
	_test_train("starport", ["Mutalisk", "Queen", "Defiler", "Scourge"], "Zerg Spire: Mutalisk + Queen + Defiler + Scourge")
	
	# ── TERRAN ──
	_hud.set_player_race("1")
	_test_train("base", ["SCV"], "Terran CC: SCV")
	_test_train("barracks", ["Marine", "Firebat", "Ghost", "Medic"], "Terran Barracks: Marine + Firebat + Ghost + Medic")
	_test_train("factory", ["Vulture", "Siege Tank", "Goliath"], "Terran Factory: Vulture + Siege Tank + Goliath")
	_test_train("starport", ["Wraith", "Dropship", "Vessel", "Valkyrie", "BattleCruiser"], "Terran Starport: Wraith + Dropship + Vessel + Valkyrie + BC")
	
	# ── PROTOSS ──
	_hud.set_player_race("3")
	_test_train("base", ["Probe"], "Protoss Nexus: Probe")
	_test_train("barracks", ["Zealot", "Dragoon", "Templar", "Dark Templar"], "Protoss Gateway: Zealot + Dragoon + Templar + DT")
	_test_train("factory", ["Reaver", "Shuttle", "Observer"], "Protoss Robotics: Reaver + Shuttle + Observer")
	_test_train("starport", ["Scout", "Carrier", "Arbiter", "Corsair"], "Protoss Stargate: Scout + Carrier + Arbiter + Corsair")
	
	print("\n🎉 %d PASSED, %d FAILED" % [_pass, _fail])
	quit()

func _test_upgrade_check(building_key: String, expected_text: String, should_find: bool, desc: String) -> void:
	# Same as _test_upgrade but without calling _show again (already called)
	var panel = _hud._upgrade_panel
	if panel == null:
		_fail += 1; print("  ❌ FAIL: %s — panel null" % desc); return
	var found := false
	for child in panel.get_children():
		if child is VBoxContainer:
			for c in child.get_children():
				if c is Button and expected_text in c.text:
					found = true
	if found == should_find:
		_pass += 1; print("  ✅ PASS: %s" % desc)
	else:
		_fail += 1; print("  ❌ FAIL: %s — found=%s expected=%s" % [desc, str(found), str(should_find)])

func _test_upgrade(building_key: String, expected_text: String, should_find: bool, desc: String, race: String = "") -> void:
	if race != "":
		_hud.set_player_race(race)
	_hud.selected_count = 1
	_hud.selected_type = "building"
	_hud.selected_building_type = building_key
	_hud._show_upgrade_panel_for(building_key)
	
	var panel = _hud._upgrade_panel
	if panel == null:
		_fail += 1; print("  ❌ FAIL: %s — panel null" % desc); return
	
	var found := false
	for child in panel.get_children():
		if child is VBoxContainer:
			for c in child.get_children():
				if c is Button and expected_text in c.text:
					found = true
	
	if found == should_find:
		_pass += 1; print("  ✅ PASS: %s" % desc)
	else:
		_fail += 1; print("  ❌ FAIL: %s — found=%s expected=%s" % [desc, str(found), str(should_find)])

func _test_train(building_key: String, expected_units: Array, desc: String) -> void:
	_hud.selected_count = 1
	_hud.selected_type = "building"
	_hud.selected_building_type = building_key
	_hud._show_train_panel_for(building_key)
	
	var tp = _hud._train_panel
	if tp == null:
		_fail += 1; print("  ❌ FAIL: %s — panel null" % desc); return
	if not tp.visible:
		_fail += 1; print("  ❌ FAIL: %s — panel not visible" % desc); return
	
	var found_units := {}
	for child in tp.get_children():
		if child is VBoxContainer:
			for c in child.get_children():
				if c is Button:
					for u in expected_units:
						if u in c.text:
							found_units[u] = true
	
	var all_found := true
	var missing := []
	for u in expected_units:
		if not found_units.has(u):
			all_found = false; missing.append(u)
	
	if all_found:
		_pass += 1; print("  ✅ PASS: %s" % desc)
	else:
		_fail += 1; print("  ❌ FAIL: %s — missing: %s" % [desc, str(missing)])
