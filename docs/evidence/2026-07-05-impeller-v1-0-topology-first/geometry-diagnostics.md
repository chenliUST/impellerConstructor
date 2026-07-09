# V0.97 Geometry Diagnostics Motivating V1.0

**Date:** 2026-07-05

## User-Observed Failure

The user reported that a previous failure returned:

```text
叶片前缘尾缘的面建模错误，沿连接edge处过渡的切向似乎在某一个点产生了180°翻转
```

Screenshot:

```text
C:/Users/CHENLI~1/AppData/Local/Temp/codex-clipboard-4371ae31-9d69-4d65-bf2c-1175754e9aae.png
```

The visible orange edge face and UV/wire pattern suggest a local parameterization or tangent/winding inversion on a blade edge transition surface.

## Current V0.97 Diagnostic Gap

The existing V0.97 validation could pass while the patch had internal failure:

```text
blade_0_tip_transition_surface
curvature_claim = G2
row_continuity_status = PASS
```

But full-grid diagnostics showed:

```text
row tangent minimum ~= -0.999
cell normal row dot ~= -0.983
cell normal column dot ~= -0.495
```

This means the patch can internally reverse direction or fold while still satisfying the limited checks used by V0.97.

## Root Cause Pattern

The V0.97 construction stack has these defects:

1. `build_v097_edge_fillet_surface()` handles leading, trailing, and tip with one generic local loop.
2. The builder has no explicit edge-family orientation contract for `u_min`, `u_max`, and `v_max`.
3. `_endpoint_tangent(..., chord)` can orient near-orthogonal retained tangents using a near-zero dot product.
4. `_progress_metrics()` only measures monotonic progress along the pressure-to-suction chord. It does not check internal section tangent reversal.
5. Validation looks at selected lines, endpoint tangency, and midpoint bulge. It does not check all rows, columns, and cell normals.

## V1.0 Diagnostic Requirement

V1.0 must fail validation if any named face has:

- section tangent reversal;
- station tangent reversal;
- negative cell-normal neighbor dot;
- foldover count above zero;
- inconsistent face orientation;
- self-intersection proxy failure;
- unsupported continuity claim.

The target is not to catch a screenshot symptom. The target is to make that class of invalid patch impossible to accept as `PASS`.

## 2026-07-05 V1.0 Topology Semantics Diagnostic

New user review after the NURBS-adapter correction identified four geometry-semantics mismatches:

1. Open impeller displayed `tip_reference_surface` as if it were material.
2. Hub bottom/top outer chamfer remained present by default, although its topology is not yet fully specified.
3. Root face was still the old pressure-to-suction root closure, visually resembling a blade bottom face.
4. Leading/trailing/tip faces were still three-column closure strips.

Diagnostic probe after correction:

```text
transition policies:
  blade_leading_edge.default = G2
  blade_trailing_edge.default = G2
  blade_root_to_hub.default = G2
  blade_tip_or_shroud.default = G2
  hub_bottom_outer.default = G0 disabled
  hub_top_outer.default = G0 disabled

open surface_count = 32
outer_chamfers = []
tip_reference_surface:
  role = construction_support_only
  display.visible_by_default = false
  display.construction_reference = true

blade_0_leading_edge_surface grid = 17 x 13
blade_0_trailing_edge_surface grid = 17 x 13
blade_0_tip_surface grid = 41 x 13
blade_0_root_annular_surface grid = 105 x 9

root topology:
  role = root_pedestal_ring_surface
  root_topology = annular_hub_to_blade_boss
  boss_width_mm = 67.2
  hub_projection_rule = project_outer_loop_to_revolved_hub_profile_by_theta_z

topology:
  shared_edge_count = 206
  synthetic_shared_edge_count = 0
  max_shared_edge_gap_mm = 0.0
```

The corrected root surface is still sampled review-grade geometry. It is not an analytic OCCT fillet, but its topology now matches the intended hub-land-to-blade-root boss instead of the old blade-internal bottom strip.

## 2026-07-05 V1.0.2 Continuous Attachment Diagnostics

V1.0.2 tightened the topology-first implementation from "native face labels" to a measured continuous blade attachment complex.

Runtime identity:

```text
geometry_version = 1.0
geometry_patch_version = 1.0.2
continuous_blade_attachment_status = PASS
```

