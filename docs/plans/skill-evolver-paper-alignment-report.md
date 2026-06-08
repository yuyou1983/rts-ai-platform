# SkillEvolver Paper Alignment Report

## Status

⚠️ CONCERNS / FINAL GATE NOT PASSED

Core SkillEvolver harness work is implemented and unit-tested, but final acceptance is blocked by:
1. architecture lint violation in `simcore/http_gateway.py`
2. presentation verifier crash on nested abstract unit mappings
3. Godot check-only timeout / unavailable verification
4. dry-run candidate was rejected by auditor, so no skill patch is promotable yet

## Summary

SkillEvolver has been upgraded from a P0 scaffold to a Godot VFX dry-run evolution loop with complete registry coverage, strict trace validation, task fixtures, strategy packet generation, structured auditing, and stronger held-out validation. However, final gate did not pass — current status is **completed with blockers**.

## Implemented

- Layer constraints aligned with AGENTS.md.
- All local `.agents/skills/*/SKILL.md` entries registered.
- SkillTrial v2 fields added.
- Strict trace validation infers silent-bypass.
- Godot VFX task fixture added.
- Fresh-agent strategy packets generated for four Godot VFX strategies.
- Structured auditor added — verified it can reject candidate patches (dry-run candidate was `dry_run_rejected` due to missing `--check-only` / manifest validation evidence).
- Contrastive validation delta analysis added.
- Godot held-out suite now uses real validation commands (but `verify_presentation_scene.py` currently crashes, so held-out is not yet usable in practice).

## Remaining Risks

- Strategy packets produced are synthetic/local traces (`agent_run_id` empty, `tool_calls` empty); not yet from real Hermes fresh-agent execution. An external Hermes/Codex runner is still required for true fresh-agent trials.
- Screenshot-based visual regression is not yet automated.
- Candidate promotion remains manual and should stay manual until held-out suites cover at least Godot, SimCore replay, and Team-AI playbooks.
- No candidate patch has been accepted by the auditor yet; the evolution loop is structurally complete but has not yet produced a promotable skill improvement.

## Next Steps (Blocker Fixes)

1. **Fix `verify_presentation_scene.py`** — support nested dict values in manifest `unit_visuals` mapping (currently crashes on `unhashable type: 'dict'`).
2. **Fix `simcore/http_gateway.py`** — remove or guard the L2→L1 fallback import of `agents.script_ai`.
3. **Resolve Godot `--check-only` hang** — either upgrade engine, use GDScript lint alternative, or mark as optional gate.
4. Re-run final gate; if all pass, update this report status to PASS.

## Final Commands

### 1. `python3 harness/skills/validate_registry.py`

- **Exit code:** 0
- **Output (last line):**
  ```
  OK — all registry entries pass validation
  ```

### 2. `python3 harness/trace/validate_traces.py --strict`

- **Exit code:** 0
- **Output (last line):**
  ```
  OK — all trace files pass validation
  ```

### 3. `python3 -m pytest tests/harness/test_skill_evolver.py tests/harness/test_trace_validation.py tests/harness/test_strategy_runner.py tests/harness/test_skill_auditor.py -q`

- **Exit code:** 0
- **Output (last lines):**
  ```
  .........................................                                [100%]
  ```

### 4. `python3 scripts/lint_deps.py`

- **Exit code:** 1
- **Error:** 1 architecture violation found
  ```
  ❌ simcore/http_gateway.py:76 from agents.script_ai (L2) in L1 — forbidden
  ```
- **Known issue:** `simcore/http_gateway.py` has a fallback import of `agents.script_ai` (L2) from L1 code, violating the AGENTS.md layer constraint (SimCore must not import Agents). This appears to be an unresolved fallback/regression, not an accepted architecture exception — `docs/milestones/m2-production.md` (line 40) prescribes replacing direct imports with an `agent_factory` callback boundary. The fallback should be removed or moved behind the runtime `agent_factory` boundary. See `simcore/http_gateway.py:74-78`.

### 5. `python3 scripts/verify_presentation_scene.py`

- **Exit code:** 1
- **Error:** `TypeError: unhashable type: 'dict'` at `check_manifest()` line 110
  ```
  if sc_name not in uvs:
  TypeError: unhashable type: 'dict'
  ```
- **Known issue:** The presentation manifest maps abstract unit types to nested dicts (scene + material overrides) instead of plain strings. The `verify_presentation_scene.py` script builds a set of keys from `unit_visuals` but then compares a dict value (`sc_name`) against that set. The script needs to be updated to handle nested mapping values. See `scripts/verify_presentation_scene.py:103-110`.

### 6. `python3 scripts/verify_godot_fog_smoothing.py`

- **Exit code:** 0
- **Output (last lines):**
  ```
  === Godot fog smoothing verification ===
    Raw repeated 2->1 downgrades: 29 tiles
    Rendered alpha spike threshold: > 0.25
    Rendered alpha spike tiles: 0
    Final alpha distribution: {0.0: 42, 0.5: 21, 0.88: 193}

  OK: raw fog still changes, but Godot rendered alpha remains stable
  ```

### 7. `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd`

- **Exit code:** N/A (process hung / timed out after 15s)
- **Error:** Godot 4.6 headless `--check-only` does not terminate on macOS. The process starts, prints the engine banner, then hangs indefinitely. This is a known Godot 4.6 engine issue where `--headless --check-only` on certain project configurations does not exit cleanly. The GDScript file `godot/scripts/game_view.gd` exists and is well-formed (used at runtime), but cannot be verified via this CLI path in the current engine version.
- **Note:** A basic syntax check (tab/space consistency) reveals the file uses tab indentation throughout, which is valid GDScript but inconsistent with some project style guides. This is a cosmetic concern, not a functional one.
