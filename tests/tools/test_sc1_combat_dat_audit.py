"""Tests for effective SC1 combat DAT extraction and source audit.

Tests that the MPQ extraction follows correct precedence (StarDat → BrooDat → Patch_rt)
 and produces structured provenance for all combat-relevant files.
Also tests the DAT audit reference for unit identity, weapon resolution, and data integrity.
"""
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_mpq_sources_precedence():
    """MPQ sources must be ordered low-to-high: StarDat, BrooDat, Patch_rt."""
    from tools.mpq.extract_dat import MPQ_SOURCES

    names = [s.name for s in MPQ_SOURCES]
    assert names == ["StarDat.mpq", "BrooDat.mpq", "Patch_rt.mpq"]


def test_combat_files_include_all_authoritative_inputs():
    """All five combat-relevant internal paths must be in the extraction list."""
    from tools.mpq.extract_dat import FILES

    required = {
        r"arr\units.dat",
        r"arr\weapons.dat",
        r"arr\techdata.dat",
        r"rez\stat_txt.tbl",
        r"scripts\iscript.bin",
    }
    assert required.issubset(set(FILES))


def test_mpq_source_paths_exist():
    """Each configured MPQ source path must exist on disk."""
    from tools.mpq.extract_dat import MPQ_SOURCES

    for source in MPQ_SOURCES:
        assert source.path.exists(), f"MPQ not found: {source.path}"


def test_effective_manifest_structure(manifest):
    """Manifest must have per-file provenance with effective_source and hashes."""
    required_files = [
        r"arr\units.dat",
        r"arr\weapons.dat",
        r"arr\techdata.dat",
        r"rez\stat_txt.tbl",
        r"scripts\iscript.bin",
    ]
    for fpath in required_files:
        assert fpath in manifest, f"Missing {fpath} from manifest"
        entry = manifest[fpath]
        assert "effective_source" in entry, f"{fpath} missing effective_source"
        assert "output_sha256" in entry, f"{fpath} missing output_sha256"
        assert "output_size" in entry, f"{fpath} missing output_size"
        assert entry["output_size"] > 0, f"{fpath} extracted as 0 bytes"


def test_patch_rt_effective_for_combat_dats(manifest):
    """Patch_rt must be the effective source for units.dat, weapons.dat, techdata.dat."""
    for fpath in [r"arr\units.dat", r"arr\weapons.dat", r"arr\techdata.dat"]:
        assert manifest[fpath]["effective_source"] == "Patch_rt.mpq", (
            f"{fpath} effective_source should be Patch_rt.mpq, "
            f"got {manifest[fpath]['effective_source']}"
        )


@pytest.fixture
def manifest():
    """Load the effective_manifest.json produced by extract_dat.py."""
    manifest_path = REPO / "tools/mpq/StarDat_extracted/effective_manifest.json"
    if not manifest_path.exists():
        pytest.skip("effective_manifest.json not found — run extract_dat.py first")
    with open(manifest_path) as f:
        return json.load(f)


# ── Task 2: Source identity and data integrity tests ──

EXPECTED_UNIT_IDS = {
    "Marine": 0, "Vulture": 2, "Tank": 5, "Firebat": 32,
    "Zergling": 37, "Hydralisk": 38, "Ultralisk": 39, "Mutalisk": 43,
    "Zealot": 65, "Dragoon": 66, "HighTemplar": 67, "Reaver": 83,
}

EXPECTED_WEAPON_IDS = {
    "Marine": 0, "Vulture": 4, "Tank": 11, "Firebat": 25,
    "Zergling": 35, "Hydralisk": 38, "Ultralisk": 40, "Mutalisk": 48,
    "Zealot": 64, "Dragoon": 66, "HighTemplar": 84, "Reaver": 82,
}


@pytest.fixture
def reference():
    """Load the audited reference JSON."""
    ref_path = REPO / "data/combat/sc1_representative_reference.json"
    if not ref_path.exists():
        pytest.skip("reference not found — run audit_sc1_combat_data.py first")
    with open(ref_path) as f:
        return json.load(f)


def test_reference_has_unique_dat_identity(reference):
    assert {name: row["unit_dat_id"] for name, row in reference["units"].items()} == EXPECTED_UNIT_IDS
    assert {name: row["effective_weapon_dat_id"] for name, row in reference["units"].items()} == EXPECTED_WEAPON_IDS


def test_reference_has_no_wiki_generation_source(reference):
    encoded = json.dumps(reference).lower()
    assert "community wiki for unit stats" not in encoded
    assert reference["meta"]["openbw_commit"] == "8265ec449b903e0752060a00ed5f930a3656bf00"


def test_patch_values(reference):
    """Key sanity-gate values from effective Patch_rt DAT."""
    units = reference["units"]
    # Tank: weapon 11, damage 30, factor 1
    assert units["Tank"]["weapon"]["weapon_dat_id"] == 11
    assert units["Tank"]["weapon"]["damage_amount"] == 30
    assert units["Tank"]["weapon"]["damage_factor"] == 1
    # Ultralisk: weapon 40, normal type
    assert units["Ultralisk"]["weapon"]["weapon_dat_id"] == 40
    assert units["Ultralisk"]["weapon"]["weapon_type"] == "normal"
    # Zealot: HP 100, shield 60, light size
    assert units["Zealot"]["hp"] == 100
    assert units["Zealot"]["shield"] == 60
    assert units["Zealot"]["unit_size"] == "light"
    # Storm: weapon 84, damage 14
    assert units["HighTemplar"]["spell_weapon"]["damage_amount"] == 14
    # Reaver: weapon 82, damage 100, splash 20/40/60
    assert units["Reaver"]["scarab_weapon"]["damage_amount"] == 100
    assert units["Reaver"]["scarab_weapon"]["splash_ranges"] == [20, 40, 60]


def test_tank_resolved_via_subunit(reference):
    """Tank weapon must be resolved through subunit1=6 -> weapon 11."""
    ev = reference["units"]["Tank"]["weapon_evidence"]
    assert "subunit1=6" in ev["resolution"]
    assert "ground_weapon=11" in ev["resolution"]


def test_reaver_resolved_via_scarab(reference):
    """Reaver weapon must be resolved through scarab unit 85 -> weapon 82."""
    ev = reference["units"]["Reaver"]["weapon_evidence"]
    assert "scarab_unit=85" in ev["resolution"]
    assert "ground_weapon=82" in ev["resolution"]


def test_templar_has_spell_weapon_not_ordinary(reference):
    """High Templar has null ordinary weapon and spell_weapon 84."""
    ht = reference["units"]["HighTemplar"]
    assert ht["ordinary_weapon"] is None
    assert ht["spell_weapon"]["weapon_dat_id"] == 84
    assert ht["spell_weapon"]["techdata_id"] == 19


def test_all_units_have_semantic_weapon_id(reference):
    """Every unit must have a semantic_weapon_id matching the catalog."""
    SEMANTIC_IDS = {
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
    for name, data in reference["units"].items():
        assert data["semantic_weapon_id"] == SEMANTIC_IDS[name], (
            f"{name} semantic_weapon_id mismatch: {data['semantic_weapon_id']} != {SEMANTIC_IDS[name]}"
        )
