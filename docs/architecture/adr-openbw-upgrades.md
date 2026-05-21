# ADR: OpenBW-Inspired Engine Upgrades

**Status:** Accepted  
**Date:** 2026-05-21  
**Context:** Phase 0 of the OpenBW Engine Upgrades roadmap  
**Supersedes:** —  

---

## Context

RTS-AI-Platform uses a Python SimCore (headless engine) + Godot 4.4.1 frontend with a four-layer architecture:

```
Proto(L0) → SimCore(L1) → Agents(L2) → Frontend(L3)
```

SimCore currently provides deterministic tick-based simulation with immutable `GameState` snapshots (`tick`, `entities`, `fog_of_war`, `resources`, `is_terminal`, `winner`), a full-snapshot replay system (`_replay: list[dict]`), and fog-filtered observations via `get_observations()`. Entities use `pos_x`/`pos_y` as world coordinates. The engine exposes `step(commands) → GameState` and `run(agents) → GameState`.

OpenBW (https://github.com/OpenBW/openbw) demonstrates proven engine patterns that would significantly improve SimCore's determinism guarantees, command semantics, observability, terrain fidelity, and replay efficiency:

| Pattern | OpenBW Proven Value | Current SimCore Gap |
|---------|-------------------|-------------------|
| State hash | Bit-exact replay verification | No hash; divergence detected only by full diff |
| Order queue | Shift-queue, auto-resume | Single command replace; no queuing |
| Event log | Structured per-tick events | No structured event stream |
| Elevation vision | High ground advantage | Binary tile passability (PLAIN/WATER/MOUNTAIN) |
| Replay V2 | Command + keyframe (compact) | Full snapshot every tick |

Borrowing these patterns is desirable but carries risk: any change that breaks the four-layer protocol barrier, alters `pos_x`/`pos_y` semantics, or makes Godot's frontend incompatible would destabilize the entire platform.

---

## Decision

We will borrow OpenBW's engine patterns (state hash, order queue, event log, elevation vision, replay V2) to upgrade SimCore, **subject to six compatibility principles** that guarantee no regression in the existing four-layer architecture, protocol, or Godot frontend.

---

## Compatibility Principles

### CP-1: pos_x / pos_y UNCHANGED — New Coordinates Are Additive

`pos_x` and `pos_y` are world coordinates that equal tile coordinates in the current system. This semantic is **preserved exactly**. Godot reads `pos_x`/`pos_y` today and will continue to do so without modification.

New coordinate levels inspired by OpenBW's multi-resolution coordinate system are introduced as **additive fields** on entity dicts:

| New Field | Unit | Relation to pos_x/pos_y |
|-----------|------|------------------------|
| `build_tile_x` / `build_tile_y` | 32×32 build tile | `= int(pos_x / 32)` |
| `walk_tile_x` / `walk_tile_y` | 8×8 walk tile | `= int(pos_x / 8)` |
| `pixel_x` / `pixel_y` | Sub-tile pixel | `= pos_x` (alias for clarity) |

These fields are **only computed and stored** when `enable_elevation` or a coordinate-aware feature flag is active. When flags are off, entities contain exactly the fields they do today (`pos_x`, `pos_y`, `hp`, `owner`, `entity_type`, `is_idle`, `target_x`, `target_y`, `attack_target_id`, `returning_to_base`, `deposit_pending`, etc.).

**Rationale:** Changing `pos_x`/`pos_y` semantics would require coordinated changes across Godot, all Agents, and the Harness — a coupling violation. Additive fields allow incremental adoption with zero frontend impact.

---

### CP-2: Feature Flags for Every Upgrade — Default Off, Revertible

Each OpenBW-inspired upgrade is guarded by a feature flag on `SimCore`. All flags default to `False`, which **MUST** produce behavior identical to the current engine:

| Flag | Upgrade Phase | Default |
|------|--------------|---------|
| `enable_state_hash` | Phase 1 | `False` |
| `enable_order_queue` | Phase 2 | `False` |
| `enable_event_log` | Phase 3 | `False` |
| `enable_replay_v2` | Phase 4 | `False` |
| `enable_elevation` | Phase 5 | `False` |

**Invariant:** Setting any flag to `False` after it was `True` **MUST** revert to current behavior with no residual state. This means:

- Hash-related fields must not appear in snapshots when `enable_state_hash=False`.
- `order_queue` field must not appear on entities when `enable_order_queue=False`.
- `events_this_tick` must not appear in state/obs when `enable_event_log=False`.
- Replay format must be V1 (snapshot-only) when `enable_replay_v2=False`.
- Elevation data and additive coordinate fields must not appear when `enable_elevation=False`.

Flags are passed at `SimCore()` construction time and are immutable for the lifetime of the engine instance.

**Rationale:** Feature flags provide a safe rollback path and allow incremental testing. If any upgrade causes a regression, toggling the flag off must be sufficient to restore baseline behavior — no code rollback required.

---

### CP-3: Protocol Versioning — V1 Backward Compatible, V2 Opt-In

New fields in state/obs/replay are versioned via a `proto_version` field:

| Version | Semantics |
|---------|-----------|
| V1 | Existing protocol. No new fields present. Identical to today's wire format. Backward compatible. |
| V2 | Extended protocol. New optional fields present (`state_hash`, `order_queue`, `events_this_tick`, `elevation`, additive coordinates, etc.). |

**Rules:**

1. When **all** feature flags are `False`, `proto_version = 1`. The serialized output is byte-identical to today's format.
2. When **any** feature flag is `True`, `proto_version = 2`. New fields are included as optional keys in the dict/JSON output.
3. L2 Agents and L3 Godot **MUST** check `proto_version` before reading new fields. V1 consumers ignore V2 fields naturally (they aren't present).
4. Proto files (`obs.proto`, `cmd.proto`, `state.proto`) add new fields as `optional` with field numbers starting above existing max. V1 protobuf bindings silently drop unknown optional fields.

**Rationale:** Protocol versioning prevents silent breakage. V1 consumers (Godot, existing Agents, Harness) continue working without modification. V2 consumers opt in by reading new fields after checking the version.

---

### CP-4: L1 Event Log, NOT L1 Callbacks

SimCore produces a structured event log per tick as a field on the state snapshot:

```python
events_this_tick: list[dict]  # appended to GameState when enable_event_log=True
```

Example event:
```python
{
    "type": "unit_damaged",
    "tick": 42,
    "entity_id": "marine_3",
    "damage": 8,
    "attacker_id": "zealot_1",
    "new_hp": 12,
}
```

**L2 Agents consume events via `obs` or `replay`, never via direct callback subscription into SimCore internals.**

This means:
- No `on_damage()`, `on_death()`, `on_build_complete()` callback hooks on SimCore.
- No observer pattern, no pub/sub, no event dispatcher within L1.
- Events are data, not control flow. They flow through the same protocol barrier as all other L1→L2 communication.

**Rationale:** Callbacks create tight coupling between L1 and L2. If Agents register callbacks on SimCore objects, the protocol barrier is broken and layering violations become inevitable. An event log preserves the data-flow-only contract: SimCore produces data, Agents consume data, all through the protocol layer.

---

### CP-5: Replay Dual-Track — V1 (Snapshot) and V2 (Command+Keyframe) Coexist

Two replay formats coexist, selected by the `enable_replay_v2` flag:

| Aspect | Replay V1 | Replay V2 |
|--------|-----------|-----------|
| Format | Full `GameState.to_snapshot()` per tick | Commands per tick + periodic keyframes |
| Storage | O(ticks × state_size) | O(ticks × cmd_size + keyframes × state_size) |
| Consumer | Godot frontend (rendering) | Training Harness (RL, analysis) |
| Validation | Full diff comparison | `state_hash` at every tick; keyframe re-execution |
| Playback | Direct snapshot read | Re-execute commands from last keyframe |
| Compatibility | Existing Godot replay player, unchanged | New Harness replay parser |

**Coexistence rules:**
- When `enable_replay_v2=False`, only V1 replay is recorded (current behavior).
- When `enable_replay_v2=True`, V2 replay is recorded **in addition to** V1. Both are available.
- Godot always uses V1 replay. It never reads V2.
- Training Harness uses V2 for compactness. It can fall back to V1 for visualization.
- State hash (from Phase 1) validates V2 replay integrity: re-executing commands from a keyframe must produce matching hashes at every tick.

**Rationale:** V1 replay is simple and sufficient for Godot rendering. V2 replay is essential for training at scale (compact, verifiable). Maintaining both avoids a forced migration and lets each consumer use the optimal format.

---

### CP-6: No Cross-Phase Parallelism — Phases Are Sequential

The five upgrade phases execute strictly sequentially:

```
Phase 1: State Hash          ───► Phase 2: Order Queue
                                       │
                                       ▼
                              Phase 3: Event Log
                                       │
                                       ▼
                              Phase 4: Replay V2
                                       │
                                       ▼
                              Phase 5: Elevation Vision
```

**Dependency chain:**
- **Phase 2 depends on Phase 1:** Order Queue changes how commands map to entity behavior, which changes state. Hash must already be proven stable so we can detect any divergence from queue changes.
- **Phase 3 depends on Phase 2:** Event types reference order completions (`order_complete`, `order_interrupted`). The event schema requires the order queue schema to be finalized.
- **Phase 4 depends on Phase 1:** Replay V2 validates via state hash. Hash must be reliable before V2 replay is trusted.
- **Phase 5 depends on Phase 2 & CP-1:** Elevation vision uses `build_tile_x/y` and `walk_tile_x/y` for terrain lookups. Coordinate additive fields must be designed (CP-1) and order queue must be stable (order targets resolve at specific tile resolution).

**Within each phase**, tasks are also ordered by dependency (write tests → implement → verify gate). No task from a later phase may begin until the current phase's gate passes.

**Rationale:** Parallelizing across phases creates merge conflicts in `engine.py` and `state.py`, makes hash divergence impossible to attribute, and risks cascading rollbacks. Sequential phases ensure each upgrade is independently validated before the next begins.

---

## New Fields & Protocol Matrix

The following table specifies every new field introduced by the OpenBW upgrades, where it exists internally, and which protocol versions and consumers can access it.

| Field | Python Internal Only | proto V1 | proto V2 | Godot | Agent | Harness | Replay V1 | Replay V2 |
|-------|:-------------------:|:--------:|:--------:|:-----:|:-----:|:-------:|:---------:|:---------:|
| `state_hash` | ✅ | ❌ | ✅ | ❌ | ✅ (debug) | ✅ | ❌ | ✅ |
| `order_queue` | ✅ | ❌ | ✅ | ✅ (read) | ✅ | ✅ | ❌ | ✅ |
| `events_this_tick` | ✅ | ❌ | ✅ | ✅ (VFX) | ✅ | ✅ | ❌ | ✅ |
| `elevation` | ✅ | ❌ | ✅ | ✅ (render) | ✅ | ❌ | ❌ | ✅ |
| `build_tile_x` / `build_tile_y` | ✅ | ❌ | ✅ | ✅ (optional) | ❌ | ❌ | ❌ | ✅ |
| `walk_tile_x` / `walk_tile_y` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `pixel_x` / `pixel_y` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `replay_commands` | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ |
| `keyframes` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `proto_version` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Notes:**

- **Python Internal Only = ✅** means the field is computed/stored in Python dataclasses but is excluded from V1 serialization. V1 serialization is `GameState.to_snapshot()` which produces exactly the current keys: `tick`, `entities`, `fog_of_war`, `resources`, `is_terminal`, `winner`.
- **proto V1 = ❌** means the field is absent from the V1 wire format. V1 consumers never see it.
- **proto V2 = ✅** means the field appears as an optional key in the V2 dict/JSON output and as an `optional` field in protobuf definitions.
- **`state_hash`** in Agent column is marked "debug" — Agents may read it for logging/diagnostics but must not use it for decision-making (it would leak full-state information through fog-of-war).
- **`events_this_tick`** in Godot column is marked "VFX" — Godot reads events to trigger visual effects (damage numbers, explosions, build-complete flashes) without polling entity diffs.
- **`replay_commands`** and **`keyframes`** are V2 replay format internals. They are not exposed in the state/obs protocol at all — they exist only in the V2 replay file structure consumed by Harness and Agents during offline analysis.
- **`proto_version`** is the single field that exists in both V1 and V2. In V1 output it is set to `1`. In V2 output it is set to `2`.

---

## Rollback Strategy

Each feature flag maps to a specific rollback behavior. Turning a flag `False` **MUST** restore current (pre-upgrade) behavior with no residual artifacts.

| Feature Flag | Flag = False Behavior | Residual State Check |
|-------------|----------------------|---------------------|
| `enable_state_hash` | `state_hash` key absent from all snapshots and obs dicts. `GameState.state_hash()` method still exists but is never called by engine. No hash computation overhead. | Verify: `"state_hash" not in engine.replay[-1]` after `step()` |
| `enable_order_queue` | Entities use current single-command replace semantics. `order_queue` key absent from entity dicts. Command processing identical to pre-Phase 2. | Verify: `"order_queue" not in entity` for all entities |
| `enable_event_log` | `events_this_tick` key absent from state snapshots and obs dicts. No event collection/computation during tick. | Verify: `"events_this_tick" not in engine.state.to_snapshot()` |
| `enable_replay_v2` | Only V1 replay (full snapshots) recorded. No command log or keyframe data stored. `_replay` format identical to current `list[dict]` of snapshots. | Verify: `len(engine.replay_v2_commands) == 0` if field exists, or `engine.replay_v2` is `None` |
| `enable_elevation` | `elevation` key absent from tile map output and state/obs. Additive coordinate fields (`build_tile_*`, `walk_tile_*`, `pixel_*`) absent from entity dicts. Fog-of-war uses current binary tile passability. | Verify: `"elevation" not in tile_data` and `"build_tile_x" not in entity` |

**Rollback test pattern (applies to every phase):**

```python
def test_feature_flag_off_no_residual():
    """Turning flag off must produce identical output to engine without the flag."""
    engine_off = SimCore()  # all flags default False
    engine_off.initialize(map_seed=42)
    engine_off.step([])

    engine_on_then_off = SimCore(enable_XXX=True)
    engine_on_then_off.initialize(map_seed=42)
    engine_on_then_off.step([])

    # Now create a fresh engine with flag off — must match engine_off
    engine_fresh = SimCore()  # flag off
    engine_fresh.initialize(map_seed=42)
    engine_fresh.step([])

    assert engine_fresh.replay[-1] == engine_off.replay[-1]
```

---

## Determinism Gate

Every phase must pass the following gate before the next phase may begin. The gate is enforced by CI and must be green on the main branch.

| Gate Criterion | Verification Method | Threshold |
|---------------|---------------------|-----------|
| **Multi-run hash consistency** | Run identical game (same seed, same ScriptAI commands) **3 times** with all active flags on; compare `state_hash` at every tick across runs | 0 divergences (100% match) |
| **Performance within 5%** | Benchmark 1k-tick and 10k-tick runs against Phase 0 baseline | Wall-clock time ≤ 1.05× baseline |
| **Full suite green** | `pytest tests/ -q -n 4` | 0 failures |

**Per-phase gate specifics:**

- **Phase 1 (State Hash):** Hash must be identical across 3 runs of 200-tick games. Baseline benchmark recorded in Phase 0. Flag off must show no `state_hash` in output.
- **Phase 2 (Order Queue):** With `enable_order_queue=True`, hash consistency still holds (queue state is part of hash). Single-command behavior (no `queued=true`) must be identical to flag-off behavior. Benchmark within 5%.
- **Phase 3 (Event Log):** Event log does not affect game state → hash must be identical whether `enable_event_log` is True or False (events are observation-only). Benchmark within 5%.
- **Phase 4 (Replay V2):** V2 replay re-execution from keyframes must produce hashes matching live execution at every tick. V1 replay must be unaffected. Benchmark within 5%.
- **Phase 5 (Elevation):** Elevation changes fog computation → different hashes are expected. But multi-run consistency must still hold (same seed + commands → same hash). Flag off must produce pre-Phase-5 hashes. Benchmark within 5%.

**Gate enforcement in CI:**

```yaml
# .github/workflows/ci.yml — add after each phase
- name: Determinism Gate (Phase N)
  run: |
    pytest tests/simcore/test_determinism_smoke.py -v
    pytest tests/simcore/test_hash.py -v
    pytest tests/simcore/test_benchmark.py -v
    pytest tests/ -q -n 4
```

---

## Consequences

### Positive

- **Determinism guarantee:** State hash enables bit-exact replay verification, catching nondeterminism bugs immediately.
- **Command richness:** Order queue enables shift-queue behavior essential for competitive RTS play.
- **Observability:** Event log gives Agents and Godot structured event data for VFX, analytics, and training signals.
- **Replay efficiency:** V2 replay reduces storage by ~10× for long games (commands vs. full snapshots).
- **Terrain fidelity:** Elevation vision adds strategic depth (high-ground advantage, cliff blocking).
- **Zero migration cost:** All upgrades are additive and flag-gated. Existing Godot frontend, Agents, and Harness work unchanged with all flags off.

### Negative

- **Complexity budget:** Five feature flags add configuration surface area. The `SimCore` constructor gains 5 boolean parameters.
- **Dual replay storage:** When `enable_replay_v2=True`, both V1 and V2 replays are stored, temporarily increasing memory until V1 is discarded or V2 replaces V1.
- **Sequential phasing:** No parallelization across phases lengthens the total upgrade timeline. This is deliberate — the dependency chain makes parallelization unsafe.
- **Testing overhead:** Each phase requires rollback tests, determinism gates, and benchmark comparisons. This is the cost of safe incremental upgrades.

### Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Hash instability from float precision | Medium | Float normalization to 4 decimal places in `state_hash()`. Dedicated test for float edge cases. |
| Order queue changes hash even with flag off | Low | Flag off = `order_queue` field absent from entity = identical serialization = identical hash. Verified by test. |
| Event log accidentally mutates state | Low | `events_this_tick` is read-only observation. Enforced by `GameState` being `frozen=True` dataclass. |
| V2 replay divergence | Medium | Hash validation at every tick during V2 replay. Keyframe interval tuned to balance re-execution cost vs. storage. |
| Elevation changes fog too aggressively | Medium | Elevation vision is additive (can see further from high ground). Flag off = binary fog (current). Easy to compare. |
| Cross-layer coupling via events | Low | CP-4 forbids callbacks. Events flow through protocol only. Architecture lint catches direct imports. |

---

## References

- OpenBW engine: https://github.com/OpenBW/openbw
- Exec plan: `docs/exec-plans/2026-05-20-openbw-engine-upgrades.md`
- Four-layer architecture: `docs/architecture/four-layers.md`
- Agent protocols: `docs/architecture/agent-protocols.md`
- SimCore design: `docs/design-docs/simcore-engine.md`
- ADR-2: Protocol isolation (proto + gRPC as sole cross-layer protocol)
- ADR-4: Python headless SimCore (not Unity headless server)