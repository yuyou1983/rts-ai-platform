# OpenBW-Inspired Engine Upgrades — Phased Technical Roadmap

> **For agentic workers:** This is a phased roadmap, NOT a parallel execution plan. Phases are strictly sequential. Within each phase, tasks are ordered by dependency. Do NOT skip phases or parallelize across phases.

**Goal:** Borrow OpenBW's proven engine patterns to upgrade SimCore's determinism, command semantics, replay, terrain, and event capabilities — without breaking the four-layer architecture, existing protocol, or Godot frontend.

**Architecture Constraints (non-negotiable):**
- L1 SimCore never imports L2 Agents or L3 Godot.
- `pos_x` / `pos_y` semantics stay as world coords = tile coords. New coordinate levels are **additive fields**, not semantic replacements.
- All new fields exposed to L2/L3 go through proto/HTTP versioning. No Python-only dict smuggling.
- Every new feature has a feature flag for rollback.
- Determinism gate: same seed + same command stream → same `state_hash`, always.

**Tech Stack:** Python 3.11, dataclasses, pytest, existing SimCore modules

**Reference Engine:** OpenBW — https://github.com/OpenBW/openbw

---

## Phase 0: Guardrails & ADR

**Gate:** Must complete before any implementation. No code changes to SimCore in this phase.

### 0.1 — ADR: OpenBW-Inspired Upgrades Compatibility Principles

**Files:**
- Create: `docs/architecture/adr-openbw-upgrades.md`

- [ ] **Step 1: Write ADR document**

Document the following decisions:

```markdown
# ADR: OpenBW-Inspired Engine Upgrades

## Decision
Borrow OpenBW's engine patterns (state hash, order queue, event log, 
elevation vision, replay command-sequence) to upgrade SimCore, subject to:

## Compatibility Principles

1. **pos_x/pos_y unchanged.** These are world coords = tile coords.
   New coordinate levels (build_tile, walk_tile, pixel) are ADDITIVE fields.
   Godot continues reading pos_x/pos_y.

2. **Feature flags for every upgrade.**
   - enable_state_hash (default: false)
   - enable_order_queue (default: false)  
   - enable_event_log (default: false)
   - enable_replay_v2 (default: false)
   - enable_elevation (default: false)
   Each flag defaults off. Turning off MUST revert to current behavior.

3. **Protocol versioning.** New fields in state/obs/replay get a 
   `proto_version` field. L2/L3 consumers check version before reading.
   Fields that don't exist in V1 are simply absent.

4. **L1 event log, not L1 callbacks.** SimCore produces an event_log 
   per tick. L2 Agents consume it via obs/replay, never via direct 
   callback subscription into SimCore internals.

5. **Replay dual-track.** V1 (snapshot) and V2 (command+keyframe) 
   coexist. Godot uses V1. Training uses V2. Hash validates V2 replay.

6. **No cross-phase parallelism.** Phases are sequential because 
   later phases depend on earlier ones (Order Queue affects Hash, 
   Elevation depends on coordinate design, Replay V2 depends on Hash).

## New Fields & Protocol Matrix

| Field | Python Internal | proto V1 | proto V2 | Godot | Agent | Harness | Replay V1 | Replay V2 |
|-------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| state_hash | ✅ | ❌ | ✅ | ❌ | ✅ (debug) | ✅ | ❌ | ✅ |
| order_queue | ✅ | ❌ | ✅ | ✅ (read) | ✅ | ✅ | ❌ | ✅ |
| events_this_tick | ✅ | ❌ | ✅ | ✅ (VFX) | ✅ | ✅ | ❌ | ✅ |
| elevation | ✅ | ❌ | ✅ | ✅ (render) | ✅ | ❌ | ❌ | ✅ |
| build_tile_x/y | ✅ | ❌ | ✅ | ✅ (optional) | ❌ | ❌ | ❌ | ✅ |
| walk_tile_x/y | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| replay_commands | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ |
| keyframes | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

V1 = existing proto (no new fields, backward compat)
V2 = extended proto (new optional fields present)
```

- [ ] **Step 2: Commit ADR**

```bash
git add docs/architecture/adr-openbw-upgrades.md
git commit -m "docs: ADR for OpenBW-inspired upgrades compatibility principles"
```

### 0.2 — Deterministic Replay Smoke Test

**Files:**
- Create: `tests/simcore/test_determinism_smoke.py`

- [ ] **Step 1: Write determinism smoke test**

