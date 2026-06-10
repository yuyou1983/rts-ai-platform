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

enum State { IDLE, CONNECTING, CONNECTED, ERROR }
enum PollMode { STEP, GET_STATE }

@export var http_address: String = "http://localhost:8080"
@export var poll_interval: float = 0.1  # 10 tps (slower for readability)

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
	current_state = State.CONNECTING
	_request_id = "start_game"
	var p1_race: String = "terran"
	var p2_race: String = "terran"
	# Pick up race selections from Engine metadata (set by main_menu)
	if Engine.has_meta("p1_race"):
		p1_race = Engine.get_meta("p1_race")
	if Engine.has_meta("p2_race"):
		p2_race = Engine.get_meta("p2_race")
	var body := JSON.stringify({
		"seed": seed,
		"max_ticks": max_ticks,
		"ai_player": ai_player,
		"ai_difficulty": ai_difficulty,
		"enable_elevation": enable_elevation,
		"player_races": {"1": p1_race, "2": p2_race},
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