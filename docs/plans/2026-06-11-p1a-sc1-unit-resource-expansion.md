# P1 SC1 Resource Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand SC1 extracted assets from P0 (20 assets) to P1A (12 new units), with batch extraction, visual_class scaling, and Test Mode verification — all while keeping commercial PNGs out of git.

**Architecture:** Incremental batch pipeline. P1 manifest extends P0; generated_manifest.json merges both. Discovery tool probes MPQs for candidate paths. Visual_class replaces per-unit hardcoded scale targets. Test Mode gains batch filter and visual_class grouping.

**Tech Stack:** Python 3.11, `tools/mpq/bin/storm_extract`, `scripts/sc1_grp_to_png.py`, Pillow, Godot 4.x headless scripts, GDScript `SpriteLoader` / `game_view.gd`, pytest.

---

## Critical MPQ Path Discovery

`storm_extract` accepts MPQ-internal paths using `\` (backslash) as separator. In Python strings these appearas `\t`, `\p`, etc. (escape sequences). The P0 manifest uses JSON-escaped `unit\\terran\\scv.grp` which Python reads as `unit\terran\scv.grp`. StarDat.mpq has no `(listfile)` — all 2924 entries are hash-only `File00000682.xxx`. BrooDat.mpq **does** have a listfile with human-readable paths. Discovery must brute-force candidates against all 3 MPQs.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `tools/sc1_assets/p1a_resource_manifest.json` | P1A unit definitions |
| Create | `scripts/sc1_discover_assets.py` | MPQ path probe tool |
| Modify | `scripts/sc1_extract_manifest.py` | Batch support + manifest merge |
| Modify | `godot/scripts/sprite_loader.gd` | Batch filter + generated merge |
| Modify | `godot/scripts/game_view.gd` | visual_class grouping in Test Mode |
| Modify | `godot/scripts/test_sprite_loader_generated.gd` | P1A batch assertions |
| Create | `tests/godot/test_sc1_p1a_manifest.py` | P1A manifest schema + merge tests |

**Ignored (never committed):**
- `local_assets/sc1_mpq_raw/p1a/`
- `local_assets/sc1_converted/p1a/`
- `godot/assets/sc1_generated/p1a/`

---

## P1A Asset List (12 Units)

| ID | Race | visual_class | Expected MPQ Path | Source MPQ |
|----|------|-------------|-------------------|-----------|
| Firebat | terran | small_ground | `unit\terran\firebat.grp` | StarDat.mpq |
| Ghost | terran | small_ground | `unit\terran\ghost.grp` | StarDat.mpq |
| Vulture | terran | medium_ground | `unit\terran\vulture.grp` | StarDat.mpq |
| Tank | terran | large_ground | `unit\terran\tank.grp` | StarDat.mpq |
| Goliath | terran | medium_ground | `unit\terran\goliath.grp` | StarDat.mpq |
| Wraith | terran | small_air | `unit\terran\wraith.grp` | StarDat.mpq |
| Hydralisk | zerg | medium_ground | `unit\zerg\hydralisk.grp` | StarDat.mpq |
| Overlord | zerg | large_air | `unit\zerg\overlord.grp` | StarDat.mpq |
| Mutalisk | zerg | small_air | `unit\zerg\mutalisk.grp` | StarDat.mpq |
| Dragoon | protoss | medium_ground | `unit\protoss\dragoon.grp` | BrooDat.mpq |
| Reaver | protoss | large_ground | `unit\protoss\reaver.grp` | StarDat.mpq |
| Carrier | protoss | large_air | `unit\protoss\carrier.grp` | StarDat.mpq |

---

## Visual Class Scale Ranges

| visual_class | Body World Target Range | Notes |
|-------------|------------------------|-------|
| worker | 0.85 – 0.95 | SCV/Drone/Probe (P0) |
| small_ground | 0.70 – 0.85 | Marine/Zergling/Zealot (P0) + Firebat/Ghost |
| medium_ground | 0.90 – 1.15 | Vulture/Goliath/Hydralisk/Dragoon |
| large_ground | 1.30 – 1.80 | Tank/Reaver/Ultralisk |
| small_air | 0.90 – 1.20 | Wraith/Mutalisk/Scourge |
| large_air | 1.60 – 2.20 | Overlord/Carrier/BattleCruiser |
| building | tier-specific map | Same as P0 VISUAL_TARGET_MAX_WORLD |

---

## Task 1: Create P1A Resource Manifest

**Files:**
- Create: `tools/sc1_assets/p1a_resource_manifest.json`

- [ ] **Step 1: Write the manifest file**

```json
{
  "schema_version": 2,
  "scope": "p1a_core_units",
  "mpq_priority_high_to_low": [
    "Patch_rt.mpq",
    "BrooDat.mpq",
    "StarDat.mpq"
  ],
  "palette": "tools/mpq/PyMS/Palettes/Units.pal",
  "assets": [
    {
      "id": "Firebat",
      "kind": "unit",
      "race": "terran",
      "visual_class": "small_ground",
      "mpq_path": "unit\\terran\\firebat.grp",
      "godot_asset": "res://assets/sprites/units/Firebat.png"
    },
    {
      "id": "Ghost",
      "kind": "unit",
      "race": "terran",
      "visual_class": "small_ground",
      "mpq_path": "unit\\terran\\ghost.grp",
      "godot_asset": "res://assets/sprites/units/Ghost.png"
    },
    {
      "id": "Vulture",
      "kind": "unit",
      "race": "terran",
      "visual_class": "medium_ground",
      "mpq_path": "unit\\terran\\vulture.grp",
      "godot_asset": "res://assets/sprites/units/Vulture.png"
    },
    {
      "id": "Tank",
      "kind": "unit",
      "race": "terran",
      "visual_class": "large_ground",
      "mpq_path": "unit\\terran\\tank.grp",
      "godot_asset": "res://assets/sprites/units/Tank.png"
    },
    {
      "id": "Goliath",
      "kind": "unit",
      "race": "terran",
      "visual_class": "medium_ground",
      "mpq_path": "unit\\terran\\goliath.grp",
      "godot_asset": "res://assets/sprites/units/Goliath.png"
    },
    {
      "id": "Wraith",
      "kind": "unit",
      "race": "terran",
      "visual_class": "small_air",
      "mpq_path": "unit\\terran\\wraith.grp",
      "godot_asset": "res://assets/sprites/units/Wraith.png"
    },
    {
      "id": "Hydralisk",
      "kind": "unit",
      "race": "zerg",
      "visual_class": "medium_ground",
      "mpq_path": "unit\\zerg\\hydralisk.grp",
      "godot_asset": "res://assets/sprites/units/Hydralisk.png"
    },
    {
      "id": "Overlord",
      "kind": "unit",
      "race": "zerg",
      "visual_class": "large_air",
      "mpq_path": "unit\\zerg\\overlord.grp",
      "godot_asset": "res://assets/sprites/units/Overlord.png"
    },
    {
      "id": "Mutalisk",
      "kind": "unit",
      "race": "zerg",
      "visual_class": "small_air",
      "mpq_path": "unit\\zerg\\mutalisk.grp",
      "godot_asset": "res://assets/sprites/units/Mutalisk.png"
    },
    {
      "id": "Dragoon",
      "kind": "unit",
      "race": "protoss",
      "visual_class": "medium_ground",
      "mpq_path": "unit\\protoss\\dragoon.grp",
      "godot_asset": "res://assets/sprites/units/Dragoon.png"
    },
    {
      "id": "Reaver",
      "kind": "unit",
      "race": "protoss",
      "visual_class": "large_ground",
      "mpq_path": "unit\\protoss\\reaver.grp",
      "godot_asset": "res://assets/sprites/units/Reaver.png"
    },
    {
      "id": "Carrier",
      "kind": "unit",
      "race": "protoss",
      "visual_class": "large_air",
      "mpq_path": "unit\\protoss\\carrier.grp",
      "godot_asset": "res://assets/sprites/units/Carrier.png"
    }
  ]
}
```

- [ ] **Step 2: Validate JSON syntax**

```bash
python3 -c "import json; json.loads(open('tools/sc1_assets/p1a_resource_manifest.json').read()); print('valid JSON')"
```

Expected: `valid JSON`

- [ ] **Step 3: Commit manifest only**

```bash
git add tools/sc1_assets/p1a_resource_manifest.json
git commit -m "feat(assets): add p1a sc1 unit resource manifest (12 units)"
```

---

## Task 2: Build MPQ Path Discovery Tool

**Files:**
- Create: `scripts/sc1_discover_assets.py`

- [ ] **Step 1: Write the discovery script**

```python
#!/usr/bin/env python3
"""Discover SC1 MPQ paths for candidate asset names.

Brute-force probes storm_extract extract-one against Patch_rt.mpq,
BrooDat.mpq, and StarDat.mpq with multiple path patterns.
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

# Common MPQ path prefixes for GRP sprites
PATH_PATTERNS = [
    "unit\\{race}\\{name}.grp",
    "unit\\{race}\\{name}norm.grp",
    "unit\\{race}\\{name}burr.grp",
    "unit\\bullet\\{name}.grp",
    "unit\\neutral\\{name}.grp",
]

RACE_MAP = {
    "terran": "terran",
    "zerg": "zerg",
    "protoss": "protoss",
    "neutral": "neutral",
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
        capture_output=True, text=True, timeout=10,
    )
    return result.returncode == 0


def discover(
    extractor: Path,
    starcraft_dir: Path,
    candidates: list[dict],
    out_path: Path,
) -> dict:
    """Probe each candidate against all MPQs and path patterns."""
    results = []
    for cand in candidates:
        asset_id = cand["id"]
        race = RACE_MAP.get(cand.get("race", ""), cand.get("race", ""))
        name_lower = asset_id.lower()
        found = False
        for pattern in PATH_PATTERNS:
            formatted = pattern.format(race=race, name=name_lower)
            for mpq_name in MPQ_PRIORITY:
                mpq_path = starcraft_dir / mpq_name
                tmp_out = out_path.parent / f"_probe_{asset_id}.tmp"
                if _probe(extractor, mpq_path, formatted, tmp_out):
                    if tmp_out.exists():
                        tmp_out.unlink()
                    results.append({
                        "id": asset_id,
                        "kind": cand.get("kind", "unit"),
                        "race": cand.get("race", ""),
                        "visual_class": cand.get("visual_class", ""),
                        "mpq_path": formatted,
                        "source_mpq": mpq_name,
                        "status": "found",
                    })
                    found = True
                    break
            if found:
                break
        if not found:
            results.append({
                "id": asset_id,
                "kind": cand.get("kind", "unit"),
                "race": cand.get("race", ""),
                "visual_class": cand.get("visual_class", ""),
                "mpq_path": "",
                "source_mpq": "",
                "status": "missing",
            })

    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "total": len(results),
        "found": sum(1 for r in results if r["status"] == "found"),
        "missing": sum(1 for r in results if r["status"] == "missing"),
        "candidates": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover SC1 MPQ asset paths")
    parser.add_argument("--manifest", type=Path,
                        default=REPO_ROOT / "tools" / "sc1_assets" / "p1a_resource_manifest.json")
    parser.add_argument("--starcraft-dir", type=Path, default=DEFAULT_STARSCRAFT_DIR)
    parser.add_argument("--extractor", type=Path, default=DEFAULT_EXTRACTOR)
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "local_assets" / "sc1_discovery" / "p1a_asset_candidates.json")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    candidates = manifest["assets"]
    report = discover(args.extractor, args.starcraft_dir, candidates, args.out)
    print(f"total={report['total']} found={report['found']} missing={report['missing']}")
    print(f"report={args.out}")
    return 0 if report["missing"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run discovery against P1A manifest**

```bash
python3 scripts/sc1_discover_assets.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --out local_assets/sc1_discovery/p1a_asset_candidates.json
```

Expected: `total=12 found=12 missing=0`

If some assets are `missing`, update `mpq_path` in the manifest based on the closest match found, then re-run discovery.

- [ ] **Step 3: Run ruff + py_compile**

```bash
ruff check scripts/sc1_discover_assets.py
python3 -m py_compile scripts/sc1_discover_assets.py
```

Expected: `All checks passed!`, exit code 0.

- [ ] **Step 4: Commit discovery script**

```bash
git add scripts/sc1_discover_assets.py
git commit -m "feat(assets): add sc1 MPQ path discovery tool"
```

---

## Task 3: Extend Extract Script for Batch + Manifest Merge

**Files:**
- Modify: `scripts/sc1_extract_manifest.py`

- [ ] **Step 1: Add `--manifest` CLI argument**

In `main()`, add an optional `--manifest` argument that defaults to P0 but can point to P1A:

```python
parser.add_argument(
    "--manifest",
    type=Path,
    default=DEFAULT_MANIFEST,
    help="Resource manifest JSON (default: p0)",
)
```

Replace all references to `DEFAULT_MANIFEST` in `main()` with `args.manifest`.

- [ ] **Step 2: Add `--batch-out` to control output directory**

```python
parser.add_argument(
    "--batch-out",
    type=str,
    default="p0",
    help="Batch subdirectory for raw/converted/generated output (default: p0)",
)
```

Wire `raw_out`, `png_out`, and generated_manifest subdirectory to use this batch name:

```python
raw_out = DEFAULT_RAW_OUT.parent / args.batch_out
png_out = DEFAULT_PNG_OUT.parent / args.batch_out
```

- [ ] **Step 3: Add manifest merge logic to `build_generated_manifest`**

After building the new batch's manifest, merge with existing `generated_manifest.json`:

```python
def build_generated_manifest(
    records: list[dict],
    png_out: Path,
    existing_manifest_path: Path | None = None,
) -> dict:
    """Build generated manifest, merging with existing if present."""
    manifest: dict = {
        "schema_version": 2,
        "generated_by": "sc1_extract_manifest.py",
        "runtime_policy": {"default_enabled": True},
        "assets": {},
    }

    # Load existing manifest if present
    if existing_manifest_path and existing_manifest_path.exists():
        existing = json.loads(existing_manifest_path.read_text())
        manifest["assets"] = existing.get("assets", {})

    # Add/overwrite with new records
    for record in records:
        asset_id = record["id"]
        entry = _build_asset_entry(record, png_out)
        entry["batch"] = record.get("batch", "p0")
        entry["runtime_enabled"] = True
        entry["visual_class"] = record.get("visual_class", "")
        manifest["assets"][asset_id] = entry

    return manifest
```

Update `main()` to pass `existing_manifest_path=DEFAULT_GENERATED_MANIFEST` when calling `build_generated_manifest`.

- [ ] **Step 4: Propagate `visual_class` from input manifest through records**

In the extraction loop, read `visual_class` from each asset dict:

```python
record = _extract_asset(...)
record["visual_class"] = asset.get("visual_class", "")
record["batch"] = args.batch_out
```

- [ ] **Step 5: Run extraction for P1A**

```bash
python3 scripts/sc1_extract_manifest.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --batch-out p1a \
  --convert
```

Expected: `assets=12 extracted=12 missing=0 converted_failed=0`

- [ ] **Step 6: Verify merged generated_manifest has 32 assets**

```bash
python3 -c "
import json
from pathlib import Path
m = json.loads(Path('godot/assets/sc1_generated/generated_manifest.json').read_text())
print('assets', len(m['assets']))
from collections import Counter
for key, count in sorted(Counter((v['race'], v['kind']) for v in m['assets'].values()).items()):
    print(key, count)
"
```

Expected: `assets 32` with P0 (20) + P1A (12) combined.

- [ ] **Step 7: Verify P1A unit scale ranges**

```bash
python3 -c "
import json
from pathlib import Path
RANGES = {
    'worker': (0.85, 0.95),
    'small_ground': (0.70, 0.85),
    'medium_ground': (0.90, 1.15),
    'large_ground': (1.30, 1.80),
    'small_air': (0.90, 1.20),
    'large_air': (1.60, 2.20),
}
m = json.loads(Path('godot/assets/sc1_generated/generated_manifest.json').read_text())
for aid, e in m['assets'].items():
    if e['kind'] != 'unit': continue
    vc = e.get('visual_class', '')
    bw = e['content_extent'] * float(e['render_scale'])
    if vc in RANGES:
        lo, hi = RANGES[vc]
        ok = lo <= bw <= hi
        print(aid, vc, round(bw, 3), '✅' if ok else '❌', f'[{lo}-{hi}]')
        assert ok, f'{aid} body_world={bw} out of range for {vc}'
    else:
        print(aid, vc, round(bw, 3), '⚠️ no range defined')
"
```

Expected: no assertion failures.

- [ ] **Step 8: Run ruff + py_compile**

```bash
ruff check scripts/sc1_extract_manifest.py
python3 -m py_compile scripts/sc1_extract_manifest.py
```

- [ ] **Step 9: Commit extract script changes**

```bash
git add scripts/sc1_extract_manifest.py
git commit -m "feat(assets): add batch + manifest merge + visual_class to extract script"
```

---

## Task 4: Visual Class Scale Configuration

**Files:**
- Create: `tools/sc1_assets/visual_class_scale_config.json`

- [ ] **Step 1: Write scale config file**

```json
{
  "schema_version": 1,
  "visual_classes": {
    "worker":         { "body_world_min": 0.85, "body_world_max": 0.95 },
    "small_ground":   { "body_world_min": 0.70, "body_world_max": 0.85 },
    "medium_ground":  { "body_world_min": 0.90, "body_world_max": 1.15 },
    "large_ground":   { "body_world_min": 1.30, "body_world_max": 1.80 },
    "small_air":      { "body_world_min": 0.90, "body_world_max": 1.20 },
    "large_air":      { "body_world_min": 1.60, "body_world_max": 2.20 }
  }
}
```

- [ ] **Step 2: Write scale validation test**

Create `tests/godot/test_visual_class_scale.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCALE_CONFIG = REPO_ROOT / "tools" / "sc1_assets" / "visual_class_scale_config.json"
GENERATED_MANIFEST = REPO_ROOT / "godot" / "assets" / "sc1_generated" / "generated_manifest.json"


def test_scale_config_schema() -> None:
    cfg = json.loads(SCALE_CONFIG.read_text())
    assert cfg["schema_version"] == 1
    assert len(cfg["visual_classes"]) >= 5
    for vc, entry in cfg["visual_classes"].items():
        assert "body_world_min" in entry, f"{vc} missing body_world_min"
        assert "body_world_max" in entry, f"{vc} missing body_world_max"
        assert entry["body_world_min"] < entry["body_world_max"], f"{vc} min >= max"


def test_p1a_units_in_scale_range() -> None:
    if not GENERATED_MANIFEST.exists():
        return  # Skip if not yet generated locally
    cfg = json.loads(SCALE_CONFIG.read_text())
    manifest = json.loads(GENERATED_MANIFEST.read_text())
    ranges = cfg["visual_classes"]
    for asset_id, entry in manifest["assets"].items():
        if entry["kind"] != "unit":
            continue
        vc = entry.get("visual_class", "")
        if vc not in ranges:
            continue
        body_world = entry["content_extent"] * float(entry["render_scale"])
        lo = ranges[vc]["body_world_min"]
        hi = ranges[vc]["body_world_max"]
        assert lo <= body_world <= hi, (
            f"{asset_id} ({vc}) body_world={body_world:.3f} "
            f"outside [{lo}, {hi}]"
        )
```

- [ ] **Step 3: Run scale validation test**

```bash
pytest tests/godot/test_visual_class_scale.py -v
```

Expected: both tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/sc1_assets/visual_class_scale_config.json tests/godot/test_visual_class_scale.py
git commit -m "feat(assets): add visual_class scale config + validation tests"
```

---

## Task 5: Update Godot SpriteLoader for Batch Merge

**Files:**
- Modify: `godot/scripts/sprite_loader.gd`

- [ ] **Step 1: Add batch field parsing to `_load_generated_manifest`**

In `_load_generated_manifest()`, after loading the JSON, iterate assets and read the `batch` and `visual_class` fields:

```gdscript
func _load_generated_manifest() -> void:
    _generated_manifest = {}
    if not FileAccess.file_exists(_generated_manifest_path):
        return
    var f := FileAccess.open(_generated_manifest_path, FileAccess.READ)
    if f:
        var json := JSON.new()
        if json.parse(f.get_as_text()) == OK and json.data is Dictionary:
            _generated_manifest = json.data
            for asset_id in _generated_manifest.get("assets", {}):
                var entry: Dictionary = _generated_manifest["assets"][asset_id]
                # Store batch and visual_class for filtering
                entry["_batch"] = entry.get("batch", "p0")
                entry["_visual_class"] = entry.get("visual_class", "")
            print("[SpriteLoader] Loaded generated SC1 manifest: %d assets" % _generated_manifest.get("assets", {}).size())
```

- [ ] **Step 2: Add `get_assets_by_batch` helper**

```gdscript
func get_assets_by_batch(batch_name: String) -> Dictionary:
    var result: Dictionary = {}
    if not _generated_manifest.has("assets"):
        return result
    for asset_id in _generated_manifest["assets"]:
        var entry: Dictionary = _generated_manifest["assets"][asset_id]
        if entry.get("_batch", "p0") == batch_name:
            result[asset_id] = entry
    return result
```

- [ ] **Step 3: Add `get_assets_by_visual_class` helper**

```gdscript
func get_assets_by_visual_class(visual_class: String) -> Dictionary:
    var result: Dictionary = {}
    if not _generated_manifest.has("assets"):
        return result
    for asset_id in _generated_manifest["assets"]:
        var entry: Dictionary = _generated_manifest["assets"][asset_id]
        if entry.get("_visual_class", "") == visual_class:
            result[asset_id] = entry
    return result
```

- [ ] **Step 4: Run Godot headless SpriteLoader test**

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sprite_loader_generated.gd 2>&1
```

Expected: `SpriteLoader generated manifest test: 5 passed, 0 failed` (same as before, no regression).

- [ ] **Step 5: Commit**

```bash
git add godot/scripts/sprite_loader.gd
git commit -m "feat(godot): add batch + visual_class helpers to SpriteLoader"
```

---

## Task 6: Update Test Mode for Batch Filter + Visual Class Grouping

**Files:**
- Modify: `godot/scripts/game_view.gd`

- [ ] **Step 1: Add "Batch" option to Test Mode filter panel**

In `_create_test_filter_panel()`, add a new OptionButton for batch selection:

```gdscript
var _batch_filter_btn := OptionButton.new()
_batch_filter_btn.name = "BatchFilter"
_batch_filter_btn.add_item("All", 0)
_batch_filter_btn.add_item("P0", 1)
_batch_filter_btn.add_item("P1A", 2)
_batch_filter_btn.item_selected.connect(_on_test_batch_filter_selected)
panel.add_child(_batch_filter_btn)
```

Add the handler:

```gdscript
var _test_batch_filter: String = ""

func _on_test_batch_filter_selected(index: int) -> void:
    match index:
        0: _test_batch_filter = ""
        1: _test_batch_filter = "p0"
        2: _test_batch_filter = "p1a"
    _rebuild_test_gallery()
```

- [ ] **Step 2: Apply batch filter in `_build_test_entities`**

In `_build_test_entities()`, when iterating generated manifest assets, skip entries that don't match the batch filter:

```gdscript
for asset_id in manifest_assets:
    var entry: Dictionary = manifest_assets[asset_id]
    if _test_batch_filter != "" and entry.get("_batch", "p0") != _test_batch_filter:
        continue
    # ... existing race/kind filtering ...
```

- [ ] **Step 3: Group units by visual_class in Test Mode display**

In `_add_test_unit_pair()`, add a visual_class label above each group:

```gdscript
func _add_test_visual_class_header(visual_class: String, pos: Vector2) -> void:
    var label := Label.new()
    label.text = visual_class
    label.position = pos
    label.add_theme_font_size_override("font_size", 14)
    _test_entities_container.add_child(label)
```

In `_build_test_entities()`, sort units by `visual_class` before layout:

```gdscript
var units_by_class: Dictionary = {}
for asset_id in manifest_assets:
    var entry: Dictionary = manifest_assets[asset_id]
    if entry.kind != "unit": continue
    var vc: String = entry.get("_visual_class", "unknown")
    if not units_by_class.has(vc):
        units_by_class[vc] = []
    units_by_class[vc].append(asset_id)

var y_offset := start_y
for vc in ["worker", "small_ground", "medium_ground", "large_ground", "small_air", "large_air"]:
    if not units_by_class.has(vc): continue
    _add_test_visual_class_header(vc, Vector2(start_x, y_offset))
    y_offset += 20
    for asset_id in units_by_class[vc]:
        var entry: Dictionary = manifest_assets[asset_id]
        _add_test_unit_pair(asset_id, entry, entry.race, Vector2(start_x, y_offset))
        y_offset += 100
```

- [ ] **Step 4: Add flight indicator for air units**

In `_add_test_unit_pair()`, if `visual_class` contains "air", add a small "✈" label:

```gdscript
if entry.get("_visual_class", "").find("air") >= 0:
    var flight_label := Label.new()
    flight_label.text = "✈"
    flight_label.position = pos + Vector2(0, -16)
    flight_label.add_theme_font_size_override("font_size", 12)
    flight_label.add_theme_color_override("font_color", Color.CYAN)
    _test_entities_container.add_child(flight_label)
```

- [ ] **Step 5: Run Godot headless GameView test**

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_game_view_probe_override.gd 2>&1
```

Expected: `GameView Probe override test: 3 passed, 0 failed`

- [ ] **Step 6: Commit**

```bash
git add godot/scripts/game_view.gd
git commit -m "feat(godot): add batch filter + visual_class grouping + flight indicator to Test Mode"
```

---

## Task 7: P1A Manifest + Merge Tests

**Files:**
- Create: `tests/godot/test_sc1_p1a_manifest.py`

- [ ] **Step 1: Write the test file**

```python
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
P0_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p0_resource_manifest.json"
P1A_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p1a_resource_manifest.json"
SCALE_CONFIG = REPO_ROOT / "tools" / "sc1_assets" / "visual_class_scale_config.json"
GENERATED_MANIFEST = REPO_ROOT / "godot" / "assets" / "sc1_generated" / "generated_manifest.json"


def test_p1a_manifest_schema() -> None:
    m = json.loads(P1A_MANIFEST.read_text())
    assert m["schema_version"] == 2
    assert m["scope"] == "p1a_core_units"
    assert len(m["assets"]) == 12
    for asset in m["assets"]:
        assert "id" in asset
        assert "kind" in asset
        assert "race" in asset
        assert "mpq_path" in asset
        assert "visual_class" in asset


def test_p1a_no_id_overlap_with_p0() -> None:
    p0 = json.loads(P0_MANIFEST.read_text())
    p1a = json.loads(P1A_MANIFEST.read_text())
    p0_ids = {a["id"] for a in p0["assets"]}
    p1a_ids = {a["id"] for a in p1a["assets"]}
    overlap = p0_ids & p1a_ids
    assert overlap == set(), f"ID overlap between P0 and P1A: {overlap}"


def test_p1a_visual_classes_valid() -> None:
    cfg = json.loads(SCALE_CONFIG.read_text())
    valid_classes = set(cfg["visual_classes"].keys())
    m = json.loads(P1A_MANIFEST.read_text())
    for asset in m["assets"]:
        vc = asset.get("visual_class", "")
        assert vc in valid_classes, f"{asset['id']} has invalid visual_class: {vc}"


def test_generated_manifest_merge() -> None:
    """Only runs if generated_manifest exists locally (after extraction)."""
    if not GENERATED_MANIFEST.exists():
        return
    m = json.loads(GENERATED_MANIFEST.read_text())
    assets = m.get("assets", {})
    p0_count = sum(1 for e in assets.values() if e.get("batch", "p0") == "p0")
    p1a_count = sum(1 for e in assets.values() if e.get("batch", "p1a") == "p1a")
    assert p0_count == 20, f"Expected 20 P0 assets, got {p0_count}"
    assert p1a_count == 12, f"Expected 12 P1A assets, got {p1a_count}"


def test_generated_manifest_unit_fields() -> None:
    if not GENERATED_MANIFEST.exists():
        return
    m = json.loads(GENERATED_MANIFEST.read_text())
    for asset_id, entry in m["assets"].items():
        if entry["kind"] != "unit":
            continue
        assert "content_extent" in entry, f"{asset_id} missing content_extent"
        assert "scale_basis" in entry, f"{asset_id} missing scale_basis"
        assert "render_scale" in entry, f"{asset_id} missing render_scale"
        assert "visual_class" in entry, f"{asset_id} missing visual_class"
        assert "frame_count" in entry, f"{asset_id} missing frame_count"
        assert "frame_width" in entry, f"{asset_id} missing frame_width"
        assert "frame_height" in entry, f"{asset_id} missing frame_height"
```

- [ ] **Step 2: Run P1A tests**

```bash
pytest tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py -v
```

Expected: all PASS.

- [ ] **Step 3: Run ruff + py_compile**

```bash
ruff check tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py
python3 -m py_compile tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py
git commit -m "test(assets): add p1a manifest schema + merge + visual_class scale tests"
```

---

## Task 8: Update Godot Headless Tests for P1A

**Files:**
- Modify: `godot/scripts/test_sprite_loader_generated.gd`

- [ ] **Step 1: Add P1A batch assertion**

```gdscript
func _test_p1a_batch_assets() -> bool:
    var loader := SpriteLoader.new()
    var p1a := loader.get_assets_by_batch("p1a")
    if p1a.size() != 12:
        _fail("P1A batch: expected 12, got %d" % p1a.size())
        return false
    # Verify Firebat specifically
    if not p1a.has("Firebat"):
        _fail("P1A batch missing Firebat")
        return false
    if p1a["Firebat"].get("_visual_class", "") != "small_ground":
        _fail("Firebat visual_class wrong")
        return false
    _pass("P1A batch assets (12, Firebat=small_ground)")
    return true
```

Call it from the test runner function alongside existing tests.

- [ ] **Step 2: Run Godot headless test**

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sprite_loader_generated.gd 2>&1
```

Expected: `SpriteLoader generated manifest test: 6 passed, 0 failed`

- [ ] **Step 3: Commit**

```bash
git add godot/scripts/test_sprite_loader_generated.gd
git commit -m "test(godot): add p1a batch assertion to SpriteLoader headless test"
```

---

## Task 9: Update SOP Document

**Files:**
- Modify: `docs/plans/2026-06-11-sc1-resource-extraction-validation-sop.md`

- [ ] **Step 1: Append P1A section**

Add at the end:

```markdown
---

## P1A Extension: Core Units

### Added Assets (12 units)

| Asset | Race | visual_class | MPQ Path | Source |
|-------|------|-------------|----------|--------|
| Firebat | terran | small_ground | unit\terran\firebat.grp | StarDat.mpq |
| Ghost | terran | small_ground | unit\terran\ghost.grp | StarDat.mpq |
| Vulture | terran | medium_ground | unit\terran\vulture.grp | StarDat.mpq |
| Tank | terran | large_ground | unit\terran\tank.grp | StarDat.mpq |
| Goliath | terran | medium_ground | unit\terran\goliath.grp | StarDat.mpq |
| Wraith | terran | small_air | unit\terran\wraith.grp | StarDat.mpq |
| Hydralisk | zerg | medium_ground | unit\zerg\hydralisk.grp | StarDat.mpq |
| Overlord | zerg | large_air | unit\zerg\overlord.grp | StarDat.mpq |
| Mutalisk | zerg | small_air | unit\zerg\mutalisk.grp | StarDat.mpq |
| Dragoon | protoss | medium_ground | unit\protoss\dragoon.grp | BrooDat.mpq |
| Reaver | protoss | large_ground | unit\protoss\reaver.grp | StarDat.mpq |
| Carrier | protoss | large_air | unit\protoss\carrier.grp | StarDat.mpq |

### Visual QA Checklist (P1A)

1. **Correct identity**: Each sprite shows the right unit (not a different unit or building).
2. **Transparency**: No opaque background box; transparent pixels are clean.
3. **Crop/scale**: Body fits within expected visual_class range; not tiny/collapsed.
4. **Cross-race proportion**: Workers remain comparable; small_ground units remain readable.
5. **Air unit separation**: ✈ indicator present; air units visually separated from ground.
6. **Animation**: move previews animate with green line; atk previews animate with red line + flash.

### Batch Commands

```bash
# Discovery
python3 scripts/sc1_discover_assets.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json

# Extraction + conversion
python3 scripts/sc1_extract_manifest.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json \
  --batch-out p1a \
  --convert

# Validation
pytest tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py -q
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-06-11-sc1-resource-extraction-validation-sop.md
git commit -m "docs: add p1a core units section to resource extraction SOP"
```

---

## Task 10: Final Gate

- [ ] **Step 1: Run all static tests**

```bash
pytest tests/godot/test_sc1_generated_manifest.py tests/godot/test_presentation_manifest.py tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py -q
```

Expected: all PASS.

- [ ] **Step 2: Run architecture lint**

```bash
python3 scripts/lint_deps.py simcore/ agents/ runtime/ proto/
```

Expected: no L1→L2 violations (P0-1 fix already committed).

- [ ] **Step 3: Run lint + compile**

```bash
ruff check scripts/sc1_extract_manifest.py scripts/sc1_discover_assets.py tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py
python3 -m py_compile scripts/sc1_extract_manifest.py scripts/sc1_discover_assets.py
```

Expected: all clean.

- [ ] **Step 4: Run Godot headless tests**

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sprite_loader_generated.gd 2>&1
```

Expected: `SpriteLoader generated manifest test: 6 passed, 0 failed`

- [ ] **Step 5: Verify gitignore**

```bash
git check-ignore godot/assets/sc1_generated/generated_manifest.json local_assets/sc1_mpq_raw/p1a/ local_assets/sc1_converted/p1a/
```

Expected: all 3 paths ignored.

- [ ] **Step 6: Verify no commercial PNGs staged**

```bash
git diff --cached --name-only | grep -E '\.(png|grp|wav)$'
```

Expected: empty output (no binary assets staged).

- [ ] **Step 7: Summary commit if any uncommitted code remains**

```bash
git status --short
# If any scripts/tests/docs are uncommitted:
git add scripts/ tests/ tools/sc1_assets/ docs/
git commit -m "chore: final p1a resource pipeline commit"
```

---

## Acceptance Criteria

The P1A iteration is complete when:

- P0 (20) + P1A (12) = 32 assets in `generated_manifest.json`.
- Every P1A unit has `visual_class`, `content_extent`, `scale_basis`, `render_scale`, `frame_count/width/height`.
- Each `visual_class` maps to a valid range in `visual_class_scale_config.json`.
- No unit's `body_world` falls outside its `visual_class` range.
- `lint_deps.py` passes (no L1→L2 violations).
- All Python and Godot headless tests pass.
- No commercial PNG/GRP/WAV files are committed.
- Godot Test Mode shows batch filter (All/P0/P1A) and visual_class grouping.
- Air units show ✈ indicator and are visually separated from ground units.
