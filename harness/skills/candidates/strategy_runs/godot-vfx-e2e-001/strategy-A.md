# Strategy A: Manifest-first audit

Task fixture: `godot-vfx/sc1-resource-alignment`
Skill: `godot-specialist`

## Required First Action

Read `.agents/skills/godot-specialist/SKILL.md` first and follow its instructions.

## Task

Align SC1-inspired unit/building resource manifest, atlas rectangles, selection rings, health bars, and fallback sprites without changing SimCore rules.

## Focus Files

- `godot/resources/presentation_manifest.json`
- `scripts/generate_presentation_manifest.py`
- `scripts/verify_presentation_scene.py`

## Strategy Rules

- Start by validating manifest structure and abstract-to-visual mappings.
- Do not edit Godot runtime scripts unless validation proves manifest data cannot express the correction.

## Forbidden Runtime Paths

- `simcore/`
- `agents/`
- `godot/scripts/`

## Validation Commands

- `python3 scripts/verify_presentation_scene.py`
- `python3 -m pytest tests/godot/test_presentation_manifest.py -q`
- `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only godot/scripts/game_view.gd`

## Pass Criteria

- presentation manifest validates without atlas bounds errors
- abstract unit/building mappings resolve to known visuals
- Godot check-only succeeds
- candidate skill patch does not modify SimCore, Agents, or Godot runtime scripts

## Trace Requirement

Record a SkillTrial v2 with:
- `skill_name`: `godot-specialist`
- `task_fixture_id`: `godot-vfx/sc1-resource-alignment`
- `strategy_label`: `A`
- `skill_md_read`: true only if the SKILL.md was actually read
- `primary_action_invoked`: true only if the declared primary action was actually invoked
- `validation_commands_run`: the exact validation commands run
- `validation_exit_codes`: command exit codes in the same order
- `baseline_or_candidate`: `baseline`