```python
# tests/simcore/test_determinism_smoke.py
"""Baseline determinism test: same seed + same commands → identical state."""
from simcore.engine import SimCore
from simcore.state import GameState


def _run_game(seed: int, max_ticks: int = 500) -> list[dict]:
    """Run a game with ScriptAI, return snapshots."""
    engine = SimCore()
    engine.initialize(map_seed=seed)
    from agents.script_ai import ScriptAI
    ai1, ai2 = ScriptAI(player=1), ScriptAI(player=2)
    snapshots = []
    for _ in range(max_ticks):
        obs = engine.state.get_observations()
        cmds = [ai1.decide(obs[0]), ai2.decide(obs[1])]
        engine.step(cmds)
        snapshots.append(engine.state.to_snapshot())
    return snapshots


def test_same_seed_same_commands_same_replay():
    """Two runs with same seed must produce identical snapshots."""
    run1 = _run_game(seed=42, max_ticks=200)
    run2 = _run_game(seed=42, max_ticks=200)
    assert len(run1) == len(run2)
    for i, (s1, s2) in enumerate(zip(run1, run2)):
        assert s1 == s2, f"Divergence at tick {i}"


def test_different_seed_different_replay():
    """Different seeds must produce different initial states."""
    run_a = _run_game(seed=42, max_ticks=1)
    run_b = _run_game(seed=99, max_ticks=1)
    assert run_a[0] != run_b[0]
```

- [ ] **Step 2: Run test — must PASS (baseline determinism already holds)**

Run: `scripts/run_tests.sh tests/simcore/test_determinism_smoke.py -v`
Expected: PASS — this is a **baseline**, not a new feature.

- [ ] **Step 3: Commit**

```bash
git add tests/simcore/test_determinism_smoke.py
git commit -m "test(simcore): baseline determinism smoke — same seed same replay"
```

### 0.3 — Performance Benchmark Baseline

**Files:**
- Modify: `tests/simcore/test_benchmark.py` (if exists) or create

- [ ] **Step 1: Record 1k/10k tick benchmark**

Run: `python3 -c "from simcore.engine import SimCore; e=SimCore(); e.initialize(42); import time; t=time.time(); [e.step([]) for _ in range(1000)]; print(f'1k ticks: {time.time()-t:.2f}s'); t=time.time(); [e.step([]) for _ in range(10000)]; print(f'10k ticks: {time.time()-t:.2f}s')"`
Record the numbers as baseline.

- [ ] **Step 2: Save benchmark results in test**

```python
# tests/simcore/test_benchmark.py (append)
def test_performance_baseline():
    """1k ticks must complete in <2s, 10k in <20s (baseline for future phases)."""
    import time
    engine = SimCore()
    engine.initialize(map_seed=42)
    t = time.time()
    for _ in range(1000):
        engine.step([])
    elapsed_1k = time.time() - t
    assert elapsed_1k < 2.0, f"1k ticks took {elapsed_1k:.2f}s (baseline <2s)"
```

- [ ] **Step 3: Commit**

```bash
git add tests/simcore/test_benchmark.py
git commit -m "test(simcore): performance baseline for future phase comparison"
```

**Phase 0 Gate:** ADR written ✓ | Determinism smoke passes ✓ | Benchmark baseline recorded ✓

---

## Phase 1: State Hash & Replay Validation (Low Risk, High Value)

**Depends on:** Phase 0 complete
**Risk:** Low — purely additive, no existing behavior changed
**Scope:** `simcore/hash.py` (new), `simcore/state.py`, `simcore/engine.py`, `simcore/replay.py`

### 1.1 — FNV-1a 64-bit State Hash

**Files:**
- Create: `simcore/hash.py`
- Create: `tests/simcore/test_hash.py`
- Modify: `simcore/state.py` (add `state_hash()` method)

- [ ] **Step 1: Write failing tests**

```python
# tests/simcore/test_hash.py
from simcore.hash import fnv1a_64


def test_fnv1a_known_empty():
    """FNV-1a 64-bit: empty string = 0xcbf29ce484222325."""
    assert fnv1a_64(b"") == 0xCBF29CE484222325


def test_fnv1a_deterministic():
    assert fnv1a_64(b"hello") == fnv1a_64(b"hello")


def test_fnv1a_different():
    assert fnv1a_64(b"aaa") != fnv1a_64(b"aab")


def test_state_hash_deterministic():
    from simcore.state import GameState
    gs = GameState(tick=1, entities={"u1": {"hp": 50}}, fog_of_war={}, resources={"p1": 100})
    assert gs.state_hash() == gs.state_hash()


def test_state_hash_changes():
    from simcore.state import GameState
    gs1 = GameState(tick=1, entities={"u1": {"hp": 50}}, fog_of_war={}, resources={"p1": 100})
    gs2 = GameState(tick=1, entities={"u1": {"hp": 49}}, fog_of_war={}, resources={"p1": 100})
    assert gs1.state_hash() != gs2.state_hash()


def test_state_hash_float_normalization():
    """Floats must be normalized to avoid spurious hash differences."""
    from simcore.state import GameState
    gs1 = GameState(tick=1, entities={"u1": {"pos_x": 1.0}}, fog_of_war={}, resources={})
    gs2 = GameState(tick=1, entities={"u1": {"pos_x": 1.000000000001}}, fog_of_war={}, resources={})
    # With float normalization, these should hash the same
    assert gs1.state_hash() == gs2.state_hash()
```

