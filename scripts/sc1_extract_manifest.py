#!/usr/bin/env python3
"""Extract and optionally convert SC1 assets listed in a manifest.

Outputs are intended for ignored local folders. Do not commit generated assets
from commercial StarCraft MPQs into this repository.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p0_resource_manifest.json"
DEFAULT_EXTRACTOR = REPO_ROOT / "tools" / "mpq" / "bin" / "storm_extract"
DEFAULT_RAW_OUT = REPO_ROOT / "local_assets" / "sc1_mpq_raw" / "p0"
DEFAULT_PNG_OUT = REPO_ROOT / "local_assets" / "sc1_converted" / "p0"
DEFAULT_REPORT = REPO_ROOT / "local_assets" / "sc1_asset_extract_report.json"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _safe_name(asset_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in asset_id)


def _extract_asset(
    extractor: Path,
    starcraft_dir: Path,
    mpq_names: list[str],
    asset: dict,
    raw_out: Path,
) -> dict:
    raw_out.mkdir(parents=True, exist_ok=True)
    target = raw_out / f"{_safe_name(asset['id'])}.grp"
    attempts = []

    for mpq_name in mpq_names:
        mpq_path = starcraft_dir / mpq_name
        if not mpq_path.exists():
            attempts.append({"mpq": mpq_name, "status": "missing_mpq"})
            continue

        result = _run(
            [
                str(extractor),
                "extract-one",
                str(mpq_path),
                asset["mpq_path"],
                str(target),
            ]
        )
        attempts.append(
            {
                "mpq": mpq_name,
                "returncode": result.returncode,
                "stderr": result.stderr.strip(),
                "stdout": result.stdout.strip(),
            }
        )
        if result.returncode == 0:
            return {
                "id": asset["id"],
                "kind": asset["kind"],
                "mpq_path": asset["mpq_path"],
                "source_mpq": mpq_name,
                "raw_path": str(target),
                "status": "extracted",
                "attempts": attempts,
            }

    return {
        "id": asset["id"],
        "kind": asset["kind"],
        "mpq_path": asset["mpq_path"],
        "raw_path": str(target),
        "status": "missing",
        "attempts": attempts,
    }


def _convert_asset(raw_path: Path, asset_id: str, png_out: Path) -> dict:
    png_out.mkdir(parents=True, exist_ok=True)
    output = png_out / f"{_safe_name(asset_id)}.png"
    result = _run(
        [
            "python3",
            str(REPO_ROOT / "scripts" / "sc1_grp_to_png.py"),
            str(raw_path),
            str(output),
        ]
    )
    return {
        "png_path": str(output),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "status": "converted" if result.returncode == 0 else "convert_failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--starcraft-dir", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, default=DEFAULT_EXTRACTOR)
    parser.add_argument("--raw-out", type=Path, default=DEFAULT_RAW_OUT)
    parser.add_argument("--png-out", type=Path, default=DEFAULT_PNG_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--convert", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    mpq_names = manifest["mpq_priority_high_to_low"]
    records = []
    for asset in manifest["assets"]:
        record = _extract_asset(
            args.extractor,
            args.starcraft_dir,
            mpq_names,
            asset,
            args.raw_out,
        )
        if args.convert and record["status"] == "extracted":
            record["conversion"] = _convert_asset(
                Path(record["raw_path"]),
                asset["id"],
                args.png_out,
            )
        records.append(record)

    report = {
        "manifest": str(args.manifest),
        "starcraft_dir": str(args.starcraft_dir),
        "raw_out": str(args.raw_out),
        "png_out": str(args.png_out) if args.convert else "",
        "records": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")

    missing = [r["id"] for r in records if r["status"] != "extracted"]
    converted_failed = [
        r["id"]
        for r in records
        if r.get("conversion", {}).get("status") == "convert_failed"
    ]
    print(f"assets={len(records)} extracted={len(records) - len(missing)} missing={len(missing)}")
    if args.convert:
        print(f"converted_failed={len(converted_failed)}")
    print(f"report={args.report}")
    return 1 if missing or converted_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
