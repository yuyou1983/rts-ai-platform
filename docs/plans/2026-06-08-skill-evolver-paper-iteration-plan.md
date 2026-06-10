# SkillEvolver Paper Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the current SkillEvolver harness closer to the workflow described by [Skill Evolution via Contrastive Trace Analysis](https://arxiv.org/html/2605.10500v1), using Godot VFX/resource alignment as the first real end-to-end trial domain.

**Architecture:** Skill evolution remains a dev-side harness concern. It may modify `.agents/skills/*`, `harness/skills/*`, `harness/trace/*`, and `harness/evolve/*`; it must not directly patch `simcore/`, `agents/`, or `godot/scripts/` as part of promotion. Runtime behavior changes still go through normal harness-executor tasks and tests.

**Tech Stack:** Python 3.11, pytest, JSON Schema, Godot 4.4.1 headless check-only, RTS-AI four-layer architecture, Hermes/Codex-style skill execution traces.

---

## Execution Rules For The Next Agent

- Work from `/Users/yuyou/code/rts-ai-platform`.
- Do not revert unrelated dirty files. The worktree is expected to contain existing user/Hermes changes.
- Use `rg` or `rg --files` for searches.
- Use `apply_patch` for manual file edits.
- Run the targeted validation commands after each task.
- Commit each completed task separately if the execution environment asks for commits. Use messages from each task's "Commit" step.
- Keep SkillEvolver promotion default as dry-run. `--apply` must remain explicit.
- Keep the project invariant: SimCore never imports Agents; Agents never import Godot; all cross-layer runtime communication is protobuf/gRPC.

## Current Evidence Snapshot

Relevant existing files:

- `AGENTS.md` defines project layers as `Proto(L0) -> SimCore(L1) -> Agents(L2) -> Frontend/Godot(L3)`.
- `docs/architecture/adr-skill-evolver-harness.md` currently defines SkillEvolver scope, but uses a conflicting layer map.
- `harness/skills/schema.json` defines registry metadata for skill evolution.
- `harness/skills/registry.json` currently contains 4 registered skills.
- `.agents/skills/*/SKILL.md` currently contains 22 local skills.
- `harness/trace/schema.py` defines `SkillTrial`.
- `harness/trace/validate_traces.py` validates trace JSONL records.
- `harness/evolve/skill_evolver.py` has static strategy templates, shallow contrast, regex auditor, held-out validation, dry-run, and explicit `--apply`.
- `harness/devops_harness/executor/scripts/task_state.py` already accepts skill trace CLI parameters in `complete`.
- `scripts/verify_presentation_scene.py` already validates Godot presentation manifest, atlas bounds, abstract mapping, fallback assets, and hardcoded drift.
- `tests/harness/test_skill_evolver.py` contains the existing SkillEvolver regression suite.

## Desired End State

After this plan:

- All 22 local skills are registered and auditable.
- Skill registry layer names match `AGENTS.md`.
- Trace validation can infer silent-bypass instead of trusting a recorded boolean.
- Godot VFX/resource alignment has a real task fixture and held-out suite.
- Strategy exploration can generate fresh-agent work packets for multiple strategies.
- Contrastive update can compare pass/fail tool traces beyond three boolean checks.
- Auditor is split into a separate module with a structured audit report.
- No skill patch can be promoted unless registry, trace validation, auditor, held-out, architecture lint, and targeted domain tests pass.

---

## File Structure

Create:

- `docs/plans/2026-06-08-skill-evolver-paper-iteration-plan.md`  
  This implementation plan.

- `harness/skills/tasks/schema.json`  
  JSON schema for reusable skill task fixtures.

- `harness/skills/tasks/godot-vfx/sc1-resource-alignment.json`  
  First real task fixture for Godot VFX/resource alignment.

- `harness/evolve/strategy_runner.py`  
  Generates per-strategy fresh-agent work packets and run manifests.

- `harness/evolve/auditor.py`  
  Independent structured auditor for candidate skill patches.

- `tests/harness/test_trace_validation.py`  
  Focused tests for strict trace validation and silent-bypass inference.

- `tests/harness/test_strategy_runner.py`  
  Tests for task fixture loading and strategy packet generation.

- `tests/harness/test_skill_auditor.py`  
  Tests for the independent auditor.

Modify:

- `docs/architecture/adr-skill-evolver-harness.md`  
  Align SkillEvolver scope with the actual project layer map.

- `harness/skills/schema.json`  
  Replace conflicting layer enum with explicit domain names.

- `harness/skills/registry.json`  
  Register all local skills and update layer constraints.

- `harness/skills/validate_registry.py`  
  Validate complete coverage and the corrected layer enum.

- `harness/trace/schema.py`  
  Add trace v2 fields while keeping backward-compatible defaults.

- `harness/trace/validate_traces.py`  
  Add strict silent-bypass inference.

- `harness/evolve/skill_evolver.py`  
  Use the independent auditor, richer trace comparison, and candidate metadata.

- `harness/skills/held_out/godot-specialist/suite.json`  
  Replace weak existence checks with real Godot presentation validation commands.

- `tests/harness/test_skill_evolver.py`  
  Update layer enum assertions and add regression tests for dry-run promotion behavior.

---

## Task 0: Baseline Verification

**Files:**
- Read: `AGENTS.md`
- Read: `harness/skills/registry.json`
- Read: `harness/skills/schema.json`
- Read: `harness/evolve/skill_evolver.py`
- Read: `scripts/verify_presentation_scene.py`

- [ ] **Step 1: Capture current dirty state**

Run:

```bash
git status --short
```

Expected:

- Output may contain many modified and untracked files.
- Do not clean, reset, checkout, or delete any file.

- [ ] **Step 2: Run current SkillEvolver tests**

Run:

```bash
python3 -m pytest tests/harness/test_skill_evolver.py -q
```

Expected:

- Existing tests pass before deeper changes.
- If failures occur, inspect whether they are caused by current repo state. Do not rewrite unrelated systems.

- [ ] **Step 3: Run current registry and trace validators**

Run:

```bash
python3 harness/skills/validate_registry.py
python3 harness/trace/validate_traces.py --strict
```

Expected:

- Record the exact output in the task notes.
- These commands define the baseline for later improvements.

- [ ] **Step 4: Commit checkpoint if requested**

Commit message:

```bash
git add docs/plans/2026-06-08-skill-evolver-paper-iteration-plan.md
git commit -m "docs: add skill evolver paper alignment plan"
```

If this plan file is already committed by the initiating agent, skip this commit.

---

## Task 1: Align SkillEvolver Layer Names With AGENTS.md

