# SC1 MPQ to Godot Resource Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract assets from the local StarCraft Windows installation MPQ files, build a verifiable asset inventory, convert the necessary SC1 resources into Godot-consumable local research assets, and compare them against the current Godot presentation manifest.

**Architecture:** This is a local research asset pipeline. Proprietary extracted assets must stay in ignored local folders unless the user explicitly confirms a private distribution policy. Source-controlled changes should be scripts, manifests, checksums, reports, and Godot integration code, not raw MPQ contents.

**Tech Stack:** Git branch safety, StormLib for MPQ extraction, PyMS or converter scripts for SC1 formats, Python 3.11, Pillow, optional ffmpeg, Godot 4.x, existing `presentation_manifest.json`, pytest validators.

---

## Status Before Execution

- Current branch created: `codex-sc1-mpq-resource-sync`
- Protection commit created: `6a7c9c5 chore: snapshot before sc1 asset sync`
- Local StarCraft path confirmed: `/Users/yuyou/code/StarCraft`
- MPQ files confirmed:
  - `/Users/yuyou/code/StarCraft/StarDat.mpq`
  - `/Users/yuyou/code/StarCraft/BrooDat.mpq`
  - `/Users/yuyou/code/StarCraft/Patch_rt.mpq`
- Current dirty files after protection commit are generated/runtime artifacts only:
  - `godot/.godot/*`
  - `harness/output/*`
  - `harness/skills/candidates/*`

## Legal and Repository Boundary

This project can use the local StarCraft install as a research input, but the repo should not automatically commit extracted proprietary resources.

Default policy:

- Extract raw MPQ contents into ignored local path: `local_assets/sc1_mpq_raw/`
- Write converted Godot-ready local assets into ignored local path: `godot/assets/sc1_extracted/`
- Commit only:
  - extraction scripts,
  - conversion scripts,
  - generated inventories with hashes and relative paths,
  - comparison reports,
  - manifest generator code,
  - Godot loader support for local asset profiles.

If the user explicitly wants a private branch containing extracted assets, create a separate commit after confirming scope and repository visibility.

## Open-Source Tool Selection

### Primary MPQ Extractor: StormLib

Use StormLib as the primary MPQ reader/extractor.

- Repository: `https://github.com/ladislav-zezula/StormLib`
- Reason: maintained C/C++ library focused on Blizzard MPQ archive reading/writing.
- Build approach: clone or download into ignored `tools/mpq/StormLib`, build with CMake, use a small local CLI wrapper if the repo build does not expose a convenient extractor binary.

### Format Conversion Reference: PyMS

Use PyMS as reference or tooling for SC1-specific formats.

- Repository: `https://github.com/poiuyqwert/PyMS`
- Relevant formats: GRP, PCX, PAL, TBL, DAT, MPQ helpers.
- Reason: SC1 sprites are not directly PNG; unit/building assets are commonly GRP plus palettes and metadata.

### Semantic Reference: OpenBW and BWAPI

Use these for file naming conventions, unit/building semantics, and SC1/BW research mapping.

- OpenBW: `https://github.com/OpenBW/openbw`
- BWAPI: `https://github.com/bwapi/bwapi`

These are not the extraction tool. They help validate that extracted resource paths and entity categories align with Brood War conventions.

## MPQ Priority Model

Use patch priority order:

```text
Patch_rt.mpq > BrooDat.mpq > StarDat.mpq
```

When the same archive path exists in multiple MPQs, the higher-priority MPQ wins. The final virtual file table should record all sources and the selected winner:

```json
{
  "archive_path": "unit/terran/marine.grp",
  "sources": [
    {"mpq": "StarDat.mpq", "sha256": "..."},
    {"mpq": "Patch_rt.mpq", "sha256": "..."}
  ],
  "selected_mpq": "Patch_rt.mpq",
  "selected_reason": "highest_priority"
}
```

---

## Resource Coverage Categories

The pipeline must classify resources into these categories:

| Category | Examples | Godot Target |
|---|---|---|
| Units | SCV, Marine, Zealot, Zergling | `unit_visuals` and generated sprite sheets |
| Buildings | CommandCenter, Hatchery, Nexus | `building_visuals` and generated sprite sheets |
| Projectiles | Gauss rifle, spores, missiles | VFX catalog and attack profiles |
| Spells/VFX | Psionic Storm, explosions, death effects | `vfx_catalog.json`, spell profiles |
| UI Icons | Command buttons, wireframes, portraits | HUD resources |
| Tilesets | Badlands, Space, Jungle, Ashworld | map/terrain research profile |
| Audio | selection, command, attack, death sounds | local Godot audio resources |
| Data Tables | units.dat, weapons.dat, upgrades.dat, stat_txt.tbl | `data/*` comparison reports |
| Maps | `.scm`, `.scx` | future map import pipeline |

---

## Resource Comparison Strategy

### 1. Source Inventory

Generate `docs/reports/sc1_mpq_inventory.json` with:

```json
{
  "archive_path": "unit/terran/marine.grp",
  "selected_mpq": "Patch_rt.mpq",
  "size": 12345,
  "sha256": "hex",
  "extension": ".grp",
  "category": "unit",
  "extracted_path": "local_assets/sc1_mpq_raw/unit/terran/marine.grp"
}
```

### 2. Conversion Inventory

Generate `docs/reports/sc1_converted_inventory.json` with:

```json
{
  "source_archive_path": "unit/terran/marine.grp",
  "converted_path": "godot/assets/sc1_extracted/units/terran/marine.png",
  "format": "png",
  "width": 640,
  "height": 480,
  "frame_count": 17,
  "palette": "unit/tunit.pal",
  "sha256": "hex"
}
```

### 3. Godot Inventory

Generate `docs/reports/godot_asset_inventory.json` by scanning:

- `godot/resources/presentation_manifest.json`
- `godot/resources/sprite_frames_config.json`
- `godot/resources/vfx/vfx_catalog.json`
- `godot/assets/**`

Each entry should include:

```json
{
  "visual_id": "Marine",
  "manifest_section": "unit_visuals",
  "source_path": "res://assets/sc1_extracted/units/terran/marine.png",
  "atlas_rect": [0, 0, 64, 64],
  "render_scale": 0.01,
  "selection_radius": 0.68,
  "exists": true,
  "sha256": "hex"
}
```

### 4. Mapping Matrix

Generate `docs/reports/sc1_godot_resource_comparison.md` with a table:

| SC1 ID | Category | MPQ Path | Converted Asset | Godot Visual ID | Manifest Status | Pixel/Frame Status | Action |
|---|---|---|---|---|---|---|---|
| Marine | unit | `unit/terran/marine.grp` | `marine.png` | `Marine` | covered | frame-count match | keep |
| CommandCenter | building | archive path | generated png | `CommandCenter` | covered | needs pivot check | adjust manifest |
| Medic | unit | archive path | generated png | missing | missing | not mapped | add manifest |

### 5. Comparison Verdicts

Use these labels:

| Label | Meaning |
|---|---|
| `exact-source` | Godot asset was generated from local MPQ source and manifest points to it. |
| `converted-source` | Asset was converted from MPQ but repacked/rescaled. |
| `current-custom` | Existing project custom asset, not from MPQ. |
| `placeholder` | Existing fallback art, not validated against SC1. |
| `missing-extraction` | Expected SC1 resource not extracted. |
| `missing-godot` | Extracted/converted resource exists but Godot does not map it. |
| `needs-manifest-tuning` | Asset exists, but pivot/scale/radius/atlas rect needs adjustment. |

### 6. Visual QA

Generate contact sheets:

- `docs/reports/sc1_units_contact_sheet.png`
- `docs/reports/sc1_buildings_contact_sheet.png`
- `docs/reports/sc1_effects_contact_sheet.png`

Each contact sheet should show:

- SC1 ID,
- current Godot render,
- extracted/converted render,
- bounding box,
- pivot point,
- selection radius overlay.

---

## File Structure

Create:

- `tools/mpq/`  
  Ignored local tool checkout/build area.

- `local_assets/sc1_mpq_raw/`  
  Ignored extracted raw MPQ files.

- `godot/assets/sc1_extracted/`  
  Ignored local Godot-ready converted assets.

