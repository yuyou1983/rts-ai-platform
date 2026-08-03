#!/usr/bin/env python3
"""Extract DAT, TBL and BIN files from effective MPQ overlay.

Implements low-to-high precedence: StarDat.mpq → BrooDat.mpq → Patch_rt.mpq.
Later successful sources overwrite earlier output. Produces structured
provenance manifest with SHA-256 hashes and effective source tracking.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXTRACTOR = REPO / "tools/mpq/bin/storm_extract"
OUTDIR = REPO / "tools/mpq/StarDat_extracted"
MANIFEST_PATH = OUTDIR / "effective_manifest.json"


@dataclass(frozen=True)
class MPQSource:
    name: str
    path: Path


MPQ_SOURCES: tuple[MPQSource, ...] = (
    MPQSource("StarDat.mpq", Path("/Users/yuyou/code/StarCraft/StarDat.mpq")),
    MPQSource("BrooDat.mpq", Path("/Users/yuyou/code/StarCraft/BrooDat.mpq")),
    MPQSource("Patch_rt.mpq", Path("/Users/yuyou/code/StarCraft/Patch_rt.mpq")),
)

FILES = [
    r"arr\units.dat",
    r"arr\sprites.dat",
    r"arr\images.dat",
    r"arr\flingy.dat",
    r"arr\weapons.dat",
    r"arr\techdata.dat",
    r"rez\stat_txt.tbl",
    r"rez\images.tbl",
    r"scripts\iscript.bin",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _try_extract(mpq_path: Path, internal: str, out_path: Path) -> bool:
    """Try to extract one file from MPQ. Returns True on success."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Use temp file to avoid 0-byte leftovers on failure
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        r = subprocess.run(
            [str(EXTRACTOR), "extract-one", str(mpq_path), internal, str(tmp_path)],
            capture_output=True,
            timeout=15,
        )
        if r.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
            os.replace(tmp_path, out_path)
            return True
        if tmp_path.exists():
            tmp_path.unlink()
        return False
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def extract_effective_files(
    sources: tuple[MPQSource, ...],
    out_dir: Path,
) -> dict[str, dict[str, str | int]]:
    """Extract low-to-high; later successful source overwrites earlier output.

    Return per internal path: source MPQ name, MPQ SHA-256, output SHA-256 and size.
    Missing optional paths in one layer do not erase a lower-layer success.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, str | int]] = {}

    for internal in FILES:
        out_path = out_dir / internal.replace("\\", "/")
        effective_source = None
        effective_mpq_sha = ""

        for source in sources:
            if not source.path.exists():
                continue
            if _try_extract(source.path, internal, out_path):
                effective_source = source.name
                effective_mpq_sha = _sha256_file(source.path)

        if effective_source is not None and out_path.exists() and out_path.stat().st_size > 0:
            manifest[internal] = {
                "effective_source": effective_source,
                "mpq_sha256": effective_mpq_sha,
                "output_sha256": _sha256_file(out_path),
                "output_size": out_path.stat().st_size,
            }

    return manifest


def main():
    manifest = extract_effective_files(MPQ_SOURCES, OUTDIR)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # Print summary
    combat_files = [
        r"arr\units.dat",
        r"arr\weapons.dat",
        r"arr\techdata.dat",
        r"rez\stat_txt.tbl",
        r"scripts\iscript.bin",
    ]
    print("Effective MPQ extraction summary:")
    for f in combat_files:
        if f in manifest:
            entry = manifest[f]
            print(
                f"  {f}: effective_source={entry['effective_source']}, "
                f"size={entry['output_size']}"
            )
        else:
            print(f"  {f}: MISSING")

    print(f"\nManifest written to {MANIFEST_PATH}")
    print(f"Total files extracted: {len(manifest)}")


if __name__ == "__main__":
    main()
