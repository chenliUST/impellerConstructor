import assert from "node:assert/strict";
import { afterEach, describe, test } from "node:test";

import { instantiateImpeller } from "./apiClient.js";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("impeller API client", () => {
  test("instantiateImpeller keeps geometryStage positional compatibility and appends transition overrides", async () => {
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

    await instantiateImpeller("http://api.test", "engine-1", {}, null, null, "blade_surfaces", transitionOverrides);

    assert.equal(requestBody.geometry_stage, "blade_surfaces");
    assert.deepEqual(requestBody.transition_overrides, transitionOverrides);
  });
});
