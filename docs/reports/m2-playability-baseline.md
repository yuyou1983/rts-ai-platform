# M2 Playability Sprint 01 Baseline Acceptance

**Date:** 2026-08-06
**Starting fixed point:** `31f12668d348024e5e50d78315acae21ee8d8f75`
**Recovery branch:** `codex/m2-playability-sprint-01`
**Verdict:** S0 ACCEPTED; S1 READY

## Scope Recovered

S0 separated the inherited dirty worktree into three reviewable commits:

1. Harness candidate-evidence hardening and its tests.
2. ChatGPT control-plane and Hermes execution-plane governance documents.
3. Godot Start Game red-capable baseline, backend helper, roadmap, and Sprint definition.

The baseline does not claim that Godot owns backend startup. The helper proves the existing backend can serve the expected state; direct Start Game remains the S1 red case.

## Gate Evidence

| Gate | Result | Evidence summary |
|---|---|---|
| Harness test suite | PASS | `tests/harness` collected and passed 357 tests. |
| Changed Harness import lint | PASS | `ruff check --select F,I` reported no errors. |
| Harness validators | PASS | Registry, task, held-out suite, and strict trace validators passed. |
| Architecture boundary | PASS | `make lint-arch` passed; 38 pre-existing print-quality warnings remain. |
| Tracked whitespace check | PASS | `git diff --check` and scoped staged checks passed. |
| Direct Godot Start Game with ports closed | EXPECTED RED | Exit 1; bridge reported HTTP 0 and backend connection loss. |
| Helper-backed Start Game | PASS | Initial state contained 30 entities and non-empty fog-of-war data. |
| Helper ownership cleanup | PASS | Ports 50051 and 8080 were closed after the owning test exited. |
| Helper shell syntax | PASS | `bash -n godot/scripts/run_frontend_backend.sh`. |

The direct and helper-backed Godot runs were serialized and used unique log files. An earlier concurrent run collided in `user://logs`; that was a test-harness artifact rather than a runtime product verdict.

## Independent Review

### Harness Evidence Hardening

- **Standards:** PASS. Changed Python files pass focused Ruff checks and the full Harness suite.
- **Specification:** PASS. Candidate promotion now requires fresh, candidate-bound evidence and held-out fixture coverage.
- **Source truth:** PASS. Candidate IDs, skill overlay hashes, runner provenance, scenario evidence, and fixture validation remain machine-checkable.

### ChatGPT-Hermes Orchestration

- **Standards:** PASS. Task/result templates, ownership boundaries, stop conditions, and final acceptance authority are explicit.
- **Specification:** PASS. ChatGPT routes and independently accepts; Hermes executes one bounded task and self-verifies.
- **Source truth:** Not applicable to runtime behavior; these documents define development governance.

### Godot Bootstrap Baseline

- **Standards:** PASS for a red-capable test scaffold and explicit helper lifecycle.
- **Specification:** PASS as an S0 reproducer only.
- **Source truth:** PASS. The same bridge receives entities and fog once gRPC and HTTP are ready, so S1 should address startup/readiness and visible failure handling, not duplicate SimCore game rules.

## Dirty Worktree Disposition

The following inherited/generated paths were deliberately excluded from S0 commits and left unchanged:

- `harness/output/promotion/promotion_history.jsonl`
- `harness/output/replays/*.jsonl`
- `simcore/proto_out/cmd_pb2.py`
- `simcore/proto_out/cmd_pb2_grpc.py`
- `simcore/proto_out/state_pb2_grpc.py`
- `docs/ai-paradigm-shift-deck-enhanced.html`
- `docs/product-form-ai-era-deck.html`
- `tmp/`
- ignored Godot `*.gd.uid` files

These files are not evidence for S1 and must not enter its result commit.

## Next Gate

S1 must make Start Game own local backend readiness in development mode, preserve externally managed services, expose startup errors, and pass three sequential clean-start runs. Its exact Git fixed point is supplied by ChatGPT in the generated Hermes Task Unit after this report is committed.