- `scripts/sc1_extract_mpq.py`  
  Builds/uses StormLib extractor, extracts MPQ contents to `local_assets/sc1_mpq_raw/`.

- `scripts/sc1_asset_inventory.py`  
  Creates source inventory JSON from extracted MPQ files.

- `scripts/sc1_convert_assets.py`  
  Converts selected PCX/GRP/WAV/TBL/DAT resources into local Godot-friendly outputs and intermediate JSON.

- `scripts/sc1_compare_godot_assets.py`  
  Compares extracted/converted resources with Godot manifests and generates Markdown/JSON reports.

- `scripts/sc1_generate_godot_manifest.py`  
  Generates `godot/resources/presentation_manifest.sc1.generated.json`.

- `tests/assets/test_sc1_asset_inventory.py`  
  Validates inventory shape, MPQ priority, hash fields, and category labels.

- `tests/assets/test_sc1_godot_asset_comparison.py`  
  Validates comparison report can detect covered/missing/placeholder assets.

- `docs/reports/sc1_mpq_inventory.json`  
  Generated source inventory.

- `docs/reports/sc1_converted_inventory.json`  
  Generated conversion inventory.

- `docs/reports/godot_asset_inventory.json`  
  Generated Godot asset inventory.

- `docs/reports/sc1_godot_resource_comparison.md`  
  Human-readable comparison report.

Modify:

- `.gitignore`  
  Ensure extracted proprietary assets and tool builds are ignored.

- `godot/resources/presentation_manifest.json` or a generated SC1 overlay manifest  
  Only after comparison report identifies safe updates.

- `godot/scripts/sprite_loader.gd`  
  Only if loader needs support for generated local asset profile.

---

## Task 1: Git Safety Gate

**Files:**
- Modify: `.gitignore`

- [x] **Step 1: Create isolated branch**

Run:

```bash
git switch -c codex-sc1-mpq-resource-sync
```

Expected:

```text
Switched to a new branch 'codex-sc1-mpq-resource-sync'
```

- [x] **Step 2: Add ignore rules for local extraction**

Ensure `.gitignore` includes:

```gitignore
node_modules/
platform/dashboard/node_modules/
platform/dashboard/dist/
local_assets/
extracted_assets/
tools/mpq/
StarCraft/**/*.mpq.extracted/
godot/assets/sc1_extracted/
godot/assets/sc1_generated/
```

- [x] **Step 3: Commit current source snapshot**

Run:

```bash
git commit -m "chore: snapshot before sc1 asset sync"
```

Expected:

```text
[codex-sc1-mpq-resource-sync 6a7c9c5] chore: snapshot before sc1 asset sync
```

- [ ] **Step 4: Add missing Godot asset ignore rules**

Patch `.gitignore` with:

```gitignore
godot/assets/sc1_extracted/
godot/assets/sc1_generated/
```

- [ ] **Step 5: Commit the extraction safety ignore update**

Run:

```bash
git add .gitignore
git commit -m "chore: ignore local sc1 extracted assets"
```

Expected:

```text
1 file changed
```

---

## Task 2: Install and Build MPQ Extractor

**Files:**
- Create: `tools/mpq/StormLib/` ignored
- Create: `tools/mpq/bin/` ignored

- [ ] **Step 1: Download StormLib**

Run:

```bash
mkdir -p tools/mpq
curl -L https://github.com/ladislav-zezula/StormLib/archive/refs/heads/master.zip -o /tmp/StormLib.zip
unzip -q /tmp/StormLib.zip -d tools/mpq
mv tools/mpq/StormLib-master tools/mpq/StormLib
```

Expected:

```text
tools/mpq/StormLib/CMakeLists.txt exists
```

- [ ] **Step 2: Build StormLib**

Run:

```bash
cmake -S tools/mpq/StormLib -B tools/mpq/StormLib/build -DCMAKE_BUILD_TYPE=Release
cmake --build tools/mpq/StormLib/build --config Release -j 4
```

Expected:

```text
StormLib library built under tools/mpq/StormLib/build
```

- [ ] **Step 3: Add local extractor wrapper**

If StormLib build does not produce a simple extractor CLI, create `tools/mpq/storm_extract.cpp` locally and compile it against the built library. The wrapper must support:

```bash
tools/mpq/bin/storm_extract list /Users/yuyou/code/StarCraft/StarDat.mpq
tools/mpq/bin/storm_extract extract /Users/yuyou/code/StarCraft/StarDat.mpq local_assets/sc1_mpq_raw/StarDat
```

Expected:

```text
list command prints archive paths
extract command writes files to output dir
```

Do not commit `tools/mpq/*`.

---

## Task 3: Build MPQ Extraction Script

**Files:**
- Create: `scripts/sc1_extract_mpq.py`
- Test: `tests/assets/test_sc1_asset_inventory.py`

- [ ] **Step 1: Write inventory test for MPQ priority**

Create `tests/assets/test_sc1_asset_inventory.py` with tests that assert:

```python
def test_mpq_priority_order() -> None:
    from scripts.sc1_asset_inventory import MPQ_PRIORITY
    assert MPQ_PRIORITY == ["StarDat.mpq", "BrooDat.mpq", "Patch_rt.mpq"]
    assert list(reversed(MPQ_PRIORITY))[0] == "Patch_rt.mpq"
```

- [ ] **Step 2: Implement extractor script**

`scripts/sc1_extract_mpq.py` must:

- accept `--starcraft-dir /Users/yuyou/code/StarCraft`,
- accept `--out local_assets/sc1_mpq_raw`,
- extract `StarDat.mpq`, `BrooDat.mpq`, and `Patch_rt.mpq`,
- preserve archive paths,
- record extraction log to `docs/reports/sc1_mpq_extraction_log.json`.

Run:

```bash
python3 scripts/sc1_extract_mpq.py --starcraft-dir /Users/yuyou/code/StarCraft --out local_assets/sc1_mpq_raw
```

Expected:

```text
extracted StarDat.mpq
extracted BrooDat.mpq
extracted Patch_rt.mpq
```

- [ ] **Step 3: Handle missing listfile**

If an MPQ does not contain a complete `(listfile)`, use a known-path list seeded from:

- PyMS format/file references,
- OpenBW/BWAPI resource path expectations,
- existing Godot SC1 manifest visual IDs.

The script must output:

```json
{
  "archive": "StarDat.mpq",
  "listfile_mode": "mpq_internal|known_paths|mixed",
  "extracted_count": 0,
  "missing_known_paths": []
}
```

---

## Task 4: Build Asset Inventory

**Files:**
- Create: `scripts/sc1_asset_inventory.py`
- Create: `docs/reports/sc1_mpq_inventory.json`

- [ ] **Step 1: Implement inventory generator**

The script must scan `local_assets/sc1_mpq_raw/` and emit:

```bash
python3 scripts/sc1_asset_inventory.py --raw local_assets/sc1_mpq_raw --out docs/reports/sc1_mpq_inventory.json
```

Expected JSON top-level keys:

```json
{
  "generated_at": "ISO-8601",
  "mpq_priority": ["StarDat.mpq", "BrooDat.mpq", "Patch_rt.mpq"],
  "items": []
}
```

- [ ] **Step 2: Categorize files**

Category rules:

```text
*.grp -> unit/building/effect sprite candidate
*.pcx -> UI/portrait/tileset image candidate
*.pal -> palette
*.tbl -> string table
*.dat -> gameplay data table
*.wav -> audio
*.smk -> video/cinematic, not needed for Godot RTS prototype
*.scm, *.scx -> map
```

- [ ] **Step 3: Run tests**

Run:

```bash
python3 -m pytest tests/assets/test_sc1_asset_inventory.py -q
```

Expected:

```text
passed
```

---

## Task 5: Convert SC1 Assets for Godot

**Files:**
- Create: `scripts/sc1_convert_assets.py`
- Create: `docs/reports/sc1_converted_inventory.json`
- Local ignored output: `godot/assets/sc1_extracted/`

- [ ] **Step 1: Convert easy image formats first**

Convert `.pcx` with Pillow:

```bash
python3 scripts/sc1_convert_assets.py --inventory docs/reports/sc1_mpq_inventory.json --kind pcx --out godot/assets/sc1_extracted
```

Expected:

```text
converted PCX files to PNG
```

