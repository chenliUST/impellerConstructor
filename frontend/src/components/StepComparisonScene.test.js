import assert from "node:assert/strict";
import { describe, test } from "node:test";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { JSDOM } from "jsdom";
import * as THREE from "three";

import { StepComparisonScene } from "./StepComparisonScene.js";
import { stepInspectionModel } from "../stepReconstructionModel.js";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("STEP comparison scene", () => {
  test("uses one native-DPR renderer per comparison pane and releases all resources on unmount", async () => {
    await withScene(async ({ container, runtime }) => {
      const root = createRoot(container);
      await act(async () => root.render(sceneElement(runtime)));
      await flush();
      assert.equal(runtime.renderers.length, 3);
      assert.ok(runtime.renderers.every((renderer) => renderer.pixelRatio === 1));
      assert.equal(container.querySelectorAll("canvas").length, 3);
      await act(async () => root.unmount());
      assert.ok(runtime.renderers.every((renderer) => renderer.disposed && renderer.contextLost));
      assert.equal(runtime.controls[0].disposed, true);
      assert.equal(container.querySelectorAll("canvas").length, 0);
    });
  });

  test("frames source reconstruction and heatmap in separate canvases with synchronized cameras", async () => {
    await withScene(async ({ container, runtime }) => {
      const root = createRoot(container);
      await act(async () => root.render(sceneElement(runtime)));
      await flush();
      const cameras = runtime.renderers.map((renderer) => renderer.rendered[0].camera);
      assert.equal(new Set(cameras).size, 3);
      assert.ok(runtime.renderers.every((renderer) => renderer.rendered.length >= 1));
      await act(async () => root.unmount());
    });
  });

  test("filters heatmap triangles when membership exists and reports evidence-only otherwise", async () => {
    await withScene(async ({ container, runtime, setHeatmap, statuses }) => {
      setHeatmap({ triangles: [[0, 1, 2], [0, 2, 3]], vertices: vertices(), colors_rgb: colors(), errors_mm: [0.1, 0.2, 0.3, 0.4], triangle_region_ids: ["blade", "hub"] });
      const root = createRoot(container);
      await act(async () => root.render(sceneElement(runtime, { semanticRegion: "source-blade", semanticRegionAliases: ["source-blade", "blade"], onRegionFilterStatus: (value) => statuses.push(value) })));
      await flush();
      assert.deepEqual(statuses.at(-1).indexes, [0]);
      assert.equal(statuses.at(-1).filterable, true);
      await act(async () => root.unmount());

      setHeatmap({ triangles: [[0, 1, 2]], vertices: vertices(), colors_rgb: colors(), errors_mm: [0.1, 0.2, 0.3] });
      const retry = createRoot(container);
      await act(async () => retry.render(sceneElement(runtime, { semanticRegion: "source-blade", onRegionFilterStatus: (value) => statuses.push(value) })));
      await flush();
      assert.equal(statuses.at(-1).mode, "evidence-only");
      assert.match(statuses.at(-1).message, /cannot be filtered/);
      await act(async () => retry.unmount());
    });
  });

  test("keeps open-tip evidence hidden by default, draws it dashed when enabled, and shades closed shroud material", async () => {
    await withScene(async ({ container, runtime }) => {
      const root = createRoot(container);
      const base = task8Inspection("open");
      await act(async () => root.render(sceneElement(runtime, { inspection: base, overlays: overlayState({ tipSupport: true, openTipReference: false }) })));
      await flush();
      assert.equal(hasOverlay(runtime.renderers, "open-tip-reference"), false);
      await act(async () => root.render(sceneElement(runtime, { inspection: base, overlays: overlayState({ tipSupport: true, openTipReference: true }) })));
      await flush();
      assert.equal(hasOverlay(runtime.renderers, "open-tip-reference"), true);
      assert.ok(overlayObjects(runtime.renderers, "open-tip-reference").every((object) => object.material?.isLineDashedMaterial));
      await act(async () => root.render(sceneElement(runtime, { inspection: task8Inspection("closed"), overlays: overlayState({ tipSupport: true }) })));
      await flush();
      assert.equal(overlayCount(runtime.renderers, "closed-shroud-material"), 4);
      assert.ok(overlayObjects(runtime.renderers, "closed-shroud-material").every((object) => object.material?.isMeshStandardMaterial));
      assert.deepEqual([...new Set(overlayObjects(runtime.renderers, "closed-shroud-material").map((object) => object.userData.profileIndex))].sort(), [0, 1]);
      await act(async () => root.render(sceneElement(runtime, {
        inspection: base,
        overlays: overlayState({ selectedLoop: true }),
      })));
      await flush();
      assert.equal(hasOverlay(runtime.renderers, "source-loop-evidence"), true);
      await act(async () => root.unmount());
    });
  });

  test("renders nonempty span surfaces and representative loops from a Task8 manifest", async () => {
    await withScene(async ({ container, runtime }) => {
      const root = createRoot(container);
      await act(async () => root.render(sceneElement(runtime, {
        inspection: task8Inspection("open"),
        overlays: overlayState({ spanSurfaces: true, representativeBlade: true }),
      })));
      await flush();
      assert.ok(overlayCount(runtime.renderers, "span-surface-evidence") >= 2);
      assert.ok(overlayCount(runtime.renderers, "representative-blade-evidence") >= 2);
      assert.ok(overlayObjects(runtime.renderers, "span-surface-evidence").every((object) => object.geometry?.getAttribute("position")?.count > 0));
      assert.ok(overlayObjects(runtime.renderers, "representative-blade-evidence").every((object) => object.geometry?.getAttribute("position")?.count > 0));
      await act(async () => root.unmount());
    });
  });

  test("ignores stale load failures after switching audits", async () => {
    await withScene(async ({ container }) => {
      const runtime = mockRuntime(container.ownerDocument, { deferLoads: true });
      const heatmapRejectors = [];
      globalThis.fetch = () => new Promise((_resolve, reject) => heatmapRejectors.push(reject));
      const root = createRoot(container);

      await act(async () => root.render(sceneElement(runtime, {
        artifactUrls: { source: "/audit-a/source.stl", reconstruction: "/audit-a/reconstruction.stl", heatmap: "/audit-a/heatmap.json" },
      })));
      await flush();
      await act(async () => root.render(sceneElement(runtime, {
        artifactUrls: { source: "/audit-b/source.stl", reconstruction: "/audit-b/reconstruction.stl", heatmap: "/audit-b/heatmap.json" },
      })));
      await flush();

      assert.equal(runtime.loadErrors.length, 4);
      assert.equal(heatmapRejectors.length, 2);
      await act(async () => {
        runtime.loadErrors[0](new Error("stale source failure"));
        runtime.loadErrors[1](new Error("stale reconstruction failure"));
        heatmapRejectors[0](new Error("stale heatmap failure"));
        await Promise.resolve();
      });
      assert.doesNotMatch(container.querySelector("[role='status']").textContent, /stale .* failure/);
      await act(async () => root.unmount());
    });
  });
});

