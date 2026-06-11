# SC1 Resource Extraction And Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract SC1 MPQ assets into local generated Godot previews, validate visual parity in Test Mode, and keep repo-safe source changes separate from ignored commercial assets.

**Architecture:** Commercial SC1 assets stay in ignored local folders. `scripts/sc1_extract_manifest.py` reads a committed manifest, extracts/converts local MPQ resources, and writes `godot/assets/sc1_generated/generated_manifest.json`. Godot `Test Mode` reads that generated manifest through `SpriteLoader` and displays race/type-filtered resources for manual QA.

**Tech Stack:** Python 3.11, local `tools/mpq/bin/storm_extract`, `scripts/sc1_grp_to_png.py`, Godot 4 headless scripts, GDScript `SpriteLoader`, `game_view.gd`.

---

## Current Test Mode Manual Validation Method

Use this when checking whether extracted resources look correct.

- Start the Python server stack used by the Godot frontend if it is not already running.
- Open Godot and run the game normally.
- Click `Test Mode` in the top-left corner.
- Use the `Race` menu to filter: `All`, `Terran`, `Zerg`, `Protoss`, `Neutral`.
- Use the `Type` menu to filter: `All`, `Buildings`, `Units`, `Resources`.
- Validate Buildings column:
  - Terran: `CommandCenter`, `Barracks`, `Refinery`.
  - Zerg: `Hatchery`, `SpawningPool`, `Extractor`.
  - Protoss: `Nexus`, `Gateway`, `Pylon`, `Assimilator`.
  - Check silhouettes, crop boundaries, transparent padding, scale, and selection/health bar readability.
- Validate Units column:
  - Terran: `SCV`, `Marine`.
  - Zerg: `Drone`, `Zergling`.
  - Protoss: `Probe`, `Zealot`.
  - Each unit appears twice: `move` and `atk`.
  - `move` should animate continuously and show a green move line.
  - `atk` should animate continuously, show a red attack line, and flash on attack cadence.
  - Compare cross-race scale: workers should be close in footprint; basic combat units should not collapse to tiny sprites.
- Validate Resources column:
  - `MineralFieldType1`, `MineralFieldType2`, `MineralFieldType3`, `VespeneGeyser`.
  - Check that resources use actual generated sprites, not old circle placeholders.

## Current Unit Scale Baseline

Generated unit scale is normalized by measured non-transparent body footprint, not full GRP cell size. This matters because many SC1 unit GRP frames have large transparent padding or occasional outlier frames.

| Asset | Race | Frame | Content Extent | Visible Body World |
| --- | --- | --- | --- | --- |
| `SCV` | Terran | `72x72` | `40` | `0.848` |
| `Marine` | Terran | `64x64` | `26` | `0.720` |
| `Drone` | Zerg | `128x128` | `38` | `0.718` |
| `Zergling` | Zerg | `128x128` | `27` | `0.621` |
| `Probe` | Protoss | `32x32` | `27` | `0.950` |
| `Zealot` | Protoss | `128x128` | `31` | `0.949` |

Acceptance range for manual QA: generated unit body footprint should be readable in Test Mode and should not collapse below `0.6` world units for P0 ground units. SCV should now be judged as a readable worker-scale sprite near Drone/Probe, not as a small Terran anchor. Marine/Drone/Zergling/Zealot should be judged relative to readable body footprint, not relative to raw 64/128 px cell sizes.

## Task 1: Prepare Branch And Baseline

**Files:**
- Read: `tools/sc1_assets/p0_resource_manifest.json`
- Read: `scripts/sc1_extract_manifest.py`
- Read: `godot/scripts/game_view.gd`
- Read: `godot/scripts/sprite_loader.gd`

- [ ] **Step 1: Confirm branch and workspace**

Run:

```bash
git branch --show-current
git status --short
```

Expected:

```text
codex-sc1-mpq-resource-sync
```

If on a different branch, create a new scoped branch:

```bash
git switch -c codex/sc1-resource-validation-pass
```

- [ ] **Step 2: Confirm local SC1 source exists**

Run:

```bash
ls /Users/yuyou/code/StarCraft
ls tools/mpq/bin/storm_extract
```

