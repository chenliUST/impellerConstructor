# Impeller V1.1.2 Canonical NURBS Parameterization Spec

Date: 2026-07-10

Status: Draft spec for implementation planning. This document defines the V1.1.2 semantic target; it is not an implementation log.

## 1. Intent

V1.1.2 is a semantic consolidation patch on top of the V1.1 blade-to-blade loop surface-family constructor.

The core V1.1 idea remains valid:

```text
blade-to-blade S-Q-H domain
  -> shared section-loop family
  -> pressure, suction, leading, trailing, root, and tip/shroud face families
  -> sampled surface graph, UV grids, mesh, and B-Rep review export
```

V1.1.2 does not start over. It adds a canonical NURBS parameterization layer in front of the current V1.1 builders so that input semantics are explicit, deterministic, direct to edit, and separable from preset tuning values.

The immediate goal is to translate the current V1.1.1 presets into this canonical layer, generate the same family of geometry, and discover whether the refined mathematics exposes bugs before larger feature work continues.

## 2. Problems To Fix

V1.1.1 made the model visibly reviewable, but the input language still mixes three concerns:

1. universal construction rules;
2. UI handles that produce plausible shapes;
3. one-off preset seed values used to make a model look useful for visual debugging.

That mixing creates real risks:

- `span_stations_h = [0, 0.25, 0.5, 0.75, 1]` can be misread as "the active blade begins exactly at the hub surface", even though root lift and manufacturable root clearance imply a blade-side root offset.
- scalar fields such as `main_flow_turn_q_mm`, `midspan_bow_q_mm`, and `spanwise_flow_turn_delta_q_mm` are deterministic, but they are not the most direct way to control blade shape.
- leading and trailing edges should not be universal semicircle primitives. They should be NURBS cap curves with rounded-cap intent and measured continuity into pressure and suction side curves.
- V1.1 conversation-derived preset values should not silently become the universal impeller construction law.

V1.1.2 separates these concerns.

## 3. Version Contract

V1.1.2 remains a V1.1 geometry family with a patch-level semantic change:

```text
geometry_version = "1.1"
geometry_patch_version = "1.1.2"
transition_geometry_status = "topology_first_blade_to_blade_5_loop_surface_family_graph"
source_kernel = "v1_1_blade_to_blade_surface_family_kernel"
math_parameterization = "v1_1_2_canonical_nurbs_parameterization"
mesh_strategy = "v1_1_1_all_surface_uv_grid_mesh"
```

The following preset ids remain active and are translated into canonical V1.1.2 input:

```text
radial_open_reference_v1_1
radial_closed_reference_v1_1
nasa_stage37_stator_ring_v1_1
rr_ultrafan_cti_fan_v1_1
public_rocket_turbopump_inducer_v1_1
```

The ids stay stable to avoid frontend and evidence churn. The manifest must make the patch change visible through `geometry_patch_version = "1.1.2"` and `math_parameterization`.

## 4. Canonical Parameterization Payload

The V1.1.2 constructor consumes a canonical payload named:

```text
canonical_nurbs_parameterization
```

The payload has seven top-level sections:

```text
support_profiles
active_span_policy
blade_population
blade_skeleton_field
thickness_field
section_loop_family
attachment_policy
pose_field
sampling_policy
```

Each section is explicit about what it owns. UI handles and legacy preset values may compile into this payload, but the surface builders consume the canonical payload.

## 5. Support Profiles

Support profiles define the meridional carrier. They are NURBS curves in R-Z coordinates:

```json
{
  "support_profiles": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "coordinate_system": "rz_meridional_mm",
      "degree": 3,
      "control_points": [[150, 400], [170, 250], [220, 150], [330, 50], [480, 10], [580, 0]],
      "weights": [1, 1, 1, 1, 1, 1],
      "knots": [0, 0, 0, 0, 0.333333, 0.666667, 1, 1, 1, 1]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "coordinate_system": "rz_meridional_mm",
      "degree": 3,
      "control_points": [[300, 407], [320, 305], [350, 218], [400, 130], [490, 70], [581, 34]],
      "weights": [1, 1, 1, 1, 1, 1],
      "knots": [0, 0, 0, 0, 0.333333, 0.666667, 1, 1, 1, 1]
    }
  }
}
```

