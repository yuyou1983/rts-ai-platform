# Godot Agent Operation Manual

**Audience:** Agents changing Godot frontend, sprites, VFX, HUD, fog, camera, selection, replay overlay, or SC1 presentation resources.  
**Goal:** Improve frontend fidelity without changing SimCore game rules unless explicitly requested.

---

## Ownership

Godot workflow owns:

- `godot/project.godot`
- `godot/scenes/*.tscn`
- `godot/scripts/*.gd`
- `godot/resources/presentation_manifest.json`
- `godot/resources/sprite_frames_config.json`
- `godot/resources/vfx/vfx_catalog.json`
- `godot/resources/abilities/*.tres`
- `godot/assets/**`
- `scripts/verify_presentation_scene.py`
- `tests/godot/*`
- `docs/design/sc1_presentation_catalog.md`
- `docs/godot_verification_guide.md`

Godot workflow may read `simcore/` and `data/` to understand state fields and entity names, but should not change SimCore rules to fix presentation problems.

---

## Core Rule

If the symptom is visual, first fix these layers in order:

1. `godot/resources/presentation_manifest.json`
2. `godot/resources/sprite_frames_config.json`
3. `godot/resources/vfx/vfx_catalog.json`
4. `godot/scripts/sprite_loader.gd`
5. `godot/scripts/game_view.gd` rendering code
6. tests and docs

Only escalate to SimCore when the actual state data is wrong.

---

## Standard Workflow

1. **Identify the failing visual mapping.**

   Determine whether the bug is:

   - abstract unit/building mapping,
   - visual ID not found,
   - atlas rectangle out of bounds,
   - render scale too small/large,
   - pivot/selection radius/health bar offset,
   - VFX mapping,
   - fog/minimap/UI rendering.

2. **Inspect manifest and generated validators.**

   ```bash
   python3 scripts/verify_presentation_scene.py
   python3 -m pytest tests/godot/ -q -x
   ```

3. **Change data before code where possible.**

   Prefer manifest/resource changes over GDScript logic changes.

4. **Run static checks.**

   ```bash
   python3 scripts/verify_presentation_scene.py
   python3 -m pytest tests/godot/ -q -x
   ```

5. **Run local game if needed.**

   ```bash
   python3 -m simcore.grpc_server --port 50051
   python3 -m simcore.http_gateway --grpc-port 50051 --http-port 8080
   /Applications/Godot.app/Contents/MacOS/Godot --path godot
   ```

---

## Visual Alignment Checklist

For every new or changed unit/building visual:

- [ ] `abstract_units` or `abstract_buildings` maps to an existing visual ID.
- [ ] `unit_visuals` or `building_visuals` entry exists.
- [ ] `atlas_rect` is inside the source texture.
- [ ] `render_scale` produces correct perceived size.
- [ ] `pivot` aligns base footprint to terrain.
- [ ] `selection_radius` matches gameplay footprint.
- [ ] `health_bar_offset` does not overlap the sprite.
- [ ] fallback visual remains valid.
- [ ] tests cover nested mapping values when morphs or aliases are used.

---

## VFX Checklist

For effects:

- [ ] Effect exists in `godot/resources/vfx/vfx_catalog.json`.
- [ ] Source texture exists under `godot/assets/`.
- [ ] Unit or spell maps to effect profile.
- [ ] Effect lifetime and scale are not hardcoded per entity ID.
- [ ] Death/build/attack/gather profiles remain generic and data-driven.

Run:

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/test_presentation_manifest.py tests/godot/test_verify_presentation_scene.py -q
```

---

## Fog and Minimap Checklist

Fog and minimap work should verify:

- [ ] unexplored/explored/visible states are visually distinct,
- [ ] fog smoothing does not flicker on repeated 2 -> 1 transitions,
- [ ] minimap positions use the same map dimensions as main rendering,
- [ ] full entity state may be rendered in Godot, but AI observations must remain fog-filtered.

Commands:

```bash
python3 scripts/verify_godot_fog_smoothing.py
python3 scripts/verify_fog_flicker.py
```

If the verifier requires a running service, start backend first:

```bash
python3 -m simcore.grpc_server --port 50051
python3 -m simcore.http_gateway --grpc-port 50051 --http-port 8080
```

---

## Manual Playtest Script

Use this when visual changes affect player-facing behavior:

1. Start backend.
2. Launch Godot.
3. Start Terran vs Terran.
4. Verify worker, base, minerals, fog, selection, health bars.
5. Start Terran vs Zerg.
6. Verify unit/building race mapping.
7. Start Protoss vs Terran.
8. Verify Pylon power circle, Protoss worker/base mapping.
9. Select workers, right-click minerals, build a building, train a unit.
10. Watch combat, death VFX, minimap dots, fog transitions.

---

## Do Not Do

- Do not fix sprite size by changing SimCore entity radius unless gameplay radius is actually wrong.
- Do not hardcode entity IDs or seed-specific positions in GDScript.
- Do not bypass failed validators with `|| true`.
- Do not commit proprietary extracted game archives.
- Do not assume SC1 parity without coverage evidence.

---

## Completion Gate

Minimum gate:

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/ -q -x
```

Add manual Godot verification for visible UI/rendering work.