Resolved preset defaults for both shipped topology-first presets:

```text
resolved_blade_count = 4
resolved_blade_thickness_mm = 92.0
resolved_root_attachment_width_mm = 67.2
resolved_root_attachment_lift_mm = 11.04
resolved_tip_attachment_width_mm = 41.4
resolved_tip_attachment_lift_mm = 9.2
edge_short_direction_sample_count = 17
attachment_short_direction_sample_count = 17
```

Open preset diagnostic probe:

```text
radial_open_reference_v1_0:
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  root attachment surfaces = 4
  closed tip attachment surfaces = 0
  root inspection_class = root_to_hub_native_root_face
  root fill = #ff00cc
  root wire = #fff200
```

Closed preset diagnostic probe:

```text
radial_closed_reference_v1_0:
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  root attachment surfaces = 4
  closed tip attachment surfaces = 4
  root inspection_class = root_to_hub_native_root_face
  closed tip inspection_class = tip_to_shroud_attachment
  root fill = #ff00cc
  closed tip fill = #00e5ff
  wire = #fff200
```

Attachment topology checks now block validation for:

```text
v1_0_2_root_inner_loop_mismatch
v1_0_2_root_support_domain_violation
v1_0_2_tip_inner_loop_mismatch
v1_0_2_tip_support_domain_violation
v1_0_2_transition_foldover
v1_0_2_resolved_attachment_defaults_missing
v1_0_2_edge_sample_count_invalid
```

Important diagnostic distinction:

```text
transition_quality.foldover_count = G2 builder/global-reference diagnostic
attachment_quality.foldover_count = blocking attachment material-domain foldover count
surface.foldover_status = explicit blocking face foldover status
```

Some default V1.0.2 review-grade surfaces still report nonzero `transition_quality.foldover_count` from the G2 builder's global-reference measurement. This is not accepted as a material-domain foldover by itself. Validation blocks only explicit foldover status, normalized top-level foldover count, attachment-quality foldover count, support-domain violations, loop mismatch, or graph-level builder failures.

Failure propagation correction:

```text
missing/malformed resolved_attachment_defaults
  -> continuous_blade_attachment_status = FAIL
  -> surface_graph_status = FAIL
  -> manifest.validity.status = FAIL
  -> geometry_validation_status = FAIL
```

This prevents a V1.0.2 constructor failure from being masked by the older NURBS kernel validity path.

## 2026-07-06 Screenshot-Driven Attachment Regression Probe

User screenshot showed several blade transition/root faces rendered as wall-like or detached surfaces. Numeric probe of the generated V1.0.2 graph found two concrete geometry-data causes before frontend rendering:

```text
Before fix:
  radial_open_reference_v1_0 graph status = PASS/PASS
  blade_0_root_annular_surface outer-inner distance:
    min = 0.0
    max = 0.000001143 mm
    <= 1e-6 count = 83 / 85
  radial_closed_reference_v1_0 blade_0_tip_surface outer-inner distance:
    min = 0.0
    max = 0.000000985 mm
    <= 1e-6 count = 85 / 85
```

The root/tip support attachment width existed in runtime metadata but was not applied to the actual support outer loop. `offset_loop_on_revolved_support` computed `requested_offset_loop`, then returned the unshifted projected point as `outer_loop`.

The same probe also found edge-cap/topology mismatch:

```text
Before fix:
  blade_0_leading_edge_surface root_profile_leading_cap vs uv_grid[0]:
    max gap = 3.686999786 mm at best matching row check, up to 86.171362435 mm against other cap row
  blade_0_trailing_edge_surface root_profile_trailing_cap vs uv_grid[0]:
    max gap = 4.473276112 mm at best matching row check, up to 34.080825497 mm against other cap row
```

Root/closed-tip attachment was therefore coupled to legacy caps, not the final visible G2 edge caps.

After fix:

```text
radial_open_reference_v1_0:
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  transition_failures = []
  blade_0_root_annular_surface outer-inner distance:
    min = 66.639436986 mm
    max = 77.349154215 mm
    mean = 67.841375427 mm
  leading root cap gap to uv_grid[0] = 0.0
  trailing root cap gap to uv_grid[0] = 0.0

radial_closed_reference_v1_0:
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  transition_failures = []
  blade_0_root_annular_surface outer-inner distance:
    min = 66.639436986 mm
    max = 77.349154409 mm
    mean = 67.841375440 mm
  blade_0_tip_surface outer-inner distance:
    min = 41.344132638 mm
    max = 45.493102415 mm
    mean = 41.737831423 mm
  leading root cap gap to uv_grid[0] = 0.0
  trailing root cap gap to uv_grid[0] = 0.0
```

