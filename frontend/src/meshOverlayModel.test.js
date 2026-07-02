import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { meshOverlayOptions, transitionRegionRows } from "./meshOverlayModel.js";

describe("mesh overlay model", () => {
  test("meshOverlayOptions exposes stable overlay ids", () => {
    assert.deepEqual(meshOverlayOptions().map((option) => option.id), [
      "off",
      "triangle_edges",
      "patch_groups",
      "quality",
      "transitions",
    ]);
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
});
