import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildSimulationViewModel,
  cfdPatchGroups,
  cfdPatchInstances,
  patchBoundaryCurveIds,
  patchSurfaceIds,
  surfaceVisibleInView,
  viewModeOptions,
} from "./simulationViewModel.js";

const RECTANGULAR_UV_GRID = [
  [
    [0, 0, 0],
    [1, 0, 0],
  ],
  [
    [0, 1, 0],
    [1, 1, 0],
  ],
];

describe("simulation view model", () => {
  test("viewModeOptions includes CAD, CFD, and feature debug views", () => {
    assert.deepEqual(viewModeOptions().map((option) => option.id), [
      "cad_review_360",
      "cfd_full_360",
      "mesh",
      "feature_debug",
    ]);
  });

  test("surfaceVisibleInView hides construction and suppressed assembly in cfd view", () => {
    assert.equal(surfaceVisibleInView({ role: "construction_support_only" }, "cfd_full_360"), false);
    assert.equal(surfaceVisibleInView({ role: "mounting_bore" }, "cfd_full_360"), false);
    assert.equal(surfaceVisibleInView({ cfd_role: "blade_pressure" }, "cfd_full_360"), true);
    assert.equal(surfaceVisibleInView({ cfd_role: "leading_edge_transition", uv_grid: RECTANGULAR_UV_GRID }, "mesh"), true);
    assert.equal(surfaceVisibleInView({ role: "construction_support_only" }, "cad_review_360"), true);
  });

  test("surfaceVisibleInView hides display-suppressed construction references outside feature debug", () => {
    const hiddenReference = {
      id: "tip_reference_surface",
      role: "reference_only",
      display: { visible_by_default: false, construction_reference: true },
    };

    assert.equal(surfaceVisibleInView(hiddenReference, "cad_review_360"), false);
    assert.equal(surfaceVisibleInView(hiddenReference, "mesh"), false);
    assert.equal(surfaceVisibleInView(hiddenReference, "feature_debug"), true);
  });

  test("surfaceVisibleInView uses manifest patch surfaces as the cfd whitelist", () => {
    const manifest = {
      simulation_manifests: {
        cfd_full_360: {
          patch_instances: {
            hub: { source_type: "surface", surface_graph_id: "hub_revolve_surface" },
          },
        },
      },
    };

    assert.equal(surfaceVisibleInView({ id: "hub_revolve_surface", cfd_role: "hub_wall" }, "cfd_full_360", manifest), true);
    assert.equal(surfaceVisibleInView({ id: "inner_hub_bottom_face", role: "inner_hub_bottom" }, "cfd_full_360", manifest), false);
  });

  test("surfaceVisibleInView uses cfd surface mesh regions as the v1.1 cfd whitelist fallback", () => {
    const manifest = {
      simulation_manifests: {
        cfd_surface_mesh: {
          patch_regions: [
            { surface_graph_id: "hub_revolve_surface", triangle_count: 96 },
            { surface_graph_id: "blade_00_pressure_surface", triangle_count: 64 },
            { surface_graph_id: "mounting_bore_inner_wall_surface", triangle_count: 32 },
          ],
        },
      },
    };

    assert.equal(surfaceVisibleInView({ id: "hub_revolve_surface", role: "hub_wall" }, "cfd_full_360", manifest), true);
    assert.equal(
      surfaceVisibleInView({ id: "blade_00_pressure_surface", role: "blade_pressure" }, "cfd_full_360", manifest),
      true,
    );
    assert.equal(
      surfaceVisibleInView({ id: "mounting_bore_inner_wall_surface", role: "mounting_bore" }, "cfd_full_360", manifest),
      false,
    );
    assert.equal(surfaceVisibleInView({ id: "unlisted_surface", role: "blade_suction" }, "cfd_full_360", manifest), false);
  });

  test("surfaceVisibleInView shows all renderable manufactured surfaces in mesh view outside the cfd whitelist", () => {
    const manifest = {
      simulation_manifests: {
        cfd_full_360: {
          patch_instances: {
            hub: { source_type: "surface", surface_graph_id: "hub_revolve_surface" },
          },
        },
        cfd_surface_mesh: {
          transition_regions: [{ surface_graph_id: "blade_00_tip_blend" }],
        },
      },
    };
    const policyTransitionSurface = {
      id: "blade_00_root_fillet",
      transition_policy_id: "root.fillet.default",
      edge_family: "blade_root_to_hub",
      uv_grid: RECTANGULAR_UV_GRID,
    };
    const manifestTransitionSurface = {
      id: "blade_00_tip_blend",
      edge_family: "blade_tip_or_shroud",
      uv_grid: RECTANGULAR_UV_GRID,
    };
    const genericEdgeSurface = {
      id: "blade_00_root_edge_closure",
      edge_family: "blade_root_to_hub",
      uv_grid: RECTANGULAR_UV_GRID,
    };
    const mountingBoreSurface = {
      id: "mounting_bore",
      role: "mounting_bore",
      uv_grid: RECTANGULAR_UV_GRID,
    };
    const meshOnlyReviewSurface = {
      id: "mesh_only_review_surface",
      mesh: { triangles: [[[0, 0, 0], [1, 0, 0], [0, 1, 0]]] },
    };

    assert.equal(surfaceVisibleInView(policyTransitionSurface, "mesh", manifest), true);
    assert.equal(surfaceVisibleInView(manifestTransitionSurface, "mesh", manifest), true);
    assert.equal(surfaceVisibleInView(genericEdgeSurface, "mesh", manifest), true);
    assert.equal(surfaceVisibleInView(mountingBoreSurface, "mesh", manifest), true);
    assert.equal(surfaceVisibleInView(meshOnlyReviewSurface, "mesh", manifest), true);
    assert.equal(surfaceVisibleInView({ id: "metadata_only_review_surface" }, "mesh", manifest), false);
    assert.equal(
      surfaceVisibleInView({ id: "hidden_construction", role: "construction_support_only", uv_grid: RECTANGULAR_UV_GRID }, "mesh", manifest),
      false,
    );
    assert.equal(
      surfaceVisibleInView({ id: "hidden_reference", role: "reference_only", uv_grid: RECTANGULAR_UV_GRID }, "mesh", manifest),
      false,
    );
    assert.equal(
      surfaceVisibleInView({ id: "suppressed_face", display: { visible_by_default: false }, uv_grid: RECTANGULAR_UV_GRID }, "mesh", manifest),
      false,
    );
    assert.equal(surfaceVisibleInView(policyTransitionSurface, "cfd_full_360", manifest), false);
  });

  test("v1.0.3 root and tip dome surfaces remain visible as transition mesh surfaces", () => {
    const manifest = {
      geometry: {
        surface_graph: {
          surfaces: [
            { id: "root_aggregate", display: { visible_by_default: false, aggregate_surface: true } },
            { id: "root_patch", role: "root_to_hub_blend", display: { inspection_class: "root_to_hub_blend" } },
            { id: "tip_dome", role: "open_tip_dome", display: { inspection_class: "open_tip_dome" } },
          ],
        },
      },
    };

    const view = buildSimulationViewModel(manifest, { simulationViewMode: "cad_review_360" });
    const surfaceIds = view.surfaces.map((surface) => surface.id);

    assert.ok(surfaceIds.includes("root_patch"));
    assert.ok(surfaceIds.includes("tip_dome"));
    assert.equal(surfaceIds.includes("root_aggregate"), false);
  });

  test("cfdPatchGroups and cfdPatchInstances return sorted arrays", () => {
    const manifest = {
      simulation_manifests: {
        cfd_full_360: {
          patch_groups: {
            hub_wall: { instances: ["hub"] },
            blade_pressure_wall: { instances: ["blade_00_pressure_surface"] },
          },
          patch_instances: {
            hub: { group: "hub_wall" },
            blade_00_pressure_surface: { group: "blade_pressure_wall" },
          },
        },
      },
    };

    assert.deepEqual(cfdPatchGroups(manifest).map((group) => group.id), ["blade_pressure_wall", "hub_wall"]);
    assert.deepEqual(cfdPatchInstances(manifest).map((instance) => instance.id), ["blade_00_pressure_surface", "hub"]);
  });

  test("patchSurfaceIds maps selected patch groups to surface graph ids", () => {
    const manifest = {
      simulation_manifests: {
        cfd_full_360: {
          patch_groups: {
            blade_pressure_wall: {
              instances: ["blade_pressure_wall:blade_00_pressure_surface", "blade_01_pressure_surface"],
            },
            inlet_patch: {
              instances: ["blade_00_leading_edge_boundary"],
            },
          },
          patch_instances: {
            "blade_pressure_wall:blade_00_pressure_surface": {
              group: "blade_pressure_wall",
              source_type: "surface",
              surface_graph_id: "blade_00_pressure_surface",
            },
            blade_01_pressure_surface: {
              group: "blade_pressure_wall",
              source_type: "surface",
              surface_graph_id: "blade_01_pressure_surface",
            },
            blade_00_leading_edge_boundary: {
              group: "inlet_patch",
              source_type: "boundary_curve",
              boundary_curve_id: "blade_00_leading_edge_boundary",
            },
          },
        },
      },
    };

    assert.deepEqual([...patchSurfaceIds(manifest, "blade_pressure_wall")], [
      "blade_00_pressure_surface",
      "blade_01_pressure_surface",
    ]);
    assert.deepEqual([...patchSurfaceIds(manifest, "inlet_patch")], []);
    assert.deepEqual([...patchBoundaryCurveIds(manifest, "inlet_patch")], ["blade_00_leading_edge_boundary"]);
  });
});
