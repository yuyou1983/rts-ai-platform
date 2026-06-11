extends SceneTree

## P1A headless test for SpriteLoader batch/visual_class query API.
## Validates that generated_manifest.json contains expected P1A core unit entries.

func _init() -> void:
	var loader = SpriteLoader.new()

	# 1. Assert get_batches() returns at least ["p0", "p1a_core_units"]
	var batches = loader.get_batches()
	assert(batches.has("p0"), "get_batches() must contain 'p0'")
	assert(batches.has("p1a_core_units"), "get_batches() must contain 'p1a_core_units'")
	print("[test] get_batches OK: %s" % str(batches))

	# 2. Assert get_visual_classes() contains at least the five required classes
	var vcs = loader.get_visual_classes()
	assert(vcs.has("small_ground"), "get_visual_classes() must contain 'small_ground'")
	assert(vcs.has("medium_ground"), "get_visual_classes() must contain 'medium_ground'")
	assert(vcs.has("large_ground"), "get_visual_classes() must contain 'large_ground'")
	assert(vcs.has("small_air"), "get_visual_classes() must contain 'small_air'")
	assert(vcs.has("large_air"), "get_visual_classes() must contain 'large_air'")
	print("[test] get_visual_classes OK: %s" % str(vcs))

	# 3. Assert get_assets_by_batch("p1a_core_units") has 10 or more entries
	var p1a_assets = loader.get_assets_by_batch("p1a_core_units")
	assert(p1a_assets.size() >= 10, "p1a_core_units batch must have >= 10 entries, got %d" % p1a_assets.size())
	print("[test] p1a_core_units batch OK: %d entries" % p1a_assets.size())

	# 4. Assert get_assets_by_visual_class("small_ground") contains an entry for "Firebat"
	var sg_assets = loader.get_assets_by_visual_class("small_ground")
	assert(sg_assets.has("Firebat"), "small_ground visual_class must contain 'Firebat'")
	print("[test] small_ground contains Firebat OK")

	# 5. Print success and quit
	print("✅ P1A SpriteLoader tests passed")
	quit()
