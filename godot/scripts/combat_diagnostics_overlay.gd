class_name CombatDiagnosticsOverlay
extends PanelContainer

## Combat Diagnostics Overlay — Test Mode ONLY.
##
## Displays detailed combat event information for debugging and verifying the
## SC1 combat differentiation plan (Task 11). It reads combat event dictionaries
## produced by SimCore's combat_resolution module (transported over gRPC) and
## renders them as readable BBCode text inside a RichTextLabel.
##
## The overlay is ONLY ever visible while Test Mode is active. It must never
## appear in a normal game. Wire it up via TestModeGallery (which toggles
## ``test_mode_active``) and call ``display_events()`` when a matchup preset is
## run.
##
## Combat event dictionary fields (from simcore/combat_events.py +
## combat_resolution.py):
##   event_type        "attack_started" / "impact_resolved" / "unit_destroyed" /
##                     "spell_resolved" / "projectile_spawned"
##   attacker_id       string entity id
##   target_id         string entity id
##   weapon_id         e.g. "terran_c10_rifle", "protoss_psi_blades"
##   weapon_type       "normal" / "explosive" / "concussive" / "spells"
##   armor_type        "light" / "medium" / "heavy"
##   base_damage       per-hit base damage (after splash/chain divisor)
##   damage_multiplier size multiplier (1.0 / 0.75 / 0.5 / 0.25)
##   shield_damage     damage absorbed by protoss shield
##   health_damage     damage applied to health
##   final_damage      shield_damage + health_damage (truncated by HP)
##   chain_index       0 for primary, 1+ for mutalisk-style bounces
##   splash_fraction   1.0 for primary, <1.0 for splash/chain
##   is_splash         true for splash impacts
##   hit_index / hit_count  for multi-hit weapons (e.g. Zealot 2 hits)
##   tick              simulation tick
##   event_id          "{tick}:{sequence}"

signal closed

# ─── Layout constants ─────────────────────────────────────────
const OVERLAY_WIDTH: float = 460.0
const OVERLAY_HEIGHT: float = 360.0
const MAX_EVENTS: int = 24

# ─── BBCode colours ──────────────────────────────────────────
const COL_ATTACK: String = "#8ad28a"      # green
const COL_IMPACT: String = "#d28a8a"      # red
const COL_SHIELD: String = "#8ac6ff"      # blue
const COL_SPELL: String = "#c08aff"        # purple
const COL_DEATH: String = "#ffaa55"        # orange
const COL_PROJECTILE: String = "#cccccc"  # grey
const COL_LABEL: String = "#9a9a9a"       # muted label
const COL_VALUE: String = "#f0f0f0"       # bright value
const COL_ACCENT: String = "#ffd966"      # gold accent
const COL_HEADER: String = "#ffffff"      # header text

# ─── Internal state ──────────────────────────────────────────
var _rich_label: RichTextLabel = null
var _title_label: Label = null
var _close_btn: Button = null
var _scroll: ScrollContainer = null

var _test_mode_active: bool = false
var _shown: bool = false
var _title: String = "⚔ Combat Diagnostics"
var _last_text: String = ""

# ─── Public API ──────────────────────────────────────────────

## When Test Mode is active the overlay MAY be shown; when inactive it is always
## hidden, regardless of ``_shown``.
var test_mode_active: bool:
	get:
		return _test_mode_active
	set(value):
		_test_mode_active = value
		_update_visibility()

func set_title(title: String) -> void:
	_title = title
	if _title_label:
		_title_label.text = title

func get_title() -> String:
	return _title

## Returns the last formatted BBCode text (useful for headless tests that cannot
## read the RichTextLabel before it enters the SceneTree).
func get_last_text() -> String:
	return _last_text

## Show the overlay (only takes effect while Test Mode is active).
func show_overlay() -> void:
	_shown = true
	_update_visibility()

## Hide the overlay.
func hide_overlay() -> void:
	_shown = false
	_update_visibility()

func clear() -> void:
	_last_text = ""
	if _rich_label:
		_rich_label.text = ""
	hide_overlay()

## Display a single combat event. Builds the BBCode, sets the label, and reveals
## the overlay (gated by ``test_mode_active``).
func display_event(event: Dictionary) -> void:
	display_events([event], _title)

