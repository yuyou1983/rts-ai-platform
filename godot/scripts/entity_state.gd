class_name EntityState
extends RefCounted

## Mirrors SimCore entity data for rendering in Godot.

var id: String = ""
var owner: int = 0
var entity_type: String = ""
var pos_x: float = 0.0
var pos_y: float = 0.0
var health: int = 0
var max_health: int = 0
var speed: float = 0.0
var attack: float = 0.0
var attack_range: float = 1.0
var is_idle: bool = true


static func from_dict(data: Dictionary) -> EntityState:
	var e := EntityState.new()
	e.id = data.get("id", "")
	e.owner = data.get("owner", 0)
	e.entity_type = data.get("entity_type", "")
	e.pos_x = data.get("pos_x", 0.0)
	e.pos_y = data.get("pos_y", 0.0)
	e.health = data.get("health", 0)
	e.max_health = data.get("max_health", 0)
	e.speed = data.get("speed", 0.0)
	e.attack = data.get("attack", 0.0)
	e.attack_range = data.get("attack_range", 1.0)
	e.is_idle = data.get("is_idle", true)
	return e