- [ ] **Step 2: Implement fnv1a_64 and GameState.state_hash()**

```python
# simcore/hash.py
"""FNV-1a 64-bit hash for deterministic game state verification."""

_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x00000100000001B3
_MASK64 = (1 << 64) - 1


def fnv1a_64(data: bytes) -> int:
    h = _FNV_OFFSET
    for byte in data:
        h ^= byte
        h = (h * _FNV_PRIME) & _MASK64
    return h
```

In `simcore/state.py`, add `state_hash()` with **float normalization**:

```python
def state_hash(self) -> int:
    """Deterministic 64-bit hash. Floats normalized to 4 decimal places."""
    import json
    from simcore.hash import fnv1a_64
    
    snapshot = self.to_snapshot()
    # Canonical JSON with float normalization
    data = json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                      default=_normalize_float).encode("utf-8")
    return fnv1a_64(data)


def _normalize_float(obj):
    """Round floats to 4 decimal places for hash stability."""
    if isinstance(obj, float):
        return round(obj, 4)
    raise TypeError(f"Unserializable type: {type(obj)}")
```

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add simcore/hash.py simcore/state.py tests/simcore/test_hash.py
git commit -m "feat(simcore): FNV-1a state hash with float normalization"
```

### 1.2 — Hash Recording in Engine with Feature Flag

**Files:**
- Modify: `simcore/engine.py`
- Modify: `tests/simcore/test_hash.py`

- [ ] **Step 1: Add feature flag and hash recording**

In `simcore/engine.py`:

```python
@dataclass
class SimCore:
    # ... existing fields ...
    enable_state_hash: bool = False  # feature flag

    def step(self, commands: list[dict]) -> GameState:
        # ... existing pipeline ...
        
        # After constructing new state:
        if self.enable_state_hash:
            snapshot = self._state.to_snapshot()
            snapshot["state_hash"] = self._state.state_hash()
            self._replay[-1] = snapshot  # replace last appended
```

- [ ] **Step 2: Write test**

```python
def test_engine_hash_with_flag_on():
    from simcore.engine import SimCore
    engine = SimCore(enable_state_hash=True)
    engine.initialize(map_seed=42)
    engine.step([])
    assert "state_hash" in engine.replay[-1]


def test_engine_hash_off_by_default():
    from simcore.engine import SimCore
    engine = SimCore()
    engine.initialize(map_seed=42)
    engine.step([])
    assert "state_hash" not in engine.replay[-1]
```

- [ ] **Step 3: Run full suite**

- [ ] **Step 4: Commit**

```bash
git add simcore/engine.py tests/simcore/test_hash.py
git commit -m "feat(simcore): state hash recording with enable_state_hash flag"
```

### 1.3 — Multi-Run Hash Consistency Test

**Files:**
- Modify: `tests/simcore/test_determinism_smoke.py`

- [ ] **Step 1: Add hash-based determinism test**

```python
def test_multi_run_hash_consistency():
    """Run same game twice, verify every tick's state_hash matches."""
    from simcore.engine import SimCore
    from agents.script_ai import ScriptAI

    def _run_with_hash(seed: int, ticks: int = 200) -> list[int]:
        engine = SimCore(enable_state_hash=True)
        engine.initialize(map_seed=seed)
        ai1, ai2 = ScriptAI(player=1), ScriptAI(player=2)
        hashes = []
        for _ in range(ticks):
            obs = engine.state.get_observations()
            cmds = [ai1.decide(obs[0]), ai2.decide(obs[1])]
            engine.step(cmds)
            hashes.append(engine.replay[-1].get("state_hash", 0))
        return hashes

    h1 = _run_with_hash(seed=42)
    h2 = _run_with_hash(seed=42)
    assert h1 == h2, "Same seed produced different hashes across runs"
