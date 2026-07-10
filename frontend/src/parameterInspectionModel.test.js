import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { presets } from "./appModel.js";
import {
  ANNOTATION_LEVELS,
  INSPECTION_TABS,
  annotationsForView,
  defaultInspectionSelection,
  mergeInspectionSelection,
  resolveParameterInspection,
  sectionLoopForSelection,
} from "./parameterInspectionModel.js";

function manifestFixture() {
  const contract = {
    contract_version: "1.1.3",
    generation_id: "g1",
    source_geometry_patch_version: "1.1.2",
    source_canonical_payload_version: "1.1.2",
    blade_instances: {
      blade_0: {
        blade_instance_id: "blade_0",
        surface_ids: ["blade_0_pressure_surface", "blade_0_suction_surface"],
        span_station_ids: ["blade_0:span_0"],
      },
    },
    surface_references: {
      blade_0_pressure_surface: {
        surface_id: "blade_0_pressure_surface",
        blade_instance_id: "blade_0",
        face_family: "blade_pressure",
      },
      blade_0_suction_surface: {
        surface_id: "blade_0_suction_surface",
        blade_instance_id: "blade_0",
        face_family: "blade_suction",
      },
    },
    span_stations: {
      "blade_0:span_0": { span_station_id: "blade_0:span_0", section_loop_id: "blade_0:span_0:loop", h: 0.1 },
    },
    section_loops: {
      "blade_0:span_0:loop": {
        section_loop_id: "blade_0:span_0:loop",
        span_station_id: "blade_0:span_0",
        segment_references: {
          pressure_side: { points_s_q: [[0, -1], [1, -1]], control_points_s_q: [[0, -1], [1, -1]] },
          trailing_edge: {
            points_s_q: [[1, -1], [1.1, 0], [1, 1]],
            control_points_s_q: [[1, -1], [1.1, 0], [1, 1]],
          },
          suction_side: { points_s_q: [[1, 1], [0, 1]], control_points_s_q: [[1, 1], [0, 1]] },
          leading_edge: {
            points_s_q: [[0, 1], [-0.1, 0], [0, -1]],
            control_points_s_q: [[0, 1], [-0.1, 0], [0, -1]],
          },
        },
        metrics: { join_status: "PASS" },
        join_metrics: { pressure_to_leading: { status: "PASS", position_gap_mm: 0 } },
      },
    },
    support_profiles: {},
    resolved_dimensions: {
      thickness_min_mm: { requested_value: 6.8, resolved_value: 6.8, unit: "mm", requested_unit: "mm" },
      thickness_max_mm: { requested_value: 18, resolved_value: 18, unit: "mm", requested_unit: "mm" },
    },
  };
  return {
    runtime_release_version: "1.1.3",
    generation_id: "g1",
    parameter_inspection: contract,
    geometry: {
      surface_graph: {
        generation_id: "g1",
        surfaces: [
          { id: "blade_0_pressure_surface", uv_grid: [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]] },
          { id: "blade_0_suction_surface", uv_grid: [[[0, 0, 1], [1, 0, 1]], [[0, 1, 1], [1, 1, 1]]] },
        ],
      },
    },
  };
}

describe("parameter inspection model", () => {
  test("declares the five approved tabs and three annotation levels", () => {
    assert.deepEqual(INSPECTION_TABS.map((tab) => tab.id), ["3d", "top", "meridional", "s_q", "quad"]);
    assert.deepEqual(ANNOTATION_LEVELS, ["key", "selected", "all"]);
  });

  test("resolves one matched manifest and rejects stale evidence", () => {
    assert.equal(resolveParameterInspection(manifestFixture()).status, "ready");
    const stale = manifestFixture();
    stale.geometry.surface_graph.generation_id = "g2";
    assert.equal(resolveParameterInspection(stale).errorCode, "parameter_inspection_generation_id_mismatch");
    const missingSurface = manifestFixture();
    missingSurface.geometry.surface_graph.surfaces = [];
    assert.equal(resolveParameterInspection(missingSurface).errorCode, "parameter_inspection_surface_reference_missing");
  });

  test("selects the first blade and station without mutation", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    const updated = mergeInspectionSelection(selection, { surfaceId: "blade_0_pressure_surface" });
    assert.equal(selection.surfaceId, null);
    assert.equal(updated.surfaceId, "blade_0_pressure_surface");
    assert.equal(sectionLoopForSelection(model, updated).section_loop_id, "blade_0:span_0:loop");
  });

  test("filters annotation levels deterministically", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    assert.ok(annotationsForView(model, "s_q", "key", selection).length > 0);
    assert.ok(annotationsForView(model, "s_q", "all", selection).length >= annotationsForView(model, "s_q", "key", selection).length);
  });

  test("selected surface excludes sibling surfaces on the same blade", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = mergeInspectionSelection(defaultInspectionSelection(model), {
      surfaceId: "blade_0_pressure_surface",
    });

    assert.deepEqual(
      annotationsForView(model, "3d", "selected", selection).map((annotation) => annotation.id),
      ["3d:blade_0_pressure_surface"],
    );
  });

  test("selected section segment excludes siblings while retaining key annotations", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = mergeInspectionSelection(defaultInspectionSelection(model), {
      sectionSegmentId: "pressure_side",
    });

    assert.deepEqual(
      annotationsForView(model, "s_q", "selected", selection).map((annotation) => annotation.id),
      [
        "s_q:thickness_min_mm",
        "s_q:thickness_max_mm",
        "s_q:blade_0:span_0:loop:pressure_side",
      ],
    );
  });

  test("blade-only selection expands to all annotations on the blade", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = {
      bladeId: "blade_0",
      surfaceId: null,
      spanStationId: null,
      sectionSegmentId: null,
      controlPointId: null,
    };

    assert.deepEqual(
      annotationsForView(model, "3d", "selected", selection).map((annotation) => annotation.id),
      ["3d:blade_0_pressure_surface", "3d:blade_0_suction_surface"],
    );
  });

  test("default selection keeps blade-linked 3D and Top annotations visible", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    assert.equal(selection.spanStationId, "blade_0:span_0");

    for (const viewId of ["3d", "top"]) {
      assert.deepEqual(
        annotationsForView(model, viewId, "selected", selection).map((annotation) => annotation.id),
        [`${viewId}:blade_0_pressure_surface`, `${viewId}:blade_0_suction_surface`],
      );
    }
  });

  test("active display names identify v1.1.3 while backend preset ids remain stable", () => {
    for (const preset of presets) {
      assert.match(preset.name, /v1\.1\.3/i);
      assert.match(preset.summary, /V1\.1\.3/);
      assert.ok(preset.tags.includes("v1.1.3"));
      assert.match(preset.presetId, /_v1_1$/);
    }
  });
});
