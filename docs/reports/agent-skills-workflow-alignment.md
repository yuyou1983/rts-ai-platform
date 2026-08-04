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
| A4 Vertical execution | FAIL | FAIL | task schema has no blockers or verification seams |
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

## Known State Drift
- Commit 2dbcf66 completes combat Tasks 8-9 but docs/reports/sc1-combat-differentiation-remediation-qa.md previously reported those tasks as partial (now fixed in 1203b28).
