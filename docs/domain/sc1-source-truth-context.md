# SC1 Source Truth Bounded-Context Glossary

> Owner: **cross-cutting** (reference integrity)
> Scope: original game data semantics — weapon IDs, unit stats, overlay mappings, reference artifacts.
> Permitted dependencies: read-only reference. No code may import or embed SC1 proprietary assets.

---

## Effective MPQ Overlay

Definition: the curated subset of original game archive data that is actively
referenced by the project as a correctness oracle, explicitly selected and
recorded rather than bulk-extracted, so that only intended data influences
rule and asset validation.

Not the same as: a full MPQ extraction, which dumps the entire archive and
may include unused, deprecated, or irrelevant data that should not guide
development decisions.

Boundary example: a weapon's damage value is validated against the Effective
MPQ Overlay entry for that weapon — not against a raw dump that might contain
a superseded value from an earlier patch.

---

## Semantic Weapon ID

Definition: a stable, human-readable identifier for a weapon's behavior class
that maps to original game data entries but is independent of raw table
indices, so that re-indexing or re-ordering the source data does not break
references.

Not the same as: a raw DAT index or array offset, which changes if the
source data table is re-sorted or re-compiled and is therefore fragile.

Boundary example: "Marine_Rifle_Attack" is a Semantic Weapon ID that maps to
index 42 in the current data table — if the table is re-sorted and the index
becomes 17, code referencing the Semantic Weapon ID is unaffected while
hardcoded index 42 silently points to the wrong weapon.

---

## Reference Artifact

Definition: an original game asset (image, sound, data table) used as the
authoritative source for replication, against which presentation-layer
reproductions and SimCore rule values are validated for correctness.

Not the same as: a Presentation Asset, which is the project's own reproduction
that is validated against the Reference Artifact — the Reference Artifact is
the oracle, the Presentation Asset is the thing being checked.

Boundary example: the original Marine sprite sheet is a Reference Artifact;
the project's re-drawn Marine atlas is a Presentation Asset that must match
the Reference Artifact's frame count and dimensions within tolerance.

---

## Presentation Asset

Definition: a visual or audio resource produced by the project for use in the
presentation layer, whose correctness is measured against a Reference
Artifact rather than asserted by design preference.

Not the same as: a Reference Artifact, which is the original-game oracle that
the Presentation Asset must match; conflating the two hides replication drift.

Boundary example: a team creates a new muzzle-flash VFX as a Presentation
Asset — it is validated against the Reference Artifact's frame timing and
color palette; if it deviates beyond tolerance it is rejected regardless of
aesthetic preference.

---

## DAT Entry

Definition: a single record within an original game data table (units.dat,
weapons.dat, etc.) that encodes a specific stat or behavior parameter, used
as the atomic unit of reference when validating SimCore rule values.

Not the same as: a Semantic Weapon ID, which is a stable label that may map
to one or more DAT Entries but is not itself a raw table row.

Boundary example: the "Marine ground attack" Semantic Weapon ID resolves to
DAT Entries for damage, cooldown, and range in weapons.dat — each DAT Entry
is checked individually; the Semantic Weapon ID groups them for readability.

---

## TBL String

Definition: a human-readable text string stored in an original game string
table, referenced by index, used as the authoritative source for in-game
labels, unit names, and tooltip text that the presentation layer must match.

Not the same as: a Semantic Weapon ID, which identifies a behavior class — a
TBL String identifies display text, which may change independently of behavior.

Boundary example: unit display name "Marine" comes from a TBL String at index
65 — the presentation layer must show this exact string; replacing it with
"Rifleman" based on preference is a replication error even if the unit's
behavior is correct.

---

## GRP Frame

Definition: a single image within a GRP-format sprite archive from the
original game, identified by its frame index, used as a Reference Artifact
for validating that the project's Presentation Assets reproduce the correct
visual sequence and timing.

Not the same as: an Animation Frame in the presentation layer, which is the
project's reproduction; a GRP Frame is the original source image being
replicated.

Boundary example: a Marine's walk cycle in the original game has 8 GRP Frames
— the Presentation Asset must produce 8 corresponding Animation Frames with
matching visual content; adding or omitting a frame is a replication
deviation caught by comparing against the GRP Frames.
