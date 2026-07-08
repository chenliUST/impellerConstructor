# Impeller V1.1.1 Viewer, Preset, And Parameter Overhaul Spec

Date: 2026-07-08

Status: Draft spec for implementation planning. This document defines the V1.1.1 semantic target; it is not an implementation log.

## 1. Intent

V1.1.1 is a patch-level overhaul on top of the accepted V1.1 blade-to-blade loop surface-family constructor. It does not change the core construction domain: blade loops are still defined in the unwrapped blade-to-blade `s-q` domain, mapped through the meridional hub/tip carrier, and lofted into the six face families.

The patch fixes three software-engineering problems that now block visual review:

1. Viewer modes do not mean what their labels say. `wireframe` currently shows construction and boundary curves for only part of the model, while `shaded` may still show line overlays.
2. `CFD360 mesh` is filtered through CFD patch metadata, so only a subset of faces is visible even though the V1.1 surface graph contains `uv_grid` and mesh data for every sampled surface.
3. The active preset catalog still mixes V1.1 topology-first examples with older V0.9 public examples whose parameters and semantics no longer match the current constructor.

V1.1.1 therefore standardizes display semantics, assigns explicit surface metadata for all generated faces, reduces the active preset catalog to representative models, and makes the frontend parameter panel follow constructor-owned editable parameters instead of legacy hard-coded fields.

## 2. Version Contract

V1.1.1 remains a V1.1 geometry version with a patch bump:

```text
geometry_version = "1.1"
geometry_patch_version = "1.1.1"
transition_geometry_status = "topology_first_blade_to_blade_5_loop_surface_family_graph"
source_kernel = "v1_1_blade_to_blade_surface_family_kernel"
mesh_strategy = "v1_1_1_all_surface_uv_grid_mesh"
viewer_surface_display_contract = "v1_1_1_all_surface_uv_and_shaded_isolation"
kernel_capability_matrix_id = "impeller_v1_1_kernel_capabilities"
golden_case_registry_id = "impeller_v1_1_golden_cases"
```

Canonical V1.1 preset ids may remain stable, but their runtime and frontend labels must report `geometry_patch_version = "1.1.1"` so the UI cannot appear to be running the older V1.1.0 patch.

Required active V1.1.1 presets:

```text
radial_open_reference_v1_1
radial_closed_reference_v1_1
nasa_stage37_stator_ring_v1_1
rr_ultrafan_cti_fan_v1_1
public_rocket_turbopump_inducer_v1_1
```

The old high-twist thin test preset and older public/analogy frontend examples are removed from the active catalog for this version. Historical evidence and older version resources are not deleted, because they are part of the development record.

## 3. Viewer Mode Semantics

### 3.1 CAD Review Surface Visibility

The normal CAD review viewer consumes `manifest.geometry.surface_graph.surfaces`.

Reference-only construction surfaces, such as the open impeller tip reference surface, remain hidden outside feature debug. Manufactured or review-relevant surfaces remain visible unless their display metadata explicitly says otherwise.

### 3.2 Shaded

`shaded` means surfaces only.

Required behavior:

- render visible surface meshes with their `display.color` and `display.opacity`;
- do not render `uv_grid` isolines;
- do not render construction lines;
- do not render named boundary curves;
- do not render triangle-edge mesh overlays.

This mode is for checking face color, material grouping, and gross surface continuity without line clutter.

### 3.3 Wireframe

`wireframe` means all visible surface UV isolines.

Required behavior:

- render no shaded faces;
- render `u` and `v` isolines for every visible surface that has a rectangular `uv_grid`;
- do not rely on `construction_lines`;
- do not show only selected blade boundary curves;
- use each surface's `display.wire_color` or `wireframe.color`;
- include hub, hub solid caps/walls, mounting bore review faces, blade pressure/suction faces, leading/trailing edge faces, root attachment faces, tip dome faces, and closed shroud faces when they are visible surfaces.

Named boundary curves may be shown only in `feature_debug` or when a CFD patch selection explicitly requests boundary inspection.

