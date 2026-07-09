# Impeller V1.1 Milestone Summary

Date: 2026-07-08
Worktree: `impeller-v1.0-topology-first`

## Milestone Statement

V1.1 is the first impeller line in this project where the blade is generated from a blade-to-blade loop surface-family rather than from local chord primitives or post-generated transition patches. The current milestone is review-grade sampled geometry, not certified sewn industrial CAD, but it now has coherent construction logic, explicit DSL resources, measurable geometry contracts, and reproducible evidence.

Current live preset path:

```text
radial_open_reference_v1_1
radial_closed_reference_v1_1
radial_open_high_twist_thin_reference_v1_1
```

Current runtime signature:

```text
geometry_version = 1.1
geometry_patch_version = 1.1.0
transition_geometry_status = topology_first_blade_to_blade_5_loop_surface_family_graph
mesh_strategy = v1_1_loop_family_shared_boundary_uv_mesh
kernel_capability_matrix_id = impeller_v1_1_kernel_capabilities
golden_case_registry_id = impeller_v1_1_golden_cases
```

## Construction Logic

The V1.1 constructor uses a shared blade-to-blade domain:

```text
D_h = (s, q, h)
s = normalized meridional streamwise coordinate
q = circumferential arc-length offset in mm, q = r * delta_theta
h = blade span station from hub-side blade loop to tip/shroud-side blade loop
```

The construction chain is:

```text
hub_profile_rz_mm + tip_or_shroud_profile_rz_mm
  -> domain mapper (s, q, h, phase_offset_pitch) -> xyz
  -> five blade-to-blade loops at h = 0, 0.25, 0.5, 0.75, 1
  -> named loop segments: pressure, leading, suction, trailing
  -> six surface families:
       pressure surface
       suction surface
       leading-edge surface
       trailing-edge surface
       root-to-hub attachment
       open tip dome or closed shroud attachment
  -> support and material faces:
       hub support revolve
       hub top annulus
       hub bottom annulus
       hub outer wall
       mounting bore wall
```

Main and splitter blades share the same domain and mapper. Splitter blades are not an independently reset local blade profile. They use:

```text
splitter_positioning_mode = main_passage_bisector
splitter_passage_fraction = 0.5
```

This means each splitter centerline is computed from the adjacent main-blade passage at the same `s,h`, so it bisects the passage between two neighboring main blades.

Leading and trailing edge caps now have a physical thin-blade contract:

```text
cap domain = s_mm-q_mm
local edge sagitta = 0.5 * local_thickness_mm
cap shape = half-thickness semicircular cap
continuity = measured C2/G2 boundary jets
```

The root and closed-shroud attachments use support-ribbon semantics:

```text
root_blade_lift_mm = explicit preset/override value
root surface = ribbon from hub footprint loop to lifted blade root loop
closed shroud surface = ribbon from blade tip loop to shroud reference loop
open tip surface = dome/cap bounded by actual h=1 blade loop
```

## DSL Resources

Primary V1.1 DSL root:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1
```

Key resources:

```text
schema.json
aliases.json
constructors/open_impeller.json
constructors/closed_impeller.json
presets/radial_open_reference.json
presets/radial_closed_reference.json
presets/radial_open_high_twist_thin_reference.json
shape_controls/default_shape_controls.json
export_contracts/blade_to_blade_loop_surface_family_graph.json
capability_matrices/impeller_v1_1_kernel_capabilities.json
golden_cases/impeller_v1_1_golden_cases.json
simulation_views/cfd_full_360.json
simulation_views/fea_solid_schema.json
```

Important preset defaults now carried in V1.1 resources:

```text
main_blade_count = 6
splitter_blade_count = 6
main_streamwise_interval_s = [0.06, 0.94]
splitter_streamwise_interval_s = [0.35, 0.88]
splitter_phase_offset_pitch = 0.5
splitter_positioning_mode = main_passage_bisector
splitter_passage_fraction = 0.5
average_blade_thickness_mm = 16.0
root_blade_lift_mm = 16.0 for open thin presets
shroud_blade_inset_mm = 16.0 for closed preset
```

## Ontology Slice

V1.1 currently encodes its ontology slice through DSL resources rather than through a separate `src/part_rule_synthesis/ontology/impeller/v1_1` directory.

The active ontology slice is composed of:

```text
schema.json:
  slice_id = axisymmetric_throughflow_radial_bladed_impeller_v1_1
  constructor_family = AxisymmetricThroughflowRadialBladedImpeller

