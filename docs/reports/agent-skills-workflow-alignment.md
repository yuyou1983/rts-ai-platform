# Agent Skills Workflow Alignment Report

## Baseline (2026-08-04)
- Branch: main
- HEAD: 1203b28
- Local skills: 22
- Registry entries: 22
- Skills with held-out suites: 4
- Skills with non-null last_evolved: 1
- Registry validator: PASS
- Focused Harness tests: 42 PASS

## Gate Status

| Gate | Initial status | Final status | Evidence |
|---|---|---|---|
| A0 Source pin | PASS | PASS | external commit and license recorded |
| A1 Registry semantics | PASS | PASS | schema requires invocation_mode/skill_kind/completion_criteria + composes (pattern, uniqueItems); 22/22 entries migrated with completion_criteria; composition graph acyclic; validate_composition wired into validator; tests/harness/test_skill_registry_semantics.py green |
| A2 Domain language | PASS | PASS | CONTEXT-MAP.md references all four bounded-context glossaries; required terms present and unambiguous; domain-modeling skill registered; brainstorm.composes=["domain-modeling"]; test_domain_contexts.py green |
| A3 Review workflow | FAIL | PASS | code-review upgraded to v0.2.0 with three independent axes (Standards, Specification, Source Truth); fixed-point diff (git diff <fixed-point>...HEAD) pins scope; verdicts kept separate per axis; contract tests (tests/harness/test_code_review_skill_contract.py) green; combat-remediation-review fixture created |
| A4 Vertical execution | FAIL | PASS | task schema gained vertical ticket fields (source_spec, blocked_by, acceptance_criteria, verification_seams, evidence_outputs, status) with status enum {blocked, ready, in_progress, verification, done}; harness/skills/validate_tasks.py enforces schema, blocker existence, blocked_by acyclicity, ready-requires-done, source_spec on disk, and no fixture forbidding the task graph; both fixtures (godot-vfx/sc1-resource-alignment, code-review/combat-remediation-review) carry the full vertical ticket; strategy_runner.py renders Source Specification / Blocked By / Acceptance Criteria / Verification Seams / Evidence Outputs / Stop Condition sections before Validation Commands; tests/harness/test_task_graph.py green |
| A5 Handoff | FAIL | FAIL | no structured handoff skill |
| A6 Candidate held-out | FAIL | FAIL | candidate patch is not executed during held-out |
| A7 Coverage | FAIL | FAIL | 4/22 skills have held-out suites |
| A8 Fresh-agent proof | BLOCKED | BLOCKED | no alignment pilot trials yet |

## A3 Review Workflow — Detail

The code-review skill was upgraded from a single-axis quality checklist to a
three-axis specification-aware review:

- **Standards Axis** — dependency direction, layer boundaries, hot-path
  discipline, local conventions. Verdict: PASS | CONCERNS | FAIL.
- **Specification Axis** — per-criterion classification
  (missing/partial/incorrect/out-of-scope) plus specification-drift detection
  (report status disagreeing with diff reality). Verdict: PASS | CONCERNS | FAIL | NOT AVAILABLE.
- **Source Truth Axis** — runs only when the originating plan declares external
  authority (SC1 DAT/OpenBW, protobuf contract, replay hash, generated fixture).
  Verdict: PASS | CONCERNS | FAIL | NOT APPLICABLE.

Axes produce independent verdicts; they are never merged into one composite
score. A combat-remediation-review fixture
(`harness/skills/tasks/code-review/combat-remediation-review.json`) pins the
fixed-point to `e201355` and target `2dbcf66`, forbids runtime layer changes
(simcore/, agents/, godot/scripts/, proto/), and requires the Specification axis
to detect the known QA status drift.

## A4 Vertical Execution — Detail

Task fixtures were upgraded from flat strategy-evolution blobs to **vertical
tickets**: each fixture is a self-contained ticket that declares its own source
specification, dependency graph, acceptance criteria, verification seams,
evidence outputs, and lifecycle status.

- **Schema** (`harness/skills/tasks/schema.json`) now requires `id`, `name`,
  `description`, `source_spec`, `blocked_by`, `acceptance_criteria`,
  `verification_seams`, `evidence_outputs`, `status`, and `forbidden_paths`.
  `status` is an enum of `{blocked, ready, in_progress, verification, done}`.
  `acceptance_criteria`, `verification_seams`, and `evidence_outputs` require
  `minItems: 1` so completion is always machine-checkable. Legacy
  strategy-evolution fields (`skill_name`, `fresh_agent_strategies`,
  `validation_commands`, `pass_criteria`, …) remain accepted as optional
  properties for backward compatibility.
- **Validator** (`harness/skills/validate_tasks.py`) loads every `*.json` under
  `harness/skills/tasks` (excluding `schema.json`), validates each against the
  schema with `jsonschema`, and enforces cross-fixture graph invariants the
  schema cannot express: blocker references must resolve to a known fixture id,
  the `blocked_by` graph must be acyclic (DFS), a `ready` ticket may only depend
  on `done` blockers, `source_spec` must be a repository-relative path that
  exists on disk, and no fixture may list the task-graph directory
  (`harness/skills/tasks`) in its own `forbidden_paths`.
- **Fixtures** — `godot-vfx/sc1-resource-alignment` and
  `code-review/combat-remediation-review` both carry the full vertical ticket.
  Both are currently ungated (`blocked_by: []`, `status: "ready"`).
- **Strategy packets** (`harness/evolve/strategy_runner.py`) now render six new
  sections before `## Validation Commands`: Source Specification, Blocked By,
  Acceptance Criteria, Verification Seams, Evidence Outputs, and a Stop
  Condition that pins the agent to the current fixture and halts after evidence
  is recorded.

## Known State Drift
- Commit 2dbcf66 completes combat Tasks 8-9 but docs/reports/sc1-combat-differentiation-remediation-qa.md previously reported those tasks as partial (now fixed in 1203b28).
