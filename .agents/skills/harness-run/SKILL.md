---
name: harness-run
description: "Execute a development task through a tight red-capable feedback loop: read spec, reproduce, minimise, fix, regress, review, record."
argument-hint: "[task_fixture_id | source_spec_path]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, Bash
---

# Harness Run — Tight Feedback Loop

This skill executes one development task through a **tight feedback loop**: a
red-capable reproducer, the smallest fix, and a regression test pinned at the
highest stable seam. The loop is deliberately narrow so that every step is
traceable and every claim of "done" is backed by evidence in this repository.

## Red-capable first

Every task begins by establishing a red-capable signal: one fast, deterministic,
agent-runnable command that currently **fails** and that will **pass** once the
slice is delivered. If you cannot build a red-capable command, you do not yet
understand the failure — go back to the source specification.

## The feedback loop (in order)

Run these steps in order. Do not skip ahead. Each step's output feeds the next.

1. **Read source specification, domain context, ADR, and current fixture.**
   Read the ticket's `Source specification` path and any ADR it references.
   Read the domain context glossaries (`docs/context/`) and the relevant
   fixture under `harness/skills/tasks/`. You must cite the spec in every
   later step.

2. **Build one fast, deterministic, agent-runnable command that can detect the
   exact failure.** This is the red-capable command. It must exit non-zero on
   the current state and exit zero once the fix lands. Prefer a single pytest
   node, a headless sim one-liner, or an architecture-lint command. No
   network, no GPU, no long batch — it must run in seconds.

3. **Reproduce and minimise.** Run the red-capable command and capture the
   failing output. Then minimise: trim the input, the map, the seed, and the
   code path until you have the smallest reproducer that still fails. The
   goal is a reproducer a reviewer can read in seconds.

4. **Record 3-5 falsifiable hypotheses for hard defects.** Write them down
   (in the task report) as concrete, testable statements — each must name a
   location and a predicted cause. "Something in combat is wrong" is not a
   hypothesis; "SimCore applies ranged damage before the move-resolution step,
   double-counting the first tick" is.

5. **Test one hypothesis at a time** with targeted instrumentation. Add the
   narrowest logging/assertion that would confirm or refute the hypothesis,
   run the red-capable command, and record the outcome. Remove the
   instrumentation before committing. Never test more than one hypothesis at
   a time — mixed signals are noise.

6. **Convert the minimal reproducer into a regression test at the highest
   stable seam.** Place the test at the highest layer where the behaviour is
   stable and observable (prefer the SimCore/gRPC boundary over an internal
   helper; prefer a Godot headless check over a unit on a private method).
   This regression test is the permanent guard against re-introduction.

7. **Implement the smallest fix.** Change the minimum code required to turn
   the red-capable command green. Resist refactors, renames, and "while I'm
   here" edits — they belong in a separate vertical-slice ticket. The
   smallest fix is the one whose diff a reviewer can understand in one read.

8. **Run targeted tests, architecture checks, then the relevant full suite.**
   First the regression test from step 6. Then `python3 scripts/lint_deps.py`
   (architecture). Then the relevant full suite (`make test-core`, or the
   domain subset named by the ticket's verification seams). Order matters:
   targeted → architecture → full, so a failure is localised fast.

9. **Run code-review against the fixture source specification.** Invoke the
   `code-review` skill against the fixed-point diff, with the ticket's
   `Source specification` as the Specification axis authority. The review's
   verdicts (Standards, Specification, Source Truth) must be recorded before
   declaring done.

10. **Update evidence and task status in the same commit.** Write the proof
    to the ticket's `Evidence outputs` paths (e.g. `docs/reports/<slice>.md`,
    `harness/output/...`), flip the ticket `Status` to `done`, and commit the
    code, the regression test, and the evidence together. Never split the
    fix from its evidence.

## Output locations (this repository only)

All evidence and artefacts are written to repository-relative paths. Do not
reference external stores.

| Artefact | Location |
|---|---|
| Task reports | `docs/reports/<slice>.md` |
| Harness output | `harness/output/` (replays, metrics, promotion logs) |
| Replays | `harness/output/replays/` |
| Promotion history | `harness/output/promotion/` |
| Regression tests | `tests/` (mirroring the layer under test) |
| Sprint plans | `production/sprints/sprint-[N].md` |

Do not invent run IDs, S3 URIs, MLflow experiment numbers, or synthetic
progress tables. If a value is not produced by a command in this repository,
it does not exist in the evidence.

## Handoff

When a ticket cannot be completed by this skill alone (e.g. it needs the
godot-specialist for a presentation fix, or team-simcore for a rule change),
produce a structured handoff:

- Restate the ticket ID, the `Source specification`, and the current `Status`.
- Record the red-capable command and its current output.
- List the hypotheses already ruled out (so the next owner does not repeat them).
- Name the exact owner skill that must continue, and the remaining acceptance
  criteria and verification seams.

A handoff is not "done". The ticket stays `in_progress` until the receiving
skill records the final evidence and flips `Status` to `done`.

## Anti-patterns to reject

- Declaring done without a green red-capable command and a passing regression test.
- Committing the fix in a different commit from its evidence.
- Testing multiple hypotheses at a time.
- A "smallest fix" that also renames, restructures, or touches unrelated paths.
- Referencing S3, MLflow, or fabricated run IDs instead of repository paths.
- Skipping the code-review step because "the tests pass".
