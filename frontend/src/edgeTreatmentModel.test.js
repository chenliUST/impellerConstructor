import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildTransitionOverridePayload,
  edgeTreatmentRows,
  updateTransitionRow,
} from "./edgeTreatmentModel.js";

const manifest = {
  edge_families: {
    blade_root_to_hub: { scope: "blade_pattern" },
    mounting_bore_top: { scope: "hub_solid" },
    blade_tip_or_shroud: { scope: "blade_pattern" },
  },
  transition_policies: {
    "mounting_bore_top.default": {
      policy_id: "mounting_bore_top.default",
      edge_family: "mounting_bore_top",
      enabled: true,
      treatment: "chamfer",
      radius_mm: 3,
      continuity: "G0",
    },
    "blade_root_to_hub.default": {
      policy_id: "blade_root_to_hub.default",
      edge_family: "blade_root_to_hub",
      enabled: true,
      treatment: "fillet",
      radius_mm: 8,
      continuity: "G1",
    },
    "blade_tip_or_shroud.default": {
      policy_id: "blade_tip_or_shroud.default",
      edge_family: "blade_tip_or_shroud",
      enabled: false,
      treatment: "none",
      radius_mm: 0,
      continuity: "G0",
    },
  },
};

describe("edge treatment model", () => {
  test("manifest transition policies become sorted edge family rows", () => {
    const rows = edgeTreatmentRows(manifest);

    assert.deepEqual(
      rows.map((row) => [row.policyId, row.edgeFamily, row.scope, row.status]),
      [
        ["blade_root_to_hub.default", "blade_root_to_hub", "blade_pattern", "OK"],
        ["blade_tip_or_shroud.default", "blade_tip_or_shroud", "blade_pattern", "OFF"],
        ["mounting_bore_top.default", "mounting_bore_top", "hub_solid", "OK"],
      ],
    );
    assert.equal(rows[0].radiusMm, 8);
    assert.equal(rows[0].continuity, "G1");
  });

  test("updateTransitionRow changes treatment and radius using API radius field", () => {
    const overrides = updateTransitionRow(
      { "blade_root_to_hub.default": { enabled: true } },
      "blade_root_to_hub.default",
      { treatment: "chamfer", radiusMm: 6.5 },
    );

    assert.deepEqual(overrides, {
      "blade_root_to_hub.default": {
        enabled: true,
        treatment: "chamfer",
        radius_mm: 6.5,
      },
    });
  });

  test("buildTransitionOverridePayload omits empty overrides but keeps explicit disabled none override", () => {
    assert.equal(buildTransitionOverridePayload({}), null);
    assert.equal(buildTransitionOverridePayload(null), null);

    const overrides = {
      "blade_tip_or_shroud.default": { enabled: false, treatment: "none" },
    };

    assert.deepEqual(buildTransitionOverridePayload(overrides), overrides);
  });

  test("edgeTreatmentRows marks negative radius as invalid", () => {
    const rows = edgeTreatmentRows({
      edge_families: { blade_root_to_hub: { scope: "blade_pattern" } },
      transition_policies: {
        "blade_root_to_hub.default": {
          edge_family: "blade_root_to_hub",
          enabled: true,
          treatment: "fillet",
          radius_mm: -1,
          continuity: "G1",
        },
      },
    });

    assert.equal(rows[0].status, "INVALID");
  });

  test("edgeTreatmentRows keeps enabled flag distinct from none treatment status", () => {
    const rows = edgeTreatmentRows({
      edge_families: { blade_tip_or_shroud: { scope: "blade_pattern" } },
      transition_policies: {
        "blade_tip_or_shroud.default": {
          edge_family: "blade_tip_or_shroud",
          enabled: true,
          treatment: "none",
          radius_mm: 0,
          continuity: "G0",
        },
      },
    });

    assert.equal(rows[0].enabled, true);
    assert.equal(rows[0].status, "OFF");
  });
});