```

- [ ] **Step 2: Run test**

- [ ] **Step 3: Commit**

```bash
git add tests/simcore/test_determinism_smoke.py
git commit -m "test(simcore): multi-run hash consistency determinism gate"
```

### 1.4 — Replay Re-Execution Validation

**Files:**
- Modify: `simcore/replay.py`
- Create: `tests/simcore/test_replay_validation.py`

- [ ] **Step 1: Write replay re-execution test**

```python
# tests/simcore/test_replay_validation.py
def test_replay_reexecution_matches_live():
    """Record a live game, re-execute its commands, verify hashes match."""
    from simcore.engine import SimCore
    from agents.script_ai import ScriptAI

    # --- Live run: record commands and hashes ---
    engine = SimCore(enable_state_hash=True)
    engine.initialize(map_seed=42)
    ai1, ai2 = ScriptAI(player=1), ScriptAI(player=2)
    recorded_commands: list[dict] = []
    live_hashes: list[int] = []
    for _ in range(200):
        obs = engine.state.get_observations()
        cmds = [ai1.decide(obs[0]), ai2.decide(obs[1])]
        recorded_commands.append({"tick": engine.tick, "commands": cmds})
        engine.step(cmds)
        live_hashes.append(engine.replay[-1]["state_hash"])

    # --- Replay run: re-execute recorded commands ---
    engine2 = SimCore(enable_state_hash=True)
    engine2.initialize(map_seed=42)
    replay_hashes: list[int] = []
    for cmd_record in recorded_commands:
        engine2.step(cmd_record["commands"])
        replay_hashes.append(engine2.replay[-1]["state_hash"])

    assert live_hashes == replay_hashes, "Replay hashes diverged from live"
```

- [ ] **Step 2: Implement if needed — may already pass due to determinism**

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add tests/simcore/test_replay_validation.py
git commit -m "test(simcore): replay re-execution validation via state hash"
```

**Phase 1 Gate:** hash tests pass ✓ | flag off = no behavior change ✓ | multi-run hash consistent ✓ | replay re-exec matches ✓ | full suite green ✓ | benchmark within 5% of baseline ✓

---

## Phase 2: Order Queue (Narrow Scope, Engine-Internal First)

**Depends on:** Phase 1 (hash must work before we change command semantics)
**Risk:** Medium — changes how commands map to entity behavior
**Scope:** `simcore/order.py` (new), `simcore/commands.py`, `simcore/engine.py`, `simcore/state.py`

**Narrowed scope:**
- Only `move`, `attack`, `gather`, `stop` — no build/train/research yet
- `order_queue` is entity-internal field, NOT exposed to Agents in Phase 2
- Default command behavior unchanged: single command = replace queue
- `queued=true` appends to queue (shift-queue equivalent)

### 2.1 — Order Dataclass and OrderQueue

**Files:**
- Create: `simcore/order.py`
- Create: `tests/simcore/test_order.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/simcore/test_order.py
from simcore.order import Order, OrderQueue


def test_order_fields():
    o = Order(action="move", target_x=5, target_y=5)
    assert o.action == "move"
    assert o.target_x == 5


def test_queue_replace():
    """Default: new command replaces entire queue (right-click behavior)."""
    q = OrderQueue()
    q.append(Order(action="gather", target_id="m1"))
    q.replace(Order(action="move", target_x=10, target_y=10))
    assert q.current().action == "move"
    assert len(q) == 1


def test_queue_append():
    """queued=true: append to queue, don't interrupt current."""
    q = OrderQueue()
    q.append(Order(action="move", target_x=5, target_y=5))
    q.append(Order(action="attack", target_id="e1"))  # queued
    assert q.current().action == "move"  # still on first
    q.complete_current()
    assert q.current().action == "attack"  # auto-resume next


def test_queue_auto_resume():
    """After current order completes, next in queue starts."""
    q = OrderQueue()
    q.append(Order(action="gather", target_id="m1"))
    q.append(Order(action="attack", target_id="e1"))
    q.complete_current()  # attack done
    assert q.current().action == "gather"  # resume gathering


def test_queue_idle():
    q = OrderQueue()
    assert q.current() is None
    assert q.is_idle


def test_queue_interruption():
    """Attack interrupt: push attack on top, resume after."""
    q = OrderQueue()
    q.append(Order(action="gather", target_id="m1"))
    q.interrupt(Order(action="attack", target_id="e1"))
    assert q.current().action == "attack"  # attack is active
    q.complete_current()  # attack finishes
    assert q.current().action == "gather"  # auto-resume
```

- [ ] **Step 2: Implement Order and OrderQueue**

