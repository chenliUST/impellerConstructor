# Impeller V1.0.4 Geometry Contract Overhaul Spec

**Date:** 2026-07-07

## Summary

V1.0.4 is a geometry-contract overhaul for the topology-first impeller constructor. It addresses the current V1.0.3 failure pattern where the graph is versioned correctly but root, tip, hub, section-loop, continuity, and viewer semantics are not yet coherent enough for expert inspection.

The V1.0.4 rule is:

> The blade section loop, hub/tip meridional carriers, root annular transition, tip dome, hub solid, mounting bore, G2 measurements, and viewer layers must share one explicit construction contract. No surface may claim smoothness, material-side validity, or parameter direction without measurable evidence.

V1.0.4 must not be a local patch over the screenshots. It must define and enforce invariants that prevent root patches flipping into material, tip patches exceeding their blade loop, cone-like hub fallback, fake G2 claims, and UI curves that are not the curves used by the backend.

## User-Observed Failures To Fix

The current generated model shows these defects:

1. Root surface patches have inconsistent parameter directions. Several patches are visibly reversed or folded into the material side.
2. Root width and height do not match the intended semantics. The root band should be roughly half the average blade thickness in both width and lift, with low variation around the loop. Current width varies too much and height is nearly absent.
3. Tip surface area exceeds the actual blade tip footprint.
4. Hub still appears conical instead of a visibly concave revolved meridional NURBS surface.
5. The frontend blade section-loop display does not look like one closed loop.
6. G2 continuity is not actually visible or measured.
7. Blade-to-hub angle is too small for inspection. Defaults should make blade faces meet the hub at approximately 60 to 120 degrees.
8. Shaded surfaces and wireframes are visually conflated. The user needs separate shade, NURBS UV wire, mesh triangle wire, and control-point layers.
9. Hub material and mounting bore are not correctly modeled as first-class topology faces.

## Scope

V1.0.4 covers the active open radial topology-first preset:

```text
preset_id = radial_open_reference_v1_0
geometry_version = 1.0
geometry_patch_version = 1.0.4
```

Closed impeller V1.0.2 behavior must remain available and passing. V0.9 through V0.97 behavior must not be modified except where shared frontend routing needs to avoid stale UI confusion.

## Non-Goals

- Do not implement exact OCCT analytic fillets.
- Do not replace the whole kernel with a CAD solid kernel.
- Do not hide invalid geometry by changing visibility defaults.
- Do not reduce root width/lift below the inspection contract just to pass foldover tests.
- Do not remove the V1.0.3 files until V1.0.4 has separate tests and evidence.

## Version Contract

Runtime and manifest fields for open V1.0.4:

```text
geometry_version = "1.0"
geometry_patch_version = "1.0.4"
transition_geometry_status = "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
source_kernel = "v1_0_4_geometry_contract_kernel"
carrier_source_kernel = "axisymmetric_throughflow_nurbs_kernel"
mesh_strategy = "v1_0_4_surface_uv_and_review_quad_mesh"
kernel_capability_matrix_id = "impeller_v1_0_4_kernel_capabilities"
golden_case_registry_id = "impeller_v1_0_4_golden_cases"
```

The old API field `transition_geometry_status` remains for compatibility, but its value must state that V1.0.4 is a measured topology-first surface graph, not a post-transition release.

## Geometry Architecture

V1.0.4 keeps the V1.0.3 ownership model but hardens each boundary contract:

```text
profile defaults -> concave hub/tip NURBS carriers
section loop -> closed four-segment blade cross-section
carrier blade rows -> pressure/suction face sampled NURBS surfaces
section-loop face builder -> pressure, suction, leading, trailing surfaces
root solver -> material-side annular transition from blade root loop to hub domain
tip solver -> bounded dome/cap inside the blade tip loop
hub solid builder -> hub shell, caps, bore wall, bore edge rings
topology graph -> shared-edge identity and continuity measurements
viewer -> separated shade / surface UV wire / mesh triangle wire / controls
```

No stage may infer material side from a local two-point chord alone. Material side must come from declared frames and be verified against support-domain signed distance.

## Section Loop Contract

Every blade station must expose one closed loop with four ordered segments:

```text
pressure_side -> leading_edge -> suction_side -> trailing_edge -> pressure_side
```

Backend loop payload:

```json
{
  "section_loop_family_id": "v1_0_4_g2_airfoil_section_loop",
  "segment_order": ["pressure_side", "leading_edge", "suction_side", "trailing_edge"],
  "closed_loop_points": [[0.0, 0.0, 0.0]],
  "segments": {
    "pressure_side": {"points": [[0.0, 0.0, 0.0]], "curve_kind": "g2_bezier_or_bspline"},
    "leading_edge": {"points": [[0.0, 0.0, 0.0]], "curve_kind": "g2_arc_like_cap"},
    "suction_side": {"points": [[0.0, 0.0, 0.0]], "curve_kind": "g2_bezier_or_bspline"},
    "trailing_edge": {"points": [[0.0, 0.0, 0.0]], "curve_kind": "g2_arc_like_cap"}
  },
  "loop_quality": {
    "max_closure_gap_mm": 0.0,
    "max_join_tangent_angle_deg": 0.0,
    "max_join_curvature_proxy_mismatch": 0.0,
    "signed_area_mm2": 0.0,
    "orientation": "ccw_material_outward"
  }
}
```

