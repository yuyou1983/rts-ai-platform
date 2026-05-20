# Godot VFX Vertical Slice

## Goal

Replace the current debug-like combat rings with a small, data-driven RTS VFX layer that gives attacks, hits, and deaths clearer StarCraft-like readability without copying a specific protected effect.

## Scope

- Add a Godot-side `VFXManager` node.
- Add a JSON VFX catalog under `godot/resources/vfx/`.
- Wire VFX into `game_view.gd` damage and death detection.
- Cover a first vertical slice: ballistic muzzle flash, generic hit spark, acid hit, tank shell impact, and building burst.

## Non-Goals

- No SimCore rule changes.
- No gameplay balance changes.
- No new unit types or abilities.
- No attempt at one-to-one StarCraft asset recreation.

## Architecture

`game_view.gd` remains the owner of SimCore state parsing. It detects visual events from state deltas, then calls `VFXManager` with compact event data. `VFXManager` owns effect lifetime, catalog lookup, texture loading, and drawing. Future work can replace individual effects with sprite-frame scenes or shaders without changing SimCore.

## Acceptance

- Damage no longer relies primarily on red debug circles.
- Attacks can spawn short muzzle flashes.
- Hits spawn type-sensitive effects.
- Removed buildings spawn a larger burst.
- The change is confined to Godot frontend files and docs.
