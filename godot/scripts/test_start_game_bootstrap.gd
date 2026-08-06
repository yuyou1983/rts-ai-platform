extends SceneTree

## End-to-end regression: Start Game must work without manually starting SimCore.

const GrpcBridgeScript = preload("res://scripts/grpc_bridge.gd")

var _finished := false
var _bridge: Node
var _timeout_timer: Timer


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_bridge = GrpcBridgeScript.new()
	root.add_child(_bridge)
	_bridge.ai_player = 2
	_bridge.game_started.connect(_on_game_started)
	_bridge.connection_lost.connect(_on_connection_lost)
	_bridge.start_game(4242, 100)
	_timeout_timer = Timer.new()
	_timeout_timer.one_shot = true
	_timeout_timer.wait_time = 12.0
	_timeout_timer.timeout.connect(_on_timeout)
	root.add_child(_timeout_timer)
	_timeout_timer.start()


func _on_timeout() -> void:
	if not _finished:
		_fail("Start Game timed out before receiving an initial state")


func _on_game_started(state: Dictionary) -> void:
	if _finished:
		return
	var entities: Dictionary = state.get("entities", {})
	var fog: Dictionary = state.get("fog_of_war", {})
	if entities.is_empty():
		_fail("Initial state contains no entities")
		return
	if fog.is_empty():
		_fail("Initial state contains no fog-of-war data")
		return
	_finished = true
	print("PASS: Start Game received %d entities and fog-of-war data" % entities.size())
	call_deferred("_finish", 0)


func _on_connection_lost() -> void:
	if not _finished:
		_fail("Start Game lost the backend connection")


func _fail(message: String) -> void:
	_finished = true
	push_error("FAIL: %s" % message)
	call_deferred("_finish", 1)


func _finish(exit_code: int) -> void:
	if is_instance_valid(_timeout_timer):
		_timeout_timer.queue_free()
	if is_instance_valid(_bridge):
		_bridge.queue_free()
	await process_frame
	quit(exit_code)