Frontend loop display:

- Draw sampled closed loop as one continuous polyline.
- Draw segment control polygons separately and label by segment.
- Do not connect control points in a way that visually contradicts sampled loop order.
- Show pressure/suction sides as flatter curves and leading/trailing caps as visibly curved arc-like sections.

## Root Surface Contract

Root surface is a material-side annular transition, not a generic fillet patch.

Default open preset values:

```text
average_blade_thickness_mm = 20.0
root_attachment_width_mm = 10.0
root_attachment_lift_mm = 10.0
root_width_rule = 0.50 * average_blade_thickness_mm
root_lift_rule = 0.50 * average_blade_thickness_mm
root_width_variation_limit = +/- 20%
root_lift_variation_limit = +/- 20%
```

Root patch generation inputs:

```text
inner_loop = blade root section loop after pressure/suction/edge face construction
hub_domain_loop = projection of inner_loop to hub theta/u or theta/z domain
outer_domain_loop = material-side offset of hub_domain_loop by root_attachment_width_mm
outer_loop = hub surface samples at outer_domain_loop
short_direction = monotone blend from inner_loop to outer_loop
lift_direction = measured support normal/material side with positive signed distance from hub
```

Root patch component order:

```text
pressure_root_patch
leading_root_corner_patch
suction_root_patch
trailing_root_corner_patch
```

Each component must report:

```json
{
  "root_patch_orientation_status": "PASS",
  "material_side_status": "PASS",
  "foldover_count": 0,
  "min_root_width_mm": 8.0,
  "max_root_width_mm": 12.0,
  "min_root_lift_mm": 8.0,
  "max_root_lift_mm": 12.0,
  "max_parameter_direction_flip_deg": 0.0,
  "max_parameter_direction_flip_role": "diagnostic_only",
  "max_tangent_angle_deg": 2.0,
  "max_normal_angle_deg": 5.0,
  "max_curvature_proxy_mismatch": 0.25
}
```

`max_parameter_direction_flip_deg` is retained for review diagnostics. It is not a blocking gate when foldover count, material side, boundary match, and measured G2 continuity pass; derivative-matched root surfaces can have high local parameter-direction curvature without a material-side failure.

Required root failure reasons:

```text
v1_0_4_root_patch_orientation_failed
v1_0_4_root_material_side_failed
v1_0_4_root_width_nonuniform
v1_0_4_root_lift_nonuniform
v1_0_4_root_foldover
v1_0_4_root_projection_failed
v1_0_4_root_g2_measurement_failed
```

## Tip Surface Contract

The open tip surface is a bounded dome/cap generated from the blade tip closed loop.

Rules:

- The first UV row must equal the blade tip closed loop.
- All interior samples must remain inside the projected tip loop footprint when measured in the tip local frame.
- The dome crest must be a contracted loop or point set inside the boundary, never outside it.
- Tip area must be bounded by the blade tip loop envelope plus a small numerical tolerance.

Default open preset values:

```text
tip_dome_height_mm = 10.0
tip_dome_height_rule = 0.50 * average_blade_thickness_mm
tip_area_ratio_limit = 1.15
```

Required tip failure reasons:

```text
v1_0_4_tip_boundary_mismatch
v1_0_4_tip_exceeds_loop_domain
v1_0_4_tip_area_exceeds_limit
v1_0_4_tip_foldover
v1_0_4_tip_g2_measurement_failed
```

## Hub And Mounting Bore Contract

Hub material must be a named axisymmetric surface graph, not only a visual support surface.

Required open V1.0.4 hub faces:

```text
hub_main_revolve_surface
hub_top_cap_surface
hub_bottom_cap_surface
mounting_bore_inner_wall_surface
mounting_bore_top_edge_surface
mounting_bore_bottom_edge_surface
```

Hub meridional profile must be visibly concave:

```text
hub_profile_concavity_status = PASS
min_profile_curvature_proxy_mm > 1.0
max_linear_fit_residual_mm >= 12.0
```

Mounting bore rules:

- Bore radius equals `mounting_bore_radius_mm`.
- Bore wall is a cylinder or revolved vertical profile segment.
- Top and bottom cap inner rings share exact edge samples with bore wall.
- The bore must create a visible through-hole in the surface graph and exported mesh/STEP.

Required hub failure reasons:

```text
v1_0_4_hub_profile_conical_fallback
v1_0_4_hub_profile_not_concave
v1_0_4_hub_material_faces_missing
v1_0_4_mounting_bore_missing
v1_0_4_mounting_bore_edge_mismatch
```

