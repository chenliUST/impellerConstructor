import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildInstantiatePayload,
  buildSynthesizePayload,
  exportFilename,
  exportFileOptions,
  exportUrl,
  facetSchema,
  overridesAfterParameterChange,
  parameterGroups,
  parameterSchema,
  presets,
} from "./appModel.js";

describe("impeller frontend model", () => {
  test("presets expose bounded impeller parameters", () => {
    assert.equal(presets.length, 2);

    for (const preset of presets) {
      const payload = buildInstantiatePayload(preset.parameters);

      assert.equal(preset.partFamilyId, "impeller");
      assert.ok(preset.presetId);
      assert.ok(preset.facets.flow_topology);
      assert.ok(preset.facets.passage_topology);
      assert.ok(payload.parameters.exit_radius_mm > payload.parameters.inlet_radius_mm);
      assert.equal(Number.isFinite(payload.parameters.hub_curve_height_mm), true);
      assert.equal(Number.isFinite(payload.parameters.blade_wrap_deg), true);
    }
  });

  test("buildInstantiatePayload preserves direct numeric input without UI range clamping", () => {
    const payload = buildInstantiatePayload({
      blade_count: 99,
      inlet_radius_mm: 600,
      exit_radius_mm: 500,
      blade_wrap_deg: 999,
      hub_curve_height_mm: -20,
      mounting_bore_radius_mm: 999,
    });

    assert.equal(payload.parameters.blade_count, 99);
    assert.equal(payload.parameters.inlet_radius_mm, 600);
    assert.equal(payload.parameters.exit_radius_mm, 500);
    assert.equal(payload.parameters.blade_wrap_deg, 999);
    assert.equal(payload.parameters.hub_curve_height_mm, -20);
    assert.equal(payload.parameters.mounting_bore_radius_mm, 999);
  });

  test("buildSynthesizePayload sends ontology preset and facets", () => {
    const payload = buildSynthesizePayload(presets[0]);

    assert.equal(payload.part_family_id, "impeller");
    assert.equal(payload.preset_id, presets[0].presetId);
    assert.deepEqual(payload.facets, presets[0].facets);
  });

  test("facetSchema focuses the first workflow on open and closed throughflow NURBS impellers", () => {
    assert.deepEqual(facetSchema.flow_topology.values, ["axial", "mixed", "radial"]);
    assert.deepEqual(facetSchema.shroud_topology.values, ["open", "closed"]);
    assert.deepEqual(facetSchema.suction_topology.values, ["single_suction"]);
    assert.deepEqual(facetSchema.blade_exit_geometry.values, ["backward_curved"]);
    assert.deepEqual(facetSchema.passage_topology.values, ["throughflow_bladed_channel"]);
    assert.deepEqual(facetSchema.working_domain.values, ["pump"]);
  });

  test("parameterSchema only exposes key NURBS construction controls", () => {
    assert.deepEqual(Object.keys(parameterSchema), [
      "blade_count",
      "inlet_radius_mm",
      "exit_radius_mm",
      "inlet_blade_height_mm",
      "outlet_blade_height_mm",
      "hub_curve_height_mm",
      "mounting_bore_radius_mm",
      "hub_base_radius_mm",
      "hub_nose_radius_mm",
      "hub_profile_convexity",
      "blade_wrap_deg",
      "blade_lean_deg",
      "leading_edge_lean_deg",
      "trailing_edge_lean_deg",
      "leading_edge_sweep_mm",
      "trailing_edge_sweep_mm",
      "blade_thickness_mm",
      "root_fillet_radius_mm",
      "hub_wall_thickness_mm",
      "hub_bottom_thickness_mm",
      "hub_top_cap_thickness_mm",
      "hub_chamfer_radius_mm",
      "hood_wall_thickness_mm",
      "hood_chamfer_radius_mm",
    ]);
  });

  test("presets include focused open and closed NURBS throughflow studies", () => {
    const open = presets.find((preset) => preset.presetId === "radial_open_reference_v0_5");
    const closed = presets.find((preset) => preset.presetId === "radial_closed_reference_v0_5");

    assert.ok(open);
    assert.ok(closed);
    assert.equal(open.facets.shroud_topology, "open");
    assert.equal(closed.facets.shroud_topology, "closed");
    assert.equal(open.facets.passage_topology, "throughflow_bladed_channel");
    assert.equal(closed.facets.passage_topology, "throughflow_bladed_channel");
    assert.equal(open.parameters.blade_count, 12);
    assert.equal(closed.parameters.blade_count, 12);
    assert.equal(open.parameters.leading_edge_lean_deg, 0);
    assert.equal(open.parameters.trailing_edge_lean_deg, 0);
    assert.equal(open.parameters.leading_edge_sweep_mm, 0);
    assert.equal(open.parameters.trailing_edge_sweep_mm, 0);
    assert.equal(closed.parameters.leading_edge_lean_deg, 0);
    assert.equal(closed.parameters.trailing_edge_lean_deg, 0);
    assert.equal(closed.parameters.leading_edge_sweep_mm, 0);
    assert.equal(closed.parameters.trailing_edge_sweep_mm, 0);
    assert.ok(open.parameters.blade_wrap_deg > 0);
    assert.ok(closed.parameters.blade_wrap_deg > 0);
    assert.ok(open.parameters.hub_wall_thickness_mm > 0);
    assert.ok(closed.parameters.hood_wall_thickness_mm > 0);
  });

  test("declares parameter groups in display order", () => {
    assert.deepEqual(parameterGroups.map((group) => group.id), [
      "main_dimensions",
      "meridional_support",
      "shape_control",
      "blade_pattern",
      "blade_boundaries",
      "blade_surface",
      "blade_profile",
      "solid_material",
      "edge_treatment",
    ]);
  });

  test("exposes leading trailing controls and semantic shape handles", () => {
    assert.equal(parameterSchema.leading_edge_lean_deg.group, "blade_boundaries");
    assert.equal(parameterSchema.trailing_edge_lean_deg.group, "blade_boundaries");
    assert.equal(parameterSchema.leading_edge_sweep_mm.group, "blade_boundaries");
    assert.equal(parameterSchema.trailing_edge_sweep_mm.group, "blade_boundaries");
    assert.equal(parameterSchema.hub_base_radius_mm.group, "shape_control");
    assert.equal(parameterSchema.hub_nose_radius_mm.group, "shape_control");
    assert.equal(parameterSchema.hub_profile_convexity.group, "shape_control");
    assert.equal(parameterSchema.hub_base_radius_mm.controlKind, "semantic_handle");
  });

  test("buildInstantiatePayload preserves explicit boundary parameters", () => {
    const payload = buildInstantiatePayload({
      leading_edge_lean_deg: 15,
      trailing_edge_lean_deg: -10,
      leading_edge_sweep_mm: 25,
      trailing_edge_sweep_mm: -30,
    });

    assert.equal(payload.parameters.leading_edge_lean_deg, 15);
    assert.equal(payload.parameters.trailing_edge_lean_deg, -10);
    assert.equal(payload.parameters.leading_edge_sweep_mm, 25);
    assert.equal(payload.parameters.trailing_edge_sweep_mm, -30);
  });

  test("buildInstantiatePayload serializes profile curve overrides and generation stage", () => {
    const profileOverrides = {
      hub_profile: {
        kind: "nurbs_curve",
        degree: 3,
        coordinate_system: "rz_meridional_mm",
        control_points: [[120, 80], [260, 60], [460, 24], [570, 0]],
        weights: [1, 1, 1, 1],
        knots: [0, 0, 0, 0, 1, 1, 1, 1],
      },
    };
    const curveOverrides = {
      blade_mean: {
        theta_center_u_curve: {
          coordinate_system: "u_theta_deg",
          control_points: [[0, 0], [0.5, -60], [1, -118]],
        },
      },
    };

    const payload = buildInstantiatePayload(
      presets[0].parameters,
      profileOverrides,
      curveOverrides,
      "blade_surfaces",
    );

    assert.equal(payload.geometry_stage, "blade_surfaces");
    assert.deepEqual(payload.profile_overrides, profileOverrides);
    assert.deepEqual(payload.curve_overrides, curveOverrides);
  });

  test("changing hub profile driver clears stale profile overrides", () => {
    const profileOverrides = {
      hub_profile: { control_points: [[1, 1], [2, 2], [3, 3], [4, 4]] },
      tip_or_shroud_profile: { control_points: [[2, 3], [3, 4], [4, 5], [5, 6]] },
    };
    const curveOverrides = {
      blade_mean: {
        theta_center_u_curve: {
          coordinate_system: "u_theta_deg",
          control_points: [[0, 0], [1, -118]],
        },
      },
    };

    const next = overridesAfterParameterChange("hub_curve_height_mm", profileOverrides, curveOverrides);

    assert.equal(next.profileOverrides, null);
    assert.deepEqual(next.curveOverrides, curveOverrides);
  });

  test("changing blade curve driver clears stale curve overrides", () => {
    const profileOverrides = { hub_profile: { control_points: [] } };
    const curveOverrides = { thickness: { thickness_u_curve: { control_points: [[0, 18], [1, 9]] } } };

    const next = overridesAfterParameterChange("blade_wrap_deg", profileOverrides, curveOverrides);

    assert.deepEqual(next.profileOverrides, profileOverrides);
    assert.equal(next.curveOverrides, null);
  });

  test("exportUrl builds API export paths", () => {
    assert.equal(
      exportUrl("http://127.0.0.1:8000", "run-abc", "stl"),
      "http://127.0.0.1:8000/api/model-runs/run-abc/exports/stl",
    );
  });

  test("exportFileOptions exposes brep mesh and manifest downloads", () => {
    assert.deepEqual(exportFileOptions.map((option) => option.id), ["step", "stl", "mesh_step", "manifest"]);
    assert.equal(exportFileOptions.find((option) => option.id === "step").label, "STEP B-Rep");
    assert.equal(exportFileOptions.find((option) => option.id === "mesh_step").extension, ".mesh.step");
  });

  test("exportFilename uses preset run id and correct extension", () => {
    assert.equal(exportFilename("radial_open_reference_v0_6", "run-abc", "step"), "radial_open_reference_v0_6_run-abc.step");
    assert.equal(exportFilename("radial_open_reference_v0_6", "run-abc", "mesh_step"), "radial_open_reference_v0_6_run-abc.mesh.step");
    assert.equal(exportFilename("radial_open_reference_v0_6", "run-abc", "manifest"), "radial_open_reference_v0_6_run-abc.manifest.json");
  });
});
