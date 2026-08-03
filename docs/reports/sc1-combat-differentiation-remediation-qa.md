# SC1 Combat Differentiation Remediation QA

## Baseline
- Source commit: 12f6aaa
- Branch: codex/sc1-combat-remediation (from codex/sc1-combat-differentiation)
- Verdict: FAIL
- Reason: source truth, production wiring, projectile/spell authority, shared Test Mode pipeline are not closed

## Gates
| Gate | Status | Evidence |
|---|---|---|
| G0 Source Truth | FAIL | audit uses Wiki and misses Patch_rt/UnitsDAT |
| G1 Runtime Wiring | FAIL | production entity drops semantic combat fields |
| G2 Authority | FAIL | rules.py still mutates health directly |
| G3 Projectile/Spell | FAIL | ranged attack hits immediately; Storm does not advance on empty command ticks |
| G4 Shared Pipeline | FAIL | Test Mode uses handwritten events and GDScript resolver |
| G5 Determinism | FAIL | Python hash used for high-ground roll |
| G6 Presentation | CONCERNS | launch/death/cast event gaps |
| G7 Final | BLOCKED | manual and 30v30 gates not run |

## Remediation Progress
| Task | Status | Commit | Notes |
|---|---|---|---|
| Task 0 | IN PROGRESS | — | Baseline creation |
| Task 1 | PENDING | — | MPQ overlay |
| Task 2 | PENDING | — | DAT audit (G0) |
| Task 3 | PENDING | — | Catalog sync |
| Task 4 | PENDING | — | Production wiring (G1) |
| Task 5 | PENDING | — | Damage resolver (G2) |
| Task 6 | PENDING | — | Attack routing (G3) |
| Task 7 | PENDING | — | Storm lifecycle (G3) |
| Task 8 | PENDING | — | CombatEvent context |
| Task 9 | PENDING | — | Test Mode fixtures (G4) |
| Task 10 | PENDING | — | E2E + determinism (G5) |
| Task 11 | PENDING | — | Final verification (G6/G7) |
