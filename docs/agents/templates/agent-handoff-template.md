# Agent Handoff

<!--
  Structured handoff template for context transfer between agents.
  Fill in every section below. Do not delete section headings.
  Reference existing plans, commits, reports, diffs, and fixtures by path
  — never duplicate their contents inline.
-->

## Objective
<one-sentence outcome — what the receiving agent must accomplish>

## Fixed Point
<commit-sha>

## Active Task Fixture
<path to task fixture JSON, e.g. harness/skills/tasks/<team>/<task-id>.json>

## Gate Status
<gate name>: <verdict (PASS | FAIL | BLOCKED)>

## Completed Evidence
- <evidence path or reference, e.g. docs/reports/<report>.md>

## Current Failure
<description of the blocking failure, or "none">

## Unrelated Working Tree Paths
- <path that is dirty but unrelated to this task, or "none">

## Next Command
<one executable command, e.g. python3 -m pytest tests/harness/test_handoff_skill_contract.py -q>

## Suggested Skills
- <skill name from harness/skills/registry.json>

## Stop Conditions
<conditions that should halt execution, e.g. "validation_commands all pass" or "no credentials remain in the handoff file">
