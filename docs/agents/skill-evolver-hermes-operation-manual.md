# SkillEvolver and Hermes Operation Manual

**Audience:** Agents using Hermes/Codex traces to improve `.agents/skills`.  
**Goal:** Evolve development skills from evidence without letting skill updates mutate business code directly.

---

## Ownership

SkillEvolver workflow owns:

- `.agents/skills/*/SKILL.md`
- `harness/skills/registry.json`
- `harness/skills/schema.json`
- `harness/skills/held_out/*`
- `harness/skills/candidates/*`
- `harness/trace/schema.py`
- `harness/trace/validate_traces.py`
- `harness/trace/trials/*.jsonl`
- `harness/evolve/skill_evolver.py`
- `harness/evolve/auditor.py`
- `harness/evolve/held_out.py`
- `harness/evolve/strategy_runner.py`
- `tests/harness/test_skill_*`
- `tests/harness/test_candidate_held_out.py`
- `tests/harness/test_trace_validation.py`
- `tests/harness/test_strategy_runner.py`

It may read runtime code for diagnosis. It must not directly patch SimCore/Godot business code as part of skill evolution.

---

## Conceptual Loop

```text
fresh task trials
  -> trace pass/fail outcomes
  -> compare successful and failed behavior
  -> propose small SKILL.md patch
  -> structured auditor rejects unsafe patches
  -> held-out validation checks generality
  -> candidate-aware evidence required for promotion
  -> manual promotion or rejection
```

---

## Validation Tiers

Skill evolution has four distinct validation tiers.  Each tier catches a
different class of defect and **no tier substitutes for another**:

| Tier | What it catches | What it cannot prove |
|------|----------------|---------------------|
| **1. Repository validation** (`validate_registry.py`, `lint_deps.py`, test suites) | Broken code, missing fields, architecture violations | That the skill *improves* agent behavior |
| **2. Baseline fresh trial** (`baseline_or_candidate = "baseline"`) | Current skill behavior on a task; pass/fail outcome | That a candidate patch is better |
| **3. Candidate held-out trial** (`baseline_or_candidate = "candidate"`, `promotion_eligible = True`) | That the candidate patch behaves correctly on unseen held-out fixtures with a fresh agent run | Whether the change is *desirable* (aesthetic, scope) |
| **4. Manual promotion approval** | Final human judgement on scope, generality, and risk | — |

### Why command-only validation is not enough

Running the held-out suite `validation_commands` without fresh candidate
`SkillTrial` records only proves the repository is in a
working state.  It **cannot** prove the candidate skill patch was actually
loaded and followed by an agent.  Therefore command-only validation always
reports `HeldOutResult.passed` but `promotion_eligible = False`.

A candidate patch is only promotable when all of the following hold:

- `audit.accepted` is `True` (structured auditor found no issues);
- `held_out.passed` is `True` (suite commands succeeded);
- `held_out.promotion_eligible` is `True` (patch-derived identity, matching
  overlay hash, one fresh run per suite scenario, and no fixture overlap);
- manual review agrees.

### Candidate trace requirements (strict mode)

When `validate_traces.py --strict` runs, every trial with
`baseline_or_candidate == "candidate"` is checked for:

- non-empty `candidate_id`
- non-empty `agent_run_id`
- a held-out `task_fixture_id`
- `skill_md_read = True`
- `primary_action_invoked = True`
- `skill_md_sha256` matches the candidate overlay
- the first recorded tool call reads that exact overlay `SKILL.md` path
- non-empty `runner_provenance`
- a `sha256:` runner output hash
- at least one `validation_commands_run` entry
- one successful exit code and stdout hash per validation command
- positive token, turn, and duration metrics
- empty `runtime_paths_changed`
- every scenario's declared `expected_findings` is present with an allowed verdict
- `functional_verification == "pass"`
- `outcome == "pass"`

A baseline trial is exempt from these candidate-only checks.

---

## Required Evidence

A useful `SkillTrial` should record:

- `task_id`
- `task_description`
- `skill_name`
- `skill_version`
- `strategy_label`
- `skill_md_read`
- `primary_action_invoked`
- `tool_calls`
- `validation_commands_run`
- `validation_results`
- `validation_exit_codes`
- `functional_verification`
- `failure_log_summary`
- `touched_files`
- `outcome`
- `silent_bypass_detected`

Synthetic traces are acceptable for harness tests. Promotion-quality traces should come from real fresh-agent runs.

---

## Standard Workflow

1. **Validate registry and traces.**

   ```bash
   python3 harness/skills/validate_registry.py
   python3 harness/trace/validate_traces.py --strict
   ```

