# Hermes Result Envelope

## Identity

- Task ID: `sprint-m2-playability-01-s1-start-game-local-backend`
- Agent run ID: `20260807_140304_d9daa3`
- Status: `PASS`
- Start fixed point: `b62ef1d1fef0f2eac5943aea183020d7ce943c55`
- End HEAD: `f20352a499fce72235d1e48b10a92e2621313f5a`

## Outcome

Implemented automatic local SimCore backend bootstrap in the Godot frontend's
"Start Game" flow. When the user clicks Start Game, `grpc_bridge.gd` now checks
if gRPC port 50051 and HTTP gateway port 8080 are already open (external
service). If not, it launches `run_frontend_backend.sh` via `OS.execute()`,
waits up to 12 seconds for both ports to become ready, then sends the start_game
HTTP request. On exit, the owned backend process group is killed via
`OS.kill(-pid)`. If bootstrap fails or the connection is lost, `game_view.gd`
shows a visible error overlay with a "Back to Menu" button — never showing an
empty GameView. One controlled retry is implemented for transient HTTP failures.

## Changed Files

- `godot/scripts/grpc_bridge.gd` — Core bootstrap logic: signals, port checking, process launch/kill, retry, cleanup on exit
- `godot/scripts/game_view.gd` — Error overlay UI, signal connections, `_game_active` gating
- `godot/scripts/test_start_game_bootstrap.gd` — Rewritten e2e test for bootstrap flow
- `tests/godot/test_frontend_bootstrap_contract.py` — New: 15 contract tests (24 cases with parametrize) for static GDScript verification
- `scripts/verify_frontend_bootstrap.py` — New: verification harness for 3 clean-start runs + external preservation test
- `harness/output/godot/bootstrap-runs.json` — Evidence: structured test results
- `harness/output/godot/qa-report-s1-bootstrap.md` — Evidence: QA report

Forbidden paths changed: `no`

## Acceptance Results

- [x] Start Game auto-bootstraps local backend (gRPC 50051, HTTP 8080) — PASS — 3/3 clean-start runs in bootstrap-runs.json
- [x] Waits for readiness with timeout — PASS — _is_port_open() with 12s poll loop, contract test verifies timeout logic
- [x] Retries on failure — PASS — One controlled retry in _on_request_completed(), contract test verifies retry logic
- [x] Cleans up on exit — PASS — Ports closed after all 3 runs, _kill_owned_backend() with process group kill
- [x] Error overlay if bootstrap fails — PASS — _on_bootstrap_failed() in game_view.gd, contract test verifies overlay creation
- [x] Never shows empty GameView — PASS — Error overlay shown before any game content, connection_lost also triggers overlay
- [x] External service preservation — PASS — External-preservation run: Godot used existing service, did not kill it on exit

## Verification Evidence

| Command | Exit code | Result | Evidence |
|---|---:|---|---|
| `Godot --headless --path godot --check-only --quit` | 0 | PASS | No parse errors, Godot v4.6.2.stable |
| `python3 -m pytest tests/godot/test_frontend_bootstrap_contract.py` | 0 | PASS | 24 passed in 1.36s |
| `python3 scripts/verify_frontend_bootstrap.py --runs 3 --require-cleanup` | 0 | PASS | 3/3 clean-start + 1/1 external preservation, all ports cleaned |
| `Godot --headless --script scripts/test_start_game_bootstrap.gd` (RED, pre-impl) | 1 | RED | /tmp/rts-s1-red-evidence.log |
| `Godot --headless --script scripts/test_start_game_bootstrap.gd` (GREEN, post-impl) | 0 | GREEN | /tmp/rts-s1-green3.log — "PASS: Start Game received 30 entities and fog-of-war data" |

## Scope Check

- Diff base: `b62ef1d1fef0f2eac5943aea183020d7ce943c55`
- Actual changed paths:
  - `godot/scripts/grpc_bridge.gd`
  - `godot/scripts/game_view.gd`
  - `godot/scripts/test_start_game_bootstrap.gd`
  - `tests/godot/test_frontend_bootstrap_contract.py`
  - `scripts/verify_frontend_bootstrap.py`
  - `harness/output/godot/bootstrap-runs.json`
  - `harness/output/godot/qa-report-s1-bootstrap.md`
- Unrelated dirty paths preserved: `none`
- Scope verdict: `PASS`

## Deviations And Risks

- Assumptions: `run_frontend_backend.sh` accepts positional args `(grpc_port, http_port, seed)` — verified by reading the script. macOS does not have `timeout` command — used Python subprocess timeout and Godot `--quit` instead.
- Spec deviations: None. All S1 acceptance criteria from `sprint-m2-playability-01.md` are met.
- Residual risks: `OS.kill(-pid)` process group kill relies on the backend script being in its own process group. If macOS changes process group behavior in future OS updates, child Python processes could be orphaned. The verify harness catches this via port cleanup checks.
- Rollback: `git revert f20352a` restores prior state where Start Game requires manual backend launch.

## Blocker

None.

## Next Command

```bash
cd /Users/yuyou/code/rts-ai-platform && git fetch && git checkout hermes/hermes-66659200 && python3 scripts/verify_frontend_bootstrap.py --runs 3 --require-cleanup
```

## Executor Self-Verdict

`PASS` because all 7 S1 acceptance criteria are met with TDD evidence (RED→GREEN), 24/24 contract tests pass, 3/3 clean-start runs + 1/1 external preservation run all pass with port cleanup verified. This is an executor verdict and requires ChatGPT final review.