**Files:**
- Modify: `harness/skills/schema.json`
- Modify: `harness/skills/validate_registry.py`
- Modify: `harness/skills/registry.json`
- Modify: `docs/architecture/adr-skill-evolver-harness.md`
- Modify: `tests/harness/test_skill_evolver.py`

The current schema uses `L0-simcore`, `L1-agents`, `L2-godot`, `L3-harness`, which conflicts with `AGENTS.md`. Use non-ambiguous domain layer names:

```json
[
  "proto",
  "simcore",
  "agents",
  "frontend-godot",
  "dev-harness"
]
```

- [ ] **Step 1: Write the failing layer enum test**

In `tests/harness/test_skill_evolver.py`, replace the existing `test_layer_enum_values` expected set with:

```python
assert set(layer_prop["items"]["enum"]) == {
    "proto",
    "simcore",
    "agents",
    "frontend-godot",
    "dev-harness",
}
```

Add a registry coverage test in `TestRegistrySchema`:

```python
def test_all_local_skills_registered(self):
    registry = json.loads(REGISTRY_PATH.read_text())
    registered = {entry["name"] for entry in registry}
    local = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    assert local <= registered
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
python3 -m pytest tests/harness/test_skill_evolver.py::TestRegistrySchema::test_layer_enum_values tests/harness/test_skill_evolver.py::TestRegistrySchema::test_all_local_skills_registered -q
```

Expected:

- `test_layer_enum_values` fails until the schema is updated.
- `test_all_local_skills_registered` fails until registry coverage is completed in Task 2.

- [ ] **Step 3: Update `harness/skills/schema.json`**

Change `properties.layer_constraints.items.enum` to:

```json
["proto", "simcore", "agents", "frontend-godot", "dev-harness"]
```

Keep the required fields unchanged:

```json
[
  "name",
  "description",
  "primary_action",
  "expected_tool_calls",
  "validation_commands",
  "owner_domain",
  "layer_constraints",
  "known_failure_modes"
]
```

- [ ] **Step 4: Update `harness/skills/validate_registry.py`**

Replace `LAYER_NAMES` with:

```python
LAYER_NAMES = {"proto", "simcore", "agents", "frontend-godot", "dev-harness"}
```

Add a local skill coverage check after duplicate-name validation:

```python
    registered = {entry.get("name") for entry in registry}
    local = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    missing = sorted(local - registered)
    if missing:
        issues.append(f"Missing registry entries for local skills: {missing}")
```

- [ ] **Step 5: Update existing registry entries**

Use these corrected layer constraints:

```json
{
  "godot-specialist": ["frontend-godot", "dev-harness"],
  "harness-run": ["proto", "simcore", "agents", "frontend-godot", "dev-harness"],
  "team-simcore": ["proto", "simcore", "dev-harness"],
  "team-ai": ["proto", "simcore", "agents", "dev-harness"]
}
```

- [ ] **Step 6: Update the ADR layer section**

In `docs/architecture/adr-skill-evolver-harness.md`, replace the conflicting four-layer block with:

```text
Runtime architecture follows AGENTS.md:
L0: Proto (`proto/`)
L1: SimCore (`simcore/`)
L2: Agents (`agents/`)
L3: Frontend/Godot (`godot/`)

SkillEvolver itself is dev-harness infrastructure. It can read runtime code for diagnosis, but promoted skill patches must target `.agents/skills/` or `harness/` unless a separate harness-executor task is opened for business-code changes.
```

- [ ] **Step 7: Run validation**

Run:

```bash
python3 -m pytest tests/harness/test_skill_evolver.py::TestRegistrySchema::test_layer_enum_values -q
python3 harness/skills/validate_registry.py
```

Expected:

- Layer enum test passes.
- Registry validator may still fail for missing entries until Task 2 is complete.

- [ ] **Step 8: Commit**

Run:

```bash
git add harness/skills/schema.json harness/skills/validate_registry.py harness/skills/registry.json docs/architecture/adr-skill-evolver-harness.md tests/harness/test_skill_evolver.py
git commit -m "fix: align skill evolver layer constraints"
```

---

## Task 2: Register All Local Skills

**Files:**
- Modify: `harness/skills/registry.json`
- Modify: `tests/harness/test_skill_evolver.py`

Use this exact local skill inventory:

```text
architecture-decision
balance-check
brainstorm
code-review
estimate
gate-check
godot-gdextension-specialist
godot-gdscript-specialist
godot-shader-specialist
godot-specialist
harness-run
milestone-review
replay-analyze
scope-check
setup-engine
sprint-plan
team-ai
team-balance
team-release
team-simcore
tech-debt
test-matrix
```

- [ ] **Step 1: Add missing registry entries**

Each entry must have:

```json
{
  "name": "skill-name",
  "description": "one sentence",
  "primary_action": "analyze_or_write_plan",
  "primary_script": null,
  "expected_tool_calls": ["Read", "Grep", "Bash"],
  "validation_commands": ["python3 harness/skills/validate_registry.py"],
  "owner_domain": "cross-cutting",
  "layer_constraints": ["dev-harness"],
  "known_failure_modes": [
    {
      "pattern": "skill rules are followed without validation evidence",
      "mitigation": "trace must include validation_commands_run and primary_action_invoked"
    }
  ],
  "silent_bypass_risks": [
    "SKILL.md is loaded but its declared primary action is not reflected in the trace"
  ],
  "version": "0.1.0",
  "last_evolved": null,
  "held_out_suite": null
}
```

Use the following concrete mapping:

| Skill | owner_domain | primary_action | layer_constraints | validation_commands |
|---|---|---|---|---|
| architecture-decision | cross-cutting | write_architecture_decision | `["dev-harness"]` | `["python3 harness/skills/validate_registry.py"]` |
| balance-check | team-balance | analyze_balance_data | `["simcore", "agents", "dev-harness"]` | `["python3 -m pytest tests/simcore/test_engine.py tests/simcore/test_state.py -q"]` |
| brainstorm | cross-cutting | write_design_options | `["dev-harness"]` | `["python3 harness/skills/validate_registry.py"]` |
| code-review | cross-cutting | review_code | `["proto", "simcore", "agents", "frontend-godot", "dev-harness"]` | `["python3 scripts/lint_deps.py"]` |
| estimate | cross-cutting | estimate_work | `["dev-harness"]` | `["python3 harness/skills/validate_registry.py"]` |
| gate-check | cross-cutting | check_phase_gate | `["dev-harness"]` | `["python3 harness/skills/validate_registry.py", "python3 scripts/lint_deps.py"]` |
| godot-gdextension-specialist | godot-specialist | analyze_native_godot_integration | `["frontend-godot", "dev-harness"]` | `["/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd"]` |
| godot-gdscript-specialist | godot-specialist | edit_gdscript | `["frontend-godot", "dev-harness"]` | `["/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd"]` |
| godot-shader-specialist | godot-specialist | review_shader_or_vfx | `["frontend-godot", "dev-harness"]` | `["/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd", "python3 scripts/verify_presentation_scene.py"]` |
| milestone-review | cross-cutting | review_milestone | `["dev-harness"]` | `["python3 harness/skills/validate_registry.py"]` |
| replay-analyze | team-simcore | analyze_replay | `["simcore", "agents", "dev-harness"]` | `["python3 -m pytest tests/simcore/test_replay_v2.py tests/simcore/test_hash.py -q"]` |
| scope-check | cross-cutting | check_scope | `["dev-harness"]` | `["python3 harness/skills/validate_registry.py"]` |
| setup-engine | godot-specialist | verify_engine_setup | `["frontend-godot", "dev-harness"]` | `["/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd"]` |
| sprint-plan | cross-cutting | write_sprint_plan | `["dev-harness"]` | `["python3 harness/skills/validate_registry.py"]` |
| team-balance | team-balance | coordinate_balance_patch | `["simcore", "agents", "dev-harness"]` | `["python3 -m pytest tests/simcore/test_engine.py tests/agents/test_script_ai.py -q"]` |
| team-release | team-release | coordinate_release_gate | `["proto", "simcore", "agents", "frontend-godot", "dev-harness"]` | `["python3 scripts/lint_deps.py", "python3 -m pytest tests/harness/test_promotion.py -q"]` |
| tech-debt | cross-cutting | analyze_technical_debt | `["proto", "simcore", "agents", "frontend-godot", "dev-harness"]` | `["python3 scripts/lint_deps.py"]` |
| test-matrix | cross-cutting | write_test_matrix | `["simcore", "agents", "dev-harness"]` | `["python3 harness/skills/validate_registry.py"]` |

Keep the existing four entries, but update their layer constraints from Task 1.

- [ ] **Step 2: Give each entry specific failure modes**

For each new entry, include at least two failure modes:

```json
[
  {
    "pattern": "validation command omitted after modifying files",
    "mitigation": "strict trace validation requires validation_commands_run"
  },
  {
    "pattern": "task-specific detail is promoted as a general skill rule",
    "mitigation": "auditor rejects seed, path, entity id, and fixture id leakage"
  }
]
```

For Godot entries, include:

```json
{
  "pattern": "visual fix changes SimCore game rules",
  "mitigation": "Skill patch must target presentation workflow; business-code changes require a separate harness-executor task"
}
```

For SimCore entries, include:

```json
{
  "pattern": "determinism is changed without replay/hash validation",
  "mitigation": "validation_commands must include replay/hash or determinism tests"
}
```

- [ ] **Step 3: Run coverage validation**

Run:

```bash
python3 harness/skills/validate_registry.py
python3 -m pytest tests/harness/test_skill_evolver.py::TestRegistrySchema::test_all_local_skills_registered -q
```

Expected:

- Both commands pass.

- [ ] **Step 4: Commit**

Run:

```bash
git add harness/skills/registry.json tests/harness/test_skill_evolver.py
git commit -m "feat: register all local skills for evolution"
```

---

## Task 3: Upgrade Trace Schema And Strict Validation

**Files:**
- Modify: `harness/trace/schema.py`
- Modify: `harness/trace/validate_traces.py`
- Create: `tests/harness/test_trace_validation.py`

- [ ] **Step 1: Add failing strict validation tests**

Create `tests/harness/test_trace_validation.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from harness.trace.validate_traces import validate_file


def _write_trial(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data) + "\n")


def _base_trial() -> dict:
    return {
        "schema_version": 2,
        "task_id": "trace-001",
        "task_description": "fix godot vfx alignment",
        "skill_name": "godot-specialist",
        "skill_version": "0.1.0",
        "candidate_id": "",
        "agent_run_id": "run-001",
        "task_fixture_id": "godot-vfx/sc1-resource-alignment",
        "baseline_or_candidate": "baseline",
        "strategy_label": "A",
        "outcome": "pass",
        "skill_md_read": True,
        "primary_script_called": False,
        "primary_action_invoked": True,
        "tool_calls": [{"tool": "Read", "args_summary": ".agents/skills/godot-specialist/SKILL.md"}],
        "validation_commands_run": ["python3 scripts/verify_presentation_scene.py"],
        "validation_results": ["pass"],
        "validation_exit_codes": [0],
        "validation_stdout_hashes": ["sha256:abc"],
        "validation_stderr_summaries": [""],
        "functional_verification": "pass",
        "failure_log_summary": "",
        "token_count": 1000,
        "turn_count": 4,
        "duration_seconds": 12.5,
        "touched_files": ["harness/skills/tasks/godot-vfx/sc1-resource-alignment.json"],
        "silent_bypass_detected": False,
        "silent_bypass_details": [],
        "timestamp": "2026-06-08T00:00:00+00:00",
    }


def test_strict_trace_accepts_complete_v2_record(tmp_path):
    path = tmp_path / "trials.jsonl"
    _write_trial(path, _base_trial())
    assert validate_file(path, strict=True) == []


def test_strict_trace_infers_missing_skill_read_as_bypass(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_trial()
    trial["skill_md_read"] = False
    trial["silent_bypass_detected"] = False
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("silent_bypass_inferred" in issue for issue in issues)


def test_strict_trace_infers_missing_validation_as_bypass(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_trial()
    trial["validation_commands_run"] = []
    trial["validation_results"] = []
    trial["silent_bypass_detected"] = False
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("validation_commands_run empty" in issue for issue in issues)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/harness/test_trace_validation.py -q
```

Expected:

- Tests fail before implementation because v2 fields and inference are not enforced.

- [ ] **Step 3: Extend `SkillTrial` with v2 fields**

In `harness/trace/schema.py`, add backward-compatible default fields near the task metadata block:

```python
schema_version: int = 2
skill_version: str = ""
candidate_id: str = ""
agent_run_id: str = ""
task_fixture_id: str = ""
baseline_or_candidate: str = "baseline"
```

Add validation evidence fields near `validation_results`:

```python
validation_exit_codes: list[int] = field(default_factory=list)
validation_stdout_hashes: list[str] = field(default_factory=list)
validation_stderr_summaries: list[str] = field(default_factory=list)
```

Keep all existing fields and defaults so older JSONL records still load.

- [ ] **Step 4: Add strict inference to `validate_traces.py`**

Add this helper:

```python
def infer_silent_bypass(d: dict) -> list[str]:
    details: list[str] = []
    if not d.get("skill_md_read", False):
        details.append("skill_md_read false")
    if not d.get("primary_action_invoked", False):
        details.append("primary_action_invoked false")
    if not d.get("validation_commands_run", []):
        details.append("validation_commands_run empty")
    if d.get("outcome") == "pass" and d.get("functional_verification") == "skip":
        details.append("pass outcome with skipped functional_verification")
    return details
```

