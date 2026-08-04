# Agent Skills Workflow Alignment Report

## Baseline (2026-08-04)
- Branch: main
- HEAD: 4f7a275
- Local skills: 24
- Registry entries: 24
- Skills with held-out suites: 4
- Skills with non-null last_evolved: 2
- Registry validator: PASS
- Focused Harness tests: 54 PASS

## Gate Status

| Gate | Initial status | Final status | Evidence |
|---|---|---|---|
| A0 Source pin | PASS | PASS | external commit and license recorded |
| A1 Registry semantics | PASS | PASS | schema requires invocation_mode/skill_kind/completion_criteria + composes (pattern, uniqueItems); 24/24 entries migrated with completion_criteria; composition graph acyclic; validate_composition wired into validator; tests/harness/test_skill_registry_semantics.py green |
| A2 Domain language | PASS | PASS | CONTEXT-MAP.md references all four bounded-context glossaries; required terms present and unambiguous; domain-modeling skill registered; brainstorm.composes=["domain-modeling"]; test_domain_contexts.py green |
| A3 Review workflow | FAIL | PASS | code-review upgraded to v0.2.0 with three independent axes (Standards, Specification, Source Truth); fixed-point diff (git diff <fixed-point>...HEAD) pins scope; verdicts kept separate per axis; contract tests (tests/harness/test_code_review_skill_contract.py) green; combat-remediation-review fixture created |
| A4 Vertical execution | FAIL | PASS | task schema gained vertical ticket fields (source_spec, blocked_by, acceptance_criteria, verification_seams, evidence_outputs, status) with status enum {blocked, ready, in_progress, verification, done}; harness/skills/validate_tasks.py enforces schema, blocker existence, blocked_by acyclicity, ready-requires-done, source_spec on disk, and no fixture forbidding the task graph; both fixtures (godot-vfx/sc1-resource-alignment, code-review/combat-remediation-review) carry the full vertical ticket; strategy_runner.py renders Source Specification / Blocked By / Acceptance Criteria / Verification Seams / Evidence Outputs / Stop Condition sections before Validation Commands; tests/harness/test_task_graph.py green; sprint-plan SKILL.md (v0.2.0) mandates vertical-slice tickets (Status/Blocked by/Source specification/What it delivers/Acceptance criteria/Verification seams/Evidence outputs/Owner skill) and forbids per-layer decomposition; harness-run SKILL.md (v0.2.0) defines the tight red-capable feedback loop (read spec → reproduce → minimise → one hypothesis at a time → regression test → smallest fix → targeted+arch+full tests → code-review → evidence+status in one commit) with structured handoff and repository-only output locations (harness/output/, docs/reports/); hardcoded S3/MLflow/fabricated run IDs removed; tests/harness/test_execution_skill_contracts.py green |
| A5 Handoff | FAIL | PASS | structured handoff skill registered (skill 24); SKILL.md at .agents/skills/handoff/ mandates one active task, one next command, temp-directory output (rts-agent-handoff-<task-id>.md), credential redaction, and rejects Conversation Dump headings; fill-in template at docs/agents/templates/agent-handoff-template.md covers all ten required sections; contract tests (tests/harness/test_handoff_skill_contract.py) green |
| A6 Candidate held-out | FAIL | PASS | HeldOutResult dataclass with promotion_eligible field; validate_held_out_candidate() requires candidate_id + agent_run_id; promote_patch takes HeldOutResult; candidate overlay; strict trace validation; 8+45 tests pass |
| A7 Coverage | FAIL | PASS | 12/24 skills with behavioral held-out suites; 8 new suites created; validate_held_out_suites.py + 10 coverage tests pass |
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

## A4 Vertical Execution — Planning & Harness Alignment

The vertical ticket schema is only useful if the skills that *produce* and
*consume* tickets speak the same vocabulary. This step aligned the two
end-to-end skills:

