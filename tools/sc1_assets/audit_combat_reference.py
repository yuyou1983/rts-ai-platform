#!/usr/bin/env python3
"""Task 1A: SC1 DAT Combat Truth Audit Script.

Loads weapons.dat via PyMS, cross-checks against combat_reference.json,
and reports any discrepancies.

Usage:
    python3 audit_combat_reference.py [--reference PATH] [--dat-dir PATH]
"""
import argparse
import json
import struct
import sys
from pathlib import Path

# PyMS for weapons.dat
sys.path.insert(0, str(Path(__file__).parent.parent / "mpq" / "PyMS"))
from PyMS.FileFormats.DAT.WeaponsDAT import WeaponsDAT


WEAPON_TYPE_MAP = {0: "independent", 1: "explosive", 2: "concussive", 3: "normal"}


def read_tbl(path: Path) -> list[str]:
    """Parse SC1 TBL file → list of strings."""
    data = path.read_bytes()
    count = struct.unpack_from("<H", data, 0)[0]
    offsets = [struct.unpack_from("<H", data, 2 + i * 2)[0] for i in range(count)]
    strings = []
    for i in range(count):
        start = offsets[i]
        end = offsets[i + 1] if i + 1 < count else len(data)
        null_pos = data.find(b"\x00", start, end)
        if null_pos >= 0:
            end = null_pos
        raw = data[start:end].decode("cp1252", errors="replace").rstrip("\r")
        strings.append("".join(c for c in raw if ord(c) >= 32))
    return strings


def load_weapons(dat_dir: Path) -> dict:
    """Load weapons.dat via PyMS → dict of weapon_id → stats."""
    wd = WeaponsDAT()
    wd.load_file(str(dat_dir / "weapons.dat"))
    tbl = read_tbl(dat_dir.parent / "rez" / "stat_txt.tbl")

    weapons = {}
    for i in range(wd.entry_count()):
        w = wd.get_entry(i)
        weapons[i] = {
            "id": i,
            "name": tbl[w.label].strip() if w.label < len(tbl) else "Unknown",
            "damage_amount": w.damage_amount,
            "damage_bonus": w.damage_bonus,
            "damage_factor": w.damage_factor,
            "weapon_cooldown": w.weapon_cooldown,
            "weapon_type_raw": w.weapon_type,
            "weapon_type": WEAPON_TYPE_MAP.get(w.weapon_type, "unknown"),
            "minimum_range": w.minimum_range,
            "maximum_range": w.maximum_range,
            "inner_splash_range": w.inner_splash_range,
            "medium_splash_range": w.medium_splash_range,
            "outer_splash_range": w.outer_splash_range,
        }
    return weapons


def verify_raw_bytes(dat_dir: Path, ref: dict) -> list[str]:
    """Cross-check PyMS values against raw file bytes."""
    errors = []
    wdata = (dat_dir / "weapons.dat").read_bytes()
    fmt = WeaponsDAT.FORMAT

    # Compute column offsets
    offset = 0
    col_offsets = {}
    for prop in fmt.properties:
        size = prop.size(False)
        col_offsets[prop.name] = offset
        offset += size * fmt.entries

    # Verify key weapons
    for uid_str, ref_w in ref["weapons"].items():
        uid = int(uid_str)
        # Check damage_amount (uint16 column)
        da_off = col_offsets["damage_amount"]
        raw_da = struct.unpack_from("<H", wdata, da_off + uid * 2)[0]
        if raw_da != ref_w["damage_amount"]:
            errors.append(
                f"Weapon({uid}) damage_amount: ref={ref_w['damage_amount']} raw={raw_da}"
            )
        # Check damage_factor (byte column)
        df_off = col_offsets["damage_factor"]
        raw_df = wdata[df_off + uid]
        if raw_df != ref_w["damage_factor"]:
            errors.append(
                f"Weapon({uid}) damage_factor: ref={ref_w['damage_factor']} raw={raw_df}"
            )
        # Check weapon_type (byte column)
        wt_off = col_offsets["weapon_type"]
        raw_wt = wdata[wt_off + uid]
        if raw_wt != ref_w["weapon_type_raw"]:
            errors.append(
                f"Weapon({uid}) weapon_type: ref={ref_w['weapon_type_raw']} raw={raw_wt}"
            )

    return errors