```python
# simcore/order.py
"""Unit order queue — inspired by OpenBW order stack, adapted for RTS semantics.

Key difference from OpenBW's LIFO stack: we use a FIFO queue with interrupt,
because RTS players think in terms of "current command + shift-queued commands",
not a stack.

Semantics:
  - replace:  clear queue, push new (right-click / default)
  - append:   add to end of queue (shift-click / queued=true)  
  - interrupt: push on top of current, auto-resume previous when done
  - complete_current: finish current, advance to next in queue
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Order:
    """A single unit order."""
    action: str  # "move", "attack", "gather", "stop"
    target_id: str = ""
    target_x: float = 0.0
    target_y: float = 0.0
    metadata: dict = field(default_factory=dict)


class OrderQueue:
    """FIFO order queue with interrupt/replace/append semantics."""

    def __init__(self) -> None:
        self._queue: list[Order] = []  # index 0 = front (next to execute)
        self._interrupted: list[Order] = []  # interrupted orders (resume stack)

    def current(self) -> Optional[Order]:
        """Active order, or None if idle."""
        if self._queue:
            return self._queue[0]
        if self._interrupted:
            return self._interrupted[-1]
        return None

    def replace(self, order: Order) -> None:
        """Clear everything, set new current (right-click behavior)."""
        self._queue.clear()
        self._interrupted.clear()
        self._queue.append(order)

    def append(self, order: Order) -> None:
        """Add order to end of queue (shift-queue behavior)."""
        self._queue.append(order)

    def interrupt(self, order: Order) -> None:
        """Push order as active. Current order is saved for auto-resume."""
        if self._queue:
            saved = self._queue.pop(0)
            self._interrupted.append(saved)
        elif self._interrupted:
            pass  # already interrupted, keep the stack
        self._queue.insert(0, order)

    def complete_current(self) -> None:
        """Mark current order as done. Resume next or interrupted."""
        if self._queue:
            self._queue.pop(0)
        elif self._interrupted:
            self._interrupted.pop()
        # else: idle, nothing to do

    @property
    def is_idle(self) -> bool:
        return self.current() is None

    def __len__(self) -> int:
        return len(self._queue) + len(self._interrupted)

    def to_dict(self) -> list[dict]:
        """Serialize for state snapshots."""
        all_orders = self._interrupted + self._queue
        return [
            {"action": o.action, "target_id": o.target_id,
             "target_x": o.target_x, "target_y": o.target_y}
            for o in all_orders
        ]

    @classmethod
    def from_dict(cls, data: list[dict]) -> OrderQueue:
        q = cls()
        for d in data:
            q.append(Order(
                action=d["action"], target_id=d.get("target_id", ""),
                target_x=d.get("target_x", 0.0), target_y=d.get("target_y", 0.0),
            ))
        return q
```

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add simcore/order.py tests/simcore/test_order.py
git commit -m "feat(simcore): OrderQueue with replace/append/interrupt/auto-resume"
```

### 2.2 — Integrate OrderQueue into Entity Dicts with Feature Flag

**Files:**
- Modify: `simcore/engine.py`
- Modify: `tests/simcore/test_order.py`

- [ ] **Step 1: Write integration test**

```python
def test_entity_order_queue_with_flag():
    """order_queue appears on entities only when flag is on."""
    from simcore.engine import SimCore
    # Flag off (default)
    engine = SimCore()
    engine.initialize(map_seed=42)
    engine.step([])
    first_entity = next(iter(engine.state.entities.values()))
    assert "order_queue" not in first_entity

    # Flag on
    engine2 = SimCore(enable_order_queue=True)
    engine2.initialize(map_seed=42)
    engine2.step([])
    first_entity2 = next(iter(engine2.state.entities.values()))
    assert "order_queue" in first_entity2


def test_order_queue_replace_semantics():
    """Default command = replace queue."""
    from simcore.engine import SimCore
    engine = SimCore(enable_order_queue=True)
    engine.initialize(map_seed=42)
    workers = {eid: e for eid, e in engine.state.entities.items()
               if e.get("entity_type") == "worker" and e.get("owner") == 1}
    wid = next(iter(workers))
    # First: gather
    engine.step([{"action": "gather", "unit_id": wid, "target_id": "mineral_0", "issuer": 1}])
    # Second: move (replaces gather)
    engine.step([{"action": "move", "unit_id": wid, "target_x": 10, "target_y": 10, "issuer": 1}])
    entity = engine.state.entities[wid]
    assert entity["order_queue"][0]["action"] == "move"
    assert len(entity["order_queue"]) == 1  # gather was replaced


def test_order_queue_queued_semantics():
    """queued=true appends without replacing."""
    from simcore.engine import SimCore
    engine = SimCore(enable_order_queue=True)
    engine.initialize(map_seed=42)
    workers = {eid: e for eid, e in engine.state.entities.items()
               if e.get("entity_type") == "worker" and e.get("owner") == 1}
    wid = next(iter(workers))
    engine.step([{"action": "move", "unit_id": wid, "target_x": 5, "target_y": 5, "issuer": 1}])
    engine.step([{"action": "attack", "unit_id": wid, "target_id": "enemy_1", "issuer": 1, "queued": True}])
    entity = engine.state.entities[wid]
    orders = entity["order_queue"]
    assert len(orders) == 2
    assert orders[0]["action"] == "move"   # current
    assert orders[1]["action"] == "attack"  # queued
