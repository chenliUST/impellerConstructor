import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildInstantiatePayload,
  buildSynthesizePayload,
  exportUrl,
  facetSchema,
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
      "blade_wrap_deg",
      "blade_lean_deg",
      "blade_thickness_mm",
    ]);
  });

  test("presets include focused open and closed NURBS throughflow studies", () => {
    const open = presets.find((preset) => preset.presetId === "axisymmetric_nurbs_open_throughflow_study");
    const closed = presets.find((preset) => preset.presetId === "axisymmetric_nurbs_closed_throughflow_study");

    assert.ok(open);
    assert.ok(closed);
    assert.equal(open.facets.shroud_topology, "open");
    assert.equal(closed.facets.shroud_topology, "closed");
    assert.equal(open.facets.passage_topology, "throughflow_bladed_channel");
    assert.equal(closed.facets.passage_topology, "throughflow_bladed_channel");
    assert.ok(open.parameters.blade_wrap_deg > 0);
    assert.ok(closed.parameters.blade_wrap_deg > 0);
  });

  test("exportUrl builds API export paths", () => {
    assert.equal(
      exportUrl("http://127.0.0.1:8000", "run-abc", "stl"),
      "http://127.0.0.1:8000/api/model-runs/run-abc/exports/stl",
    );
  });
});
