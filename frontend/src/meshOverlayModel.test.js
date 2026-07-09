import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  effectiveMeshOverlayMode,
  isTransitionSurface,
  meshOverlayControlVisible,
  meshOverlayOptions,
  transitionRegionRows,
  transitionSurfaceIds,
  viewerLayerVisibility,
  viewerVisibilityForMeshOverlay,
} from "./meshOverlayModel.js";

describe("mesh overlay model", () => {
  test("meshOverlayOptions exposes stable overlay ids", () => {
    assert.deepEqual(meshOverlayOptions().map((option) => option.id), ["off", "triangle_edges"]);
  });

  test("mesh overlay is active by default only in mesh inspection view", () => {
    assert.equal(effectiveMeshOverlayMode("mesh", undefined), "triangle_edges");
    assert.equal(effectiveMeshOverlayMode("mesh", "off"), "off");
    assert.equal(effectiveMeshOverlayMode("cad_review_360", "triangle_edges"), "off");
    assert.equal(effectiveMeshOverlayMode("cfd_full_360", "triangle_edges"), "off");
  });

  test("mesh overlay control is only relevant for mesh inspection view", () => {
    assert.equal(meshOverlayControlVisible("mesh"), true);
    assert.equal(meshOverlayControlVisible("cad_review_360"), false);
    assert.equal(meshOverlayControlVisible("cfd_full_360"), false);
  });

  test("viewerLayerVisibility separates shaded surfaces and UV wire by view mode", () => {
    assert.deepEqual(
      viewerLayerVisibility({
        simulationViewMode: "cad_review_360",
        viewMode: "shaded",
        meshOverlayMode: "triangle_edges",
        visibleLayers: { shaded_surfaces: true },
      }),
      {
        showShadedSurfaces: true,
        showSurfaceUvWire: false,
        showMeshEdges: false,
        showConstructionLines: false,
      },
    );
    assert.deepEqual(
      viewerLayerVisibility({
        simulationViewMode: "cad_review_360",
        viewMode: "wireframe",
        meshOverlayMode: "triangle_edges",
        visibleLayers: { shaded_surfaces: true },
      }),
      {
        showShadedSurfaces: false,
        showSurfaceUvWire: true,
        showMeshEdges: false,
        showConstructionLines: false,
      },
    );
    assert.deepEqual(
      viewerLayerVisibility({
        simulationViewMode: "cad_review_360",
        viewMode: "combined",
        meshOverlayMode: "triangle_edges",
        visibleLayers: { shaded_surfaces: true },
      }),
      {
        showShadedSurfaces: true,
        showSurfaceUvWire: true,
        showMeshEdges: false,
        showConstructionLines: false,
      },
    );
  });

  test("viewerLayerVisibility shows mesh edges only in mesh inspection non-shaded modes when enabled", () => {
    assert.deepEqual(
      viewerLayerVisibility({
        simulationViewMode: "mesh",
        viewMode: "wireframe",
        meshOverlayMode: "triangle_edges",
        visibleLayers: { shaded_surfaces: true },
      }),
      {
        showShadedSurfaces: false,
        showSurfaceUvWire: true,
        showMeshEdges: true,
        showConstructionLines: false,
      },
    );
    assert.deepEqual(
      viewerLayerVisibility({
        simulationViewMode: "mesh",
        viewMode: "shaded",
        meshOverlayMode: "triangle_edges",
        visibleLayers: { shaded_surfaces: true },
      }),
      {
        showShadedSurfaces: true,
        showSurfaceUvWire: false,
        showMeshEdges: false,
        showConstructionLines: false,
      },
    );
    assert.deepEqual(
      viewerLayerVisibility({
        simulationViewMode: "mesh",
        viewMode: "combined",
        meshOverlayMode: "off",
        visibleLayers: { shaded_surfaces: true },
      }),
      {
        showShadedSurfaces: true,
        showSurfaceUvWire: true,
        showMeshEdges: false,
        showConstructionLines: false,
      },
    );
  });

  test("viewerLayerVisibility only enables construction lines in feature debug", () => {
    assert.equal(
      viewerLayerVisibility({ simulationViewMode: "cad_review_360", viewMode: "combined" }).showConstructionLines,
      false,
    );
    assert.equal(
      viewerLayerVisibility({ simulationViewMode: "feature_debug", viewMode: "shaded" }).showConstructionLines,
      true,
    );
  });

  test("viewerVisibilityForMeshOverlay wraps the layer visibility model for legacy callers", () => {
    assert.deepEqual(
      viewerVisibilityForMeshOverlay({
        simulationViewMode: "mesh",
        viewMode: "combined",
        meshOverlayMode: "triangle_edges",
        visibleLayers: { shaded_surfaces: true },
      }),
      { showShaded: true, showMeshOverlay: true },
    );
    assert.deepEqual(
      viewerVisibilityForMeshOverlay({
        simulationViewMode: "mesh",
        viewMode: "wireframe",
        meshOverlayMode: "off",
        visibleLayers: { shaded_surfaces: true },
      }),
      { showShaded: false, showMeshOverlay: false },
    );
  });

  test("transitionRegionRows maps mesh manifest transition regions", () => {
    const rows = transitionRegionRows({
      transition_regions: [
        {
          edge_family: "blade_root_to_hub",
          transition_policy_id: "root.fillet.default",
          surface_graph_id: "blade_00_root_fillet",
          triangle_count: 42,
        },
      ],
    });

    assert.deepEqual(rows, [
      {
        edgeFamily: "blade_root_to_hub",
        transitionPolicyId: "root.fillet.default",
        surfaceGraphId: "blade_00_root_fillet",
        triangleCount: 42,
      },
    ]);
  });

  test("transitionSurfaceIds extracts manifest transition region surface ids", () => {
    assert.deepEqual(
      [...transitionSurfaceIds({
        transition_regions: {
          root: { surface_graph_id: "blade_00_root_fillet" },
          tip: { surfaceGraphId: "blade_00_tip_chamfer" },
        },
      })],
      ["blade_00_root_fillet", "blade_00_tip_chamfer"],
    );
  });

  test("transition helpers tolerate absent mesh manifest during surface render", () => {
    assert.deepEqual(transitionRegionRows(null), []);
    assert.deepEqual([...transitionSurfaceIds(null)], []);
    assert.equal(isTransitionSurface({ id: "blade_0_pressure_surface", role: "blade_pressure" }, null), false);
  });

  test("isTransitionSurface ignores raw edge family without transition evidence", () => {
    assert.equal(isTransitionSurface({ edge_family: "blade_root_to_hub" }), false);
    assert.equal(isTransitionSurface({ transition_policy_id: "root.fillet.default", edge_family: "blade_root_to_hub" }), true);
    assert.equal(isTransitionSurface({ role: "blade_root_fillet" }), true);
    assert.equal(
      isTransitionSurface(
        { id: "blade_00_root_fillet", edge_family: "blade_root_to_hub" },
        { transition_regions: [{ surface_graph_id: "blade_00_root_fillet" }] },
      ),
      true,
    );
  });
});
