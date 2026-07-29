# SC1 Combat Differentiation QA

## Baseline
- Commit: 87ddbd8
- Godot version: v4.6.2.stable.official.71f334935
- SimCore combat tests: 74/74 PASS
- VFX profile tests: PASS
- Presentation verification: OK — manifest structure valid, atlas in bounds

## Automated Gates
| Gate | Target | Result | Status |
|---|---:|---:|---|
| CombatEvent transport | 100% fields preserved | pending | PENDING |
| 12-unit weapon mapping | 12/12 | pending | PENDING |
| Counter matrix | exact | pending | PENDING |
| Godot event pipeline | all event types | pending | PENDING |
| 30v30 VFX cap | no overflow | pending | PENDING |

## Manual Gates
| Unit | attack animation | projectile | impact | timing | verdict |
|---|---|---|---|---|---|
