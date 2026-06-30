import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  cfdPatchGroups,
  cfdPatchInstances,
  patchSurfaceIds,
  surfaceVisibleInView,
  viewModeOptions,
} from "./simulationViewModel.js";

describe("simulation view model", () => {
  test("viewModeOptions includes CAD, CFD, and feature debug views", () => {
    assert.deepEqual(viewModeOptions().map((option) => option.id), [
      "cad_review_360",
      "cfd_full_360",
      "feature_debug",
    ]);
  });

  test("surfaceVisibleInView hides construction and suppressed assembly in cfd view", () => {
    assert.equal(surfaceVisibleInView({ role: "construction_support_only" }, "cfd_full_360"), false);
    assert.equal(surfaceVisibleInView({ role: "mounting_bore" }, "cfd_full_360"), false);
    assert.equal(surfaceVisibleInView({ cfd_role: "blade_pressure" }, "cfd_full_360"), true);
    assert.equal(surfaceVisibleInView({ role: "construction_support_only" }, "cad_review_360"), true);
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
  });
});
