---
name: sprint-plan
description: "Plan a sprint as a set of vertical-slice tickets. Each ticket is the narrowest independently demonstrable path across the architecture."
argument-hint: "[new|update|status]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit
---

# Sprint Planning — Vertical Slice Tickets

This skill plans a sprint as a set of **vertical slice** tickets. A vertical slice
is the narrowest independently demonstrable path through the whole architecture:
it crosses as many layers as required to deliver one observable, verifiable
behaviour, and no more.

## Core Principle

Do not decompose a ticket into one ticket per architectural layer. A ticket may
cross Proto, SimCore, gRPC, and Godot when that is the narrowest independently
demonstrable path. Horizontal tickets ("rewrite the proto layer", "refactor all
of SimCore") are rejected: they cannot demonstrate an outcome on their own, so
they cannot be verified or handed off in isolation.

A ticket is only "done" when its evidence outputs are produced and its
verification seams pass. A layer-only change with no observable behaviour is
not a ticket — it is a sub-step inside a vertical slice.

## Ticket Format

Every ticket MUST carry these fields, in this order:

```
### [TICKET-ID] <one-line outcome>

- Status: <blocked | ready | in_progress | verification | done>
- Blocked by: <comma-separated ticket IDs, or "none">
- Source specification: <repository-relative path to the spec / ADR / fixture>
- What it delivers: <one or two sentences naming the observable behaviour>
- Acceptance criteria:
  - <machine-checkable criterion>
  - <machine-checkable criterion>
- Verification seams:
  - <command or test path that proves the slice works end to end>
- Evidence outputs:
  - <repository-relative path where proof is recorded>
- Owner skill: <the harness skill that will execute this ticket>
```

### Field rules

- **Status** — lifecycle of the ticket. `blocked` tickets cannot start until
  every `Blocked by` ticket is `done`. `ready` means unblocked and not yet
  started. `verification` means the slice is implemented but evidence/ seams
  are pending. `done` means evidence outputs exist and every verification seam
  passes.
- **Blocked by** — the explicit dependency graph. The blocked_by graph must be
  acyclic; a `ready` ticket may only depend on `done` tickets.
- **Source specification** — a repository-relative path that already exists on
  disk (an ADR, a domain-context document, a design spec, or a fixture). No
  spec, no ticket.
- **What it delivers** — names the *observable behaviour*, not the files
  touched. "Units take damage from ranged attacks and the replay hash is
  stable" is good; "edit combat.py" is not.
- **Acceptance criteria** — every criterion must be machine-checkable
  (a command exit code, a file's presence, a test passing). Vague criteria
  ("combat feels better") are rejected.
- **Verification seams** — the exact commands or test paths that prove the
  slice works end to end. At least one seam must exercise the slice through
  the full intended path (Proto → SimCore → gRPC → Godot where relevant).
- **Evidence outputs** — repository-relative paths where the proof is written
  (e.g. `docs/reports/<slice>.md`, `harness/output/...`). Evidence must be
  produced in the same commit that flips Status to `done`.
- **Owner skill** — the registered harness skill (e.g. `harness-run`,
  `team-simcore`, `godot-specialist`) that will execute the ticket.

## Workflow

1. Read the milestone definition and the current stage file (`production/stage.txt`).
2. Read the previous sprint's velocity and carryover from
   `production/sprints/sprint-[N].md`.
3. Scan `docs/` for specifications, ADRs, and fixtures marked ready.
4. Propose vertical slice tickets, each carrying the full ticket format above.
   Prefer the narrowest slice that delivers an observable behaviour.
5. Resolve the blocked_by graph: no ticket may be `ready` while depending on a
  non-`done` ticket. Detect cycles and refuse them.
6. Write the sprint plan to `production/sprints/sprint-[N].md`, listing every
  ticket with its full ticket block.

## Anti-patterns to reject

- One ticket per layer ("proto ticket", "simcore ticket", "godot ticket") for a
  single behaviour — collapse into one vertical slice.
- Tickets with no `Source specification` (no spec on disk = not ready to plan).
- Tickets whose `Acceptance criteria` cannot be run by a command.
- Tickets whose `Verification seams` only touch one layer when the slice
  crosses several — the seam must prove the end-to-end path.
- Tickets with no `Evidence outputs` — done cannot be proven.
