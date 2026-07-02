import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  cfdPatchGroups,
  cfdPatchInstances,
  patchBoundaryCurveIds,
  patchSurfaceIds,
  surfaceVisibleInView,
  viewModeOptions,
} from "./simulationViewModel.js";

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
    assert.equal(surfaceVisibleInView({ cfd_role: "leading_edge_transition" }, "mesh"), true);
    assert.equal(surfaceVisibleInView({ role: "construction_support_only" }, "cad_review_360"), true);
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

  test("surfaceVisibleInView keeps transition-tagged surfaces visible in mesh view outside the cfd whitelist", () => {
    const manifest = {
      simulation_manifests: {
        cfd_full_360: {
          patch_instances: {
            hub: { source_type: "surface", surface_graph_id: "hub_revolve_surface" },
          },
        },
      },
    };
    const transitionSurface = {
      id: "blade_00_root_fillet",
      transition_policy_id: "root.fillet.default",
      edge_family: "blade_root_to_hub",
    };

    assert.equal(surfaceVisibleInView(transitionSurface, "mesh", manifest), true);
    assert.equal(surfaceVisibleInView(transitionSurface, "cfd_full_360", manifest), false);
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