## Blade-To-Hub Angle Contract

The default open preset must make blade surfaces meet the hub at an inspection-friendly angle:

```text
min_blade_hub_angle_deg >= 60.0
max_blade_hub_angle_deg <= 120.0
angle_sample_roles = pressure_root_edge, suction_root_edge, leading_root_corner, trailing_root_corner
```

Angles must be measured between the blade/root local material frame and the hub normal. The measurement must be emitted in `surface_graph["v1_0_4_angle_quality"]`.

Required angle failure reason:

```text
v1_0_4_blade_hub_angle_out_of_range
```

## G2 Measurement Contract

V1.0.4 may target G2 for sampled review-grade surfaces, but it must not claim G2 without measured evidence.

For every regular two-face edge:

```text
max_position_gap_mm <= 1.0e-6
max_tangent_angle_deg <= 2.0
max_normal_angle_deg <= 5.0
max_curvature_proxy_mismatch <= 0.25
```

Allowed continuity statuses:

```text
G2_MEASURED
G1_MEASURED_G2_FAILED
G0_ONLY_FAILED
EXTRAORDINARY_VERTEX_EXCLUDED
```

Required continuity failure reason:

```text
v1_0_4_g2_continuity_failed
```

## Viewer Contract

The frontend must separate these visual layers:

```text
shade_surfaces
nurbs_uv_wire
mesh_triangle_wire
control_curves
control_points
shared_edges
diagnostic_failures
```

Default visibility:

```text
shade_surfaces = on
nurbs_uv_wire = on
mesh_triangle_wire = off
control_curves = on
control_points = on
shared_edges = off
diagnostic_failures = on
```

Open tip reference/support surfaces must not be visible in normal review mode. Tip dome surfaces are visible because they are actual blade material faces.

## Preset Contract

The first open UI preset must remain:

```text
preset_id = radial_open_reference_v1_0
name includes "v1.0.4"
apiDefault = http://127.0.0.1:8061
```

Default values must be chosen to satisfy the V1.0.4 contracts:

```text
blade_count = 8
main_blade_count = 4
splitter_blade_count = 4
blade_thickness_mm = 20.0
root_attachment_width_mm = 10.0
root_attachment_lift_mm = 10.0
tip_dome_height_mm = 10.0
main_streamwise_start_u = 0.18
main_streamwise_end_u = 0.84
splitter_streamwise_start_u = 0.48
splitter_streamwise_end_u = 0.78
```

If these values are locally infeasible, the geometry must fail with a precise V1.0.4 reason. It must not silently shrink the root/tip surfaces or reduce blade extent.

## Validation And Tests

Required backend tests:

```text
tests/test_impeller_v10_4_resources.py
tests/test_impeller_v10_4_section_loop_contract.py
tests/test_impeller_v10_4_root_surface_contract.py
tests/test_impeller_v10_4_tip_surface_contract.py
tests/test_impeller_v10_4_hub_solid_contract.py
tests/test_impeller_v10_4_continuity_contract.py
tests/test_impeller_v10_4_angle_contract.py
tests/test_impeller_v10_4_surface_graph.py
```

Required frontend tests:

```text
frontend/src/appModel.test.js
frontend/src/appFiles.test.js
frontend/src/components/CurveControlPanel.test.js
frontend/src/simulationViewModel.test.js
frontend/src/workspaceModel.test.js
```

Required service smoke:

```text
radial_open_reference_v1_0:
  geometry_patch_version = 1.0.4
  surface_graph_status = PASS
  geometry_validation_status = PASS
  transition_geometry_status = topology_first_measured_g2_section_loop_root_tip_hub_solid_graph
  root_foldover_count = 0
  tip_area_ratio <= 1.15
  hub_profile_concavity_status = PASS
  mounting_bore_status = PASS
```

## Evidence Requirements

Every V1.0.4 implementation turn must update:

```text
docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md
docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md
docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md
```

The logs must include:

- before/after root cause;
- exact failing tests introduced;
- exact commands run;
- service ports used;
- any intentional regression or known limitation;
- screenshots or manifest-derived measurements when visual inspection drives a decision.

## Acceptance Criteria

V1.0.4 is accepted only when all are true:

1. The frontend first preset displays V1.0.4, not V0.97 or V1.0.3.
2. Open preset generation returns `geometry_patch_version = 1.0.4`.
3. Root patches have no foldover and no material-side inversion.
4. Root width/lift are approximately 10 mm with bounded variation.
5. Tip dome remains inside the blade tip loop and satisfies area ratio.
6. Hub profile is visibly concave and measured non-conical.
7. Mounting bore is a named through-hole surface set.
8. Section-loop UI displays one closed loop with segment control data.
9. G2 claims are backed by continuity measurements or downgraded explicitly.
10. Shaded, UV wire, mesh wire, controls, and diagnostics are separate viewer layers.
11. Backend and frontend targeted tests pass.
12. Service smoke passes on `http://127.0.0.1:8061`.
