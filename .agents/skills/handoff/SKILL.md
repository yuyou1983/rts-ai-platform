---
name: handoff
description: "Structured context transfer between agents — one task, one command, no conversation dumps."
argument-hint: "[task-id]"
user-invocable: true
allowed-tools: Read, Write, Bash
---

## Purpose

Transfer structured context between agents so a receiving agent can resume
work without reading a transcript. The handoff is a **single file** written
to the OS temporary directory. It captures exactly one active task, one next
command, and pointers to all prior evidence — nothing more.

## Output Location

The skill writes the handoff to the OS temporary directory (`$TMPDIR` on
macOS, `/tmp` on Linux) using the filename:

```
rts-agent-handoff-<task-id>.md
```

The file is never written inside the repository working tree. It lives in a
temporary directory so it does not pollute `git status`.

## Process

When this skill is invoked:

1. **Identify the one active task.** Read the originating task fixture and
   determine the single task that is currently in progress. The handoff may
   reference only one active task — if multiple tasks are in flight, produce
   one handoff file per task.

2. **Pin the fixed point.** Record the commit SHA of the last known good
   state. This is the `Fixed Point` the receiving agent diffs against.

3. **Gather evidence by path.** List completed evidence (reports, test
   outputs, diffs) as repository-relative paths. **Do not duplicate plan,
   report, or diff content** — reference each artifact by path so the
   receiving agent reads the canonical source.

4. **Record the current failure.** If the task is blocked, describe the
   failure in one or two sentences. If the task is not blocked, write
   `none`.

5. **State the next command.** Provide exactly one executable command that
   the receiving agent should run first. This is the `Next Command` section.
   It must be a single shell command the receiving agent can copy-paste.

6. **Flag unrelated working-tree changes.** If `git status` shows dirty
   paths that are unrelated to the active task, list them under
   `Unrelated Working Tree Paths` so the receiving agent does not
   accidentally revert or commit them.

7. **Suggest follow-up skills.** List one or more skill names from
   `harness/skills/registry.json` that the receiving agent should consider
   invoking.

8. **Define stop conditions.** State the conditions under which the
   receiving agent should halt (e.g., all validation commands pass, or a
   specific test turns green).

## Required Sections

The handoff file must contain all of the following section headings, in
this order:

1. **Objective** — one-sentence outcome.
2. **Fixed Point** — commit SHA.
3. **Active Task Fixture** — path to the task fixture JSON.
4. **Gate Status** — gate name and verdict.
5. **Completed Evidence** — list of evidence paths or references.
6. **Current Failure** — description or "none".
7. **Unrelated Working Tree Paths** — list of paths or "none".
8. **Next Command** — one executable command.
9. **Suggested Skills** — list of skill names.
10. **Stop Conditions** — conditions that should halt execution.

Use `docs/agents/templates/agent-handoff-template.md` as the fill-in
template.

## Constraints

- **Reject "Conversation Dump" headings.** The handoff must not contain a
  section named "Conversation Dump", "Chat Log", "Transcript", or any
  heading that implies pasting raw conversation history. If the agent
  produces such a heading, the handoff is invalid and must be rewritten.
  Conversation dumps are forbidden.

- **Redact credentials and secrets.** Before writing the handoff file,
  scan the content for API keys, tokens, passwords, and any credential
  material. Redact every match (e.g., `AKIA****`). The handoff must not
  leak secrets or credentials into the temporary file.

- **Do not copy proprietary asset paths outside the repository.** Paths to
  assets that live outside the repository (S3 URIs, local model weights,
  proprietary data) must not be included. If such a path is relevant,
  reference it by a stable identifier, not by the raw filesystem or cloud
  URI.

- **Exactly one active task.** The handoff captures one task only. If
  multiple tasks are in flight, split into multiple handoff files.

- **Exactly one next command.** The `Next Command` section contains a
  single command, not a list.

- **Reference, do not duplicate.** Plans, reports, diffs, and fixtures are
  referenced by repository-relative path. Their contents must not be
  inlined.

## Completion Criteria

- All ten required sections are present in the handoff file.
- The handoff file is written to the OS temporary directory as
  `rts-agent-handoff-<task-id>.md`.
- No credentials or secrets appear in the output.
- Exactly one active task and one next command are recorded.
- No "Conversation Dump" heading is present.
