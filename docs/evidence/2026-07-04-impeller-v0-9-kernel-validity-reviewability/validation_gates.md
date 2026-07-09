# V0.9 Validation Gates

## Pre-Export Blocking Gates

- Fillet convex signed bulge must be positive.
- Fillet/chamfer radius recorded on a transition surface must match the active
  transition policy radius.
- Enabled root transitions must use pressure-root and suction-root surfaces, not the
  legacy single root transition surface.
- Disabled transition policies must not leave phantom transition surfaces.
- Transition surfaces must have adjacent trim or trim-exclusion metadata on their
  declared adjacent surfaces.

## Export Gates

- STL/OBJ mesh generation skips trim-excluded cells.
- STEP export does not write `TRIANGULATED_FACE_SET`.
- STEP export does not write old unbounded `10000`-scale placeholder planes.
- STEP reimport face count must match manifest `bounded_face_count` when OCCT
  reimport is available.
- STEP/STL manifests must expose transition and trim counters for review.