Open impellers treat `tip_or_shroud_profile` as a reference support curve, not a manufactured visible face in normal CAD review. Closed impellers treat it as the inner shroud support profile.

## 6. Active Span Policy

The active blade span is not identical to the full hub-to-tip support span.

V1.1.2 defines a resolved active span domain:

```text
H(s) = hub support point
T(s) = tip or shroud support point
root_offset(s) = blade-side lift away from hub support
tip_offset(s) = blade-side inset away from tip/shroud support
usable_span(s) = distance(H(s), T(s)) - root_offset(s) - tip_offset(s)
active_point(s, h) = H(s) + [root_offset(s) + h * usable_span(s)] * span_unit(s)
```

The default policy is thickness driven:

```json
{
  "active_span_policy": {
    "root_offset": {
      "mode": "thickness_ratio",
      "ratio_of_local_thickness": 1.0,
      "minimum_mm": 0.0,
      "process_allowance_mm": 0.0
    },
    "tip_offset": {
      "mode": "closed_shroud_thickness_ratio_or_open_zero",
      "ratio_of_local_thickness": 1.0,
      "open_impeller_offset_mm": 0.0
    },
    "report_resolved_offsets": true
  }
}
```

Tooling-aware input is allowed through the same policy:

```json
{
  "root_offset": {
    "mode": "tool_radius",
    "tool_radius_mm": 12.0,
    "process_allowance_mm": 2.0
  }
}
```

The builder must not silently clamp offsets. It reports:

```text
requested_root_offset_mm
resolved_root_offset_min_mm
resolved_root_offset_max_mm
requested_tip_offset_mm
resolved_tip_offset_min_mm
resolved_tip_offset_max_mm
offset_feasibility_status
```

## 7. Blade Population

Blade population is topology, not a loose scalar:

```json
{
  "blade_population": {
    "main_blade_count": 8,
    "splitter_blade_count": 8,
    "splitter_positioning_mode": "main_passage_bisector",
    "splitter_passage_fraction": 0.5,
    "main_streamwise_interval_s": [0.06, 0.94],
    "splitter_streamwise_interval_s": [0.35, 0.88],
    "splitter_phase_offset_pitch": 0.5
  }
}
```

Compatibility rule:

```text
blade_count = main_blade_count + splitter_blade_count
```

Closed reference presets may set `splitter_blade_count = 0`. This is valid and must not create hidden splitters.

## 8. Blade Skeleton Field

The blade skeleton is the center field in the unwrapped blade-to-blade domain. It is a NURBS surface:

```json
{
  "blade_skeleton_field": {
    "kind": "nurbs_surface",
    "coordinate_system": "s_h_q_mm",
    "degree_s": 3,
    "degree_h": 3,
    "control_points": [
      [[0.06, 0.00, 0.0], [0.30, 0.00, 72.0], [0.60, 0.00, 190.0], [0.94, 0.00, 320.0]],
      [[0.06, 0.50, 16.0], [0.30, 0.50, 92.0], [0.60, 0.50, 218.0], [0.94, 0.50, 338.0]],
      [[0.06, 1.00, 30.0], [0.30, 1.00, 118.0], [0.60, 1.00, 250.0], [0.94, 1.00, 396.0]]
    ],
    "weights": "all_ones",
    "knots_s": "clamped_uniform",
    "knots_h": "clamped_uniform"
  }
}
```

This field replaces universal dependence on `main_flow_turn_q_mm`, `spanwise_flow_turn_delta_q_mm`, and `midspan_bow_q_mm`.

Those old fields may remain as frontend handles or preset seeds, but they compile into `blade_skeleton_field`.

## 9. Thickness Field

Thickness is a NURBS scalar field:

```json
{
  "thickness_field": {
    "kind": "nurbs_surface",
    "coordinate_system": "s_h_thickness_mm",
    "degree_s": 3,
    "degree_h": 2,
    "control_points": [
      [[0.06, 0.0, 10.0], [0.25, 0.0, 16.0], [0.65, 0.0, 15.0], [0.94, 0.0, 8.0]],
      [[0.06, 0.5, 9.0], [0.25, 0.5, 14.0], [0.65, 0.5, 13.0], [0.94, 0.5, 7.0]],
      [[0.06, 1.0, 8.0], [0.25, 1.0, 12.0], [0.65, 1.0, 11.0], [0.94, 1.0, 6.0]]
    ],
    "minimum_thickness_mm": 1.0
  }
}
```

The sampled local half thickness defines the nominal offset from skeleton to pressure and suction sides in S-Q space.

## 10. Section Loop Family

The section loop family is the canonical source of blade side and cap curves.

Two input modes are supported. Both compile to the same canonical NURBS segment curves.

### 10.1 Skeleton, Thickness, And Cap Intent

This is the default preset and frontend mode:

```json
{
  "section_loop_family": {
    "mode": "skeleton_thickness_caps",
    "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
    "segments": {
      "pressure_side": {"construction": "skeleton_minus_half_thickness"},
      "suction_side": {"construction": "skeleton_plus_half_thickness"},
      "leading_edge_cap": {
        "kind": "nurbs_cap_curve",
        "sagitta_policy": {"mode": "local_thickness_ratio", "ratio": 0.5},
        "continuity_goal": "C2"
      },
      "trailing_edge_cap": {
        "kind": "nurbs_cap_curve",
        "sagitta_policy": {"mode": "local_thickness_ratio", "ratio": 0.5},
        "continuity_goal": "C2"
      }
    }
  }
}
```

Leading and trailing edge caps are not semicircle primitives. They are NURBS curves with rounded-cap intent. The sagitta ratio is a target, not a command to force a circle when continuity would fail.

### 10.2 Direct Segment Curves

Expert mode provides direct NURBS curves for each segment at each span station:

```json
{
  "section_loop_family": {
    "mode": "direct_segment_curves",
    "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
    "loop_stations": [
      {
        "h": 0.0,
        "segments": {
          "pressure_side": {"kind": "nurbs_curve", "coordinate_system": "s_q_mm"},
          "leading_edge_cap": {"kind": "nurbs_curve", "coordinate_system": "s_q_mm"},
          "suction_side": {"kind": "nurbs_curve", "coordinate_system": "s_q_mm"},
          "trailing_edge_cap": {"kind": "nurbs_curve", "coordinate_system": "s_q_mm"}
        }
      }
    ]
  }
}
```

Direct mode must still enforce shared endpoints and measured C2/G2 join metrics. The builder does not accept visually close but topologically separate endpoints.

## 11. Pose Field

V1.1.2 treats pose as a deterministic field, not as several overlapping scalar effects.

The canonical pose field is:

```json
{
  "pose_field": {
    "kind": "nurbs_surface",
    "coordinate_system": "s_h_theta_offset_deg",
    "control_points": [
      [[0.0, 0.0, 0.0], [0.5, 0.0, -90.0], [1.0, 0.0, -216.0]],
      [[0.0, 1.0, 12.0], [0.5, 1.0, -70.0], [1.0, 1.0, -180.0]]
    ]
  }
}
```

Legacy UI handles compile into this field:

```text
blade_wrap_deg
blade_lean_deg
leading_edge_lean_deg
trailing_edge_lean_deg
leading_edge_sweep_mm
trailing_edge_sweep_mm
```

They remain deterministic: the same input payload must produce byte-stable canonical fields after rounding. The manifest must record both original handles and resolved fields so users can understand what was actually constructed.

## 12. Attachment Policy

Root and closed-shroud attachments use the same boundary idea:

```json
{
  "attachment_policy": {
    "root_to_hub": {
      "kind": "nurbs_ribbon",
      "support_boundary": "hub_profile",
      "blade_boundary": "active_span_h0_section_loop",
      "width_policy": {"mode": "thickness_ratio", "ratio": 1.0},
      "lift_policy": {"mode": "active_span_policy_root_offset"},
      "continuity_goal": "G2_measured"
    },
    "tip_to_shroud": {
      "kind": "nurbs_ribbon",
      "enabled_when": "closed",
      "support_boundary": "tip_or_shroud_profile",
      "blade_boundary": "active_span_h1_section_loop",
      "width_policy": {"mode": "thickness_ratio", "ratio": 1.0},
      "lift_policy": {"mode": "active_span_policy_tip_offset"},
      "continuity_goal": "G2_measured"
    },
    "open_tip": {
      "kind": "nurbs_cover_surface",
      "enabled_when": "open",
      "boundary": "active_span_h1_section_loop",
      "continuity_goal": "G2_measured"
    }
  }
}
```