Expected: StarCraft MPQs exist under `/Users/yuyou/code/StarCraft`, and `storm_extract` exists.

- [ ] **Step 3: Confirm generated assets are ignored**

Run:

```bash
git check-ignore godot/assets/sc1_generated/generated_manifest.json
git check-ignore local_assets/sc1_converted/p0/SCV.png
```

Expected: both paths are ignored. Do not commit generated PNGs or generated manifest unless the project policy changes.

## Task 2: Extract And Convert P0 Resources

**Files:**
- Read: `tools/sc1_assets/p0_resource_manifest.json`
- Use: `scripts/sc1_extract_manifest.py`
- Use: `scripts/sc1_grp_to_png.py`
- Generated ignored output: `local_assets/sc1_mpq_raw/p0/`
- Generated ignored output: `local_assets/sc1_converted/p0/`
- Generated ignored output: `godot/assets/sc1_generated/generated_manifest.json`

- [ ] **Step 1: Run extraction**

Run:

```bash
python3 scripts/sc1_extract_manifest.py --starcraft-dir /Users/yuyou/code/StarCraft --convert
```

Expected:

```text
assets=20 extracted=20 missing=0
converted_failed=0
generated_manifest=/Users/yuyou/code/rts-ai-platform/godot/assets/sc1_generated/generated_manifest.json
```

- [ ] **Step 2: Verify generated manifest counts**

Run:

```bash
python3 - <<'PY'
import json
from collections import Counter
from pathlib import Path
m = json.loads(Path("godot/assets/sc1_generated/generated_manifest.json").read_text())
print("assets", len(m["assets"]))
for key, count in sorted(Counter((v["race"], v["kind"]) for v in m["assets"].values()).items()):
    print(key, count)
PY
```

Expected:

```text
assets 20
('neutral', 'resource') 4
('protoss', 'building') 4
('protoss', 'unit') 2
('terran', 'building') 3
('terran', 'unit') 2
('zerg', 'building') 3
('zerg', 'unit') 2
```

- [ ] **Step 3: Verify generated unit scale range**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("godot/assets/sc1_generated/generated_manifest.json").read_text())
for asset_id, entry in m["assets"].items():
    if entry["kind"] != "unit":
        continue
    body_world = entry["content_extent"] * float(entry["render_scale"])
    print(asset_id, entry["race"], round(body_world, 3), entry["scale_basis"])
    assert entry["scale_basis"] == "content_median_extent"
    assert body_world >= 0.6, (asset_id, body_world)
PY
```

Expected: no assertion failure.

## Task 3: Automated Regression Tests

**Files:**
- Test: `tests/godot/test_sc1_generated_manifest.py`
- Test: `godot/scripts/test_sprite_loader_generated.gd`
- Test: `godot/scripts/test_game_view_probe_override.gd`

- [ ] **Step 1: Run Python manifest tests**

Run:

```bash
pytest tests/godot/test_sc1_generated_manifest.py tests/godot/test_presentation_manifest.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run SpriteLoader generated manifest test**

Run:

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sprite_loader_generated.gd
```

Expected:

```text
SpriteLoader generated manifest test: 5 passed, 0 failed
```

- [ ] **Step 3: Run GameView Test Mode gallery test**

Run:

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_game_view_probe_override.gd
```

Expected:

```text
GameView Probe override test: 3 passed, 0 failed
```

- [ ] **Step 4: Run Python lint and compile checks**

Run:

```bash
ruff check scripts/sc1_extract_manifest.py tests/godot/test_sc1_generated_manifest.py
python3 -m py_compile scripts/sc1_extract_manifest.py scripts/sc1_grp_to_png.py
```

Expected: `ruff` prints `All checks passed!`, and `py_compile` exits with code `0`.

## Task 4: Manual Visual QA In Test Mode

**Files:**
- Inspect manually in Godot runtime.
- Reference: `godot/assets/sc1_generated/generated_manifest.json`

- [ ] **Step 1: Open Test Mode**

Start game in Godot, click `Test Mode`.

Expected: three world-space columns appear: `Buildings`, `Units`, `Resources`.

