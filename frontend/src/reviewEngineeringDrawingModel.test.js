import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  dimensionLayout,
  drawingBounds,
  drawingContractStatus,
  fitDrawingFrame,
  representativeBladeGraph,
} from "./reviewEngineeringDrawingModel.js";

describe("review engineering drawing model", () => {
  test("bounds handle public-preset surface projections without argument-stack expansion", () => {
    const points = Array.from({ length: 250000 }, (_, index) => [index - 125000, 2 * index - 100]);
    assert.deepEqual(drawingBounds(points), {
      minX: -125000,
      maxX: 124999,
      minY: -100,
      maxY: 499898,
    });
  });

  test("accepts only the current generation semantic contract", () => {
    const contract = { contract_version: "1.1.5", generation_id: "geometry-1" };
    assert.equal(drawingContractStatus(contract, "geometry-1"), "ready");
    assert.equal(drawingContractStatus(contract, "geometry-2"), "stale");
    assert.equal(drawingContractStatus({ ...contract, contract_version: "1.1.3" }), "unsupported");
  });

  test("lays dimensions out from geometry witnesses and assigns external lanes", () => {
    const frame = fitDrawingFrame(
      [{ points: [[-10, -5], [10, 5]] }],
      [],
      { x: 0, y: 0, width: 400, height: 300 },
      40,
    );
    const layout = dimensionLayout({
      id: "diameter",
      kind: "diameter",
      label: "Ø 20",
      witness_points: [[-10, 0], [10, 0]],
    }, frame, 1);

    assert.deepEqual(layout.witnessStart, frame.map([-10, 0]));
    assert.deepEqual(layout.witnessEnd, frame.map([10, 0]));
    assert.equal(layout.lineStart[1], 260);
    assert.equal(layout.lineEnd[1], 260);
  });

  test("isolates one blade surface family for the shared WebGL renderer", () => {
    const graph = { surfaces: [{ id: "blade_0_pressure" }, { id: "blade_1_pressure" }, { id: "hub" }] };
    const isolated = representativeBladeGraph(graph, ["blade_1_pressure"]);
    assert.deepEqual(isolated.surfaces, [{ id: "blade_1_pressure" }]);
  });
});
