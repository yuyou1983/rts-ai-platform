# RTS-AI-Platform — Agent Navigation Map

> AI Native RTS game platform. Python SimCore headless engine + Godot 4.4.1 frontend.
> Four-layer decoupled architecture: Proto(L0) → SimCore(L1) → Agents(L2) → Frontend(L3).
> Runtime agents orchestrated by AgentScope (MsgHub + Pipeline + ReAct).
> Dev-side agents from claude-game-studios (Godot specialist team).

## Quick Start

```bash
make build          # Install deps + compile protos
make test           # Run test suite
make lint-arch      # Check import constraints
make sim            # Run headless simulation
```

## Architecture

| Layer | Dir | Can Import | Cannot Import |
|-------|-----|-----------|---------------|
| L0 Proto | `proto/` | stdlib only | simcore, agents, godot |
| L1 SimCore | `simcore/` | L0 | agents, godot |
| L2 Agents | `agents/` | L0, L1 | godot |
| L3 Frontend | `godot/` | L0-L2 | — |

**Key invariant**: SimCore never imports Agents. Agents never import Godot.
All cross-layer communication through protobuf + gRPC.

## Key Files

| File | Purpose |
|------|---------|
| `simcore/engine.py` | Main game loop + tick system |
| `simcore/state.py` | Immutable state snapshots |
| `simcore/rules.py` | Rule engine (movement, combat, fog-of-war) |
| `simcore/replay.py` | Deterministic replay recorder |
| `agents/base_agent.py` | AgentScope ReActAgent wrapper |
| `agents/script_ai.py` | Baseline scripted AI (rule-based) |
| `proto/obs.proto` | Observation protocol (world, local, fog) |
| `proto/cmd.proto` | Command protocol (move, attack, build) |
| `proto/state.proto` | State snapshot protocol (replay) |

## Commands

| Command | What it does |
|---------|-------------|
| `make build` | `pip install -e ".[dev]"` + compile protos |
| `make test` | `pytest tests/ -q -n 4` |
| `make lint` | `ruff check . && mypy simcore/ agents/` |
| `make lint-arch` | `python3 scripts/lint_deps.py` + `lint_quality.py` |
| `make sim` | `python -m simcore.engine` (headless) |
| `make proto` | Compile protobuf definitions |

## Agent System

### Runtime Agents (game decisions, AgentScope)

| Agent | Role | M0 | M1 | M2 |
|-------|------|----|----|-----|
| BaselineAgent | Monolithic script AI | ✓ | — | — |
| Coordinator | Strategic coordinator | — | ✓ | ✓ |
| Economy | Resource management | — | ✓ | ✓ |
| Combat | Tactical combat | — | ✓ | ✓ |
| Strategy | Grand strategy | — | — | ✓ |
| Scout | Intelligence/recon | — | — | ✓ |
| Build | Construction/tech | — | — | ✓ |

### Dev-side Agents (code generation, claude-game-studios)

| Agent | Role |
|-------|------|
| godot-specialist | Godot engine architecture lead |
| godot-gdscript-specialist | GDScript expert |
| godot-gdextension-specialist | C++/Rust native binding expert |
| godot-shader-specialist | Shader expert |

See `.claude/agents/` for full definitions.

## Milestone Status

| Phase | Status | File |
|-------|--------|------|
| M0 Startup | 🟡 In Progress | `docs/milestones/m0-startup.md` |
| M1 Multi-Agent | ⬜ Not Started | — |
| M2 Production | ⬜ Not Started | — |

Current stage: `production/stage.txt` = **M0**

## CI

GitHub Actions: `.github/workflows/ci.yml`
- Python 3.11, ruff, mypy, pytest -n 4
- Architecture lint: `make lint-arch`
- Headless smoke battle: `make smoke-test`

## Key Decisions

- **ADR-1**: Gradual agent splitting (M0 mono → M1 3-core → M2 full-6)
- **ADR-2**: Protobuf + gRPC as sole cross-layer protocol
- **ADR-3**: LLM not in high-frequency loop; compile trajectories to deterministic scripts
- **ADR-4**: Python headless SimCore (not Unity headless server)
- **ADR-5**: AgentScope as runtime agent framework (MsgHub + ReAct + Trinity-RFT)