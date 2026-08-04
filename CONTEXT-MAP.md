# RTS-AI-Platform Context Map

> Bounded-context map for the RTS-AI-Platform. Each context owns a canonical
> glossary. Terms must not drift across contexts; when a term is shared, the
> glossary of the context that owns the concept is authoritative.

## Dependency Direction (Restated)

```text
Proto -> SimCore -> Agents -> Frontend/Godot
Development Harness observes all layers but promoted skill patches cannot mutate runtime business code.
```

---

## Bounded Contexts

### 1. SimCore

| Field | Value |
|---|---|
| **Owner** | team-simcore |
| **Canonical glossary** | `docs/domain/simcore-context.md` |
| **Scope** | Headless game engine: game loop, rules, state, determinism, replay |
| **Permitted dependencies** | Proto (L0) only. Must not import Agents or Godot. |
| **Inbound consumers** | Agents (L2), Frontend/Godot (L3) via protobuf + gRPC |

### 2. Godot Presentation

| Field | Value |
|---|---|
| **Owner** | godot-specialist |
| **Canonical glossary** | `docs/domain/godot-presentation-context.md` |
| **Scope** | Visual rendering, sprites, animation, VFX, input feedback |
| **Permitted dependencies** | Proto (L0), SimCore (L1), Agents (L2). Must not change SimCore rules. |
| **Inbound consumers** | Development Harness (visual validation commands) |

### 3. Skill Harness

| Field | Value |
|---|---|
| **Owner** | harness-executor (cross-cutting) |
| **Canonical glossary** | `docs/domain/skill-harness-context.md` |
| **Scope** | Skill trials, candidate patches, traces, auditors, held-out suites, promotion |
| **Permitted dependencies** | Observes all layers. May read and test any layer but **promoted skill patches cannot mutate runtime business code** (`simcore/`, `agents/`, `godot/scripts/`, `proto/`). |
| **Inbound consumers** | SkillEvolver, gate-check, promotion pipeline |

### 4. SC1 Source Truth

| Field | Value |
|---|---|
| **Owner** | cross-cutting (reference integrity) |
| **Canonical glossary** | `docs/domain/sc1-source-truth-context.md` |
| **Scope** | Original game data semantics: weapon IDs, unit stats, overlay mappings, reference artifacts |
| **Permitted dependencies** | Read-only reference. No code in any layer may import or embed SC1 proprietary assets. |
| **Inbound consumers** | SimCore (rule validation), Godot Presentation (asset alignment), Skill Harness (reference checks) |

---

## Cross-Context Rules

1. **One glossary per concept.** When a term appears in multiple contexts, each
   glossary must cross-reference the owning context's definition and must not
   silently redefine it.

2. **No implementation detail in glossaries.** Glossary entries contain domain
   meaning only — no file paths, function signatures, implementation plans, or
   mutable task status.

3. **Domain changes are documentation, not code.** Resolving a term updates the
   relevant glossary immediately. If the choice is hard to reverse, surprising,
   and involves a real trade-off, raise an ADR via the `architecture-decision`
   skill — do not embed the decision in code.

4. **Harness observes, does not mutate.** The Skill Harness may read and test
   any layer, but a promoted skill patch that touches runtime business code
   (`simcore/`, `agents/`, `godot/scripts/`, `proto/`) must be routed to a
   separate `harness-run` implementation task, not applied during promotion.
