# External Source Note: mattpocock/skills

## Source Repository
- URL: https://github.com/mattpocock/skills
- Pinned commit: `2ab958093e83e0ec752e6c1c5932da465bf23e0c`
- License: MIT (https://opensource.org/licenses/MIT)
- Copyright: Matt Pocock

## Methods Adapted
1. Invocation separation — user vs model-composable skills
2. Domain glossary — bounded-context terminology
3. Tracer-bullet tickets — vertical slice fixtures with blockers and seams
4. Tight debugging loops — red-capable, minimise, one-hypothesis-at-a-time
5. Dual-axis review — independent Standards and Specification verdicts
6. Structured handoff — temporary context transfer artifact
7. Progressive disclosure — completion criteria and composition semantics
8. Explicit completion criteria — externally checkable success conditions

## Files Influenced
- harness/skills/schema.json — invocation_mode, skill_kind, composes, completion_criteria
- harness/skills/registry.json — 22 migrated + 2 new (domain-modeling, handoff)
- .agents/skills/code-review/SKILL.md — Standards/Specification/Source Truth axes
- .agents/skills/harness-run/SKILL.md — tight feedback loop
- .agents/skills/sprint-plan/SKILL.md — vertical ticket semantics
- .agents/skills/domain-modeling/SKILL.md — new skill
- .agents/skills/handoff/SKILL.md — new skill
- CONTEXT-MAP.md — project context boundaries
- docs/domain/ — four bounded-context glossaries
- harness/skills/tasks/schema.json — vertical ticket fields
- harness/evolve/held_out.py — candidate-aware validation

## Attribution Statement
No runtime AgentScope logic, SimCore engine code, Godot scripts, or protobuf definitions are derived from the external repository. The external methods are adapted to the existing RTS development-skill registry, trace, auditor, held-out, and promotion pipeline. The external repository is not copied into this project. All adaptations preserve the original MIT license attribution.
