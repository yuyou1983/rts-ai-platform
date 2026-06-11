# SC1 P1A Reproducible Scale And P1B Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make P1A generated SC1 resources fully reproducible from source manifests and MPQs, then start P1B building/resource expansion on top of a stable generated-manifest contract.

**Architecture:** `tools/sc1_assets/*.json` are the committed source of truth. `scripts/sc1_extract_manifest.py` must be able to regenerate the top-level Godot generated manifest deterministically from those source manifests plus local MPQs. Generated commercial PNG/GRP files remain ignored; committed files are limited to manifests, scripts, tests, docs, and the metadata-only `godot/assets/sc1_generated/generated_manifest.json`.

**Tech Stack:** Python 3.11, Pillow, `tools/mpq/bin/storm_extract`, `scripts/sc1_grp_to_png.py`, Godot 4.6 headless scripts, GDScript `SpriteLoader`, pytest, ruff.

---

## Gate Check Snapshot

Checked on branch `codex-sc1-mpq-resource-sync` after commit:

```text
77bb6be fix(assets): stabilize p0 p1a generated manifest contract
```

Passing checks:

```bash
pytest tests/godot/test_sc1_generated_manifest.py tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py tests/godot/test_presentation_manifest.py -q
python3 scripts/sc1_discover_assets.py --manifest tools/sc1_assets/p1a_resource_manifest.json --starcraft-dir /Users/yuyou/code/StarCraft --out /private/tmp/p1a_asset_candidates_verify.json
ruff check scripts/sc1_extract_manifest.py scripts/sc1_discover_assets.py tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py
python3 -m py_compile scripts/sc1_extract_manifest.py scripts/sc1_discover_assets.py scripts/sc1_grp_to_png.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sprite_loader_generated.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_p1a_sprite_loader.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_game_view_probe_override.gd
```

Current observed state:

```text
P1A discovery: total=12 found=12 missing=0 pending=0
Top-level generated manifest: 32 assets
Wraith path: unit\terran\phoenix.grp
Reaver path: unit\protoss\trilob.grp
```

Blocking concern before P1B:

```text
python3 scripts/sc1_extract_manifest.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --raw-out /private/tmp/sc1_verify_raw \
  --png-out /private/tmp/sc1_verify_png \
  --report /private/tmp/sc1_verify_report.json \
  --generated-manifest /private/tmp/sc1_verify_generated_manifest.json \
  --convert
```

The temporary manifest extracts all 12 P1A assets, but every P1A unit is missing `render_scale`, `content_extent`, and `scale_basis`. The current top-level `godot/assets/sc1_generated/generated_manifest.json` has those fields, so it is not reproducible from the extraction script yet.

Verdict: **CONCERNS / NO-GO for P1B extraction until Task 1 and Task 2 are complete.**

---

## Target End State

- `scripts/sc1_extract_manifest.py` computes unit scale from `visual_class` for all generated units not covered by explicit per-asset overrides.
- `--batch-out` writes raw and PNG outputs into batch directories but still updates the top-level aggregate `godot/assets/sc1_generated/generated_manifest.json`.
- Re-running P0 then P1A from MPQs produces the same 32-asset top-level manifest contract.
- Every generated unit has `visual_class`, `content_extent`, `render_scale`, and `scale_basis`.
- P1B starts only after P1A regeneration is deterministic.

---

## Task 1: Add Visual-Class Scale Generation

**Files:**
- Modify: `scripts/sc1_extract_manifest.py`
- Modify: `tests/godot/test_sc1_generated_manifest.py`

- [ ] **Step 1: Add a failing test for P1A visual_class scale**

Append this test to `tests/godot/test_sc1_generated_manifest.py`:

```python
def test_generated_manifest_scales_units_from_visual_class(tmp_path: Path) -> None:
    firebat_path = tmp_path / "Firebat.png"
    reaver_path = tmp_path / "Reaver.png"
    wraith_path = tmp_path / "Wraith.png"
    _write_padded_unit_sheet(firebat_path, 32, 32, [28, 29, 29, 30, 31])
    _write_padded_unit_sheet(reaver_path, 84, 84, [82, 84, 84, 84, 84])
    _write_padded_unit_sheet(wraith_path, 64, 64, [62, 64, 64, 64, 64])

    records = [
        {
            "id": "Firebat",
            "kind": "unit",
            "race": "terran",
            "mpq_path": "unit\\terran\\firebat.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(firebat_path),
                "stdout": "wrote Firebat.png from firebat.grp frames=5 frame_size=32x32",
            },
        },
        {
            "id": "Reaver",
            "kind": "unit",
            "race": "protoss",
            "mpq_path": "unit\\protoss\\trilob.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(reaver_path),
                "stdout": "wrote Reaver.png from trilob.grp frames=5 frame_size=84x84",
            },
        },
        {
            "id": "Wraith",
            "kind": "unit",
            "race": "terran",
            "mpq_path": "unit\\terran\\phoenix.grp",
            "source_mpq": "StarDat.mpq",
            "status": "extracted",
            "conversion": {
                "status": "converted",
                "png_path": str(wraith_path),
                "stdout": "wrote Wraith.png from phoenix.grp frames=5 frame_size=64x64",
            },
        },
    ]
    input_manifest = {
        "assets": [
            {"id": "Firebat", "visual_class": "small_ground"},
            {"id": "Reaver", "visual_class": "large_ground"},
            {"id": "Wraith", "visual_class": "small_air"},
        ]
    }

    generated = build_generated_manifest(
        records,
        Path("/repo/godot/assets/sc1_generated/p1a_core_units"),
        batch="p1a_core_units",
        input_manifest=input_manifest,
    )

    firebat = generated["assets"]["Firebat"]
    reaver = generated["assets"]["Reaver"]
    wraith = generated["assets"]["Wraith"]

    assert firebat["content_extent"] == 29
    assert reaver["content_extent"] == 84
    assert wraith["content_extent"] == 64
    assert firebat["scale_basis"] == "content_median_extent"
    assert reaver["scale_basis"] == "content_median_extent"
    assert wraith["scale_basis"] == "content_median_extent"
    assert 0.68 <= firebat["content_extent"] * firebat["render_scale"] <= 0.72
    assert 1.52 <= reaver["content_extent"] * reaver["render_scale"] <= 1.58
    assert 1.03 <= wraith["content_extent"] * wraith["render_scale"] <= 1.07
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
pytest tests/godot/test_sc1_generated_manifest.py::test_generated_manifest_scales_units_from_visual_class -q
```

Expected before implementation:

```text
FAILED
```

The failure should show missing `content_extent`, missing `render_scale`, or missing `scale_basis` for the P1A units.

- [ ] **Step 3: Add visual-class scale config loading**

In `scripts/sc1_extract_manifest.py`, add:

```python
DEFAULT_SCALE_CONFIG = REPO_ROOT / "tools" / "sc1_assets" / "visual_class_scale_config.json"
```

Add this helper:

```python
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
```

- [ ] **Step 4: Pass visual_class into `_visual_overrides`**

Change `_visual_overrides` signature:

```python
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
```

In `build_generated_manifest`, compute targets once:

```python
visual_class_targets = _load_visual_class_targets()
```

Pass both `vc` and `visual_class_targets` into `_visual_overrides`.

- [ ] **Step 5: Implement unit target fallback**

Inside the `kind == "unit"` branch, replace:

```python
target_max = VISUAL_UNIT_TARGET_BODY_WORLD.get(asset_id)
```

with:

```python
targets = visual_class_targets or {}
target_max = VISUAL_UNIT_TARGET_BODY_WORLD.get(asset_id)
if target_max is None and visual_class:
    target_max = targets.get(visual_class)
```

Keep `VISUAL_UNIT_TARGET_BODY_WORLD` as an explicit per-asset override for existing hand-tuned P0 units.

- [ ] **Step 6: Keep content extent measurement for all scaled units**

Ensure the successful branch still emits:

```python
overrides["content_extent"] = content_extent
overrides["scale_basis"] = "content_median_extent"
```

Do not emit `scale_basis: "content_extent"` for extracted units; the pipeline should use measured median alpha content.

- [ ] **Step 7: Re-run the failing test**

Run:

```bash
pytest tests/godot/test_sc1_generated_manifest.py::test_generated_manifest_scales_units_from_visual_class -q
```

Expected:

```text
1 passed
```

- [ ] **Step 8: Run broader Python checks**

Run:

```bash
pytest tests/godot/test_sc1_generated_manifest.py tests/godot/test_visual_class_scale.py -q
ruff check scripts/sc1_extract_manifest.py tests/godot/test_sc1_generated_manifest.py
python3 -m py_compile scripts/sc1_extract_manifest.py
```