This preserves V1.1 root/tip semantics while removing the ambiguity that root starts at the raw hub support.

## 13. Surface Generation

The canonical payload compiles into a resolved loop family:

```text
resolved_loop_family:
  blade_class
  blade_index
  h station
  pressure_side NURBS samples
  suction_side NURBS samples
  leading_edge_cap NURBS samples
  trailing_edge_cap NURBS samples
  join metrics
```

The current V1.1 surface graph builder continues to generate:

```text
pressure_surface
suction_surface
leading_edge_surface
trailing_edge_surface
root_attachment_surface
open_tip_dome_surface or closed_shroud_attachment_surface
hub_support and material surfaces
closed shroud support and material surfaces
mounting bore surfaces
```

The implementation may keep sampled `uv_grid` output in V1.1.2. Exact analytic OCCT NURBS faces remain out of scope for this patch, but every sampled grid must carry its canonical NURBS source metadata.

## 14. Frontend Multi-View Parameter Annotation Tab

V1.1.2 adds a frontend tab for annotated model inspection.

Tab name:

```text
Parameter views
```

Purpose:

- show the actual generated model in multiple synchronized engineering views;
- overlay the resolved canonical parameters on the model, not on a separate abstract diagram only;
- make the distinction between preset seed, UI handle, and resolved canonical parameter visible.

Required views:

```text
top view / plan view
meridional section view
blade-to-blade S-Q view
span station view
```

Required annotations:

```text
hub_profile control points and sampled curve
tip_or_shroud_profile control points and sampled curve
active root offset and active tip offset
main and splitter streamwise intervals
main/splitter blade counts and splitter passage fraction
blade skeleton field samples
thickness field samples
leading/trailing cap sagitta targets and resolved values
root and tip/shroud attachment width/lift
pose field or resolved wrap/stacking lines
```

The tab must consume manifest-resolved canonical data after generation. Before generation, it may show preset canonical defaults with a clear "preset defaults" state.

The tab must not mutate geometry by itself. Edits remain owned by the existing parameter inputs and curve/control editors.

## 15. Frontend Parameter Ownership

V1.1.2 frontend inputs are divided into three categories:

```text
universal canonical inputs
preset-owned seeds
derived UI handles
```

Universal canonical inputs are the target payload fields.

Preset-owned seeds define a representative model and should not appear as casual scalar controls if changing them alters topology or feasibility.

Derived UI handles remain useful, but must be labeled and serialized through a translator:

```text
handle -> canonical_nurbs_parameterization -> surface graph
```

The manifest must expose:

```text
canonical_input_source = "direct" | "translated_from_legacy_v1_1" | "translated_from_frontend_handles"
```

## 16. Validation Gates

Required V1.1.2 failure reasons:

```text
v1_1_2_canonical_payload_missing
v1_1_2_support_profile_invalid_nurbs
v1_1_2_active_span_offset_infeasible
v1_1_2_blade_population_count_mismatch
v1_1_2_skeleton_field_invalid_nurbs
v1_1_2_thickness_field_invalid_nurbs
v1_1_2_section_loop_mode_unknown
v1_1_2_section_loop_not_closed
v1_1_2_section_loop_join_c2_failed
v1_1_2_cap_sagitta_unresolved
v1_1_2_pose_field_invalid_nurbs
v1_1_2_attachment_policy_infeasible
v1_1_2_legacy_handle_conflicts_with_direct_canonical_input
v1_1_2_frontend_annotation_manifest_missing
```

Required reported metrics:

```text
canonical_payload_version
canonical_input_source
support_profile_control_count
active_root_offset_min_mm
active_root_offset_max_mm
active_tip_offset_min_mm
active_tip_offset_max_mm
skeleton_field_control_net_shape
thickness_min_mm
thickness_max_mm
loop_station_count
max_join_position_gap_mm
max_join_tangent_angle_deg
max_join_curvature_proxy_mismatch
leading_cap_sagitta_target_min_mm
leading_cap_sagitta_resolved_min_mm
trailing_cap_sagitta_target_min_mm
trailing_cap_sagitta_resolved_min_mm
attachment_width_min_mm
attachment_lift_min_mm
```

## 17. Preset Translation

All five V1.1.1 active presets must translate to canonical V1.1.2 payloads.

Translation rules:

- `hub_profile_rz_mm` and `tip_or_shroud_profile_rz_mm` become `support_profiles`.
- `main_blade_count`, `splitter_blade_count`, passage intervals, and splitter fields become `blade_population`.
- `main_flow_turn_q_mm`, `splitter_flow_turn_q_mm`, `spanwise_flow_turn_delta_q_mm`, and `midspan_bow_q_mm` become `blade_skeleton_field`.
- `average_blade_thickness_mm`, `maximum_blade_thickness_mm`, and `blade_thickness_mm` become `thickness_field`.
- `leading_edge_cap_roundness` and `trailing_edge_cap_roundness` become cap intent modifiers, not circle commands.
- `root_attachment_width_mm`, `root_attachment_lift_mm`, `root_blade_lift_mm`, and `shroud_blade_inset_mm` become `active_span_policy` and `attachment_policy`.
- `blade_wrap_deg`, `blade_lean_deg`, edge lean, and sweep values become `pose_field`.

The translator must report the exact source of every resolved canonical section.

## 18. Tests

Backend tests:

```text
tests/test_impeller_v11_2_canonical_parameterization.py
tests/test_impeller_v11_2_preset_translation.py
tests/test_impeller_v11_2_active_span_policy.py
tests/test_impeller_v11_2_nurbs_loop_caps.py
tests/test_impeller_v11_2_surface_graph_compatibility.py
```

Frontend tests:

```text
frontend V1.1.2 parameter views tab renders before generation from preset canonical defaults
frontend V1.1.2 parameter views tab renders resolved manifest annotations after generation
frontend V1.1.2 annotation view does not mutate geometry payload
frontend distinguishes preset seeds, UI handles, and resolved canonical parameters
```

Regression tests:

```text
V1.1.1 active presets still synthesize by existing ids
V1.1 surface graph role names remain compatible with viewer and exports
V1.0.4 historical tests still pass
```

## 19. Acceptance Criteria

V1.1.2 is acceptable when:

1. all five active V1.1 preset ids instantiate through canonical V1.1.2 translation;
2. manifests report `geometry_patch_version = "1.1.2"`;
3. manifests include `canonical_nurbs_parameterization` and resolved metrics;
4. pressure, suction, leading, trailing, root, and tip/shroud faces are still generated with the existing V1.1 face-family roles;
5. leading and trailing caps are NURBS cap curves with measured C2/G2 join metrics, not hard-coded semicircle primitives;
6. active span offsets are derived from policy and reported, not implied by raw `span_stations_h`;
7. the frontend exposes a `Parameter views` tab with annotated generated-model views;
8. the implementation does not delete historical V1.1 semantics, specs, or evidence;
9. tests prove old preset fields translate to canonical fields deterministically.

## 20. Non-Goals

V1.1.2 does not require exact analytic OCCT NURBS solids. It still emits sampled review-grade surface graphs, meshes, and bounded B-Rep review exports.

V1.1.2 does not remove legacy V1.1 parameters from compatibility paths. It classifies them and routes them through a translator.

V1.1.2 does not redesign the entire frontend curve editor. It adds a multi-view annotation tab and enough data plumbing to inspect resolved canonical parameters.

## 21. Self-Review

- No placeholder sections remain.
- The spec preserves V1.1 S-Q-H semantics while making the input language canonical and NURBS-based.
- The frontend multi-view annotation requirement is scoped as inspection, not as a new editing system.
- The spec explicitly separates universal construction rules, preset seeds, and UI handles.
- The acceptance criteria are testable without claiming production CAD or analytic fillets.
