# Impeller V1.1.1 Viewer, Preset, And Parameter Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.1.1 as a patch-level release that fixes viewer mode semantics, all-surface UV/mesh display, representative preset registration, zero-splitter closed blades, and constructor-aligned frontend parameters.

**Architecture:** Keep the V1.1 blade-to-blade loop surface-family constructor as the core geometry path, and bump only the patch contract to `geometry_patch_version = "1.1.1"`. Add explicit surface metadata so backend mesh manifests and frontend rendering use the same surface graph contract. Reduce active preset catalogs to five representative V1.1 presets and drive the parameter panel from preset-owned `editable_parameters`.

**Tech Stack:** Python geometry/runtime services with pytest; JSON DSL resources; React frontend with Node test runner; Three.js viewer.

## Global Constraints

- `geometry_version = "1.1"`
- `geometry_patch_version = "1.1.1"`
- `transition_geometry_status = "topology_first_blade_to_blade_5_loop_surface_family_graph"`
- `source_kernel = "v1_1_blade_to_blade_surface_family_kernel"`
- `mesh_strategy = "v1_1_1_all_surface_uv_grid_mesh"`
- Active V1.1.1 preset ids are exactly `radial_open_reference_v1_1`, `radial_closed_reference_v1_1`, `nasa_stage37_stator_ring_v1_1`, `rr_ultrafan_cti_fan_v1_1`, and `public_rocket_turbopump_inducer_v1_1`.
- Historical evidence folders and old-version resources are not deleted.
- Open reference preset uses 8 main blades and 8 splitter blades.
- Closed reference preset uses 12 main blades and 0 splitter blades.
- `shaded` renders surfaces only; `wireframe` renders all visible surface UV lines; `combined` renders surfaces plus all visible surface UV lines.
- `CFD360 mesh` must render mesh edges for all visible manufactured/review surfaces, not only transition surfaces.

---

## File Structure

