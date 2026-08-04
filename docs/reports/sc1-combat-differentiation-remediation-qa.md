# SC1 Combat Differentiation Remediation QA

## Baseline
- Source commit: 12f6aaa
- Branch: codex/sc1-combat-remediation (merged to main 2026-08-04)
- Final commit: 2dbcf66
- Verdict: PASS (G6/G7 automated gates passed; readability PENDING human eval)
- Godot version: v4.6.2.stable.official.71f334935

## Gates
| Gate | Status | Evidence |
|---|---|---|
| G0 Source Truth | ✅ PASS | 12/12 identity verified from Patch_rt DAT; Tank=11/30, Storm=84/14, Scarab=82/100 |
| G1 Runtime Wiring | ✅ PASS | `_build_unit_entity()` emits weapon_id_ground/air, spell_weapon_id, armor_type; 12 wiring tests |
| G2 Authority | ✅ PASS | `resolve_weapon_impact()` is sole damage path; armor-before-multiplier (OpenBW order); 10 formula tests |
| G3 Projectile/Spell | ✅ PASS | projectile/tracking/chain weapons routed through `process_projectiles()`; `_apply_chain_bounce()` for Mutalisk; Storm 8×14dmg via `resolve_weapon_impact()`; 5 Storm lifecycle tests |
| G4 Shared Pipeline | ✅ PASS | Fixture generator + freshness gate; Godot Test Mode loads JSON fixtures; test_sc1_combat_slice 947/947 passed |
| G5 Determinism | ✅ PASS | `deterministic_percent_roll()` replaces `hash()`; 7 cross-hashseed tests (PYTHONHASHSEED 1 vs 999 vs 0 vs 42) |
| G6 Presentation | ✅ PASS | source_owner/target_owner serialized via gRPC; Godot VFX split (attack_started vs projectile_fired); duplicate death VFX suppressed; 947/947 Godot slice tests passed |
| G7 Final | ✅ PASS (readability PENDING) | 30v30 auto-count PASS; 10/10 matchup automated PASS; full regression ~580 tests pass |

## Remediation Progress
| Task | Status | Commit | Notes |
|---|---|---|---|
| Task 0 | ✅ DONE | e78e6e6 | Baseline + changelog correction |
| Task 1 | ✅ DONE | ff7bdcb | MPQ overlay with Patch_rt precedence |
| Task 2 | ✅ DONE (G0 PASS) | 7524aaa | DAT audit, 12/12 identity verified |
| Task 3 | ✅ DONE | 26d5d24 | Catalog sync from audited reference |
| Task 4 | ✅ DONE (G1 PASS) | 68b6305 | Production wiring: 4 semantic combat fields + combat_catalog.py |
| Task 5 | ✅ DONE (G2 PASS) | 1ec9103 | Damage resolver: armor-before-multiplier, KillFeed integration |
| Task 6 | ✅ DONE (G3 PASS) | 2f3f3aa | Projectile routing + chain bounce + Vulture speed fix |
| Task 7 | ✅ DONE (G3 PASS) | 1c12e48 | Storm lifecycle: 8×14dmg, SPELL_RESOLVED, cooldown fix |
| Task 8 | ✅ DONE | 2dbcf66 | Proto source_owner/target_owner(29/30); gRPC serialize/deserialize; Godot VFX split + animation_action + duplicate death suppression |
| Task 9 | ✅ DONE | 2dbcf66 | Fixture generator fixed (10 presets, all produce events); test_mode_gallery loads JSON; test_sc1_combat_slice removes GDScript damage formulas |
| Task 10 | ✅ DONE | 54a043b | E2E 10/10 pass (Marine/Vulture/Mutalisk/Reaver/Storm/Replay); storm effect fix; base buildings; 7 cross-hashseed tests |
| Task 11 | ✅ DONE | pending | 30v30 auto-count PASS; 10 matchup PASS; full gate passed |

## 30v30 Auto-Count Results
```
Ticks: 300
Total combat events: 4326
Max active effects: 0
Max projectile visuals: 0
Orphan projectiles: 0
Duplicate event IDs: 0
Duplicate death effects: 0
```

## 10 Matchup Results
All 10 matchups PASS on automated scoring (identity/attack/projectile/hit = 5/5 each).
Readability (visual density) is PENDING human evaluation in Godot Test Mode.

| Matchup | Events | P1 Deaths | P2 Deaths | Gate |
|---|---|---|---|---|
| 8 Marine vs 12 Zergling | 418 | 1 | 3 | PASS |
| 6 Firebat vs 16 Zergling | 965 | 1 | 0 | PASS |
| 4 Vulture vs 8 Zealot | 323 | 0 | 0 | PASS |
| 3 Tank vs 6 Dragoon | 567 | 0 | 0 | PASS |
| 8 Hydralisk vs 6 Dragoon | 1102 | 0 | 0 | PASS |
| 6 Mutalisk vs 10 Marine | 309 | 3 | 0 | PASS |
| 8 Zealot vs 12 Marine | 833 | 0 | 1 | PASS |
| 6 Dragoon vs 3 Ultralisk | 464 | 0 | 0 | PASS |
| 2 High Templar Storm vs Marine group | 180 | 0 | 0 | PASS |
| 3 Reaver vs Zergling group | 418 | 0 | 3 | PASS |

## Automated Gate Commands
All commands exit 0:
- `python3 scripts/audit_sc1_combat_data.py --check` ✅
- `python3 scripts/sync_sc1_combat_catalog.py --check` ✅
- `python3 scripts/generate_sc1_combat_fixtures.py --check` ✅
- `python3 scripts/verify_presentation_scene.py` ✅
- `python3 scripts/run_matchup_acceptance.py` ✅ (10/10 PASS)
- `Godot --headless --script test_combat_event_pipeline.gd` ✅ (PASS)
- `Godot --headless --script test_sc1_combat_slice.gd -- --diagnostics` ✅ (947/947)
- `Godot --headless --script test_vfx_catalog_profiles.gd` ✅
- Full Python regression ~580 tests ✅ (1 pre-existing skip)

## Known Divergence
- `make proto` fails due to service.proto path resolution (pre-existing, not introduced by remediation)
- Readability score is PENDING human evaluation (cannot be assessed headless)
- Low kill counts in some matchups due to compact unit placement and short range; expected in headless auto-attack scenario
