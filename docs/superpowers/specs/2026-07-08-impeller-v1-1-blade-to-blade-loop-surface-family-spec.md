# Impeller V1.1 Blade-To-Blade Loop Surface Family Spec

Date: 2026-07-08

Status: Draft spec for implementation planning. This document defines the V1.1 semantic target; it is not an implementation log.

## 1. Summary

V1.1 replaces the V1.0.4 local section-loop interpretation with a blade-to-blade loop surface-family model.

The first implementation target uses five span stations from hub to tip/shroud. At each span station, the blade cross-boundary is defined as a closed loop in the unwrapped blade-to-blade domain, not in a local XY chord plane. The loop is split into four named segment curves: pressure side, suction side, leading edge, and trailing edge. These five loop stations are the only source of truth for the six generated blade face families:

1. pressure surface
2. suction surface
3. leading edge surface
4. trailing edge surface
5. root-to-hub attachment surface
6. open tip dome surface or closed shroud attachment surface

Root, tip, leading, and trailing surfaces are no longer independent patch repairs after pressure and suction faces exist. They consume the same shared loop-family boundary network and the same C2/G2 join data.

## 2. Problem Statement

V1.0.4 made several validation contracts explicit, but screenshots still show primitive-like blades, staple-shaped edge/root patches, oversized tip surfaces, and root surfaces crossing into material. The root cause is that the active "section loop" still mixes a local chord/thickness diagram with streamwise lofting. Once the loop domain is wrong, later fixes to root, tip, edge, or chamfer surfaces can only move artifacts around.

The accepted sandbox proved a better construction direction: define the blade loop in a blade-to-blade unwrapped stream-surface domain, then map the loop family onto the meridional hub/tip carrier. V1.1 makes that rule explicit and versioned.

## 3. Version Contract

V1.1 must be introduced as a new versioned path. Historical V1.0.4 behavior and tests remain available.

```text
geometry_version = "1.1"
geometry_patch_version = "1.1.0"
transition_geometry_status = "topology_first_blade_to_blade_5_loop_surface_family_graph"
mesh_strategy = "v1_1_loop_family_shared_boundary_uv_mesh"
source_kernel = "v1_1_blade_to_blade_surface_family_kernel"
kernel_capability_matrix_id = "impeller_v1_1_kernel_capabilities"
golden_case_registry_id = "impeller_v1_1_golden_cases"
```

Required preset ids:

```text
radial_open_reference_v1_1
radial_closed_reference_v1_1
```

Frontend labels should make the active version visible:

```text
Topology first open throughflow v1.1
Topology first closed throughflow v1.1
```

## 4. Coordinate Domains

### 4.1 Meridional Carrier

The hub and tip/shroud carrier is a smooth meridional R-Z profile, revolved or sampled into support surfaces. It defines where a span station lives in 3D, but it does not define the blade loop shape.

For V1.1 presets, the default hub and tip/shroud reference profiles should use the discussed concave control data, not a conical fallback:

```text
hub_profile_rz_mm:
  P0 = (150, 400)
  P1 = (170, 250)
  P2 = (220, 150)
  P3 = (330,  50)
  P4 = (480,  10)
  P5 = (580,   0)

tip_or_shroud_profile_rz_mm:
  P0 = (230, 401)
  P1 = (250, 270)
  P2 = (310, 170)
  P3 = (400,  90)
  P4 = (490,  50)
  P5 = (581,  30)
```

Open impellers may keep the tip reference profile as construction support, but normal viewer mode must not display it as a manufactured face.

### 4.2 Blade-To-Blade Loop Domain

At each span station `h`, the blade loop is defined in:

```text
D_h = (s, q)
s = normalized meridional streamwise coordinate
q = r * delta_theta, circumferential offset in millimeters
h = span coordinate from hub to tip/shroud
```

The 3D map is:

```text
(r, z) = carrier(s, h)
theta = theta_camber(s, h) + q / max(r, epsilon)
x = r * cos(theta + blade_phase)
y = r * sin(theta + blade_phase)
z = z
```

