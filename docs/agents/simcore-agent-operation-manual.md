# SimCore Agent Operation Manual

**Audience:** Engineers or agents changing deterministic simulation, protocol, replay, rules, economy, construction, combat, fog, map, or Gym integration.  
**Goal:** Keep SimCore deterministic, testable, and isolated from Agents/Godot.

---

## Ownership

SimCore workflow owns:

- `proto/*.proto`
- `simcore/engine.py`
- `simcore/state.py`
- `simcore/rules.py`
- `simcore/economy.py`
- `simcore/construction.py`
- `simcore/movement.py`
- `simcore/pathfinder.py`
- `simcore/map.py`
- `simcore/mapgen.py`
- `simcore/replay.py`
- `simcore/recorder.py`
- `simcore/spells.py`
- `simcore/upgrades.py`
- `simcore/gym_env.py`
- `tests/simcore/*`

It may read `agents/` only to understand command consumers. It must not import from `agents/`.

---

## Non-Negotiable Rules

- SimCore never imports Agents.
- SimCore never imports Godot.
- Same seed plus same command sequence must produce same replay.
- `GameState` snapshots should remain serializable and replay-friendly.
- Fog-filtered observations must not leak invisible enemy data.
- Feature flags must be additive and revertible.
- Existing `pos_x` and `pos_y` semantics must not change without a formal ADR.

---

## Standard Change Workflow

1. **Classify the change.**

   | Change Type | Primary Files | Required Tests |
   |---|---|---|
   | Combat formula | `simcore/rules.py`, `data/combat.json` | `tests/simcore/test_combat.py` |
   | Economy/gathering | `simcore/economy.py`, `simcore/rules.py` | `tests/simcore/test_gas_loop.py`, engine tests |
   | Construction/tech | `simcore/construction.py`, `data/buildings/*` | construction, morph, upgrade tests |
   | Fog/visibility | `simcore/state.py`, `simcore/rules.py` | `tests/simcore/test_fog.py`, cloak tests |
   | Replay/determinism | `simcore/replay.py`, `simcore/hash.py`, `simcore/engine.py` | replay, hash, determinism tests |
   | Protocol | `proto/*.proto`, generated bindings | proto compile, integration tests |

2. **Write or update tests first.**

   Prefer tests that build a tiny `GameState` or short `SimCore` scenario.

3. **Implement with no cross-layer imports.**

   If AI behavior is needed, inject a factory from `runtime/`, not from `simcore/`.

4. **Run focused tests.**

   ```bash
   python3 -m pytest tests/simcore/ -q -x
   ```

5. **Run protocol generation if proto changed.**

   ```bash
   make proto
   ```

6. **Run architecture lint.**

   ```bash
   python3 scripts/lint_deps.py simcore/ agents/ runtime/ proto/
   ```

---

## Determinism Checklist

Before completing a SimCore task:

- [ ] No unseeded random calls were added.
- [ ] Entity iteration order is stable or order-independent.
- [ ] Float outputs are normalized when used in state hashes.
- [ ] Replay output is stable for repeated same-seed runs.
- [ ] Tests compare behavior, not incidental dict ordering.

Recommended commands:

```bash
python3 -m pytest tests/simcore/test_hash.py tests/simcore/test_replay_v2.py tests/simcore/test_determinism_smoke.py -q
python3 -m pytest tests/simcore/ -q -x
```

---

## Protocol Change Rules

When changing `proto/*.proto`:

- Add optional/new fields instead of changing existing field meaning.
- Do not reuse field numbers.
- Keep Python dict adapters backward-compatible.
- Update gRPC conversion code in `simcore/grpc_server.py` and `simcore/grpc_client.py`.
- Update Godot/HTTP consumers only through documented response fields.

Run:

```bash
make proto
python3 -m pytest tests/test_http_integration.py -q -x
```

---

## Common Failure Modes

| Failure | Cause | Fix |
|---|---|---|
| `lint_deps.py` fails | SimCore imported `agents/*` | Move import to `runtime/` and inject callback. |
| Replay mismatch | Nondeterministic order or random source | Sort keys, seed random, add hash tests. |
| Godot shows wrong entity | State field changed without manifest/bridge update | Keep old fields, add new fields, update bridge docs. |
| AI sees hidden enemy | Observation filtering bypassed | Route through `GameState.get_observations()`. |
| Training action invalid | Gym action decoder drifted from command validator | Update `simcore/gym_env.py` and command tests together. |

---

## Completion Gate

Minimum gate for SimCore changes:

```bash
python3 scripts/lint_deps.py simcore/ agents/ runtime/ proto/
python3 -m pytest tests/simcore/ -q -x
python3 -m pytest tests/agents/test_script_ai.py -q -x
```

Add integration tests when changing gRPC/HTTP/Gym:

```bash
python3 -m pytest tests/test_http_integration.py tests/test_http_harness.py -q -x
python3 -m pytest tests/simcore/test_gym_env.py -q -x
```