Expected: all pass.

- [ ] **Step 9: Commit**

Run:

```bash
git add scripts/sc1_extract_manifest.py tests/godot/test_sc1_generated_manifest.py
git commit -m "fix(assets): scale generated units from visual_class"
```

---

## Task 2: Make Batch Extraction Update The Aggregate Manifest

**Files:**
- Modify: `scripts/sc1_extract_manifest.py`
- Modify: `tests/godot/test_sc1_p1a_manifest.py`

- [ ] **Step 1: Add an aggregate-path regression test**

Append to `tests/godot/test_sc1_p1a_manifest.py`:

```python
def test_p1a_generated_manifest_path_is_top_level_contract() -> None:
    generated = json.loads(GENERATED_MANIFEST.read_text())
    assert "assets" in generated
    assert generated["assets"]["Firebat"]["asset"] == (
        "res://assets/sc1_generated/p1a_core_units/Firebat.png"
    )
```

This test documents the intended contract: batch PNGs live under a batch subdir, but the manifest consumed by `SpriteLoader` is still the top-level aggregate file.

- [ ] **Step 2: Fix `--batch-out` generated-manifest path**

In `scripts/sc1_extract_manifest.py`, keep batch-specific `raw_out` and `png_out`, but set `generated_manifest_path` to the top-level output:

```python
if args.batch_out:
    raw_out = REPO_ROOT / "local_assets" / "sc1_mpq_raw" / batch
    png_out = REPO_ROOT / "local_assets" / "sc1_converted" / batch
    generated_manifest_path = args.generated_manifest
else:
    raw_out = args.raw_out
    png_out = args.png_out
    generated_manifest_path = args.generated_manifest
```

Do not write `godot/assets/sc1_generated/<batch>/generated_manifest.json` as the primary output.

- [ ] **Step 3: Regenerate P0 then P1A from MPQs**

Run:

```bash
python3 scripts/sc1_extract_manifest.py \
  --manifest tools/sc1_assets/p0_resource_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --convert
```

Then:

```bash
python3 scripts/sc1_extract_manifest.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --convert --batch-out
```

Expected:

```text
P0 merged_total=20
P1A total=12 extracted=12 converted=12 skipped=0 merged_total=32
```

- [ ] **Step 4: Verify aggregate manifest fields**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("godot/assets/sc1_generated/generated_manifest.json").read_text())
expected = {
    "Firebat", "Ghost", "Vulture", "Tank", "Goliath", "Wraith",
    "Hydralisk", "Overlord", "Mutalisk", "Dragoon", "Reaver", "Carrier",
}
assert len(manifest["assets"]) == 32
assert expected <= set(manifest["assets"])
for asset_id in sorted(expected):
    entry = manifest["assets"][asset_id]
    assert entry["batch"] == "p1a_core_units", asset_id
    assert entry["asset"] == f"res://assets/sc1_generated/p1a_core_units/{asset_id}.png"
    assert "visual_class" in entry, asset_id
    assert "content_extent" in entry, asset_id
    assert "render_scale" in entry, asset_id
    assert entry["scale_basis"] == "content_median_extent", asset_id
