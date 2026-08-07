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

signal replay_loaded(replay_data: Dictionary)
signal replay_list_loaded(replay_data: Dictionary)
signal league_ranking_loaded(ranking: Dictionary)
signal league_match_completed(result: Dictionary)
signal league_result_submitted(response: Dictionary)

## Emitted when the local backend bootstrap fails.  The frontend must show
## a visible error state instead of entering an empty GameView.
signal bootstrap_failed(reason: String)

enum State { IDLE, CONNECTING, CONNECTED, ERROR }
enum PollMode { STEP, GET_STATE }

@export var http_address: String = "http://localhost:8080"
@export var poll_interval: float = 0.1  # 10 tps (slower for readability)

## gRPC and HTTP ports used for local backend bootstrap readiness checks.
@export var grpc_port: int = 50051
@export var http_port: int = 8080

## When true (development default), Start Game will launch the local
## SimCore gRPC + HTTP helper if the backend is absent.  Set false in
## export/release builds so published clients never spawn subprocesses.
@export var enable_local_bootstrap: bool = true

## Bounded timeout (milliseconds) for waiting on backend readiness.
@export var bootstrap_timeout_msec: int = 12000

## STEP = send commands + advance tick (default)
@export var poll_mode: PollMode = PollMode.STEP

## Which player is AI-controlled (0=none, 1 or 2). Set before start_game().
@export var ai_player: int = 2

## AI difficulty: "easy", "medium", "hard". Affects APM throttle, production caps, micro.
@export var ai_difficulty: String = "medium"

## Phase D: enable terrain elevation system (height_map + speed/vision modifiers)
@export var enable_elevation: bool = true

var current_state: State = State.IDLE
var _tick: int = 0
var _winner: int = 0
var _is_terminal: bool = false
var selected_units: PackedStringArray = PackedStringArray()
var _pending_commands: Array = []

# ─── Backend bootstrap state ───────────────────────────────────
var _owned_backend_pid: int = -1
var _bootstrap_retried: bool = false
var _start_game_retried: bool = false
var _start_game_seed: int = 42
var _start_game_max_ticks: int = 10000


func _ready() -> void:
	_http = HTTPRequest.new()
	_http.request_completed.connect(_on_request_completed)
	add_child(_http)
	# Second HTTPRequest for non-polling requests (replay, league)
	_http_extra = HTTPRequest.new()
	_http_extra.request_completed.connect(_on_extra_request_completed)
	add_child(_http_extra)
	_poll_timer = Timer.new()
	_poll_timer.wait_time = poll_interval
	_poll_timer.one_shot = false
	_poll_timer.timeout.connect(_poll_state)
	add_child(_poll_timer)
	_poll_timer.stop()


func start_game(seed: int = 42, max_ticks: int = 10000) -> void:
	_start_game_seed = seed
	_start_game_max_ticks = max_ticks
	_attempt_start_game()


## Ensure the backend is reachable, bootstrapping it if necessary, then
## send the start_game HTTP request.  This is the single entry point for
## both the initial attempt and the one controlled retry.
func _attempt_start_game() -> void:
	current_state = State.CONNECTING
	# ── Proactive readiness check + bootstrap ──
	if not _is_port_open(http_port):
		if enable_local_bootstrap and not _bootstrap_retried:
			var err := _try_bootstrap_backend()
			_bootstrap_retried = true
			if not err.is_empty():
				push_error("[GrpcBridge] Backend bootstrap failed: %s" % err)
				bootstrap_failed.emit(err)
				current_state = State.ERROR
				return
		elif not enable_local_bootstrap:
			var reason := "Backend not available on port %d and local bootstrap is disabled" % http_port
			push_error("[GrpcBridge] %s" % reason)
			bootstrap_failed.emit(reason)
			current_state = State.ERROR
			return
		else:
			var reason := "Backend did not become ready after bootstrap attempt"
			push_error("[GrpcBridge] %s" % reason)
			bootstrap_failed.emit(reason)
			current_state = State.ERROR
			return
	_send_start_game_request()


