#!/usr/bin/env python3
"""Extract and optionally convert SC1 assets listed in a manifest.

Outputs are intended for ignored local folders. Do not commit generated assets
from commercial StarCraft MPQs into this repository.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p0_resource_manifest.json"
DEFAULT_EXTRACTOR = REPO_ROOT / "tools" / "mpq" / "bin" / "storm_extract"
DEFAULT_RAW_OUT = REPO_ROOT / "local_assets" / "sc1_mpq_raw" / "p0"
DEFAULT_PNG_OUT = REPO_ROOT / "local_assets" / "sc1_converted" / "p0"
DEFAULT_REPORT = REPO_ROOT / "local_assets" / "sc1_asset_extract_report.json"
DEFAULT_GENERATED_MANIFEST = (
    REPO_ROOT / "godot" / "assets" / "sc1_generated" / "generated_manifest.json"
)

_CONVERT_META_RE = re.compile(r"frames=(?P<frames>\d+)\s+frame_size=(?P<width>\d+)x(?P<height>\d+)")

# Target non-transparent body footprint in Godot world units for generated unit GRPs.
# Generated unit cells often contain large transparent padding, so units must scale
# from measured alpha content rather than full GRP cell size.
VISUAL_UNIT_TARGET_BODY_WORLD = {
    "SCV": 0.85,
    "Marine": 0.72,
    "Drone": 0.72,
    "Zergling": 0.62,
    "Probe": 0.95,
    "Zealot": 0.95,
}

# Target maximum on-screen footprint in Godot world units for generated GRP cells.
# These values keep same-tier buildings visually comparable after replacing old
# hand-cut atlas cells with exact MPQ frame sizes.
VISUAL_TARGET_MAX_WORLD = {
    "CommandCenter": 5.6,
    "Hatchery": 5.6,
    "Nexus": 5.6,
    "Barracks": 4.8,
    "Gateway": 4.8,
    "SpawningPool": 4.5,
    "Refinery": 4.0,
    "Extractor": 4.0,
    "Assimilator": 4.0,
    "Pylon": 1.8,
    "MineralFieldType1": 1.45,
    "MineralFieldType2": 1.45,
    "MineralFieldType3": 1.45,
    "VespeneGeyser": 2.2,
}

VISUAL_SELECTION_RADIUS = {
    "CommandCenter": 4.1,
    "Hatchery": 4.1,
    "Nexus": 4.1,
    "Barracks": 3.2,
    "Gateway": 3.2,
    "SpawningPool": 2.8,
    "Refinery": 2.8,
    "Extractor": 2.5,
    "Assimilator": 2.8,
    "Pylon": 2.0,
    "MineralFieldType1": 1.0,
    "MineralFieldType2": 1.0,
    "MineralFieldType3": 1.0,
    "VespeneGeyser": 1.6,
}


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
                "race": asset.get("race", ""),
                "mpq_path": asset["mpq_path"],
                "source_mpq": mpq_name,
                "raw_path": str(target),
                "status": "extracted",
                "attempts": attempts,
            }

    return {
        "id": asset["id"],
        "kind": asset["kind"],
        "race": asset.get("race", ""),
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


def _parse_conversion_metadata(stdout: str) -> tuple[int, int, int]:
    match = _CONVERT_META_RE.search(stdout)
    if not match:
        return (0, 0, 0)
    return (
        int(match.group("frames")),
        int(match.group("width")),
        int(match.group("height")),
    )


def _to_res_path(path: Path, batch: str = "", asset_id: str = "") -> str:
    """Convert a filesystem path to a Godot res:// path.

    When batch and asset_id are provided (batch extraction mode),
    we know the intended res:// path directly:
        res://assets/sc1_generated/{batch}/{asset_id}.png
    Otherwise fall back to path manipulation.
    """
    if batch and asset_id:
        return f"res://assets/sc1_generated/{batch}/{_safe_name(asset_id)}.png"
    resolved = path.resolve()
    godot_root = (REPO_ROOT / "godot").resolve()
    try:
        return "res://" + resolved.relative_to(godot_root).as_posix()
    except ValueError:
        parts = path.parts
        if "godot" in parts:
            index = parts.index("godot")
            return "res://" + Path(*parts[index + 1 :]).as_posix()
    return str(path)


def _measure_content_extent(
    png_path: Path,
    frame_count: int,
    frame_width: int,
    frame_height: int,
) -> int:
    if frame_count <= 0 or frame_width <= 0 or frame_height <= 0 or not png_path.exists():
        return 0

    from PIL import Image

    image = Image.open(png_path).convert("RGBA")
    columns = max(1, image.width // frame_width)
    extents: list[int] = []
    for frame_idx in range(frame_count):
        x = (frame_idx % columns) * frame_width
        y = (frame_idx // columns) * frame_height
        if x + frame_width > image.width or y + frame_height > image.height:
            continue
        frame = image.crop((x, y, x + frame_width, y + frame_height))
        bbox = frame.getchannel("A").getbbox()
        if not bbox:
            continue
        extents.append(max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
    if not extents:
        return 0
    return int(round(statistics.median(extents)))


DEFAULT_SCALE_CONFIG = REPO_ROOT / "tools" / "sc1_assets" / "visual_class_scale_config.json"


def _load_visual_class_targets(path: Path = DEFAULT_SCALE_CONFIG) -> dict[str, float]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    targets: dict[str, float] = {}
    for visual_class, entry in data.get("visual_classes", {}).items():
        lo = float(entry["body_world_min"])
        hi = float(entry["body_world_max"])
        targets[visual_class] = round((lo + hi) / 2.0, 4)
    return targets


def _visual_overrides(
    asset_id: str,
    kind: str,
    frame_width: int,
    frame_height: int,
    png_path: Path | None = None,
    frame_count: int = 0,
    visual_class: str = "",
    visual_class_targets: dict[str, float] | None = None,
) -> dict:
    if kind not in {"building", "resource", "unit"}:
        return {}
    max_dim = max(frame_width, frame_height)
    if kind == "unit":
        targets = visual_class_targets or {}
        target_max = VISUAL_UNIT_TARGET_BODY_WORLD.get(asset_id)
        if target_max is None and visual_class:
            target_max = targets.get(visual_class)
        content_extent = (
            _measure_content_extent(png_path, frame_count, frame_width, frame_height)
            if png_path
            else 0
        )
        scale_basis = content_extent if content_extent > 0 else max_dim
        if not target_max or scale_basis <= 0:
            return {}
        overrides = {
            "render_scale": round(target_max / scale_basis, 4),
        }
        if content_extent > 0:
            overrides["content_extent"] = content_extent
            overrides["scale_basis"] = "content_median_extent"
        return overrides

    target_max = VISUAL_TARGET_MAX_WORLD.get(asset_id)
    if not target_max or max_dim <= 0:
        return {}

    overrides = {
        "render_scale": round(target_max / max_dim, 4),
    }
    selection_radius = VISUAL_SELECTION_RADIUS.get(asset_id)
    if selection_radius is not None:
        overrides["selection_radius"] = selection_radius
    return overrides


def build_generated_manifest(
    records: list[dict],
    png_out: Path,
    batch: str = "p0",
    input_manifest: dict | None = None,
) -> dict:
    assets: dict[str, dict] = {}
    # Build visual_class lookup from input manifest if available
    vc_lookup: dict[str, str] = {}
    if input_manifest:
        for asset in input_manifest.get("assets", []):
            vc_lookup[asset["id"]] = asset.get("visual_class", "")
    visual_class_targets = _load_visual_class_targets()
    for record in records:
        conversion = record.get("conversion", {})
        if record.get("status") != "extracted" or conversion.get("status") != "converted":
            continue

        frame_count, frame_width, frame_height = _parse_conversion_metadata(
            str(conversion.get("stdout", ""))
        )
        kind = str(record.get("kind", ""))
        asset_id = str(record["id"])
        png_path = Path(str(conversion.get("png_path", png_out / f"{_safe_name(asset_id)}.png")))

        entry = {
            "kind": kind,
            "race": record.get("race", ""),
            "batch": batch,
            "runtime_enabled": kind in {"building", "resource"},
            "asset": _to_res_path(png_path, batch=batch, asset_id=asset_id),
            "source_mpq": record.get("source_mpq", ""),
            "mpq_path": record.get("mpq_path", ""),
            "frame_count": frame_count,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "atlas_rect": [0, 0, frame_width, frame_height],
        }
        # Carry visual_class from input manifest
        vc = vc_lookup.get(asset_id, "")
        if vc:
            entry["visual_class"] = vc
        entry.update(
            _visual_overrides(
                asset_id,
                kind,
                frame_width,
                frame_height,
                png_path,
                frame_count,
                visual_class=vc_lookup.get(asset_id, ""),
                visual_class_targets=visual_class_targets,
            )
        )
        assets[asset_id] = entry

    return {
        "schema_version": 1,
        "generated_by": "scripts/sc1_extract_manifest.py",
        "runtime_policy": "building_and_resource_overrides_with_visual_scale",
        "assets": assets,
    }


def _merge_manifests(existing: dict, incoming: dict) -> dict:
    """Merge *incoming* manifest entries into *existing*, preserving all keys."""
    merged = dict(existing)
    merged.setdefault("assets", {})
    for asset_id, entry in incoming.get("assets", {}).items():
        merged["assets"][asset_id] = entry
    # Ensure top-level metadata from incoming if missing in existing
    for key in ("schema_version", "generated_by", "runtime_policy"):
        if key not in merged and key in incoming:
            merged[key] = incoming[key]
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--starcraft-dir", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, default=DEFAULT_EXTRACTOR)
    parser.add_argument("--raw-out", type=Path, default=DEFAULT_RAW_OUT)
    parser.add_argument("--png-out", type=Path, default=DEFAULT_PNG_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--generated-manifest", type=Path, default=DEFAULT_GENERATED_MANIFEST)
    parser.add_argument("--convert", action="store_true")
    parser.add_argument(
        "--batch-out",
        action="store_true",
        help=(
            "Output to batch-specific subdirs derived from manifest scope "
            "(e.g. local_assets/sc1_mpq_raw/{batch}/). "
            "Defaults to 'p0' when scope is absent."
        ),
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    mpq_names = manifest["mpq_priority_high_to_low"]
    batch = manifest.get("batch", manifest.get("scope", "p0"))

    # Resolve output directories — batch-specific when --batch-out is set
    if args.batch_out:
        raw_out = REPO_ROOT / "local_assets" / "sc1_mpq_raw" / batch
        png_out = REPO_ROOT / "local_assets" / "sc1_converted" / batch
        # Always write to the top-level aggregate manifest, not per-batch
        generated_manifest_path = (
            args.generated_manifest
            or (REPO_ROOT / "godot" / "assets" / "sc1_generated" / "generated_manifest.json")
        )
    else:
        raw_out = args.raw_out
        png_out = args.png_out
        generated_manifest_path = args.generated_manifest

    records: list[dict] = []
    skipped = 0
    for asset in manifest["assets"]:
        # Skip assets whose mpq_path is PENDING
        if asset.get("mpq_path") == "PENDING":
            print(f"WARNING: skipping PENDING asset: {asset['id']}")
            skipped += 1
            continue

        record = _extract_asset(
            args.extractor,
            args.starcraft_dir,
            mpq_names,
            asset,
            raw_out,
        )
        if args.convert and record["status"] == "extracted":
            record["conversion"] = _convert_asset(
                Path(record["raw_path"]),
                asset["id"],
                png_out,
            )
        records.append(record)

    total = len(records) + skipped
    extracted = len(records) - sum(1 for r in records if r["status"] != "extracted")
    converted = sum(
        1 for r in records if r.get("conversion", {}).get("status") == "converted"
    )

    report = {
        "manifest": str(args.manifest),
        "starcraft_dir": str(args.starcraft_dir),
        "raw_out": str(raw_out),
        "png_out": str(png_out) if args.convert else "",
        "records": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")

    merged_total = 0
    if args.convert:
        batch_manifest = build_generated_manifest(
            records, png_out, batch=batch, input_manifest=manifest,
        )
        generated_manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Merge with existing generated_manifest.json if present
        if generated_manifest_path.exists():
            existing = json.loads(generated_manifest_path.read_text())
            merged = _merge_manifests(existing, batch_manifest)
        else:
            merged = batch_manifest

        generated_manifest_path.write_text(json.dumps(merged, indent=2) + "\n")
        merged_total = len(merged.get("assets", {}))

    missing = [r["id"] for r in records if r["status"] != "extracted"]
    converted_failed = [
        r["id"]
        for r in records
        if r.get("conversion", {}).get("status") == "convert_failed"
    ]
    print(
        f"total={total} extracted={extracted} converted={converted} "
        f"skipped={skipped} merged_total={merged_total}"
    )
    if args.convert:
        print(f"converted_failed={len(converted_failed)}")
        print(f"generated_manifest={generated_manifest_path}")
    print(f"report={args.report}")
    return 1 if missing or converted_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
