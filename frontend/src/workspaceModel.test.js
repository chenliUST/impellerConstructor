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
    assert.equal(layers.transition_surfaces, true);
    assert.equal(layers.mesh_edges, true);
    assert.equal(layers.transition_mesh_edges, true);
    assert.equal(layers.solid_context, true);
    assert.equal(layers.fluid_boundary, true);
  });

  test("maps surface graph roles to stable inspection layers", () => {
    assert.equal(layerForSurface({ role: "hub" }), "hub_support");
    assert.equal(layerForSurface({ role: "reference_only" }), "tip_support");
    assert.equal(layerForSurface({ role: "front_shroud_inner_surface" }), "tip_support");
    assert.equal(layerForSurface({ role: "blade_pressure" }), "blade_surfaces");
    assert.equal(layerForSurface({ kind: "edge_closure_surface" }), "edge_closures");
  });

  test("maps transition surfaces before generic blade or edge closure layers", () => {
    assert.equal(layerForSurface({ transition_policy_id: "root.fillet.default", role: "blade_root" }), "transition_surfaces");
    assert.equal(layerForSurface({ edge_family: "blade_tip_or_shroud", kind: "edge_closure_surface" }), "edge_closures");
    assert.equal(
      layerForSurface(
        { id: "blade_00_tip_blend", edge_family: "blade_tip_or_shroud", kind: "edge_closure_surface" },
        { transition_regions: [{ surface_graph_id: "blade_00_tip_blend" }] },
      ),
      "transition_surfaces",
    );
    assert.equal(layerForSurface({ role: "blade_root_fillet" }), "transition_surfaces");
    assert.equal(layerForSurface({ cfd_role: "leading_edge_transition" }), "transition_surfaces");
  });

  test("maps solid context and fluid boundary surfaces to dedicated layers", () => {
    assert.equal(layerForSurface({ role: "solid_context" }), "solid_context");
    assert.equal(layerForSurface({ cfd_role: "fluid_boundary" }), "fluid_boundary");
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
