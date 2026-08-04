# Strategy A: Standards-first review

Task fixture: `combat-remediation-review`
Skill: `code-review`

## Required First Action

Read `.agents/skills/code-review/SKILL.md` first and follow its instructions.

## Task

Review the combat remediation implementation against its plan and QA report

## Focus Files

- `.agents/skills/code-review/SKILL.md`
- `AGENTS.md`
- `harness/skills/registry.json`

## Strategy Rules

- Start by running git diff e201355...2dbcf66 to identify all changes.
- Evaluate architecture boundary compliance against AGENTS.md.
- Do not modify runtime business code.

## Forbidden Runtime Paths

- `simcore/`
- `agents/`
- `godot/scripts/`
- `proto/`

## Source Specification

`docs/plans/2026-08-03-sc1-combat-differentiation-remediation-plan.md`

## Blocked By

_(none — ticket is ungated)_

## Acceptance Criteria

- Standards axis reports architecture boundary compliance
- Specification axis detects QA status drift where Task 8-9 implementation is complete but QA report previously reported partial
- Source Truth axis checks SC1 DAT weapon identity against implementation

## Verification Seams

- `python3 harness/skills/validate_registry.py`
- `python3 -m pytest tests/harness/test_code_review_skill_contract.py -q`

## Evidence Outputs

- `docs/reports/agent-skills-workflow-alignment.md`

## Stop Condition

Execute ONLY the current task fixture (`combat-remediation-review`). Do not begin any other
fixture. Stop after every verification seam passes and all evidence outputs have
been recorded/updated. If a seam fails, stop and report the failure rather than
proceeding to a different ticket.

## Validation Commands

- `python3 -m pytest tests/harness/test_code_review_skill_contract.py -q`
- `python3 harness/skills/validate_registry.py`

## Pass Criteria

- Standards axis reports architecture boundary compliance
- Specification axis detects QA status drift
- Source Truth axis checks SC1 DAT weapon identity
- No runtime business code modified

## Trace Requirement

Record a SkillTrial v2 with:
- `skill_name`: `code-review`
- `task_fixture_id`: `combat-remediation-review`
- `strategy_label`: `A`
- `skill_md_read`: true only if the SKILL.md was actually read
- `primary_action_invoked`: true only if the declared primary action was actually invoked
- `validation_commands_run`: the exact validation commands run
- `validation_exit_codes`: command exit codes in the same order
- `baseline_or_candidate`: `baseline`
