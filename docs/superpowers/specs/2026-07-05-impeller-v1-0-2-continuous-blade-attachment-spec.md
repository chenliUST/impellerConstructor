# V1.0.2 Continuous Blade Attachment Constructor Spec

**Date:** 2026-07-05

## Summary

V1.0.2 upgrades the V1.0 topology-first impeller constructor from a named-face adapter into a coherent continuous blade attachment constructor.

The key semantic change is:

```text
blade = one six-face surface complex grown from hub/shroud support domains
```

The blade is no longer allowed to be interpreted as pressure/suction surfaces plus renamed closure strips. The pressure, suction, leading-edge, trailing-edge, tip, and root faces must be generated as one coupled surface complex with shared boundary loops, shared derivative frames, and measurable G2 targets wherever the topology is a regular two-face interface.

V1.0.2 applies to the whole V1.0.2 topology-first preset family, not only to the first UI example used during debugging. The initial mandatory presets are:

```text
radial_open_reference_v1_0
radial_closed_reference_v1_0
```

Any existing or future preset routed through the V1.0.2 continuous-blade constructor must satisfy the same default G2, attachment, and support-domain constraints before it can be exposed in the UI. A preset must not be accepted as "inspection ready" merely because the first open preset works.

The older public-data and mechanical-analogy V0.9 presets remain historical comparison cases and must not be silently migrated.

## User Intent Restatement

The user-observed failure is not a color or viewer issue. The visible geometry still behaves like primitive closure geometry:

1. Tip, leading edge, and trailing edge faces look planar and do not show actual smooth G2 transition into pressure/suction surfaces.
2. Root is now visually ring-like, but the inner loop does not match the blade exterior loop, so it does not look continuous with pressure/suction/edge faces.
3. Root needs default physical width and thickness so that the hub-to-blade boss is visible and reviewable.
4. The full six-face blade must grow from the hub; no blade face, root loop, or attachment boss may exceed the support-domain boundary in a way that makes the blade float, penetrate, or overshoot the hub.
5. For closed impellers, the blade tip is not an exposed cap. It must become a shroud/outer-hub attachment surface constructed with the same attachment logic as the root surface.
6. All V1.0.2 presets must default to G2 blade transitions and must ship with compliant default dimensions. If the blade/hub/shroud relationship introduces a new constraint, preset defaults must be adjusted to satisfy it rather than leaving the preset in a failing state.

The design target is therefore a construction-rule correction, not a local patch.

## Version Identity

V1.0.2 keeps the public API version family as V1.0 unless the runtime needs a more specific patch marker:

```text
geometry_version = "1.0"
geometry_patch_version = "1.0.2"
transition_geometry_status = "topology_first_continuous_blade_attachment_surface_graph"
mesh_strategy = "topology_first_shared_edge_continuous_blade_quad_mesh"
kernel_capability_matrix_id = "impeller_v1_0_2_kernel_capabilities"
golden_case_registry_id = "impeller_v1_0_2_golden_cases"
```

If compatibility requires keeping `transition_geometry_status = "topology_first_closed_nurbs_impeller_surface_graph"`, then V1.0.2 must still emit:

```text
surface_graph.geometry_patch_version = "1.0.2"
surface_graph.continuous_blade_attachment_status = "PASS"
```

## Scope

### In Scope

- Every preset routed to the V1.0.2 topology-first continuous-blade constructor.
- The initial mandatory open and closed radial throughflow presets.
- Preset-default normalization so every V1.0.2 preset starts from a support-domain-compliant parameter set.
- Continuous six-face blade surface complex generation.
- G2 target construction for:
  - pressure to leading edge;
  - suction to leading edge;
  - pressure to trailing edge;
  - suction to trailing edge;
  - pressure to tip attachment/cap;
  - suction to tip attachment/cap;
  - root attachment inner loop to all blade exterior faces where regular topology allows it.
- Root attachment boss with default width and thickness.
- Closed impeller tip-to-shroud attachment surface using root-like support-domain construction.
- Hub/shroud support-domain clamping and validation.
- Viewer-visible UV/wire diagnostics for the attachment and G2 transition faces.
- Regression protection for V0.9-V0.97 behavior.

