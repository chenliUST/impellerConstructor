import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  attachmentReportRows,
  auditArtifactUrls,
  comparisonViewportRects,
  defaultStepOverlayVisibility,
  heatmapLegend,
  inspectionPolylinePoints,
  heatmapTriangleSelection,
  reportSummaryRows,
  semanticRegionOptions,
  selectedInspectionProvenance,
  stepInspectionModel,
  unsupportedSourceFeatures,
} from "./stepReconstructionModel.js";

describe("STEP reconstruction model", () => {
  test("exposes comparison phase and scoped unsupported source faces", () => {
    const manifest = task8Manifest("open");
    manifest.comparison_alignment = { rotation_about_axis_deg: -10.625 };
    manifest.reconstruction = {
      reconstruction_variant: "v1.1.6_adaptive_review_extension_r1",
    };
    manifest.comparison_scope = {
      excluded_surfaces: [{
        source_face_id: "source-face-9",
        semantic_role: "source_material_boundary",
        reason: "unsupported_spline_or_keyway",
      }],
    };

    assert.equal(stepInspectionModel(manifest).comparisonPhaseDeg, -10.625);
    assert.equal(
      stepInspectionModel(manifest).reconstructionVariant,
      "v1.1.6_adaptive_review_extension_r1",
    );
    assert.deepEqual(
      unsupportedSourceFeatures(manifest).map((record) => record.source_face_id),
      ["source-face-9"],
    );
  });

  test("binds declared R8 Geometric Manifest and preserves legacy STL fallback", () => {
    const urls = auditArtifactUrls("http://127.0.0.1:8061/", "step-audit-abc", {
      artifacts: { geometric_manifest: { file_name: "geometric-manifest.json" } },
    });
    assert.equal(urls.geometricManifest, "http://127.0.0.1:8061/api/step-reconstruction-audits/step-audit-abc/artifacts/geometric-manifest.json");
    assert.equal(
      auditArtifactUrls("http://127.0.0.1:8061/", "legacy-audit").geometricManifest,
      undefined,
    );
    assert.deepEqual(heatmapLegend({ comparison: { reconstruction_to_corresponding_source: { minimum_mm: 0.1, median_mm: 0.2, p95_mm: 0.3, maximum_mm: 0.4 } } }), [
      { label: "Triangle-centroid min", value: 0.1 },
      { label: "Triangle-centroid median", value: 0.2 },
      { label: "Triangle-centroid P95", value: 0.3 },
      { label: "Triangle-centroid max", value: 0.4 },
    ]);
    assert.deepEqual(
      heatmapLegend({ comparison: { bidirectional: { minimum_mm: 99 } } }),
      [],
    );
  });

  test("normalizes object-valued R8 comparison regions and never selects zero triangles", () => {
    const options = semanticRegionOptions({
      comparison: {
        regions: {
          blade_sides: { reconstruction_triangle_count: 2 },
          blade_root_attachment: { reconstruction_triangle_count: 1 },
        },
      },
    });
    assert.deepEqual(options.map((option) => option.id), [
      "all",
      "blade_sides",
      "blade_root_attachment",
    ]);
    const selection = heatmapTriangleSelection(
      {
        triangles: [[0, 1, 2]],
        triangle_regions: ["blade_sides"],
      },
      "blade_root_attachment",
      ["blade_root_attachment"],
    );
    assert.equal(selection.mode, "evidence-only");
    assert.deepEqual(selection.indexes, [0]);
  });

  test("keeps the three renderer viewports in a stable comparison grid", () => {
    assert.deepEqual(comparisonViewportRects(1001, 801), {
      source: { x: 0, y: 400, width: 500, height: 401 },
      reconstruction: { x: 500, y: 400, width: 501, height: 401 },
      heatmap: { x: 0, y: 0, width: 500, height: 400 },
    });
  });

  test("normalizes the Task8 open contract without discarding station or representative geometry", () => {
    const model = stepInspectionModel(task8Manifest("open"), { populationId: "main", spanStationId: "0.5" });
    assert.equal(model.topology, "open");
    assert.equal(model.hasMaterialShroud, false);
    assert.equal(defaultStepOverlayVisibility.openTipReference, false);
    assert.equal(defaultStepOverlayVisibility.spanSurfaces, false);
    assert.deepEqual(model.supportGeometry.openTip.control_points_rz_mm, tipControls());
    assert.deepEqual(model.stations[1].support_profile_rz_mm, [[20, 2], [25, 6], [31, 10]]);
    assert.equal(model.representative.source_component_id, "main-component-03");
    assert.equal(model.representative.section_loops.length, 2);
    assert.deepEqual(model.populations.map((population) => population.id), ["main", "splitter"]);
    assert.deepEqual(inspectionPolylinePoints(model.selectedLoop), [[10, 0, 4], [11, 0, 4]]);
    assert.deepEqual(selectedInspectionProvenance(model).source_face_ids, ["face-loop-mid", "face-map-mid"]);
  });

  test("uses authoritative nested closed topology and both material profile fits", () => {
    const manifest = task8Manifest("closed");
    manifest.semantics.shroud_topology = "open";
    const model = stepInspectionModel(manifest);
    assert.equal(model.topology, "closed");
    assert.equal(model.hasMaterialShroud, true);
    assert.equal(model.supportGeometry.openTip, null);
    assert.deepEqual(model.supportGeometry.closedShroud.map((profile) => profile.control_points_rz_mm), [tipControls(), outerControls()]);
  });

  test("reports root attachment dimensions, residual gate, promotability and provenance", () => {
    const [root] = attachmentReportRows(task8Manifest("open"));
    assert.equal(root.measured_lift_mm, 1.5);
    assert.equal(root.fitted_lift_mm, 1.48);
    assert.equal(root.measured_width_mm, 3.5);
    assert.equal(root.fitted_width_mm, 3.42);
    assert.equal(root.maximum_relative_residual, 0.022857);
    assert.equal(root.status, "PASS");
    assert.equal(root.promotable, true);
    assert.deepEqual(root.source_ids, ["edge-footprint-root", "face-hub", "face-root"]);
    assert.equal(root.method, "source_median_attachment_fit");
    assert.equal(root.coordinate_frame, "canonical_axis_frame_xyz_mm");
  });

  test("does not report unknown exact collision state as periodic PASS", () => {
    const manifest = task8Manifest("open");
    manifest.parameter_mapping.periodic_provenance.collision_status = "UNKNOWN";
    manifest.parameter_mapping.periodic_provenance.collision_free = null;
    const row = reportSummaryRows(manifest, stepInspectionModel(manifest)).find(
      (candidate) => candidate.id === "periodic_provenance",
    );
    assert.equal(row.value, "TOPOLOGY PASS / COLLISION UNKNOWN");
  });

  test("separates audit completion from global reconstruction acceptance", () => {
    const manifest = task8Manifest("open");
    manifest.status = "PASS";
    manifest.axis_first_algorithm_status = "REJECTED";
    manifest.reconstruction_disposition = "review_only_not_promotable";
    manifest.promotable = false;
    manifest.acceptance_evaluation = {
      status: "REJECTED",
      contract: "ks007g23b_axis_first_acceptance_v1",
    };

    const rows = Object.fromEntries(
      reportSummaryRows(manifest, stepInspectionModel(manifest)).map((row) => [row.id, row.value]),
    );
    assert.equal(rows.audit_process, "PASS");
    assert.equal(rows.algorithm_status, "REJECTED");
    assert.equal(rows.reconstruction_disposition, "review_only_not_promotable");
    assert.equal(rows.global_promotability, "NOT PROMOTABLE");
    assert.equal(rows.acceptance_status, "REJECTED / ks007g23b_axis_first_acceptance_v1");
  });

  test("does not substitute a different loop when the requested station is absent", () => {
    const model = stepInspectionModel(task8Manifest("open"), { populationId: "main", spanStationId: "missing-station" });
    assert.equal(model.selectedLoop, null);
    assert.equal(model.spanStationId, "missing-station");
    assert.equal(model.selectionEvidence.state, "unavailable");
    assert.match(model.selectionEvidence.message, /no fallback loop/i);
  });

  test("keeps stale and incomplete manifests inspectable", () => {
    const model = stepInspectionModel({ parameter_mapping: { source_section_loops: { stale: true } } });
    assert.equal(model.selectedLoop, null);
    assert.doesNotThrow(() => stepInspectionModel(null));
  });

  test("never substitutes legacy topology when current support evidence is incomplete", () => {
    const manifest = task8Manifest("open");
    manifest.parameter_mapping.support_recovery = { status: "INCOMPLETE" };
    manifest.semantics.shroud_topology = "closed";
    manifest.axis_first_section_reconstruction = {
      support_recovery: { topology: { decision: "closed", mode: "closed" } },
    };

    const model = stepInspectionModel(manifest);
    assert.equal(model.topology, "undetermined");
    assert.equal(model.hasMaterialShroud, false);
    assert.equal(model.supportGeometry.closedShroud.length, 0);
  });

  test("requires passing topology evidence before treating a shroud as material", () => {
    const manifest = task8Manifest("closed");
    manifest.parameter_mapping.support_recovery.status = "INCOMPLETE";

    const model = stepInspectionModel(manifest);
    assert.equal(model.topology, "undetermined");
    assert.equal(model.hasMaterialShroud, false);
  });

  test("rejects a closed topology_mode without an explicit passing topology record", () => {
    const manifest = task8Manifest("closed");
    delete manifest.parameter_mapping.support_recovery.topology;
    manifest.parameter_mapping.support_recovery.topology_mode = "closed";

    const model = stepInspectionModel(manifest);
    assert.equal(model.topology, "undetermined");
    assert.equal(model.hasMaterialShroud, false);
    assert.equal(model.supportGeometry.closedShroud.length, 0);
  });
});