### 3.4 Combined

`combined` means shaded faces plus all visible surface UV isolines.

Required behavior:

- render the same visible shaded surfaces as `shaded`;
- render the same UV isolines as `wireframe`;
- keep construction lines hidden by default;
- allow feature debug to add construction and control overlays without changing normal combined mode.

### 3.5 CFD360 Mesh

`CFD360 mesh` is a mesh visualization mode, not a CFD patch filter.

Required behavior:

- render mesh edges for every visible manufactured/review surface with a valid `uv_grid`;
- include the full sampled blade face family, hub material review faces, mounting bore review faces, and closed shroud faces;
- exclude only explicit `reference_only` construction support surfaces unless feature debug is active;
- keep CFD patch groups available for solver-oriented metadata, but do not use patch group membership as the viewer's surface visibility filter.

The current failure mode, where only edge/transition regions appear, is forbidden for V1.1.1.

## 4. Backend Surface Metadata Contract

Every V1.1.1 generated surface must carry enough metadata for CAD review, wireframe, CFD mesh visualization, and tests to agree on what the surface is.

Required fields for manufactured/review surfaces:

```text
id
kind
face_family
role
source_kernel
uv_grid
control_net
wireframe.enabled
wireframe.color
mesh
display.color
display.wire_color
display.opacity
display.visible_by_default
feature_id
cfd_role
viewer_surface_role
```

Reference-only surfaces may omit CFD-facing roles, but must declare:

```text
surface_flags.reference_only = true
display.reference_only = true
display.visible_by_default = false
```

### 4.1 CFD Roles

V1.1.1 assigns CFD/review roles from the constructor's six face families:

```text
pressure surface           -> cfd_role = "blade_pressure"
suction surface            -> cfd_role = "blade_suction"
leading edge surface       -> cfd_role = "leading_edge_transition"
trailing edge surface      -> cfd_role = "trailing_edge_transition"
root attachment surface    -> cfd_role = "root_transition"
open tip dome              -> cfd_role = "tip_transition"
closed shroud attachment   -> cfd_role = "tip_transition"
hub support/material faces -> cfd_role = "hub_wall"
closed shroud surfaces     -> cfd_role = "tip_or_shroud_wall"
```

Mounting bore and other internal assembly review faces may keep an internal assembly role for CFD export suppression, but the mesh viewer must still be able to display their UV/mesh overlays in CAD review and mesh inspection.

### 4.2 Mesh Manifest

The surface mesh manifest must expose all-surface regions, not only transition regions.

Required manifest content:

```text
mesh_strategy = "v1_1_1_all_surface_uv_grid_mesh"
triangle_regions[] with surface_graph_id for every included visible surface
included_surface_ids[] for every included visible surface
excluded_surface_ids[] only for reference-only or invalid-grid surfaces
transition_regions[] retained as a subset for transition inspection
```

Frontend mesh display uses `triangle_regions` or direct surface `uv_grid` triangulation for visibility. It must not depend on `transition_regions` as the full surface list.

## 5. Active Preset Catalog

V1.1.1 keeps only representative presets in the active frontend and V1.1 DSL preset catalog.

### 5.1 Open Radial Reference

Preset id:

```text
radial_open_reference_v1_1
```

Required changes:

- open impeller;
- 8 main blades and 8 splitter blades;
- splitters use `splitter_positioning_mode = "main_passage_bisector"`;
- `blade_count = main_blade_count + splitter_blade_count = 16`;
- splitter blades approximately bisect each passage between adjacent main blades;
- keep the accepted high-height open-tip meridional profile family:

```text
tip_or_shroud_profile_rz_mm:
  (300, 407), (320, 305), (350, 218), (400, 130), (490, 70), (581, 34)
```

- keep thin enough blade defaults for visual review, with representative maximum thickness near 20 mm unless the preset explicitly documents a larger inspection value;
- open tip reference support remains hidden in normal viewer modes.

### 5.2 Closed Radial Reference

Preset id:

```text
radial_closed_reference_v1_1
```