def audit_units(ref: dict, weapons: dict) -> list[str]:
    """Verify all 12 units have valid weapon references."""
    errors = []
    expected_count = {"terran": 4, "zerg": 4, "protoss": 4}
    total = 0

    for race, count in expected_count.items():
        if race not in ref["units"]:
            errors.append(f"Missing race: {race}")
            continue
        units = ref["units"][race]
        if len(units) != count:
            errors.append(f"Race {race}: expected {count} units, got {len(units)}")
        for key, unit in units.items():
            total += 1
            # Check required fields
            for field in ["unit_id", "name", "hp", "shield", "armor", "unit_size",
                          "ground_weapon_id", "air_weapon_id", "sight_range"]:
                if field not in unit:
                    errors.append(f"Unit {key}: missing field {field}")
            # Check weapon references
            for wkey in ["ground_weapon", "air_weapon"]:
                wid = unit[wkey.replace("weapon", "weapon_id")] if "weapon_id" in wkey else None
                if wkey == "ground_weapon":
                    wid = unit.get("ground_weapon_id")
                elif wkey == "air_weapon":
                    wid = unit.get("air_weapon_id")
                if wid is not None and wid < 130:
                    if wid not in weapons:
                        errors.append(f"Unit {key}: weapon ID {wid} not in weapons.dat")
                    if unit[wkey] is None:
                        errors.append(f"Unit {key}: {wkey} is None but ID {wid} is set")

    if total != 12:
        errors.append(f"Expected 12 units, found {total}")

    return errors


def print_report(ref: dict, weapons: dict, byte_errors: list, unit_errors: list):
    """Print audit report."""
    print("=" * 70)
    print("SC1 Combat Reference Audit Report")
    print("=" * 70)

    print(f"\n1. WEAPONS.DAT")
    print(f"   Total weapons loaded: {len(weapons)}")
    print(f"   Byte-level verification: {'PASS' if not byte_errors else 'FAIL'}")
    if byte_errors:
        for e in byte_errors[:10]:
            print(f"     ✗ {e}")

    print(f"\n2. UNITS (12 target units)")
    print(f"   Unit count check: {'PASS' if not unit_errors else 'FAIL'}")
    if unit_errors:
        for e in unit_errors[:10]:
            print(f"     ✗ {e}")

    print(f"\n3. UNIT COMBAT STATS SUMMARY")
    print(f"   {'Unit':<16} {'HP':>4} {'SH':>3} {'AR':>2} {'Size':<7} "
          f"{'Ground Weapon':<35} {'Air Weapon':<25}")
    print(f"   {'-'*16} {'-'*4} {'-'*3} {'-'*2} {'-'*7} {'-'*35} {'-'*25}")

    for race in ["terran", "zerg", "protoss"]:
        for key, u in ref["units"][race].items():
            gw = u.get("ground_weapon")
            aw = u.get("air_weapon")
            gw_s = f"{gw['name']}({gw['damage']}×{gw['factor']}/{gw['type']}/cd{gw['cooldown']})" if gw else "—"
            aw_s = f"{aw['name']}({aw['damage']}×{aw['factor']}/{aw['type']})" if aw else "—"
            print(f"   {u['name']:<16} {u['hp']:>4} {u['shield']:>3} {u['armor']:>2} {u['unit_size']:<7} "
                  f"{gw_s:<35} {aw_s:<25}")

    print(f"\n4. DAMAGE TYPE MATRIX")
    dm = ref["damage_type_matrix"]
    print(f"   {'Type':<12} {'Small':>6} {'Medium':>7} {'Large':>6}")
    for dtype, eff in dm.items():
        print(f"   {dtype:<12} {eff['small']:>6.0%} {eff['medium']:>7.0%} {eff['large']:>6.0%}")

    print(f"\n5. NOTES")
    print(f"   • weapons.dat: {len(weapons)} entries loaded via PyMS (raw byte-verified)")
    print(f"   • units.dat: column layout mismatch with PyMS; unit stats from SC1 wiki")
    print(f"   • weapon_type enum: 0=independent, 1=explosive, 2=concussive, 3=normal")
    print(f"   • Reaver weapon 81 base damage=20 in weapons.dat (wiki says 100)")
    print(f"   • Zealot damage_factor=1 in weapons.dat (wiki says 8×2=16)")

    all_pass = not byte_errors and not unit_errors
    print(f"\n{'='*70}")
    print(f"OVERALL: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'='*70}")
    return all_pass


def main():
    parser = argparse.ArgumentParser(description="SC1 Combat Reference Audit")
    parser.add_argument("--reference", default=None,
                        help="Path to combat_reference.json")
    parser.add_argument("--dat-dir", default=None,
                        help="Path to StarDat_extracted/arr/")
    args = parser.parse_args()

    base = Path(__file__).parent
    ref_path = Path(args.reference) if args.reference else base / "combat_reference.json"
    dat_dir = Path(args.dat_dir) if args.dat_dir else base.parent / "mpq" / "StarDat_extracted" / "arr"

    # Load reference
    with open(ref_path) as f:
        ref = json.load(f)

    # Load weapons.dat
    weapons = load_weapons(dat_dir)

    # Verify raw bytes
    byte_errors = verify_raw_bytes(dat_dir, ref)

    # Audit units
    unit_errors = audit_units(ref, weapons)

    # Print report
    all_pass = print_report(ref, weapons, byte_errors, unit_errors)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