Additional support-domain finding:

```text
Final G2 leading root cap z range = 400.0 .. 400.086789612
Hub support profile z range = 0.0 .. 400.0
Final G2 leading tip cap z range = 401.0 .. 401.089647178
Shroud support profile z range = 30.0 .. 401.0
```

These overrun values are smaller than the resolved attachment lift defaults (`root = 11.04 mm`, `tip = 9.2 mm`). The support-domain projection now accepts this as an attachment-lift transition and clamps the support outer loop to the nearest hub/shroud boundary z while keeping the blade inner loop on the final G2 edge cap.

## 2026-07-06 V1.0.2 Six-Face Regression Probe

A later screenshot showed that the blade six-face complex still looked primitive: root height was not visually robust, root inner and blade exterior alignment was hard to inspect, and trailing/tip transitions could still show reversal artifacts.

Numeric root cause before this fix:

```text
radial_open_reference_v1_0:
  trailing edge max pressure tangent flip ~= 179.999 deg
  trailing edge max suction tangent flip ~= 179.999 deg
  trailing edge foldover_count = 201
  open tip foldover_count = 13
  root aggregate transition_quality.foldover_count = 114

trailing pressure boundary z samples:
  11.033860, 8.936670, 7.722190, 7.390418, 7.941354, 9.375000, ...
```

The root lift was applied along the blade span tangent, producing a local root-edge reversal. The G2 edge builder also allowed curvature proxy to dominate material normal for short-direction bulge, which caused internal trailing-edge folds after the boundary reversal was removed.

Corrected open-preset metrics:

```text
radial_open_reference_v1_0:
  surface_graph_status = PASS
  geometry_validation_status = PASS
  graph patch = 1.0.2
  blade_0_leading_edge_surface foldover_count = 0
  blade_0_trailing_edge_surface foldover_count = 0
  blade_0_tip_surface foldover_count = 0
  blade_0_root_annular_surface visible_by_default = false
  visible root component patch count for blade_0 = 4
  visible root component max foldover_count = 0
  root leading cap gap to final edge cap = 0.0
  root trailing cap gap to final edge cap = 0.0
```

HTTP smoke against the restarted local backend:

```text
POST /api/rule-engines/synthesize preset_id=radial_open_reference_v1_0 -> PASS
POST /api/rule-engines/{engine_id}/instantiate -> geometry_validation_status PASS
geometry_version = 1.0
transition_geometry_status = topology_first_closed_nurbs_impeller_surface_graph
surface_graph.geometry_patch_version = 1.0.2
surface_count = 48
root_component_count = 4
root_component_max_foldover = 0
open_tip_foldover = 0
```

Known remaining closed-tip limitation:

```text
closed tip aggregate and closed tip cap component patches can still fold where the blade tip cap endpoint already lies on the shroud support.
This requires dedicated closed-tip corner/shroud coupling patches, not another single annular patch.
```

## 2026-07-06 V1.0.3 Section-Loop Root Blend Verification

`radial_open_reference_v1_0` now routes the default open inspection path to the V1.0.3 section-loop constructor.

HTTP smoke after restarting the local backend from this worktree:

```text
geometry_version = 1.0
geometry_patch_version = 1.0.3
transition_geometry_status = topology_first_section_loop_blade_root_blend_surface_graph
surface_graph_status = PASS
geometry_validation_status = PASS
main_blade_count = 4
splitter_blade_count = 4
blade_thickness_mm = 32.0
root_component_max_foldover = 0
tip_dome_max_foldover = 0
```

Root blend components retain segment-specific roles such as `pressure_root`, `suction_root`, `leading_root_corner`, and `trailing_root_corner`. The family-level query key is `display.inspection_class = root_to_hub_blend`; this preserves the four physical root segments while still allowing validator/viewer grouping.

Open tip domes are visible V1.0.3 transition components with `role = open_tip_dome`, mesh data, wireframe display, and zero foldover for shipped defaults.
