# Strategy C: GameView selection and health-bar audit

Task fixture: `godot-vfx/sc1-resource-alignment`
Skill: `godot-specialist`

## Required First Action

Read `.agents/skills/godot-specialist/SKILL.md` first and follow its instructions.

## Task

Align SC1-inspired unit/building resource manifest, atlas rectangles, selection rings, health bars, and fallback sprites without changing SimCore rules.

## Focus Files

- `godot/scripts/game_view.gd`
- `godot/scripts/selection_manager.gd`
- `godot/resources/presentation_manifest.json`

## Strategy Rules

- Check _visual_radius, selection rings, and health bar offsets against manifest values.
- Preserve the frontend-only boundary for visual corrections.

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
- `strategy_label`: `C`
- `skill_md_read`: true only if the SKILL.md was actually read
- `primary_action_invoked`: true only if the declared primary action was actually invoked
- `validation_commands_run`: the exact validation commands run
- `validation_exit_codes`: command exit codes in the same order
- `baseline_or_candidate`: `baseline`
