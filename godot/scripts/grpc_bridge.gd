class_name GrpcBridge
extends Node

## Bridge between Godot frontend and SimCore gRPC backend.
##
## Manages connection lifecycle, state polling, and command submission.
## The SimCore Python server must be running:
##   python -m simcore.grpc_server --port 50051 --auto-step

signal game_started(initial_state: Dictionary)
signal state_updated(state: Dictionary)
signal connection_lost()

enum State { IDLE, CONNECTING, CONNECTED, ERROR }

@export var server_address: String = "localhost:50051"
@export var poll_interval: float = 0.05  # 20 tps by default

var current_state: State = State.IDLE
var _tick: int = 0
var _map_seed: int = 42

# Selected units — populated by game_view on click
var selected_units: PackedStringArray = []


func _ready() -> void:
	_poll_timer = Timer.new()
	_poll_timer.wait_time = poll_interval
	_poll_timer.one_shot = false
	_poll_timer.timeout.connect(_poll_state)
	add_child(_poll_timer)
	_poll_timer.stop()


func start_game(seed: int = 42, max_ticks: int = 10000) -> void:
	"""Connect to SimCore and start a new game."""
	_map_seed = seed
	current_state = State.CONNECTING

	# Launch SimCore server as subprocess
	_launch_simcore_server()

	# Give the server a moment to start
	await get_tree().create_timer(1.5).timeout

	# Request initial state
	var result := await _call_python("start_game", {"seed": seed, "max_ticks": max_ticks})
	if result.is_empty():
		push_error("[GrpcBridge] Failed to start game")
		current_state = State.ERROR
		connection_lost.emit()
		return

	current_state = State.CONNECTED
	_tick = 0
	game_started.emit(result)
	_poll_timer.start()


func submit_commands(commands: Array) -> void:
	"""Submit player commands for the next tick."""
	if current_state != State.CONNECTED:
		return
	# Fire and forget — we don't need the response, next poll will show new state
	_call_python_no_wait("step", {"commands": commands})


func get_health() -> Dictionary:
	"""Health check."""
	if current_state != State.CONNECTED:
		return {"healthy": false, "status": "disconnected"}
	var result := await _call_python("health", {})
	return result if result else {"healthy": false, "status": "error"}


# ─── Internal ────────────────────────────────────────────────

var _poll_timer: Timer
var _server_pid: int = 0


func _launch_simcore_server() -> void:
	"""Launch SimCore gRPC server as a subprocess (auto-step mode)."""
	if _server_pid != 0:
		return
	var port := server_address.split(":")[1] if ":" in server_address else "50051"
	var args := [
		"-m", "simcore.grpc_server",
		"--port", port,
		"--auto-step",
		"--tick-rate", "20",
	]
	_server_pid = OS.create_process("python3", args)
	print("[GrpcBridge] SimCore server PID=%d started on port %s" % [_server_pid, port])


func _poll_state() -> void:
	"""Called by timer: fetch latest state from SimCore."""
	if current_state != State.CONNECTED:
		return
	var result := await _call_python("get_state", {})
	if result.is_empty():
		current_state = State.ERROR
		connection_lost.emit()
		_poll_timer.stop()
		return
	_tick = result.get("tick", _tick)
	state_updated.emit(result)


func _call_python(method: String, params: Dictionary) -> Dictionary:
	"""Call py_bridge.py synchronously (blocks until response)."""
	var script_path := "res://scripts/py_bridge.py"
	var port := server_address.split(":")[1] if ":" in server_address else "50051"
	var addr := "localhost:" + port
	var args := [script_path, addr, method, JSON.stringify(params)]
	var output: Array = []
	var exit_code := OS.execute("python3", args, output)
	if exit_code != 0 or output.is_empty():
		return {}
	var json_parser := JSON.new()
	if json_parser.parse(output[0]) != OK:
		return {}
	return json_parser.data if json_parser.data else {}


func _call_python_no_wait(method: String, params: Dictionary) -> void:
	"""Fire-and-forget call to py_bridge.py — runs in thread pool."""
	var script_path := "res://scripts/py_bridge.py"
	var port := server_address.split(":")[1] if ":" in server_address else "50051"
	var addr := "localhost:" + port
	var args := PackedStringArray([script_path, addr, method, JSON.stringify(params)])
	OS.create_process("python3", args)


func _exit_tree() -> void:
	if _server_pid != 0:
		OS.kill(_server_pid)
		_server_pid = 0