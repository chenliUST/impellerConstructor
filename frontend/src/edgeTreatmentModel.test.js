import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  buildTransitionOverridePayload,
  edgeTreatmentRows,
  effectiveTransitionRow,
  transitionRuntimeSummary,
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

  test("transitionRuntimeSummary reads resolved transition runtime counts", () => {
    assert.deepEqual(
      transitionRuntimeSummary({
        transition_geometry_status: "resolved_trimmed_surface_graph",
        transition_surface_count: 6,
        unsupported_transition_count: 0,
        transition_failure_count: 1,
      }),
      {
        status: "resolved_trimmed_surface_graph",
        surfaceCount: 6,
        unsupportedCount: 0,
        failureCount: 1,
        available: true,
      },
    );
  });

  test("transitionRuntimeSummary falls back to mesh transition region count", () => {
    assert.deepEqual(
      transitionRuntimeSummary({
        simulation_manifests: {
          cfd_surface_mesh: {
            transition_regions: [{ surface_graph_id: "root" }, { surface_graph_id: "tip" }],
          },
        },
      }),
      {
        status: "",
        surfaceCount: 2,
        unsupportedCount: 0,
        failureCount: 0,
        available: true,
      },
    );
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

  test("updateTransitionRow keeps treatment and enabled semantics aligned", () => {
    assert.deepEqual(
      updateTransitionRow({}, "blade_tip_or_shroud.default", { treatment: "fillet" }),
      {
        "blade_tip_or_shroud.default": {
          treatment: "fillet",
          enabled: true,
        },
      },
    );

    assert.deepEqual(
      updateTransitionRow(
        { "blade_root_to_hub.default": { enabled: true, treatment: "fillet", radius_mm: 4 } },
        "blade_root_to_hub.default",
        { treatment: "none" },
      ),
      {
        "blade_root_to_hub.default": {
          enabled: false,
          treatment: "none",
        },
      },
    );
  });

  test("effectiveTransitionRow reflects payload semantics for checkbox and status", () => {
    const disabledBaseRow = edgeTreatmentRows(manifest).find((row) => row.policyId === "blade_tip_or_shroud.default");
    const enabled = effectiveTransitionRow(disabledBaseRow, { treatment: "fillet", enabled: true });
    const disabled = effectiveTransitionRow(disabledBaseRow, { treatment: "none", enabled: false });

    assert.equal(enabled.enabled, true);
    assert.equal(enabled.treatment, "fillet");
    assert.equal(enabled.status, "INVALID");
    assert.equal(disabled.enabled, false);
    assert.equal(disabled.treatment, "none");
    assert.equal(disabled.status, "OFF");
  });

  test("reenabling a default-none row restores a positive fillet radius in payload", () => {
    const baseRow = edgeTreatmentRows(manifest).find((row) => row.policyId === "blade_tip_or_shroud.default");
    const overrides = updateTransitionRow({}, "blade_tip_or_shroud.default", { enabled: true }, baseRow);
    const override = overrides["blade_tip_or_shroud.default"];
    const effective = effectiveTransitionRow(baseRow, override);

    assert.equal(override.enabled, true);
    assert.equal(override.treatment, "fillet");
    assert.equal(override.radius_mm, 1);
    assert.equal(effective.radiusMm, 1);
    assert.equal(effective.status, "OK");
    assert.deepEqual(buildTransitionOverridePayload(overrides), {
      "blade_tip_or_shroud.default": {
        enabled: true,
        treatment: "fillet",
        radius_mm: 1,
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

  test("buildTransitionOverridePayload removes stale invalid radius when disabling a treatment", () => {
    const row = edgeTreatmentRows(manifest).find((item) => item.policyId === "blade_root_to_hub.default");
    const overrides = updateTransitionRow(
      {
        "blade_root_to_hub.default": {
          enabled: true,
          treatment: "fillet",
          radius_mm: -1,
        },
      },
      "blade_root_to_hub.default",
      { enabled: false },
      row,
    );
    const effective = effectiveTransitionRow(row, overrides["blade_root_to_hub.default"]);

    assert.equal(effective.status, "OFF");
    assert.deepEqual(buildTransitionOverridePayload(overrides), {
      "blade_root_to_hub.default": {
        enabled: false,
        treatment: "fillet",
      },
    });
  });

  test("buildTransitionOverridePayload removes stale invalid radius when selecting none", () => {
    const row = edgeTreatmentRows(manifest).find((item) => item.policyId === "blade_root_to_hub.default");
    const overrides = updateTransitionRow(
      {
        "blade_root_to_hub.default": {
          enabled: true,
          treatment: "fillet",
          radius_mm: -1,
        },
      },
      "blade_root_to_hub.default",
      { treatment: "none" },
      row,
    );
    const effective = effectiveTransitionRow(row, overrides["blade_root_to_hub.default"]);

    assert.equal(effective.status, "OFF");
    assert.deepEqual(buildTransitionOverridePayload(overrides), {
      "blade_root_to_hub.default": {
        enabled: false,
        treatment: "none",
      },
    });
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

  test("edgeTreatmentRows marks zero radius active treatment as invalid", () => {
    const rows = edgeTreatmentRows({
      edge_families: { blade_root_to_hub: { scope: "blade_pattern" } },
      transition_policies: {
        "blade_root_to_hub.default": {
          edge_family: "blade_root_to_hub",
          enabled: true,
          treatment: "fillet",
          radius_mm: 0,
          continuity: "G1",
        },
      },
    });

    assert.equal(rows[0].status, "INVALID");
  });

  test("edgeTreatmentRows marks non-finite radius as invalid", () => {
    const rows = edgeTreatmentRows({
      edge_families: { blade_root_to_hub: { scope: "blade_pattern" } },
      transition_policies: {
        "blade_root_to_hub.default": {
          edge_family: "blade_root_to_hub",
          enabled: true,
          treatment: "fillet",
          radius_mm: "not-a-number",
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
