# Impeller V1.1.5 Semantic Change Log

## Release Identity

- Runtime release: `1.1.5`.
- Engineering Drawing contract: `1.1.5`.
- Parameter Inspection contract: `1.1.4`.
- Geometry patch and canonical NURBS payload: `1.1.2`.
- Preset ids remain stable.

## Drawing Geometry Semantics

1. A Top blade outline is now the orthographic projection of resolved blade
   surface boundaries. A blade section loop is never substituted for a full-part
   Top projection.
2. Top hub topology explicitly includes the outer envelope, hub top outer and
   inner boundaries, and mounting bore.
3. Top section evidence is class-aware. Main and splitter blades, when present,
   each expose active-root, midspan and active-tip sections.
4. Meridional support profiles are evaluated rational NURBS curves. Control
   polygons are separate dashed construction evidence and are not geometry.
5. Meridional material regions are closed semantic polygons suitable for section
   hatching. The side view is a separate orthographic surface projection.
6. An S-Q row is a five-station family: active root, `h=0.25`, midspan,
   `h=0.75`, and active tip. The corresponding XYZ loops use the same resolved
   station records and are overlaid on the representative blade.

## Parameter Presentation Semantics

- Every canonical parameter leaf is assigned one presentation mode:
  `dimensioned_on_drawing`, `listed_in_construction_table`,
  `reported_as_quality_evidence`, or `not_applicable`.
- Six stable tables cover population, support profiles, blade sections,
  pose/twist fields, attachments, and quality constraints.
- A zero-length unaccounted list is a contract invariant.
- Drawing dimensions retain semantic feature ids and model-space witness points;
  viewport bounds are not dimensional evidence.

## Runtime And UI Semantics

- Drawing contracts are cached per immutable model run.
- The frontend loads Top first and requests Meridional, S-Q, or construction
  tables only when selected.
- Drawing-mode instantiation uses `review_summary`: it retains the complete graph
  server-side but skips export generation, CFD mesh generation, manifest-file
  serialization and full-graph response transport. CAD Review keeps the historical
  full instantiate path and export behavior.
- Each S-Q row carries only its representative blade surfaces, so high-DPI 3D
  inspection does not require the complete graph in the browser manifest.
- The 3D S-Q companion uses one shared renderer, high-DPI output, depth-tested
  contours and five colored section-loop overlays.
- Screen dimensions remain blue; print rules convert drawing evidence to black.

## Compatibility

- V1.1.5 does not change blade construction mathematics, canonical inputs, preset
  ownership, topology semantics or export geometry.
- `review_summary` is explicitly non-exporting. Regenerate from CAD Review when
  STEP/STL artifacts are required.
- Historical V1.1.4 Parameter Inspection data remains valid and is not rewritten.
