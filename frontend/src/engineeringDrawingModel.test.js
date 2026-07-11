import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  engineeringDrawingBounds,
  layoutEngineeringDimension,
  projectEngineeringFeature,
} from "./engineeringDrawingModel.js";

const FRAME = {
  bounds: { minX: 0, minY: 0, maxX: 100, maxY: 50 },
  viewport: { x: 0, y: 0, width: 240, height: 160 },
};

const VIEWPORT = { x: 0, y: 0, width: 240, height: 160 };

function path(points) {
  return { kind: "path", points, className: "engineering-feature-context" };
}

function assertPadded(primitives, viewport = VIEWPORT) {
  const bounds = engineeringDrawingBounds(primitives, []);
  assert.ok(bounds);
  assert.ok(bounds.minX >= viewport.x + 16, `minX ${bounds.minX}`);
  assert.ok(bounds.maxX <= viewport.x + viewport.width - 16, `maxX ${bounds.maxX}`);
  assert.ok(bounds.minY >= viewport.y + 16, `minY ${bounds.minY}`);
  assert.ok(bounds.maxY <= viewport.y + viewport.height - 16, `maxY ${bounds.maxY}`);
}

describe("engineering drawing projection", () => {
  test("projects top coordinates as x and y with an equal-aspect frame", () => {
    const drawing = projectEngineeringFeature({
      id: "blade-edge",
      kind: "polyline",
      points: [[0, 0, 9], [100, 50, -4]],
    }, "top", FRAME);

    assert.equal(drawing.kind, "path");
    assert.equal(drawing.className, "engineering-feature-selected");
    assert.deepEqual(drawing.points.map((point) => point.length), [2, 2]);
    assert.equal(drawing.points[1][0] - drawing.points[0][0], 2 * (drawing.points[1][1] - drawing.points[0][1]));
    assertPadded([drawing]);
  });

  test("projects meridional coordinates as radius and z", () => {
    const drawing = projectEngineeringFeature({
      id: "hub-profile",
      kind: "polyline",
      points: [[3, 4, 10], [0, 10, 30]],
    }, "meridional");

    assert.deepEqual(drawing.points, [[5, 10], [10, 30]]);
  });

  test("uses metric S-Q display coordinates without returning normalized coordinates", () => {
    const drawing = projectEngineeringFeature({
      id: "pressure-side",
      kind: "nurbs_curve",
      control_points: [[0, 0], [1, 1]],
      display_control_points_s_q_mm: [[12, -8], [48, 16]],
    }, "s_q");

    assert.deepEqual(drawing.points, [[12, -8], [48, 16]]);
  });

  test("returns null for non-finite feature coordinates", () => {
    assert.equal(projectEngineeringFeature({
      id: "invalid",
      kind: "point",
      coordinates: [0, Number.NaN, 2],
    }, "top", FRAME), null);
    assert.equal(projectEngineeringFeature({
      id: "invalid-curve",
      kind: "polyline",
      points: [[0, 0, 0], [10, Number.POSITIVE_INFINITY, 4]],
    }, "top", FRAME), null);
  });
});

describe("engineering dimension layout", () => {
  for (const [kind, definition] of [
    ["linear", { measurement_points: [[60, 60], [130, 60]] }],
    ["angular", {
      measurement_points: [[90, 90], [120, 90]],
      reference_direction: [1, 0],
      measured_direction: [0, 1],
    }],
    ["arc_height", { measurement_points: [[60, 60], [130, 60], [95, 95]] }],
    ["ordinate", { measurement_points: [[50, 50], [110, 85]] }],
    ["control_coordinate", { measurement_points: [[50, 50], [110, 85]] }],
  ]) {
    test(`lays out ${kind} dimensions as padded blue dimension primitives`, () => {
      const primitives = layoutEngineeringDimension({
        kind,
        unit: "mm",
        resolvedValue: 12.5,
        note: "secondary note",
        ...definition,
      }, [path([[40, 40], [170, 120]])], VIEWPORT);

      assert.equal(primitives.length, 1);
      const [dimension] = primitives;
      assert.equal(dimension.kind, "dimension");
      assert.equal(dimension.className, "engineering-dimension");
      assert.equal(dimension.line.className, "engineering-dimension");
      assert.ok(dimension.extensions.length > 0);
      assert.ok(dimension.arrows.length > 0);
      assert.ok(dimension.extensions.every((line) => line.className === "engineering-dimension"));
      assert.ok(dimension.arrows.every((arrow) => arrow.className === "engineering-dimension"));
      assert.equal(dimension.text.className, "engineering-dimension");
      assertPadded(primitives);
    });
  }

  test("suppresses the secondary note before a dimension reaches context bounds", () => {
    const context = [path([[20, 30], [220, 130]])];
    const [dimension] = layoutEngineeringDimension({
      kind: "linear",
      measurement_points: [[70, 40], [140, 40]],
      unit: "mm",
      resolvedValue: 70,
      note: "outside placement note",
    }, context, VIEWPORT);

    const contextBounds = engineeringDrawingBounds(context, []);
    assert.equal(dimension.note, null);
    assert.ok(dimension.line.points.every((point) => point[1] <= contextBounds.minY));
    assertPadded([dimension]);
  });
});

test("combines finite context and selected primitive bounds", () => {
  assert.deepEqual(
    engineeringDrawingBounds(
      [path([[0, 5], [4, 8]])],
      [{ kind: "point", point: [10, -2], className: "engineering-feature-selected" }],
    ),
    { minX: 0, minY: -2, maxX: 10, maxY: 8, width: 10, height: 10, center: [5, 3] },
  );
});