function task8Manifest(mode) {
  const closed = mode === "closed";
  const tip = closed ? {
    semantic_role: "closed_shroud", material: true,
    inner_flowpath: { source_face_ids: ["face-shroud-inner"], profile_fit: profileFit(tipControls(), "face-shroud-inner") },
    outer_material: { source_face_ids: ["face-shroud-outer"], profile_fit: profileFit(outerControls(), "face-shroud-outer") },
    thickness: { finite_positive: true, samples_mm: [2.0, 2.1] },
  } : {
    semantic_role: "open_tip_reference", material: false, render_default: "hidden", export_default: "excluded",
    display_policy: { construction_overlay_only: true, material_style_forbidden: true },
    source_tip_caps: { source_face_ids: ["face-tip-01", "face-tip-02"] },
    profile_fit: profileFit(tipControls(), "edge-open-tip"),
  };
  return {
    audit_id: `audit-task8-${mode}`,
    canonical_geometry_version: "1.1.2",
    source: { solid_count: 1, face_count: 240, edge_count: 612 },
    frame: { axis: { origin_mm: [0, 0, 0], direction: [0, 0, 1] } },
    semantics: { main_blade_count: 13, splitter_blade_count: 13, shroud_topology: closed ? "closed" : "open" },
    parameter_mapping: {
      support_recovery: {
        status: "PASS",
        topology: { status: "PASS", decision: mode, mode, material_shroud: closed ? tip : null },
        topology_mode: mode,
        hub_profile: profileFit(hubControls(), "face-hub"),
        tip_reference_or_shroud: tip,
      },
      periodic_provenance: {
        status: "PASS", closure_pass: true, collision_free: true, phase_consistent: true,
        main: { count: 13, pitch_deg: 27.692307, phase_deg: 0, representative_instance: { source_component_id: "main-component-03", instance_id: "main-03", source_face_ids: ["face-main-a", "face-main-b"] } },
        splitter: { count: 13, pitch_deg: 27.692307, phase_deg: 13.846154, representative_instance: { source_component_id: "splitter-component-09", instance_id: "splitter-09", source_face_ids: ["face-split-a", "face-split-b"] } },
      },
      source_section_loops: [
        sectionLoop("main", 0, "main-root", [[9, 0, 0], [10, 0, 0]], [[18, 1], [23, 5], [29, 9]], "face-loop-root"),
        sectionLoop("main", 0.5, "main-mid", [[10, 0, 4], [11, 0, 4]], [[20, 2], [25, 6], [31, 10]], "face-loop-mid"),
        sectionLoop("splitter", 0.5, "splitter-mid", [[15, 0, 4], [16, 0, 4]], [[21, 2], [26, 6], [32, 10]], "face-loop-splitter"),
      ],
      measurement_bundle: { attachments: { root: { lift_samples_mm: [1.4, 1.5, 1.6], width_samples_mm: [3.4, 3.5, 3.6], source_ids: ["face-root", "edge-footprint-root"], source_measurement: true, promotable: true, material_side: 1 } } },
      promotion: { promotable: true, policy: "specification_values_are_promotion_maxima" },
      objective_terms: {
        normal_thickness: promotionTerm("normal_thickness", [{ family: "main", h: 0.5, loop_id: "main-mid", fitted: 1.3, residual: 0.02, source_ids: ["face-map-mid"] }]),
        attachment: {
          ...promotionTerm("attachment", [{ attachment: "root", target_lift_mm: 1.5, fitted_lift_mm: 1.48, target_width_mm: 3.5, fitted_width_mm: 3.42, lift_relative: 0.013333, width_relative: 0.022857, status: "PASS", source_ids: ["face-root", "face-hub", "edge-footprint-root"] }]),
          residual: { maximum_relative: 0.022857 }, gate: { relative_limit: 0.1, status: "PASS" },
        },
      },
    },
  };
}

function sectionLoop(population, h, loopId, points, supportProfile, sourceFaceId) {
  return { population, h, support_span_h: h, loop_id: loopId, support_profile_rz_mm: supportProfile, source_face_ids: [sourceFaceId], exact_section: { accepted_loop: { points_xyz_mm: points } } };
}
function promotionTerm(role, records) {
  return { role, method: "source_median_attachment_fit", frame: { coordinate_system: "canonical_axis_frame_xyz_mm" }, units: { target: "mm", fitted: "mm", residual: "relative" }, provenance: { algorithm: "axis_first_measurement_bundle_task8_r2" }, source_ids: records.flatMap((record) => record.source_ids), records };
}
function profileFit(controlPoints, sourceId) { return { control_points_rz_mm: controlPoints, residuals: { orthogonal_rms_mm: 0.02 }, pipeline_authenticated_occt_support: { source_face_id: sourceId } }; }
function hubControls() { return [[12, 30], [15, 25], [20, 18], [30, 8], [42, 2], [51.5, 0]]; }
function tipControls() { return [[20, 35], [23, 30], [29, 24], [38, 16], [47, 10], [52, 7]]; }
function outerControls() { return [[22, 37], [25, 32], [31, 26], [40, 18], [49, 12], [54, 9]]; }