```

- [ ] **Step 2: Add flag + integration to engine.py**

Add to SimCore: `enable_order_queue: bool = False`

In `step()`, when flag is on, process commands through OrderQueue:

```python
# After validating commands, when enable_order_queue:
if self.enable_order_queue:
    for cmd in valid:
        eid = cmd.get("unit_id") or cmd.get("attacker_id", "")
        if eid and eid in entities:
            q = OrderQueue.from_dict(entities[eid].get("order_queue", []))
            new_order = Order(action=cmd["action"], target_id=cmd.get("target_id", ""),
                              target_x=cmd.get("target_x", 0), target_y=cmd.get("target_y", 0))
            if cmd.get("queued"):
                q.append(new_order)
            else:
                q.replace(new_order)
            entities[eid]["order_queue"] = q.to_dict()
```

When flag is off, entity dicts don't get `order_queue` field at all — existing behavior preserved.

- [ ] **Step 3: Run full suite**

- [ ] **Step 4: Commit**

```bash
git add simcore/engine.py tests/simcore/test_order.py
git commit -m "feat(simcore): order queue integration with enable_order_queue flag"
```

**Phase 2 Gate:** order tests pass ✓ | flag off = no order_queue field ✓ | flag on = replace/append work ✓ | full suite green ✓ | benchmark within 5% ✓

---

## Phase 3: Event Log (Not Callback-Driven Agent)

**Depends on:** Phase 2 (order completions produce events)
**Risk:** Low-Medium — purely additive, but needs pipeline care
**Scope:** `simcore/events.py` (new), `simcore/engine.py`

**Design principle:** SimCore produces `events_this_tick: list[dict]`. This is appended to state snapshot. L2 Agents read it from obs. No L1→L2 callback wiring.

### 3.1 — Event Types and Engine Emission

**Files:**
- Create: `simcore/events.py`
- Create: `tests/simcore/test_events.py`
- Modify: `simcore/engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/simcore/test_events.py
def test_event_log_in_snapshot():
    """When flag on, each snapshot contains events_this_tick."""
    from simcore.engine import SimCore
    engine = SimCore(enable_event_log=True)
    engine.initialize(map_seed=42)
    engine.step([])
    snap = engine.replay[-1]
    assert "events_this_tick" in snap
    assert isinstance(snap["events_this_tick"], list)


def test_event_log_off_by_default():
    from simcore.engine import SimCore
    engine = SimCore()
    engine.initialize(map_seed=42)
    engine.step([])
    assert "events_this_tick" not in engine.replay[-1]


def test_unit_destroyed_event():
    """When a unit dies, event appears in the log."""
    from simcore.engine import SimCore
    engine = SimCore(enable_event_log=True, enable_state_hash=True)
    engine.initialize(map_seed=42)
    # Force a kill by modifying HP directly
    enemies = [eid for eid, e in engine.state.entities.items()
               if e.get("owner") == 2 and e.get("entity_type") == "soldier"]
    if not enemies:
        pytest.skip("No enemy soldiers in initial state")
    eid = enemies[0]
    # We'll need to damage the unit through combat or direct HP set
    # For now, test the event emission mechanism directly
```

- [ ] **Step 2: Implement event types and engine emission**

```python
# simcore/events.py
"""Event log types — produced by SimCore, consumed via obs/replay.

NOT a callback system. SimCore writes events_this_tick into state snapshot.
L2 Agents read from obs. L3 Godot reads from HTTP for VFX triggers.
"""

# Event type constants
UNIT_CREATED = "unit_created"
UNIT_DESTROYED = "unit_destroyed"
UNIT_ATTACKED = "unit_attacked"
BUILDING_COMPLETED = "building_completed"
RESOURCE_DEPLETED = "resource_depleted"
COMBAT_HIT = "combat_hit"
ORDER_COMPLETED = "order_completed"


def make_event(event_type: str, tick: int, **data) -> dict:
    """Create an event dict for the event log."""
    return {"type": event_type, "tick": tick, **data}
```

In `engine.py`, add `enable_event_log: bool = False` flag. When on, accumulate events during step(), write into snapshot:

```python
# At start of step():
events_this_tick: list[dict] = []

# During combat resolution:
if target_hp <= 0:
    if self.enable_event_log:
        events_this_tick.append(make_event(UNIT_DESTROYED, tick=self._tick, unit_id=target_id, killer_id=attacker_id))

# At end of step(), before appending to replay:
if self.enable_event_log:
    snapshot["events_this_tick"] = events_this_tick
```

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add simcore/events.py simcore/engine.py tests/simcore/test_events.py
git commit -m "feat(simcore): event log with enable_event_log flag (not callback-driven)"
```