function sceneElement(runtime, overrides = {}) {
  return React.createElement(StepComparisonScene, {
    artifactUrls: { source: "/source.stl", reconstruction: "/reconstruction.stl", heatmap: "/heatmap.json" },
    inspection: task8Inspection("open"), overlays: overlayState(), semanticRegion: "all", semanticRegionAliases: ["all"],
    onHeatmapReadout: () => {}, onRegionFilterStatus: () => {}, runtime,
    ...overrides,
  });
}

function overlayState(overrides = {}) {
  return { axis: false, hub: false, tipSupport: false, spanSurfaces: false, representativeBlade: false, selectedLoop: false, openTipReference: false, ...overrides };
}

function hasOverlay(renderer, kind) {
  return overlayCount(renderer, kind) > 0;
}

function overlayCount(renderer, kind) {
  return overlayObjects(renderer, kind).length;
}

function overlayObjects(renderer, kind) {
  const renderers = Array.isArray(renderer) ? renderer : [renderer];
  const found = new Set();
  renderers.forEach((candidate) => candidate.rendered.forEach(({ scene }) => scene.traverse((object) => { if (object.userData?.overlayKind === kind) found.add(object.uuid); })));
  const objects = [];
  renderers.forEach((candidate) => candidate.rendered.forEach(({ scene }) => scene.traverse((object) => { if (found.has(object.uuid) && !objects.some((existing) => existing.uuid === object.uuid)) objects.push(object); })));
  return objects;
}

async function withScene(run) {
  const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", { url: "http://example.test" });
  const previous = { window: globalThis.window, document: globalThis.document, ResizeObserver: globalThis.ResizeObserver, fetch: globalThis.fetch };
  const heatmap = { value: { triangles: [[0, 1, 2]], vertices: vertices(), colors_rgb: colors(), errors_mm: [0.1, 0.2, 0.3] } };
  const statuses = [];
  Object.assign(globalThis, { window: dom.window, document: dom.window.document });
  dom.window.devicePixelRatio = 1;
  dom.window.requestAnimationFrame = () => 17;
  dom.window.cancelAnimationFrame = () => {};
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  globalThis.fetch = async () => ({ ok: true, json: async () => heatmap.value });
  const runtime = mockRuntime(dom.window.document);
  try { await run({ container: dom.window.document.getElementById("root"), runtime, statuses, setHeatmap: (value) => { heatmap.value = value; } }); } finally { Object.assign(globalThis, previous); dom.window.close(); }
}