## Send the actual HTTP POST to /api/start_game.
func _send_start_game_request() -> void:
	_request_id = "start_game"
	var p1_race: String = "terran"
	var p2_race: String = "terran"
	# Pick up race selections from Engine metadata (set by main_menu)
	if Engine.has_meta("p1_race"):
		p1_race = Engine.get_meta("p1_race")
	if Engine.has_meta("p2_race"):
		p2_race = Engine.get_meta("p2_race")
	var body := JSON.stringify({
		"seed": _start_game_seed,
		"max_ticks": _start_game_max_ticks,
		"ai_player": ai_player,
		"ai_difficulty": ai_difficulty,
		"enable_elevation": enable_elevation,
		"player_races": {"1": p1_race, "2": p2_race},
	})
	var url := http_address + "/api/start_game"
	var err := _http.request(url, ["Content-Type: application/json"], HTTPClient.METHOD_POST, body)
	if err != OK:
		push_error("[GrpcBridge] HTTP request failed: %d" % err)
		# One controlled retry: try to bootstrap and resend
		if not _start_game_retried:
			_start_game_retried = true
			call_deferred("_attempt_start_game")
			return
		current_state = State.ERROR
		bootstrap_failed.emit("HTTP request creation failed (error %d)" % err)
		connection_lost.emit()


func submit_commands(commands: Array) -> void:
	"""Buffer player commands for next tick."""
	_pending_commands.append_array(commands)


# ─── Internal ────────────────────────────────────────────────
var _poll_timer: Timer
var _http: HTTPRequest
var _http_extra: HTTPRequest
var _request_id: String = ""
var _extra_request_id: String = ""


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
			# One controlled retry: bootstrap if needed and resend
			if not _start_game_retried:
				_start_game_retried = true
				_request_id = ""
				# If port is down, try to bootstrap before retrying
				if not _is_port_open(http_port) and enable_local_bootstrap and not _bootstrap_retried:
					var berr := _try_bootstrap_backend()
					_bootstrap_retried = true
					if not berr.is_empty():
						push_error("[GrpcBridge] Backend bootstrap failed on retry: %s" % berr)
						bootstrap_failed.emit(berr)
						current_state = State.ERROR
						return
				call_deferred("_attempt_start_game")
				return
			push_error("[GrpcBridge] start_game failed (HTTP %d)" % code)
			current_state = State.ERROR
			bootstrap_failed.emit("Start Game failed (HTTP %d) after retry" % code)
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
	_kill_owned_backend()


# ─── Backend bootstrap helpers ────────────────────────────────

## Check whether a TCP port on localhost is accepting connections.
func _is_port_open(port: int, timeout_msec: int = 500) -> bool:
	var peer := StreamPeerTCP.new()
	var err := peer.connect_to_host("127.0.0.1", port)
	if err != OK:
		return false
	var start := Time.get_ticks_msec()
	while Time.get_ticks_msec() - start < timeout_msec:
		peer.poll()
		var status := peer.get_status()
		if status == StreamPeerTCP.STATUS_CONNECTED:
			peer.disconnect_from_host()
			return true
		if status != StreamPeerTCP.STATUS_CONNECTING:
			peer.disconnect_from_host()
			return false
		OS.delay_msec(20)
	peer.disconnect_from_host()
	return false


## Launch the local backend helper script and wait for readiness.
## Returns an empty string on success, or an error message on failure.
func _try_bootstrap_backend() -> String:
	var script_path := ""
	if OS.has_environment("RTS_FRONTEND_BACKEND_SCRIPT"):
		script_path = OS.get_environment("RTS_FRONTEND_BACKEND_SCRIPT")
	else:
		script_path = ProjectSettings.globalize_path("res://scripts/run_frontend_backend.sh")
	if not FileAccess.file_exists(script_path):
		return "Helper script not found: " + script_path
	# Use OS.create_process with an argument array — never a shell string.
	# Ports and parent PID are internal values, not user input.
	var args := PackedStringArray([
		script_path,
		str(grpc_port),
		str(http_port),
		str(OS.get_process_id()),
	])
	_owned_backend_pid = OS.create_process("/bin/bash", args, false)
	if _owned_backend_pid < 0:
		return "Failed to launch helper process (create_process returned %d)" % _owned_backend_pid
	# Wait for readiness with a bounded timeout
	var start := Time.get_ticks_msec()
	while Time.get_ticks_msec() - start < bootstrap_timeout_msec:
		if _is_port_open(http_port, 300):
			return ""  # Ready
		OS.delay_msec(200)
	return "Backend did not become ready within %d ms" % bootstrap_timeout_msec


