# SimCore Engine Design

## Overview

SimCore is the headless deterministic game engine at L1 of the four-layer architecture. It implements pure game logic without any rendering or I/O, enabling:

- **Deterministic replay**: Same seed + commands → identical state
- **Parallel batch simulation**: 32-64 concurrent instances for RL training
- **Headless operation**: No GPU or display required
- **Protocol isolation**: Communicates exclusively via protobuf + gRPC

## Core Design

### Tick-Based Architecture

```
Tick N:
  1. Receive commands from AgentHub (via gRPC)
  2. Parse and validate commands against cmd.proto
  3. Apply movement rules
  4. Resolve combat encounters
  5. Process resource gathering
  6. Handle construction/production
  7. Update fog-of-war per player
  8. Check win/loss conditions
  9. Emit new GameState snapshot (frozen)
  10. Append snapshot to replay buffer
```

### State Immutability

Every tick produces a **new frozen GameState** — the old state is never mutated. This guarantees:

- Safe parallel reads (multiple agents observe same state)
- Deterministic replay (snapshots are serializable)
- No race conditions in multi-threaded simulation

### Entity Component Model

Entities use frozen dataclasses with explicit types:

| Entity | Key Fields |
|--------|-----------|
| `Unit` | id, owner, position, health, speed, attack, carry |
| `Building` | id, owner, position, health, production_queue |
| `Resource` | id, position, resource_type, amount |

### Rule Resolution Order

Rules are applied in a strict order to maintain determinism:

1. **Command validation** — reject invalid/out-of-range commands
2. **Movement** — update positions, check collisions
3. **Combat** — resolve attacks in attack-range order
4. **Economy** — process gathering, spending
5. **Construction** — advance build timers
6. **Fog-of-war** — update visibility per player
7. **Terminal check** — win/loss/draw detection

### Map Generation

Procedural from seed: `generate_map(seed, config) → GameState`

- Resource placement, spawn points, terrain — all deterministic
- Config allows tuning: map size, resource density, starting units

## gRPC Interface

SimCore exposes a gRPC server (default port 50051):

```protobuf
service SimCoreService {
  rpc StartGame(GameConfig) returns (stream GameStateUpdate);
  rpc Step(StepRequest) returns (GameState);
  rpc GetReplay(ReplayRequest) returns (stream GameStateSnapshot);
}
```

## Performance Targets (M0)

| Metric | Target |
|--------|--------|
| Single-instance tick rate | 20 ticks/sec |
| Parallel instances | 32-64 |
| Replay overhead | < 5% of tick time |
| Memory per instance | < 50MB |
| Crash rate | < 2% |