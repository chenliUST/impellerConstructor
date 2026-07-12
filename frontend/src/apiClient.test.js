import assert from "node:assert/strict";
import { afterEach, describe, test } from "node:test";

import { instantiateImpeller, instantiatePresetImpeller } from "./apiClient.js";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("impeller API client", () => {
  test("instantiatePresetImpeller sends no defaults from another preset", async () => {
    let requestBody = null;
    globalThis.fetch = async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return new Response(JSON.stringify({ manifest: {}, run_id: "run-preset" }), { status: 200 });
    };

    await instantiatePresetImpeller("http://api.test", "engine-preset");

    assert.deepEqual(requestBody, {
      parameters: {},
      geometry_stage: "edge_closures",
    });
  });

  test("instantiatePresetImpeller opts into compact drawing review responses explicitly", async () => {
    let requestBody = null;
    globalThis.fetch = async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return new Response(JSON.stringify({ manifest: {}, run_id: "run-review" }), { status: 200 });
    };

    await instantiatePresetImpeller("http://api.test", "engine-review", "edge_closures", "review_summary");

    assert.deepEqual(requestBody, {
      parameters: {},
      geometry_stage: "edge_closures",
      response_mode: "review_summary",
    });
  });

  test("instantiateImpeller keeps geometryStage positional compatibility and appends transition and section-loop overrides", async () => {
    let requestBody = null;
    globalThis.fetch = async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return new Response(JSON.stringify({ manifest: {}, run_id: "run-1" }), { status: 200 });
    };

    const transitionOverrides = {
      "blade_root_to_hub.default": {
        enabled: true,
        treatment: "fillet",
        radius_mm: 3,
      },
    };
    const sectionLoopOverrides = {
      blade_section_loop_template: {
        stations: [{ eta: 0, max_thickness_mm: 40 }],
      },
    };

    await instantiateImpeller(
      "http://api.test",
      "engine-1",
      {},
      null,
      null,
      "blade_surfaces",
      transitionOverrides,
      sectionLoopOverrides,
    );

    assert.equal(requestBody.geometry_stage, "blade_surfaces");
    assert.deepEqual(requestBody.transition_overrides, transitionOverrides);
    assert.deepEqual(requestBody.section_loop_overrides, sectionLoopOverrides);
  });

  test("instantiateImpeller posts blade-to-blade loop family overrides", async () => {
    let requestBody = null;
    globalThis.fetch = async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return new Response(JSON.stringify({ manifest: {}, run_id: "run-v11" }), { status: 200 });
    };

    const bladeToBladeLoopFamilyOverrides = {
      main: { mid_camber_q_mm: [0, 20, -12, 8, 0] },
    };

    await instantiateImpeller(
      "http://api.test",
      "engine-v11",
      {},
      null,
      null,
      "full",
      null,
      null,
      bladeToBladeLoopFamilyOverrides,
    );

    assert.deepEqual(requestBody.blade_to_blade_loop_family_overrides, bladeToBladeLoopFamilyOverrides);
  });
});
