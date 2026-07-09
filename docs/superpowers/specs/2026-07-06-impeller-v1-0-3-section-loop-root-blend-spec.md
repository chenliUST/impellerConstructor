# Impeller V1.0.3 Section-Loop Blade And Robust Root Blend Spec

**Date:** 2026-07-06

## Summary

V1.0.3 upgrades the V1.0 topology-first impeller constructor from a
surface-adapter and attachment-patch model into a section-loop-first blade
constructor.

The key semantic change is:

```text
blade = lofted section-loop surface complex with support-domain root blend
```

Each blade station must start from a closed NURBS section loop. The loop is
split into pressure-side, suction-side, leading-edge, and trailing-edge curve
segments. The blade faces are lofts of those curve families. Root and open-tip
faces are constructed from the same section-loop source, not from independent
closure strips or endpoint-only annular patches.

This version specifically fixes the observed failure where the suction-side root
blend can run below the blade. That symptom is treated as a material-side and
support-domain construction failure, not as a local suction-side rendering bug.

## User Intent Restatement

The user confirmed these V1.0.3 goals:

1. The previous phrase "root width and height should be comparable to blade
   average height" was a typo. The correct requirement is:

   ```text
   root width and root lift/height should be comparable to blade average thickness
   ```

2. The default topology-first open throughflow preset currently has blades that
   are too long. Leading and trailing regions reach the hub support bounds, so
   the root blend has little or no visible width. V1.0.3 presets must shorten
   the blade relative to the hub/tip support domain.

3. The default open inspection preset should use four blade pairs:

   ```text
   4 main blades + 4 splitter blades
   ```

   Splitter blades are shorter than main blades and live in the passages between
   main blades.

4. The blade thickness should be reduced to approximately one third of the
   current V1.0.2 default. Root width, root lift, edge radii, and tip dome height
   must be rescaled from this new average thickness.

5. Blade design should follow common section-based practice: first define a
   section loop, then split it into four NURBS curve segments. Pressure and
   suction segments are relatively mild. Leading and trailing edge segments are
   highly curved and near arc-like.

6. The open blade tip needs a dome surface. It is the blade top face, not a
   visible blade-tip reference support and not a shroud attachment.

7. Frontend shape control must expose NURBS curves and control points for:

   - blade section loop;
   - blade section segment curves;
   - hub profile curve;
   - tip dome controls.

   The curve itself, control points, and control polygon must be visible.

8. Every transition face must provide wireframe and mesh inspection. The
   generated geometry must include measurable checks for tangent, normal,
   curvature proxy, material side, and foldover.

## Version Identity

V1.0.3 remains in the public V1.0 family but must expose a patch marker:

```text
geometry_version = "1.0"
geometry_patch_version = "1.0.3"
transition_geometry_status = "topology_first_section_loop_blade_root_blend_surface_graph"
mesh_strategy = "section_loop_shared_edge_review_grade_quad_mesh"
kernel_capability_matrix_id = "impeller_v1_0_3_kernel_capabilities"
golden_case_registry_id = "impeller_v1_0_3_golden_cases"
```

If compatibility requires retaining the older transition status string in some
manifests, `surface_graph.geometry_patch_version = "1.0.3"` and a V1.0.3
constructor status field are still mandatory.

## Scope

### In Scope

- Topology-first open throughflow preset as the first mandatory acceptance case.
- V1.0.3 defaults for all presets routed through the V1.0.3 constructor.
- Four main blades plus four splitter blades in the default open inspection
  preset.
- Section-loop-first blade construction.
- Frontend-editable NURBS control points for blade section loops and hub
  profiles.
- Open-tip dome construction.
- Robust segmented support-domain Hermite/G2 root blend.
- Wireframe and mesh emission for pressure, suction, leading, trailing, root,
  and tip/dome faces.
- Validation gates for tangent, normal, curvature proxy, material side, support
  domain, and foldover.
- Evidence logs for semantic changes, geometric diagnostics, and insights.

### Out Of Scope

- Production OCCT analytic fillets.
- Fully watertight STEP sewing as a manufacturing solid.
- Closed-tip shroud corner coupling as a mandatory V1.0.3 acceptance item.
- Reintroducing hub outer chamfers.
- Migrating V0.9-V0.97 presets into V1.0.3.
- Full CFD boundary-layer meshing.

