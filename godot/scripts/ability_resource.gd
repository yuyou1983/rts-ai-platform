class_name AbilityResource
extends Resource

## Defines the properties of a single ability (move, attack, gather, etc.).
## Adapted from RTS_AbilityResource / RTS_ClickAbilityResource for our
## server-authoritative architecture where abilities submit commands to SimCore
## instead of executing locally.

# ── Identity ──────────────────────────────────────────────────────────────────

## Unique ability identifier (e.g. &"move", &"attack", &"gather").
@export var id: StringName = &""

## Human-readable name shown in the HUD ability bar.
@export var display_name: String = ""

## Tooltip text shown on hover.
@export var description: String = ""

## Keyboard shortcut that triggers this ability (e.g. KEY_M for move).
@export var hotkey: Key = KEY_NONE

## Optional icon displayed in the ability bar.
@export var icon: Texture2D = null

# ── Cost & Cooldown ───────────────────────────────────────────────────────────

## Seconds between uses (0 = no cooldown).
@export var cooldown: float = 0.0

## Action-point cost per use (1 = standard).
@export var ap_cost: int = 1

# ── Behaviour Flags ───────────────────────────────────────────────────────────

## If true, Shift+click queues this ability after the current one.
@export var is_chainable: bool = true

## If true, all selected entities activate the ability together.
## If false, only the "primary" entity (highest_selected) uses it.
@export var allow_trigger_multiple: bool = true

## If true, one command dict is built for the entire group (e.g. group-move
## with formation offsets). If false, each entity sends its own command.
@export var activate_as_group: bool = true

## If true, this ability doesn't clear existing targets/waypoints (e.g. patrol,
## attack-move) when issued without Shift.
@export var dont_clear_targets: bool = false

# ── Targeting ────────────────────────────────────────────────────────────────

## What kind of target this ability requires:
##   0 = none / self  (e.g. stop, hold)
##   1 = position     (e.g. move, patrol, attack-move)
##   2 = entity       (e.g. attack, gather)
##   3 = position or entity  (e.g. attack-move, right-click context)
@export var target_type: int = 0

## Maximum cast range in world units (999 = effectively unlimited).
@export var cast_max_range: float = 999.0

## If true and the caster is out of range, SimCore will auto-move closer before
## casting. (Server-side enforcement — we just submit the command.)
@export var auto_move_to_cast: bool = true