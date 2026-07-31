# SC1 Combat Differentiation QA

## Baseline
- Commit: 87ddbd8
- Godot version: v4.6.2.stable.official.71f334935
- SimCore combat tests: 74/74 PASS
- VFX profile tests: PASS
- Presentation verification: OK — manifest structure valid, atlas in bounds

## Test Counts (current)
- Python tests: **1430** PASS, 1 skipped, 0 failures
- Godot diagnostics tests: **51** PASS (Task 11 Test Mode combat diagnostics layer)
  - Headless slice script: `godot/scripts/test_sc1_combat_slice.gd -- --diagnostics`
  - 10 matchup presets: Marine/Zergling, Firebat splash, Vulture/Zealot,
    Tank 2-hit, Hydralisk, Mutalisk chain, Zealot 2-hit, Dragoon/Ultralisk,
    Templar storm, Reaver splash
- E2E integration tests: **6** PASS (Task 13)
  - Combat event pipeline, determinism (subprocess PYTHONHASHSEED), 3-race completeness

## Automated Gates
| Gate | Target | Result | Status |
|---|---:|---:|---|
| CombatEvent transport | 100% fields preserved | 100% | ✅ PASS (Task 5) |
| 12-unit weapon mapping | 12/12 | 12/12 | ✅ PASS (Task 2) |
| Counter matrix | exact | exact | ✅ PASS (Task 2) |
| Godot event pipeline | all event types | all event types | ✅ PASS (Task 6-7) |
| 30v30 VFX cap | no overflow | no overflow | ✅ PASS (Task 6) |
| 12-unit resource gate | 12/12 units | 12/12 units | ✅ PASS (Task 12) |

## Manual Gates
| Unit | attack animation | projectile | impact | timing | verdict |
|---|---|---|---|---|---|

## Task 2 — Semantic Weapons Catalog (commit: pending)

### Test Results
- `tests/simcore/test_sc1_representative_weapons.py`: 20/20 PASS
- `tests/simcore/test_combat.py`: 13/13 PASS (no regression)

### Balance Check

#### Damage Type Multiplier Matrix
| Type | Light | Medium | Heavy |
|---|---|---|---|
| normal | 1.0 | 1.0 | 1.0 |
| explosive | 0.5 | 0.75 | 1.0 |
| concussive | 1.0 | 0.5 | 0.25 |

#### 12 Units Base DPS (vs same-size target, no armor)
| Unit | Weapon | Dmg/Hit | Hits | Total | CD(ticks) | DPS |
|---|---|---|---|---|---|---|
| Marine | terran_c10_rifle | 6 | 1 | 6 | 6 | 10.0 |
| Firebat | terran_flame_thrower | 8 | 1 | 8 | 9 | 8.9 |
| Vulture | terran_fragmentation_grenade | 20 | 1 | 20 | 13 | 15.4 |
| Tank | terran_arclite_cannon | 20 | 2 | 40 | 9 | 44.4 |
| Zergling | zerg_claws | 5 | 1 | 5 | 3 | 16.7 |
| Hydralisk | zerg_needle_spines | 10 | 1 | 10 | 6 | 16.7 |
| Mutalisk | zerg_glave_wurm | 9 | 1 | 9 | 13 | 6.9 |
| Ultralisk | zerg_kaiser_blades | 20 | 1 | 20 | 6 | 33.3 |
| Zealot | protoss_psi_blades | 8 | 2 | 16 | 9 | 17.8 |
| Dragoon | protoss_phase_disruptor | 20 | 1 | 20 | 13 | 15.4 |
| Templar | protoss_psionic_storm | 112 | 1 | 112 | 19 | 58.9 |
| Reaver | protoss_scarab | 20 | 1 | 20 | 9 | 22.2 |

#### Mutalisk 3-Chain Total Theoretical Damage
- Base damage per hit: 9
- Chain fractions: [1.0, 0.333333, 0.111111]
- Total: 9×1.0 + 9×0.333 + 9×0.111 = **13.00**

#### Zealot Dual-Hit Total Damage
- Damage per hit: 8, Hit count: 2, Total: **16**

#### Splash Profiles
| Weapon | Splash Profile |
|---|---|
| terran_arclite_cannon | none |
| terran_flame_thrower | radial |
| protoss_scarab | radial |

### Runtime Changes
- `_meta.engine_tps`: 20 → 10 (matches SimCore.tick_rate=10.0)
- Cooldown formula: `round(sc1_frames * 10 / 23.81)`
- 12 units updated: weapon_id_ground/air/spell, attack, cooldown, armor_type
- All changes limited to the 12 representative units; other units and global tick rate unchanged

## Tasks 7–11 — Completion Status

| Task | Scope | Commit | Status |
|---|---|---|---|
| 7 | Weapon visual catalog wired into combat event pipeline | 67c7dda | ✅ DONE |
| 7A | Unified combat resolution (`combat_resolution.py`) | 02bbf80, 13312d0 | ✅ DONE |
| 8 | Terran 4-unit closure + SC1 shield fix | 41698d3 | ✅ DONE |
| 9 | Zerg 4-unit closure + Mutalisk chain bounce | 75dd70d | ✅ DONE |
| 10 | Protoss 4-unit closure + multi-hit loop | 6f4fe61 | ✅ DONE |
| 11 | Test Mode diagnostics layer (51 Godot tests pass) | ec92860 | ✅ DONE |

### Task 7 — Weapon visual catalog → combat event pipeline
- `godot/resources/vfx/weapon_visual_catalog.json`: 12 per-weapon visual mappings
  (8 required fields each: animation_action, launch_effect, projectile_style,
  impact_effect, shield_impact_effect, death_effect, audio_cue, priority).
