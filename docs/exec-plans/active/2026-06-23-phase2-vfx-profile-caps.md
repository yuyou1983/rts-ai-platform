# Phase 2: VFX Profiles + Active Effect Caps

**Created**: 2026-06-23

## Goal
Make combat visually readable — who's attacking, what hit where, what damage type — while capping active VFX to prevent FPS drops in dense 30v30 combat.

## Scope
- **Files to modify**: `godot/resources/vfx/vfx_catalog.json`, `godot/scripts/vfx_manager.gd`, `godot/scripts/game_view.gd`, `godot/resources/feel/control_feel_config.json`
- **Files to create**: `tests/godot/test_vfx_profiles.py`, `godot/scripts/test_vfx_catalog_profiles.gd`

## Phases

### Phase 1: VFX Profile Layer in Catalog
- [ ] Add `profiles` top-level section to `vfx_catalog.json` with 10 profiles: `terran_ballistic`, `terran_explosive`, `terran_flame`, `zerg_melee`, `zerg_acid`, `zerg_spore`, `protoss_psi`, `protoss_phase`, `building_hit`, `shield_hit`
- [ ] Each profile specifies: attack effect, hit effect, death effect, projectile behavior (hitscan/ballistic/melee/acid/psi), tracer style, priority
- [ ] Add `vfx_profile` field to `presentation_manifest.json` asset entries for all combat units
- [ ] New test: `tests/godot/test_vfx_profiles.py` — verify all profiles resolve, all combat units have vfx_profile, profile→effect chain valid
- **Validates with**: `python3 -m pytest tests/godot/test_vfx_profiles.py -q`

### Phase 2: Profile Lookup + Cap System in VFXManager
- [ ] Modify `vfx_manager.gd`: lookup by profile first, fallback to unit key
- [ ] Add `_max_active_effects` (default 64), `_max_projectiles` (default 32), `_max_death_effects` (default 16)
- [ ] Add `_active_count` tracking; spawn methods check caps and discard lowest-priority effects
- [ ] Load cap config from `control_feel_config.json` under `vfx_limits` key
- [ ] Wire game_view.gd damage/death detection to pass `vfx_profile` instead of raw unit_name
- **Validates with**: `python3 -m pytest tests/godot/ -q`

### Phase 3: Projectile/Tracer Rendering + Headless Test
- [ ] Add projectile state tracking: hitscan tracers (short line flash), ballistic (moving dot), melee (arc flash), acid (slow blob), psi (bright flash + shield ripple)
- [ ] `_draw_projectiles()` in VFXManager: render active projectiles per frame
- [ ] Aging + prune in `_process` for projectile entries
- [ ] Add `test_vfx_catalog_profiles.gd` headless Godot script
- [ ] Run full test suite
- **Validates with**: `python3 -m pytest tests/godot/ -q && /Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd`
