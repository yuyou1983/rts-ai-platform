# SC1 Combat Differentiation Remediation QA

## Baseline
- Source commit: 12f6aaa
- Branch: codex/sc1-combat-remediation (from codex/sc1-combat-differentiation)
- Verdict: IN PROGRESS
- Reason: Python-side remediation Tasks 0-10 complete; Godot-side (Task 8 Step 3-6, Task 9 Step 4-5) and final QA (Task 11) pending

## Gates
| Gate | Status | Evidence |
|---|---|---|
| G0 Source Truth | ✅ PASS | 12/12 identity verified from Patch_rt DAT; Tank=11/30, Storm=84/14, Scarab=82/100 |
| G1 Runtime Wiring | ✅ PASS | `_build_unit_entity()` emits weapon_id_ground/air, spell_weapon_id, armor_type; 12 wiring tests |
| G2 Authority | ✅ PASS | `resolve_weapon_impact()` is sole damage path; armor-before-multiplier (OpenBW order); 10 formula tests |
| G3 Projectile/Spell | ✅ PASS | projectile/tracking/chain weapons routed through `process_projectiles()`; `_apply_chain_bounce()` for Mutalisk; Storm 8×14dmg via `resolve_weapon_impact()`; 5 Storm lifecycle tests |
| G4 Shared Pipeline | PARTIAL | Fixture generator + freshness gate done; Godot Test Mode script changes pending |
| G5 Determinism | ✅ PASS | `deterministic_percent_roll()` replaces `hash()`; 7 cross-hashseed tests (PYTHONHASHSEED 1 vs 999 vs 0 vs 42) |
| G6 Presentation | CONCERNS | CombatEvent now carries source_owner/target_owner/positions; Godot VFX changes pending |
| G7 Final | BLOCKED | manual and 30v30 gates not run |

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
| Task 8 | PARTIAL | cd8cf6b | Proto source_owner/target_owner(29/30) + 6 contract tests; Godot Steps 3-6 pending |
| Task 9 | PARTIAL | 4e879de | Fixture generator + 10 presets + freshness gate; Godot Steps 4-5 pending |
| Task 10 | PARTIAL | bb5afa0 | deterministic_percent_roll + 7 cross-hashseed tests; E2E gRPC/replay pending |
| Task 11 | PENDING | — | Final verification (G6/G7) |

## Test Summary
- Total tests: ~580+ (all passing, 1 pre-existing skip)
- New tests added: 12 (wiring) + 10 (formula) + 5 (Storm) + 6 (contract) + 7 (determinism) = 40 new tests
- Regression: 0 failures across full suite
