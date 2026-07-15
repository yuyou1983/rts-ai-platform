class_name TestModeUIController
extends Control

## Test Mode UI Controller — manages sidebar, filter panel, and zoom buttons.
## Keeps UI elements in a fixed screen-space sidebar so they don't overlap
## the sprite showcase area.

signal mode_selected(mode: String)
signal filter_changed(key: String, value: String)

var mode_sidebar: VBoxContainer
var filter_panel: PanelContainer

func setup() -> void:
	anchor_left = 0.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	mouse_filter = Control.MOUSE_FILTER_PASS

	mode_sidebar = VBoxContainer.new()
	mode_sidebar.name = "ModeSidebar"
	mode_sidebar.anchor_left = 0.0
	mode_sidebar.anchor_top = 0.0
	mode_sidebar.anchor_right = 0.0
	mode_sidebar.anchor_bottom = 0.0
	mode_sidebar.offset_left = 12
	mode_sidebar.offset_top = 96
	mode_sidebar.offset_right = 156
	mode_sidebar.offset_bottom = 360
	mode_sidebar.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(mode_sidebar)

	filter_panel = PanelContainer.new()
	filter_panel.name = "FilterPanel"
	filter_panel.anchor_left = 0.0
	filter_panel.anchor_top = 0.0
	filter_panel.anchor_right = 1.0
	filter_panel.anchor_bottom = 0.0
	filter_panel.offset_left = 168
	filter_panel.offset_top = 12
	filter_panel.offset_right = -320
	filter_panel.offset_bottom = 172
	filter_panel.visible = false
	filter_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(filter_panel)