2. **Generate or collect trials.**

   For real Hermes/Codex runs, ensure the execution wrapper records `SkillTrial` rows. For local dry-runs, make clear that traces are synthetic.

3. **Run dry evolution first.**

   ```bash
   python3 -m harness.evolve.skill_evolver godot-specialist
   ```

4. **Inspect candidates.**

   Look under:

   ```text
   harness/skills/candidates/<skill-name>/<timestamp>/
   ```

   Required files:

   - `patch.md`
   - `rationale.json`

5. **Check auditor result.**

   Reject candidates that:

   - instruct edits to `simcore/`, `agents/`, or `godot/scripts/` directly,
   - hardcode seed, entity ID, or fixture ID,
   - add broad "must always" rules without validation evidence,
   - weaken existing validation commands,
   - overfit to one task.

6. **Run every generated held-out packet in a fresh task.**

   The dry run prints the derived candidate ID, temporary overlay path, and
   packet count. Packets are stored under
   `harness/skills/candidates/strategy_runs/<candidate-id>/`. Execute every
   packet in an independent Hermes/Codex task and combine the resulting
   SkillTrial rows into one JSONL evidence file. Each task must read the exact
   overlay path written in its packet before taking any other action. When the
   packet declares `fixture_files`, review only those isolated inputs and record
   the required per-axis findings in the trace.

7. **Validate and explicitly approve promotion.**

   ```bash
   python3 -m harness.evolve.skill_evolver <skill> --apply \
       --candidate-trace-file <candidate-traces.jsonl> \
       --approve-promotion
   ```

   Without a complete trace file, or without `--approve-promotion`, the evolver
   leaves `SKILL.md` unchanged. Legacy `--candidate-id` / `--agent-run-id`
   arguments are ignored as evidence and cannot authorize promotion.

8. **Review the resulting diff.**

   Promotion should append or edit the relevant `SKILL.md` only after
   review.  `promote_patch` requires both `audit.accepted` and
   `held_out.promotion_eligible` plus explicit manual approval; a plain `bool`
   argument is treated as command-only and never promotes.

---

## Safety Boundary

Allowed direct targets:

- `.agents/skills/*`
- `harness/skills/*`
- `harness/trace/*`
- `harness/evolve/*`
- `harness/memory/procedures/*`
- docs explaining skill behavior

Forbidden direct targets for SkillEvolver promotion:

- `simcore/*`
- `agents/*`
- `godot/scripts/*`
- model weights such as `*.pt`, `*.pth`, `*.safetensors`
- proprietary assets

If a skill-evolution result implies business-code changes, open a separate implementation task and run the relevant agent manual.

---

## Common Commands

Registry:

```bash
python3 harness/skills/validate_registry.py
```

Trace validation:

```bash
python3 harness/trace/validate_traces.py --strict
```

Harness tests:

```bash
python3 -m pytest tests/harness/test_skill_evolver.py tests/harness/test_trace_validation.py tests/harness/test_strategy_runner.py tests/harness/test_skill_auditor.py tests/harness/test_candidate_held_out.py -q
```

Godot held-out support:

```bash
python3 scripts/verify_presentation_scene.py
python3 scripts/verify_godot_fog_smoothing.py
```

Architecture gate:

```bash
python3 scripts/lint_deps.py
```

---

## Promotion Checklist

Before promoting a skill patch:

- [ ] Registry validation passes.
- [ ] Strict trace validation passes (`validate_traces.py --strict`).
- [ ] Candidate has pass/fail evidence.
- [ ] Auditor accepts the patch (`audit.accepted = True`).
- [ ] Held-out suite passes (`HeldOutResult.passed = True`).
- [ ] Held-out is **candidate-aware** (`HeldOutResult.promotion_eligible = True`):
      derived candidate identity, matching overlay/trace hashes, unique
      `agent_run_id` per suite scenario, complete scenario coverage, and no
      training/held-out fixture overlap.
- [ ] Patch only changes skill or harness-owned files.
- [ ] Patch is general, not task-specific.
- [ ] Business-code changes are split into a separate task.
- [ ] Manual review agrees and `--approve-promotion` is supplied.

---

## Current Known Blockers

As of 2026-06-10, the final gate is not clean because:

- `scripts/lint_deps.py` reports `simcore/http_gateway.py` importing `agents.script_ai`.
- Godot `--check-only` may hang in the local Godot 4.6 environment.
- Some held-out Godot checks require backend services to be running.
- At least one dry-run candidate passed audit but failed held-out validation.

Treat SkillEvolver as an evidence assistant until these blockers are fixed.