## Kill only the backend process this bridge launched.  Externally
## managed services are never touched.  We kill the process group
## (negative PID) so that child Python processes are also terminated.
func _kill_owned_backend() -> void:
	if _owned_backend_pid > 0:
		# Kill the process group (negative PID) to ensure child
		# processes (gRPC server, HTTP gateway) are also terminated.
		OS.kill(-_owned_backend_pid)
		OS.kill(_owned_backend_pid)
		_owned_backend_pid = -1


# ─── Replay & League API ─────────────────────────────────────

func fetch_replay(match_id: String) -> void:
	_extra_request_id = "replay"
	_http_extra.request(http_address + "/api/replay/" + match_id, ["Content-Type: application/json"], HTTPClient.METHOD_GET, "")

func fetch_replay_list() -> void:
	_extra_request_id = "replay_list"
	_http_extra.request(http_address + "/api/replay/list", ["Content-Type: application/json"], HTTPClient.METHOD_GET, "")

func fetch_replay_download(filename: String) -> void:
	_extra_request_id = "replay_download"
	_http_extra.request(http_address + "/api/replay/download/" + filename, ["Content-Type: application/json"], HTTPClient.METHOD_GET, "")

func fetch_league_ranking() -> void:
	_extra_request_id = "league_ranking"
	_http_extra.request(http_address + "/api/league/ranking", ["Content-Type: application/json"], HTTPClient.METHOD_GET, "")

func request_league_match(p1_version: String, p2_version: String, map_seed: int = 42, max_ticks: int = 5000) -> void:
	_extra_request_id = "league_match"
	var body := JSON.stringify({"p1_version": p1_version, "p2_version": p2_version, "map_seed": map_seed, "max_ticks": max_ticks})
	_http_extra.request(http_address + "/api/league/match", ["Content-Type: application/json"], HTTPClient.METHOD_POST, body)

func submit_league_result(p1_version: String, p2_version: String, winner: int, ticks: int) -> void:
	_extra_request_id = "league_submit"
	var body := JSON.stringify({"p1_version": p1_version, "p2_version": p2_version, "winner": winner, "ticks": ticks})
	_http_extra.request(http_address + "/api/league/submit_result", ["Content-Type: application/json"], HTTPClient.METHOD_POST, body)


func _on_extra_request_completed(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if code != 200 or body.is_empty():
		push_warning("[GrpcBridge] extra request '%s' failed (HTTP %d)" % [_extra_request_id, code])
		_extra_request_id = ""
		return

	var json_parser := JSON.new()
	if json_parser.parse(body.get_string_from_utf8()) != OK:
		_extra_request_id = ""
		return
	var data: Dictionary = json_parser.data if json_parser.data else {}

	match _extra_request_id:
		"replay":
			replay_loaded.emit(data)
		"replay_list":
			replay_list_loaded.emit(data)
		"replay_download":
			# Parse JSONL into ticks format for replay player
			var raw_text: String = body.get_string_from_utf8()
			var ticks: Array = []
			for line in raw_text.split("\n"):
				line = line.strip_edges()
				if line.is_empty():
					continue
				var line_json := JSON.new()
				if line_json.parse(line) == OK and line_json.data is Dictionary:
					var d: Dictionary = line_json.data
					if d.get("type") == "header":
						continue  # skip header line
					ticks.append(d)
			# Convert to format expected by ReplayPlayer
			var replay_data := {
				"match_id": data.get("match_id", ""),
				"tick_count": ticks.size(),
				"ticks": ticks,
			}
			replay_loaded.emit(replay_data)
		"league_ranking":
			league_ranking_loaded.emit(data)
		"league_match":
			league_match_completed.emit(data)
		"league_submit":
			league_result_submitted.emit(data)
		_:
			pass
	_extra_request_id = ""