Required changes:

- closed impeller;
- 12 blades total;
- no splitter blades;
- `main_blade_count = 12`;
- `splitter_blade_count = 0`;
- `blade_count = 12`;
- hub and shroud profiles are flatter than the open reference;
- front shroud has finite thickness through `hood_wall_thickness_mm`;
- blade tip uses the same topology-first attachment idea as the root-to-hub surface, but attaches to the closed shroud support.

The loop-family builder and validators must allow zero splitter blades for presets that explicitly set `splitter_blade_count = 0`.

### 5.3 NASA Stage 37 Stator Ring

Preset id:

```text
nasa_stage37_stator_ring_v1_1
```

Required interpretation:

- closed axial/compressor stator-ring approximation;
- use public Stage 37 vane-count and annulus data from the existing evidence casebook as source references;
- use V1.1 blade-to-blade loops, not V0.9 curve overrides;
- no splitters;
- thin stator/vane loop family with low wrap and modest lean;
- closed shroud support visible as a manufactured surface.

### 5.4 RR UltraFan CTi Fan

Preset id:

```text
rr_ultrafan_cti_fan_v1_1
```

Required interpretation:

- open fan approximation;
- use public UltraFan/CTi fan reference data from the existing evidence casebook as source references;
- use V1.1 blade-to-blade loops;
- no splitters unless explicitly justified by the source data;
- high-span, thin, twisted fan blade defaults;
- open tip reference support hidden in normal viewer modes.

### 5.5 Public Rocket Turbopump Inducer

Preset id:

```text
public_rocket_turbopump_inducer_v1_1
```

Required interpretation:

- open axial/screw-inducer approximation;
- use public liquid rocket turbopump inducer references from the existing evidence casebook;
- use V1.1 blade-to-blade loops;
- no splitters by default;
- high wrap and small blade count;
- preserve the screw-like flow turn while still emitting the six V1.1 face families.

## 6. Preset Deletion Policy

For V1.1.1 active catalogs:

- remove `radial_open_high_twist_thin_reference_v1_1`;
- remove NASA Rotor 67, NASA Rotor 37, NASA SDT R4, NASA SR-7L, RR UltraFan OGV, gear, turbine rotor analogy, worm analogy, and other non-selected frontend presets;
- remove or unregister active V1.1 DSL preset files that are not part of the five representative models.

Historical folders, evidence images, casebooks, and old-version resources remain available unless a later cleanup task explicitly scopes archival deletion.

## 7. Frontend Parameter Ownership

The frontend `ParameterPanel` must follow constructor-owned editable parameters, not a hard-coded legacy V1.1 set.

### 7.1 Source Of Truth

Preferred source order:

1. active preset `editable_parameters`;
2. synthesized runtime manifest `editable_parameters`;
3. fallback frontend schema for non-versioned legacy examples only.

V1.1.1 preset JSON files must declare their editable parameter ids explicitly.

### 7.2 Editable Scalar Parameters

V1.1.1 scalar parameters should be limited to values that the current constructor consumes directly and can vary without breaking the loop-family topology:

```text
mounting_bore_radius_mm
blade_thickness_mm
blade_wrap_deg
hub_wall_thickness_mm
hub_bottom_thickness_mm
hood_wall_thickness_mm       closed presets only
```

Optional additional parameters may be exposed only if the implementation adds validation proving they keep the preset feasible.

### 7.3 Preset-Owned Parameters

These are not normal scalar controls in V1.1.1:

```text
blade_count
main_blade_count
splitter_blade_count
splitter_passage_fraction
hub_profile_rz_mm
tip_or_shroud_profile_rz_mm
root_attachment_width_mm
root_attachment_lift_mm
segment_control_counts
leading_edge_cap_roundness
trailing_edge_cap_roundness
```

Blade population and topological mode are preset-owned because they change the passage graph. Meridional profiles and blade-to-blade loop curves belong in curve/control editors, not in the scalar parameter panel.

### 7.4 Curve Editors

