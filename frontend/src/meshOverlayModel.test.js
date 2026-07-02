import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { isTransitionSurface, meshOverlayOptions, transitionRegionRows, transitionSurfaceIds } from "./meshOverlayModel.js";

describe("mesh overlay model", () => {
  test("meshOverlayOptions exposes stable overlay ids", () => {
    assert.deepEqual(meshOverlayOptions().map((option) => option.id), ["off", "triangle_edges"]);
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