constructors/open_impeller.json and constructors/closed_impeller.json:
  classification
  coordinate_system
  support_surfaces
  material_domain
  blade_surface_model
  surface_graph_contract
  feature_graph_contract
  display_policy
  validation

export_contracts/blade_to_blade_loop_surface_family_graph.json:
  graph mode
  supported geometry status
  mesh strategy

capability_matrices/impeller_v1_1_kernel_capabilities.json:
  supported, partial, research_grade, unsupported capability claims
```

The semantic boundary is:

```text
V1.1 can claim:
  review-grade blade-to-blade loop-family graph
  main/splitter blade passage semantics
  shared-boundary UV sampled surfaces
  explicit support/material surface ids
  measurable C2/G2 loop continuity
  bounded root/tip/shroud attachment semantics

V1.1 cannot yet claim:
  exact sewn OCCT solid
  industrial variable-radius analytic fillets
  certified manufacturing CAD
  solver-ready CFD volume mesh
  automatic expert-rule patching from feedback
```

## Backend Implementation Map

Primary V1.1 modules:

```text
src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py
src/part_rule_synthesis/impeller_v11_surface_family.py
src/part_rule_synthesis/impeller_v11_loop_validation.py
src/part_rule_synthesis/impeller_v11_validation.py
src/part_rule_synthesis/impeller_v11_constants.py
```

Integration modules:

```text
src/part_rule_synthesis/impeller_runtime_compiler.py
src/part_rule_synthesis/service.py
src/part_rule_synthesis/api.py
src/part_rule_synthesis/impeller_geometry_validation.py
```

Frontend integration:

```text
frontend/src/appModel.js
frontend/src/components/CurveControlPanel.js
frontend/src/components/ProfileCurveEditor.js
frontend/src/components/ModelViewer.js
```

## Validation And Evidence

Latest backend verification:

```text
$files = Get-ChildItem -Path tests -Filter 'test_impeller_v11_*.py' | ForEach-Object { $_.FullName }
python -m pytest $files -q
64 passed in 144.20s
```

Latest HTTP smoke:

```text
base = http://127.0.0.1:8061
preset = radial_open_reference_v1_1
geometry_version = 1.1
geometry_validation_status = PASS
splitter_positioning_status = PASS
splitter_passage_fraction_min = 0.499894967
splitter_passage_fraction_max = 0.50008856
splitter_passage_fraction_avg = 0.500026951
```

Recent detailed evidence:

```text
docs/evidence/2026-07-08-impeller-v1-1-preset-hub-solid-display-evidence.md
```

This evidence file records:

```text
V1.1 preset/hub/display correction
root blade lift correction
closed shroud attachment correction
first open preset high-twist shape correction
thin-blade leading/trailing edge spike correction
splitter passage-bisector position correction
```

Semantic and insight logs:

```text
docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md
docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md
```

## Current Services

Current local service state after the latest V1.1 correction:

```text
backend = http://127.0.0.1:8061
backend PID = 23220
frontend = http://127.0.0.1:5199
```

## Next Risks

The current milestone is stable enough for visual inspection, but the next changes should avoid silent semantic drift:

1. Do not reintroduce local chord-loop construction into V1.1 blade faces.
2. Do not treat splitter blades as independent local camber curves.
3. Do not relax half-thickness edge-cap sagitta to hide surface spikes.
4. Do not expose frontend controls unless they serialize to the actual loop-family or profile payload owner.
5. Keep V1.1 exactness labels research-grade until sewn B-Rep and downstream meshing evidence exist.
