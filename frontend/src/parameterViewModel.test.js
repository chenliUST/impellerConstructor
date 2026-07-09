import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { presets } from "./appModel.js";
import {
  parameterViewTabs,
  resolvedCanonicalParameterization,
} from "./parameterViewModel.js";

describe("V1.1.2 parameter view model", () => {
  test("uses preset canonical defaults before generation", () => {
    const preset = presets[0];
    const resolved = resolvedCanonicalParameterization(preset, null);

    assert.equal(resolved.sourceLabel, "preset defaults");
    assert.equal(resolved.canonical.canonical_payload_version, "1.1.2");
    assert.equal(resolved.canonical.math_parameterization, "v1_1_2_canonical_nurbs_parameterization");
  });

  test("uses manifest canonical data after generation", () => {
    const preset = presets[0];
    const manifest = {
      geometry: {
        surface_graph: {
          canonical_nurbs_parameterization: {
            canonical_payload_version: "1.1.2",
            math_parameterization: "v1_1_2_canonical_nurbs_parameterization",
            canonical_input_source: "translated_from_frontend_handles",
            support_profiles: { hub_profile: { control_points: [[1, 2]] }, tip_or_shroud_profile: { control_points: [[3, 4]] } },
            active_span_policy: { root_offset: { resolved_constant_mm: 14 }, tip_offset: { resolved_constant_mm: 0 } },
            blade_population: { main_blade_count: 8, splitter_blade_count: 8 },
            section_loop_family: { span_stations_h: [0, 0.25, 0.5, 0.75, 1] },
          },
        },
      },
    };

    const resolved = resolvedCanonicalParameterization(preset, manifest);
    assert.equal(resolved.sourceLabel, "resolved manifest");
    assert.equal(resolved.canonical.canonical_input_source, "translated_from_frontend_handles");
  });

  test("returns top meridional blade-to-blade and span station tabs", () => {
    const tabs = parameterViewTabs(presets[0], null);

    assert.deepEqual(tabs.map((tab) => tab.id), ["top", "meridional", "blade_to_blade", "span_station"]);
    assert.ok(tabs.every((tab) => tab.annotations.length > 0));
  });
});
