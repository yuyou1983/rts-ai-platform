# RTS Multi-Language Greenfield Template

Complete scaffolding for an AI Native RTS game development platform with four-layer
decoupled architecture (SimCore → AgentHub → Harness → Pipeline).

## Project Characteristics

- **Multi-language**: Python (SimCore, agents, ML) + GDScript (Godot frontend) + Protobuf (protocol)
- **Engine-agnostic**: SimCore is a Python headless engine; Godot is a thin rendering shell
- **Agent-driven**: AgentScope for runtime multi-agent orchestration; claude-game-studios for dev-side codegen
- **Deterministic replay**: SimCore produces deterministic state snapshots for training and replay

## Directory Structure

```
rts-ai-platform/
├── proto/                          # L0: Protocol definitions (Protobuf + gRPC)
│   ├── obs.proto                   # Observation messages
│   ├── cmd.proto                   # Command messages
│   └── state.proto                 # State snapshot messages
├── simcore/                        # L1: Python headless game engine
│   ├── __init__.py
│   ├── engine.py                   # Main game loop + tick system
│   ├── state.py                    # Immutable state snapshots
│   ├── rules.py                    # Rule engine (movement, combat, fog-of-war)
│   ├── entities.py                 # Unit, building, resource entities
│   ├── mapgen.py                   # Procedural map generation
│   └── replay.py                   # Deterministic replay recorder/player
├── agents/                         # L2: AI agents
│   ├── __init__.py
│   ├── base_agent.py               # AgentScope ReActAgent wrapper
│   ├── script_ai.py                # Baseline scripted AI (rule-based)
│   ├── tactical_agent.py           # LLM-powered tactical agent
│   └── trainer/                    # RL training (Trinity-RFT / TRL)
│       ├── reward.py
│       └── train_loop.py
├── godot/                          # L3: Godot 4.4.1 frontend
│   ├── project.godot
│   ├── scenes/
│   │   ├── main_menu.tscn
│   │   ├── battle_field.tscn
│   │   └── hud_overlay.tscn
│   ├── scripts/
│   │   ├── battle_field.gd         # Scene controller (thin shell)
│   │   ├── hud_overlay.gd          # UI binding
│   │   └── grpc_bridge.gd         # gRPC client to SimCore
│   └── addons/                     # Godot addons
├── harness/                        # Agent Harness infrastructure
│   ├── config/
│   │   └── environment.json        # Runtime ecosystem contract
│   ├── tasks/                      # Task state tracking
│   ├── memory/                     # Episodic memory store
│   └── trace/                      # Verification traces
├── scripts/                        # Dev/lint scripts
│   ├── lint_deps.py                # Architecture dependency linter
│   └── lint_quality.py             # Code quality linter
├── docs/                           # Documentation
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── design-docs/
│   └── exec-plans/
│       ├── active/
│       └── completed/
├── tests/                          # Test suite
│   ├── simcore/
│   ├── agents/
│   └── integration/
├── CLAUDE.md                       # Dev-side agent config
├── AGENTS.md                       # Agent navigation map
├── Makefile                        # Build/lint/test targets
├── pyproject.toml                  # Python project config
├── production/
│   └── stage.txt                   # Milestone marker (M0/M1/M2)
└── README.md
```

## pyproject.toml

```toml
[project]
name = "rts-ai-platform"
version = "0.1.0"
description = "AI Native RTS Game Development Platform — 2D headless trainable replayable batch-simulatable RTS combat sandbox"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "Apache-2.0"}
dependencies = [
    "protobuf>=5.0",
    "grpcio>=1.60",
    "grpcio-tools>=1.60",
    "agentscope>=0.1",
    "numpy>=1.26",
    "pydantic>=2.5",
]

[project.optional-dependencies]
train = [
    "torch>=2.2",
    "trl>=0.12",
    "trinity-rft>=0.1",
]
dev = [
    "pytest>=8.0",
    "pytest-xdist>=3.5",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q -n 4"
```

## Makefile

```makefile
.PHONY: build test lint lint-arch format clean proto

# ─── Protocol Buffers ──────────────────────────────────────
proto:
	python -m grpc_tools.protoc -Iproto \
		--python_out=simcore/proto_out \
		--grpc_python_out=simcore/proto_out \
		proto/*.proto

# ─── Python ────────────────────────────────────────────────
build: proto
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -q -n 4

lint: lint-arch
	ruff check .
	mypy simcore/ agents/ --ignore-missing-imports

lint-arch:
	@echo "Checking architecture constraints..."
	@python3 scripts/lint_deps.py simcore/ agents/ proto/
	@python3 scripts/lint_quality.py .
	@echo "✓ Architecture checks passed"

format:
	ruff format .

clean:
	rm -rf __pycache__ .mypy_cache .pytest_cache
	rm -rf simcore/proto_out
```

