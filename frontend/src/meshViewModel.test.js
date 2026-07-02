import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { meshQualitySummary, meshViewModes } from "./meshViewModel.js";

describe("mesh view model", () => {
  test("meshViewModes includes surface mesh inspection", () => {
    assert.deepEqual(meshViewModes.map((mode) => mode.id), ["patches", "mesh", "quality"]);
  });

  test("meshQualitySummary formats mesh manifest metrics", () => {
    const summary = meshQualitySummary({
      triangle_count: 12,
      degenerate_triangle_count: 1,
      quality_metrics: { min_area: 0.25, max_area: 4, max_aspect_ratio: 8.5 },
    });

    assert.deepEqual(summary, {
      triangleCount: 12,
      degenerateTriangleCount: 1,
      minArea: 0.25,
      maxArea: 4,
      maxAspectRatio: 8.5,
    });
  });
});
