import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { meshInspectionSummary, meshQualitySummary, meshViewModes } from "./meshViewModel.js";

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

  test("meshInspectionSummary surfaces mesh type and transition coverage", () => {
    const summary = meshInspectionSummary({
      mesh_type: "transition_aware_surface_mesh",
      triangle_count: 120,
      degenerate_triangle_count: 1,
      quality_metrics: { max_aspect_ratio: 8.5 },
      transition_regions: [
        { surface_graph_id: "root", triangle_count: 24 },
        { surface_graph_id: "tip", triangle_count: 16 },
      ],
    });

    assert.deepEqual(summary, {
      meshType: "transition_aware_surface_mesh",
      triangleCount: 120,
      degenerateTriangleCount: 1,
      minArea: 0,
      maxArea: 0,
      maxAspectRatio: 8.5,
      transitionRegionCount: 2,
      transitionTriangleCount: 40,
      hasTransitionRegions: true,
    });
  });

  test("meshInspectionSummary makes absent transition regions explicit", () => {
    const summary = meshInspectionSummary({ mesh_type: "surface_triangles", triangle_count: 12 });

    assert.equal(summary.meshType, "surface_triangles");
    assert.equal(summary.transitionRegionCount, 0);
    assert.equal(summary.transitionTriangleCount, 0);
    assert.equal(summary.hasTransitionRegions, false);
  });
});
