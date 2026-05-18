# Fix AI Train Commands Through HTTP Gateway

**Created**: 2026-05-14

## Goal
AI train commands (soldier/scout) reach the gRPC Step call when going through the HTTP gateway, so that combat units are produced in HTTP→gRPC mode just as they are in engine-direct mode.

## Scope
- **Files to modify**: `simcore/http_gateway.py`, `simcore/construction.py`
- **Files to create**: none

## Phases

### Phase 1: Fix _UNIT_TYPE_MAP lowercase keys
- [ ] Step 1.1: Add `'scout': 'Wraith'` to `_UNIT_TYPE_MAP` in construction.py (Terran scout = Wraith)
- [ ] Step 1.2: Verify no other lowercase keys are missing (compare with AI agent's unit_type values)
- **Validates with**: `python3 -m py_compile simcore/construction.py`

### Phase 2: Fix HTTP gateway AI command injection
- [ ] Step 2.1: Trace how AI agent commands are collected in http_gateway.py step loop
- [ ] Step 2.2: Find why train commands from AI are dropped before gRPC Step call
- [ ] Step 2.3: Fix the command injection / deduplication logic
- **Validates with**: `python3 -m py_compile simcore/http_gateway.py`

### Phase 3: End-to-end verification
- [ ] Step 3.1: Start gRPC server + HTTP gateway
- [ ] Step 3.2: Run 300-tick test, verify P2 produces soldiers and/or scouts
- [ ] Step 3.3: Run `make test` — all tests pass
- **Validates with**: `make test`