The frontend may continue to show curve/control editors, but they must match V1.1.1 ownership:

- meridional hub/tip/shroud profile controls edit carrier curves;
- blade-to-blade loop controls edit segment controls in `s-q`;
- control point display and generated curve display must remain tied to the same payload keys consumed by the backend;
- obsolete V0.x blade-curve controls must not appear for V1.1.1 presets.

## 8. Validation And Tests

### 8.1 Backend Tests

Required tests:

- V1.1.1 resource registration:
  - exactly the five active V1.1.1 preset ids are registered for the active catalog;
  - each reports `geometry_patch_version == "1.1.1"`;
  - open reference has 8 main and 8 splitter blades;
  - closed reference has 12 main and 0 splitter blades;
  - public presets use V1.1 constructor ids and V1.1 loop-family defaults.
- Surface metadata contract:
  - every manufactured/review surface has `feature_id`, `cfd_role`, `display`, `wireframe`, `mesh`, and rectangular `uv_grid`;
  - reference-only tip support is hidden in normal views.
- Mesh manifest:
  - all visible manufactured/review surfaces appear in `triangle_regions`;
  - `transition_regions` remains a subset, not the full mesh visibility source.
- Zero-splitter closed preset:
  - loop builder accepts `splitter_blade_count = 0`;
  - no splitter blades are emitted;
  - validation still passes.

### 8.2 Frontend Tests

Required tests:

- `shaded` hides UV wires, mesh edge overlays, construction lines, and named boundary curves;
- `wireframe` renders all visible surface UV lines and no shaded faces;
- `combined` renders shaded faces and all visible surface UV lines;
- `CFD360 mesh` renders mesh edges for all visible manufactured/review surfaces, not only transition surfaces;
- active preset list contains exactly the five V1.1.1 representative presets;
- V1.1.1 parameter panel is driven by `editable_parameters` and does not show obsolete edge-treatment or legacy curve scalar controls.

### 8.3 Smoke Verification

Required verification commands:

```text
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_mesh_and_export_contract.py -q
python -m pytest tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_six_face_surface_family.py -q
cd frontend
npm.cmd test
```

Required service smoke:

- synthesize and instantiate all five V1.1.1 active presets;
- each manifest reports:

```text
geometry_version == "1.1"
geometry_patch_version == "1.1.1"
geometry_validation_status == "PASS"
transition_geometry_status == "topology_first_blade_to_blade_5_loop_surface_family_graph"
```

Manual frontend acceptance:

- `shaded` view has no line clutter;
- `wireframe` view shows UV lines on every visible surface;
- `combined` view shows shaded faces plus UV lines;
- `CFD360 mesh` shows mesh edges on every visible manufactured/review surface;
- open reference shows 8 main + 8 splitter blades;
- closed reference shows 12 blades and a finite-thickness shroud;
- only the five representative presets appear in the preset list.

## 9. Non-Goals

- No V1.2 geometry-domain change.
- No rollback to V1.0.4 or V0.9 preset semantics.
- No exact analytic OCCT/NURBS B-Rep replacement; sampled review-grade geometry remains in scope.
- No deletion of historical evidence logs or prior version documentation.
- No public-source reclassification beyond the five selected representative presets.

## 10. Risks

- If `CFD360 mesh` keeps using CFD patch groups as a hard filter, the user-visible bug will remain even if backend mesh data is complete.
- If the frontend keeps a hard-coded V1.1 visible-parameter list, new preset-owned constraints can be overridden accidentally.
- If public presets are migrated only in frontend parameters and not backend DSL resources, service smoke and export behavior will diverge again.
- If closed impeller zero-splitter behavior is not explicitly tested, the loop builder may keep assuming one splitter per main passage.

## 11. Self-Review

- No placeholder sections remain.
- V1.1.1 is scoped as a patch on V1.1, not a new geometry family.
- Viewer mode semantics are explicit and testable.
- Preset deletion scope is limited to active catalogs and resources, preserving historical evidence.
- Parameter ownership is explicit enough for implementation planning.
