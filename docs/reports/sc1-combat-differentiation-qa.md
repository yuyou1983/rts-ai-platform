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
| 12-unit weapon mapping | 12/12 | 12/12 | ✅ PASS (Task 2) |
| Counter matrix | exact | exact | ✅ PASS (Task 2) |
| Godot event pipeline | all event types | pending | PENDING |
| 30v30 VFX cap | no overflow | pending | PENDING |

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
