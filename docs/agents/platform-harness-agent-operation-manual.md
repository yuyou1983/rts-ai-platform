# Platform Harness Agent Operation Manual

**Audience:** Agents operating benchmark, league, promotion, telemetry, replay, dashboard, and platform validation.  
**Goal:** Turn gameplay and agent changes into repeatable evidence.

---

## Ownership

Platform/harness workflow owns:

- `harness/pool.py`
- `harness/benchmark.py`
- `harness/league.py`
- `harness/promotion.py`
- `harness/telemetry.py`
- `harness/output/*`
- `scripts/run_benchmark.py`
- `scripts/run_league.py`
- `scripts/gen_replay.py`
- `scripts/verify_gameplay.py`
- `platform/dashboard/*`
- `tests/harness/*`
- `tests/train/*`
- `tests/test_http_harness.py`

---

## Operating Modes

| Mode | Purpose | Primary Commands |
|---|---|---|
| Smoke | Confirm one short game works | `make smoke-test`, `python3 scripts/smoke_mvp.py` |
| Core test | Fast non-socket regression | `make test-core` |
| Integration | gRPC/HTTP behavior | `make test-integration` |
| Benchmark | Many games, summary stats | `python3 scripts/run_benchmark.py` |
| League | Agent version pool and ELO | `python3 scripts/run_league.py` |
| Promotion | Decide whether candidate advances | `python3 -m pytest tests/harness/test_promotion.py -q` |
| Dashboard | Platform UI | `cd platform/dashboard && npm run dev` |

---

## Standard Validation Workflow

1. **Define the evidence question.**

   Examples:

   - Did the agent win rate improve?
   - Did illegal command rate increase?
   - Did replay determinism regress?
   - Did promotion gate accept the candidate with enough confidence?
   - Did Godot-visible state still match SimCore state?

2. **Choose the smallest test matrix.**

   Start with:

   ```text
   seeds: 42, 43, 44
   maps: default procedural
   matchups: baseline vs baseline, candidate vs baseline
   max_ticks: 1000 or 5000 depending on feature
   ```

3. **Run focused tests first.**

   ```bash
   python3 -m pytest tests/harness/ -q -x
   ```

4. **Run smoke or benchmark.**

   ```bash
   python3 scripts/run_benchmark.py
   ```

5. **Record results.**

   Use files under:

   - `harness/output/benchmark_stats.json`
   - `harness/output/benchmark_report.txt`
   - `harness/output/replays/`
   - `harness/output/promotion/promotion_history.jsonl`

6. **Summarize with a decision.**

   Use:

   ```text
   PASS: promote / keep change
   CONCERNS: keep but add blockers
   FAIL: rollback or do not merge
   ```

---

## Promotion Gate Checklist

Before promoting an agent or gameplay change:

- [ ] Candidate beats baseline above configured threshold.
- [ ] Confidence interval is acceptable.
- [ ] No crash or timeout regression.
- [ ] Illegal command rate does not increase.
- [ ] Determinism tests pass.
- [ ] Replay samples are available for inspection.
- [ ] Godot presentation is checked if player-facing behavior changed.

Recommended commands:

```bash
python3 -m pytest tests/harness/test_promotion.py tests/harness/test_league.py tests/harness/test_pool.py -q
python3 scripts/run_benchmark.py
```

---

## Dashboard Workflow

Current dashboard status: React/Vite skeleton with mock data.

When extending dashboard:

1. Add API shape first.
2. Add a read-only adapter over existing `harness/output/`.
3. Replace mock data in pages.
4. Add loading/error/empty states.
5. Add charts after data path is real.

Suggested first real endpoints:

| Endpoint | Source |
|---|---|
| `GET /api/matches` | `harness/output/replays/` |
| `GET /api/matches/:id` | replay JSON/JSONL |
| `GET /api/benchmark/latest` | `harness/output/benchmark_stats.json` |
| `GET /api/league/ranking` | `harness/league.py` or gateway league API |
| `GET /api/promotion/history` | `harness/output/promotion/promotion_history.jsonl` |

Dashboard validation:

```bash
cd platform/dashboard
npm run build
```

---

## Report Template

Use this structure for platform run summaries:

```markdown
# Platform Validation Report

## Scope
- Change under test:
- Commit/branch:
- Date:

## Commands
- `python3 -m pytest ...`
- `python3 scripts/run_benchmark.py`

## Results
| Metric | Baseline | Candidate | Verdict |
|---|---:|---:|---|
| Win rate | | | |
| Crash count | | | |
| Avg ticks | | | |
| Illegal commands | | | |
| Replay mismatch | | | |

## Decision
PASS / CONCERNS / FAIL

## Follow-ups
- Concrete next action.
```

---

## Do Not Do

- Do not promote based on one seed.
- Do not compare runs with different maps/config unless documented.
- Do not hide failed tests behind benchmark averages.
- Do not edit SimCore rules from a platform-only task.
- Do not make dashboard mock data look like real experiment evidence.

