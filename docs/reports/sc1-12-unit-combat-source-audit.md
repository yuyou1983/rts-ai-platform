# SC1 12-Unit Combat Source Audit

**OpenBW commit**: `8265ec449b903e0752060a00ed5f930a3656bf00`
**DAT source**: Patch_rt.mpq > BrooDat.mpq > StarDat.mpq

## Unit Identity Table

| Project unit | SC1 unit id | Weapon DAT id | Resolution rule |
|---|---:|---:|---|
| Marine | 0 | 0 | unit 0.ground_weapon=0 |
| Vulture | 2 | 4 | unit 2.ground_weapon=4 |
| Tank | 5 | 11 | unit 5.subunit1=6.ground_weapon=11 |
| Firebat | 32 | 25 | unit 32.ground_weapon=25 |
| Zergling | 37 | 35 | unit 37.ground_weapon=35 |
| Hydralisk | 38 | 38 | unit 38.ground_weapon=38 |
| Ultralisk | 39 | 40 | unit 39.ground_weapon=40 |
| Mutalisk | 43 | 48 | unit 43.ground_weapon=48 |
| Zealot | 65 | 64 | unit 65.ground_weapon=64 |
| Dragoon | 66 | 66 | unit 66.ground_weapon=66 |
| HighTemplar | 67 | 84 | unit 67 ordinary_weapon=null, spell_weapon=84 (techdata 19) |
| Reaver | 83 | 82 | unit 83 ordinary_weapon=null, scarab_unit=85.ground_weapon=82 |

## Key Values

| Unit | HP | Shield | Armor | Size | Weapon | Damage | Type |
|---|---:|---:|---:|---|---|---:|---|
| Marine | 40 | 0 | 0 | light | Gauss Rifle | 6 | normal |
| Vulture | 80 | 0 | 0 | medium | Fragmentation Grenade | 20 | concussive |
| Tank | 150 | 0 | 1 | heavy | Arclite Cannon | 30 | explosive |
| Firebat | 50 | 0 | 1 | light | Flame Thrower | 8 | concussive |
| Zergling | 35 | 0 | 0 | light | Claws | 5 | normal |
| Hydralisk | 80 | 0 | 0 | medium | Needle Spines | 10 | explosive |
| Ultralisk | 400 | 0 | 1 | heavy | Kaiser Blades | 20 | normal |
| Mutalisk | 120 | 0 | 0 | light | Glave Wurm | 9 | normal |
| Zealot | 100 | 60 | 1 | light | Psi Blades | 8 | normal |
| Dragoon | 100 | 80 | 1 | heavy | Phase Disruptor | 20 | explosive |
| HighTemplar | 40 | 40 | 0 | light | lHallucination | 14 | independent_spell |
| Reaver | 100 | 80 | 0 | heavy | Missiles | 100 | normal |