print("aggregate p1a manifest ok")
PY
```

Expected:

```text
aggregate p1a manifest ok
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/godot/test_sc1_generated_manifest.py tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py tests/godot/test_presentation_manifest.py -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_p1a_sprite_loader.gd
```

Expected: all pass.

- [ ] **Step 6: Commit aggregate manifest fix**

Run:

```bash
git add scripts/sc1_extract_manifest.py tests/godot/test_sc1_p1a_manifest.py godot/assets/sc1_generated/generated_manifest.json
git commit -m "fix(assets): regenerate aggregate manifest from batch extraction"
```

---

## Task 3: Commit P1A Path Resolution Cleanly

**Files:**
- Modify: `tools/sc1_assets/p1a_resource_manifest.json`
- Modify: `docs/plans/2026-06-11-sc1-resource-extraction-validation-sop.md`

- [ ] **Step 1: Format P1A manifest with newline**

Ensure `tools/sc1_assets/p1a_resource_manifest.json` is pretty-printed JSON and ends with a newline.

Required resolved entries:

```json
{
  "id": "Wraith",
  "mpq_path": "unit\\terran\\phoenix.grp",
  "mpq_source": "StarDat.mpq"
}
```

```json
{
  "id": "Reaver",
  "mpq_path": "unit\\protoss\\trilob.grp",
  "mpq_source": "StarDat.mpq"
}
```

- [ ] **Step 2: Document the resolved SC1 aliases**

In `docs/plans/2026-06-11-sc1-resource-extraction-validation-sop.md`, add:

```text
P1A resolved aliases:
- Wraith uses unit\terran\phoenix.grp in StarDat.mpq.
- Reaver uses unit\protoss\trilob.grp in StarDat.mpq.
```

- [ ] **Step 3: Run discovery and manifest tests**

Run:

```bash
python3 scripts/sc1_discover_assets.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --out /private/tmp/p1a_asset_candidates_verify.json
pytest tests/godot/test_sc1_p1a_manifest.py -q
```

Expected:

```text
total=12 found=12 missing=0 pending=0
```

and all tests pass.

- [ ] **Step 4: Commit**

Run:

```bash
git add tools/sc1_assets/p1a_resource_manifest.json docs/plans/2026-06-11-sc1-resource-extraction-validation-sop.md
git commit -m "data(assets): resolve p1a wraith and reaver mpq paths"
```

---

## Task 4: P1B Discovery Manifest For Tech Buildings

**Files:**
- Create: `tools/sc1_assets/p1b_building_manifest.json`
- Modify: `scripts/sc1_discover_assets.py`
- Create: `tests/godot/test_sc1_p1b_manifest.py`

- [ ] **Step 1: Extend discovery to support `candidate_names`**

In `scripts/sc1_discover_assets.py`, when `mpq_path == "PENDING"`, use this candidate list:

```python
candidate_names = cand.get("candidate_names", [])
if not candidate_names:
    candidate_names = ABBREVIATION_MAP.get(asset_id, [])
```

For each candidate, probe:

```python
candidate = f"unit\\{race_dir}\\{candidate_name}.grp"
```

Keep exact-path behavior unchanged for non-PENDING assets.

- [ ] **Step 2: Create the P1B manifest**

Create `tools/sc1_assets/p1b_building_manifest.json`:

```json
{
  "schema_version": 2,
  "scope": "p1b_tech_buildings",
  "batch": "p1b_tech_buildings",
  "mpq_priority_high_to_low": [
    "Patch_rt.mpq",
    "BrooDat.mpq",
    "StarDat.mpq"
  ],
  "palette": "tools/mpq/PyMS/Palettes/Units.pal",
  "assets": [
    {
      "id": "SupplyDepot",
      "kind": "building",
      "race": "terran",
      "visual_class": "small_building",
      "mpq_path": "PENDING",
      "candidate_names": ["supply", "supdepot", "tsupply"],
      "godot_asset": "res://assets/sprites/buildings/TerranBuilding.png"
    },
    {
      "id": "Factory",
      "kind": "building",
      "race": "terran",
      "visual_class": "medium_building",
      "mpq_path": "PENDING",
      "candidate_names": ["factory", "tfactory"],
      "godot_asset": "res://assets/sprites/buildings/TerranBuilding.png"
    },
    {
      "id": "Starport",
      "kind": "building",
      "race": "terran",
      "visual_class": "medium_building",
      "mpq_path": "PENDING",
      "candidate_names": ["starport", "tstarport"],
      "godot_asset": "res://assets/sprites/buildings/TerranBuilding.png"
    },
    {
      "id": "Bunker",
      "kind": "building",
      "race": "terran",
      "visual_class": "small_building",
      "mpq_path": "PENDING",
      "candidate_names": ["bunker", "tbunker"],
      "godot_asset": "res://assets/sprites/buildings/TerranBuilding.png"
    },
    {
      "id": "HydraliskDen",
      "kind": "building",
      "race": "zerg",
      "visual_class": "medium_building",
      "mpq_path": "PENDING",
      "candidate_names": ["hydraliskden", "hydraden", "den"],
      "godot_asset": "res://assets/sprites/buildings/ZergBuilding.png"
    },
    {
      "id": "Spire",
      "kind": "building",
      "race": "zerg",
      "visual_class": "medium_building",
      "mpq_path": "PENDING",
      "candidate_names": ["spire", "zspire"],
      "godot_asset": "res://assets/sprites/buildings/ZergBuilding.png"
    },
    {
      "id": "SunkenColony",
      "kind": "building",
      "race": "zerg",
      "visual_class": "small_building",
      "mpq_path": "PENDING",
      "candidate_names": ["sunken", "sunkcol", "colony"],
      "godot_asset": "res://assets/sprites/buildings/ZergBuilding.png"
    },
    {
      "id": "PhotonCannon",
      "kind": "building",
      "race": "protoss",
      "visual_class": "small_building",
      "mpq_path": "PENDING",
      "candidate_names": ["cannon", "pcannon", "photonc"],
      "godot_asset": "res://assets/sprites/buildings/ProtossBuilding.png"
    },
    {
      "id": "CyberneticsCore",
      "kind": "building",
      "race": "protoss",
      "visual_class": "medium_building",
      "mpq_path": "PENDING",
      "candidate_names": ["cyber", "cybcore", "core"],
      "godot_asset": "res://assets/sprites/buildings/ProtossBuilding.png"
    },
    {
      "id": "Stargate",
      "kind": "building",
      "race": "protoss",
      "visual_class": "medium_building",
      "mpq_path": "PENDING",
      "candidate_names": ["stargate", "pstarg"],
      "godot_asset": "res://assets/sprites/buildings/ProtossBuilding.png"
    },
    {
      "id": "RoboticsFacility",
      "kind": "building",
      "race": "protoss",
      "visual_class": "medium_building",
      "mpq_path": "PENDING",
      "candidate_names": ["robotics", "robotfac", "robofac"],
      "godot_asset": "res://assets/sprites/buildings/ProtossBuilding.png"
    }
  ]
}
```

- [ ] **Step 3: Add P1B schema tests**

Create `tests/godot/test_sc1_p1b_manifest.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
P1B_MANIFEST = REPO_ROOT / "tools" / "sc1_assets" / "p1b_building_manifest.json"


