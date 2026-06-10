# SC1 Completeness Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a validation system that measures how completely the project covers SC1-inspired planning data, balance values, visual/audio resources, and playable mechanics.

**Architecture:** This is a dev-harness and data-validation effort. It must not require proprietary StarCraft assets or raw game archives in the repository. The validation system reads existing project data (`data/*`, `godot/resources/*`, `godot/assets/*`) and produces explicit coverage reports: `exact`, `scaled`, `abstract`, `missing`, or `unknown`.

**Tech Stack:** Python 3.11, pytest, JSON Schema-style validation, existing SimCore/Godot data files, Godot presentation manifest, RTS test matrix.

---

## Problem Statement

The current project has a lot of SC1-inspired content:

- `data/units/units.json`
- `data/buildings/buildings.json`
- `data/spells/spells.json`
- `data/upgrades/upgrades.json`
- `data/combat.json`
- `godot/resources/presentation_manifest.json`
- `godot/resources/sprite_frames_config.json`
- `godot/resources/vfx/vfx_catalog.json`
- `godot/assets/sprites/*`
- `godot/assets/audio/*`
- `docs/design/sc1_presentation_catalog.md`
- `docs/dual_track_roadmap.md`
- `docs/SC1_Godot_Replication_Plan.md`

But the project lacks a single answer to:

- Which SC1 units/buildings/spells/upgrades are represented?
- Which ones have gameplay data but no visual/audio resources?
- Which values are exact, scaled, abstracted, or unknown?
- Which mechanics are implemented in SimCore versus only documented?
- Which gaps block a credible research demo?

This plan creates that answer as a repeatable report.

## Fidelity Levels

Use these labels everywhere:

| Level | Meaning |
|---|---|
| `exact` | Data is intended to match SC1/BW reference behavior or value. |
| `scaled` | Data is converted into this engine's units/ticks but keeps proportional intent. |
| `abstract` | Item is intentionally simplified for research/playability. |
| `placeholder` | Item exists only to avoid missing references; not validated. |
| `missing` | Required item does not exist. |
| `unknown` | Item exists, but reference source or fidelity is not established. |

## Legal Boundary

- Do not commit extracted proprietary assets or MPQ/CASC contents.
- Reference catalogs may contain names, local project IDs, coverage state, and links to local files.
- If external SC1 values are used later, record source and confidence, but keep this plan executable without external downloads.
- The first version should audit current project completeness; it should not claim exact SC1 balance parity.

---

## File Structure

Create:

- `data/sc1_reference/schema.json`  
  Defines coverage item structure.

- `data/sc1_reference/coverage_manifest.json`  
  Human-editable coverage ledger for units, buildings, spells, upgrades, resources, UI, and mechanics.

- `scripts/sc1_completeness_audit.py`  
  Reads current project data and coverage manifest, prints coverage totals and writes JSON report.

- `scripts/verify_sc1_assets.py`  
  Checks visual/audio/VFX asset coverage by entity.

- `scripts/verify_sc1_values.py`  
  Checks data-field coverage and value provenance tags.

- `scripts/verify_sc1_mechanics.py`  
  Checks mechanics coverage against tests and implementation files.

- `tests/data/test_sc1_completeness_audit.py`  
  Tests audit report shape and required coverage categories.

- `tests/data/test_sc1_assets_coverage.py`  
  Tests asset verifier catches missing or placeholder-only coverage.

- `tests/data/test_sc1_values_coverage.py`  
  Tests values have required fields and fidelity labels.

- `docs/reports/sc1_completeness_report.md`  
  Generated or manually updated summary for the user.

Modify:

- `docs/design/sc1_presentation_catalog.md`  
  Add link to generated completeness report.

- `docs/dual_track_roadmap.md`  
  Replace rough percentages with report-backed coverage numbers.

---

## Task 1: Define Coverage Schema

**Files:**
- Create: `data/sc1_reference/schema.json`
- Create: `tests/data/test_sc1_completeness_audit.py`

- [ ] **Step 1: Create schema file**