- [ ] **Step 2: Check all filters**

Select each filter combination:

```text
Race: All, Terran, Zerg, Protoss, Neutral
Type: All, Buildings, Units, Resources
```

Expected: only matching assets remain visible; returning to `All` restores the full gallery.

- [ ] **Step 3: Check building crops and scale**

Expected:

```text
CommandCenter ~= Hatchery ~= Nexus as base-tier buildings
Barracks ~= Gateway as production-tier buildings
Pylon remains visibly smaller than Nexus/Gateway
Gas buildings are readable and not clipped
```

- [ ] **Step 4: Check unit scale and animation**

Expected:

```text
SCV, Drone, Probe workers have comparable visual footprint
Marine, Zergling, Zealot are readable and not tiny
move previews animate and show green move lines
atk previews animate, show red attack lines, and flash
```

- [ ] **Step 5: Check resources**

Expected:

```text
Mineral fields and geyser display generated sprites
No circular placeholder remains in Test Mode for generated resources
Transparent background is clean
```

## Task 5: Commit Repo-Safe Changes Only

**Files to stage when code changes are made:**
- `scripts/sc1_extract_manifest.py`
- `godot/scripts/sprite_loader.gd`
- `godot/scripts/game_view.gd`
- `tests/godot/test_sc1_generated_manifest.py`
- `godot/scripts/test_sprite_loader_generated.gd`
- `godot/scripts/test_game_view_probe_override.gd`
- `docs/plans/2026-06-11-sc1-resource-extraction-validation-sop.md`

- [ ] **Step 1: Check status**

Run:

```bash
git status --short
```

Expected: generated `.godot/imported/*`, `godot/assets/sc1_generated/*`, and `local_assets/*` are not staged.

- [ ] **Step 2: Stage only repo-safe files**

Run:

```bash
git add scripts/sc1_extract_manifest.py godot/scripts/sprite_loader.gd godot/scripts/game_view.gd tests/godot/test_sc1_generated_manifest.py godot/scripts/test_sprite_loader_generated.gd godot/scripts/test_game_view_probe_override.gd docs/plans/2026-06-11-sc1-resource-extraction-validation-sop.md
```

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "docs: add sc1 resource extraction validation sop"
```

Expected: commit includes only code/tests/docs, not commercial generated assets.

## P1A Extension Notes

### Batch Extraction

P1A uses `--batch-out` flag on `sc1_extract_manifest.py`:
```bash
python3 scripts/sc1_extract_manifest.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --convert --batch-out
```

### Path Discovery

New units may have abbreviated MPQ filenames. Use `sc1_discover_assets.py` to probe:
```bash
python3 scripts/sc1_discover_assets.py \
  --manifest tools/sc1_assets/p1a_resource_manifest.json
```

Known abbreviations:
- Hydralisk → `hydra.grp`
- Mutalisk → `mutalid.grp`
- Dragoon → comes from BrooDat.mpq

### Pending Assets

Wraith and Reaver have `mpq_path: "PENDING"` — their actual GRP filename inside StarDat.mpq could not be determined via images.tbl. These need manual MPQ browsing or dat file parsing.

### Visual Class Scale Rules

| Class | body_world range |
|-------|-----------------|
| worker | 0.85–0.95 |
| small_ground | 0.70–0.85 |
| medium_ground | 0.90–1.15 |
| large_ground | 1.30–1.80 |
| small_air | 0.90–1.20 |
| large_air | 1.60–2.20 |

### P1A QA Checklist (append to existing)

- [ ] P0 + P1A manifest merge produces 30+ assets
- [ ] No ID overlap between P0 and P1A
- [ ] All unit visual_classes map to valid scale ranges
- [ ] Batch filter in Test Mode shows P0/P1A/All
- [ ] Flying units show ✈ marker
- [ ] Building sorting follows race + tech tier

---

## P1A Resolved Aliases

- Wraith uses `unit\terran\phoenix.grp` in StarDat.mpq (SC1 dev codename: phoenix).
- Reaver uses `unit\protoss\trilob.grp` in StarDat.mpq (SC1 dev codename: trilob).