## Display a batch of combat events (e.g. splash / chain / multi-hit). Each event
## is rendered as a block separated by a divider.
func display_events(events: Array, title: String = "") -> void:
	if title != "":
		set_title(title)
	var blocks: PackedStringArray = PackedStringArray()
	var count: int = 0
	for ev in events:
		if not ev is Dictionary:
			continue
		if count >= MAX_EVENTS:
			blocks.append("[color=%s]… %d more event(s) truncated[/color]" % [COL_LABEL])
			break
		blocks.append(format_event(ev))
		count += 1
	_last_text = "\n".join(blocks)
	if _rich_label:
		_rich_label.text = _last_text
	show_overlay()

## Pure formatter — turns one combat event dictionary into a BBCode string.
## Does not touch any UI node, so it is safe to call on a freshly ``new()``-ed
## overlay in headless tests.
func format_event(event: Dictionary) -> String:
	var lines: PackedStringArray = PackedStringArray()
	var et: String = str(event.get("event_type", "unknown"))

	# ── Header line ──
	lines.append("[color=%s][b]%s[/b][/color]" % [_color_for_event_type(et), _event_type_label(et)])

	# ── Attacker → Target ──
	var attacker_id: String = str(event.get("attacker_id", "?"))
	var target_id: String = str(event.get("target_id", "?"))
	lines.append("[color=%s]Attacker[/color] [color=%s][b]%s[/b][/color] → [color=%s]Target[/color] [color=%s][b]%s[/b][/color]" % [COL_LABEL, COL_VALUE, attacker_id, COL_LABEL, COL_VALUE, target_id])

	# ── Weapon / Armor type ──
	var weapon_id: String = str(event.get("weapon_id", "?"))
	var weapon_type: String = str(event.get("weapon_type", "?"))
	var armor_type: String = str(event.get("armor_type", "?"))
	lines.append("[color=%s]Weapon[/color] [color=%s][b]%s[/b][/color] [color=%s](%s)[/color]  [color=%s]Armor[/color] [color=%s][b]%s[/b][/color]" % [COL_LABEL, COL_VALUE, weapon_id, COL_ACCENT, weapon_type, COL_LABEL, COL_VALUE, armor_type])

	# ── Base damage / multiplier ──
	var base_damage: float = float(event.get("base_damage", 0.0))
	var mult: float = float(event.get("damage_multiplier", 1.0))
	lines.append("[color=%s]Base dmg[/color] [color=%s]%.2f[/color]  [color=%s]Multiplier[/color] [color=%s]%.3f[/color]" % [COL_LABEL, COL_VALUE, base_damage, COL_LABEL, COL_ACCENT, mult])

	# ── Shield / Health / Final damage ──
	var shield_dmg: float = float(event.get("shield_damage", 0.0))
	var health_dmg: float = float(event.get("health_damage", 0.0))
	var final_dmg: float = float(event.get("final_damage", 0.0))
	lines.append("[color=%s]Shield[/color] [color=%s]%.2f[/color]  [color=%s]Health[/color] [color=%s]%.2f[/color]  [color=%s]Final[/color] [color=%s][b]%.2f[/b][/color]" % [COL_LABEL, COL_SHIELD, shield_dmg, COL_LABEL, COL_IMPACT, health_dmg, COL_LABEL, COL_VALUE, final_dmg])

	# ── Splash fraction OR chain index ──
	var is_splash: bool = bool(event.get("is_splash", false))
	var chain_index: int = int(event.get("chain_index", 0))
	var splash_fraction: float = float(event.get("splash_fraction", 1.0))
	var hit_index: int = int(event.get("hit_index", 0))
	var hit_count: int = int(event.get("hit_count", 1))
	if chain_index > 0 or _looks_like_chain(event):
		lines.append("[color=%s]Chain[/color] [color=%s]index %d[/color]  [color=%s]fraction[/color] [color=%s]%.3f[/color]" % [COL_LABEL, COL_ACCENT, chain_index, COL_LABEL, COL_VALUE, splash_fraction])
	elif is_splash or splash_fraction < 1.0:
		lines.append("[color=%s]Splash[/color] [color=%s]fraction %.3f[/color]  [color=%s]is_splash=%s[/color]" % [COL_LABEL, COL_ACCENT, splash_fraction, COL_LABEL, str(is_splash).to_lower()])
	if hit_count > 1:
		lines.append("[color=%s]Hit[/color] [color=%s]%d/%d[/color]" % [COL_LABEL, COL_ACCENT, hit_index + 1, hit_count])

	# ── Extra flags ──
	var extras: PackedStringArray = PackedStringArray()
	if bool(event.get("killed", false)):
		extras.append("[color=%s]KILLED[/color]" % COL_DEATH)
	if bool(event.get("missed", false)):
		extras.append("[color=%s]MISSED[/color]" % COL_LABEL)
	if bool(event.get("is_splash", false)) and chain_index == 0:
		extras.append("[color=%s]splash[/color]" % COL_ACCENT)
	if extras.size() > 0:
		lines.append(" ".join(extras))

	# ── Tick / Event ID ──
	var tick: int = int(event.get("tick", 0))
	var event_id: String = str(event.get("event_id", "?"))
	lines.append("[color=%s]tick[/color] [color=%s]%d[/color]  [color=%s]event_id[/color] [color=%s]%s[/color]" % [COL_LABEL, COL_VALUE, tick, COL_LABEL, COL_ACCENT, event_id])

	return "\n".join(lines)