**Phase 3 Gate:** event log tests pass ✓ | flag off = no events_this_tick ✓ | events appear on unit death / building complete ✓ | full suite green ✓

---

## Phase 4: Replay V2 Dual-Track

**Depends on:** Phase 1 (hash for validation) + Phase 2 (order queue changes replay)
**Risk:** Medium — new storage format, but V1 untouched
**Scope:** `simcore/replay.py`, `simcore/engine.py`

**Design:** V1 snapshot replay stays the default. V2 adds command-sequence recording + periodic keyframes. Hash validates V2 re-execution. Godot continues using V1.

### 4.1 — ReplayV2 Recording

**Files:**
- Modify: `simcore/replay.py` (add ReplayV2 class)
- Modify: `simcore/engine.py` (add V2 recording alongside V1)
- Create: `tests/simcore/test_replay_v2.py`

- [ ] **Step 1: Write tests for ReplayV2 recording**

```python
# tests/simcore/test_replay_v2.py
def test_replay_v2_records_commands():
    """V2 records per-tick commands, not full snapshots."""
    from simcore.replay import ReplayV2
    rec = ReplayV2(seed=42, map_width=64, map_height=64)
    rec.record_tick(1, [{"action": "move", "unit_id": "w1", "target_x": 5, "target_y": 5}])
    rec.record_tick(2, [])
    assert len(rec.commands) == 2

def test_replay_v2_keyframes():
    """V2 records keyframes every N ticks."""
    from simcore.replay import ReplayV2
    rec = ReplayV2(seed=42, map_width=64, map_height=64, keyframe_interval=10)
    for t in range(25):
        rec.record_tick(t, [])
    rec.record_keyframe(10, {"tick": 10, "entities": {}})
    rec.record_keyframe(20, {"tick": 20, "entities": {}})
    assert len(rec.keyframes) == 2

def test_replay_v2_smaller_than_v1():
    """V2 JSON is much smaller than V1 for same game."""
    import json
    from simcore.replay import ReplayV2
    rec = ReplayV2(seed=42, map_width=64, map_height=64)
    for t in range(100):
        rec.record_tick(t, [{"action": "move", "unit_id": "w1", "target_x": t, "target_y": t}])
    v2_size = len(json.dumps(rec.to_dict(), separators=(",", ":")))
    assert v2_size < 3000  # V1 would be ~50KB+

def test_engine_dual_replay():
    """Engine records both V1 and V2 when enable_replay_v2 is on."""
    from simcore.engine import SimCore
    engine = SimCore(enable_replay_v2=True, enable_state_hash=True)
    engine.initialize(map_seed=42)
    for _ in range(10):
        engine.step([])
    assert len(engine.replay) == 11  # V1 still works
    assert engine._replay_v2 is not None
    assert len(engine._replay_v2.commands) == 10  # V2 has commands
```

- [ ] **Step 2: Implement ReplayV2**

```python
# simcore/replay.py — add ReplayV2
@dataclass
class ReplayV2:
    """Compact replay: seed + command sequence + periodic keyframes.
    
    V1 (full snapshot) stays the default for Godot.
    V2 is for training/replay analysis.
    Hash validates V2 re-execution determinism.
    """
    seed: int
    map_width: int
    map_height: int
    config: dict = field(default_factory=dict)
    commands: list[dict] = field(default_factory=list)
    keyframes: dict[int, dict] = field(default_factory=dict)
    keyframe_interval: int = 100

    def record_tick(self, tick: int, cmds: list[dict]) -> None:
        self.commands.append({"tick": tick, "commands": cmds})

    def record_keyframe(self, tick: int, snapshot: dict) -> None:
        self.keyframes[tick] = snapshot

    def to_dict(self) -> dict:
        return {
            "version": 2, "seed": self.seed,
            "map_width": self.map_width, "map_height": self.map_height,
            "config": self.config,
            "commands": self.commands,
            "keyframes": {str(k): v for k, v in self.keyframes.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReplayV2:
        return cls(
            seed=data["seed"], map_width=data["map_width"],
            map_height=data["map_height"], config=data.get("config", {}),
            commands=data.get("commands", []),
            keyframes={int(k): v for k, v in data.get("keyframes", {}).items()},
        )
```

- [ ] **Step 3: Add dual recording to engine.py**

Add `enable_replay_v2: bool = False` flag. When on, record commands into `_replay_v2` alongside existing `_replay` V1.

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git add simcore/replay.py simcore/engine.py tests/simcore/test_replay_v2.py
git commit -m "feat(simcore): ReplayV2 dual-track with command sequence + keyframes"
```

### 4.2 — Replay V2 Re-Execution Validation

- [ ] **Step 1: Write test**

```python
def test_replay_v2_reexecution_matches_live():
    """Re-execute V2 commands, verify state_hash matches live run."""
    # (Similar to Phase 1.4 but using V2 command records instead of ad-hoc recording)
