import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildInstantiatePayload,
  buildSynthesizePayload,
  exportFilename,
  exportFileOptions,
  exportUrl,
  hiddenParameterIdsForPreset,
  overridesAfterParameterChange,
  parameterGroups,
  parameterSchema,
  parameterSchemaForPreset,
  presets,
} from "./appModel.js";

function maxAbsCurveValue(curve) {
  return Math.max(...curve.control_points.map((point) => Math.abs(point[1])));
}

function supportOffsetEnvelope(parameters, sweepName) {
  const radialSpan = Math.max(1, Math.abs(parameters.exit_radius_mm - parameters.inlet_radius_mm));
  const scalarOffset = Math.abs(parameters[sweepName]) / (2 * radialSpan);
  return scalarOffset === 0 ? 0 : Math.min(0.121, scalarOffset * 1.65);
}

describe("impeller frontend model", () => {
  test("presets expose bounded impeller parameters", () => {
    assert.ok(presets.length >= 2);

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
    const nasaStage37 = "public-nasa-stage37-stator-ring";

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
    assert.deepEqual(Object.keys(parameterSchemaForPreset(nasaStage37)), [
      "mounting_bore_radius_mm",
      "blade_thickness_mm",
      "blade_wrap_deg",
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

  test("v1.1.1 closed preset sends the closed shroud material-domain profiles", () => {
    const closed = presets.find((preset) => preset.id === "axisymmetric-nurbs-closed-throughflow");

    assert.deepEqual(closed.profileOverrides.hub_profile.control_points, [
      [180, 300], [210, 220], [270, 145], [380, 75], [500, 24], [610, 0],
    ]);
    assert.deepEqual(closed.profileOverrides.tip_or_shroud_profile.control_points, [
      [260, 306], [290, 240], [350, 165], [450, 95], [540, 50], [615, 34],
    ]);
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

  test("buildSynthesizePayload omits display-only public preset facets outside the v1.1 slice", () => {
    const publicPresets = presets.filter((preset) => preset.tags.includes("public-data"));

    assert.ok(publicPresets.length > 0);
    for (const preset of publicPresets) {
      const payload = buildSynthesizePayload(preset);

      assert.equal(payload.part_family_id, "impeller");
      assert.equal(payload.preset_id, preset.presetId);
      assert.deepEqual(payload.facets, {});
    }
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
      "leading_edge_radius_mm",
      "trailing_edge_radius_mm",
      "tip_edge_radius_mm",
      "hub_wall_thickness_mm",
      "hub_bottom_thickness_mm",
      "hub_top_cap_thickness_mm",
      "hub_chamfer_radius_mm",
      "hood_wall_thickness_mm",
      "hood_chamfer_radius_mm",
    ]);
  });

  test("buildInstantiatePayload serializes section-loop overrides separately from curve overrides", () => {
    const sectionLoopOverrides = {
      blade_section_loop_template: {
        construction: "s_camber_normal_offset_c2_loop",
        stations: [
          { eta: 0, s_camber_amplitude_mm: 32, max_thickness_mm: 40 },
          { eta: 0.5, s_camber_amplitude_mm: 28, max_thickness_mm: 36 },
          { eta: 1, s_camber_amplitude_mm: 22, max_thickness_mm: 32 },
        ],
      },
    };

    const payload = buildInstantiatePayload(
      presets[0].parameters,
      null,
      { blade_mean: { theta_center_u_curve: { control_points: [[0, 0], [1, -120]] } } },
      null,
      "edge_closures",
      sectionLoopOverrides,
    );

    assert.deepEqual(payload.section_loop_overrides, sectionLoopOverrides);
    assert.equal(payload.curve_overrides.blade_mean.theta_center_u_curve.control_points.length, 2);
  });

  test("buildInstantiatePayload keeps blade-to-blade overrides separate from section-loop overrides", () => {
    const sectionLoopOverrides = { legacy: true };
    const bladeToBladeLoopFamilyOverrides = { main: { station_count: 5 } };

    const payload = buildInstantiatePayload(
      presets[0].parameters,
      null,
      null,
      null,
      "full",
      sectionLoopOverrides,
      bladeToBladeLoopFamilyOverrides,
    );

    assert.deepEqual(payload.blade_to_blade_loop_family_overrides, bladeToBladeLoopFamilyOverrides);
    assert.deepEqual(payload.section_loop_overrides, sectionLoopOverrides);
  });

  test("buildInstantiatePayload omits empty blade-to-blade overrides", () => {
    const payload = buildInstantiatePayload(
      presets[0].parameters,
      null,
      null,
      null,
      "full",
      null,
      {},
    );

    assert.equal("blade_to_blade_loop_family_overrides" in payload, false);
  });

  test("first UI preset advertises active v1.1.1 geometry contract", () => {
    assert.equal(presets[0].presetId, "radial_open_reference_v1_1");
    assert.equal(presets[0].geometryPatchVersion, "1.1.1");
    assert.match(presets[0].name, /v1\.1/);
    assert.equal(
      presets[0].metadata.transitionGeometryStatus,
      "topology_first_blade_to_blade_5_loop_surface_family_graph",
    );
  });

  test("curve-owned values are not duplicated as scalar controls for v1.1.1 open preset", () => {
    const hidden = hiddenParameterIdsForPreset("radial_open_reference_v1_1");

    assert.ok(hidden.includes("root_fillet_radius_mm"));
    assert.ok(hidden.includes("leading_edge_radius_mm"));
    assert.ok(hidden.includes("trailing_edge_radius_mm"));
    assert.ok(hidden.includes("tip_edge_radius_mm"));
    assert.ok(hidden.includes("inlet_blade_height_mm"));
    assert.ok(hidden.includes("outlet_blade_height_mm"));
    assert.ok(hidden.includes("hub_curve_height_mm"));
    assert.equal(hidden.includes("blade_thickness_mm"), false);
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

  test("parameter schema keeps interactive fillet and edge radius definitions available", () => {
    assert.equal(parameterSchema.root_fillet_radius_mm.group, "edge_treatment");
    assert.equal(parameterSchema.leading_edge_radius_mm.group, "edge_treatment");
    assert.equal(parameterSchema.trailing_edge_radius_mm.group, "edge_treatment");
    assert.equal(parameterSchema.tip_edge_radius_mm.group, "edge_treatment");

    const payload = buildInstantiatePayload({
      root_fillet_radius_mm: 10,
      leading_edge_radius_mm: 4,
      trailing_edge_radius_mm: 2.5,
      tip_edge_radius_mm: 2,
    });

    assert.equal(payload.parameters.root_fillet_radius_mm, 10);
    assert.equal(payload.parameters.leading_edge_radius_mm, 4);
    assert.equal(payload.parameters.trailing_edge_radius_mm, 2.5);
    assert.equal(payload.parameters.tip_edge_radius_mm, 2);
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

  test("buildInstantiatePayload serializes profile curve transition overrides and generation stage", () => {
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
    const transitionOverrides = {
      "blade_root_to_hub.default": {
        treatment: "chamfer",
        radius_mm: 6,
      },
    };

    const payload = buildInstantiatePayload(
      presets[0].parameters,
      profileOverrides,
      curveOverrides,
      transitionOverrides,
      "blade_surfaces",
    );

    assert.equal(payload.geometry_stage, "blade_surfaces");
    assert.deepEqual(payload.profile_overrides, profileOverrides);
    assert.deepEqual(payload.curve_overrides, curveOverrides);
    assert.deepEqual(payload.transition_overrides, transitionOverrides);
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
    assert.deepEqual(exportFileOptions.map((option) => option.id), ["step", "stl", "mesh_step", "obj", "manifest"]);
    assert.equal(exportFileOptions.find((option) => option.id === "step").label, "STEP B-Rep");
    assert.equal(exportFileOptions.find((option) => option.id === "mesh_step").extension, ".mesh.step");
    assert.equal(exportFileOptions.find((option) => option.id === "obj").extension, ".obj");
  });

  test("exportFilename uses preset run id and correct extension", () => {
    assert.equal(exportFilename("radial_open_reference_v0_9", "run-abc", "step"), "radial_open_reference_v0_9_run-abc.step");
    assert.equal(exportFilename("radial_open_reference_v0_9", "run-abc", "mesh_step"), "radial_open_reference_v0_9_run-abc.mesh.step");
    assert.equal(exportFilename("radial_open_reference_v0_9", "run-abc", "obj"), "radial_open_reference_v0_9_run-abc.obj");
    assert.equal(exportFilename("radial_open_reference_v0_9", "run-abc", "manifest"), "radial_open_reference_v0_9_run-abc.manifest.json");
  });
});
