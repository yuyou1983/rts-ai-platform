# Development Guide

## Prerequisites

- **Python**: 3.11+
- **Godot**: 4.4.1 (only needed for frontend work)
- **Protocol Buffers**: `grpcio-tools` (installed via pip)

## Setup

```bash
# Clone and install
git clone <repo-url> && cd rts-ai-platform
make build

# Or manually:
pip install -e ".[dev]"
make proto   # compile protobuf definitions
```

## Build Commands

| Command | What it does |
|---------|-------------|
| `make build` | Install all deps + compile protos |
| `make proto` | Compile `proto/*.proto` → Python stubs |
| `make test` | Run pytest with 4 workers |
| `make lint` | Ruff check + mypy type check |
| `make lint-arch` | Architecture constraint check |
| `make format` | Auto-format with ruff |
| `make sim` | Run headless simulation |
| `make smoke-test` | Run headless smoke battle |
| `make clean` | Remove build artifacts |

## Architecture Constraints

**Critical**: These are enforced by `scripts/lint_deps.py` at CI time.

```
L0 proto/     → imports nothing internal
L1 simcore/   → imports L0 only
L2 agents/    → imports L0, L1
L3 godot/     → imports L0, L1, L2
```

Violations will fail CI. If you need to share code between layers:
1. Put it in `proto/` (L0) if it's a type/protocol definition
2. Put it in a new shared module at the appropriate level
3. Never import downwards

## Testing

### Running Tests

```bash
make test                    # full suite, CI-parity
pytest tests/simcore/ -q     # just SimCore tests
pytest tests/agents/ -q      # just agent tests
pytest -k "test_replay" -v   # specific test pattern
```

### Test Organization

```
tests/
├── simcore/
│   ├── test_engine.py       # Game loop + tick system
│   ├── test_state.py        # State snapshots + immutability
│   ├── test_rules.py        # Rule engine correctness
│   └── test_replay.py       # Deterministic replay verification
├── agents/
│   ├── test_script_ai.py    # Baseline AI behavior
│   └── test_base_agent.py   # AgentScope wrapper
└── integration/
    └── test_smoke_battle.py # Full game loop smoke test
```

### Writing Tests

- Every new module gets a corresponding test file
- Use `pytest` fixtures for SimCore initialization (see `tests/conftest.py`)
- Replay determinism tests: verify same seed + commands → identical state
- Agent tests: verify `decide()` returns valid `cmd.proto` structure

## Code Style

- **Ruff** for formatting and linting (configured in `pyproject.toml`)
- **mypy** for type checking (strict mode for `simcore/`)
- **Docstrings**: All public APIs must have docstrings
- **Type hints**: Required for all function signatures in `simcore/` and `agents/`
- **Immutability**: Game state uses frozen dataclasses — never mutate in place

## Protocol Buffers

### Compiling

```bash
make proto
# Equivalent to:
python -m grpc_tools.protoc -Iproto \
  --python_out=simcore/proto_out \
  --grpc_python_out=simcore/proto_out \
  proto/*.proto
```

### Adding a New Message

1. Define message in `proto/` (L0)
2. Run `make proto` to generate Python stubs
3. Import generated stubs in `simcore/` (L1) or `agents/` (L2)
4. Never import protos from `godot/` — use gRPC bridge instead

## gRPC Server

SimCore exposes a gRPC server for Godot frontend:

```bash
# Start the server
python -m simcore.grpc_server

# Default: localhost:50051
# Configurable via GRPC_PORT env var
```

## Agent Development

### M0: BaselineAgent

Simple rule-based AI. No LLM, no learning. Implements `AgentInterface` protocol:

```python
class AgentInterface(Protocol):
    def decide(self, obs: dict) -> dict: ...
```

### M1+: AgentScope Integration

Agents are AgentScope `ReActAgent` instances orchestrated by `MsgHub`:

```python
from agentscope.agent import ReActAgent
from agentscope.pipeline import MsgHub

coordinator = ReActAgent(name="coordinator", ...)
economy = ReActAgent(name="economy", ...)
combat = ReActAgent(name="combat", ...)

hub = MsgHub(participants=[coordinator, economy, combat])
```

See `docs/architecture/agentscope-integration.md` for full details.

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`):

1. **Lint**: ruff + mypy + architecture lint
2. **Test**: pytest -n 4
3. **Smoke test**: headless battle simulation
4. **Build**: package verification

All checks must pass before merge.