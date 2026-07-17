# Impeller V1.1.6 R15 Semantic Change Log

Date: 2026-07-17

## Contract Delta

- Audit implementation revision changes from
  `axis_first_triangle_surface_r14_0` to
  `axis_first_triangle_surface_r15_3`.
- Canonical positive Z now has one explicit radial-impeller meaning:
  `large_radius_backplate_to_small_radius_eye`.
- Axis polarity is selected from authenticated conical support endpoints when
  available, otherwise from radius-squared-weighted axial asymmetry. An
  unresolved sign fails as `v116_axis_direction_semantics_ambiguous`.
- Recovered hub and tip/shroud profiles now carry named endpoint records:
  `eye_inlet_small_radius` and `backplate_exit_large_radius`. Each record binds
  canonical R-Z coordinates to source ids and confidence.
- V1.1.2 mapping rejects missing, reversed, or mutually inconsistent support
  directions before construction. It no longer relies on list order or
  independent radius/axial extrema.
- Adaptive hub closure consumes the authenticated endpoints. The outer closure
  wall begins at the backplate endpoint and spans only the configured bottom
  thickness; a semantic mismatch fails as
  `v116_hub_closure_endpoint_semantics_failed`.
- Periodic representative selection is measured on the two authenticated
  pressure/suction blade-side faces. Complete root/edge topology and source ids
  remain attached to the selected component, but a STEP seam that splits one
  transition patch no longer changes the blade-side medoid or its fit gate.
- Support-bound material thickness uses the named large-radius backplate
  endpoint as its axial terminal. With the eye-positive canonical axis, hub
  back material is required on the negative-Z side of that endpoint; the
  former `max(Z)` terminal heuristic is removed.
- Audit payloads distinguish `process_status` from `geometry_status`. A
  completed but rejected audit remains inspectable without presenting process
  completion as geometry acceptance.
- Source, reconstruction, and heatmap use one source-derived canonical camera
  frame. Reconstruction and heatmap are not independently recentered or
  normalized.

## New Stable Failures

- `v116_axis_direction_semantics_ambiguous`
- `v116_support_profile_orientation_failed`
- `v116_support_profile_endpoint_role_missing`
- `v116_support_profile_streamwise_mismatch`
- `v116_hub_closure_endpoint_semantics_failed`

## Preserved Semantics

- Runtime release remains V1.1.6 and canonical geometry remains V1.1.2.
- V1.1.2 blade-loop, six-face, attachment, continuity, and residual gates are
  unchanged.
- Exact corresponding-surface distance and R14 checkpoint mathematics are
  unchanged, but R14 checkpoints are not reusable after the canonical-frame
  fingerprint changes.
- The periodic representative ceiling is unchanged. R15 changes which
  authenticated surface role supplies that measurement; it does not raise the
  limit to admit a failing full-component point cloud.
- Spline grooves, auxiliary holes, keyways, the spline-modified bore cylinder,
  and the non-planar source bottom boss remain explicitly unsupported and are
  excluded with source provenance. Supported hub and blade material faces
  remain individually represented in the comparison ledger and heatmap.
- R15 is review-grade reconstruction. It does not claim analytic B-Rep
  certification or relax a failed mapping gate.