# ─── Lifecycle ───────────────────────────────────────────────

func _ready() -> void:
	_build_ui()
	_update_visibility()

func _build_ui() -> void:
	# Dock to the bottom-right of the screen.
	anchor_left = 1.0
	anchor_top = 1.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	offset_left = -OVERLAY_WIDTH
	offset_top = -OVERLAY_HEIGHT
	offset_right = 0.0
	offset_bottom = 0.0
	custom_minimum_size = Vector2(OVERLAY_WIDTH, OVERLAY_HEIGHT)
	modulate = Color(1.0, 1.0, 1.0, 0.96)

	# Panel style — dark translucent background.
	var stylebox := StyleBoxFlat.new()
	stylebox.bg_color = Color(0.06, 0.07, 0.09, 0.92)
	stylebox.border_color = Color(0.35, 0.4, 0.5, 0.9)
	stylebox.set_border_width_all(2)
	stylebox.set_corner_radius_all(6)
	stylebox.set_content_margin_all(8)
	add_theme_stylebox_override("panel", stylebox)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 6)
	add_child(vbox)

	# ── Title bar (title + close button) ──
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 6)
	vbox.add_child(header)

	_title_label = Label.new()
	_title_label.text = _title
	_title_label.add_theme_font_size_override("font_size", 14)
	_title_label.add_theme_color_override("font_color", Color(1.0, 0.85, 0.6))
	_title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(_title_label)

	_close_btn = Button.new()
	_close_btn.text = "✕"
	_close_btn.tooltip_text = "Hide combat diagnostics overlay"
	_close_btn.custom_minimum_size = Vector2(28, 24)
	_close_btn.modulate = Color(1.0, 0.7, 0.7)
	_close_btn.size_flags_horizontal = Control.SIZE_SHRINK_END
	header.add_child(_close_btn)
	_close_btn.pressed.connect(_on_close_pressed)

	# ── Scrollable diagnostics text ──
	_scroll = ScrollContainer.new()
	_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	vbox.add_child(_scroll)

	_rich_label = RichTextLabel.new()
	_rich_label.bbcode_enabled = true
	_rich_label.fit_content = false
	_rich_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_rich_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_rich_label.custom_minimum_size = Vector2(OVERLAY_WIDTH - 24, OVERLAY_HEIGHT - 64)
	_rich_label.add_theme_font_size_override("normal_font_size", 13)
	_rich_label.add_theme_font_size_override("bold_font_size", 13)
	_scroll.add_child(_rich_label)

func _update_visibility() -> void:
	visible = _test_mode_active and _shown

func _on_close_pressed() -> void:
	hide_overlay()
	closed.emit()

# ─── Helpers ──────────────────────────────────────────────────

func _color_for_event_type(et: String) -> String:
	match et:
		"attack_started":
			return COL_ATTACK
		"impact_resolved":
			return COL_IMPACT
		"unit_destroyed":
			return COL_DEATH
		"spell_resolved":
			return COL_SPELL
		"projectile_spawned":
			return COL_PROJECTILE
		_:
			return COL_HEADER

func _event_type_label(et: String) -> String:
	return et.replace("_", " ").to_upper()

## Heuristic: a mutalisk-style chain event records chain_index > 0 or a weapon_id
## hinting at a glaive/bounce.
func _looks_like_chain(event: Dictionary) -> bool:
	if int(event.get("chain_index", 0)) > 0:
		return true
	var wid: String = str(event.get("weapon_id", "")).to_lower()
	return wid.find("glaive") >= 0 or wid.find("chain") >= 0 or wid.find("bounce") >= 0
