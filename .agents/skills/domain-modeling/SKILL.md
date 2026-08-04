---
name: domain-modeling
description: "RTS domain terminology discipline — detect, test, and resolve language drift across bounded contexts."
argument-hint: "[term-or-concept]"
user-invocable: true
allowed-tools: Read, Grep, Write
---

## Purpose

Keep the RTS domain language unambiguous across the four bounded contexts
(SimCore, Godot Presentation, Skill Harness, SC1 Source Truth). Detect vague
or conflicting terminology, test it against concrete scenarios, and resolve it
by updating the relevant glossary — never by embedding the decision in code.

## Process

When this skill is invoked:

1. **Read the context map and relevant glossary.** Begin by reading
   `CONTEXT-MAP.md` to identify which bounded context owns the concept in
   question, then read that context's canonical glossary in `docs/domain/`.

2. **Detect vague or conflicting terminology.** Examine the request, the
   originating specification, and the code or document behavior for terms
   that are overloaded, undefined, or used differently across contexts. Flag
   any term whose meaning changes depending on who reads it.

3. **Test the proposed language with at least two concrete edge scenarios.**
   Construct two distinct, realistic scenarios that would distinguish the
   proposed definition from a plausible alternative. If the scenarios do not
   disambiguate the term, the definition is not yet ready.

4. **Update the glossary immediately when a term is resolved.** Write the
   resolved term into the owning context's glossary using the canonical
   entry shape (Definition, Not the same as, Boundary example). Do not defer
   the update to a later task.

5. **Offer an ADR only when all three conditions hold:** the choice is hard
   to reverse, surprising without context, and involves a real trade-off.
   If these conditions are not all met, the glossary update is sufficient.
   When an ADR is warranted, recommend that the user invoke the
   `architecture-decision` skill separately — do not compose it directly
   (only orchestrators may compose).

6. **Finish only when terminology, scenarios, and any code/document
   disagreement are recorded.** The glossary must contain the resolved term,
   its disambiguating scenarios, and a note on any disagreement that was
   found and how it was reconciled. If a disagreement cannot be resolved in
   this session, record it explicitly as an open question in the glossary.

## Constraints

- **Must not modify runtime code.** This skill writes to `docs/domain/` and
  `CONTEXT-MAP.md` only. It must not edit `simcore/`, `agents/`,
  `godot/scripts/`, or `proto/`. If the terminology issue requires a code
  change, recommend a separate `harness-run` task.

- **Glossary entries must contain domain meaning only.** No file paths, no
  function signatures, no implementation plans, no mutable task status. An
  entry that references a specific function or file path has leaked
  implementation detail and must be revised.

- **One glossary per concept.** When a term spans contexts, each glossary
  must cross-reference the owning context's definition rather than silently
  redefining the term.

## Completion Criteria

- The relevant glossary has been read (not assumed).
- At least two edge scenarios were constructed and recorded.
- The resolved term is written in canonical shape in the owning glossary.
- Any code/document disagreement found during the session is recorded.
- No runtime code was modified.
