class_name GrpcBridge
extends Node

## Bridge between Godot frontend and SimCore gRPC backend.
##
## Handles connection lifecycle, state polling, and command submission.
## The SimCore Python server must be running: `python -m simcore.grpc_server`

signal game_started(initial_state: Dictionary)
signal state_updated(state: Dictionary)
signal connection_lost()

enum State { IDLE, CONNECTING, CONNECTED, ERROR }

@export var server_address: String = "localhost:50051"
@export var poll_interval: float = 0.05  # seconds between state polls (20 tps)

var current_state: State = State.IDLE
var _tick: int = 0
var _map_seed: int = 42


func _ready() -> void:
	# Polling timer
	var timer := Timer.new()
	timer.wait_time = poll_interval
	timer.one_shot = false
	timer.timeout.connect(_poll_state)
	add_child(timer)
	timer.stop()
	_timer = timer


func start_game(seed: int = 42, max_ticks: int = 10000) -> void:
	"""Connect to SimCore and start a new game."""
	_map_seed = seed
	current_state = State.CONNECTING

	# We use HTTP to talk to the gRPC gateway or direct Python subprocess.
	# For M1 we spawn SimCore as a subprocess and use its gRPC port.
	_launch_simcore_server()

	# Give the server a moment to start
	await get_tree().create_timer(1.0).timeout

	# Request initial state via Python subprocess (JSON over stdout)
	var result := await _call_python("start_game", {"seed": seed, "max_ticks": max_ticks})
	if result.is_empty():
		current_state = State.ERROR
		connection_lost.emit()
		return

	current_state = State.CONNECTED
	_tick = 0
	game_started.emit(result)
	_timer.start()


func submit_commands(commands: Array) -> void:
	"""Submit player commands for the next tick."""
	if current_state != State.CONNECTED:
		return
	await _call_python("step", {"commands": commands})


func get_health() -> Dictionary:
	"""Health check."""
	if current_state != State.CONNECTED:
		return {"healthy": false, "status": "disconnected"}
	var result := await _call_python("health", {})
	return result if result else {"healthy": false, "status": "error"}


# ─── Internal ────────────────────────────────────────────────

var _timer: Timer
var _server_pid: int = 0


func _launch_simcore_server() -> void:
	"""Launch SimCore gRPC server as a subprocess."""
	if _server_pid != 0:
		return
	var args := [
		"-m", "simcore.grpc_server",
		"--port", server_address.split(":")[1] if ":" in server_address else "50051",
	]
	_server_pid = OS.create_process("python3", args)
	push_warning("[GrpcBridge] SimCore server PID=%d started" % _server_pid)


func _poll_state() -> void:
	"""Called by timer: fetch latest state from SimCore."""
	if current_state != State.CONNECTED:
		return
	var result := await _call_python("get_state", {})
	if result.is_empty():
		current_state = State.ERROR
		connection_lost.emit()
		_timer.stop()
		return
	_tick = result.get("tick", _tick)
	state_updated.emit(result)


func _call_python(method: String, params: Dictionary) -> Dictionary:
	"""Call a Python helper script that talks gRPC and returns JSON."""
	var script_path := "res://scripts/py_bridge.py"
	var args := [script_path, server_address, method, JSON.stringify(params)]
	var output: Array = []
	var exit_code := OS.execute("python3", args, output)
	if exit_code != 0 or output.is_empty():
		return {}
	var json := JSON.new()
	if json.parse(output[0]) != OK:
		return {}
	return json.data


func _exit_tree() -> void:
	if _server_pid != 0:
		OS.kill(_server_pid)
		_server_pid = 0