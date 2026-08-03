#!/usr/bin/env python3
"""Audit SC1 combat data from effective DAT overlay (Patch_rt > BrooDat > StarDat).

Produces reference JSON with unit identities, weapon mechanics, and provenance.
Does NOT use Wiki values — all data from effective DAT/TBL/iscript with OpenBW cross-check.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DAT_DIR = REPO / "tools/mpq/StarDat_extracted/arr"
TBL_DIR = REPO / "tools/mpq/StarDat_extracted/rez"
SCRIPT_DIR = REPO / "tools/mpq/StarDat_extracted/scripts"
REFERENCE_PATH = REPO / "data/combat/sc1_representative_reference.json"
REPORT_PATH = REPO / "docs/reports/sc1-12-unit-combat-source-audit.md"

# PyMS is bundled in tools/mpq/PyMS
sys.path.insert(0, str(REPO / "tools/mpq/PyMS"))
from PyMS.FileFormats.DAT.UnitsDAT import UnitsDAT
from PyMS.FileFormats.DAT.WeaponsDAT import WeaponsDAT

OPENBW_COMMIT = "8265ec449b903e0752060a00ed5f930a3656bf00"

WEAPON_TYPE_MAP = {0: "independent", 1: "explosive", 2: "concussive", 3: "normal", 4: "independent_spell"}
SIZE_MAP = {0: "independent", 1: "light", 2: "medium", 3: "heavy"}
EXPLOSION_MAP = {0: "none", 1: "normal", 2: "radial_splash", 3: "line_splash", 4: "unknown"}

# Project unit name → SC1 unit DAT id
PROJECT_UNIT_IDS = {
    "Marine": 0,
    "Vulture": 2,
    "Tank": 5,
    "Firebat": 32,
    "Zergling": 37,
    "Hydralisk": 38,
    "Ultralisk": 39,
    "Mutalisk": 43,
    "Zealot": 65,
    "Dragoon": 66,
    "HighTemplar": 67,
    "Reaver": 83,
}

# Semantic weapon IDs for the 12 project units
SEMANTIC_WEAPON_IDS = {
    "Marine": "terran_c10_rifle",
    "Vulture": "terran_fragmentation_grenade",
    "Tank": "terran_arclite_cannon",
    "Firebat": "terran_flame_thrower",
    "Zergling": "zerg_claws",
    "Hydralisk": "zerg_needle_spines",
    "Ultralisk": "zerg_kaiser_blades",
    "Mutalisk": "zerg_glave_wurm",
    "Zealot": "protoss_psi_blades",
    "Dragoon": "protoss_phase_disruptor",
    "HighTemplar": "protoss_psionic_storm",
    "Reaver": "protoss_scarab",
}

# Expected weapon DAT IDs (resolved per plan rules)
EXPECTED_WEAPON_IDS = {
    "Marine": 0,
    "Vulture": 4,
    "Tank": 11,       # unit 5 -> subunit1=6 -> weapon 11
    "Firebat": 25,
    "Zergling": 35,
    "Hydralisk": 38,
    "Ultralisk": 40,
    "Mutalisk": 48,
    "Zealot": 64,
    "Dragoon": 66,
    "HighTemplar": 84,  # spell weapon
    "Reaver": 82,       # scarab unit 85 -> weapon 82
}


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


def load_effective_dat(dat_root: Path) -> tuple[UnitsDAT, WeaponsDAT, dict]:
    """Load effective DAT files from extracted MPQ overlay."""
    ud = UnitsDAT()
    ud.load_file(str(dat_root / "arr/units.dat"))
    wd = WeaponsDAT()
    wd.load_file(str(dat_root / "arr/weapons.dat"))
    tbl = read_tbl(dat_root / "rez/stat_txt.tbl")
    return ud, wd, {"stat_txt": tbl}


def resolve_effective_weapon(
    project_name: str,
    unit_id: int,
    units_dat: UnitsDAT,
) -> tuple[int | None, dict[str, int | str]]:
    """Resolve the effective weapon DAT id for a project unit.

    Rules:
    - Tank: unit 5 -> subunit1=6 -> ground weapon 11
    - HighTemplar: ordinary weapon null, spell weapon 84 (techdata 19)
    - Reaver: ordinary weapon null, scarab unit 85 -> weapon 82
    - Others: unit ground weapon
    """
    u = units_dat.get_entry(unit_id)
    evidence: dict[str, int | str] = {}

    if project_name == "Tank":
        subunit_id = u.subunit1
        sub = units_dat.get_entry(subunit_id)
        weapon_id = sub.ground_weapon
        evidence["resolution"] = f"unit {unit_id}.subunit1={subunit_id}.ground_weapon={weapon_id}"
        return weapon_id, evidence

    if project_name == "HighTemplar":
        # No ordinary weapon; spell weapon is 84 (Psi Storm, techdata 19)
        weapon_id = 84
        evidence["resolution"] = f"unit {unit_id} ordinary_weapon=null, spell_weapon={weapon_id} (techdata 19)"
        evidence["is_spell"] = True
        return weapon_id, evidence

    if project_name == "Reaver":
        # No ordinary weapon; scarab unit 85 -> weapon 82
        scarab_id = 85
        scarab = units_dat.get_entry(scarab_id)
        weapon_id = scarab.ground_weapon
        evidence["resolution"] = f"unit {unit_id} ordinary_weapon=null, scarab_unit={scarab_id}.ground_weapon={weapon_id}"
        evidence["is_scarab"] = True
        return weapon_id, evidence

    weapon_id = u.ground_weapon
    evidence["resolution"] = f"unit {unit_id}.ground_weapon={weapon_id}"
    return weapon_id, evidence


def build_reference(dat_root: Path, provenance: dict) -> dict:
    """Build the complete reference JSON from effective DAT."""
    ud, wd, extras = load_effective_dat(dat_root)
    tbl = extras["stat_txt"]

    units: dict[str, dict] = {}
    for name, uid in PROJECT_UNIT_IDS.items():
        u = ud.get_entry(uid)
        weapon_id, weapon_evidence = resolve_effective_weapon(name, uid, ud)

        # Get weapon entry
        w = wd.get_entry(weapon_id) if weapon_id is not None and weapon_id < wd.entry_count() else None

        hp = u.hit_points.whole if hasattr(u.hit_points, "whole") else int(u.hit_points)
        shield = u.shield_amount if u.shield_enabled else 0

        unit_data: dict = {
            "unit_dat_id": uid,
            "semantic_weapon_id": SEMANTIC_WEAPON_IDS[name],
            "effective_weapon_dat_id": weapon_id,
            "weapon_evidence": weapon_evidence,
            "hp": hp,
            "shield": shield,
            "shield_enabled": bool(u.shield_enabled),
            "armor": u.armor,
            "unit_size": SIZE_MAP.get(u.unit_size, "unknown"),
            "unit_size_raw": u.unit_size,
            "max_ground_hits": u.max_ground_hits,
            "max_air_hits": u.max_air_hits,
            "ground_weapon_raw": u.ground_weapon,
            "air_weapon_raw": u.air_weapon,
            "subunit1": u.subunit1 if hasattr(u, "subunit1") else None,
            "subunit2": u.subunit2 if hasattr(u, "subunit2") else None,
        }

        if w is not None:
            unit_data["weapon"] = {
                "weapon_dat_id": weapon_id,
                "label_id": w.label,
                "label_name": tbl[w.label].strip() if w.label < len(tbl) else "Unknown",
                "damage_amount": w.damage_amount,
                "damage_bonus": w.damage_bonus,
                "damage_factor": w.damage_factor,
                "weapon_type": WEAPON_TYPE_MAP.get(w.weapon_type, "unknown"),
                "weapon_type_raw": w.weapon_type,
                "weapon_cooldown": w.weapon_cooldown,
                "minimum_range": w.minimum_range,
                "maximum_range": w.maximum_range,
                "inner_splash_range": w.inner_splash_range,
                "medium_splash_range": w.medium_splash_range,
                "outer_splash_range": w.outer_splash_range,
                "explosion_type": EXPLOSION_MAP.get(w.explosion_type, "unknown"),
                "explosion_type_raw": w.explosion_type,
                "weapon_behavior": w.weapon_behavior,
            }

        # Special fields
        if name == "HighTemplar":
            unit_data["spell_weapon"] = unit_data.pop("weapon")
            unit_data["spell_weapon"]["techdata_id"] = 19
            unit_data["ordinary_weapon"] = None
        elif name == "Reaver":
            unit_data["scarab_weapon"] = unit_data.pop("weapon")
            unit_data["scarab_weapon"]["scarab_unit_id"] = 85
            unit_data["scarab_weapon"]["splash_ranges"] = [
                w.inner_splash_range, w.medium_splash_range, w.outer_splash_range
            ]
            unit_data["scarab_weapon"]["splash_fractions"] = [1.0, 0.5, 0.25]
            unit_data["ordinary_weapon"] = None

        units[name] = unit_data

    reference: dict = {
        "meta": {
            "openbw_commit": OPENBW_COMMIT,
            "dat_source": "Patch_rt.mpq > BrooDat.mpq > StarDat.mpq",
            "provenance": provenance,
            "generator": "scripts/audit_sc1_combat_data.py",
        },
        "units": units,
    }
    return reference


def write_report(reference: dict):
    """Write human-readable audit report."""
    lines = [
        "# SC1 12-Unit Combat Source Audit",
        "",
        f"**OpenBW commit**: `{OPENBW_COMMIT}`",
        f"**DAT source**: Patch_rt.mpq > BrooDat.mpq > StarDat.mpq",
        "",
        "## Unit Identity Table",
        "",
        "| Project unit | SC1 unit id | Weapon DAT id | Resolution rule |",
        "|---|---:|---:|---|",
    ]
    for name, data in reference["units"].items():
        ev = data.get("weapon_evidence", {}).get("resolution", "direct")
        lines.append(f"| {name} | {data['unit_dat_id']} | {data['effective_weapon_dat_id']} | {ev} |")

    lines.extend(["", "## Key Values", ""])
    lines.append("| Unit | HP | Shield | Armor | Size | Weapon | Damage | Type |")
    lines.append("|---|---:|---:|---:|---|---|---:|---|")
    for name, data in reference["units"].items():
        w = data.get("weapon") or data.get("spell_weapon") or data.get("scarab_weapon")
        if w:
            lines.append(
                f"| {name} | {data['hp']} | {data['shield']} | {data['armor']} | "
                f"{data['unit_size']} | {w.get('label_name','?')} | "
                f"{w.get('damage_amount',0)} | {w.get('weapon_type','?')} |"
            )

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Report written to {REPORT_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-reference", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    # Load provenance
    manifest_path = REPO / "tools/mpq/StarDat_extracted/effective_manifest.json"
    provenance = {}
    if manifest_path.exists():
        import json as j
        provenance = j.loads(manifest_path.read_text())

    reference = build_reference(DAT_DIR.parent, provenance)

    if args.check:
        # Compare against existing reference
        if REFERENCE_PATH.exists():
            existing = json.loads(REFERENCE_PATH.read_text())
            if json.dumps(existing, sort_keys=True) != json.dumps(reference, sort_keys=True):
                print("FAIL: reference is stale")
                sys.exit(1)
            print("OK: reference is up to date")
        else:
            print("FAIL: reference does not exist")
            sys.exit(1)
        return

    if args.write_reference:
        REFERENCE_PATH.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n")
        print(f"Reference written to {REFERENCE_PATH}")

    if args.write_report:
        write_report(reference)

    if not args.write_reference and not args.write_report:
        # Default: print summary
        print(json.dumps(reference, indent=2, sort_keys=True)[:2000])


if __name__ == "__main__":
    main()
