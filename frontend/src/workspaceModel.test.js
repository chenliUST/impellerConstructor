import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildWorkspaceModel,
  defaultVisibleLayers,
  geometryStats,
  layerForConstructionFeature,
  layerForSurface,
  meshOverlayLayerForV104,
  sharedEdgeLayerForV104,
  usesV104ViewerLayers,
} from "./workspaceModel.js";

describe("impeller geometry workspace model", () => {
  test("defaultVisibleLayers enables every declared layer", () => {
    const layers = defaultVisibleLayers();

    assert.equal(layers.shaded_surfaces, true);
    assert.equal(layers.shade_surfaces, true);
    assert.equal(layers.nurbs_uv_wire, true);
    assert.equal(layers.mesh_triangle_wire, false);
    assert.equal(layers.control_curves, true);
    assert.equal(layers.control_points, true);
    assert.equal(layers.shared_edges, false);
    assert.equal(layers.diagnostic_failures, true);
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
    assert.equal(
      layerForSurface({ role: "root_to_hub_blend", display: { inspection_class: "root_to_hub_blend" } }),
      "transition_surfaces",
    );
    assert.equal(
      layerForSurface({ role: "open_tip_dome", display: { inspection_class: "open_tip_dome" } }),
      "transition_surfaces",
    );
  });

  test("curve control overlays are preserved in workspace state", () => {
    const manifest = {
      curve_controls: {
        hub_profile_nurbs: { control_points: [[160, 400], [580, 0]] },
      },
      geometry: {
        section_loop_controls: {
          blade_section_loop_template: {
            segments: {
              pressure_side: { control_points: [[0, -16], [100, -10]] },
            },
          },
        },
      },
    };

    const workspace = buildWorkspaceModel({ manifest });

    assert.deepEqual(workspace.curveControls.hub_profile_nurbs.control_points, [[160, 400], [580, 0]]);
    assert.deepEqual(
      workspace.sectionLoopControls.blade_section_loop_template.segments.pressure_side.control_points,
      [[0, -16], [100, -10]],
    );
  });

  test("maps v1.0.2 attachment inspection classes to edge closure layers", () => {
    assert.equal(
      layerForSurface({
        role: "root_pedestal_ring_surface",
        display: { inspection_class: "root_to_hub_native_root_face" },
      }),
      "edge_closures",
    );
    assert.equal(
      layerForSurface({
        role: "tip_to_shroud_attachment_surface",
        display: { inspection_class: "tip_to_shroud_attachment" },
      }),
      "edge_closures",
    );
  });

  test("detects V1.0.4 viewer layers without enabling them for legacy manifests", () => {
    assert.equal(
      usesV104ViewerLayers({
        geometry: { surface_graph: { geometry_patch_version: "1.0.4" } },
      }),
      true,
    );
    assert.equal(
      usesV104ViewerLayers({
        metadata: { transitionGeometryStatus: "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph" },
      }),
      true,
    );
    assert.equal(
      usesV104ViewerLayers({
        geometry: { surface_graph: { geometry_patch_version: "1.0.3" } },
      }),
      false,
    );
    assert.equal(usesV104ViewerLayers(null), false);
  });

  test("maps V1.0.4 mesh and shared-edge diagnostics to explicit layers", () => {
    assert.equal(meshOverlayLayerForV104({ id: "blade_0_pressure_surface" }), "mesh_triangle_wire");
    assert.equal(meshOverlayLayerForV104({ id: "blade_0_root_annular_surface", status: "FAIL" }), "diagnostic_failures");
    assert.equal(sharedEdgeLayerForV104({ id: "edge_0" }), "shared_edges");
    assert.equal(sharedEdgeLayerForV104({ id: "edge_1", blocking: true }), "diagnostic_failures");
  });

  test("maps V1.1 blade-to-blade surface families to stable layers", () => {
    assert.equal(layerForSurface({ role: "blade_pressure", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "blade_surfaces");
    assert.equal(layerForSurface({ role: "blade_leading_edge", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "edge_closures");
    assert.equal(layerForSurface({ role: "root_to_hub_attachment", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "transition_surfaces");
    assert.equal(layerForSurface({ role: "open_tip_dome", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "transition_surfaces");
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