In strict mode, add:

```python
            inferred = infer_silent_bypass(d)
            if inferred and not d.get("silent_bypass_detected", False):
                issues.append(
                    f"{path.name}:{line_no}: silent_bypass_inferred but field is false: {inferred}"
                )
```

Extend `REQUIRED_FIELDS` with:

```python
"schema_version",
"skill_version",
"candidate_id",
"agent_run_id",
"task_fixture_id",
"baseline_or_candidate",
"primary_script_called",
"functional_verification",
"failure_log_summary",
"validation_exit_codes",
"validation_stdout_hashes",
"validation_stderr_summaries",
"silent_bypass_details",
```

- [ ] **Step 5: Run tests**

Run:

```bash
python3 -m pytest tests/harness/test_trace_validation.py tests/harness/test_skill_evolver.py -q
python3 harness/trace/validate_traces.py --strict
```

Expected:

- Unit tests pass.
- Existing trace files may fail strict validation if they are old v1 records. If so, add a migration step that treats missing `schema_version` as v1 and reports a clear message without crashing.

- [ ] **Step 6: Commit**

Run:

```bash
git add harness/trace/schema.py harness/trace/validate_traces.py tests/harness/test_trace_validation.py
git commit -m "feat: add strict skill trace v2 validation"
```

---

## Task 4: Add Real Skill Task Fixtures

**Files:**
- Create: `harness/skills/tasks/schema.json`
- Create: `harness/skills/tasks/godot-vfx/sc1-resource-alignment.json`
- Create: `tests/harness/test_strategy_runner.py`

- [ ] **Step 1: Create fixture schema**