- **sprint-plan** (`v0.1.0` → `v0.2.0`) now plans sprints as **vertical slice**
  tickets. Each ticket block carries `Status`, `Blocked by`, `Source
  specification`, `What it delivers`, `Acceptance criteria`, `Verification
  seams`, `Evidence outputs`, and `Owner skill`. The skill explicitly forbids
  decomposing a ticket into one ticket per architectural layer: *"A ticket may
  cross Proto, SimCore, gRPC, and Godot when that is the narrowest
  independently demonstrable path."* The `blocked_by` graph must be acyclic and
  a `ready` ticket may only depend on `done` tickets — the same invariants the
  task validator enforces on fixtures.

- **harness-run** (`v0.1.0` → `v0.2.0`) now executes each ticket through a
  **tight red-capable feedback loop** in fixed order: (1) read source
  specification, domain context, ADR, and fixture; (2) build one fast
  deterministic red-capable command; (3) reproduce and minimise; (4) record
  3-5 falsifiable hypotheses; (5) test one hypothesis at a time; (6) convert
  the minimal reproducer into a regression test at the highest stable seam;
  (7) implement the smallest fix; (8) run targeted → architecture → full
  tests; (9) run code-review against the fixture source specification;
  (10) update evidence and task status in the same commit. The skill mandates
  a structured **handoff** (restating ticket ID, red-capable command, ruled-out
  hypotheses, receiving owner skill) when a ticket cannot be completed alone.
  Hardcoded S3 URIs, MLflow experiment numbers, fabricated run IDs, and the
  synthetic progress table were removed; all evidence now references
  repository-relative paths (`harness/output/`, `docs/reports/`,
  `production/sprints/`).

- **Contract tests** (`tests/harness/test_execution_skill_contracts.py`) pin
  both skills: `TestSprintPlanContract` asserts the vertical-slice ticket
  format and required fields; `TestHarnessRunContract` asserts the red-capable
  loop, minimise, one-hypothesis-at-a-time, regression, handoff, and execution
  order. 13 tests, all green.

## A5 Handoff — Detail

The structured agent handoff skill (skill 24, `handoff`) provides a disciplined
way to transfer context between agents without pasting raw conversation
history. It is registered as a `discipline` skill with `invocation_mode: user`
and `owner_domain: cross-cutting`.

- **SKILL.md** (`.agents/skills/handoff/SKILL.md`) mandates that the handoff
  be written to the OS temporary directory as
  `rts-agent-handoff-<task-id>.md`, never inside the repository working tree.
  The skill enforces exactly one active task and one next command per handoff.
  It rejects any heading named "Conversation Dump" (or "Chat Log",
  "Transcript") — conversation dumps are forbidden. Before writing, the agent
  must scan for and redact API keys, tokens, passwords, and other credential
  material. Proprietary asset paths outside the repository must not be copied
  into the handoff. Plans, reports, diffs, and fixtures are referenced by
  repository-relative path, never inlined.

- **Template** (`docs/agents/templates/agent-handoff-template.md`) provides a
  fill-in skeleton with all ten required sections: Objective, Fixed Point,
  Active Task Fixture, Gate Status, Completed Evidence, Current Failure,
  Unrelated Working Tree Paths, Next Command, Suggested Skills, and Stop
  Conditions. The template uses placeholders (`<task-id>`, `<commit-sha>`,
  `<path>`) and references existing artifacts by path rather than duplicating
  their contents.

- **Registry entry** (`harness/skills/registry.json`, skill 24) declares
  `expected_tool_calls: [Read, Write, Bash]`, `validation_commands` pointing
  to the contract test suite, and two `known_failure_modes`: conversation-dump
  substitution and credential leakage.

- **Contract tests** (`tests/harness/test_handoff_skill_contract.py`) — 12
  tests pinning file existence, all ten required sections in both SKILL.md and
  the template, conversation-dump rejection, credential mention, temp-directory
  usage, one-active-task constraint, one-next-command constraint, path-based
  references in the template, registry registration, and the 24-skill count.

## Known State Drift
- Commit 2dbcf66 completes combat Tasks 8-9 but docs/reports/sc1-combat-differentiation-remediation-qa.md previously reported those tasks as partial (now fixed in 1203b28).
