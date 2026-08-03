"""Tests for effective SC1 combat DAT extraction with Patch_rt overlay.

Tests that the MPQ extraction follows correct precedence (StarDat → BrooDat → Patch_rt)
 and produces structured provenance for all combat-relevant files.
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
