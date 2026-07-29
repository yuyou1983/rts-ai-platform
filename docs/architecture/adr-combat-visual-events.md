# ADR: Authoritative Combat Visual Events

> Status: Accepted
> Date: 2026-07-29
> Related plan: `docs/plans/2026-07-29-sc1-combat-differentiation-execution-plan.md`

## Context

The RTS-AI-Platform previously rendered combat purely by *inferring* events from
HP deltas and state diffs in Godot (`combat_visual_controller.gd`,
`vfx_manager.gd`).  This produced several systemic problems:

- Godot guessed attacker / weapon / multiplier from after-the-fact deltas,
  duplicating resolution logic and losing causality.
- `gRPC GameStateSnapshot` carried no combat events, so HTTP/Godot clients had
  no authoritative combat channel.
- Cooldown field mismatches (`attack_cooldown` vs `cooldown_timer`) and
  shield naming (`shield` vs `shields`) caused missed or double triggers.
- Replays could not re-derive visuals deterministically because the facts
  never left SimCore.

SC1 combat differentiation requires each attack cycle to surface a stable,
semantic, cross-layer event so that Godot only *interprets* facts rather than
*reconstructing* them.

## Decision

- SimCore owns combat facts.  Weapons, hits, shields, splash, chain bounces and
  deaths are resolved in the headless engine; the result is the single source
  of truth.
- Proto transports semantic `CombatEvent` records.  The `GameStateSnapshot`
  carries a `repeated CombatEvent combat_events` field so both live gRPC and
  replay snapshots share one wire format.
- Godot owns `weapon_id -> visual` mapping.  The frontend maps a semantic
  `weapon_id` to animation, projectile, impact, shield ripple and audio via
  `weapon_visual_catalog.json`; it never reverse-engineers mechanics.
- Test Mode injects the same `CombatEvent` shape.  Test Mode fixtures emit the
  identical event contract as a real match, adding only a diagnostic overlay
  (weapon type, multiplier, armor type) that is hidden in normal play.
- HP-delta inference is migration fallback only.  Godot's legacy diff-based
  triggers may remain temporarily to keep regressions bounded, but no new
  combat logic may depend on inference, and it must not override authoritative
  events.

## Consequences

- Protocol and replay snapshots grow.  `combat_events` adds per-tick event
  records; snapshot size scales with combat intensity.  This is accepted in
  exchange for replayable, testable visuals.
- Event order must be deterministic.  SimCore assigns stable `event_id`
  (`tick:sequence`) and emits events in a fixed per-tick order; consumers may
  rely on the ordering for visual sequencing (e.g. chain bounces, splash).
- Godot visuals become replayable and testable.  Because visuals are a pure
  function of `CombatEvent` + catalog, a recorded replay reproduces identical
  animation, projectile and impact playback without SimCore running.
- SimCore remains independent from Godot assets.  SimCore and proto code must
  not reference `res://` paths, `vfx_profile`, scene files or any Godot
  resource; the architectural lint (`make lint-arch`) guards this boundary.