Create `data/sc1_reference/schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SC1 Completeness Coverage Manifest",
  "type": "object",
  "required": ["version", "categories", "fidelity_levels"],
  "properties": {
    "version": {"type": "string"},
    "fidelity_levels": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["exact", "scaled", "abstract", "placeholder", "missing", "unknown"]
      },
      "minItems": 6
    },
    "categories": {
      "type": "object",
      "required": ["units", "buildings", "spells", "upgrades", "resources", "ui", "mechanics"],
      "properties": {
        "units": {"type": "object"},
        "buildings": {"type": "object"},
        "spells": {"type": "object"},
        "upgrades": {"type": "object"},
        "resources": {"type": "object"},
        "ui": {"type": "object"},
        "mechanics": {"type": "object"}
      }
    }
  }
}
```

- [ ] **Step 2: Add test for manifest categories**

Create `tests/data/test_sc1_completeness_audit.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/sc1_reference/coverage_manifest.json"


def test_sc1_coverage_manifest_has_required_categories() -> None:
    manifest = json.loads(MANIFEST.read_text())
    categories = set(manifest["categories"])
    assert {
        "units",
        "buildings",
        "spells",
        "upgrades",
        "resources",
        "ui",
        "mechanics",
    } <= categories


def test_sc1_coverage_items_have_fidelity_labels() -> None:
    manifest = json.loads(MANIFEST.read_text())
    allowed = set(manifest["fidelity_levels"])
    for category, items in manifest["categories"].items():
        for item_id, item in items.items():
            assert item["fidelity"] in allowed, f"{category}/{item_id}"
            assert item["status"] in {"covered", "partial", "missing", "unknown"}, f"{category}/{item_id}"
```

- [ ] **Step 3: Run test and verify it fails**

Run:

```bash
python3 -m pytest tests/data/test_sc1_completeness_audit.py -q
```

Expected:

- Fails because `coverage_manifest.json` does not exist yet.

---

## Task 2: Create Initial Coverage Manifest

**Files:**
- Create: `data/sc1_reference/coverage_manifest.json`

- [ ] **Step 1: Create initial manifest**

Create `data/sc1_reference/coverage_manifest.json`:

```json
{
  "version": "0.1.0",
  "fidelity_levels": ["exact", "scaled", "abstract", "placeholder", "missing", "unknown"],
  "categories": {
    "units": {},
    "buildings": {},
    "spells": {},
    "upgrades": {},
    "resources": {
      "mineral_field": {
        "status": "partial",
        "fidelity": "abstract",
        "current_data_paths": ["simcore/mapgen.py", "godot/resources/sprite_frames_config.json"],
        "visual_required": true,
        "sim_required": true,
        "notes": "Mineral gameplay exists, visual/resource-node completeness needs explicit audit."
      },
      "vespene_geyser": {
        "status": "partial",
        "fidelity": "abstract",
        "current_data_paths": ["simcore/mapgen.py", "godot/resources/sprite_frames_config.json"],
        "visual_required": true,
        "sim_required": true,
        "notes": "Gas loop exists, full geyser/refinery behavior requires audit."
      }
    },
    "ui": {
      "command_card": {
        "status": "partial",
        "fidelity": "abstract",
        "current_data_paths": ["godot/scripts/hud.gd", "godot/assets/sprites/ui/CmdIcons.png"],
        "notes": "Command card assets exist; icon-to-command coverage needs audit."
      },
      "portrait": {
        "status": "partial",
        "fidelity": "placeholder",
        "current_data_paths": ["godot/assets/sprites/ui/Portrait.png"],
        "notes": "Portrait sheet exists but per-unit portrait mapping is not verified."
      }
    },
    "mechanics": {
      "selection_limit_12": {
        "status": "partial",
        "fidelity": "abstract",
        "current_data_paths": ["docs/frontend_test_cases.md", "godot/scripts/selection_manager.gd"],
        "notes": "SC1-style selection cap is documented; implementation/test coverage needs audit."
      },
      "fog_three_state": {
        "status": "covered",
        "fidelity": "abstract",
        "current_data_paths": ["simcore/rules.py", "godot/scripts/game_view.gd", "tests/simcore/test_fog.py"],
        "notes": "Three-state fog is implemented, visual smoothing is Godot-side."
      }
    }
  }
}
```

