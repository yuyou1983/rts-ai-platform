class_name AudioManager
extends Node

## Central audio system for the RTS game.
## Handles unit voices, SFX, and ambient audio.

# ── Bus layout ──
# Master
#   ├─ SFX
#   ├─ Voice  
#   └─ Ambient

var _voice_players: Array[AudioStreamPlayer] = []
var _sfx_players: Array[AudioStreamPlayer] = []
var _ambient_player: AudioStreamPlayer = null
var _cache: Dictionary = {}  # path → AudioStream

const MAX_VOICE := 2
const MAX_SFX := 8
const VOICE_COOLDOWN := 0.3  # seconds between same-unit voice lines

var _last_voice_time: Dictionary = {}  # unit_name → timestamp

func _ready() -> void:
	# Create audio buses if they don't exist
	if not AudioServer.get_bus_count() > 0:
		AudioServer.add_bus()  # Master (0)
	if AudioServer.get_bus_count() < 2:
		AudioServer.add_bus()  # SFX (1)
		AudioServer.set_bus_name(1, "SFX")
		AudioServer.set_bus_send(1, "Master")
	if AudioServer.get_bus_count() < 3:
		AudioServer.add_bus()  # Voice (2)
		AudioServer.set_bus_name(2, "Voice")
		AudioServer.set_bus_send(2, "Master")
	if AudioServer.get_bus_count() < 4:
		AudioServer.add_bus()  # Ambient (3)
		AudioServer.set_bus_name(3, "Ambient")
		AudioServer.set_bus_send(3, "Master")
	
	for i in range(MAX_VOICE):
		var p := AudioStreamPlayer.new()
		p.bus = "Voice"
		add_child(p)
		_voice_players.append(p)
	
	for i in range(MAX_SFX):
		var p := AudioStreamPlayer.new()
		p.bus = "SFX"
		add_child(p)
		_sfx_players.append(p)
	
	_ambient_player = AudioStreamPlayer.new()
	_ambient_player.bus = "Ambient"
	add_child(_ambient_player)

func _get_stream(path: String) -> AudioStream:
	if _cache.has(path):
		return _cache[path]
	if not ResourceLoader.exists(path):
		return null
	var stream = ResourceLoader.load(path)
	if stream:
		_cache[path] = stream
	return stream

func _get_idle_player(pool: Array) -> AudioStreamPlayer:
	for p in pool:
		if not p.playing:
			return p
	return null

# ── Public API ──

## Play a unit voice line (e.g., Zergling_selected, Marine_moving)
func play_unit_voice(unit_name: String, action: String) -> void:
	var key := "%s_%s" % [unit_name, action]
	var now := Time.get_ticks_msec() / 1000.0
	if _last_voice_time.get(key, 0.0) + VOICE_COOLDOWN > now:
		return
	_last_voice_time[key] = now
	var path := "res://assets/audio/units/%s_%s.wav" % [unit_name, action]
	var stream := _get_stream(path)
	if stream == null:
		return
	var player := _get_idle_player(_voice_players)
	if player:
		player.stream = stream
		player.play()

## Play a gameplay SFX
func play_sfx(path: String, volume_db: float = 0.0) -> void:
	var stream := _get_stream(path)
	if stream == null:
		return
	var player := _get_idle_player(_sfx_players)
	if player:
		player.stream = stream
		player.volume_db = volume_db
		player.play()

## Play building construction sound
func play_build_sound(building_type: String) -> void:
	play_sfx("res://assets/audio/sfx/Terran_build.wav" if building_type.find("Terran") >= 0 or building_type in ["SupplyDepot", "Barracks", "Factory", "CommandCenter"] else "res://assets/audio/sfx/Protoss_build.wav" if building_type in ["Pylon", "Gateway", "Nexus", "Assimilator", "Forge", "CyberneticsCore"] else "res://assets/audio/sfx/Zerg_build.wav")

## Play attack sound
func play_attack_sound(unit_name: String) -> void:
	play_unit_voice(unit_name, "attack")

## Play selection sound
func play_selection_sound(unit_name: String) -> void:
	play_unit_voice(unit_name, "selected")

## Play death sound for unit
func play_death_sound(unit_name: String) -> void:
	play_sfx("res://assets/audio/units/%s_death.wav" % unit_name)

## Set ambient track
func set_ambient(path: String) -> void:
	var stream := _get_stream(path)
	if stream and _ambient_player:
		_ambient_player.stream = stream
		_ambient_player.play()

## Stop ambient
func stop_ambient() -> void:
	if _ambient_player:
		_ambient_player.stop()

## Set bus volume (bus_index: 0=Master, 1=SFX, 2=Voice, 3=Ambient)
func set_bus_volume(bus_idx: int, volume_db: float) -> void:
	if bus_idx >= 0 and bus_idx < AudioServer.get_bus_count():
		AudioServer.set_bus_volume_db(bus_idx, volume_db)