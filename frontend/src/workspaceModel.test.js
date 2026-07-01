import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  defaultVisibleLayers,
  geometryStats,
  layerForConstructionFeature,
  layerForSurface,
} from "./workspaceModel.js";

describe("impeller geometry workspace model", () => {
  test("defaultVisibleLayers enables every declared layer", () => {
    const layers = defaultVisibleLayers();

    assert.equal(layers.shaded_surfaces, true);
    assert.equal(layers.surface_uv, true);
    assert.equal(layers.blade_boundaries, true);
    assert.equal(layers.edge_closures, true);
  });

  test("maps surface graph roles to stable inspection layers", () => {
    assert.equal(layerForSurface({ role: "hub" }), "hub_support");
    assert.equal(layerForSurface({ role: "reference_only" }), "tip_support");
    assert.equal(layerForSurface({ role: "front_shroud_inner_surface" }), "tip_support");
    assert.equal(layerForSurface({ role: "blade_pressure" }), "blade_surfaces");
    assert.equal(layerForSurface({ kind: "edge_closure_surface" }), "edge_closures");
  });

  test("maps construction features to the same inspection layers", () => {
    assert.equal(layerForConstructionFeature("hub"), "hub_support");
    assert.equal(layerForConstructionFeature("shroud"), "tip_support");
    assert.equal(layerForConstructionFeature("surface_uv"), "surface_uv");
    assert.equal(layerForConstructionFeature("blade_boundaries"), "blade_boundaries");
    assert.equal(layerForConstructionFeature("named_boundary_curve"), "blade_boundaries");
    assert.equal(layerForConstructionFeature("blade_edges"), "edge_closures");
  });

  test("geometryStats counts surfaces named boundaries and construction lines", () => {
    const stats = geometryStats({
      geometry: {
        surface_graph: {
          surfaces: [{ id: "hub" }, { id: "blade_pressure" }],
          named_boundary_curves: [{ id: "root" }, { id: "tip" }],
        },
        construction_lines: {
          surface_uv: [{}, {}],
          blade_boundaries: [{}],
        },
      },
    });

    assert.deepEqual(stats, {
      surfaceCount: 2,
      boundaryCount: 2,
      constructionLineCount: 3,
    });
  });
});