- [ ] **Step 2: Run manifest tests**

Run:

```bash
python3 -m pytest tests/data/test_sc1_completeness_audit.py -q
```

Expected:

- Passes with the initial categories.

---

## Task 3: Generate Unit/Building/Spell/Upgrade Coverage Automatically

**Files:**
- Create: `scripts/sc1_completeness_audit.py`
- Modify: `data/sc1_reference/coverage_manifest.json`
- Modify: `tests/data/test_sc1_completeness_audit.py`

- [ ] **Step 1: Add audit script**

Create `scripts/sc1_completeness_audit.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MANIFEST = DATA / "sc1_reference/coverage_manifest.json"
REPORT_JSON = ROOT / "docs/reports/sc1_completeness_report.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def race_items(path: Path) -> dict[str, dict]:
    data = load_json(path)
    out: dict[str, dict] = {}
    for race in ("terran", "zerg", "protoss"):
        for name, item in data.get(race, {}).items():
            out[name] = {"race": race, **item}
    return out


def list_spells() -> dict[str, dict]:
    return {item["name"]: item for item in load_json(DATA / "spells/spells.json")["spells"]}


def list_upgrades() -> dict[str, dict]:
    return {item["name"]: item for item in load_json(DATA / "upgrades/upgrades.json")["upgrades"]}


def summarize_category(expected: dict[str, dict], manifest_items: dict[str, dict]) -> dict:
    rows = {}
    for name, item in expected.items():
        coverage = manifest_items.get(name, {})
        rows[name] = {
            "race": item.get("race", item.get("race_required", "neutral")),
            "status": coverage.get("status", "unknown"),
            "fidelity": coverage.get("fidelity", "unknown"),
            "has_manifest_entry": name in manifest_items,
        }
    return rows


def main() -> int:
    manifest = load_json(MANIFEST)
    categories = manifest["categories"]
    report = {
        "units": summarize_category(race_items(DATA / "units/units.json"), categories.get("units", {})),
        "buildings": summarize_category(race_items(DATA / "buildings/buildings.json"), categories.get("buildings", {})),
        "spells": summarize_category(list_spells(), categories.get("spells", {})),
        "upgrades": summarize_category(list_upgrades(), categories.get("upgrades", {})),
        "resources": categories.get("resources", {}),
        "ui": categories.get("ui", {}),
        "mechanics": categories.get("mechanics", {}),
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    for category in ("units", "buildings", "spells", "upgrades"):
        rows = report[category]
        total = len(rows)
        known = sum(1 for row in rows.values() if row["status"] != "unknown")
        covered = sum(1 for row in rows.values() if row["status"] == "covered")
        partial = sum(1 for row in rows.values() if row["status"] == "partial")
        print(f"{category}: total={total} known={known} covered={covered} partial={partial} unknown={total-known}")

    print(f"wrote {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add test for generated report**

Append to `tests/data/test_sc1_completeness_audit.py`:

```python
def test_sc1_completeness_audit_generates_report() -> None:
    import subprocess

    result = subprocess.run(
        ["python3", "scripts/sc1_completeness_audit.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((ROOT / "docs/reports/sc1_completeness_report.json").read_text())
    assert len(report["units"]) >= 40
    assert len(report["buildings"]) >= 30
    assert len(report["spells"]) >= 25
    assert len(report["upgrades"]) >= 50
```

- [ ] **Step 3: Run audit**

Run:

```bash
python3 scripts/sc1_completeness_audit.py
python3 -m pytest tests/data/test_sc1_completeness_audit.py -q
```

Expected:

- Report is generated under `docs/reports/sc1_completeness_report.json`.
- Most entries are initially `unknown`; this is acceptable and becomes the work queue.

---

## Task 4: Asset Coverage Verification

**Files:**
- Create: `scripts/verify_sc1_assets.py`
- Create: `tests/data/test_sc1_assets_coverage.py`

- [ ] **Step 1: Create asset verifier**

Create `scripts/verify_sc1_assets.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "godot/resources/presentation_manifest.json"
VFX = ROOT / "godot/resources/vfx/vfx_catalog.json"
ASSET_ROOT = ROOT / "godot"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def res_exists(path: str) -> bool:
    return path.startswith("res://") and (ASSET_ROOT / path.removeprefix("res://")).exists()


def main() -> int:
    manifest = load_json(MANIFEST)
    vfx = load_json(VFX)
    issues: list[str] = []

    for name, visual in manifest["unit_visuals"].items():
        if not res_exists(visual.get("asset", "")):
            issues.append(f"unit {name}: missing sprite asset {visual.get('asset')}")
        fallback = visual.get("fallback", {})
        if fallback.get("asset") and not res_exists(fallback["asset"]):
            issues.append(f"unit {name}: missing fallback asset {fallback['asset']}")

    for name, visual in manifest["building_visuals"].items():
        if not res_exists(visual.get("asset", "")):
            issues.append(f"building {name}: missing sprite asset {visual.get('asset')}")

    unit_effects = set(vfx.get("unit_effects", {}))
    for name in manifest["unit_visuals"]:
        if name not in unit_effects:
            issues.append(f"unit {name}: missing vfx unit_effects mapping")

    if issues:
        print(f"FAIL — {len(issues)} SC1 asset issue(s)")
        for issue in issues[:200]:
            print(f"  - {issue}")
        return 1

    print("OK — SC1 asset coverage checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add asset verifier test**

Create `tests/data/test_sc1_assets_coverage.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_sc1_asset_verifier_runs() -> None:
    result = subprocess.run(
        ["python3", "scripts/verify_sc1_assets.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 1}
    assert "SC1 asset" in result.stdout or "SC1 asset" in result.stderr
```

- [ ] **Step 3: Run verifier**

Run:

```bash
python3 scripts/verify_sc1_assets.py
python3 -m pytest tests/data/test_sc1_assets_coverage.py -q
```

Expected:

- The script may fail initially due to missing VFX mappings. That is acceptable if it reports actionable gaps.

---

## Task 5: Value Coverage Verification

**Files:**
- Create: `scripts/verify_sc1_values.py`
- Create: `tests/data/test_sc1_values_coverage.py`

- [ ] **Step 1: Define required value fields**

Create `scripts/verify_sc1_values.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

UNIT_REQUIRED = ["name", "hp", "cost", "build_time", "supply", "sprite"]
BUILDING_REQUIRED = ["name", "hp", "cost", "build_time"]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def check_race_dict(path: Path, required: list[str], category: str) -> list[str]:
    data = load_json(path)
    issues: list[str] = []
    for race in ("terran", "zerg", "protoss"):
        for name, item in data.get(race, {}).items():
            for field in required:
                if field not in item:
                    issues.append(f"{category} {race}/{name}: missing {field}")
    return issues


def main() -> int:
    issues: list[str] = []
    issues.extend(check_race_dict(ROOT / "data/units/units.json", UNIT_REQUIRED, "unit"))
    issues.extend(check_race_dict(ROOT / "data/buildings/buildings.json", BUILDING_REQUIRED, "building"))

    if issues:
        print(f"FAIL — {len(issues)} SC1 value coverage issue(s)")
        for issue in issues[:200]:
            print(f"  - {issue}")
        return 1

    print("OK — SC1 unit/building value fields present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add value verifier test**

Create `tests/data/test_sc1_values_coverage.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_sc1_value_verifier_runs() -> None:
    result = subprocess.run(
        ["python3", "scripts/verify_sc1_values.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 1}
    assert "SC1" in result.stdout or "SC1" in result.stderr
```

- [ ] **Step 3: Run value verifier**

Run:

```bash
python3 scripts/verify_sc1_values.py
python3 -m pytest tests/data/test_sc1_values_coverage.py -q
```

Expected:

- The first run may fail because field names differ. If so, update `UNIT_REQUIRED` / `BUILDING_REQUIRED` to match current data shape, but keep the verifier strict enough to identify missing value coverage.

---

## Task 6: Mechanics Coverage Verification

**Files:**
- Create: `scripts/verify_sc1_mechanics.py`
- Create: `docs/reports/sc1_mechanics_matrix.md`

- [ ] **Step 1: Define mechanics matrix**

Create `docs/reports/sc1_mechanics_matrix.md`:

```markdown
# SC1 Mechanics Coverage Matrix

| Mechanic | Target fidelity | Current evidence | Status | Blocking tests |
|---|---:|---|---|---|
| Worker gather loop | abstract | `tests/simcore/test_gas_loop.py` | partial | `python3 -m pytest tests/simcore/test_gas_loop.py -q` |
| Fog three-state | abstract | `tests/simcore/test_fog.py` | covered | `python3 -m pytest tests/simcore/test_fog.py -q` |
| Cloak/detection | abstract | `tests/simcore/test_cloak.py` | partial | `python3 -m pytest tests/simcore/test_cloak.py -q` |
| Zerg morph | abstract | `tests/simcore/test_zerg_morph.py` | partial | `python3 -m pytest tests/simcore/test_zerg_morph.py -q` |
| Protoss shields | abstract | `tests/simcore/test_combat.py` | partial | `python3 -m pytest tests/simcore/test_combat.py -q` |
| Pylon power | abstract | `godot/scripts/game_view.gd` | partial | manual/Godot needed |
| High-ground miss chance | scaled | `docs/dual_track_roadmap.md` | missing | no test |
| Creep spread | abstract | `docs/dual_track_roadmap.md` | missing | no test |
| Siege mode | abstract | `docs/dual_track_roadmap.md` | missing | no test |
| Carrier interceptors | abstract | `docs/dual_track_roadmap.md` | missing | no test |
```

- [ ] **Step 2: Create verifier**

Create `scripts/verify_sc1_mechanics.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TESTS = {
    "fog_three_state": "tests/simcore/test_fog.py",
    "cloak_detection": "tests/simcore/test_cloak.py",
    "zerg_morph": "tests/simcore/test_zerg_morph.py",
    "gas_loop": "tests/simcore/test_gas_loop.py",
}


def main() -> int:
    issues: list[str] = []
    for mechanic, path in REQUIRED_TESTS.items():
        if not (ROOT / path).exists():
            issues.append(f"{mechanic}: missing test {path}")

    if issues:
        print(f"FAIL — {len(issues)} mechanics coverage issue(s)")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("OK — required SC1 mechanics test files exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run mechanics verifier**

Run:

```bash
python3 scripts/verify_sc1_mechanics.py
python3 -m pytest tests/simcore/test_fog.py tests/simcore/test_cloak.py tests/simcore/test_gas_loop.py tests/simcore/test_zerg_morph.py -q
```

Expected:

- Test files exist.
- Some tests may fail depending on current SimCore state. Failures become mechanics blockers, not verifier blockers.

---

## Task 7: Generate Research Demo Acceptance Matrix

**Files:**
- Create: `production/test-matrices/sc1_research_demo_matrix.yaml`

- [ ] **Step 1: Create test matrix**

Create `production/test-matrices/sc1_research_demo_matrix.yaml`:

```yaml
test_matrix:
  id: "SC1-RESEARCH-DEMO-001"
  purpose: "Validate enough SC1-inspired completeness for research demos, not full Brood War parity."
  dimensions:
    races:
      - terran
      - zerg
      - protoss
    categories:
      - data_values
      - visual_assets
      - audio_assets
      - vfx
      - ui_command_card
      - economy_loop
      - combat_loop
      - fog
      - replay
    maps:
      - procedural_64
      - procedural_96
    seeds:
      - 1
      - 42
      - 123
      - 2026
    opponents:
      - script_ai_easy
      - script_ai_medium
  gates:
    p0_demo:
      required:
        - all worker/base/basic_combat units covered
        - all base/barracks/refinery/supply buildings covered
        - no missing sprite for covered units/buildings
        - economy loop passes for all races
        - basic combat loop passes for all races
    p1_extended:
      required:
        - all units have data and sprite coverage
        - all buildings have data and manifest coverage
        - at least one spell per race has gameplay and VFX evidence
        - replay hash deterministic for 1000 ticks
```

- [ ] **Step 2: Link matrix from report**

Add this line to `docs/reports/sc1_completeness_report.md` when Task 8 creates it:

```markdown
Research demo gate matrix: `production/test-matrices/sc1_research_demo_matrix.yaml`
```

---

## Task 8: Produce Human-Readable Completeness Report

**Files:**
- Create: `docs/reports/sc1_completeness_report.md`
- Modify: `docs/dual_track_roadmap.md`

- [ ] **Step 1: Create report**

Create `docs/reports/sc1_completeness_report.md`:

```markdown
# SC1 Completeness Report

## Status

This report measures project coverage for SC1-inspired design, balance values, resources, UI, and mechanics. It does not claim full Brood War parity.

## Current Gates

| Gate | Status | Notes |
|---|---|---|
| Data catalog exists | PASS | `data/units`, `data/buildings`, `data/spells`, `data/upgrades` exist |
| Presentation manifest validates | PASS/FAIL | Run `python3 scripts/verify_presentation_scene.py` |
| Asset coverage verifier | PASS/FAIL | Run `python3 scripts/verify_sc1_assets.py` |
| Value coverage verifier | PASS/FAIL | Run `python3 scripts/verify_sc1_values.py` |
| Mechanics coverage verifier | PASS/FAIL | Run `python3 scripts/verify_sc1_mechanics.py` |

## Demo Scope

P0 research demo should focus on:

- Three workers: SCV, Drone, Probe
- Three bases: CommandCenter, Hatchery, Nexus
- Three basic combat units: Marine, Zergling, Zealot
- Three production buildings: Barracks, SpawningPool, Gateway
- Resource loop: mineral + gas
- Basic attack/move/fog/replay

## Known Gaps

- Exact SC1 values are not provenance-tagged.
- Resource node visuals and interactions need a dedicated audit.
- Command card icon mapping is not fully verified.
- Per-unit portrait mapping is not verified.
- Several advanced mechanics remain missing or partial: creep, high ground, siege mode, carrier interceptors.
```

- [ ] **Step 2: Update roadmap**

In `docs/dual_track_roadmap.md`, update Track B B1 statuses to reference this report:

```markdown
> Coverage source: `docs/reports/sc1_completeness_report.md`
```

- [ ] **Step 3: Run report commands**

Run:

```bash
python3 scripts/sc1_completeness_audit.py
python3 scripts/verify_presentation_scene.py
python3 scripts/verify_sc1_assets.py
python3 scripts/verify_sc1_values.py
python3 scripts/verify_sc1_mechanics.py
```

Expected:

- The report can be updated from these command results.
- Failures are allowed at first, but each must be specific and actionable.

---

## Task 9: Final Validation

Run:

```bash
python3 -m pytest tests/data/test_sc1_completeness_audit.py tests/data/test_sc1_assets_coverage.py tests/data/test_sc1_values_coverage.py -q
python3 scripts/sc1_completeness_audit.py
python3 scripts/verify_presentation_scene.py
python3 scripts/verify_sc1_assets.py
python3 scripts/verify_sc1_values.py
python3 scripts/verify_sc1_mechanics.py
```

Expected:

- Unit tests pass.
- Verification scripts produce stable output.
- It is acceptable for asset/value/mechanics verifiers to exit `1` if they report real gaps. The final report must list those gaps.

---

## Recommended First Sprint

Do not try to make SC1 complete in one sprint. First sprint should only make the unknowns measurable.

**P0**

- Build `coverage_manifest.json`.
- Generate `sc1_completeness_report.json`.
- Add asset/value/mechanics verifiers.
- Produce `sc1_completeness_report.md`.

**P1**

- Fill manifest entries for P0 demo scope: worker/base/basic combat/production/refinery/resource nodes.
- Add provenance tags for current unit/building values.
- Add command card icon and portrait mapping checks.

**P2**

- Add exact-value reference import path if you provide legal source files.
- Add screenshot or pixel-level Godot checks for resource/building alignment.
- Add replay-based mechanics validation for 1v1 demo loops.

## Success Criteria

- You can answer “what is missing?” with a generated report, not screenshots or intuition.
- P0 research demo scope is clearly separated from full SC1 parity.
- Missing data/resources are categorized as `missing` or `unknown`, not silently treated as complete.
- The next Godot/SimCore iteration can target the highest-impact gaps first.