### Out Of Scope

- Exact analytic OCCT fillet generation.
- Full watertight sewing into production STEP solids.
- Hub bottom/top outer chamfer reintroduction.
- Migrating V0.9 public-data or mechanical-analogy presets to V1.0.2.
- CAM/manufacturing annotations.
- Full CFD boundary-layer mesh generation.

## Required Construction Model

### 1. Six-Face Blade Surface Complex

Each blade instance must be constructed as a single logical complex:

```text
blade_i_complex:
  pressure_surface
  suction_surface
  leading_edge_surface
  trailing_edge_surface
  root_attachment_surface
  tip_surface_or_tip_attachment_surface
```

All six faces must derive from one shared source object:

```text
blade_section_frame_lattice
```

The lattice must contain, for each streamwise/spanwise station:

- point on pressure side;
- point on suction side;
- section chord direction;
- section thickness direction;
- local camber tangent;
- local span tangent;
- material-side normal;
- curvature proxy for pressure side;
- curvature proxy for suction side;
- attachment support-domain coordinates.

The constructor must not independently generate root, tip, leading, or trailing faces from separate midpoint/chord heuristics.

### 2. Shared Loops

The blade complex must expose these exact shared loops:

```text
pressure_root_loop
suction_root_loop
leading_root_corner_loop
trailing_root_corner_loop
pressure_tip_loop
suction_tip_loop
leading_tip_corner_loop
trailing_tip_corner_loop
leading_pressure_loop
leading_suction_loop
trailing_pressure_loop
trailing_suction_loop
```

The same list of coordinates, or references to the same coordinate source, must be used by both incident faces. Shared edges are structural, not tolerance-matched after the fact.

### 3. Edge Surface G2 Construction

Leading, trailing, and open-tip faces must be built as NURBS or sampled B-spline patches with at least:

```text
short_direction_sample_count >= 17
short_direction_control_count >= 5
degree_short >= 3
degree_span_or_stream >= 3
```

For each short-direction section from pressure to suction:

```text
P0 = pressure boundary point
P1/P2 = pressure-side derivative handles
M = material-side convex handle or shape-control point
Q2/Q1 = suction-side derivative handles
Q0 = suction boundary point
```

The handles must be computed from retained adjacent face derivative frames:

```text
P1 = P0 + alpha_p * pressure_cross_edge_tangent
P2 = P1 + beta_p * pressure_curvature_proxy
Q1 = Q0 + alpha_s * suction_cross_edge_tangent
Q2 = Q1 + beta_s * suction_curvature_proxy
```

The midpoint handle must be on the material side and must not collapse to the chord midpoint. If the computed G2 handles are infeasible, the surface must fail or downgrade with an explicit reason. It must not silently emit a planar strip.

Required metrics per edge face:

```text
continuity_claim
short_direction_sample_count
short_direction_control_count
min_midpoint_bulge_mm
min_curvature_proxy_mm
max_section_tangent_flip_deg
max_normal_flip_deg
foldover_count
g2_measurement_status_by_shared_edge
```

Minimum visual-review gate:

```text
min_midpoint_bulge_mm >= max(1.0, 0.12 * effective_radius_mm)
foldover_count == 0
max_section_tangent_flip_deg < 90
```

### 4. Root Attachment Surface

The root is a support-domain attachment surface, not a blade bottom cap.

The root surface must be defined by:

```text
inner_loop = exact closed blade exterior root loop
outer_loop = offset/projected loop on hub support surface
attachment_sections = G2-target sections from hub outer loop to blade inner loop
```

The inner loop must be assembled from the same source loops used by the blade faces:

```text
pressure_root_loop
trailing_root_corner_loop
reversed(suction_root_loop)
leading_root_corner_loop
```

The outer loop must be generated in the hub support parameter domain, not by naive radial XYZ offset. The solver must:

1. Convert the inner loop to hub support coordinates.
2. Offset in hub-surface parameter space by root attachment width.
3. Project back to the hub revolved NURBS surface.
4. Validate projection residual.
5. Validate that the loop remains inside hub support-domain bounds.

