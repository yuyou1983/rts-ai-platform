# Runtime Agent Operation Manual

**Audience:** Agent engineers working on `agents/` and `runtime/`.  
**Goal:** Improve game-playing agents without breaking SimCore determinism or the four-layer boundary.

---

## Ownership

Runtime agents own:

- `agents/script_ai.py`
- `agents/coordinator.py`
- `agents/sub_agents.py`
- `agents/economy.py`
- `agents/combat.py`
- `agents/scout.py`
- `agents/race_ai_base.py`
- `agents/react_adapter.py`
- `agents/game_loop.py`
- `runtime/agent_factory.py`
- `runtime/auto_step.py`
- `runtime/gym_ai.py`
- `tests/agents/*`

Runtime agents may read `simcore/` and `proto/` for contract understanding, but should not change SimCore rules unless the task is explicitly escalated to the SimCore workflow.

---

## Architecture Contract

The runtime agent path is:

```text
GameState.get_observations()
  -> CoordinatorAgent.decide(obs)
  -> EconomyAgent / CombatAgent / ScoutAgent
  -> merged command list
  -> SimCore.step(commands)
```

Hard constraints:

- Agents may import `proto/` and `simcore/`.
- Agents must not import Godot.
- SimCore must not import agents.
- Do not put LLM calls in per-tick high-frequency loops.
- Return deterministic commands for deterministic observations unless the task explicitly adds controlled stochasticity.
- Every command must include legal issuer/player ownership information.

---

## Agent Roles

| Agent | Current Role | Typical Output |
|---|---|---|
| `ScriptAI` | M0 fallback baseline | Gather, train, build, attack commands. |
| `CoordinatorAgent` | M1 orchestrator | Budget split, command merge, dedup. |
| `EconomyAgent` | Workers, resources, production basics | Gather/build/train commands. |
| `CombatAgent` | Unit production and attacks | Attack/train/move commands. |
| `ScoutAgent` | Recon and retreat | Move commands based on fog and health. |
| `ReactGameAgent` | Experimental LLM adapter with heuristic fallback | JSON parsed commands. |

---

## Standard Workflow

1. **Define the target behavior.**

   Write it as an observable test condition, for example:

   ```text
   Given idle workers and visible minerals, EconomyAgent issues gather commands.
   Given nearby enemy attacking base, Coordinator shifts budget toward combat.
   Given damaged scout, ScoutAgent retreats to base.
   ```

2. **Add or update a focused test.**

   Use `tests/agents/` for agent logic. Prefer direct observations over full-game tests unless coordination requires full integration.

3. **Implement in the narrowest agent.**

   - Economy behavior goes in economy agent.
   - Combat target choice goes in combat agent.
   - Cross-agent resource allocation goes in coordinator.
   - Race-specific behavior goes in `race_ai_base.py` or the race-specific AI file.

4. **Run agent tests.**

   ```bash
   python3 -m pytest tests/agents/ -q -x
   ```

5. **Run a deterministic integration smoke.**

   ```bash
   python3 -m pytest tests/agents/test_multi_agent.py -q -x
   python3 -m pytest tests/simcore/test_determinism_smoke.py -q -x
   ```

6. **Run architecture lint after touching imports.**

   ```bash
   python3 scripts/lint_deps.py simcore/ agents/ runtime/ proto/
   ```

---

## Command Output Rules

Agents should output command dicts shaped like:

```python
{"action": "gather", "worker_id": "worker_1", "resource_id": "mineral_1", "issuer": 1}
{"action": "move", "unit_id": "marine_1", "target_x": 32.0, "target_y": 40.0, "issuer": 1}
{"action": "attack", "attacker_id": "marine_1", "target_id": "enemy_1", "issuer": 1}
{"action": "build", "builder_id": "worker_1", "building_type": "barracks", "pos_x": 12.0, "pos_y": 10.0, "issuer": 1}
{"action": "train", "building_id": "base_p1", "unit_type": "worker", "issuer": 1}
```

Do not emit commands for entities not owned by the agent's player.

---

## When To Escalate

Escalate to SimCore workflow if the agent needs:

- a new action type,
- new state fields,
- new command validation,
- new fog/visibility semantics,
- new combat/economy rule semantics,
- replay format changes.

Escalate to Godot workflow if the issue is:

- sprite not shown,
- health bar/selection ring misaligned,
- VFX missing,
- HUD button missing,
- minimap or fog rendering wrong.

---

## Validation Checklist

Before marking a runtime agent task complete:

- [ ] Agent tests pass.
- [ ] Determinism smoke passes if behavior affects full-game decisions.
- [ ] `lint_deps.py` passes or the failure is explicitly unrelated and documented.
- [ ] No Godot imports were added.
- [ ] No per-tick LLM call was added.
- [ ] Commands include issuer and legal entity IDs.

