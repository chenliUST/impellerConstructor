import assert from "node:assert/strict";
import { describe, test } from "node:test";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { JSDOM } from "jsdom";

import { StepReconstructionWorkspace } from "./StepReconstructionWorkspace.js";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("STEP reconstruction workspace", () => {
  test("renders incomplete evidence without a white screen and exposes unavailable station evidence", async () => {
    await withDom(async (container) => {
      const stale = { ...manifest(), parameter_mapping: { source_section_loops: [] } };
      const root = createRoot(container);
      await act(async () => root.render(React.createElement(StepReconstructionWorkspace, {
        apiBase: "http://example.test", initialManifest: stale, SceneComponent: () => React.createElement("div", null, "mocked scene"),
      })));
      assert.match(container.textContent, /Parameter & deviation report/);
      assert.match(container.textContent, /No exact source-section station is available/);
      await act(async () => root.unmount());
    });
  });

  test("renders exact-loop provenance and never masks it with a fallback", async () => {
    await withDom(async (container) => {
      const root = createRoot(container);
      await act(async () => root.render(React.createElement(StepReconstructionWorkspace, {
        apiBase: "http://example.test", initialManifest: manifest(), SceneComponent: () => React.createElement("div", null, "mocked scene"),
      })));
      assert.match(container.textContent, /main-component/);
      assert.match(container.textContent, /face-loop-root/);
      assert.match(container.textContent, /Periodic provenance/);
      assert.match(container.textContent, /Root attachment mapping/);
      assert.match(container.textContent, /1\.500 source \/ 1\.480 fitted mm/);
      assert.match(container.textContent, /Promotable/);
      assert.match(container.textContent, /edge-footprint-root/);
      assert.match(container.textContent, /source_median_attachment_fit \/ canonical_axis_frame_xyz_mm/);
      await act(async () => root.unmount());
    });
  });
});

async function withDom(run) {
  const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", { url: "http://example.test" });
  const previous = { window: globalThis.window, document: globalThis.document };
  Object.assign(globalThis, { window: dom.window, document: dom.window.document });
  try { await run(dom.window.document.getElementById("root")); } finally { Object.assign(globalThis, previous); dom.window.close(); }
}

function manifest() {
  const profileFit = (points, sourceId) => ({ control_points_rz_mm: points, residuals: { orthogonal_rms_mm: 0.02 }, pipeline_authenticated_occt_support: { source_face_id: sourceId } });
  return {
    audit_id: "task8-open-workspace",
    canonical_geometry_version: "1.1.2",
    semantics: { main_blade_count: 13, shroud_topology: "open" },
    source: { solid_count: 1, face_count: 20, edge_count: 40 },
    frame: { axis: { origin_mm: [0, 0, 0], direction: [0, 0, 1] } },
    parameter_mapping: {
      support_recovery: {
        status: "PASS", topology: { status: "PASS", decision: "open", mode: "open", material_shroud: null }, topology_mode: "open",
        hub_profile: profileFit([[12, 30], [15, 25], [20, 18], [30, 8], [42, 2], [51.5, 0]], "face-hub"),
        tip_reference_or_shroud: { semantic_role: "open_tip_reference", material: false, render_default: "hidden", export_default: "excluded", display_policy: { construction_overlay_only: true, material_style_forbidden: true }, profile_fit: profileFit([[20, 35], [23, 30], [29, 24], [38, 16], [47, 10], [52, 7]], "edge-open-tip") },
      },
      periodic_provenance: { status: "PASS", closure_pass: true, collision_free: true, phase_consistent: true, main: { count: 13, pitch_deg: 27.692307, representative_instance: { source_component_id: "main-component", instance_id: "main-03", source_face_ids: ["face-main-a", "face-main-b"] } }, splitter: null },
      source_section_loops: [{ population: "main", h: 0, loop_id: "main-root", support_profile_rz_mm: [[18, 1], [24, 6], [31, 10]], source_face_ids: ["face-loop-root"], exact_section: { accepted_loop: { points_xyz_mm: [[0, 0, 0], [1, 0, 0]] } } }],
      measurement_bundle: { attachments: { root: { lift_samples_mm: [1.4, 1.5, 1.6], width_samples_mm: [3.4, 3.5, 3.6], source_ids: ["face-root", "edge-footprint-root"], source_measurement: true, promotable: true, material_side: 1 } } },
      promotion: { promotable: true },
      objective_terms: { attachment: { method: "source_median_attachment_fit", frame: { coordinate_system: "canonical_axis_frame_xyz_mm" }, provenance: { algorithm: "axis_first_measurement_bundle_task8_r2" }, source_ids: ["face-root", "edge-footprint-root"], residual: { maximum_relative: 0.022857 }, gate: { status: "PASS" }, records: [{ attachment: "root", target_lift_mm: 1.5, fitted_lift_mm: 1.48, target_width_mm: 3.5, fitted_width_mm: 3.42, lift_relative: 0.013333, width_relative: 0.022857, status: "PASS", source_ids: ["face-root", "edge-footprint-root"] }] } },
    },
  };
}