Default root dimensions:

```text
root_attachment_width_mm = max(1.20 * root_fillet_radius_mm, 0.55 * blade_thickness_mm, 16.0)
root_attachment_lift_mm = max(0.18 * root_fillet_radius_mm, 0.12 * blade_thickness_mm, 4.0)
root_attachment_short_direction_sample_count = 17
```

The `root_attachment_lift_mm` is a visual and geometric review-grade boss height along the local support-to-blade material direction. It is not a separate hub chamfer.

Required root metrics:

```text
root_topology = "support_domain_annular_attachment_boss"
inner_loop_source = "blade_exterior_root_loop"
outer_loop_source = "hub_support_parameter_offset"
root_attachment_width_mm
root_attachment_lift_mm
hub_projection_max_residual_mm
inner_loop_max_gap_to_blade_faces_mm
outer_loop_max_gap_to_hub_surface_mm
min_midpoint_bulge_mm
foldover_count
support_domain_violation_count
```

Blocking failures:

```text
v1_0_2_root_inner_loop_mismatch
v1_0_2_root_hub_projection_failed
v1_0_2_root_support_domain_violation
v1_0_2_root_boss_width_missing
v1_0_2_root_boss_lift_missing
v1_0_2_root_foldover
```

### 5. Open Tip Surface

For open impellers, the tip face is an exposed blade face. It must connect pressure and suction surfaces with a visible G2 target section. It must not be a planar cap.

The open tip reference support surface remains construction-only:

```text
tip_reference_surface.display.visible_by_default = false
tip_reference_surface.display.construction_reference = true
```

The open tip face may use the tip support profile for boundary placement, but its rendered/material face must be the blade tip transition surface.

### 6. Closed Tip Attachment Surface

For closed impellers, the blade tip must use attachment construction analogous to the root:

```text
inner_loop = exact closed blade exterior tip loop
outer_loop = offset/projected loop on shroud/front-hood inner support surface
attachment_sections = G2-target sections from blade tip loop to shroud support loop
```

The surface id may remain:

```text
blade_{i}_tip_surface
```

But the role must be:

```text
role = "tip_to_shroud_attachment_surface"
tip_topology = "support_domain_annular_attachment_boss"
```

Required closed-tip metrics:

```text
shroud_projection_max_residual_mm
inner_loop_max_gap_to_blade_faces_mm
outer_loop_max_gap_to_shroud_surface_mm
tip_attachment_width_mm
tip_attachment_lift_mm
foldover_count
support_domain_violation_count
```

Blocking failures:

```text
v1_0_2_tip_inner_loop_mismatch
v1_0_2_tip_shroud_projection_failed
v1_0_2_tip_support_domain_violation
v1_0_2_tip_attachment_width_missing
v1_0_2_tip_attachment_lift_missing
v1_0_2_tip_foldover
```

## Support-Domain Constraint

The blade complex must be grown from support surfaces:

```text
root support = hub_revolve_surface
open tip support = construction-only tip_reference_surface
closed tip support = shroud_surface or front_shroud_inner_surface
```

V1.0.2 must enforce:

```text
all root outer-loop points lie on hub support domain
all closed tip outer-loop points lie on shroud support domain
all blade root/tip station points remain within valid support u/v bounds
no blade face extends beyond support-domain clipping boundary
no attachment section crosses through hub/shroud material in the wrong direction
```

Required validation fields:

```text
support_domain_status
support_domain_violation_count
support_domain_violation_samples
max_hub_domain_residual_mm
max_shroud_domain_residual_mm
max_blade_overhang_mm
```

Blocking failures:

```text
v1_0_2_blade_exceeds_hub_domain
v1_0_2_blade_exceeds_shroud_domain
v1_0_2_attachment_material_side_failed
v1_0_2_support_projection_residual_exceeded
```

## Preset Parameter Feasibility Contract

V1.0.2 presets must be valid by default. The constructor may reject user overrides that break support-domain feasibility, but the shipped preset defaults must not rely on user edits to pass.

For every V1.0.2 preset, the runtime compiler must compute and expose:

```text
preset_feasibility_status
preset_feasibility_constraints
preset_adjusted_defaults
preset_default_violation_count
```

