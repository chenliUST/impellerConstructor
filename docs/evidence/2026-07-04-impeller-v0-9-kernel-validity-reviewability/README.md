# V0.9 Kernel Validity And Reviewability Evidence

Date: 2026-07-04

## Root Cause

V0.8 exposed fillet/chamfer controls but still allowed a semantic loss at the blade
root: one `blade_i_root_transition_surface` could be treated as a successful
root-to-hub transition even though pressure-side and suction-side root blends have
different adjacency and trimming responsibilities. This made concave or untrimmed
transition geometry hard to detect and easy to hide under full hub/blade faces.

## V0.9 Change

V0.9 defines kernel validity as a first-class review artifact:

- `blade_root_to_hub` now requires per-blade pressure-root and suction-root
  transition surfaces.
- `geometry_validation_report` blocks STL/OBJ/STEP export when transition
  convexity, radius synchronization, disabled-policy cleanup, or adjacent trim
  coverage fails.
- Mesh/STL/OBJ triangulation skips trim-excluded cells and records trimmed-cell
  provenance.
- STEP export remains a bounded, unsewn review B-Rep shell, but trim-excluded
  sampled surfaces are split into bounded review patches instead of being written
  as one full untrimmed face.
- Batch regression tooling can run golden and negative case groups and writes
  JSON summaries.

## Review Artifacts

Large binary CAD/mesh review files stay under `Model Output/` or local `runs/`
directories and are not committed. Git evidence is limited to text, JSON resources,
tests, and summaries.

Expected V0.9 review fields:

- `geometry_validation_status`
- `geometry_validation_report`
- `kernel_capability_matrix_id`
- `capability_claim_level`
- `export_manifests.step.trim_excluded_cell_count`
- `export_manifests.step.trim_split_face_count`
- `export_manifests.stl.trimmed_cell_count`
- `transition_regions[*].edge_family`
- `transition_regions[*].transition_policy_id`

## Acceptance Boundary

V0.9 can claim review-grade validated sampled surface/B-Rep shell behavior for the
reference radial open and closed impeller resource line. It cannot claim exact
industrial variable-radius blends, sewn watertight solids, production CAD healing,
solver-ready CFD volume meshes, or automatic expert-rule patching.
