# Candidate Held-Out Evidence Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make skill promotion depend on a reproducible candidate overlay and fresh-agent traces bound to the exact patch and every held-out scenario.

**Architecture:** Candidate identity is derived from the skill name and patch content. A temporary overlay carries signed metadata and the resulting `SKILL.md` hash. Held-out commands remain diagnostic; promotion additionally requires strict candidate traces whose candidate ID, overlay hash, skill, fixture, and runner evidence match the overlay and suite.

**Tech Stack:** Python 3.11, dataclasses, JSON/JSONL, hashlib, pytest.

---

### Task 1: Lock candidate identity and overlay evidence

**Files:**
- Modify: `harness/evolve/held_out.py`
- Test: `tests/harness/test_candidate_held_out.py`

- [x] Add failing tests proving arbitrary IDs, missing suites, missing overlays, and mismatched overlay metadata cannot become promotion-eligible.
- [x] Run `python3 -m pytest tests/harness/test_candidate_held_out.py -q -n 0` and confirm the new tests fail for the intended assertions.
- [x] Derive candidate IDs from `skill_name + patch_content`, write `.candidate.json`, and validate overlay metadata plus `SKILL.md` hash.
- [x] Re-run the focused test and confirm it passes.

### Task 2: Bind fresh traces to every held-out scenario

**Files:**
- Modify: `harness/trace/schema.py`
- Modify: `harness/trace/validate_traces.py`
- Modify: `harness/evolve/held_out.py`
- Test: `tests/harness/test_trace_validation.py`
- Test: `tests/harness/test_candidate_held_out.py`

- [x] Add failing tests for missing runner provenance, zero execution metrics, missing output hashes, candidate mismatch, overlay hash mismatch, duplicate run IDs, and incomplete scenario coverage.
- [x] Extend `SkillTrial` with `skill_md_sha256`, `runner_provenance`, and `runner_output_hash` evidence.
- [x] Require strict, unique, matching candidate trials for every scenario before setting `promotion_eligible=True`.
- [x] Add concrete code-review spec/diff fixtures and validate expected per-axis verdicts from candidate traces.
- [x] Re-run the focused trace and held-out tests.

### Task 3: Generate executable candidate held-out packets

**Files:**
- Modify: `harness/evolve/strategy_runner.py`
- Test: `tests/harness/test_strategy_runner.py`

- [x] Add failing tests for candidate packet identity, overlay-first instructions, unique run IDs, and manifest metadata.
- [x] Add a held-out packet generator that emits one packet per scenario and binds each packet to the candidate overlay.
- [x] Keep baseline packet generation backward compatible.
- [x] Re-run strategy-runner tests.

### Task 4: Harden promotion and evolve CLI

**Files:**
- Modify: `harness/evolve/skill_evolver.py`
- Test: `tests/harness/test_skill_evolver.py`

- [x] Add failing tests that reject a held-out result for another skill or another patch-derived candidate ID.
- [x] Load candidate traces from a caller-provided JSONL file and create the exact overlay for each accepted patch.
- [x] Remove ID-only promotion eligibility; IDs become derived evidence rather than caller assertions.
- [x] Re-run skill-evolver tests.

### Task 5: Reconcile gates and documentation

**Files:**
- Modify: `docs/reports/agent-skills-workflow-alignment-change-summary.md`
- Modify: `docs/reports/agent-skills-workflow-alignment.md`

- [x] Mark A6-A8 and Task 10 blocked until a real candidate run supplies complete evidence.
- [x] Distinguish structural suite validation from fresh-agent behavioral validation.
- [x] Correct collected test counts and document the reproducible candidate workflow.

### Task 6: Final verification

- [x] Run `python3 -m pytest tests/harness -q -p no:warnings -n 0`.
- [x] Run all four harness validators in strict mode where supported.
- [x] Run `python3 scripts/lint_deps.py` and `git diff --check`.
- [x] Re-run the fabricated-ID probe and confirm `promotion_eligible=False`.
- [x] Review only files changed by this plan; leave unrelated working-tree files untouched.
