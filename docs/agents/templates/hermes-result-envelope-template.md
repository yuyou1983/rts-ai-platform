# Hermes Result Envelope

<!-- Return this envelope for PASS, FAIL, and BLOCKED executions. -->

## Identity

- Task ID: `<task-id>`
- Agent run ID: `<unique-run-id>`
- Status: `<PASS | FAIL | BLOCKED>`
- Start fixed point: `<git-commit-sha>`
- End HEAD: `<git-commit-sha or unchanged>`

## Outcome

<Concise description of what actually changed or why execution stopped.>

## Changed Files

- `<repository-relative-path and purpose, or none>`

Forbidden paths changed: `<no | yes: list and stop reason>`

## Acceptance Results

- [ ] `<criterion>` — `<PASS | FAIL | BLOCKED>` — `<evidence reference>`
- [ ] `<criterion>` — `<PASS | FAIL | BLOCKED>` — `<evidence reference>`

## Verification Evidence

| Command | Exit code | Result | Evidence |
|---|---:|---|---|
| `<exact command>` | `<integer>` | `<PASS | FAIL>` | `<path, short output, or hash>` |

## Scope Check

- Diff base: `<fixed-point>`
- Actual changed paths: `<paths>`
- Unrelated dirty paths preserved: `<paths or none>`
- Scope verdict: `<PASS | FAIL>`

## Deviations And Risks

- Assumptions: `<list or none>`
- Spec deviations: `<list or none>`
- Residual risks: `<list or none>`
- Rollback: `<revert scope or not applicable>`

## Blocker

<External condition and recovery condition, or none.>

## Next Command

```bash
<exactly one command for ChatGPT final verification or recovery>
```

## Executor Self-Verdict

`<PASS | FAIL | BLOCKED>` because <one-sentence evidence-based reason>. This is an executor verdict and requires ChatGPT final review.