Required default feasibility checks:

```text
blade_count is low enough for visible attachment inspection
blade_thickness_mm fits inside inter-blade pitch with attachment margin
root_attachment_width_mm fits on hub support domain
root_attachment_lift_mm does not invert the root attachment section
tip_attachment_width_mm fits on open tip or closed shroud support domain
tip_attachment_lift_mm does not invert the tip attachment section
leading_edge_radius_mm fits local pressure/suction section width
trailing_edge_radius_mm fits local pressure/suction section width
hub/support profile has enough radial/axial room for root outer loop
closed shroud profile has enough room for tip outer loop
mounting bore radius and hub wall thickness leave sufficient hub material under root attachment
```

Recommended default relationships:

```text
inter_blade_pitch_at_root_mm = 2*pi*root_attachment_mean_radius_mm / blade_count
minimum_pitch_clearance_mm = blade_thickness_mm + 2*root_attachment_width_mm

blade_count must satisfy:
  inter_blade_pitch_at_root_mm >= 1.15 * minimum_pitch_clearance_mm

hub_wall_thickness_mm must satisfy:
  hub_wall_thickness_mm >= root_attachment_lift_mm + 0.25 * blade_thickness_mm

hub_bottom_thickness_mm must satisfy:
  hub_bottom_thickness_mm >= max(0.30 * root_attachment_width_mm, 8.0)

closed hood_wall_thickness_mm must satisfy:
  hood_wall_thickness_mm >= tip_attachment_lift_mm + 0.15 * blade_thickness_mm
```

If a preset default violates these formulas, the preset owner must adjust one or more of:

```text
blade_count
blade_thickness_mm
root_fillet_radius_mm
tip_edge_radius_mm
root_attachment_width_mm
root_attachment_lift_mm
tip_attachment_width_mm
tip_attachment_lift_mm
hub_wall_thickness_mm
hub_bottom_thickness_mm
hood_wall_thickness_mm
hub_profile control points
tip/shroud profile control points
```

The compiler may derive missing attachment defaults, but it must not silently clamp an infeasible preset into a different geometry. Derived defaults must be reported in `preset_adjusted_defaults`; infeasible defaults must fail with:

```text
v1_0_2_preset_default_infeasible
v1_0_2_preset_blade_pitch_insufficient
v1_0_2_preset_hub_material_insufficient
v1_0_2_preset_shroud_material_insufficient
v1_0_2_preset_attachment_default_missing
```

## Continuity Contract

### Regular Shared Edges

G2 is required as a construction target and validation measurement for regular two-face shared edges:

```text
pressure <-> leading_edge
suction <-> leading_edge
pressure <-> trailing_edge
suction <-> trailing_edge
pressure <-> open_tip
suction <-> open_tip
root_attachment inner loop <-> blade exterior root loop
closed_tip_attachment inner loop <-> blade exterior tip loop
```

The constructor may report:

```text
G2_MEASURED
G2_TARGET_REVIEW_GRADE
G2_DOWNGRADED
FAIL
```

It must not report `G2` if all second-derivative or curvature proxy values are zero.

### Extraordinary Vertices

At multi-face corners, such as leading-root, trailing-root, leading-tip, and trailing-tip, V1.0.2 must not claim unsupported global G2. It must report local edge continuity and corner coupling quality separately:

```text
corner_position_gap_mm
corner_tangent_mismatch_deg
corner_normal_mismatch_deg
corner_curvature_proxy_mismatch
corner_status
```

## Preset Defaults

For every V1.0.2 topology-first preset, defaults must make the transition surfaces visible enough for human inspection and must satisfy the support-domain feasibility contract. The first open throughflow example is not a special case; it is only the first regression target.

Required default policy values:

```text
blade_leading_edge.default.continuity = G2
blade_trailing_edge.default.continuity = G2
blade_tip_or_shroud.default.continuity = G2
blade_root_to_hub.default.continuity = G2

root_attachment_width_mm = max(1.20 * root_fillet_radius_mm, 0.55 * blade_thickness_mm, 16.0)
root_attachment_lift_mm = max(0.18 * root_fillet_radius_mm, 0.12 * blade_thickness_mm, 4.0)
tip_attachment_width_mm = max(1.00 * tip_edge_radius_mm, 0.45 * blade_thickness_mm, 12.0)
tip_attachment_lift_mm = max(0.16 * tip_edge_radius_mm, 0.10 * blade_thickness_mm, 3.0)

edge_short_direction_sample_count >= 17
attachment_short_direction_sample_count >= 17
```

Blade count and blade thickness remain review-oriented, but they are no longer fixed constants. Each preset must use values that pass pitch, support-domain, and attachment feasibility checks.

```text
default blade_count target = 4, unless feasibility requires fewer/more
default blade_thickness_mm target = 92.0, unless feasibility requires adjustment
```

Every preset must emit the final resolved defaults:

```text
resolved_blade_count
resolved_blade_thickness_mm
resolved_root_attachment_width_mm
resolved_root_attachment_lift_mm
resolved_tip_attachment_width_mm
resolved_tip_attachment_lift_mm
resolved_support_domain_margins
```

Hub bottom/top outer chamfer remains disabled by default.

## Frontend Requirements

The frontend must make V1.0.2 diagnosable:

1. Default open preset must hide `tip_reference_surface`.
2. Root attachment surfaces must use the high-contrast inspection palette:

```text
fill = "#ff00cc"
wire = "#fff200"
```

3. Tip-to-shroud attachment surfaces in closed mode need their own inspection class:

```text
inspection_class = "tip_to_shroud_attachment"
fill = "#00e5ff"
wire = "#fff200"
```

4. The viewer must expose face-family isolation for:
   - pressure;
   - suction;
   - leading edge;
   - trailing edge;
   - root attachment;
   - open tip;
   - closed tip attachment;
   - hub support;
   - shroud support.
5. UV/wire overlay must remain visible on G2 transition and attachment faces.
6. Manifest panels must expose:
   - G2 measurement status;
   - bulge;
   - foldover count;
   - support-domain residuals;
   - root/tip attachment width and lift.

## Backend Test Requirements

### Resource Tests

Add:

```text
tests/test_impeller_v10_2_resources.py
```

Required assertions:

- Every V1.0.2 topology-first preset compiles with V1.0.2 patch metadata.
- Every V1.0.2 topology-first preset resolves G2 blade transition policies.
- Every V1.0.2 topology-first preset reports `preset_feasibility_status = PASS`.
- Hub bottom/top outer chamfers are disabled.
- Attachment width/lift defaults are present or derivable.
- Resolved default dimensions are present and satisfy pitch/support-domain feasibility formulas.

### Edge G2 Tests

Add:

```text
tests/test_impeller_v10_2_edge_g2_surfaces.py
```

Required assertions:

- Leading, trailing, and open-tip surfaces have at least 17 short-direction samples.
- Short-direction sections are not planar chord strips.
- G2 measurement status is emitted per shared edge.
- Replacing a face with straight chord samples fails validation.

### Root Attachment Tests

Add:

```text
tests/test_impeller_v10_2_root_attachment.py
```

Required assertions:

- Root inner loop equals the blade exterior root loop within tolerance.
- Root outer loop projects to hub support surface within tolerance.
- Root width and lift are positive and match defaults.
- Root foldover count is zero.
- Root support-domain violation count is zero.
- A mismatched inner loop fails with `v1_0_2_root_inner_loop_mismatch`.

### Closed Tip Attachment Tests

Add:

```text
tests/test_impeller_v10_2_closed_tip_attachment.py
```

Required assertions:

- Closed preset emits `tip_to_shroud_attachment_surface` semantics.
- Tip inner loop equals the blade exterior tip loop within tolerance.
- Tip outer loop projects to shroud support surface within tolerance.
- Tip foldover count is zero.
- A planar cap fails for closed impeller.

### Support Domain Tests

Add:

```text
tests/test_impeller_v10_2_support_domain.py
```

Required assertions:

- Blade root does not exceed hub support-domain bounds.
- Closed blade tip does not exceed shroud support-domain bounds.
- Deliberately over-offset attachment loops fail validation.