def test_p1b_manifest_schema() -> None:
    manifest = json.loads(P1B_MANIFEST.read_text())
    assert manifest["schema_version"] == 2
    assert manifest["batch"] == "p1b_tech_buildings"
    assert len(manifest["assets"]) == 11


def test_p1b_assets_have_discovery_candidates() -> None:
    manifest = json.loads(P1B_MANIFEST.read_text())
    for asset in manifest["assets"]:
        assert asset["kind"] == "building"
        assert asset["mpq_path"] == "PENDING"
        assert asset["candidate_names"], f"{asset['id']}: missing candidate_names"
        assert asset["visual_class"] in {"small_building", "medium_building", "large_building"}
```

- [ ] **Step 4: Run discovery**

Run:

```bash
python3 scripts/sc1_discover_assets.py \
  --manifest tools/sc1_assets/p1b_building_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --out local_assets/sc1_discovery/p1b_building_candidates.json
```

Expected: a report is written. It is acceptable for this task to leave some assets pending; do not guess unresolved paths.

- [ ] **Step 5: Commit discovery scaffolding**

Run:

```bash
pytest tests/godot/test_sc1_p1b_manifest.py -q
ruff check scripts/sc1_discover_assets.py tests/godot/test_sc1_p1b_manifest.py
python3 -m py_compile scripts/sc1_discover_assets.py
git add tools/sc1_assets/p1b_building_manifest.json scripts/sc1_discover_assets.py tests/godot/test_sc1_p1b_manifest.py
git commit -m "feat(assets): add p1b building discovery manifest"
```

---

## Task 5: Final Gate Before P1B Extraction

Run:

```bash
git status --short
pytest tests/godot/test_sc1_generated_manifest.py tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py tests/godot/test_presentation_manifest.py -q
ruff check scripts/sc1_extract_manifest.py scripts/sc1_discover_assets.py tests/godot/test_sc1_generated_manifest.py tests/godot/test_sc1_p1a_manifest.py tests/godot/test_visual_class_scale.py
python3 -m py_compile scripts/sc1_extract_manifest.py scripts/sc1_discover_assets.py scripts/sc1_grp_to_png.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sprite_loader_generated.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_p1a_sprite_loader.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_game_view_probe_override.gd
```

Pass criteria:

```text
No Python or Godot test failures.
P1A discovery reports 12 found, 0 missing, 0 pending.
Re-running extraction into a temporary manifest produces render_scale/content_extent for all 12 P1A units.
Top-level generated manifest has exactly 32 assets before P1B extraction.
No generated PNG/GRP files or .godot import cache files are staged.
```
