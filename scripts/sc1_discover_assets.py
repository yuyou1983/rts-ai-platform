#!/usr/bin/env python3
"""Discover SC1 MPQ paths for candidate asset names.

Brute-force probes storm_extract extract-one against Patch_rt.mpq,
BrooDat.mpq, and StarDat.mpq using mpq_path from the manifest.

Supports:
  - Exact path probe (mpq_path is not "PENDING")
  - Fuzzy path probe for "PENDING" entries (tries abbreviated 8.3 names)
  - Reports found / missing / pending status per asset
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTOR = REPO_ROOT / "tools" / "mpq" / "bin" / "storm_extract"
DEFAULT_STARSCRAFT_DIR = Path("/Users/yuyou/code/StarCraft")
MPQ_PRIORITY = ["Patch_rt.mpq", "BrooDat.mpq", "StarDat.mpq"]

# SC1 uses 8.3 abbreviated filenames inside MPQs.
# Known abbreviation patterns: full_name → abbreviated (up to 8 chars before .grp)
ABBREVIATION_MAP: dict[str, list[str]] = {
    "Wraith": ["wraith", "twraith", "wrait", "twrait"],
    "Reaver": ["reaver", "preaver", "reav", "preav", "reavr"],
}


def _probe(
    extractor: Path,
    mpq_path: Path,
    candidate_path: str,
    tmp_out: Path,
) -> bool:
    """Return True if extract-one succeeds for candidate_path."""
    if not mpq_path.exists():
        return False
    result = subprocess.run(
        [str(extractor), "extract-one", str(mpq_path), candidate_path, str(tmp_out)],
        capture_output=True,
        timeout=10,
    )
    return result.returncode == 0


def _fuzzy_probe(
    extractor: Path,
    mpq_path: Path,
    asset_id: str,
    kind: str,
    race: str,
    tmp_out: Path,
) -> str | None:
    """Try abbreviated path variants for a PENDING asset.

    Returns the successful mpq_path or None.
    """
    abbreviations = ABBREVIATION_MAP.get(asset_id, [])
    if not abbreviations:
        return None

    race_dir = race.lower()
    kind_dir = "unit" if kind == "unit" else kind
    for abbrev in abbreviations:
        candidate = f"{kind_dir}\\{race_dir}\\{abbrev}.grp"
        if _probe(extractor, mpq_path, candidate, tmp_out):
            return candidate
    return None


def discover(
    extractor: Path,
    starcraft_dir: Path,
    candidates: list[dict],
    out_path: Path,
) -> dict:
    """Probe each candidate against all MPQs in priority order."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for cand in candidates:
        asset_id = cand["id"]
        kind = cand.get("kind", "unit")
        race = cand.get("race", "")
        candidate_path = cand["mpq_path"]
        found = False

        # If the manifest says PENDING, try fuzzy abbreviations
        if candidate_path.upper() == "PENDING":
            for mpq_name in MPQ_PRIORITY:
                mpq_path = starcraft_dir / mpq_name
                tmp_out = out_path.parent / f"_probe_{asset_id}.tmp"
                hit = _fuzzy_probe(extractor, mpq_path, asset_id, kind, race, tmp_out)
                if hit is not None:
                    if tmp_out.exists():
                        tmp_out.unlink()
                    results.append({
                        "id": asset_id,
                        "kind": kind,
                        "race": race,
                        "visual_class": cand.get("visual_class", ""),
                        "mpq_path": hit,
                        "source_mpq": mpq_name,
                        "status": "found",
                    })
                    found = True
                    break
            if not found:
                results.append({
                    "id": asset_id,
                    "kind": kind,
                    "race": race,
                    "visual_class": cand.get("visual_class", ""),
                    "mpq_path": "",
                    "source_mpq": "",
                    "status": "pending",
                })
            continue

        # Normal exact-path probe
        for mpq_name in MPQ_PRIORITY:
            mpq_path = starcraft_dir / mpq_name
            tmp_out = out_path.parent / f"_probe_{asset_id}.tmp"
            if _probe(extractor, mpq_path, candidate_path, tmp_out):
                if tmp_out.exists():
                    tmp_out.unlink()
                results.append({
                    "id": asset_id,
                    "kind": kind,
                    "race": race,
                    "visual_class": cand.get("visual_class", ""),
                    "mpq_path": candidate_path,
                    "source_mpq": mpq_name,
                    "status": "found",
                })
                found = True
                break
        if not found:
            results.append({
                "id": asset_id,
                "kind": kind,
                "race": race,
                "visual_class": cand.get("visual_class", ""),
                "mpq_path": "",
                "source_mpq": "",
                "status": "missing",
            })

    report = {
        "total": len(results),
        "found": sum(1 for r in results if r["status"] == "found"),
        "missing": sum(1 for r in results if r["status"] == "missing"),
        "pending": sum(1 for r in results if r["status"] == "pending"),
        "candidates": results,
    }
    out_path.write_text(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover SC1 MPQ asset paths")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "tools" / "sc1_assets" / "p1a_resource_manifest.json",
    )
    parser.add_argument(
        "--starcraft-dir",
        type=Path,
        default=DEFAULT_STARSCRAFT_DIR,
    )
    parser.add_argument(
        "--extractor",
        type=Path,
        default=DEFAULT_EXTRACTOR,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "local_assets" / "sc1_discovery" / "p1a_asset_candidates.json",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    candidates = manifest["assets"]
    report = discover(args.extractor, args.starcraft_dir, candidates, args.out)
    print(
        f"total={report['total']} found={report['found']} "
        f"missing={report['missing']} pending={report['pending']}"
    )
    return 0 if report["missing"] == 0 and report["pending"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