This makes `q` a physical circumferential offset rather than an arbitrary local chord axis. The XY view of a loop is only a projection for diagnostics.

### 4.3 Main And Splitter Blades

Main blades and splitter blades use the same domain and the same 3D map. They differ by streamwise interval and phase:

```text
main phase       = k * pitch
splitter phase   = (k + 0.5) * pitch + splitter_phase_bias
main s interval  = [s_main_le, s_main_te]
splitter interval = [s_splitter_le, s_splitter_te]
```

Splitter blades are not a separately scaled local chord primitive. They are shorter blade-to-blade loops in the same passage domain.

## 5. Five-Loop Family

The default V1.1 surface family uses five span stations:

```text
h = [0.00, 0.25, 0.50, 0.75, 1.00]
```

Each station owns one closed loop:

```text
L_h = PS_h + TE_h + reverse(SS_h) + LE_h
```

Where:

```text
PS_h(u) = pressure-side segment, leading edge to trailing edge
SS_h(u) = suction-side segment, leading edge to trailing edge
LE_h(v) = leading-edge cap, pressure side to suction side
TE_h(v) = trailing-edge cap, pressure side to suction side
```

The loop must be represented by enough controls to show realistic blade thickness variation and smooth edge caps:

```text
pressure-side controls per station >= 11
suction-side controls per station >= 11
leading-edge controls per station >= 9
trailing-edge controls per station >= 9
```

Pressure and suction curves should be broadly parallel in the blade-to-blade domain. Leading and trailing curves may be much more curved, approximating rounded blade noses/tails rather than rectangular caps. The S-shape is present but moderate; it must make blade twist readable without forcing self-intersection or excessive passage blockage.

## 6. C2/G2 Join Contract

Each loop join must carry a shared continuity jet:

```text
position
unit tangent
second derivative or curvature vector
surface-side material normal hint
```

Required joins:

```text
PS_h(0) == LE_h(0)
SS_h(0) == LE_h(1)
PS_h(1) == TE_h(0)
SS_h(1) == TE_h(1)
```

The adjacent segment curves must reuse the same join data, not independently approximate it. The generator may expose high-level handles in the frontend, but it must solve adjacent control points from the shared join jets so that C2 continuity is built into the curve family.

Surface validation must measure shared-edge quality after the 3D map:

```text
position gap <= 1e-6 mm
tangent angle <= 2 deg
normal angle <= 5 deg
curvature proxy mismatch <= 0.25
```

If the measurement fails, the graph must report a downgrade or failure. A preset label of `G2` is not sufficient.

## 7. Six Face Families

### 7.1 Pressure Surface

The pressure surface is a span loft through the five `PS_h` curves. All stations must have compatible parameterization, control counts, and knots. The pressure surface does not generate its own leading/trailing boundaries.

### 7.2 Suction Surface

The suction surface is a span loft through the five `SS_h` curves. It shares leading and trailing boundary curves with the edge surfaces through the loop join data. It must not be mirrored from the pressure side after the fact.

### 7.3 Leading Edge Surface

The leading edge surface is a span loft through the five `LE_h` cap curves. It is a rounded edge face, not a rectangular strip. Its pressure-side and suction-side boundary curves must be the same shared edges used by the pressure and suction surfaces.

### 7.4 Trailing Edge Surface

The trailing edge surface is a span loft through the five `TE_h` cap curves. It follows the same contract as the leading edge surface, with thinner but still curved cap geometry.

### 7.5 Root-To-Hub Attachment Surface

The root surface is an attachment ribbon from the hub support surface to the `h=0` blade loop. It is not the bottom face of a blade hexahedron.

Required construction data:

```text
inner boundary = h=0 blade loop boundary
outer boundary = projected hub footprint loop
width target = approximately 0.5 * average blade thickness
lift target = approximately 0.5 * average blade thickness
material side = signed side from blade-to-blade loop interior and hub normal
```