Closed impeller tip-to-shroud coupling remains a separate follow-up because it
requires dedicated corner/shroud patches. V1.0.3 may keep closed presets
available, but open topology-first throughflow is the primary correctness gate.

## Required Construction Model

### 1. Preset Feasibility Defaults

The default V1.0.3 open preset must be resized before construction:

```text
main_blade_count = 4
splitter_blade_count = 4
blade_pair_count = 4
blade_thickness_mm ~= previous_v1_0_2_thickness / 3
root_attachment_width_mm ~= k_width * average_blade_thickness_mm
root_attachment_lift_mm ~= k_lift * average_blade_thickness_mm
tip_dome_height_mm ~= k_dome * average_blade_thickness_mm
```

Recommended initial scale factors:

```text
k_width = 1.0 .. 1.6
k_lift = 0.6 .. 1.2
k_dome = 0.5 .. 1.0
```

The constructor must derive the effective values from the section thickness
distribution, not from blade height.

The blade meridional domain must include support margins:

```text
leading_edge_support_margin_mm > root_attachment_width_mm
trailing_edge_support_margin_mm > root_attachment_width_mm
root_footprint_inside_hub_domain = true
tip_loop_inside_tip_support_domain = true
```

If these constraints fail, the preset must be rejected or internally adjusted
before becoming a default UI preset.

### 2. Blade Population: Main And Splitter Blades

The V1.0.3 blade population model must distinguish blade classes:

```text
blade_population:
  main:
    count = 4
    streamwise_extent = full
    phase = 0
  splitter:
    count = 4
    streamwise_extent = partial
    phase = half passage offset
```

Each blade instance must carry:

```text
blade_class = "main" | "splitter"
blade_pair_index
passage_index
streamwise_start_u
streamwise_end_u
section_loop_family_id
```

Splitter blades must use the same section-loop construction logic as main
blades, but with shorter streamwise extent and local feasibility checks.

### 3. Section-Loop Source Object

For each blade station, the constructor must build:

```text
blade_section_loop:
  coordinate_frame:
    origin
    camber_tangent
    span_tangent
    thickness_direction
    material_normal
  segments:
    pressure_side
    leading_edge
    suction_side
    trailing_edge
  shared_vertices:
    pressure_leading
    leading_suction
    suction_trailing
    trailing_pressure
```

Each segment is a NURBS curve or sampled B-spline curve with:

```text
degree >= 3
control_point_count >= 5 for PS/SS
control_point_count >= 5 for LE/TE
weights
knots
sample_count >= 17
```

Pressure and suction segments should have lower curvature. Leading and trailing
segments should be convex, arc-like, and visibly rounded.

The four segment endpoints must be exactly shared. The constructor must not
copy and tolerance-match endpoint coordinates after the fact.

### 4. Section Loop G2 Continuity

At each section-loop join, the constructor must check:

```text
position_gap_mm
tangent_angle_deg
normal_angle_deg
curvature_proxy_mismatch
material_side_sign
```

Target gates:

```text
position_gap_mm <= 1e-6
tangent_angle_deg <= 5 deg
normal_angle_deg <= 8 deg
curvature_proxy_mismatch <= configured review-grade tolerance
material_side_sign > 0
```

If G2 is infeasible, the builder must report one of:

```text
v1_0_3_section_loop_g2_infeasible
v1_0_3_section_loop_material_side_ambiguous
v1_0_3_section_loop_endpoint_mismatch
v1_0_3_section_loop_foldover
```

It must not silently emit a planar or right-angle closure.

### 5. Face Lofting From Section Segments

The blade faces are generated by lofting corresponding segment families:

```text
pressure_surface = loft(section[i].pressure_side)
suction_surface = loft(section[i].suction_side)
leading_edge_surface = loft(section[i].leading_edge)
trailing_edge_surface = loft(section[i].trailing_edge)
```

All faces must reference the same section-loop source. Shared boundaries must
be structural:

```text
pressure.leading == leading.pressure
leading.suction == suction.leading
suction.trailing == trailing.suction
trailing.pressure == pressure.trailing
```

No face may independently regenerate a boundary loop from another surface's
display grid.

### 6. Open Tip Dome Surface

For open impellers, the tip face is a dome, not a flat cap:

```text
tip_dome_surface:
  boundary_loop = blade_tip_section_loop
  crest_curve = section-loop camber/center curve lifted along material normal
  dome_height = thickness-scaled default
  construction = Coons/Gordon-style or tensor-product NURBS patch with internal crest controls
```

The dome must satisfy:

```text
dome_height_mm ~= 0.5 .. 1.0 * average_blade_thickness_mm
tip_dome_boundary_gap_mm <= 1e-6
tip_dome_foldover_count == 0
tip_dome_material_side_valid = true
```

The dome must expose:

```text
edge_samples.tip_section_loop
edge_samples.tip_crest_curve
display.inspection_class = "open_tip_dome"
wireframe = true
mesh = true
```

The open-tip reference support surface remains hidden by default.

## Robust Root Surface Method

### Method Name

V1.0.3 root construction is defined as:

```text
section-loop-driven segmented support-domain Hermite/G2 root blend
```

The root is not a blade bottom cap and not a single annular UV sheet. It is a
segmented support-domain transition from the hub footprint to the blade root
section loop.

### Root Inputs

The root builder receives:

```text
blade_root_section_loop
hub_revolved_support_surface
section_frame_lattice
average_blade_thickness_mm
root_width_mm
root_lift_mm
material_domain
```

`blade_root_section_loop` is the exact blade root exterior loop:

```text
pressure_root_segment
leading_root_segment
suction_root_segment
trailing_root_segment
```

### Hub Footprint Projection

The builder first projects the blade root loop into the hub support parameter
domain:

```text
hub_domain = (theta, meridional_z_or_profile_u)
projected_blade_footprint = project(blade_root_section_loop, hub_domain)
```

Projection must be parameter-domain based, not unconstrained nearest-point 3D
search. This prevents suction-side points from jumping to the wrong side of the
hub.

Required projection metrics:

```text
max_projection_residual_mm
domain_bracket_success_count
domain_bracket_failure_count
support_z_clamp_count
support_domain_violation_count
```

### Outer Footprint Offset

The root outer loop is generated by offsetting the projected footprint in the
hub parameter domain:

```text
root_outer_footprint = offset(projected_blade_footprint, root_width_mm)
root_outer_loop = evaluate(hub_surface, root_outer_footprint)
```

Offset direction is determined by the closed footprint winding and the desired
outside material side. It must not be inferred independently for pressure and
suction segments from local cross products.

Required offset metrics:

```text
root_width_request_mm
min_effective_root_width_mm
max_effective_root_width_mm
winding_orientation
offset_self_intersection_count
support_domain_violation_count
```

### Segmented Root Patches

The root is emitted as visible segment patches:

```text
root_pressure_blend_patch
root_leading_corner_blend_patch
root_suction_blend_patch
root_trailing_corner_blend_patch
```

An aggregate root surface may be emitted for diagnostics, but it must not be
the default visible geometry.

### Hermite/G2 Root Sections

For each segment sample `s`, construct a section curve:

```text
C(0) = root_outer_loop[s] on hub support
C(1) = blade_root_loop[s] on blade exterior
```

Endpoint derivative rules:

```text
C'(0) = hub-surface tangent from outer footprint toward blade footprint
C'(1) = blade-face root derivative from root toward blade interior, reversed into the blend
```

Important: `C'(0)` is a tangent direction on the hub surface, not the hub normal.
The blend must leave the hub tangentially, then rise toward the blade.

The blade-side derivative must come from the incident blade face derivative
frame. It must not be reconstructed from a chord midpoint.

### Root Material-Side Validation

Every root section sample must satisfy:

```text
signed_height_to_hub >= -tolerance
outside_blade_material_domain = true
section_winding_consistent = true
root_section_foldover_count = 0
```

The signed height is computed from the hub normal and the hub support point.
If the suction-side blend runs below the blade or hub, this metric must become
negative and fail validation.

Required root failure reasons:

```text
v1_0_3_root_projection_failed
v1_0_3_root_footprint_offset_failed
v1_0_3_root_material_side_ambiguous
v1_0_3_root_signed_height_failed
v1_0_3_root_blade_derivative_missing
v1_0_3_root_hub_tangent_missing
v1_0_3_root_segment_foldover
v1_0_3_root_segment_g2_infeasible
v1_0_3_root_component_gap
```

### Root Acceptance Gates

The default open preset must satisfy:

```text
root_component_count == 4 per blade
root_aggregate_visible_by_default == false
max_root_inner_loop_gap_mm <= 1e-6
max_root_outer_loop_gap_to_hub_mm <= 1e-6
min_effective_root_width_mm >= 0.5 * requested_root_width_mm
max_tangent_flip_deg < 45
max_normal_flip_deg < 45
foldover_count == 0 for every visible root component patch
min_signed_height_to_hub_mm >= -1e-6
```

## Frontend Shape Control Requirements

### Curve Editing Model

The frontend must expose structured curve controls for:

```text
hub_profile_nurbs
tip_or_shroud_profile_nurbs
blade_section_loop_template
blade_section_pressure_segment
blade_section_suction_segment
blade_section_leading_segment
blade_section_trailing_segment
tip_dome_crest_curve
```

Each editable curve view must display:

```text
curve polyline or sampled curve
control points
control polygon
selected point state
drag/update interaction
reset-to-preset action
```

Curve edits must serialize through structured overrides:

```text
profile_overrides
curve_overrides
section_loop_overrides
```

They must not create duplicate scalar controls for the same geometry.

### Hub Curve Control

Hub profile editing must move beyond semantic scalar handles. The user must be
able to inspect and edit the actual NURBS control points for the hub meridional
profile. The frontend must show the control polygon and the sampled hub curve.

Validation feedback should include:

```text
hub_profile_self_intersection
hub_tip_profile_crossing
mounting_bore_clearance_violation
support_domain_margin_violation
```

### Blade Section Loop Control

The frontend should provide a section-loop editor that shows PS, SS, LE, and TE
segments with distinct visual styling. It should show continuity status at the
four joins.

Required visible diagnostics:

```text
control points by segment
shared endpoint markers
tangent handles
curvature or G2 status badges
material-side normal direction
```

## Mesh And Wireframe Requirements

Every V1.0.3 face must have:

```text
uv_grid
wireframe overlay data
mesh triangles/quads
display.inspection_class
face_family
role
```

Mandatory visible inspection classes:

```text
blade_pressure
blade_suction
blade_leading_edge
blade_trailing_edge
root_to_hub_blend
open_tip_dome
main_blade
splitter_blade
```

The mesh overlay must include root and tip/dome component patches. It must not
omit transition faces because they are generated after the main pressure/suction
surfaces.

## Validation And Tests

### Backend Resource Tests

Add or update tests for:

```text
tests/test_impeller_v10_3_resources.py
tests/test_impeller_v10_3_preset_defaults.py
```

Required checks:

```text
radial_open_reference_v1_0 routes to geometry_patch_version 1.0.3 when V1.0.3 is active
main_blade_count == 4
splitter_blade_count == 4
blade_thickness_mm ~= previous_default / 3
root_width/lift derive from average thickness
blade support margins are positive
```

### Section Loop Tests

Add:

```text
tests/test_impeller_v10_3_section_loop.py
```

Required checks:

```text
section loop has four segments
segment endpoints are shared exactly
LE/TE curvature exceeds PS/SS curvature
join tangent and normal metrics pass
no section-loop foldover
main and splitter section loops are both valid
```

### Root Blend Tests

Add:

```text
tests/test_impeller_v10_3_root_blend.py
```

Required checks:

```text
root projection uses hub parameter domain
root outer loop comes from footprint offset
root component count == 4
pressure and suction root components both stay on material side
min signed height to hub >= -1e-6
root inner loop exactly matches blade section root loop
root outer loop lies on hub support
visible root components have foldover_count == 0
synthetic suction-loop reversal fails with v1_0_3_root_material_side_ambiguous or is corrected before build
```

### Tip Dome Tests

Add:

```text
tests/test_impeller_v10_3_tip_dome.py
```

Required checks:

```text
open tip dome boundary equals blade tip section loop
dome crest rises on material side
dome height derives from average thickness
dome foldover_count == 0
dome has wireframe and mesh payload
open tip reference surface remains hidden by default
```

### Frontend Tests

Add/update tests for:

```text
section loop control points render before generation
hub profile control polygon is visible/editable
curve edits serialize through structured overrides
no duplicate scalar controls for curve-controlled values
root and tip/dome wireframe toggles affect visible transition surfaces
main/splitter blade metadata is visible in manifest/view model
```

### Required Verification Commands

Backend:

```text
python -m pytest tests/test_impeller_v10_3_resources.py tests/test_impeller_v10_3_preset_defaults.py -q
python -m pytest tests/test_impeller_v10_3_section_loop.py tests/test_impeller_v10_3_root_blend.py tests/test_impeller_v10_3_tip_dome.py -q
python -m pytest tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_surface_graph_integration.py tests/test_impeller_v10_2_validation.py -q
```

Frontend:

```text
cd frontend
npm.cmd test
```

Service smoke:

```text
POST /api/rule-engines/synthesize preset_id=radial_open_reference_v1_0
POST /api/rule-engines/{engine_id}/instantiate
```

Expected smoke fields:

```text
geometry_version == "1.0"
surface_graph.geometry_patch_version == "1.0.3"
geometry_validation_status == "PASS"
surface_graph_status == "PASS"
main_blade_count == 4
splitter_blade_count == 4
root_component_max_foldover == 0
open_tip_dome_foldover == 0
```

## Migration Notes

V1.0.3 should not delete V1.0.2 builders immediately. It should add a new
versioned path so V1.0.2 evidence remains reproducible:

```text
impeller_v10_3_section_loop.py
impeller_v10_3_root_blend.py
impeller_v10_3_tip_dome.py
impeller_v10_3_validation.py
```

V1.0.2 tests must continue to pass unless a test is explicitly migrated to the
V1.0.3 path.

## Acceptance Criteria

The V1.0.3 open throughflow preset is acceptable when:

1. The first UI preset visibly shows four main blades and four splitter blades.
2. Blades are shorter than the hub/tip support bounds and no longer touch the
   hub boundary at leading/trailing extremes.
3. Blade section-loop curves show pressure, suction, leading, and trailing
   segments with visible control points.
4. Hub profile curve and control polygon are visible and editable.
5. Leading and trailing edges are visibly rounded, not right-angle strips.
6. Open tip is a dome surface with visible wireframe and mesh.
7. Root blend is visible as four material-side component patches per blade.
8. Pressure-side and suction-side root blends both remain outside blade/hub
   material and do not run below the blade.
9. Every visible transition component has `foldover_count == 0`.
10. Backend tests, frontend tests, and HTTP smoke pass.

## Locked Decisions For Implementation Planning

The implementation plan must use these defaults unless the user explicitly
changes them before development starts:

1. The first UI open throughflow preset routes to V1.0.3 when V1.0.3 is
   implemented. V1.0.2 remains available only as a historical/debug path, not as
   the default inspection preset.
2. The first V1.0.3 open inspection default uses:

   ```text
   blade_thickness_mm = 32.0
   average_blade_thickness_mm = 32.0
   root_attachment_width_mm = 40.0
   root_attachment_lift_mm = 28.0
   tip_dome_height_mm = 24.0
   ```

   These values keep root width and height comparable to blade average
   thickness while remaining visibly inspectable.

3. Splitter blades inherit the same section-loop template as main blades in the
   first implementation. They differ by streamwise extent and angular phase, not
   by a separate airfoil template. A separate splitter section template may be
   added after the main/splitter construction is stable.

4. The frontend must expose editable control points in the first V1.0.3
   implementation. Read-only control points are insufficient for this release
   because the user explicitly needs NURBS curve adjustment in the frontend.

5. Closed impeller shroud coupling is not a blocking V1.0.3 default acceptance
   gate. The implementation may keep the closed preset on the V1.0.2 path until
   a dedicated closed-tip corner/shroud patch spec is written.