function mockRuntime(document, { deferLoads = false } = {}) {
  const renderers = [];
  const controls = [];
  const loadErrors = [];
  class Renderer {
    constructor() {
      this.domElement = document.createElement("canvas");
      Object.defineProperties(this.domElement, { clientWidth: { value: 800 }, clientHeight: { value: 600 } });
      this.renderLists = { dispose: () => { this.renderListsDisposed = true; } };
      this.rendered = [];
      this.viewports = [];
      renderers.push(this);
    }
    setPixelRatio(value) { this.pixelRatio = value; }
    setScissorTest(value) { this.scissorTest = value; }
    setSize(width, height) { this.domElement.width = width * (this.pixelRatio || 1); this.domElement.height = height * (this.pixelRatio || 1); }
    setViewport(x, y, width, height) { this.viewports.push({ x, y, width, height }); }
    setScissor() {}
    setClearColor() {}
    clear() {}
    render(scene, camera) { this.rendered.push({ scene, camera }); }
    dispose() { this.disposed = true; }
    forceContextLoss() { this.contextLost = true; }
  }
  class Controls {
    constructor() { this.target = new THREE.Vector3(); controls.push(this); }
    update() {}
    dispose() { this.disposed = true; }
  }
  class Loader {
    load(_url, onLoad, _onProgress, onError) {
      if (deferLoads) {
        loadErrors.push(onError);
        return;
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices().flat(), 3));
      onLoad(geometry);
    }
  }
  return { THREE: { ...THREE, WebGLRenderer: Renderer }, OrbitControls: Controls, STLLoader: Loader, renderers, controls, loadErrors };
}

function vertices() { return [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]; }
function colors() { return [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0]]; }
async function flush() { await act(async () => { await Promise.resolve(); await Promise.resolve(); }); }

function task8Inspection(mode) {
  return stepInspectionModel(task8Manifest(mode), { populationId: "main", spanStationId: "0.5" });
}

function task8Manifest(mode) {
  const fit = (points, sourceId) => ({ control_points_rz_mm: points, residuals: { orthogonal_rms_mm: 0.02 }, pipeline_authenticated_occt_support: { source_face_id: sourceId } });
  const tipControls = [[20, 35], [23, 30], [29, 24], [38, 16], [47, 10], [52, 7]];
  const outerControls = [[22, 37], [25, 32], [31, 26], [40, 18], [49, 12], [54, 9]];
  const closed = mode === "closed";
  const tip = closed ? {
    semantic_role: "closed_shroud", material: true,
    inner_flowpath: { source_face_ids: ["face-shroud-inner"], profile_fit: fit(tipControls, "face-shroud-inner") },
    outer_material: { source_face_ids: ["face-shroud-outer"], profile_fit: fit(outerControls, "face-shroud-outer") },
    thickness: { finite_positive: true, samples_mm: [2, 2.1] },
  } : {
    semantic_role: "open_tip_reference", material: false, render_default: "hidden", export_default: "excluded",
    display_policy: { construction_overlay_only: true, material_style_forbidden: true },
    source_tip_caps: { source_face_ids: ["face-tip-01", "face-tip-02"] },
    profile_fit: fit(tipControls, "edge-open-tip"),
  };
  const loop = (population, h, id, x) => ({
    population, h, loop_id: id,
    support_profile_rz_mm: [[18 + h, 1], [24 + h, 6], [31 + h, 10]],
    source_face_ids: [`face-${id}`],
    exact_section: { accepted_loop: { points_xyz_mm: [[x, 0, h * 8], [x + 1, 0, h * 8]] } },
  });
  return {
    audit_id: `task8-${mode}`,
    canonical_geometry_version: "1.1.2",
    source: { solid_count: 1, face_count: 240, edge_count: 612 },
    frame: { axis: { origin_mm: [0, 0, 0], direction: [0, 0, 1] } },
    semantics: { main_blade_count: 13, splitter_blade_count: 13, shroud_topology: mode },
    parameter_mapping: {
      support_recovery: {
        status: "PASS", topology: { status: "PASS", decision: mode, mode, material_shroud: closed ? tip : null }, topology_mode: mode,
        hub_profile: fit([[12, 30], [15, 25], [20, 18], [30, 8], [42, 2], [51.5, 0]], "face-hub"),
        tip_reference_or_shroud: tip,
      },
      periodic_provenance: {
        status: "PASS", closure_pass: true, collision_free: true, phase_consistent: true,
        main: { count: 13, pitch_deg: 27.692307, representative_instance: { source_component_id: "main-component-03", instance_id: "main-03", source_face_ids: ["face-main-a", "face-main-b"] } },
        splitter: { count: 13, pitch_deg: 27.692307, representative_instance: { source_component_id: "splitter-component-09", instance_id: "splitter-09", source_face_ids: ["face-split-a", "face-split-b"] } },
      },
      source_section_loops: [loop("main", 0, "main-root", 9), loop("main", 0.5, "main-mid", 10), loop("splitter", 0.5, "splitter-mid", 15)],
      measurement_bundle: { attachments: { root: { lift_samples_mm: [1.4, 1.5, 1.6], width_samples_mm: [3.4, 3.5, 3.6], source_ids: ["face-root", "edge-root"], source_measurement: true, promotable: true, material_side: 1 } } },
      promotion: { promotable: true },
      objective_terms: { attachment: { records: [{ attachment: "root", target_lift_mm: 1.5, fitted_lift_mm: 1.48, target_width_mm: 3.5, fitted_width_mm: 3.42, lift_relative: 0.013, width_relative: 0.023, status: "PASS", source_ids: ["face-root"] }] } },
    },
  };
}