The root footprint must be projected onto the hub support domain. It must remain outside the blade material, monotone in the short direction, and foldover-free. Pressure-side and suction-side root ribbons may have different local curvature, but they must share the same loop-family boundary and material-side convention. A suction-side root falling under the blade is a root construction failure, not a display issue.

### 7.6 Tip Or Shroud Attachment Surface

For open impellers, the tip surface is a bounded dome or roof generated from the `h=1` loop. It must cover only the actual blade tip loop:

```text
tip area ratio <= 1.15 against h=1 loop area in mapped space
```

For closed impellers, the same boundary logic generates a shroud attachment ribbon from the `h=1` loop to the shroud support surface. Closed tip construction follows the root attachment pattern, with support-side projection on the outer shroud instead of the hub.

## 8. Default V1.1 Preset Policy

The default V1.1 presets are for review-grade geometry, not final compressor design optimization. They should make the construction visible and feasible.

Recommended first preset values:

```text
main_blade_count = 6
splitter_blade_count = 6
blade_count_total = 12
maximum_blade_thickness_mm = 40.0
average_blade_thickness_mm = 32.0 to 36.0
root_attachment_width_mm = 18.0 to 22.0
root_attachment_lift_mm = 18.0 to 22.0
open_tip_dome_height_mm = 12.0 to 18.0
blade_hub_angle_contract_deg = 60.0 to 120.0
```

The main blade should cover most of the valid hub streamwise domain while preserving inlet/outlet clearance:

```text
main_streamwise_start_s >= 0.06
main_streamwise_end_s <= 0.94
splitter_streamwise_start_s >= 0.35
splitter_streamwise_end_s <= 0.88
```

Preset generation must reject parameters that violate hub clearance, passage clearance, root width/lift feasibility, or blade-hub angle constraints. It must not silently clamp them into a primitive-looking fallback.

## 9. Frontend Contract

The V1.1 frontend must restore the blade loop as an explicit editable model, but the editor should show the correct domain:

```text
editor view = blade-to-blade (s, q) domain
not = local XY chord plane
```

Required editor features:

1. display five span stations, with hub/mid/tip quick filters
2. display main and splitter loops in the same passage domain
3. show pressure, suction, leading, and trailing segment colors separately
4. show control points and control polygons
5. show C2 join locks or failure markers
6. serialize edits only through `blade_to_blade_loop_family_overrides`
7. keep legacy `section_loop` controls hidden for active V1.1 presets

The compact parameter panel should keep only high-level dimensions and counts. It should not expose duplicate scalar controls for values owned by the loop-family editor.

Viewer rendering requirements:

```text
open normal mode: hide tip reference/support surface
shade: translucent per manufactured surface family
wireframe: drawn on every generated NURBS/sampled surface
root/tip/edge diagnostics: distinct shade and wire colors
```

## 10. Backend Resource Contract

V1.1 resources should be created as a new bundle rather than mutating V1.0.4 in place:

```text
resources/impeller/v1_1/...
```

The resource bundle must include:

```text
schema id
preset ids
constructor ids
capability matrix id
golden-case registry id
export contract id
default blade-to-blade loop family
default hub/tip profile controls
validation policy
mesh/render policy
```

The runtime compiler must route `geometry_version = "1.1"` to the V1.1 loop-family builder. V1.0.4 remains available for regression tests and historical inspection.

## 11. Validation Gates

V1.1 validation must fail early when the loop family is invalid. Required failure reasons:

```text
v1_1_loop_control_count_insufficient
v1_1_loop_not_closed
v1_1_loop_self_intersection
v1_1_loop_orientation_failed
v1_1_loop_join_c2_failed
v1_1_loop_station_knot_mismatch
v1_1_main_splitter_phase_failed
v1_1_main_splitter_passage_clearance_failed
v1_1_surface_boundary_not_shared
v1_1_surface_loft_foldover
v1_1_root_footprint_projection_failed
v1_1_root_material_side_failed
v1_1_root_width_height_out_of_contract
v1_1_root_continuity_failed
v1_1_tip_domain_exceeded
v1_1_tip_continuity_failed
v1_1_shroud_attachment_projection_failed
v1_1_blade_hub_angle_out_of_range
v1_1_frontend_payload_legacy_section_loop_conflict
```

