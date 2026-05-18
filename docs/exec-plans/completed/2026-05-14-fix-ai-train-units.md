# Fix AI Train Units Bug

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Created**: 2026-05-14

## Goal
Fix AI training units bug: train soldier/scout commands are sent by AI but ignored by SimCore backend, resulting in 0 combat units being created via HTTP→gRPC flow.

**Architecture**: The bug is in the command processing path — `construction.py`'s `check_train_prerequisites()` or `check_supply()` is silently rejecting train soldier commands when invoked through the HTTP→gRPC→engine path, even though the same commands work when calling `engine.step()` directly.

**Tech Stack**: Python SimCore, gRPC, Protobuf, aiohttp

## Root Cause Analysis (from prior debugging)

| Symptom | Direct Engine Call | HTTP→gRPC Flow |
|---------|-------------------|---------------|
| Train worker | ✅ Works (30 workers) | ✅ Works (30 workers) |
| Train soldier | ✅ Works (7 soldiers) | ❌ 0 soldiers |
| AI sends train soldier | 329 commands | 329 commands |
| Commands reach engine | Yes | Unknown (need to verify) |

**Already Fixed (in prior sessions):**
1. `engine.py:90` — default `player_races` changed from `{1:"zerg", 2:"protoss"}` to `{1:"terran", 2:"terran"}`
2. `proto/state.proto` — added `repeated int32 production_timers = 22`
3. `grpc_server.py` / `grpc_client.py` — added production_timers serialization/deserialization

**Remaining Bug:**
- `construction.py:575` — `check_train_prerequisites(built, owner, building_id, utype)` may reject "soldier" when called from gRPC path
- Possible causes: `building_type` empty string after gRPC round-trip (proto3 default), or `check_supply()` resource key mismatch

## Scope
- **Files to modify**: `simcore/construction.py`, `simcore/http_gateway.py`
- **Files to create**: None
- **Tests to modify**: `tests/test_http_integration.py` (strengthen assertions for combat units)

## Phases

### Phase 1: Diagnose train soldier rejection point
- [ ] Step 1.1: Add temporary logging to `construction.py:575` (`check_train_prerequisites`) to log which check fails for "soldier" type
- [ ] Step 1.2: Add temporary logging to `construction.py:579` (`check_supply`) to log supply check result
- [ ] Step 1.3: Add temporary logging to `construction.py:596-598` (resource cost check) to log mineral/gas values
- [ ] Step 1.4: Run HTTP→gRPC flow test (500 ticks) and capture logs to identify exact rejection point
- **Validates with**: Manual test via `python3 -c "..."` with log output showing which `continue` fires

### Phase 2: Fix the identified root cause
- [ ] Step 2.1: Apply the fix based on Phase 1 findings (likely `building_type` proto3 empty string, or resource key format mismatch, or supply cap issue)
- [ ] Step 2.2: Remove ALL temporary debug logging from `construction.py` and `http_gateway.py`
- [ ] Step 2.3: Verify `python3 -m py_compile` passes for all modified files
- **Validates with**: `make build && make lint`

### Phase 3: End-to-end verification
- [ ] Step 3.1: Restart gRPC server + HTTP gateway
- [ ] Step 3.2: Run engine-direct test: 500 ticks with CoordinatorAI → verify soldiers > 0
- [ ] Step 3.3: Run HTTP→gRPC test: 500 ticks with AI → verify soldiers > 0
- [ ] Step 3.4: Run `make test` — all integration tests pass
- [ ] Step 3.5: Strengthen test_ai_produces_combat_units to assert soldiers ≥ 1 (not just entities > 6)
- **Validates with**: `make test`