- [ ] **Step 2: Convert audio**

Copy `.wav` files into:

```text
godot/assets/sc1_extracted/audio/
```

If compression is required later, convert to `.ogg` in a separate step.

- [ ] **Step 3: Convert GRP sprites**

Use PyMS or a small converter to combine:

- `.grp` sprite frames,
- required palette,
- frame metadata,
- optional shadow/overlay resources.

Output:

```text
godot/assets/sc1_extracted/units/<race>/<unit>.png
godot/assets/sc1_extracted/buildings/<race>/<building>.png
godot/assets/sc1_extracted/effects/<effect>.png
```

The converter must record:

```json
{
  "source_archive_path": "unit/terran/marine.grp",
  "converted_path": "godot/assets/sc1_extracted/units/terran/marine.png",
  "frame_count": 17,
  "frame_width": 64,
  "frame_height": 64,
  "palette": "..."
}
```

- [ ] **Step 4: Generate contact sheets**

Run:

```bash
python3 scripts/sc1_convert_assets.py --inventory docs/reports/sc1_mpq_inventory.json --contact-sheets docs/reports
```

Expected files:

```text
docs/reports/sc1_units_contact_sheet.png
docs/reports/sc1_buildings_contact_sheet.png
docs/reports/sc1_effects_contact_sheet.png
```

---

## Task 6: Compare Against Current Godot Resources

**Files:**
- Create: `scripts/sc1_compare_godot_assets.py`
- Create: `docs/reports/godot_asset_inventory.json`
- Create: `docs/reports/sc1_godot_resource_comparison.md`
- Test: `tests/assets/test_sc1_godot_asset_comparison.py`

- [ ] **Step 1: Write comparison test**

Create `tests/assets/test_sc1_godot_asset_comparison.py`:

```python
from __future__ import annotations

from scripts.sc1_compare_godot_assets import verdict_for_asset


def test_verdict_missing_godot_mapping() -> None:
    assert verdict_for_asset(extracted=True, godot_mapped=False, placeholder=False) == "missing-godot"


def test_verdict_placeholder() -> None:
    assert verdict_for_asset(extracted=False, godot_mapped=True, placeholder=True) == "placeholder"


def test_verdict_exact_source() -> None:
    assert verdict_for_asset(extracted=True, godot_mapped=True, placeholder=False) == "exact-source"
```

- [ ] **Step 2: Implement Godot inventory scanner**

The scanner must read:

- `godot/resources/presentation_manifest.json`
- `godot/resources/sprite_frames_config.json`
- `godot/resources/vfx/vfx_catalog.json`

and emit:

```bash
python3 scripts/sc1_compare_godot_assets.py --converted docs/reports/sc1_converted_inventory.json --godot godot/resources/presentation_manifest.json --out docs/reports/sc1_godot_resource_comparison.md
```

- [ ] **Step 3: Compare all core categories**

The report must contain sections:

```text
Units
Buildings
Effects
UI Icons
Audio
Data Tables
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m pytest tests/assets/test_sc1_godot_asset_comparison.py -q
```

Expected:

```text
passed
```

---

## Task 7: Generate Godot Manifest Overlay

**Files:**
- Create: `scripts/sc1_generate_godot_manifest.py`
- Create: `godot/resources/presentation_manifest.sc1.generated.json`
- Modify only if needed: `godot/scripts/sprite_loader.gd`

- [ ] **Step 1: Generate overlay manifest**

Run:

```bash
python3 scripts/sc1_generate_godot_manifest.py --comparison docs/reports/sc1_godot_resource_comparison.md --converted docs/reports/sc1_converted_inventory.json --out godot/resources/presentation_manifest.sc1.generated.json
```

Expected:

```json
{
  "profile": "sc1_extracted_local",
  "asset_root": "res://assets/sc1_extracted",
  "unit_visuals": {},
  "building_visuals": {},
  "spell_visuals": {}
}
```

- [ ] **Step 2: Keep existing manifest as fallback**

Do not delete existing current custom mappings. The Godot loader should resolve in this order:

```text
presentation_manifest.sc1.generated.json if present
presentation_manifest.json fallback
hardcoded fallback only as last resort
```

- [ ] **Step 3: Validate manifest**

