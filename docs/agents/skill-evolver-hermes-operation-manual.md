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
- `harness/evolve/strategy_runner.py`
- `tests/harness/test_skill_*`
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
  -> manual promotion or rejection
```

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
   python3 -m harness.evolve.skill_evolver --skill godot-specialist --dry-run
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

6. **Run held-out validation.**

   A candidate is not promotable without held-out passing.

7. **Promote manually.**

   Promotion should append or edit the relevant `SKILL.md` only after review.

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
python3 -m pytest tests/harness/test_skill_evolver.py tests/harness/test_trace_validation.py tests/harness/test_strategy_runner.py tests/harness/test_skill_auditor.py -q
```

Godot held-out support:

```bash
python3 scripts/verify_presentation_scene.py
python3 scripts/verify_godot_fog_smoothing.py
```

Architecture gate:

```bash
python3 scripts/lint_deps.py simcore/ agents/ runtime/ proto/
```

---

## Promotion Checklist

Before promoting a skill patch:

- [ ] Registry validation passes.
- [ ] Strict trace validation passes.
- [ ] Candidate has pass/fail evidence.
- [ ] Auditor accepts the patch.
- [ ] Held-out suite passes.
- [ ] Patch only changes skill or harness-owned files.
- [ ] Patch is general, not task-specific.
- [ ] Business-code changes are split into a separate task.

---

## Current Known Blockers

As of 2026-06-10, the final gate is not clean because:

- `scripts/lint_deps.py` reports `simcore/http_gateway.py` importing `agents.script_ai`.
- Godot `--check-only` may hang in the local Godot 4.6 environment.
- Some held-out Godot checks require backend services to be running.
- At least one dry-run candidate passed audit but failed held-out validation.

Treat SkillEvolver as an evidence assistant until these blockers are fixed.

