# Hermes Task Unit

<!-- One file represents one independently executable and returnable task. -->

## Identity

- Task ID: `<domain>/<stable-task-id>`
- Owner domain: `<simcore | agents | frontend-godot | dev-harness | cross-cutting>`
- Source spec: `<repository-relative-path>`
- Fixed point: `<git-commit-sha>`
- Blocked by: `<task IDs or none>`

## Objective

<One observable outcome.>

## Scope

Allowed paths:

- `<repository-relative-path-or-prefix>`

Forbidden paths:

- `<repository-relative-path-or-prefix>`

Existing unrelated dirty paths:

- `<repository-relative-path or none>`

## Required Context

- `AGENTS.md`
- `<authoritative plan, ADR, fixture, or skill path>`

## First Command

```bash
<exactly one baseline or reproduction command>
```

## Acceptance Criteria

- [ ] `<observable criterion>`
- [ ] `<observable criterion>`

## Verification Commands

```bash
<targeted validation command>
<regression or architecture validation command>
```

## Required Evidence

- `<test output, report, screenshot, replay, trace, or diff reference>`
- `git diff --name-only <fixed-point>` scope check

## Stop Conditions

- Return `PASS` only when every acceptance criterion and verification command passes.
- Return `FAIL` when implementation or validation fails with a reproducible cause.
- Return `BLOCKED` before modifying forbidden paths, changing the specification, or using an unapproved external dependency.
- Preserve all unrelated working-tree changes.

## Return Contract

Write `hermes-result-<task-id>.md` using `docs/agents/templates/hermes-result-envelope-template.md`. Return the result file path and do not paste raw conversation history.
