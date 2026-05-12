class_name ObjectPool
extends Node

## 2D object pool adapted from RTS_ObjectPool / RTS_ObjectPoolItem.
## Pool items are Node2D-based wrappers; the actual PackedScene instance is
## added as a child so any scene can be recycled without modification.
##
## Inner classes:
##   ObjectPool.ObjectPoolItem – pooled item wrapper (extends Node2D)
##   ObjectPool.PoolManager   – registry of named pools (extends Node)


# ── ObjectPoolItem ────────────────────────────────────────────────────────────

## Wraps a recycled Node2D scene instance.  Toggles visible / processing
## based on active state so inactive items cost nothing per frame.
class ObjectPoolItem extends Node2D:
	var is_active: bool = false
	var _scene_instance: Node2D = null

	func set_active(value: bool) -> void:
		is_active = value
		visible = value
		set_process(value)
		set_physics_process(value)
		set_process_input(value)
		if _scene_instance:
			_scene_instance.visible = value
			_scene_instance.set_process(value)
			_scene_instance.set_physics_process(value)

	## Returns the wrapped scene root (null if the prefab root was not Node2D).
	func get_scene_instance() -> Node2D:
		return _scene_instance


# ── PoolManager ───────────────────────────────────────────────────────────────

## Keeps named ObjectPool references so systems can request pools by name.
class PoolManager extends Node:
	var _pools: Dictionary = {}

	func get_pool(pool_name: String) -> ObjectPool:
		if _pools.has(pool_name):
			return _pools[pool_name] as ObjectPool
		return null

	func add_pool(pool_name: String, pool: ObjectPool) -> void:
		_pools[pool_name] = pool
		if not pool.get_parent():
			add_child(pool)

	func remove_pool(pool_name: String) -> void:
		if _pools.has(pool_name):
			var pool: ObjectPool = _pools[pool_name]
			_pools.erase(pool_name)
			if pool.get_parent() == self:
				remove_child(pool)
			pool.queue_free()


# ── ObjectPool (main class) ───────────────────────────────────────────────────

@export var prefab: PackedScene
@export var prewarm_count: int = 0

var _available: Array[ObjectPoolItem] = []
var _in_use: Array[ObjectPoolItem] = []


func _ready() -> void:
	for i in prewarm_count:
		var item := _create_item()
		item.set_active(false)
		_available.append(item)


func _create_item() -> ObjectPoolItem:
	var item := ObjectPoolItem.new()
	if prefab:
		var instance := prefab.instantiate()
		if instance is Node2D:
			item._scene_instance = instance as Node2D
		item.add_child(instance)
	add_child(item)
	return item


## Acquire an item from the pool.  If the pool is empty a new item is created.
func get_item(set_active: bool = true) -> Node2D:
	var item: ObjectPoolItem
	if _available.size() > 0:
		item = _available.pop_back()
	else:
		item = _create_item()

	if set_active:
		item.set_active(true)

	_in_use.append(item)
	return item


## Return an item to the pool.  Accepts either the ObjectPoolItem itself or
## the wrapped scene instance (detected via parent check).
func retire_item(item: Node2D) -> void:
	var pool_item: ObjectPoolItem = null
	if item is ObjectPoolItem:
		pool_item = item as ObjectPoolItem
	elif item.get_parent() is ObjectPoolItem:
		pool_item = item.get_parent() as ObjectPoolItem

	if pool_item == null:
		push_warning("ObjectPool: Cannot retire item — not an ObjectPoolItem or child of one.")
		return

	pool_item.set_active(false)
	_in_use.erase(pool_item)
	if not _available.has(pool_item):
		_available.append(pool_item)