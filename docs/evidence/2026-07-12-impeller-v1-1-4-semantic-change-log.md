# Impeller V1.1.4 Semantic Change Log

## Release Identity

- Runtime and inspection contract: `1.1.4`.
- Geometry family: `1.1`.
- Canonical NURBS payload: `1.1.2`.
- Preset ids remain stable.

## Geometry Semantics

1. `main_passage_bisector` now means that the splitter centerline is evaluated
   against the adjacent main-blade centerline at the same physical streamwise `s`,
   even when canonical NURBS skeleton fields are active.
2. Splitter passage fraction is measured across every sampled splitter centerline
   and span station. A failed measurement blocks surface-family generation.
3. The first open and closed presets opt into a support-profile feasibility gate:
   the hub-to-tip/shroud span direction is measured against the local hub
   meridional tangent and the active height is measured after attachment offsets.
4. The accepted angle range is 60 to 120 degrees. This is a resolved geometric
   measurement, not a promise based on a raw, reversible NURBS parameter arrow.
5. Closed shroud height is defined from its inner flowpath support profile; material
   thickness remains a separate construction concern.

## Inspection Semantics

- A no-splitter preset reports splitter phase as not applicable while retaining the
  actual main-blade reference direction.
- Angular source matching uses a `1e-6` degree engineering tolerance.
- The active frontend no longer interprets resolved geometry parameters as
  independently editable values.
- CAD Review and Engineering Drawing are the only active workspaces.
- CFD and feature-debug manifests remain backend evidence but are not active UI
  destinations in V1.1.4.

## Compatibility

- Historical editor components and geometry helper models remain in the repository.
- V1.1.4 does not delete historical V1.1.3 evidence or redefine the V1.1.2 NURBS
  payload.
- Instantiate requests from the active frontend contain an empty parameter override
  map and no profile, curve, transition, section-loop or family overrides.

## Preset-Only Instantiate Semantics

- The active review workspace uses a dedicated instantiate payload containing only
  `parameters: {}` and the requested geometry stage.
- Historical `buildInstantiatePayload` fallback behavior remains available only to
  inactive editor paths; it is not a source of preset defaults for active review.
- `splitter_blade_count = 0` remains an explicit valid population. Population
  mismatch diagnostics report the received total, expected main/splitter composition,
  and preset id; totals are never silently coerced.

## Engineering Drawing Semantics

- `GET /api/model-runs/{run_id}/engineering-drawing` returns a generation-bound,
  read-only `1.1.4` contract derived from resolved geometry evidence.
- Every measured dimension contains semantic source feature ids and model-space
  witness points. Viewport bounds and fixed screen coordinates are forbidden as
  dimension evidence.
- Top sections mean the first active root station, `h = 0.5`, and the last active
  tip/shroud station. They are not arbitrary image-space cuts.
- Meridional actual support curves and NURBS control polygons are separate records;
  control polygons are construction evidence, not substituted geometry.
- S-Q emits one representative row per present blade class. No-splitter presets do
  not synthesize a splitter row.