### Frontend Tests

Add or extend:

```text
frontend/src/simulationViewModel.test.js
frontend/src/workspaceModel.test.js
frontend/src/appFiles.test.js
```

Required assertions:

- Hidden construction tip reference remains hidden outside feature debug.
- Root attachment color/wire priority is preserved.
- Closed tip attachment inspection class has priority over generic tip color.
- V1.0.2 manifest metrics are rendered.

## Acceptance Criteria

### All V1.0.2 Presets

Every V1.0.2 preset must satisfy:

```text
geometry_validation_status = PASS
continuous_blade_attachment_status = PASS
preset_feasibility_status = PASS
all blade transition policies default to G2
resolved default dimensions are emitted
support_domain_violation_count = 0
foldover_count = 0 for all blade transition and attachment faces
```

If a preset is added to the V1.0.2 family and fails any of these checks, it must not appear as a normal UI preset. It may only appear as an explicit failing diagnostic/golden-negative case.

### Open V1.0.2 Presets

For every open V1.0.2 preset, including `radial_open_reference_v1_0`:

```text
geometry_validation_status = PASS
continuous_blade_attachment_status = PASS
tip_reference_surface.display.visible_by_default = false
hub bottom/top outer chamfer absent or disabled
leading/trailing/tip surfaces are curved G2-target patches
root is support-domain annular attachment boss
root inner loop matches blade exterior root loop
root outer loop lies on hub support surface
support_domain_violation_count = 0
foldover_count = 0 for all blade transition and attachment faces
```

### Closed V1.0.2 Presets

For every closed V1.0.2 preset, including `radial_closed_reference_v1_0`:

```text
geometry_validation_status = PASS
continuous_blade_attachment_status = PASS
shroud surface visible as material support
tip surface role = tip_to_shroud_attachment_surface
tip inner loop matches blade exterior tip loop
tip outer loop lies on shroud/front-hood support surface
root attachment criteria pass
support_domain_violation_count = 0
foldover_count = 0 for all blade transition and attachment faces
```

### Human Review Criteria

The generated geometry must make these features visually inspectable:

- leading and trailing edge faces are curved, not flat rectangles;
- open tip face is curved between pressure and suction surfaces;
- root boss has visible width and thickness;
- root boss inner edge follows the actual blade root perimeter;
- closed tip attachment behaves like a shroud-grown attachment, not a cap;
- no blade appears to extend past or float outside the hub/shroud support boundary.

## Implementation Notes

V1.0.2 should not be implemented as another layer of display metadata. The implementation should introduce explicit builder units:

```text
impeller_v10_2_blade_lattice.py
impeller_v10_2_g2_edge_surface.py
impeller_v10_2_support_attachment.py
impeller_v10_2_support_domain.py
impeller_v10_2_continuity_validation.py
```

The existing `axisymmetric_throughflow_nurbs` math can remain the source for hub, shroud, pressure, and suction placement, but V1.0.2 must derive all native blade transition and attachment faces from a shared blade lattice, not from independently rewritten closure grids.

## Risks

1. True G2 across sampled NURBS patches is difficult without analytic derivative surfaces.
   - Mitigation: use explicit derivative-frame handles and report review-grade measured status.
2. Root and closed-tip support projection can fail for aggressive blade thickness or support profile curvature.
   - Mitigation: fail with explicit support-domain reasons instead of silently clamping.
3. Corner G2 is not generally valid where many faces meet.
   - Mitigation: edge-scope G2 claims and emit separate corner metrics.
4. Mesh density may increase substantially.
   - Mitigation: use deterministic sampling limits and keep V1.0.2 review-grade.

## Non-Negotiable Rules

- Do not reintroduce primitive disk/blade fallback geometry.
- Do not claim G2 from zero second derivatives.
- Do not generate root as a blade bottom cap.
- Do not show open tip reference surface as material.
- Do not enable hub bottom/top outer chamfer by default.
- Do not migrate V0.9 public-data or analogy presets into V1.0.2 without a separate spec.
- Do not allow a V1.0.2 preset to pass validation if blade attachment exceeds hub/shroud support-domain bounds.
