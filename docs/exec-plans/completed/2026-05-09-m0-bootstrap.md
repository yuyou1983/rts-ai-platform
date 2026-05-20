# M0 Bootstrap: Protocol + SimCore + Baseline AI + Replay

**Created**: 2026-05-09

## Goal
Complete M0 milestone: protocol v1, headless SimCore, baseline script AI, replay system, CI pipeline — all connected end-to-end.

## Scope
- **Files to create**: proto/obs.proto, proto/cmd.proto, proto/state.proto, simcore/grpc_server.py, godot/project.godot (scaffold)
- **Files to modify**: simcore/engine.py (wire protobuf), agents/script_ai.py (complete heuristics), simcore/replay.py (protobuf serialization)

## Phases

### Phase 1: Protocol v1
- [ ] Define obs.proto (WorldObservation, LocalObservation, FogState)
- [ ] Define cmd.proto (Move, Attack, Build, Gather, Research)
- [ ] Define state.proto (GameStateSnapshot, EntityState)
- [ ] Compile protos → Python stubs
- **Validates with**: `make proto && python -c "from simcore.proto_out import obs_pb2"`

### Phase 2: SimCore Core
- [ ] Complete engine.py (wire protobuf types)
- [ ] Implement rules.py (movement, combat, economy)
- [ ] Implement mapgen.py (seed-based generation)
- [ ] Add replay.py protobuf serialization
- [ ] Write tests: test_engine.py, test_state.py, test_rules.py, test_replay.py
- **Validates with**: `make test`

### Phase 3: Baseline AI
- [ ] Complete script_ai.py heuristics (gather → build → attack)
- [ ] Wire AgentInterface protocol
- [ ] Write test_script_ai.py
- **Validates with**: `make test`

### Phase 4: CI + Smoke Test
- [ ] Complete .github/workflows/ci.yml
- [ ] Add smoke-test target to Makefile
- [ ] Verify: push → green CI
- **Validates with**: `make lint-arch && make lint && make test && make smoke-test`

### Phase 5: Godot Scaffold
- [ ] Create godot/project.godot
- [ ] Create minimal scenes (main_menu, battle_field)
- [ ] Add grpc_bridge.gd skeleton
- **Validates with**: `godot --headless --path godot/ --quit`