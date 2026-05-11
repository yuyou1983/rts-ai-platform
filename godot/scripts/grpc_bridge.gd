class_name GrpcBridge
extends Node

## Bridge between Godot frontend and SimCore HTTP gateway.
##
## Uses Godot's native HTTPRequest node — no subprocess, no Python dependency.
## The SimCore HTTP gateway must be running:
##   python3 -m simcore.http_gateway --grpc-port 50051 --http-port 8080
##
## STEP mode: send commands + advance tick (default).
## The gateway auto-injects AI commands for the configured ai_player.

signal game_started(initial_state: Dictionary)
signal state_updated(state: Dictionary)
signal connection_lost()
signal game_over(winner: int, tick: int)

enum State { IDLE, CONNECTING, CONNECTED, ERROR }
enum PollMode { STEP, GET_STATE }

@export var http_address: String = "http://localhost:8080"
@export var poll_interval: float = 0.05  # 20 tps

## STEP = send commands + advance tick (default)
@export var poll_mode: PollMode = PollMode.STEP

## Which player is AI-controlled (0=none, 1 or 2). Set before start_game().
@export var ai_player: int = 2

var current_state: State = State.IDLE
var _tick: int = 0
var _winner: int = 0
var _is_terminal: bool = false
var selected_units: PackedStringArray = PackedStringArray()
var _pending_commands: Array = []


func _ready() -> void:
	_http = HTTPRequest.new()
	_http.request_completed.connect(_on_request_completed)
	add_child(_http)
	_poll_timer = Timer.new()
	_poll_timer.wait_time = poll_interval
	_poll_timer.one_shot = false
	_poll_timer.timeout.connect(_poll_state)
	add_child(_poll_timer)
	_poll_timer.stop()


func start_game(seed: int = 42, max_ticks: int = 10000) -> void:
	current_state = State.CONNECTING
	_request_id = "start_game"
	var body := JSON.stringify({
		"seed": seed,
		"max_ticks": max_ticks,
		"ai_player": ai_player,
	})
	var url := http_address + "/api/start_game"
	var err := _http.request(url, ["Content-Type: application/json"], HTTPClient.METHOD_POST, body)
	if err != OK:
		push_error("[GrpcBridge] HTTP request failed: %d" % err)
		current_state = State.ERROR
		connection_lost.emit()


func submit_commands(commands: Array) -> void:
	"""Buffer player commands for next tick."""
	_pending_commands.append_array(commands)


# ─── Internal ────────────────────────────────────────────────
var _poll_timer: Timer
var _http: HTTPRequest
var _request_id: String = ""


func _poll_state() -> void:
	"""Called by timer: fetch state (and optionally advance tick)."""
	if current_state != State.CONNECTED:
		return
	if _is_terminal:
		_poll_timer.stop()
		return
	if _http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		return  # previous request still pending, skip this tick

	if poll_mode == PollMode.STEP:
		var body := JSON.stringify({"commands": _pending_commands})
		_pending_commands.clear()
		_request_id = "step"
		_http.request(http_address + "/api/step", ["Content-Type: application/json"], HTTPClient.METHOD_POST, body)
	else:
		_request_id = "get_state"
		_http.request(http_address + "/api/get_state", ["Content-Type: application/json"], HTTPClient.METHOD_POST, "{}")


func _on_request_completed(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if code != 200 or body.is_empty():
		if _request_id == "start_game":
			push_error("[GrpcBridge] start_game failed (HTTP %d)" % code)
			current_state = State.ERROR
			connection_lost.emit()
		_request_id = ""
		return

	var json_parser := JSON.new()
	if json_parser.parse(body.get_string_from_utf8()) != OK:
		_request_id = ""
		return
	var data: Dictionary = json_parser.data if json_parser.data else {}

	match _request_id:
		"start_game":
			current_state = State.CONNECTED
			_tick = 0
			_is_terminal = data.get("is_terminal", false)
			_winner = data.get("winner", 0)
			game_started.emit(data)
			_poll_timer.start()
		"step", "get_state":
			_tick = data.get("tick", _tick)
			_is_terminal = data.get("is_terminal", false)
			_winner = data.get("winner", 0)
			state_updated.emit(data)
			if _is_terminal:
				_poll_timer.stop()
				game_over.emit(_winner, _tick)
		_:
			pass
	_request_id = ""


func _exit_tree() -> void:
	pass