```

- [ ] **Step 2: Implement re-execution in ReplayV2**

Add `replay()` classmethod that takes a SimCore, replays commands, and verifies hashes.

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(simcore): ReplayV2 re-execution validation via state hash"
```

**Phase 4 Gate:** V2 recording works ✓ | V1 untouched ✓ | V2 re-exec hash matches ✓ | Godot still uses V1 ✓ | full suite green ✓

---

## Phase 5: Multi-Coords & Elevation — Design Only, No Implementation

**Depends on:** Phases 0-4 complete
**Risk:** HIGH — touches Godot coords, fog mapping, pathfinding, replay
**Action:** Design document only. No code changes to SimCore.

### 5.1 — Coordinate Compatibility Design

**Files:**
- Create: `docs/architecture/design-multi-coords.md`

- [ ] **Step 1: Write design document**

```markdown
# Design: Multi-Level Coordinate System

## Current State
- pos_x / pos_y = world coords = tile coords (TILE_SIZE=1)
- Godot renders pos_x/pos_y directly
- Pathfinding operates on build_tile grid (64×64)
- Fog-of-war maps world coords to fog grid

## Proposed Addition (NOT replacement)
- Add fields: build_tile_x, build_tile_y (32px grid)
- Add fields: walk_tile_x, walk_tile_y (8px grid)  
- Add fields: pixel_x, pixel_y (sub-tile precision)
- pos_x/pos_y KEPT as-is, derived from build_tile coords

## Migration Path
1. Add new fields as COMPUTED properties (no storage change)
2. Move pathfinding to walk_tile grid
3. Move collision to walk_tile grid
4. Godot reads pos_x/pos_y as before, optionally uses pixel_x/y for smoother rendering
5. Fog mapping updated to use walk_tile grid

## Rollback
- All new fields are computed. Removing computation = revert.
- pos_x/pos_y never change meaning.
```

### 5.2 — Elevation Vision Design

**Files:**
- Create: `docs/architecture/design-elevation-vision.md`

- [ ] **Step 1: Write design document**

```markdown
# Design: Terrain Elevation & Height-Based Vision

## Current State
- Flat map: elevation = 0 everywhere
- Vision: distance-based only (radius check)
- Fog: 3-state (unexplored / explored / visible)

## Proposed
- elevation grid: 2D array on TileMap (build_tile resolution)
  0=low, 1=medium, 2=high
- Vision rule: unit at height H can see tiles at height ≤ H
- Low→high: blocked. High→low: visible.
- Ramp tiles: height=1, allow transition between 0 and 2

## Protocol Impact
- elevation grid included in GameStateSnapshot (V2 proto only)
- Fog update uses elevation check
- Godot renders different tile colors per elevation

## Rollback
- enable_elevation flag. Off = flat map = current behavior.
```

- [ ] **Step 2: Commit designs**

```bash
git add docs/architecture/design-multi-coords.md docs/architecture/design-elevation-vision.md
git commit -m "docs: design documents for multi-coords and elevation (Phase 5, no implementation)"
```

**Phase 5 Gate:** Design documents written ✓ | No SimCore code changed ✓ | ADR updated with coordinate/elevation principles ✓

---

## Rollback Strategy

Every feature has a flag. Turning it off MUST revert to current behavior:

| Flag | Default | Rollback Action |
|------|---------|----------------|
| `enable_state_hash` | `False` | No hash recorded, no hash in snapshot |
| `enable_order_queue` | `False` | No `order_queue` field on entities, single-command behavior |
| `enable_event_log` | `False` | No `events_this_tick` in snapshot |
| `enable_replay_v2` | `False` | V1 snapshot replay only, no V2 recording |
| `enable_elevation` | `False` | Flat map, distance-only vision (Phase 5, design only) |

## Determinism Gate

After every phase, run:

```bash
# Multi-run hash consistency
scripts/run_tests.sh tests/simcore/test_determinism_smoke.py -v

# Performance within 5% of baseline  
scripts/run_tests.sh tests/simcore/test_benchmark.py -v

# Full suite
scripts/run_tests.sh
```

If any gate fails, STOP. Fix before proceeding.

## Execution Order (Strict Sequential)

```
Phase 0 (guardrails)  →  Gate
                        ↓
Phase 1 (hash)        →  Gate
                        ↓
Phase 2 (order queue)  →  Gate
                        ↓
Phase 3 (event log)    →  Gate
                        ↓
Phase 4 (replay V2)    →  Gate
                        ↓
Phase 5 (design only)  →  Done
```

No parallel execution across phases. Within a phase, steps are sequential by dependency.