---
name: code-review
description: "Reviews a change set against three independent axes — Standards, Specification, and Source Truth — using a pinned fixed-point diff and the originating plan. Produces separate verdicts per axis; never merges them into one score."
argument-hint: "[fixed-point] [spec-path-or-issue]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

This skill performs a specification-aware code review along three independent axes.
It does not require a subagent tool; a single agent run with Read/Grep/Bash is sufficient.

## Pin The Fixed Point

1. Accept a fixed-point ref (commit SHA, tag, or branch) from the argument hint or
   the task fixture's `fixed_point` field.
2. If no fixed-point is provided, compute the merge-base with the upstream branch
   (`git merge-base HEAD @{u}`) and use it **only** when unambiguous. If ambiguous
   (multiple upstreams, no upstream, or shallow clone), stop and request the
   fixed-point explicitly.
3. Run `git diff <fixed-point>...HEAD` to capture the complete change set under
   review. This triple-dot form compares the merge-base, so it captures all
   commits on the working branch since divergence.
4. Record the fixed-point SHA, the diff stat summary, and the list of changed
   files as the review scope. No file outside this diff is in scope.

## Locate The Originating Specification

1. Find the plan, issue, ADR, or spec document that the work was supposed to
   implement. Sources of truth, in priority order:
   - Task fixture `source_spec` field (e.g. `docs/plans/...`)
   - Commit message body referencing an issue/plan
   - `docs/plans/` directory matching the branch or feature name
   - Linked GitHub issue in the PR description
2. Read the originating specification in full. Extract:
   - Declared tasks and their acceptance criteria
   - Declared external authority (DAT files, protobuf contracts, replay hashes,
     generated fixtures) — this gates the Source Truth axis
   - Out-of-scope items explicitly excluded by the spec
3. If no originating specification can be located, record `Specification: NOT AVAILABLE`
   and continue with the Standards and Source Truth axes.

## Standards Axis

Check the diff against project-local standards and architecture boundaries.

- [ ] Dependency direction respects the layer rules (see AGENTS.md):
      L0 Proto ← L1 SimCore ← L2 Agents ← L3 Frontend.
      SimCore never imports Agents; Agents never import Godot.
- [ ] No circular dependencies introduced between modules.
- [ ] Cross-layer communication goes through protobuf + gRPC, not direct imports.
- [ ] Consistent with established patterns in the codebase (state snapshots,
      deterministic replay, rule engine).
- [ ] Game hot paths avoid per-tick allocations and non-seeded randomness.
- [ ] Public methods/classes have doc comments; no method exceeds 40 lines
      (excluding data declarations); cyclomatic complexity under 10.
- [ ] Configuration values loaded from data files, not hardcoded constants.

Verdict: PASS | CONCERNS | FAIL

## Specification Axis

Report behavior against the originating plan/issue. For every declared task or
acceptance criterion, classify the implementation as:

- **missing** — declared but absent from the diff
- **partial** — present but incomplete relative to the criterion
- **incorrect** — present but contradicts the spec
- **out-of-scope** — present in the diff but not declared by the spec

Also detect **specification drift**: cases where a report, QA doc, or status
table claims a state (e.g. "partial") that disagrees with what the diff
actually shows (e.g. the implementation is complete). Record each drift as a
finding with the conflicting source quotes.

Verdict: PASS | CONCERNS | FAIL | NOT AVAILABLE

## Source Truth Axis

Runs **only** when the originating plan declares an external authority. If no
external authority is declared, this axis is skipped.

Authorities and how to check them:

- **SC1 DAT / OpenBW** — weapon/spell/armor identity must match the audited
  reference values (e.g. Patch_rt DAT). Compare implementation constants
  against the recorded audit table.
- **Protobuf contract** — field numbers, types, and names must match the
  `.proto` definitions; generated code must not drift from the schema.
- **Replay hash** — if the plan pins a replay hash, the deterministic
  replay output must reproduce it.
- **Generated fixture** — if the plan references a fixture generator, the
  fixture content must be reproducible from the generator without manual edits.

Verdict: PASS | CONCERNS | FAIL | NOT APPLICABLE

## Independent Verdicts

The three axes are independent. They may be run in parallel or sequentially,
but each axis keeps its own notes and its own verdict line. Do NOT merge the
axes into a single composite score — a PASS on Standards does not rescue a
FAIL on Specification, and vice versa.

## Output Format

```
## Standards
[findings with file:line references]
Verdict: PASS | CONCERNS | FAIL

## Specification
[per-criterion classification: missing/partial/incorrect/out-of-scope]
[drift findings with conflicting source quotes]
Verdict: PASS | CONCERNS | FAIL | NOT AVAILABLE

## Source Truth
[authority checks: DAT identity, proto contract, replay hash, fixture]
Verdict: PASS | CONCERNS | FAIL | NOT APPLICABLE

## Summary
Standards findings: N; Specification findings: N; Source Truth findings: N.
```