## SimCore Engine Stub

### simcore/engine.py

```python
"""RTS SimCore — Headless deterministic game engine.

Produces immutable state snapshots per tick. No rendering, no I/O delays.
Designed for: parallel batch simulation, deterministic replay, RL training.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from simcore.state import GameState
from simcore.rules import RuleEngine


class AgentInterface(Protocol):
    """Protocol for agent integration — AgentScope ReActAgent implements this."""
    def decide(self, obs: dict) -> dict: ...


@dataclass
class SimCore:
    """Main game engine loop. Tick-based, deterministic, headless."""

    tick_rate: float = 20.0  # ticks per second
    max_ticks: int = 10_000
    rule_engine: RuleEngine = field(default_factory=RuleEngine)

    _tick: int = field(default=0, init=False)
    _state: GameState = field(default=None, init=False)
    _replay: list[dict] = field(default_factory=list, init=False)

    def initialize(self, map_seed: int = 42, config: dict | None = None) -> None:
        """Initialize game state from seed + config (deterministic)."""
        from simcore.mapgen import generate_map
        self._state = generate_map(seed=map_seed, config=config or {})
        self._tick = 0
        self._replay = [self._state.to_snapshot()]

    def step(self, commands: list[dict]) -> GameState:
        """Advance one tick: apply commands → resolve rules → snapshot state."""
        self._tick += 1
        self._state = self.rule_engine.apply(self._state, commands, self._tick)
        self._replay.append(self._state.to_snapshot())
        return self._state

    def run(self, agents: list[AgentInterface]) -> GameState:
        """Run full game loop with agent decisions each tick."""
        self.initialize()
        while self._tick < self.max_ticks and not self._state.is_terminal:
            obs = self._state.get_observations()
            commands = [a.decide(o) for a, o in zip(agents, obs)]
            self.step(commands)
        return self._state

    @property
    def replay(self) -> list[dict]:
        """Full replay trace — can be replayed deterministically."""
        return list(self._replay)
```

### simcore/state.py

```python
"""Immutable game state snapshots for deterministic replay."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GameState:
    """Frozen game state — each tick produces a new snapshot."""
    tick: int
    entities: dict[str, Any] = field(default_factory=dict)
    fog_of_war: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, int] = field(default_factory=dict)
    is_terminal: bool = False

    def to_snapshot(self) -> dict:
        return {
            "tick": self.tick,
            "entities": self.entities,
            "fog_of_war": self.fog_of_war,
            "resources": self.resources,
            "is_terminal": self.is_terminal,
        }

    def get_observations(self) -> list[dict]:
        """Generate per-player observations (respecting fog-of-war)."""
        # TODO: implement fog-of-war filtering per player
        return [{"tick": self.tick, "entities": self.entities}]
```

## Baseline Script AI

### agents/script_ai.py

```python
"""Baseline scripted AI — deterministic rule-based opponent for RL training."""
from __future__ import annotations


class ScriptAI:
    """Simple rule-based RTS AI. No LLM, no learning — pure heuristics."""

    def decide(self, obs: dict) -> dict:
        """Generate commands from observation using heuristic rules."""
        commands = []
        my_units = [e for e in obs.get("entities", {}).values()
                    if e.get("owner") == "self"]

        # Rule 1: Attack nearest enemy if in range
        # Rule 2: Gather resources if idle
        # Rule 3: Build structures if resources sufficient

        return {"commands": commands, "tick": obs.get("tick", 0)}
```

## Architecture Lint Script

### scripts/lint_deps.py

```python
#!/usr/bin/env python3
"""Architecture dependency linter for RTS-AI-Platform.

Enforces four-layer import constraints:
  L0 (proto/) → nothing
  L1 (simcore/) → L0 only
  L2 (agents/) → L0, L1
  L3 (godot/) → L0, L1, L2
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LAYERS = {
    "proto": 0,
    "simcore": 1,
    "agents": 2,
    "godot": 3,
}

FORBIDDEN = {
    0: {"simcore", "agents", "godot"},
    1: {"agents", "godot"},
    2: {"godot"},
    3: set(),
}

errors = 0


def get_layer(filepath: Path) -> int | None:
    for name, layer in LAYERS.items():
        try:
            filepath.relative_to(name)
            return layer
        except ValueError:
            continue
    return None


def check_file(filepath: Path) -> None:
    global errors
    file_layer = get_layer(filepath)
    if file_layer is None:
        return

    source = filepath.read_text()
    tree = ast.parse(source, filename=str(filepath))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            mod = alias.name.split(".")[0]
            mod_layer = LAYERS.get(mod)
            if mod_layer is not None and mod in FORBIDDEN.get(file_layer, set()):
                print(
                    f"❌ {filepath}:{node.lineno} "
                    f"imports {alias.name} (L{mod_layer}) "
                    f"from L{file_layer} — forbidden"
                )
                errors += 1


def main() -> None:
    dirs = sys.argv[1:] or ["simcore", "agents", "proto"]
    for d in dirs:
        for p in Path(d).rglob("*.py"):
            check_file(p)
    if errors:
        sys.exit(1)
    print("✓ Architecture checks passed")


if __name__ == "__main__":
    main()
```

