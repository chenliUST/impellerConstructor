# V0.91 Topology-First Transition Evidence

Date: 2026-07-04

## Motivation Evidence

User-provided frontend screenshots showed that V0.9/V0.91 transition modeling was still not reviewable:

- `screenshots/frontend-leading-edge-hub-corner-failure.png`: leading-edge to hub corner had visibly broken patch topology.
- `screenshots/frontend-root-transition-missing.png`: blade root transition was not visible as a real transitional surface.
- `screenshots/frontend-tip-transition-missing.png`: blade tip/edge transition visibility was incomplete.
- `screenshots/frontend-fillet-control-chamfer-direction-failure.png`: fillet control was under-sampled and chamfer/transition direction looked wrong.

## Root Cause

The first V0.91 patch-complex implementation fixed several V0.9 semantic losses but still used undersampled rectangular corner patches. Tip corner patches were initially 3 x 3 grids with collapsed rows/duplicated corner points. This caused two classes of failures:

1. OCCT B-spline interpolation could stall on degenerate corner grids during bounded B-Rep STEP export.
2. Patch mesh triangulation had to skip degenerate triangles around singular corner cells, hiding a topology problem behind final synthetic closure.

## Implemented Repair

The repair keeps V0.91 as a review-grade topology milestone, not a V1.0 industrial B-Rep claim.

- Corner transition patches now use 5-sample local boundary extraction instead of 3-sample extraction.
- Internal collapsed rows/columns are desingularized from adjacent samples while preserving shared endpoint node identity.
- The shared-node patch mesh now first chooses the non-degenerate quad diagonal. True duplicate-node or duplicate-coordinate corner singularities remain explicit through `singular_corner_cell_count`, but the default V0.91 presets no longer need that fallback.
- V0.91 validation blocks export if `skipped_triangle_count > 0`.
- V0.91 validation also blocks if skipped-triangle accounting is missing.
- STL, mesh STEP, and OBJ manifests now expose `singular_corner_cell_count` and `singular_corner_cells`.
- The bounded B-Rep STEP writer now rejects collapsed and rank-deficient B-spline grids before entering OCCT interpolation.

## Verification Summary

Targeted tests:

- `python -m pytest tests/test_impeller_bounded_brep_export.py tests/test_impeller_geometry_validation.py tests/test_impeller_v091_patch_mesh.py tests/test_impeller_v091_transition_topology.py tests/test_impeller_v091_resources.py tests/test_impeller_v091_sections.py tests/test_impeller_transition_topology.py tests/test_impeller_v09_workflow.py tests/test_impeller_v09_batch.py -q`
  - 98 passed
- `python -m pytest tests/test_impeller_v091_patch_mesh.py tests/test_impeller_v091_transition_topology.py tests/test_impeller_geometry_validation.py -q`
  - 27 passed
- `python -m pytest tests/test_impeller_bounded_brep_export.py -q`
  - 35 passed
- `python -m pytest tests/test_impeller_v091_resources.py tests/test_impeller_v091_sections.py tests/test_impeller_transition_topology.py -q`
  - 27 passed
- `python -m pytest tests/test_impeller_v09_workflow.py tests/test_impeller_v09_batch.py -q`
  - 4 passed
- `npm.cmd test`
  - 86 passed
- `npm.cmd run build`
  - frontend build check passed

End-to-end service smoke:

- `radial_open_reference_v0_91`
  - elapsed: 32.945 s
  - geometry validation: PASS
  - STEP size: 6,879,536 bytes
  - STL size: 1,804,884 bytes
  - OBJ size: 1,342,345 bytes
  - STEP bounded faces: 181
  - STL triangles: 36,096
  - mesh skipped triangles: 0
  - singular corner cells: 0
- `radial_closed_reference_v0_91`
  - elapsed: 34.127 s
  - geometry validation: PASS
  - STEP size: 7,273,025 bytes
  - STL size: 1,804,884 bytes
  - OBJ size: 1,342,277 bytes
  - STEP bounded faces: 187
  - STL triangles: 36,096
  - mesh skipped triangles: 0
  - singular corner cells: 0

## Remaining Limitation

V0.91 still exports a review-grade bounded, unsewn B-Rep face shell and a shared-node review mesh. It does not claim a watertight sewn solid, exact p-curve trimming, solver-ready CFD, or V1.0-grade industrial B-Rep topology. The source patch complex still uses synthetic review closure for remaining open patch boundaries; this is intentionally recorded as `synthetic_mesh_closure_review_caveat`.