Create `harness/skills/tasks/schema.json` with:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Skill Evolver Task Fixture",
  "type": "object",
  "required": [
    "id",
    "skill_name",
    "task_type",
    "description",
    "fresh_agent_strategies",
    "allowed_paths",
    "forbidden_paths",
    "validation_commands",
    "pass_criteria"
  ],
  "properties": {
    "id": {"type": "string"},
    "skill_name": {"type": "string"},
    "task_type": {"type": "string"},
    "description": {"type": "string"},
    "fresh_agent_strategies": {
      "type": "array",
      "minItems": 2,
      "items": {
        "type": "object",
        "required": ["label", "description", "focus_files", "extra_rules"],
        "properties": {
          "label": {"type": "string"},
          "description": {"type": "string"},
          "focus_files": {"type": "array", "items": {"type": "string"}},
          "extra_rules": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "allowed_paths": {"type": "array", "items": {"type": "string"}},
    "forbidden_paths": {"type": "array", "items": {"type": "string"}},
    "validation_commands": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    "pass_criteria": {"type": "array", "items": {"type": "string"}, "minItems": 1}
  }
}
```

- [ ] **Step 2: Create Godot VFX fixture**

Create `harness/skills/tasks/godot-vfx/sc1-resource-alignment.json`:

```json
{
  "id": "godot-vfx/sc1-resource-alignment",
  "skill_name": "godot-specialist",
  "task_type": "godot-vfx",
  "description": "Align SC1-inspired unit/building resource manifest, atlas rectangles, selection rings, health bars, and fallback sprites without changing SimCore rules.",
  "fresh_agent_strategies": [
    {
      "label": "A",
      "description": "Manifest-first audit",
      "focus_files": [
        "godot/resources/presentation_manifest.json",
        "scripts/generate_presentation_manifest.py",
        "scripts/verify_presentation_scene.py"
      ],
      "extra_rules": [
        "Start by validating manifest structure and abstract-to-visual mappings.",
        "Do not edit Godot runtime scripts unless validation proves manifest data cannot express the correction."
      ]
    },
    {
      "label": "B",
      "description": "SpriteLoader atlas audit",
      "focus_files": [
        "godot/scripts/sprite_loader.gd",
        "godot/resources/sprite_frames_config.json",
        "godot/resources/presentation_manifest.json"
      ],
      "extra_rules": [
        "Trace how atlas_rect, pivot, render_scale, and selection_radius flow into rendered sprites.",
        "Check AtlasTexture usage and do not assign flip_h to AtlasTexture."
      ]
    },
    {
      "label": "C",
      "description": "GameView selection and health-bar audit",
      "focus_files": [
        "godot/scripts/game_view.gd",
        "godot/scripts/selection_manager.gd",
        "godot/resources/presentation_manifest.json"
      ],
      "extra_rules": [
        "Check _visual_radius, selection rings, and health bar offsets against manifest values.",
        "Preserve the frontend-only boundary for visual corrections."
      ]
    },
    {
      "label": "D",
      "description": "Regression-verification first",
      "focus_files": [
        "tests/godot/test_presentation_manifest.py",
        "scripts/verify_presentation_scene.py",
        "scripts/verify_godot_fog_smoothing.py"
      ],
      "extra_rules": [
        "Run validation before proposing changes.",
        "Prefer adding a failing validation for any visual mismatch that cannot currently be detected."
      ]
    }
  ],
  "allowed_paths": [
    ".agents/skills/godot-specialist/SKILL.md",
    "harness/skills/tasks/godot-vfx/",
    "harness/skills/candidates/",
    "harness/trace/",
    "tests/harness/",
    "tests/godot/",
    "scripts/verify_presentation_scene.py"
  ],
  "forbidden_paths": [
    "simcore/",
    "agents/",
    "godot/scripts/"
  ],
  "validation_commands": [
    "python3 scripts/verify_presentation_scene.py",
    "python3 -m pytest tests/godot/test_presentation_manifest.py -q",
    "/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd"
  ],
  "pass_criteria": [
    "presentation manifest validates without atlas bounds errors",
    "abstract unit/building mappings resolve to known visuals",
    "Godot check-only succeeds",
    "candidate skill patch does not modify SimCore, Agents, or Godot runtime scripts"
  ]
}
```

- [ ] **Step 3: Add fixture schema tests**

In `tests/harness/test_strategy_runner.py`, add:

```python
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK_SCHEMA = ROOT / "harness/skills/tasks/schema.json"
GODOT_FIXTURE = ROOT / "harness/skills/tasks/godot-vfx/sc1-resource-alignment.json"


def test_godot_vfx_fixture_matches_schema():
    import jsonschema

    schema = json.loads(TASK_SCHEMA.read_text())
    fixture = json.loads(GODOT_FIXTURE.read_text())
    jsonschema.validate(fixture, schema)


def test_godot_vfx_fixture_has_four_unique_strategies():
    fixture = json.loads(GODOT_FIXTURE.read_text())
    labels = [s["label"] for s in fixture["fresh_agent_strategies"]]
    assert labels == ["A", "B", "C", "D"]
    assert len(labels) == len(set(labels))


def test_godot_vfx_fixture_forbids_runtime_business_layers:
    fixture = json.loads(GODOT_FIXTURE.read_text())
    assert "simcore/" in fixture["forbidden_paths"]
    assert "agents/" in fixture["forbidden_paths"]
    assert "godot/scripts/" in fixture["forbidden_paths"]
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m pytest tests/harness/test_strategy_runner.py -q
python3 scripts/verify_presentation_scene.py
```

Expected:

- Fixture schema tests pass.
- Presentation validation may expose existing visual drift. If it fails, keep the fixture and record the failure as evidence; do not fix Godot visuals inside this task.

- [ ] **Step 5: Commit**

Run:

```bash
git add harness/skills/tasks/schema.json harness/skills/tasks/godot-vfx/sc1-resource-alignment.json tests/harness/test_strategy_runner.py
git commit -m "feat: add godot vfx skill task fixture"
```

---

## Task 5: Generate Fresh-Agent Strategy Work Packets

**Files:**
- Create: `harness/evolve/strategy_runner.py`
- Modify: `tests/harness/test_strategy_runner.py`

This task does not need to invoke Hermes directly. It produces deterministic work packets that another agent/model can execute independently.

- [ ] **Step 1: Add tests for strategy packet generation**

Append to `tests/harness/test_strategy_runner.py`:

```python
def test_strategy_runner_writes_packet_per_strategy(tmp_path, monkeypatch):
    from harness.evolve.strategy_runner import generate_strategy_packets

    fixture_path = ROOT / "harness/skills/tasks/godot-vfx/sc1-resource-alignment.json"
    out_dir = tmp_path / "runs"
    manifest = generate_strategy_packets(fixture_path, out_dir=out_dir, run_id="run-test")

    assert manifest["run_id"] == "run-test"
    assert manifest["skill_name"] == "godot-specialist"
    assert len(manifest["packets"]) == 4
    for packet in manifest["packets"]:
        packet_path = out_dir / packet["packet_path"]
        assert packet_path.exists()
        text = packet_path.read_text()
        assert "Read `.agents/skills/godot-specialist/SKILL.md` first" in text
        assert "Record a SkillTrial v2" in text
```

- [ ] **Step 2: Implement `strategy_runner.py`**

Create `harness/evolve/strategy_runner.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "harness/skills/candidates/strategy_runs"


def _load_fixture(fixture_path: Path) -> dict[str, Any]:
    return json.loads(fixture_path.read_text())


def _packet_text(fixture: dict[str, Any], strategy: dict[str, Any]) -> str:
    focus = "\n".join(f"- `{p}`" for p in strategy["focus_files"])
    rules = "\n".join(f"- {r}" for r in strategy["extra_rules"])
    validations = "\n".join(f"- `{cmd}`" for cmd in fixture["validation_commands"])
    forbidden = "\n".join(f"- `{p}`" for p in fixture["forbidden_paths"])
    criteria = "\n".join(f"- {p}" for p in fixture["pass_criteria"])
    skill = fixture["skill_name"]
    return f"""# Strategy {strategy["label"]}: {strategy["description"]}

Task fixture: `{fixture["id"]}`
Skill: `{skill}`

## Required First Action

Read `.agents/skills/{skill}/SKILL.md` first and follow its instructions.

## Task

{fixture["description"]}

## Focus Files

{focus}

## Strategy Rules

{rules}

## Forbidden Runtime Paths

{forbidden}

## Validation Commands

{validations}

## Pass Criteria

{criteria}

## Trace Requirement

Record a SkillTrial v2 with:
- `skill_name`: `{skill}`
- `task_fixture_id`: `{fixture["id"]}`
- `strategy_label`: `{strategy["label"]}`
- `skill_md_read`: true only if the SKILL.md was actually read
- `primary_action_invoked`: true only if the declared primary action was actually invoked
- `validation_commands_run`: the exact validation commands run
- `validation_exit_codes`: command exit codes in the same order
- `baseline_or_candidate`: `baseline`
"""


def generate_strategy_packets(
    fixture_path: Path,
    out_dir: Path = DEFAULT_OUT_DIR,
    run_id: str | None = None,
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path)
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    packets: list[dict[str, str]] = []
    for strategy in fixture["fresh_agent_strategies"]:
        rel = Path(run_id) / f"strategy-{strategy['label']}.md"
        packet_path = out_dir / rel
        packet_path.write_text(_packet_text(fixture, strategy))
        packets.append({
            "strategy_label": strategy["label"],
            "packet_path": str(rel),
        })

    manifest = {
        "run_id": run_id,
        "fixture_id": fixture["id"],
        "skill_name": fixture["skill_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "packets": packets,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate fresh-agent strategy packets")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    manifest = generate_strategy_packets(args.fixture, args.out_dir, args.run_id)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests and generate a real run packet**

Run:

```bash
python3 -m pytest tests/harness/test_strategy_runner.py -q
python3 -m harness.evolve.strategy_runner harness/skills/tasks/godot-vfx/sc1-resource-alignment.json --run-id godot-vfx-manual-001
```

Expected:

- Tests pass.
- `harness/skills/candidates/strategy_runs/godot-vfx-manual-001/strategy-A.md` through `strategy-D.md` exist.
- `run_manifest.json` exists.

- [ ] **Step 4: Commit**

Run:

```bash
git add harness/evolve/strategy_runner.py tests/harness/test_strategy_runner.py harness/skills/candidates/strategy_runs/godot-vfx-manual-001
git commit -m "feat: generate skill strategy work packets"
```

If candidate run outputs are ignored by `.gitignore`, do not force-add them. Commit the runner and tests only.

---

## Task 6: Strengthen Godot Held-Out Validation

**Files:**
- Modify: `harness/skills/held_out/godot-specialist/suite.json`
- Modify: `tests/harness/test_skill_evolver.py`

- [ ] **Step 1: Replace weak held-out commands**

Update `harness/skills/held_out/godot-specialist/suite.json` so each scenario runs at least one real validation command.

Use these scenarios:

```json
{
  "suite": "godot-specialist-held-out",
  "version": "0.2.0",
  "scenarios": [
    {
      "id": "godot-vfx-001",
      "type": "vfx_alignment",
      "description": "presentation manifest resolves abstract units/buildings and atlas rects are within PNG bounds",
      "skill": "godot-specialist",
      "validation_commands": [
        "python3 scripts/verify_presentation_scene.py",
        "python3 -m pytest tests/godot/test_presentation_manifest.py -q"
      ],
      "pass_criteria": "manifest valid, atlas in bounds, abstract mappings resolve, no hardcoded drift"
    },
    {
      "id": "godot-fog-002",
      "type": "fog_rendering",
      "description": "Godot fog smoothing hides raw 2->1 visual flicker without changing SimCore fog rules",
      "skill": "godot-specialist",
      "validation_commands": [
        "python3 scripts/verify_godot_fog_smoothing.py",
        "python3 -m pytest tests/simcore/test_fog.py -q"
      ],
      "pass_criteria": "rendered alpha does not spike on raw fog downgrade and SimCore fog tests pass"
    },
    {
      "id": "godot-check-003",
      "type": "gdscript_static_check",
      "description": "Godot frontend scripts pass check-only after presentation changes",
      "skill": "godot-specialist",
      "validation_commands": [
        "/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd",
        "/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/minimap_rect.gd"
      ],
      "pass_criteria": "Godot check-only exits 0"
    }
  ]
}
```

- [ ] **Step 2: Add held-out command quality regression**

In `tests/harness/test_skill_evolver.py`, add:

```python
def test_godot_held_out_uses_real_validation_commands():
    suite = json.loads((HELD_OUT_DIR / "godot-specialist" / "suite.json").read_text())
    commands = [
        cmd
        for scenario in suite["scenarios"]
        for cmd in scenario["validation_commands"]
    ]
    assert any("verify_presentation_scene.py" in cmd for cmd in commands)
    assert any("verify_godot_fog_smoothing.py" in cmd for cmd in commands)
    assert any("--check-only" in cmd for cmd in commands)
    assert all("|| true" not in cmd for cmd in commands)
```

- [ ] **Step 3: Run held-out validation**

Run:

```bash
python3 -m pytest tests/harness/test_skill_evolver.py::test_godot_held_out_uses_real_validation_commands -q
python3 scripts/verify_presentation_scene.py
python3 scripts/verify_godot_fog_smoothing.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd
```

Expected:

- The new regression passes.
- If `verify_presentation_scene.py` fails due to current known Godot presentation drift, keep the held-out suite strict and record the failure. Do not weaken the command.

- [ ] **Step 4: Commit**

Run:

```bash
git add harness/skills/held_out/godot-specialist/suite.json tests/harness/test_skill_evolver.py
git commit -m "test: strengthen godot skill held-out validation"
```

---

## Task 7: Add Independent Structured Auditor

**Files:**
- Create: `harness/evolve/auditor.py`
- Create: `tests/harness/test_skill_auditor.py`
- Modify: `harness/evolve/skill_evolver.py`

- [ ] **Step 1: Add auditor tests**

Create `tests/harness/test_skill_auditor.py`:

```python
from __future__ import annotations

from harness.evolve.auditor import audit_candidate_patch


def test_auditor_rejects_runtime_business_code_target():
    result = audit_candidate_patch(
        skill_name="godot-specialist",
        patch_content="Add a rule: edit simcore/rules.py to make fog stable.",
        skill_md_content="primary_action: write_file\nvalidation_commands: [python3 scripts/verify_presentation_scene.py]",
        evidence={"touched_files": ["simcore/rules.py"]},
    )
    assert not result.accepted
    assert "runtime_business_code_target" in result.issues


def test_auditor_rejects_training_fixture_leak():
    result = audit_candidate_patch(
        skill_name="godot-specialist",
        patch_content="Always fix godot-vfx/sc1-resource-alignment by changing CommandCenter atlas_rect to [205,190,145,95].",
        skill_md_content="primary_action: write_file\nvalidation_commands: [python3 scripts/verify_presentation_scene.py]",
        evidence={"task_fixture_id": "godot-vfx/sc1-resource-alignment"},
    )
    assert not result.accepted
    assert "fixture_specific_rule" in result.issues


def test_auditor_accepts_general_validation_rule():
    result = audit_candidate_patch(
        skill_name="godot-specialist",
        patch_content="For Godot VFX tasks, run presentation manifest validation before changing runtime scripts and record atlas/fallback failures as evidence.",
        skill_md_content="primary_action: write_file\nvalidation_commands: [python3 scripts/verify_presentation_scene.py]",
        evidence={"touched_files": [".agents/skills/godot-specialist/SKILL.md"]},
    )
    assert result.accepted
```

- [ ] **Step 2: Implement `auditor.py`**

Create `harness/evolve/auditor.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


RUNTIME_BUSINESS_PREFIXES = ("simcore/", "agents/", "godot/scripts/")


@dataclass
class StructuredAuditResult:
    accepted: bool
    issues: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def audit_candidate_patch(
    skill_name: str,
    patch_content: str,
    skill_md_content: str,
    evidence: dict[str, Any] | None = None,
) -> StructuredAuditResult:
    evidence = evidence or {}
    issues: list[str] = []
    patch_lower = patch_content.lower()
    skill_lower = skill_md_content.lower()

    touched_files = evidence.get("touched_files", [])
    if any(str(path).startswith(RUNTIME_BUSINESS_PREFIXES) for path in touched_files):
        issues.append("runtime_business_code_target")

    if any(prefix in patch_content for prefix in RUNTIME_BUSINESS_PREFIXES):
        issues.append("runtime_business_code_instruction")

    if re.search(r"seed\s*[=:]\s*\d+", patch_lower):
        issues.append("hardcoded_seed")

    if re.search(r"entity_[a-z]+_\d+", patch_lower):
        issues.append("hardcoded_entity_id")

    task_fixture_id = str(evidence.get("task_fixture_id", ""))
    if task_fixture_id and task_fixture_id.lower() in patch_lower:
        issues.append("fixture_specific_rule")

    if "always" in patch_lower or "must" in patch_lower or "必须" in patch_content:
        if "validation_commands" not in skill_lower and "expected_tool_calls" not in skill_lower:
            issues.append("unsupported_must_without_validation_evidence")

    if "simcore" in skill_name and ("llm" in patch_lower or "chat.completions" in patch_lower):
        issues.append("llm_in_simcore_loop")

    if "godot" in skill_name and "check-only" not in patch_lower and "verify_presentation_scene.py" not in patch_lower:
        issues.append("godot_patch_missing_static_or_manifest_validation")

    return StructuredAuditResult(
        accepted=not issues,
        issues=issues,
        evidence=evidence,
    )
```

- [ ] **Step 3: Wire `skill_evolver.py` to use `auditor.py`**

In `harness/evolve/skill_evolver.py`, import:

```python
from harness.evolve.auditor import audit_candidate_patch
```

Inside `audit_patch`, after current checks or as a replacement layer, call:

```python
    structured = audit_candidate_patch(
        skill_name=patch.skill_name,
        patch_content=patch.patch_content,
        skill_md_content=skill_md_content,
        evidence={
            "evidence_pass": patch.evidence_pass,
            "evidence_fail": patch.evidence_fail,
        },
    )
    issues.extend(structured.issues)
```

Keep the existing `AuditResult` return type to avoid breaking callers.

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m pytest tests/harness/test_skill_auditor.py tests/harness/test_skill_evolver.py -q
```

Expected:

- Auditor tests pass.
- Existing SkillEvolver tests pass or are updated only where the stricter auditor intentionally rejects unsafe patches.

- [ ] **Step 5: Commit**

Run:

```bash
git add harness/evolve/auditor.py harness/evolve/skill_evolver.py tests/harness/test_skill_auditor.py
git commit -m "feat: add structured skill patch auditor"
```

---

## Task 8: Improve Contrastive Trace Analysis

**Files:**
- Modify: `harness/evolve/skill_evolver.py`
- Modify: `tests/harness/test_skill_evolver.py`

Current contrast only reacts to silent-bypass, unread skill, and missing primary action. Add comparison of validation commands, tool calls, and touched files.

- [ ] **Step 1: Add failing contrast test**

In `tests/harness/test_skill_evolver.py`, add a test using monkeypatched `load_trials`:

```python
def test_contrast_detects_missing_validation_command(monkeypatch):
    from harness.evolve import skill_evolver as mod
    from harness.trace.schema import SkillTrial

    pass_trial = SkillTrial(
        task_id="pass-1",
        task_description="godot vfx",
        skill_name="godot-specialist",
        outcome="pass",
        skill_md_read=True,
        primary_action_invoked=True,
        validation_commands_run=["python3 scripts/verify_presentation_scene.py"],
        validation_results=["pass"],
        touched_files=["godot/resources/presentation_manifest.json"],
    )
    fail_trial = SkillTrial(
        task_id="fail-1",
        task_description="godot vfx",
        skill_name="godot-specialist",
        outcome="fail",
        skill_md_read=True,
        primary_action_invoked=True,
        validation_commands_run=[],
        validation_results=[],
        touched_files=["godot/scripts/game_view.gd"],
    )

    def fake_load_trials(skill_name=None, outcome=None):
        return {"pass": [pass_trial], "fail": [fail_trial]}[outcome]

    monkeypatch.setattr(mod, "load_trials", fake_load_trials)
    patches = mod.contrast_trials("godot-specialist")
    assert any("verify_presentation_scene.py" in p.patch_content for p in patches)
```

- [ ] **Step 2: Implement command-delta analysis**

In `contrast_trials`, after current failure classes:

```python
    pass_commands = {
        cmd
        for trial in pass_trials
        for cmd in trial.validation_commands_run
    }
    fail_commands = {
        cmd
        for trial in fail_trials
        for cmd in trial.validation_commands_run
    }
    missing_commands = sorted(pass_commands - fail_commands)
    if missing_commands:
        patches.append(SkillPatch(
            skill_name=skill_name,
            timestamp=ts,
            patch_content=(
                "## Validation Delta 修复\n\n"
                "成功轨迹运行了失败轨迹缺失的验证命令。"
                "将这些命令加入该 skill 的 validation workflow：\n"
                + "\n".join(f"- `{cmd}`" for cmd in missing_commands[:5])
            ),
            rationale="contrastive validation delta: pass traces include commands absent from fail traces",
            evidence_pass=[t.task_id for t in pass_trials[:5]],
            evidence_fail=[t.task_id for t in fail_trials[:5]],
        ))
```

- [ ] **Step 3: Implement runtime-path risk analysis**

Still in `contrast_trials`, add:

```python
    risky_prefixes = ("simcore/", "agents/", "godot/scripts/")
    risky_fail_files = sorted({
        path
        for trial in fail_trials
        for path in trial.touched_files
        if path.startswith(risky_prefixes)
    })
    if risky_fail_files and "godot" in skill_name:
        patches.append(SkillPatch(
            skill_name=skill_name,
            timestamp=ts,
            patch_content=(
                "## Runtime Boundary 修复\n\n"
                "Godot skill 的失败轨迹触碰了 runtime business paths。"
                "后续 Godot VFX/resource alignment 任务必须先尝试 manifest、asset、test/harness 层修复；"
                "业务代码变更必须拆成单独 harness-executor 任务。\n"
                + "\n".join(f"- observed: `{path}`" for path in risky_fail_files[:5])
            ),
            rationale="contrastive boundary risk: failed traces touched forbidden runtime paths",
            evidence_pass=[t.task_id for t in pass_trials[:5]],
            evidence_fail=[t.task_id for t in fail_trials[:5]],
        ))
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m pytest tests/harness/test_skill_evolver.py -q
```

Expected:

- New contrast test passes.
- Existing auditor tests may reject patches with runtime paths. If so, adjust the patch wording to describe the boundary without instructing direct runtime edits.

- [ ] **Step 5: Commit**

Run:

```bash
git add harness/evolve/skill_evolver.py tests/harness/test_skill_evolver.py
git commit -m "feat: compare validation deltas in skill evolution"
```

---

## Task 9: End-To-End Godot VFX Dry Run

**Files:**
- Read: `harness/skills/tasks/godot-vfx/sc1-resource-alignment.json`
- Read: `harness/skills/candidates/strategy_runs/`
- Read: `harness/trace/trials/`
- Modify only if required by earlier tests: `harness/evolve/skill_evolver.py`

- [ ] **Step 1: Generate strategy packets**

Run:

```bash
python3 -m harness.evolve.strategy_runner harness/skills/tasks/godot-vfx/sc1-resource-alignment.json --run-id godot-vfx-e2e-001
```

Expected:

- Four strategy packet markdown files are generated.
- `run_manifest.json` lists strategies A-D.

- [ ] **Step 2: Execute at least one packet manually or through Hermes**

For a manual dry-run, use Strategy A packet:

```bash
sed -n '1,220p' harness/skills/candidates/strategy_runs/godot-vfx-e2e-001/strategy-A.md
```

The executing agent should:

- Read `.agents/skills/godot-specialist/SKILL.md`.
- Run `python3 scripts/verify_presentation_scene.py`.
- Run `python3 -m pytest tests/godot/test_presentation_manifest.py -q`.
- Run Godot check-only if Godot is available.
- Record a v2 `SkillTrial` through `task_state.py complete` or a direct `record_trial()` helper.

- [ ] **Step 3: Record a synthetic fail/pass pair if no Hermes runner is available**

If the environment cannot dispatch fresh Hermes agents, create two controlled local traces using `python3 -c` so `contrast_trials` can be exercised:

```bash
python3 -c "from harness.trace.schema import SkillTrial, record_trial; record_trial(SkillTrial(task_id='godot-vfx-pass-001', task_description='godot vfx fixture pass', skill_name='godot-specialist', skill_version='0.1.0', task_fixture_id='godot-vfx/sc1-resource-alignment', baseline_or_candidate='baseline', strategy_label='A', outcome='pass', skill_md_read=True, primary_action_invoked=True, validation_commands_run=['python3 scripts/verify_presentation_scene.py'], validation_results=['pass'], validation_exit_codes=[0], functional_verification='pass', touched_files=['godot/resources/presentation_manifest.json']))"
python3 -c "from harness.trace.schema import SkillTrial, record_trial; record_trial(SkillTrial(task_id='godot-vfx-fail-001', task_description='godot vfx fixture fail', skill_name='godot-specialist', skill_version='0.1.0', task_fixture_id='godot-vfx/sc1-resource-alignment', baseline_or_candidate='baseline', strategy_label='B', outcome='fail', skill_md_read=True, primary_action_invoked=True, validation_commands_run=[], validation_results=[], validation_exit_codes=[], functional_verification='fail', failure_log_summary='manifest validation omitted', touched_files=['godot/scripts/game_view.gd']))"
```

- [ ] **Step 4: Run SkillEvolver dry-run**

Run:

```bash
python3 -m harness.evolve.skill_evolver godot-specialist
```

Expected:

- It runs in dry-run mode.
- It writes candidate patch artifacts under `harness/skills/candidates/`.
- It does not modify `.agents/skills/godot-specialist/SKILL.md`.
- It does not update `harness/skills/registry.json`.

- [ ] **Step 5: Validate final state**

Run:

```bash
python3 harness/skills/validate_registry.py
python3 harness/trace/validate_traces.py --strict
python3 -m pytest tests/harness/test_skill_evolver.py tests/harness/test_trace_validation.py tests/harness/test_strategy_runner.py tests/harness/test_skill_auditor.py -q
python3 scripts/lint_deps.py
```

Expected:

- All commands pass, except trace strict validation may report intentionally synthetic failing traces if they were recorded with missing validation. In that case, record this as expected evidence and remove synthetic traces from committed files if they are not ignored.

- [ ] **Step 6: Commit**

Run:

```bash
git add harness/evolve harness/skills harness/trace tests/harness docs/architecture
git commit -m "feat: run godot vfx skill evolution dry run"
```

Do not force-add ignored runtime candidate outputs unless the project owner explicitly wants them versioned.

---

## Task 10: Final Gate And Report

**Files:**
- Modify: `docs/plans/skill-evolver-p0-changes.md` if it needs an addendum.
- Create or modify: `docs/plans/skill-evolver-paper-alignment-report.md`

- [ ] **Step 1: Run final gate commands**

Run:

```bash
python3 harness/skills/validate_registry.py
python3 harness/trace/validate_traces.py --strict
python3 -m pytest tests/harness/test_skill_evolver.py tests/harness/test_trace_validation.py tests/harness/test_strategy_runner.py tests/harness/test_skill_auditor.py -q
python3 scripts/lint_deps.py
python3 scripts/verify_presentation_scene.py
python3 scripts/verify_godot_fog_smoothing.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd
```

Expected:

- Harness tests pass.
- Registry validates all local skills.
- Trace validation either passes or clearly reports only intentionally retained fail-trace evidence.
- Godot validation commands are strict and not swallowed by `|| true`.

- [ ] **Step 2: Write final report**

Create `docs/plans/skill-evolver-paper-alignment-report.md` with:

```markdown
# SkillEvolver Paper Alignment Report

## Summary

SkillEvolver has been upgraded from a P0 scaffold to a Godot VFX dry-run evolution loop with complete registry coverage, strict trace validation, task fixtures, strategy packet generation, structured auditing, and stronger held-out validation.

## Implemented

- Layer constraints aligned with AGENTS.md.
- All local `.agents/skills/*/SKILL.md` entries registered.
- SkillTrial v2 fields added.
- Strict trace validation infers silent-bypass.
- Godot VFX task fixture added.
- Fresh-agent strategy packets generated for four Godot VFX strategies.
- Structured auditor added.
- Contrastive validation delta analysis added.
- Godot held-out suite now uses real validation commands.

## Remaining Risks

- Strategy packets still require an external Hermes/Codex runner for true fresh-agent execution.
- Screenshot-based visual regression is not yet automated.
- Candidate promotion remains manual and should stay manual until held-out suites cover at least Godot, SimCore replay, and Team-AI playbooks.

## Final Commands

Record each final gate command, exit code, and the last 20 lines of output. If a command fails because of an already-known project issue, include the failing command, exact error summary, and the linked task or file that explains why it is not fixed in this iteration.
```

- [ ] **Step 3: Commit final report**

Run:

```bash
git add docs/plans/skill-evolver-paper-alignment-report.md
git commit -m "docs: report skill evolver paper alignment status"
```

---

## Quality Gates

The whole iteration is complete only when these pass or have a documented reason for failure:

```bash
python3 harness/skills/validate_registry.py
python3 harness/trace/validate_traces.py --strict
python3 -m pytest tests/harness/test_skill_evolver.py tests/harness/test_trace_validation.py tests/harness/test_strategy_runner.py tests/harness/test_skill_auditor.py -q
python3 scripts/lint_deps.py
python3 scripts/verify_presentation_scene.py
python3 scripts/verify_godot_fog_smoothing.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd
```

## Non-Goals

- Do not train or fine-tune a model.
- Do not push `.agents/skills` into runtime RTS tick decisions.
- Do not directly patch `simcore/`, `agents/`, or `godot/scripts/` as a SkillEvolver promotion side effect.
- Do not weaken held-out commands to make them pass.
- Do not commit extracted StarCraft assets or proprietary game files.

## Recommended Execution Order

1. Task 0 baseline.
2. Task 1 architecture layer alignment.
3. Task 2 full registry coverage.
4. Task 3 trace v2 strict validation.
5. Task 4 Godot VFX task fixture.
6. Task 5 strategy packet generator.
7. Task 6 stronger Godot held-out suite.
8. Task 7 independent auditor.
9. Task 8 contrastive validation delta.
10. Task 9 Godot VFX dry-run.
11. Task 10 final gate and report.

## Success Criteria

- SkillEvolver remains safely scoped to dev-harness artifacts.
- The next agent can generate and execute Godot VFX strategy packets.
- The resulting traces are strict enough to detect silent-bypass.
- Candidate patches are blocked if they contain runtime code edits, fixture leakage, hardcoded seed/entity IDs, or missing validation evidence.
- Godot VFX/resource alignment becomes the first repeatable research workflow for testing the paper's method in this RTS project.
