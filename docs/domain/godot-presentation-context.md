# Godot Presentation Bounded-Context Glossary

> Owner: **godot-specialist**
> Scope: visual rendering, sprites, animation, VFX, input feedback.
> Permitted dependencies: Proto (L0), SimCore (L1), Agents (L2). Must not change SimCore rules.

---

## Presentation State

Definition: the visual approximation of the Authoritative Game State as
rendered by the Godot frontend at a given frame, which may lag behind or
deliberately omit information not visible to the local player.

Not the same as: Authoritative Game State, which is the exact simulation
snapshot and the source of truth that Presentation State must reconcile to.

Boundary example: a damaged unit's health bar in Presentation State may
display the previous tick's value for two frames due to interpolation, while
the Authoritative Game State already reflects the updated health.

---

## CombatVisualController

Definition: a presentation-layer component responsible for translating
CombatEvents received from the simulation into the correct sequence of visual
effects, animations, and audio cues on the affected entities.

Not the same as: the combat rule engine in SimCore, which resolves damage and
state transitions — the controller only renders the outcome.

Boundary example: when a CombatEvent arrives indicating a unit took damage, the
CombatVisualController plays the hit animation and spawns a damage-number
label; it must not recalculate or alter the damage value.

---

## Test Mode Fixture

Definition: a controlled, deterministic visual scenario assembled in Godot
that exercises a specific presentation behavior — such as a sprite swap,
animation transition, or VFX trigger — without running the full simulation.

Not the same as: a simulation test, which validates game rules and state;
a Test Mode Fixture validates only that the presentation layer renders
correctly for a given input.

Boundary example: a fixture that places two units and fires a mock
CombatEvent to verify that the muzzle-flash VFX plays at the correct
offset — the fixture does not run the SimCore damage calculation.

---

## Visual Manifest

Definition: a structured declaration of the visual assets, sprite atlases,
animation frames, and metadata required to present a game entity, serving as
the contract between reference assets and the presentation layer.

Not the same as: the raw asset files themselves, which are the binary
resources the manifest describes and points to.

Boundary example: a Visual Manifest for a Marine lists its walk animation
frames and their pixel dimensions; the manifest is validated before the
atlas is loaded so a missing frame is caught at startup, not at runtime.

---

## Sprite Atlas

Definition: a single texture image containing multiple sub-sprites arranged
in a grid, referenced by the presentation layer to render entity graphics
without loading individual files per frame.

Not the same as: a Visual Manifest, which declares the metadata and layout
of assets but is not the pixel data itself.

Boundary example: a 256×256 atlas containing 16 frames of a walk cycle is
loaded once; the presentation layer crops sub-regions per frame — swapping
the atlas for individual frame files would be a performance regression, not
a correctness issue.

---

## Animation Frame

Definition: a single still image within an animation sequence, identified by
its position in the sprite atlas and its duration in rendered frames, used by
the presentation layer to advance visual motion.

Not the same as: a simulation Tick, which advances game state; an Animation
Frame advances only the visual representation and may span multiple ticks or
sub-tick intervals.

Boundary example: a walk cycle has 8 Animation Frames played at 15 fps, while
the simulation runs at 22 ticks per second — the visual cadence and simulation
cadence are intentionally decoupled.

---

## Godot Scene

Definition: the structural unit of the Godot engine's scene tree representing a
visual entity or UI element, composed of nodes that the presentation layer
instantiates, updates, and destroys in response to simulation events.

Not the same as: a game entity in the Authoritative Game State, which exists
independently of whether a Godot Scene has been created to render it.

Boundary example: a Production Entity may exist in the simulation before its
Godot Scene is instantiated (e.g., during fog-of-war when the building is not
yet visible to the local player) — the scene is created on reveal.