- `godot/scripts/vfx_manager.gd`: `spawn_weapon_event(event, visual)` dispatches on
  `projectile_style`; loads catalog at `_ready` via `_load_weapon_visual_catalog`;
  handles `spell_resolved` event type for Templar; retains legacy
  `spawn_combat_event` fallback.
- `godot/scripts/combat_visual_controller.gd`: calls `spawn_weapon_event` when a
  weapon visual is available, looks up via `get_weapon_visual`, retains
  `spawn_combat_event` as fallback; `_handle_spell_resolved` sets `weapon_id`
  so the weapon visual lookup succeeds for spells (psionic storm).

### Task 7A — Unified combat resolution
- `simcore/engine/combat_resolution.py`: single `resolve_weapon_impact` entry point
  computing damage multiplier (damage_type × armor_type), shield→health
  overflow, splash fraction, and chain index.
- Projectile damage routed through the unified resolver; all 12 weapons and
  spells share the same multiplier/shield logic.

### Task 8 — Terran 4-unit closure + SC1 shield fix
- Marine, Firebat, Vulture, Tank combat scenarios pass.
- SC1 shield mechanic fixed: damage hits shields first, overflow to health;
  multiplier applies to the post-shield portion consistently.

### Task 9 — Zerg 4-unit closure + Mutalisk chain bounce
- Zergling, Hydralisk, Mutalisk, Ultralisk combat scenarios pass.
- Mutalisk glave wurm 3-chain bounce implemented: chain fractions
  [1.0, 0.333, 0.111], total 13.00.

### Task 10 — Protoss 4-unit closure + multi-hit loop
- Zealot, Dragoon, Templar, Reaver combat scenarios pass.
- Multi-hit loop: Tank (hit_count=2) and Zealot (hit_count=2) resolve multiple
  impacts per attack tick through the unified resolver.

### Task 11 — Test Mode diagnostics layer
- `godot/scripts/combat_diagnostics_overlay.gd`: PanelContainer + RichTextLabel
  overlay showing attacker/target, weapon/armor type, base damage, multiplier,
  shield/health damage, splash fraction, chain index, tick/event ID. Only
  visible in Test Mode, never in normal games.
- `godot/scripts/test_sc1_combat_slice.gd`: headless diagnostics runner, 10
  matchup presets, **51/51 diagnostics tests pass**.
- `godot/scripts/test_mode_gallery.gd`: 10 matchup preset buttons in the combat
  gallery mode, wires diagnostics overlay to combat events.

## Task 12 — 12-Unit Resource Gate Results

### Gate Summary
| Check | Scope | Result |
|---|---|---|
| presentation_manifest.unit_visuals | 12 combat units | 12/12 ✅ |
| sprite_frames_config.units | 12 combat units | 12/12 ✅ |
| Non-Templar `attack` animation >0 frames | 11 units | 11/11 ✅ |
| Templar `cast` animation >0 frames | 1 unit | 1/1 ✅ (3 frames) |
| On-disk asset PNGs (godot/assets/sprites/units/) | 12 units | 12/12 ✅ |
| weapon_visual_catalog IDs ↔ weapons.json IDs | 12 weapons | 12/12 ✅ (bijective) |
| catalog weapon_id ↔ manifest unit weapon_id | 12 mappings | 12/12 ✅ |

### Per-Unit Animation Inventory
| Unit | Weapon ID | attack frames | cast frames | asset on disk |
|---|---|---:|---:|---|
| Marine | terran_c10_rifle | 7 | — | ✅ |
| Firebat | terran_flame_thrower | 4 | — | ✅ |
| Vulture | terran_fragmentation_grenade | 4 | — | ✅ |
| Tank | terran_arclite_cannon | 4 | — | ✅ |
| Zergling | zerg_claws | 5 | — | ✅ |
| Hydralisk | zerg_needle_spines | 4 | — | ✅ |
| Mutalisk | zerg_glave_wurm | 4 | — | ✅ |
| Ultralisk | zerg_kaiser_blades | 4 | — | ✅ |
| Zealot | protoss_psi_blades | 5 | — | ✅ |
| Dragoon | protoss_phase_disruptor | 4 | — | ✅ |
| Templar | protoss_psionic_storm | — | 3 | ✅ |
| Reaver | protoss_scarab | 4 | — | ✅ |

### Verification Commands
```bash
# Python resource-gate tests
python -m pytest tests/godot/test_weapon_visual_catalog.py \
    tests/godot/test_presentation_manifest.py -v --tb=short -n 1

# Standalone presentation/asset verifier (exits non-zero on missing critical resource)
python3 scripts/verify_presentation_scene.py
```

### Verification Output
- `tests/godot/test_weapon_visual_catalog.py::TestResourceGate`: 7/7 PASS
- `scripts/verify_presentation_scene.py`: OK — 12-unit combat resource gate
  passed (all visual/sprite/asset/weapon IDs OK), exits 0.

## Known Gaps

### Templar original extraction assets
- The Templar sprite PNG (`godot/assets/sprites/units/Templar.png`) exists and
  defines a `cast` animation (3 frames), but the **original SC1 extraction**
  animation frames for Templar are incomplete relative to the other 11 units.
- Templar has no `attack` animation (by design — it casts `protoss_psionic_storm`,
  a spell, so the weapon visual catalog maps `animation_action: "cast"`).
- The 3-frame `cast` animation is a minimal placeholder; richer original
  extraction frames (casting channel/follow-through) are not yet wired.
- Impact: gameplay and diagnostics are unaffected (cast animation >0 frames
  satisfies the resource gate); only visual richness is reduced.

### Open items
- Manual gate table (per-unit attack/projectile/impact/timing verdicts) is
  still pending visual review against the Godot frontend.
- Task 2 commit hash remains "pending" pending the final squash/merge.