## harness/config/environment.json

```json
{
  "version": "2.0",
  "project": {
    "name": "rts-ai-platform",
    "language": "multi",
    "languages": ["python", "gdscript", "protobuf"],
    "frameworks": ["godot-4.4.1", "agentscope", "grpc"],
    "entry_points": {
      "simcore": "python -m simcore.engine",
      "godot": "godot --path godot/ --headless",
      "train": "python -m agents.trainer.train_loop"
    }
  },
  "startup": {
    "command": "python -m simcore.engine",
    "readiness_check": {
      "type": "grpc_health",
      "target": "localhost:50051",
      "timeout_seconds": 10
    }
  },
  "services": [
    {
      "name": "simcore-grpc",
      "type": "grpc_server",
      "port": 50051,
      "required": true,
      "startup": "python -m simcore.grpc_server"
    }
  ],
  "env_vars": [
    {"name": "GRPC_PORT", "default": "50051", "required": false, "description": "SimCore gRPC server port"},
    {"name": "TICK_RATE", "default": "20", "required": false, "description": "Simulation ticks per second"},
    {"name": "MAP_SEED", "default": "42", "required": false, "description": "Deterministic map seed"}
  ],
  "databases": [],
  "architecture": {
    "layers": [
      {"name": "proto", "level": 0, "description": "Protocol definitions — no internal deps"},
      {"name": "simcore", "level": 1, "description": "Headless game engine — depends on proto only"},
      {"name": "agents", "level": 2, "description": "AI agents — depends on proto, simcore"},
      {"name": "godot", "level": 3, "description": "Frontend rendering — depends on all below"}
    ],
    "forbidden_imports": {
      "proto": ["simcore", "agents", "godot"],
      "simcore": ["agents", "godot"],
      "agents": ["godot"]
    }
  }
}
```

## Test Stubs

### tests/simcore/test_engine.py

```python
"""Test SimCore deterministic replay and tick system."""
import pytest
from simcore.engine import SimCore


def test_initialization_deterministic():
    """Same seed → same initial state."""
    engine1 = SimCore()
    engine1.initialize(map_seed=123)
    engine2 = SimCore()
    engine2.initialize(map_seed=123)
    assert engine1._state == engine2._state


def test_replay_deterministic():
    """Same commands → same replay trace."""
    engine = SimCore(max_ticks=100)
    engine.initialize(map_seed=42)
    # Apply same commands
    for _ in range(10):
        engine.step(commands=[])
    replay = engine.replay
    assert len(replay) == 11  # init + 10 ticks
```

### tests/agents/test_script_ai.py

```python
"""Test baseline scripted AI."""
from agents.script_ai import ScriptAI


def test_script_ai_returns_commands():
    ai = ScriptAI()
    obs = {"tick": 1, "entities": {}}
    result = ai.decide(obs)
    assert "commands" in result
    assert "tick" in result
```

## AGENTS.md Template (RTS-Optimized)

```markdown
# RTS-AI-Platform — Agent Navigation Map

> AI Native RTS game platform. Python SimCore headless engine + Godot 4.4.1 frontend.
> Four-layer architecture: Proto(L0) → SimCore(L1) → Agents(L2) → Frontend(L3).

## Quick Start
\`\`\`bash
make build          # Install deps + compile protos
make test           # Run test suite
make lint-arch      # Check import constraints
\`\`\`

## Architecture
| Layer | Dir | Can Import | Cannot Import |
|-------|-----|-----------|---------------|
| L0 Proto | proto/ | stdlib | simcore, agents, godot |
| L1 SimCore | simcore/ | L0 | agents, godot |
| L2 Agents | agents/ | L0, L1 | godot |
| L3 Frontend | godot/ | L0-L2 | — |

## Key Files
- simcore/engine.py — Main game loop
- simcore/state.py — Immutable state snapshots
- agents/base_agent.py — AgentScope ReActAgent wrapper
- proto/obs.proto — Observation protocol

## Commands
- Build: `make build`
- Test: `make test`
- Lint: `make lint-arch`
- Run sim: `python -m simcore.engine`

## M0 Milestone Status
See production/stage.txt and docs/milestones/m0-startup.md
```