- `src/part_rule_synthesis/impeller_v11_constants.py` owns V1.1.1 patch constants.
- `src/part_rule_synthesis/impeller_runtime_compiler.py` turns V1.1 preset resources into runtime metadata and parameter specs.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/*.json` owns active backend preset defaults.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/aliases.json` owns active V1.1 preset id routing.
- `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py` owns main/splitter loop generation and zero-splitter behavior.
- `src/part_rule_synthesis/impeller_v11_surface_family.py` owns V1.1 sampled surface graph construction and surface metadata.
- `src/part_rule_synthesis/impeller_surface_graph_export.py` and `src/part_rule_synthesis/impeller_mesh_manifest.py` own all-surface triangulation and mesh manifest summaries.
- `src/part_rule_synthesis/service.py` owns service-level mesh manifest generation for V1.1.
- `frontend/src/appModel.js` owns active frontend preset catalog, parameter schema, and editable parameter selection.
- `frontend/src/simulationViewModel.js` owns surface visibility by simulation mode.
- `frontend/src/meshOverlayModel.js` owns local shaded/wireframe/combined/mesh overlay visibility policy.
- `frontend/src/components/ModelViewer.js` applies viewer visibility policy to Three.js objects.
- Tests stay next to their current responsibilities: backend in `tests/test_impeller_v11_*.py`, frontend in `frontend/src/*.test.js`.

---

### Task 1: Patch Version And Representative Backend Preset Catalog

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_constants.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_open_reference.json`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_closed_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/nasa_stage37_stator_ring.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/rr_ultrafan_cti_fan.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/public_rocket_turbopump_inducer.json`
- Delete: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_open_high_twist_thin_reference.json`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/aliases.json`
- Test: `tests/test_impeller_v11_resources.py`

**Interfaces:**
- Consumes: `compile_impeller_runtime_preset(preset_id: str) -> dict[str, Any]`
- Produces: V1.1.1 runtime dictionaries with `geometry_patch_version == "1.1.1"` and `resolved_blade_to_blade_loop_family_defaults`.

- [ ] **Step 1: Write failing resource tests**

Add these tests to `tests/test_impeller_v11_resources.py`:

```python
def test_v111_active_backend_preset_catalog():
    ids = {preset_id for preset_id in impeller_json_preset_ids() if preset_id.endswith("_v1_1")}

    assert ids == {
        "radial_open_reference_v1_1",
        "radial_closed_reference_v1_1",
        "nasa_stage37_stator_ring_v1_1",
        "rr_ultrafan_cti_fan_v1_1",
        "public_rocket_turbopump_inducer_v1_1",
    }


def test_v111_open_reference_uses_eight_main_and_eight_splitters():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

    assert runtime["geometry_version"] == "1.1"
    assert runtime["geometry_patch_version"] == "1.1.1"
    assert runtime["mesh_strategy"] == "v1_1_1_all_surface_uv_grid_mesh"
    assert runtime["parameters"]["blade_count"]["default"] == 16
    assert defaults["main_blade_count"] == 8
    assert defaults["splitter_blade_count"] == 8
    assert defaults["splitter_positioning_mode"] == "main_passage_bisector"
    assert defaults["splitter_passage_fraction"] == 0.5


def test_v111_closed_reference_uses_twelve_full_blades_no_splitters():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

    assert runtime["geometry_patch_version"] == "1.1.1"
    assert runtime["facets"]["shroud_topology"] == "closed"
    assert runtime["parameters"]["blade_count"]["default"] == 12
    assert defaults["main_blade_count"] == 12
    assert defaults["splitter_blade_count"] == 0
    assert defaults["tip_attachment_mode"] == "closed_shroud_attachment"
    assert runtime["parameters"]["hood_wall_thickness_mm"]["default"] > 0.0


def test_v111_public_presets_use_v11_surface_family_language():
    for preset_id in [
        "nasa_stage37_stator_ring_v1_1",
        "rr_ultrafan_cti_fan_v1_1",
        "public_rocket_turbopump_inducer_v1_1",
    ]:
        runtime = compile_impeller_runtime_preset(preset_id)
        defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

        assert runtime["geometry_version"] == "1.1"
        assert runtime["geometry_patch_version"] == "1.1.1"
        assert runtime["transition_geometry_status"] == "topology_first_blade_to_blade_5_loop_surface_family_graph"
        assert runtime["constructor_id"].endswith("_v1_1")
        assert defaults["coordinate_system"] == "blade_to_blade_s_q_mm"
        assert defaults["main_blade_count"] == runtime["parameters"]["blade_count"]["default"]
        assert defaults["splitter_blade_count"] == 0
        assert defaults["side_sample_count"] >= 49
        assert defaults["edge_cap_sample_count"] >= 33
```

- [ ] **Step 2: Run the resource tests to verify failure**

Run:

```powershell
python -m pytest tests/test_impeller_v11_resources.py -q
```

Expected: FAIL because `geometry_patch_version` is still `1.1.0`, the active V1.1 catalog still includes the high-twist preset, and the three public V1.1 preset ids are missing.

- [ ] **Step 3: Update V1.1 constants**

Modify `src/part_rule_synthesis/impeller_v11_constants.py`:

```python
GEOMETRY_PATCH_VERSION = "1.1.1"
MESH_STRATEGY = "v1_1_1_all_surface_uv_grid_mesh"
```

- [ ] **Step 4: Make runtime compiler consume preset patch metadata**

Modify `_v11_runtime_defaults()` in `src/part_rule_synthesis/impeller_runtime_compiler.py` so the patch version and mesh strategy are not hard-coded to V1.1.0:

```python
return {
    "resolved_parameter_defaults": dict(parameters),
    "geometry_version": "1.1",
    "geometry_patch_version": preset.get("geometry_patch_version", "1.1.1"),
    "transition_geometry_status": preset.get(
        "transition_geometry_status",
        "topology_first_blade_to_blade_5_loop_surface_family_graph",
    ),
    "mesh_strategy": preset.get(
        "mesh_strategy",
        export_contract.get("mesh_strategy", "v1_1_1_all_surface_uv_grid_mesh"),
    ),
    "kernel_capability_matrix_id": "impeller_v1_1_kernel_capabilities",
    "golden_case_registry_id": "impeller_v1_1_golden_cases",
    "resolved_blade_to_blade_loop_family_defaults": dict(defaults),
    "editable_parameters": list(preset.get("editable_parameters", [])),
}
```

- [ ] **Step 5: Update open radial preset defaults**

In `radial_open_reference.json`, set:

```json
{
  "geometry_patch_version": "1.1.1",
  "mesh_strategy": "v1_1_1_all_surface_uv_grid_mesh",
  "parameter_values": {
    "blade_count": 16,
    "inlet_radius_mm": 150.0,
    "exit_radius_mm": 580.0,
    "inlet_blade_height_mm": 170.0,
    "outlet_blade_height_mm": 30.0,
    "inlet_blade_angle_deg": 21.0,
    "outlet_blade_angle_deg": 42.0,
    "blade_thickness_mm": 16.0,
    "hub_curve_height_mm": 400.0,
    "mounting_bore_radius_mm": 44.0,
    "blade_wrap_deg": 216.0,
    "blade_lean_deg": 18.0,
    "leading_edge_lean_deg": 6.0,
    "trailing_edge_lean_deg": -10.0,
    "leading_edge_sweep_mm": 0.0,
    "trailing_edge_sweep_mm": 0.0,
    "root_fillet_radius_mm": 14.0,
    "leading_edge_radius_mm": 4.0,
    "trailing_edge_radius_mm": 3.0,
    "tip_edge_radius_mm": 6.0,
    "hub_wall_thickness_mm": 24.0,
    "hub_bottom_thickness_mm": 32.0,
    "hub_top_cap_thickness_mm": 8.0,
    "hub_chamfer_radius_mm": 6.0
  }
}
```

In `blade_to_blade_loop_family_defaults`, set:

```json
{
  "main_blade_count": 8,
  "splitter_blade_count": 8,
  "splitter_positioning_mode": "main_passage_bisector",
  "splitter_passage_fraction": 0.5,
  "maximum_blade_thickness_mm": 18.0,
  "average_blade_thickness_mm": 14.0,
  "root_attachment_width_mm": 8.0,
  "root_attachment_lift_mm": 14.0,
  "root_blade_lift_mm": 14.0,
  "main_flow_turn_q_mm": 320.0,
  "splitter_flow_turn_q_mm": 230.0,
  "spanwise_flow_turn_delta_q_mm": 76.0,
  "midspan_bow_q_mm": 18.0,
  "tip_attachment_mode": "open_tip_dome",
  "tip_or_shroud_profile_rz_mm": [[300, 407], [320, 305], [350, 218], [400, 130], [490, 70], [581, 34]]
}
```

Set `editable_parameters` to:

```json
[
  "mounting_bore_radius_mm",
  "blade_thickness_mm",
  "blade_wrap_deg",
  "hub_wall_thickness_mm",
  "hub_bottom_thickness_mm"
]
```

- [ ] **Step 6: Update closed radial preset defaults**

In `radial_closed_reference.json`, set:

```json
{
  "geometry_patch_version": "1.1.1",
  "mesh_strategy": "v1_1_1_all_surface_uv_grid_mesh",
  "parameter_values": {
    "blade_count": 12,
    "inlet_radius_mm": 180.0,
    "exit_radius_mm": 610.0,
    "inlet_blade_height_mm": 120.0,
    "outlet_blade_height_mm": 60.0,
    "inlet_blade_angle_deg": 22.0,
    "outlet_blade_angle_deg": 38.0,
    "blade_thickness_mm": 24.0,
    "hub_curve_height_mm": 300.0,
    "mounting_bore_radius_mm": 42.0,
    "blade_wrap_deg": 136.0,
    "blade_lean_deg": 7.0,
    "leading_edge_lean_deg": 0.0,
    "trailing_edge_lean_deg": 0.0,
    "leading_edge_sweep_mm": 0.0,
    "trailing_edge_sweep_mm": 0.0,
    "root_fillet_radius_mm": 14.0,
    "leading_edge_radius_mm": 4.0,
    "trailing_edge_radius_mm": 3.0,
    "tip_edge_radius_mm": 6.0,
    "hub_wall_thickness_mm": 24.0,
    "hub_bottom_thickness_mm": 32.0,
    "hub_top_cap_thickness_mm": 8.0,
    "hub_chamfer_radius_mm": 6.0,
    "hood_wall_thickness_mm": 24.0,
    "hood_chamfer_radius_mm": 6.0
  }
}
```

In `blade_to_blade_loop_family_defaults`, set:

```json
{
  "main_blade_count": 12,
  "splitter_blade_count": 0,
  "main_streamwise_interval_s": [0.08, 0.92],
  "splitter_streamwise_interval_s": [0.35, 0.88],
  "splitter_positioning_mode": "main_passage_bisector",
  "splitter_passage_fraction": 0.5,
  "maximum_blade_thickness_mm": 26.0,
  "average_blade_thickness_mm": 22.0,
  "root_attachment_width_mm": 12.0,
  "root_attachment_lift_mm": 18.0,
  "root_blade_lift_mm": 18.0,
  "shroud_blade_inset_mm": 18.0,
  "main_flow_turn_q_mm": 160.0,
  "splitter_flow_turn_q_mm": 0.0,
  "spanwise_flow_turn_delta_q_mm": 32.0,
  "midspan_bow_q_mm": 8.0,
  "tip_attachment_mode": "closed_shroud_attachment",
  "hub_profile_rz_mm": [[180, 300], [210, 220], [270, 145], [380, 75], [500, 24], [610, 0]],
  "tip_or_shroud_profile_rz_mm": [[260, 306], [290, 240], [350, 165], [450, 95], [540, 50], [615, 34]]
}
```

Set `editable_parameters` to:

```json
[
  "mounting_bore_radius_mm",
  "blade_thickness_mm",
  "blade_wrap_deg",
  "hub_wall_thickness_mm",
  "hub_bottom_thickness_mm",
  "hood_wall_thickness_mm"
]
```

- [ ] **Step 7: Add the three public V1.1 preset JSON files**

Create the three new files with these ids and source values from `docs/evidence/2026-07-02-axial-public-data-v07/axial_public_presets_v0_7.json`.

`nasa_stage37_stator_ring.json`:

```json
{
  "preset_id": "nasa_stage37_stator_ring_v1_1",
  "display_name": "NASA Stage 37 stator ring v1.1",
  "summary": "Representative public axial stator-ring approximation migrated to V1.1 blade-to-blade loop surface-family defaults.",
  "geometry_version": "1.1",
  "geometry_patch_version": "1.1.1",
  "mesh_strategy": "v1_1_1_all_surface_uv_grid_mesh",
  "transition_geometry_status": "topology_first_blade_to_blade_5_loop_surface_family_graph",
  "constructor_id": "axisymmetric_throughflow_radial_closed_impeller_v1_1",
  "parameter_values": {
    "blade_count": 46,
    "inlet_radius_mm": 176.4,
    "exit_radius_mm": 253.7,
    "inlet_blade_height_mm": 77.3,
    "outlet_blade_height_mm": 75.6,
    "inlet_blade_angle_deg": 18.0,
    "outlet_blade_angle_deg": 28.0,
    "blade_thickness_mm": 2.3,
    "hub_curve_height_mm": 60.0,
    "mounting_bore_radius_mm": 82.0,
    "blade_wrap_deg": 24.0,
    "blade_lean_deg": 2.0,
    "leading_edge_lean_deg": -4.0,
    "trailing_edge_lean_deg": 5.0,
    "leading_edge_sweep_mm": 2.0,
    "trailing_edge_sweep_mm": -3.0,
    "root_fillet_radius_mm": 0.9,
    "leading_edge_radius_mm": 0.35,
    "trailing_edge_radius_mm": 0.25,
    "tip_edge_radius_mm": 0.25,
    "hub_wall_thickness_mm": 4.5,
    "hub_bottom_thickness_mm": 6.0,
    "hub_top_cap_thickness_mm": 3.0,
    "hub_chamfer_radius_mm": 0.8,
    "hood_wall_thickness_mm": 3.0,
    "hood_chamfer_radius_mm": 0.8
  },
  "blade_to_blade_loop_family_defaults": {
    "loop_family_id": "v1_1_default_blade_to_blade_loop_family",
    "coordinate_system": "blade_to_blade_s_q_mm",
    "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
    "main_blade_count": 46,
    "splitter_blade_count": 0,
    "main_streamwise_interval_s": [0.08, 0.92],
    "splitter_streamwise_interval_s": [0.35, 0.88],
    "splitter_phase_offset_pitch": 0.5,
    "splitter_positioning_mode": "main_passage_bisector",
    "splitter_passage_fraction": 0.5,
    "maximum_blade_thickness_mm": 2.4,
    "average_blade_thickness_mm": 2.0,
    "root_attachment_width_mm": 1.2,
    "root_attachment_lift_mm": 2.0,
    "root_blade_lift_mm": 2.0,
    "shroud_blade_inset_mm": 2.0,
    "main_flow_turn_q_mm": 24.0,
    "splitter_flow_turn_q_mm": 0.0,
    "spanwise_flow_turn_delta_q_mm": 8.0,
    "midspan_bow_q_mm": 2.0,
    "leading_edge_cap_roundness": 0.56,
    "trailing_edge_cap_roundness": 0.56,
    "tip_attachment_mode": "closed_shroud_attachment",
    "segment_control_count_minimums": {"pressure_side": 11, "suction_side": 11, "leading_edge": 13, "trailing_edge": 13},
    "segment_control_counts": {"pressure_side": 11, "suction_side": 11, "leading_edge": 13, "trailing_edge": 13},
    "side_sample_count": 49,
    "edge_cap_sample_count": 33,
    "surface_span_sample_count": 9,
    "root_short_direction_sample_count": 7,
    "closed_shroud_short_direction_sample_count": 7,
    "profile_revolve_sample_count": 49,
    "theta_sample_count": 97,
    "hub_solid_radial_sample_count": 9,
    "hub_solid_axial_sample_count": 17,
    "hub_profile_rz_mm": [[176.4, 60], [176.8, 48], [177.3, 36], [177.8, 23], [178.2, 11], [178.6, 0]],
    "tip_or_shroud_profile_rz_mm": [[253.7, 61], [253.4, 49], [253, 37], [252.6, 24], [252.3, 12], [252, 1]],
    "blade_hub_angle_contract_deg": [60.0, 120.0]
  },
  "editable_parameters": ["mounting_bore_radius_mm", "blade_thickness_mm", "blade_wrap_deg", "hub_wall_thickness_mm", "hub_bottom_thickness_mm", "hood_wall_thickness_mm"],
  "source_refs": ["public_stage37_casebook_2026_07_02", "impeller_v1_1_1_viewer_preset_parameter_overhaul_spec_2026_07_08"]
}
```

`rr_ultrafan_cti_fan.json`:

```json
{
  "preset_id": "rr_ultrafan_cti_fan_v1_1",
  "display_name": "RR UltraFan CTi fan v1.1",
  "summary": "Representative public UltraFan CTi fan approximation migrated to V1.1 blade-to-blade loop surface-family defaults.",
  "geometry_version": "1.1",
  "geometry_patch_version": "1.1.1",
  "mesh_strategy": "v1_1_1_all_surface_uv_grid_mesh",
  "transition_geometry_status": "topology_first_blade_to_blade_5_loop_surface_family_graph",
  "constructor_id": "axisymmetric_throughflow_radial_open_impeller_v1_1",
  "parameter_values": {
    "blade_count": 18,
    "inlet_radius_mm": 533.0,
    "exit_radius_mm": 1778.0,
    "inlet_blade_height_mm": 1245.0,
    "outlet_blade_height_mm": 1170.0,
    "inlet_blade_angle_deg": 18.0,
    "outlet_blade_angle_deg": 42.0,
    "blade_thickness_mm": 45.0,
    "hub_curve_height_mm": 850.0,
    "mounting_bore_radius_mm": 90.0,
    "blade_wrap_deg": 92.0,
    "blade_lean_deg": 28.0,
    "leading_edge_lean_deg": 16.0,
    "trailing_edge_lean_deg": -14.0,
    "leading_edge_sweep_mm": 90.0,
    "trailing_edge_sweep_mm": -120.0,
    "root_fillet_radius_mm": 14.0,
    "leading_edge_radius_mm": 7.0,
    "trailing_edge_radius_mm": 4.0,
    "tip_edge_radius_mm": 4.0,
    "hub_wall_thickness_mm": 55.0,
    "hub_bottom_thickness_mm": 75.0,
    "hub_top_cap_thickness_mm": 24.0,
    "hub_chamfer_radius_mm": 8.0,
    "hood_wall_thickness_mm": 12.0,
    "hood_chamfer_radius_mm": 3.0
  },
  "blade_to_blade_loop_family_defaults": {
    "loop_family_id": "v1_1_default_blade_to_blade_loop_family",
    "coordinate_system": "blade_to_blade_s_q_mm",
    "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
    "main_blade_count": 18,
    "splitter_blade_count": 0,
    "main_streamwise_interval_s": [0.08, 0.94],
    "splitter_streamwise_interval_s": [0.35, 0.88],
    "splitter_phase_offset_pitch": 0.5,
    "splitter_positioning_mode": "main_passage_bisector",
    "splitter_passage_fraction": 0.5,
    "maximum_blade_thickness_mm": 45.0,
    "average_blade_thickness_mm": 38.0,
    "root_attachment_width_mm": 24.0,
    "root_attachment_lift_mm": 38.0,
    "root_blade_lift_mm": 38.0,
    "main_flow_turn_q_mm": 1450.0,
    "splitter_flow_turn_q_mm": 0.0,
    "spanwise_flow_turn_delta_q_mm": 320.0,
    "midspan_bow_q_mm": 70.0,
    "leading_edge_cap_roundness": 0.56,
    "trailing_edge_cap_roundness": 0.56,
    "tip_attachment_mode": "open_tip_dome",
    "segment_control_count_minimums": {"pressure_side": 11, "suction_side": 11, "leading_edge": 13, "trailing_edge": 13},
    "segment_control_counts": {"pressure_side": 11, "suction_side": 11, "leading_edge": 13, "trailing_edge": 13},
    "side_sample_count": 49,
    "edge_cap_sample_count": 33,
    "surface_span_sample_count": 9,
    "root_short_direction_sample_count": 7,
    "closed_shroud_short_direction_sample_count": 7,
    "profile_revolve_sample_count": 49,
    "theta_sample_count": 97,
    "hub_solid_radial_sample_count": 9,
    "hub_solid_axial_sample_count": 17,
    "hub_profile_rz_mm": [[140, 850], [255, 790], [430, 650], [530, 430], [575, 170], [600, 0]],
    "tip_or_shroud_profile_rz_mm": [[1778, 851], [1776, 791], [1773, 651], [1770, 431], [1765, 171], [1760, 1]],
    "blade_hub_angle_contract_deg": [60.0, 120.0]
  },
  "editable_parameters": ["mounting_bore_radius_mm", "blade_thickness_mm", "blade_wrap_deg", "hub_wall_thickness_mm", "hub_bottom_thickness_mm"],
  "source_refs": ["public_rr_ultrafan_casebook_2026_07_02", "impeller_v1_1_1_viewer_preset_parameter_overhaul_spec_2026_07_08"]
}
```

`public_rocket_turbopump_inducer.json`:

```json
{
  "preset_id": "public_rocket_turbopump_inducer_v1_1",
  "display_name": "Public rocket turbopump inducer v1.1",
  "summary": "Representative public liquid-rocket turbopump inducer approximation migrated to V1.1 blade-to-blade loop surface-family defaults.",
  "geometry_version": "1.1",
  "geometry_patch_version": "1.1.1",
  "mesh_strategy": "v1_1_1_all_surface_uv_grid_mesh",
  "transition_geometry_status": "topology_first_blade_to_blade_5_loop_surface_family_graph",
  "constructor_id": "axisymmetric_throughflow_radial_open_impeller_v1_1",
  "parameter_values": {
    "blade_count": 3,
    "inlet_radius_mm": 35.0,
    "exit_radius_mm": 72.5,
    "inlet_blade_height_mm": 35.0,
    "outlet_blade_height_mm": 32.5,
    "inlet_blade_angle_deg": 12.0,
    "outlet_blade_angle_deg": 58.0,
    "blade_thickness_mm": 2.5,
    "hub_curve_height_mm": 120.0,
    "mounting_bore_radius_mm": 4.0,
    "blade_wrap_deg": 230.0,
    "blade_lean_deg": 10.0,
    "leading_edge_lean_deg": 4.0,
    "trailing_edge_lean_deg": 14.0,
    "leading_edge_sweep_mm": 10.0,
    "trailing_edge_sweep_mm": -8.0,
    "root_fillet_radius_mm": 0.8,
    "leading_edge_radius_mm": 0.35,
    "trailing_edge_radius_mm": 0.25,
    "tip_edge_radius_mm": 0.25,
    "hub_wall_thickness_mm": 4.0,
    "hub_bottom_thickness_mm": 6.0,
    "hub_top_cap_thickness_mm": 2.0,
    "hub_chamfer_radius_mm": 0.6,
    "hood_wall_thickness_mm": 2.0,
    "hood_chamfer_radius_mm": 0.5
  },
  "blade_to_blade_loop_family_defaults": {
    "loop_family_id": "v1_1_default_blade_to_blade_loop_family",
    "coordinate_system": "blade_to_blade_s_q_mm",
    "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
    "main_blade_count": 3,
    "splitter_blade_count": 0,
    "main_streamwise_interval_s": [0.04, 0.96],
    "splitter_streamwise_interval_s": [0.35, 0.88],
    "splitter_phase_offset_pitch": 0.5,
    "splitter_positioning_mode": "main_passage_bisector",
    "splitter_passage_fraction": 0.5,
    "maximum_blade_thickness_mm": 2.5,
    "average_blade_thickness_mm": 2.1,
    "root_attachment_width_mm": 1.2,
    "root_attachment_lift_mm": 2.5,
    "root_blade_lift_mm": 2.5,
    "main_flow_turn_q_mm": 165.0,
    "splitter_flow_turn_q_mm": 0.0,
    "spanwise_flow_turn_delta_q_mm": 28.0,
    "midspan_bow_q_mm": 8.0,
    "leading_edge_cap_roundness": 0.56,
    "trailing_edge_cap_roundness": 0.56,
    "tip_attachment_mode": "open_tip_dome",
    "segment_control_count_minimums": {"pressure_side": 11, "suction_side": 11, "leading_edge": 13, "trailing_edge": 13},
    "segment_control_counts": {"pressure_side": 11, "suction_side": 11, "leading_edge": 13, "trailing_edge": 13},
    "side_sample_count": 49,
    "edge_cap_sample_count": 33,
    "surface_span_sample_count": 9,
    "root_short_direction_sample_count": 7,
    "closed_shroud_short_direction_sample_count": 7,
    "profile_revolve_sample_count": 49,
    "theta_sample_count": 97,
    "hub_solid_radial_sample_count": 9,
    "hub_solid_axial_sample_count": 17,
    "hub_profile_rz_mm": [[10, 120], [15, 110], [25, 92], [34, 62], [39, 26], [42, 0]],
    "tip_or_shroud_profile_rz_mm": [[70, 121], [70.5, 111], [71, 93], [71.5, 63], [72, 27], [72.5, 1]],
    "blade_hub_angle_contract_deg": [60.0, 120.0]
  },
  "editable_parameters": ["mounting_bore_radius_mm", "blade_thickness_mm", "blade_wrap_deg", "hub_wall_thickness_mm", "hub_bottom_thickness_mm"],
  "source_refs": ["public_liquid_rocket_turbopump_inducer_casebook_2026_07_02", "impeller_v1_1_1_viewer_preset_parameter_overhaul_spec_2026_07_08"]
}
```

- [ ] **Step 8: Update aliases and remove high-twist preset**

Replace `v1_1/aliases.json` with:

```json
{
  "radial_open_reference_v1_1": "radial_open_reference_v1_1",
  "radial_closed_reference_v1_1": "radial_closed_reference_v1_1",
  "nasa_stage37_stator_ring_v1_1": "nasa_stage37_stator_ring_v1_1",
  "rr_ultrafan_cti_fan_v1_1": "rr_ultrafan_cti_fan_v1_1",
  "public_rocket_turbopump_inducer_v1_1": "public_rocket_turbopump_inducer_v1_1"
}
```

Delete the high-twist preset with `git rm -- src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_open_high_twist_thin_reference.json`.

- [ ] **Step 9: Run resource tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_resources.py -q
```

Expected: PASS for resource tests, except zero-splitter execution tests may still fail until Task 2.

- [ ] **Step 10: Commit Task 1**

```powershell
git add src/part_rule_synthesis/impeller_v11_constants.py src/part_rule_synthesis/impeller_runtime_compiler.py src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1 tests/test_impeller_v11_resources.py
git commit -m "feat: define impeller v1.1.1 preset catalog"
```

---

### Task 2: Zero-Splitter Loop Family Support

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py`
- Modify: `src/part_rule_synthesis/impeller_v11_loop_validation.py`
- Test: `tests/test_impeller_v11_main_splitter_domain.py`
- Test: `tests/test_impeller_v11_blade_to_blade_loop_domain.py`

**Interfaces:**
- Consumes: `build_v11_blade_to_blade_loop_family(parameters, defaults, overrides=None) -> dict[str, Any]`
- Produces: loop-family payloads where `splitter_blade_count == 0` is valid and reports `splitter_positioning_status == "NOT_APPLICABLE"`.

- [ ] **Step 1: Write failing zero-splitter tests**

Add to `tests/test_impeller_v11_main_splitter_domain.py`:

```python
from collections import Counter


def test_closed_v111_loop_family_accepts_zero_splitters():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")

    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    classes = Counter(blade["blade_class"] for blade in family["blades"])

    assert family["status"] == "PASS"
    assert classes == {"main": 12}
    assert family["metrics"]["blade_count"] == 12
    assert family["metrics"]["splitter_positioning_status"] == "NOT_APPLICABLE"
    assert family["metrics"]["splitter_passage_fraction_min"] is None
    assert family["metrics"]["splitter_passage_fraction_max"] is None
    assert family["metrics"]["splitter_passage_fraction_avg"] is None
```

Add to `tests/test_impeller_v11_blade_to_blade_loop_domain.py`:

```python
def test_zero_splitter_defaults_reject_negative_splitter_count():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = dict(runtime["resolved_blade_to_blade_loop_family_defaults"])
    defaults["splitter_blade_count"] = -1

    with pytest.raises(ValueError, match="splitter_blade_count must be zero or positive"):
        build_v11_blade_to_blade_loop_family(runtime["parameters"], defaults)
```

- [ ] **Step 2: Run zero-splitter tests to verify failure**

Run:

```powershell
python -m pytest tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_blade_to_blade_loop_domain.py -q
```

Expected: FAIL because `_validated_defaults()` still requires splitter blade counts to be positive and splitter metrics return `FAIL` when no splitter exists.

- [ ] **Step 3: Allow zero splitters in `_validated_defaults()`**

In `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py`, replace the positive-count check:

```python
if values["main_blade_count"] <= 0 or values["splitter_blade_count"] <= 0:
    raise ValueError("main and splitter blade counts must be positive")
```

with:

```python
if values["main_blade_count"] <= 0:
    raise ValueError("main_blade_count must be positive")
if values["splitter_blade_count"] < 0:
    raise ValueError("splitter_blade_count must be zero or positive")
if values["main_blade_count"] + values["splitter_blade_count"] != values["blade_count"]:
    raise ValueError("blade_count must equal main_blade_count + splitter_blade_count")
if values["splitter_blade_count"] == 0:
    values["splitter_flow_turn_q_mm"] = 0.0
```

Change the flow-turn validation:

```python
if values["main_flow_turn_q_mm"] <= 0.0 or values["splitter_flow_turn_q_mm"] <= 0.0:
    raise ValueError("flow turn q values must be positive")
```

to:

```python
if values["main_flow_turn_q_mm"] <= 0.0:
    raise ValueError("main_flow_turn_q_mm must be positive")
if values["splitter_blade_count"] > 0 and values["splitter_flow_turn_q_mm"] <= 0.0:
    raise ValueError("splitter_flow_turn_q_mm must be positive when splitters are present")
```

- [ ] **Step 4: Return non-failure metrics when no splitter exists**

Modify `_splitter_passage_fraction_metrics()`:

```python
if int(values.get("splitter_blade_count", 0)) == 0:
    return {
        "splitter_positioning_status": "NOT_APPLICABLE",
        "splitter_passage_fraction_min": None,
        "splitter_passage_fraction_max": None,
        "splitter_passage_fraction_avg": None,
    }
```

Keep the existing `FAIL` return for malformed cases where `splitter_blade_count > 0` but no splitter blade is emitted.

- [ ] **Step 5: Update validation to accept NOT_APPLICABLE splitter status**

In `src/part_rule_synthesis/impeller_v11_loop_validation.py`, find any check that treats non-`PASS` splitter positioning as failure. Change it to accept `{"PASS", "NOT_APPLICABLE"}`:

```python
if metrics.get("splitter_positioning_status") not in {"PASS", "NOT_APPLICABLE"}:
    failures.append(_failure("v1_1_splitter_positioning_failed"))
```

- [ ] **Step 6: Run zero-splitter tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_blade_to_blade_loop_domain.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py src/part_rule_synthesis/impeller_v11_loop_validation.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_blade_to_blade_loop_domain.py
git commit -m "feat: support zero-splitter v1.1 loop families"
```

---

### Task 3: Surface Metadata And All-Surface Mesh Manifest

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_surface_family.py`
- Modify: `src/part_rule_synthesis/impeller_v11_validation.py`
- Modify: `src/part_rule_synthesis/impeller_surface_graph_export.py`
- Modify: `src/part_rule_synthesis/impeller_mesh_manifest.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_v11_mesh_and_export_contract.py`
- Test: `tests/test_impeller_v11_six_face_surface_family.py`

**Interfaces:**
- Consumes: `build_v11_surface_graph(parameters, facets, defaults, profile_defaults=None, profile_overrides=None, overrides=None) -> dict[str, Any]`
- Produces: surfaces with `feature_id`, `cfd_role`, `viewer_surface_role`, all-surface `triangle_regions`, and `mesh_strategy == "v1_1_1_all_surface_uv_grid_mesh"`.

- [ ] **Step 1: Write failing backend surface metadata tests**

Add to `tests/test_impeller_v11_mesh_and_export_contract.py`:

```python
def test_v111_manufactured_surfaces_have_viewer_and_cfd_metadata():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    manufactured = [
        surface for surface in graph["surfaces"]
        if surface.get("role") not in {"open_tip_reference", "reference_only"}
    ]
    assert manufactured
    for surface in manufactured:
        assert surface["source_kernel"] == "v1_1_blade_to_blade_surface_family_kernel"
        assert surface.get("feature_id")
        assert surface.get("viewer_surface_role")
        assert surface.get("cfd_role")
        assert surface.get("wireframe", {}).get("enabled") is True
        assert surface.get("mesh", {}).get("triangle_count", 0) > 0
        assert isinstance(surface.get("display", {}).get("color"), str)
        assert isinstance(surface.get("display", {}).get("wire_color"), str)
```

Add to the same file:

```python
def test_v111_mesh_manifest_includes_all_visible_manufactured_surfaces(tmp_path: Path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", "radial_open_reference_v1_1")
    parameters = {
        name: spec["default"]
        for name, spec in service.engines[engine.engine_id]["parameters"].items()
    }

    run = service.instantiate(engine.engine_id, parameters)
    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]
    mesh_manifest = manifest["simulation_manifests"]["cfd_surface_mesh"]
    visible_surface_ids = {
        surface["id"]
        for surface in graph["surfaces"]
        if surface.get("display", {}).get("visible_by_default") is not False
        and surface.get("role") not in {"open_tip_reference", "reference_only"}
    }

    assert manifest["mesh_strategy"] == "v1_1_1_all_surface_uv_grid_mesh"
    assert visible_surface_ids
    assert visible_surface_ids.issubset(set(mesh_manifest["included_surface_ids"]))
    assert visible_surface_ids.issubset({region["surface_graph_id"] for region in mesh_manifest["triangle_regions"]})
    assert len(mesh_manifest["transition_regions"]) < len(mesh_manifest["triangle_regions"])
```

- [ ] **Step 2: Run metadata/mesh tests to verify failure**

Run:

```powershell
python -m pytest tests/test_impeller_v11_mesh_and_export_contract.py -q
```

Expected: FAIL because V1.1 surfaces lack uniform `cfd_role`/`feature_id`, V1.1 service mesh manifest is incomplete or missing, and mesh strategy still reports the V1.1.0 value.

- [ ] **Step 3: Add metadata mapping in `impeller_v11_surface_family.py`**

Add near `_display_policy()`:

```python
_SURFACE_ROLE_METADATA = {
    "blade_pressure": {"feature_id": "blade_pressure_surface", "cfd_role": "blade_pressure", "viewer_surface_role": "manufactured_blade_face"},
    "blade_suction": {"feature_id": "blade_suction_surface", "cfd_role": "blade_suction", "viewer_surface_role": "manufactured_blade_face"},
    "blade_leading_edge": {"feature_id": "blade_leading_edge_surface", "cfd_role": "leading_edge_transition", "viewer_surface_role": "manufactured_transition_face"},
    "blade_trailing_edge": {"feature_id": "blade_trailing_edge_surface", "cfd_role": "trailing_edge_transition", "viewer_surface_role": "manufactured_transition_face"},
    "root_to_hub_attachment": {"feature_id": "root_to_hub_attachment_surface", "cfd_role": "root_transition", "viewer_surface_role": "manufactured_transition_face"},
    "open_tip_dome": {"feature_id": "open_tip_dome_surface", "cfd_role": "tip_transition", "viewer_surface_role": "manufactured_transition_face"},
    "closed_shroud_attachment": {"feature_id": "closed_shroud_attachment_surface", "cfd_role": "tip_transition", "viewer_surface_role": "manufactured_transition_face"},
    "hub_support": {"feature_id": "hub_support_surface", "cfd_role": "hub_wall", "viewer_surface_role": "manufactured_support_face"},
    "shroud_support": {"feature_id": "shroud_support_surface", "cfd_role": "tip_or_shroud_wall", "viewer_surface_role": "manufactured_support_face"},
    "hub_top_cap": {"feature_id": "hub_material_solid", "cfd_role": "hub_wall", "viewer_surface_role": "manufactured_hub_solid_face"},
    "hub_bottom_cap": {"feature_id": "hub_material_solid", "cfd_role": "hub_wall", "viewer_surface_role": "manufactured_hub_solid_face"},
    "hub_bottom_outer_wall": {"feature_id": "hub_material_solid", "cfd_role": "hub_wall", "viewer_surface_role": "manufactured_hub_solid_face"},
    "mounting_bore": {"feature_id": "mounting_bore", "cfd_role": "internal_assembly", "viewer_surface_role": "manufactured_internal_review_face"},
}
```

Add helper:

```python
def _surface_role_metadata(role: str, face_family: str) -> dict[str, Any]:
    metadata = _SURFACE_ROLE_METADATA.get(role) or _SURFACE_ROLE_METADATA.get(face_family) or {}
    return {
        "feature_id": metadata.get("feature_id", role or face_family),
        "cfd_role": metadata.get("cfd_role", role or face_family),
        "viewer_surface_role": metadata.get("viewer_surface_role", "manufactured_review_face"),
    }
```

Update `_generic_surface()`:

```python
metadata = _surface_role_metadata(role, face_family)
return {
    "id": surface_id,
    "kind": "native_topology_face",
    "face_family": face_family,
    "role": role,
    "feature_id": metadata["feature_id"],
    "cfd_role": metadata["cfd_role"],
    "viewer_surface_role": metadata["viewer_surface_role"],
    "source_kernel": SOURCE_KERNEL,
    "uv_grid": copy.deepcopy(uv_grid),
    "control_net": _control_net(uv_grid),
    "edge_samples": {},
    "wireframe": {"enabled": True, "color": display["wire_color"]},
    "mesh": _quad_mesh(uv_grid),
    "display": display,
}
```

- [ ] **Step 4: Mark open tip reference as reference-only display**

In `_support_surfaces()`, make the open tip reference surface display overrides include:

```python
display_overrides={
    "visible_by_default": False,
    "reference_only": True,
    "construction_reference": True,
    "inspection_class": "open_tip_reference",
}
```

Keep:

```python
surface_flags={"reference_only": True}
```

- [ ] **Step 5: Add all-surface mesh visibility mode**

In `src/part_rule_synthesis/impeller_surface_graph_export.py`, update `_surface_visible_in_view()`:

```python
if view_id == "v1_1_1_all_surface_mesh":
    display = surface.get("display") if isinstance(surface.get("display"), dict) else {}
    flags = surface.get("surface_flags") if isinstance(surface.get("surface_flags"), dict) else {}
    role = surface.get("role")
    if flags.get("reference_only") is True or display.get("reference_only") is True:
        return False
    if role in {"reference_only", "open_tip_reference", "construction_support_only"}:
        return False
    return True
```

Leave existing `cfd_full_360` behavior intact for solver patch exports.

- [ ] **Step 6: Generate V1.1 mesh manifest through all-surface view**

In `src/part_rule_synthesis/service.py`, include `"1.1"` in mesh manifest generation and call the new view id for V1.1:

```python
if dsl["part_family"] == "impeller" and _dsl_version(dsl) in {"0.6", "0.7", "0.8", "0.9", "1.0", "1.1"}:
    surface_graph_for_mesh = geometry_metadata.get("surface_graph", {})
    mesh_view_id = "v1_1_1_all_surface_mesh" if _dsl_version(dsl) == "1.1" else "cfd_full_360"
    simulation_manifests["cfd_surface_mesh"] = build_surface_mesh_manifest(
        surface_graph_for_mesh,
        view_id=mesh_view_id,
    )
```

Preserve the existing deferred V1.0.3 branch inside this block by applying the `mesh_view_id` only in the non-deferred call.

- [ ] **Step 7: Add mesh strategy status to mesh manifest**

In `src/part_rule_synthesis/impeller_mesh_manifest.py`, include the surface graph mesh strategy:

```python
"mesh_strategy_status": surface_graph.get("mesh_strategy", triangulation.get("mesh_strategy", "")),
"view_id": view_id,
```

Also ensure `transition_regions` is always present:

```python
"transition_regions": [
    {
        "surface_graph_id": region["surface_graph_id"],
        "edge_family": region.get("edge_family", ""),
        "transition_policy_id": region.get("transition_policy_id", ""),
        "triangle_start": region["triangle_start"],
        "triangle_count": region["triangle_count"],
    }
    for region in transition_regions
],
```

- [ ] **Step 8: Update V1.1 validation for required metadata**

In `src/part_rule_synthesis/impeller_v11_validation.py`, inside `_is_manufactured_surface(surface)` validation loop, add:

```python
for required_key in ("feature_id", "cfd_role", "viewer_surface_role"):
    if not surface.get(required_key):
        failures.append(_failure("v1_1_surface_metadata_missing", surface_graph_id=surface_id, missing_key=required_key))
```

Do not apply this to `reference_only` surfaces.

- [ ] **Step 9: Run backend metadata/mesh tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_mesh_and_export_contract.py tests/test_impeller_v11_six_face_surface_family.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit Task 3**

```powershell
git add src/part_rule_synthesis/impeller_v11_surface_family.py src/part_rule_synthesis/impeller_v11_validation.py src/part_rule_synthesis/impeller_surface_graph_export.py src/part_rule_synthesis/impeller_mesh_manifest.py src/part_rule_synthesis/service.py tests/test_impeller_v11_mesh_and_export_contract.py tests/test_impeller_v11_six_face_surface_family.py
git commit -m "feat: add v1.1.1 all-surface mesh metadata"
```

---

### Task 4: Frontend Viewer Mode Semantics

**Files:**
- Modify: `frontend/src/meshOverlayModel.js`
- Modify: `frontend/src/meshOverlayModel.test.js`
- Modify: `frontend/src/simulationViewModel.js`
- Modify: `frontend/src/simulationViewModel.test.js`
- Modify: `frontend/src/components/ModelViewer.js`

**Interfaces:**
- Consumes: surface graph surfaces with `display.visible_by_default`, `surface_flags.reference_only`, `uv_grid`, and `mesh`.
- Produces: `viewerLayerVisibility({ simulationViewMode, viewMode, meshOverlayMode, visibleLayers }) -> { showShadedSurfaces, showSurfaceUvWire, showMeshEdges, showConstructionLines }`.

- [ ] **Step 1: Write failing frontend visibility tests**

In `frontend/src/meshOverlayModel.test.js`, add:

```javascript
import { viewerLayerVisibility } from "./meshOverlayModel.js";

test("v1.1.1 local viewer modes keep shaded wireframe and combined distinct", () => {
  assert.deepEqual(
    viewerLayerVisibility({ simulationViewMode: "cad_review_360", viewMode: "shaded" }),
    {
      showShadedSurfaces: true,
      showSurfaceUvWire: false,
      showMeshEdges: false,
      showConstructionLines: false,
    },
  );
  assert.deepEqual(
    viewerLayerVisibility({ simulationViewMode: "cad_review_360", viewMode: "wireframe" }),
    {
      showShadedSurfaces: false,
      showSurfaceUvWire: true,
      showMeshEdges: false,
      showConstructionLines: false,
    },
  );
  assert.deepEqual(
    viewerLayerVisibility({ simulationViewMode: "cad_review_360", viewMode: "combined" }),
    {
      showShadedSurfaces: true,
      showSurfaceUvWire: true,
      showMeshEdges: false,
      showConstructionLines: false,
    },
  );
});

test("v1.1.1 mesh inspection shows mesh edges except in shaded-only local mode", () => {
  assert.equal(
    viewerLayerVisibility({ simulationViewMode: "mesh", viewMode: "combined", meshOverlayMode: "triangle_edges" }).showMeshEdges,
    true,
  );
  assert.equal(
    viewerLayerVisibility({ simulationViewMode: "mesh", viewMode: "shaded", meshOverlayMode: "triangle_edges" }).showMeshEdges,
    false,
  );
  assert.equal(
    viewerLayerVisibility({ simulationViewMode: "mesh", viewMode: "wireframe", meshOverlayMode: "off" }).showMeshEdges,
    false,
  );
});
```

In `frontend/src/simulationViewModel.test.js`, replace the CFD whitelist test with:

```javascript
test("mesh view keeps all visible manufactured surfaces instead of cfd patch whitelist", () => {
  const manifest = {
    simulation_manifests: {
      cfd_full_360: {
        patch_instances: {
          pressure: { source_type: "surface", surface_graph_id: "blade_0_pressure_surface" },
        },
      },
    },
  };

  assert.equal(
    surfaceVisibleInView({ id: "hub_top_annulus_surface", role: "hub_top_cap", cfd_role: "hub_wall" }, "mesh", manifest),
    true,
  );
  assert.equal(
    surfaceVisibleInView({ id: "mounting_bore_inner_wall_surface", role: "mounting_bore", cfd_role: "internal_assembly" }, "mesh", manifest),
    true,
  );
  assert.equal(
    surfaceVisibleInView({ id: "tip_reference_surface", role: "open_tip_reference", display: { visible_by_default: false, reference_only: true } }, "mesh", manifest),
    false,
  );
});
```

- [ ] **Step 2: Run frontend visibility tests to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- meshOverlayModel.test.js simulationViewModel.test.js
```

Expected: FAIL because `viewerLayerVisibility` does not exist and mesh visibility still uses patch whitelists.

- [ ] **Step 3: Add `viewerLayerVisibility()`**

In `frontend/src/meshOverlayModel.js`, add:

```javascript
export function viewerLayerVisibility({
  simulationViewMode = "cad_review_360",
  viewMode = "combined",
  meshOverlayMode = "triangle_edges",
  visibleLayers = {},
} = {}) {
  const activeMeshOverlayMode = effectiveMeshOverlayMode(simulationViewMode, meshOverlayMode);
  const shadedEnabled = visibleLayers.shaded_surfaces !== false;
  const uvWireEnabled = visibleLayers.nurbs_uv_wire !== false;
  const meshEdgesEnabled = visibleLayers.mesh_edges !== false && visibleLayers.transition_mesh_edges !== false;
  const isMeshInspection = simulationViewMode === "mesh";
  return {
    showShadedSurfaces: shadedEnabled && (viewMode === "shaded" || viewMode === "combined"),
    showSurfaceUvWire: uvWireEnabled && (viewMode === "wireframe" || viewMode === "combined"),
    showMeshEdges: meshEdgesEnabled && isMeshInspection && activeMeshOverlayMode !== "off" && viewMode !== "shaded",
    showConstructionLines: simulationViewMode === "feature_debug",
  };
}
```

Keep `viewerVisibilityForMeshOverlay()` as a compatibility wrapper:

```javascript
export function viewerVisibilityForMeshOverlay(args = {}) {
  const visibility = viewerLayerVisibility(args);
  return {
    showShaded: visibility.showShadedSurfaces,
    showMeshOverlay: visibility.showMeshEdges,
  };
}
```

- [ ] **Step 4: Update `surfaceVisibleInView()` for mesh all-surface mode**

In `frontend/src/simulationViewModel.js`, replace mesh-specific transition filtering:

```javascript
if (viewMode === "mesh" && isTransitionSurface(surface, cfdSurfaceMeshManifest(manifest))) {
  return true;
}
const patchSurfaceIds = cfdPatchSurfaceIds(manifest);
if (patchSurfaceIds.size > 0) {
  return patchSurfaceIds.has(surface?.id || surface?.surface_graph_id);
}
return Boolean(surface?.cfd_role);
```

with:

```javascript
if (viewMode === "mesh") {
  return Boolean(surface?.uv_grid?.length || surface?.mesh) && surface?.role !== "open_tip_reference";
}
const patchSurfaceIds = cfdPatchSurfaceIds(manifest);
if (patchSurfaceIds.size > 0) {
  return patchSurfaceIds.has(surface?.id || surface?.surface_graph_id);
}
return Boolean(surface?.cfd_role);
```

Also remove `"mounting_bore"` from `CFD_HIDDEN_ROLES` for mesh mode by moving the hidden-role check below the `viewMode === "mesh"` branch:

```javascript
if (viewMode === "mesh") {
  if (["open_tip_reference", "reference_only", "construction_support_only"].includes(surface?.role)) {
    return false;
  }
  return Boolean(surface?.uv_grid?.length || surface?.mesh);
}
if ([surface?.role, surface?.cfd_role, surface?.kind, surface?.assembly_role].some((role) => CFD_HIDDEN_ROLES.has(role))) {
  return false;
}
```

- [ ] **Step 5: Apply new visibility policy in `ModelViewer.js`**

Import `viewerLayerVisibility`:

```javascript
import {
  effectiveMeshOverlayMode,
  meshOverlayControlVisible,
  meshOverlayOptions,
  viewerLayerVisibility,
} from "../meshOverlayModel.js?v=1.1.3";
```

In `updateVisibility()`, replace the current `viewerVisibilityForMeshOverlay()` block with:

```javascript
const visibility = viewerLayerVisibility({
  simulationViewMode,
  viewMode,
  meshOverlayMode: activeMeshOverlayMode,
  visibleLayers,
});
shaded.visible = visibility.showShadedSurfaces || visibility.showSurfaceUvWire || visibility.showMeshEdges;
shaded.traverse((child) => {
  if (child.isMesh && child.userData.layer) {
    child.visible = visibility.showShadedSurfaces && visibleLayers[child.userData.layer] !== false;
  }
  if (child.isLineSegments && child.userData.isSurfaceUvWire && child.userData.layer) {
    child.visible = visibility.showSurfaceUvWire && visibleLayers[child.userData.layer] !== false;
  }
  if (child.isLineSegments && child.userData.isMeshOverlay && child.userData.layer) {
    child.visible = visibility.showMeshEdges && visibleLayers[child.userData.layer] !== false;
  }
});
```

Replace construction visibility with:

```javascript
constructionGroup.visible = visibility.showConstructionLines;
```

Keep selected CFD boundary curves visible only when explicitly selected:

```javascript
const showConstruction =
  visibility.showConstructionLines ||
  (isCfdInspectionView(simulationViewMode) && constructionGroup.userData.hasCfdBoundarySelection);
constructionGroup.visible = showConstruction;
```

- [ ] **Step 6: Run frontend visibility tests**

Run:

```powershell
cd frontend
npm.cmd test -- meshOverlayModel.test.js simulationViewModel.test.js
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```powershell
git add frontend/src/meshOverlayModel.js frontend/src/meshOverlayModel.test.js frontend/src/simulationViewModel.js frontend/src/simulationViewModel.test.js frontend/src/components/ModelViewer.js
git commit -m "feat: clarify v1.1.1 viewer modes"
```

---

### Task 5: Frontend Representative Presets And Constructor-Aligned Parameters

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/appModel.test.js`
- Modify: `frontend/src/components/ParameterPanel.js`
- Test: `frontend/src/appModel.test.js`

**Interfaces:**
- Consumes: frontend preset objects with `presetId`, `parameters`, `facets`, `profileOverrides`, `curveControls`, and `editableParameters`.
- Produces: active `presets` array with exactly five V1.1.1 representative presets and parameter panel rows driven by `editableParameters`.

- [ ] **Step 1: Write failing app model tests**

In `frontend/src/appModel.test.js`, replace old public/analogy catalog tests with:

```javascript
test("v1.1.1 frontend catalog contains exactly five representative presets", () => {
  assert.deepEqual(
    presets.map((preset) => preset.id),
    [
      "axisymmetric-nurbs-open-throughflow",
      "axisymmetric-nurbs-closed-throughflow",
      "public-nasa-stage37-stator-ring",
      "public-rr-ultrafan-cti-fan",
      "public-liquid-rocket-turbopump-inducer",
    ],
  );
  assert.deepEqual(
    presets.map((preset) => preset.presetId),
    [
      "radial_open_reference_v1_1",
      "radial_closed_reference_v1_1",
      "nasa_stage37_stator_ring_v1_1",
      "rr_ultrafan_cti_fan_v1_1",
      "public_rocket_turbopump_inducer_v1_1",
    ],
  );
  assert.ok(presets.every((preset) => preset.geometryPatchVersion === "1.1.1"));
});

test("v1.1.1 parameter panel schema follows preset editableParameters", () => {
  const open = presets[0];
  const closed = presets[1];

  assert.deepEqual(Object.keys(parameterSchemaForPreset(open)), [
    "mounting_bore_radius_mm",
    "blade_wrap_deg",
    "blade_thickness_mm",
    "hub_wall_thickness_mm",
    "hub_bottom_thickness_mm",
  ]);
  assert.deepEqual(Object.keys(parameterSchemaForPreset(closed)), [
    "mounting_bore_radius_mm",
    "blade_wrap_deg",
    "blade_thickness_mm",
    "hub_wall_thickness_mm",
    "hub_bottom_thickness_mm",
    "hood_wall_thickness_mm",
  ]);
  assert.ok(hiddenParameterIdsForPreset(open).includes("blade_count"));
  assert.ok(hiddenParameterIdsForPreset(open).includes("root_fillet_radius_mm"));
  assert.ok(hiddenParameterIdsForPreset(open).includes("leading_edge_radius_mm"));
});

test("v1.1.1 frontend open and closed population defaults match backend contract", () => {
  const open = presets[0];
  const closed = presets[1];

  assert.equal(open.parameters.blade_count, 16);
  assert.equal(open.loopFamilyDefaults.main_blade_count, 8);
  assert.equal(open.loopFamilyDefaults.splitter_blade_count, 8);
  assert.equal(closed.parameters.blade_count, 12);
  assert.equal(closed.loopFamilyDefaults.main_blade_count, 12);
  assert.equal(closed.loopFamilyDefaults.splitter_blade_count, 0);
});
```

- [ ] **Step 2: Run app model tests to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js
```

Expected: FAIL because old presets remain and `parameterSchemaForPreset()` still uses hard-coded V1.1 visible fields.

- [ ] **Step 3: Add `editableParameterIdsForPreset()` and use it in schema filtering**

In `frontend/src/appModel.js`, add:

```javascript
export function editableParameterIdsForPreset(presetRef) {
  const preset = resolvePresetReference(presetRef);
  if (Array.isArray(preset?.editableParameters) && preset.editableParameters.length > 0) {
    return [...preset.editableParameters];
  }
  return Object.keys(parameterSchema);
}
```

Replace `hiddenParameterIdsForPreset()` with:

```javascript
export function hiddenParameterIdsForPreset(presetRef) {
  const preset = resolvePresetReference(presetRef);
  const editable = new Set(editableParameterIdsForPreset(preset));
  return Object.keys(parameterSchema).filter((name) => !editable.has(name));
}
```

Keep `parameterSchemaForPreset()` unchanged except that it now uses the new hidden list.

- [ ] **Step 4: Replace frontend `presets` array with five active V1.1.1 entries**

In `frontend/src/appModel.js`, delete entries for:

```text
radial_open_reference_v1_0
radial_closed_reference_v1_0
radial_open_high_twist_thin_reference_v1_1
radial_open_reference_v0_9 public Rotor 67
radial_open_reference_v0_9 public Rotor 37
radial_open_reference_v0_9 public SDT R4
radial_closed_reference_v0_9 RR UltraFan OGV
radial_open_reference_v0_9 NASA SR-7L
mechanical analogy presets
```

Keep only five objects. Each object must include:

```javascript
geometryPatchVersion: "1.1.1",
metadata: {
  geometryVersion: "1.1",
  geometryPatchVersion: "1.1.1",
  transitionGeometryStatus: "topology_first_blade_to_blade_5_loop_surface_family_graph",
},
editableParameters: [
  "mounting_bore_radius_mm",
  "blade_wrap_deg",
  "blade_thickness_mm",
  "hub_wall_thickness_mm",
  "hub_bottom_thickness_mm",
],
loopFamilyDefaults: {
  main_blade_count: 8,
  splitter_blade_count: 8,
},
```

For the closed preset, include `"hood_wall_thickness_mm"` in `editableParameters` and set `loopFamilyDefaults` to `{ main_blade_count: 12, splitter_blade_count: 0 }`.

For the three public presets, use the parameter values and ids from Task 1.

- [ ] **Step 5: Update `presetDisplayRank()`**

Replace the rank map with:

```javascript
const preferredOrder = {
  radial_open_reference_v1_1: 0,
  radial_closed_reference_v1_1: 1,
  nasa_stage37_stator_ring_v1_1: 2,
  rr_ultrafan_cti_fan_v1_1: 3,
  public_rocket_turbopump_inducer_v1_1: 4,
};
```

- [ ] **Step 6: Keep ParameterPanel driven by schema**

`frontend/src/components/ParameterPanel.js` already calls `parameterSchemaForPreset(activePreset)`. Remove the unused `hiddenParameterIds` calculation if it becomes redundant:

```javascript
const visibleParameterSchema = parameterSchemaForPreset(activePreset);
const groupedParameters = parameterGroups
  .map((group) => ({
    ...group,
    entries: Object.entries(visibleParameterSchema).filter(([, spec]) => spec.group === group.id),
  }))
  .filter((group) => group.entries.length > 0);
```

- [ ] **Step 7: Run app model tests**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```powershell
git add frontend/src/appModel.js frontend/src/appModel.test.js frontend/src/components/ParameterPanel.js
git commit -m "feat: focus v1.1.1 frontend presets and parameters"
```

---

### Task 6: End-To-End Verification And Evidence Update

**Files:**
- Modify: `docs/version-history.md`
- Modify: `docs/repository-map.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md`
- Create: `docs/evidence/2026-07-08-impeller-v1-1-1-viewer-preset-parameter-overhaul-evidence.md`

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: test transcript summary and version/evidence documentation for V1.1.1.

- [ ] **Step 1: Run backend V1.1 tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_mesh_and_export_contract.py -q
python -m pytest tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: PASS.

- [ ] **Step 3: Run service smoke for five presets**

Run this PowerShell command from the worktree root:

```powershell
@'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

presets = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]
service = RuleSynthesisService(Path(".tmp-v111-smoke"), model_output_root=Path(".tmp-v111-smoke") / "Model Output")
for preset_id in presets:
    engine = service.synthesize("impeller", preset_id)
    parameters = {name: spec["default"] for name, spec in service.engines[engine.engine_id]["parameters"].items()}
    run = service.instantiate(engine.engine_id, parameters)
    manifest = run.manifest
    assert manifest["geometry_version"] == "1.1", preset_id
    assert manifest["geometry_patch_version"] == "1.1.1", preset_id
    assert manifest["geometry_validation_status"] == "PASS", preset_id
    assert manifest["transition_geometry_status"] == "topology_first_blade_to_blade_5_loop_surface_family_graph", preset_id
    assert manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"] > 0, preset_id
    print(preset_id, manifest["geometry_validation_status"], manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"])
'@ | python -
```

Expected: one line per preset with `PASS` and a positive triangle count.

- [ ] **Step 4: Update evidence document**

Create `docs/evidence/2026-07-08-impeller-v1-1-1-viewer-preset-parameter-overhaul-evidence.md`:

```markdown
# Impeller V1.1.1 Viewer, Preset, And Parameter Overhaul Evidence

Date: 2026-07-08

## Summary

V1.1.1 keeps the V1.1 blade-to-blade loop surface-family constructor and patches display semantics, all-surface mesh metadata, active preset selection, zero-splitter closed presets, and frontend parameter ownership.

## Verification

- `python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_mesh_and_export_contract.py -q`
- `python -m pytest tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q`
- `cd frontend && npm.cmd test`
- five-preset RuleSynthesisService smoke

## Result

- Backend V1.1 tests: PASS
- Frontend tests: PASS
- Five-preset service smoke: PASS for `radial_open_reference_v1_1`, `radial_closed_reference_v1_1`, `nasa_stage37_stator_ring_v1_1`, `rr_ultrafan_cti_fan_v1_1`, and `public_rocket_turbopump_inducer_v1_1`
```

Before committing the evidence file, replace the three PASS bullets with concise terminal summaries that include test counts and smoke triangle counts.

- [ ] **Step 5: Update version and insight logs**

Append to `docs/version-history.md`:

```markdown
### V1.1.1 - Viewer, Preset, And Parameter Overhaul

- Clarifies shaded/wireframe/combined viewer semantics.
- Makes CFD360 mesh inspection use all visible sampled surfaces instead of only transition regions.
- Narrows active V1.1 catalog to five representative presets.
- Adds zero-splitter closed preset support.
- Moves V1.1 frontend parameter visibility to preset-owned `editable_parameters`.
```

Append to `docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md`:

```markdown
## 2026-07-08 - V1.1.1 Viewer And Preset Catalog Patch

V1.1.1 preserves the V1.1 blade-to-blade loop geometry semantics while changing active software behavior: viewer modes are now semantic rendering contracts, mesh inspection uses all visible sampled surfaces, and the active preset catalog is reduced to five representative models.
```

Append to `docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md`:

```markdown
## Insight - Viewer Modes Must Consume Surface Graphs, Not Construction Lines

The V1.1 geometry graph already contains enough sampled surface data for UV and mesh inspection. Rendering only construction or CFD patch lines hides correct geometry and makes failures look like geometry regressions. V1.1.1 therefore treats `uv_grid` as the review source of truth for wireframe and mesh inspection.
```

- [ ] **Step 6: Commit Task 6**

```powershell
git add docs/version-history.md docs/repository-map.md docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md docs/evidence/2026-07-08-impeller-v1-1-1-viewer-preset-parameter-overhaul-evidence.md
git commit -m "docs: record impeller v1.1.1 evidence"
```

---

## Final Verification

- [ ] Run all V1.1 backend tests:

```powershell
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_mesh_and_export_contract.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q
```

- [ ] Run frontend tests:

```powershell
cd frontend
npm.cmd test
```

- [ ] Run five-preset service smoke from Task 6.

- [ ] Start local backend and frontend from this worktree, then manually verify:
  - preset list has exactly five entries;
  - open preset has 8 main and 8 splitter blades;
  - closed preset has 12 blades and finite shroud thickness;
  - `shaded` has no lines;
  - `wireframe` has UV lines on all visible surfaces;
  - `combined` has shaded faces and UV lines;
  - `CFD360 mesh` has mesh edges for all visible manufactured/review surfaces.

## Self-Review

- Spec coverage: viewer modes, backend metadata, all-surface mesh, five-preset catalog, zero splitter, parameter ownership, tests, and evidence are each mapped to a task.
- Placeholder scan: no incomplete markers, deferred-work phrases, or undefined task references.
- Type consistency: planned names are stable across tasks: `geometry_patch_version`, `mesh_strategy`, `viewerLayerVisibility`, `editableParameterIdsForPreset`, `feature_id`, `cfd_role`, `viewer_surface_role`, and `v1_1_1_all_surface_mesh`.
