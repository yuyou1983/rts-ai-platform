# Agent Operation Manuals

This directory contains operating manuals for the current RTS-AI-Platform agent workflows.

| Manual | Use When |
|---|---|
| `runtime-agent-operation-manual.md` | Working on game-playing agents under `agents/` and `runtime/`. |
| `simcore-agent-operation-manual.md` | Changing deterministic simulation, rules, protocol, replay, or engine state. |
| `godot-agent-operation-manual.md` | Changing Godot UI, sprites, VFX, fog rendering, HUD, or SC1 presentation mapping. |
| `platform-harness-agent-operation-manual.md` | Running or extending benchmark, league, promotion, telemetry, dashboard, and platform validation. |
| `skill-evolver-hermes-operation-manual.md` | Using Hermes/Codex traces and SkillEvolver to improve `.agents/skills`. |
| `chatgpt-hermes-orchestration-manual.md` | Routing atomic work from ChatGPT to local Hermes, collecting self-verified result envelopes, and performing independent final review. |

Read the architecture report first:

- `docs/architecture/current-platform-architecture-report.md`
- `docs/architecture/adr-chatgpt-hermes-orchestration.md`

Execution templates:

- `docs/agents/templates/hermes-task-unit-template.md`
- `docs/agents/templates/hermes-result-envelope-template.md`
- `docs/agents/templates/agent-handoff-template.md`