Required reported metrics:

```text
loop_station_count
loop_segment_control_counts
max_loop_join_position_gap_mm
max_loop_join_tangent_angle_deg
max_loop_join_curvature_mismatch
surface_shared_edge_count
max_surface_shared_edge_gap_mm
max_surface_tangent_angle_deg
max_surface_normal_angle_deg
max_surface_curvature_mismatch
root_width_min_mm
root_width_max_mm
root_lift_min_mm
root_lift_max_mm
root_foldover_count
tip_area_ratio
blade_hub_angle_min_deg
blade_hub_angle_max_deg
main_splitter_min_clearance_mm
```

## 12. Mesh And Export Contract

Every generated face family must expose UV/grid lines and mesh triangles. The mesh generator must use the same face-family boundaries as the surface graph:

```text
mesh source = validated V1.1 face family graph
not = independent triangulation of visual primitives
```

The exported model must include named surface families:

```text
hub_support_surface
pressure_surface
suction_surface
leading_edge_surface
trailing_edge_surface
root_to_hub_attachment_surface
open_tip_dome_surface
closed_shroud_attachment_surface
mounting_bore_surface
```

For open presets, `closed_shroud_attachment_surface` is absent. For closed presets, `open_tip_dome_surface` is absent.

## 13. Test Requirements

Backend tests:

```text
tests/test_impeller_v11_resources.py
tests/test_impeller_v11_blade_to_blade_loop_domain.py
tests/test_impeller_v11_loop_c2_continuity.py
tests/test_impeller_v11_six_face_surface_family.py
tests/test_impeller_v11_root_attachment_surface.py
tests/test_impeller_v11_tip_or_shroud_surface.py
tests/test_impeller_v11_main_splitter_domain.py
tests/test_impeller_v11_mesh_and_export_contract.py
```

Frontend tests:

```text
frontend loop editor renders V1.1 blade-to-blade domain before generation
frontend shows five stations and main/splitter loops
frontend serializes only blade_to_blade_loop_family_overrides
frontend hides legacy section-loop controls for V1.1 presets
frontend hides open tip reference face in normal mode
frontend applies shade and wireframe to every generated face family
```

Regression tests:

```text
V1.0.4 geometry contract tests still pass
V1.0.3 historical fixture still works
V0.97 resources remain routeable if requested directly
```

## 14. Acceptance Criteria

V1.1 is acceptable when:

1. `radial_open_reference_v1_1` and `radial_closed_reference_v1_1` synthesize through the runtime service.
2. generated manifests report `geometry_version = "1.1"` and `geometry_patch_version = "1.1.0"`.
3. five loop stations are visible in the frontend blade-to-blade editor.
4. pressure, suction, leading, trailing, root, and tip/shroud faces are all generated from shared loop-family boundaries.
5. edge and root surfaces no longer appear as staple-shaped primitive patches.
6. open tip surfaces do not exceed the actual blade tip loop domain.
7. root width and lift are near half average blade thickness and do not flip under the blade.
8. blade-hub angle measurements stay within 60 to 120 degrees.
9. hub geometry uses the concave R-Z profile instead of a cone fallback.
10. every manufactured surface has visible wireframe lines and an exportable mesh.

## 15. Non-Goals

V1.1 does not require exact analytic OCCT fillets. The first implementation remains sampled review-grade geometry, but the sampling must come from the V1.1 loop-family surface graph rather than post-hoc visual primitives.

V1.1 does not require more than five span stations by default. More stations may be added later for expert inspection after the five-loop contract is proven stable.

V1.1 does not solve final aerodynamic optimization. It establishes a robust geometric construction rule that can later receive optimized blade laws.
