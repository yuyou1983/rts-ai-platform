# SimCore Bounded-Context Glossary

> Owner: **team-simcore**
> Scope: headless game engine — game loop, rules, state, determinism, replay.
> Permitted dependencies: Proto (L0) only.

---

## Authoritative Game State

Definition: the single immutable snapshot of the entire simulation at a given
tick, against which all layers — agents, frontend, replay — must reconcile.

Not the same as: Presentation State (a visual approximation that may lag or
omit hidden information) or any per-client observation.

Boundary example: two clients receive fog-of-war observations that differ, but
both must reconcile to the same Authoritative Game State when fog lifts.

---

## CombatEvent

Definition: a discrete, fully-resolved occurrence within a simulation tick in
which one entity applies damage or an effect to another entity, including the
attacker, target, weapon, and resulting state delta.

Not the same as: a visual effect or animation triggered in the presentation
layer, which is a rendering consequence and not the authoritative record.

Boundary example: a unit fires a projectile that is still in flight when the
tick ends — the CombatEvent is recorded at the tick the damage is applied, not
when the visual projectile appears.

---

## Determinism

Definition: the property that feeding the same ordered sequence of inputs and
seed into the simulation produces byte-identical game state at every tick,
enabling exact replay and reproducible testing.

Not the same as: visual smoothness or frame-rate stability, which are
presentation-layer concerns and do not affect the simulation outcome.

Boundary example: two runs on different machines with the same seed and input
sequence produce the same state hash; a run that uses wall-clock time or
unseeded randomness breaks Determinism even if the gameplay "feels" the same.

---

## Production Entity

Definition: a game object within the simulation that is capable of producing
or training other entities, governed by queue, cost, and timing rules.

Not the same as: a Presentation Asset (the visual representation of the
building) or a generic "unit" (which may be produced but cannot itself
produce).

Boundary example: a Hatchery is a Production Entity because it queues larva
spawning; a Zergling is not a Production Entity even though it exists in the
same game state.

---

## Tick

Definition: the atomic, fixed-duration step of the simulation loop during which
all rules are evaluated and state transitions occur exactly once.

Not the same as: a rendered frame, which is a presentation-layer cadence that
may run faster or slower than the simulation tick.

Boundary example: the simulation may run at 22 ticks per second while the
frontend renders at 60 frames per second — multiple frames interpolate between
two consecutive ticks.

---

## Replay Hash

Definition: a deterministic digest of the complete game state at a specific
tick, used to verify that two runs produced identical simulations.

Not the same as: a file checksum of the replay recording, which validates
storage integrity but not simulation equivalence.

Boundary example: two replays with identical state hashes but different file
sizes (due to compression) are considered simulation-equivalent; two replays
with the same file checksum but different state hashes are not.

---

## Fog of War

Definition: the simulation rule that determines which portion of the
Authoritative Game State is observable by a given player at a given tick,
restricting visibility based on entity sight ranges and terrain.

Not the same as: a visual fog or darkness overlay rendered by the
presentation layer, which is a rendering of the fog state and not the rule
itself.

Boundary example: a player's scout reveals terrain that remains visible
(terrain memory) even after the scout leaves — the scout's sight no longer
covers that area, but terrain visibility persists by rule.