Run:

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/test_presentation_manifest.py tests/godot/test_verify_presentation_scene.py -q
```

Expected:

```text
OK — manifest structure valid
```

---

## Task 8: Godot Runtime Validation

**Files:**
- Existing: `godot/scripts/game_view.gd`
- Existing: `godot/scripts/sprite_loader.gd`
- Existing: `godot/resources/presentation_manifest*.json`

- [ ] **Step 1: Start backend**

Run:

```bash
python3 -m simcore.grpc_server --port 50051
python3 -m simcore.http_gateway --grpc-port 50051 --http-port 8080
```

Expected:

```text
gRPC server listening on 50051
HTTP gateway listening on 8080
```

- [ ] **Step 2: Start Godot**

Run:

```bash
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```

- [ ] **Step 3: Manual visual checks**

Check:

- Terran: CommandCenter, SCV, Marine, Barracks, Refinery.
- Zerg: Hatchery, Drone, Zergling, SpawningPool, Extractor.
- Protoss: Nexus, Probe, Zealot, Gateway, Pylon.
- Resources: minerals and gas.
- Effects: attack, death, building construction.
- UI: selection circle, health bar, minimap, HUD train/build buttons.

- [ ] **Step 4: Record screenshots**

Save local screenshots to ignored:

```text
local_assets/sc1_visual_qa/
```

Generate report:

```text
docs/reports/sc1_visual_qa_report.md
```

---

## Task 9: Final Gate

**Files:**
- Create/Update: `docs/reports/sc1_godot_resource_comparison.md`
- Create/Update: `docs/reports/sc1_visual_qa_report.md`

- [ ] **Step 1: Run static gates**

```bash
python3 scripts/sc1_asset_inventory.py --raw local_assets/sc1_mpq_raw --out docs/reports/sc1_mpq_inventory.json
python3 scripts/sc1_compare_godot_assets.py --converted docs/reports/sc1_converted_inventory.json --godot godot/resources/presentation_manifest.json --out docs/reports/sc1_godot_resource_comparison.md
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/assets tests/godot -q
```

- [ ] **Step 2: Run architecture gate**

```bash
python3 scripts/lint_deps.py simcore/ agents/ runtime/ proto/
```

Known current blocker before this plan:

```text
simcore/http_gateway.py:76 from agents.script_ai (L2) in L1 — forbidden
```

If still failing, report as existing architecture blocker, not an asset pipeline blocker.

- [ ] **Step 3: Commit scripts and reports only**

Allowed commit targets:

```text
scripts/sc1_*.py
tests/assets/*
docs/reports/sc1_*.json
docs/reports/sc1_*.md
godot/resources/presentation_manifest.sc1.generated.json
godot/scripts/sprite_loader.gd
.gitignore
```

Forbidden commit targets unless explicitly approved:

```text
local_assets/**
godot/assets/sc1_extracted/**
godot/assets/sc1_generated/**
tools/mpq/**
raw MPQ files
```

Run:

```bash
git add scripts/sc1_*.py tests/assets docs/reports/sc1_* godot/resources/presentation_manifest.sc1.generated.json godot/scripts/sprite_loader.gd .gitignore
git commit -m "feat: add sc1 local asset extraction and comparison pipeline"
```

---

## Acceptance Criteria

The iteration is complete when:

- `Patch_rt.mpq`, `BrooDat.mpq`, and `StarDat.mpq` are inventory-scanned.
- Extracted file priority resolves conflicts deterministically.
- At least the P0 visual set is converted and available locally:
  - Terran: SCV, Marine, CommandCenter, Barracks, Refinery.
  - Zerg: Drone, Zergling, Hatchery, SpawningPool, Extractor.
  - Protoss: Probe, Zealot, Nexus, Gateway, Pylon.
  - Resources: minerals, gas.
- `docs/reports/sc1_godot_resource_comparison.md` clearly lists covered, placeholder, missing, and needs-manifest-tuning resources.
- Godot can still start a game with current fallback resources if local SC1 assets are absent.
- Godot can prefer local extracted assets when `presentation_manifest.sc1.generated.json` and ignored asset files exist.
- No proprietary raw extracted assets are committed by default.

