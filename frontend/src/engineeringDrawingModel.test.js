import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  engineeringDrawingBounds,
  layoutEngineeringDimension,
  projectEngineeringDimensionEvidence,
  projectEngineeringFeature,
} from "./engineeringDrawingModel.js";

const FRAME = {
  bounds: { minX: 0, minY: 0, maxX: 100, maxY: 50 },
  viewport: { x: 0, y: 0, width: 240, height: 160 },
};

const VIEWPORT = { x: 0, y: 0, width: 240, height: 160 };

function context(viewId, frame, primitives, projectPoint) {
  return { viewId, frame, primitives, ...(projectPoint ? { projectPoint } : {}) };
}

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

    assert.deepEqual(drawing.points[0], [12, -8]);
    assert.deepEqual(drawing.points.at(-1), [48, 16]);
    assert.equal(drawing.points.length, 65);
    assert.deepEqual(drawing.controlPoints, [[12, -8], [48, 16]]);
  });

  test("selects view-specific authoritative coordinates and rejects unsupported spaces", () => {
    const feature = {
      id: "leading-edge",
      kind: "polyline",
      coordinate_system: "model_xyz",
      points: [[3, 4, 10], [0, 10, 30]],
      display_points_s_q_mm: [[12, -8], [48, 16]],
    };

    assert.deepEqual(projectEngineeringFeature(feature, "top").points, [[3, 4], [0, 10]]);
    assert.deepEqual(projectEngineeringFeature(feature, "meridional").points, [[5, 10], [10, 30]]);
    assert.deepEqual(projectEngineeringFeature(feature, "s_q").points, [[12, -8], [48, 16]]);
    assert.equal(projectEngineeringFeature({
      id: "s-q-only",
      kind: "polyline",
      coordinate_system: "s_q_mm",
      points: [[0, 0], [1, 1]],
    }, "top"), null);
    const profile = projectEngineeringFeature({
      id: "hub-profile",
      kind: "nurbs_curve",
      coordinate_system: "profile_rz_mm",
      control_points: [[150, 400], [580, 0]],
    }, "meridional");
    assert.deepEqual([profile.points[0], profile.points.at(-1)], [[150, 400], [580, 0]]);
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

  test("evaluates the authoritative rational NURBS separately from its control polygon", () => {
    const curve = projectEngineeringFeature({
      id: "rational-quarter-arc",
      kind: "nurbs_curve",
      degree: 2,
      knots: [0, 0, 0, 1, 1, 1],
      weights: [1, Math.SQRT1_2, 1],
      control_points: [[1, 0], [1, 1], [0, 1]],
    }, "s_q");

    assert.deepEqual(curve.controlPoints, [[1, 0], [1, 1], [0, 1]]);
    assert.equal(curve.points.length, 65);
    assert.ok(Math.abs(curve.points[32][0] - Math.SQRT1_2) < 1e-9);
    assert.ok(Math.abs(curve.points[32][1] - Math.SQRT1_2) < 1e-9);
    assert.notDeepEqual(curve.points[32], curve.controlPoints[1]);
  });

  test("projects raw dimension anchors for joint workspace framing", () => {
    assert.deepEqual(
      projectEngineeringDimensionEvidence({ measurement_points: [[10, 20], [30, 40]] }, "meridional")
        .map((primitive) => primitive.point),
      [[10, 20], [30, 40]],
    );
    assert.deepEqual(
      projectEngineeringDimensionEvidence({
        measurement_points: [[0, 0], [1, 1]],
        display_measurement_points_s_q_mm: [[12, -8], [48, 16]],
      }, "s_q").map((primitive) => primitive.point),
      [[12, -8], [48, 16]],
    );
  });
});

describe("engineering dimension layout", () => {
  test("projects raw dimension endpoints through the feature context in every engineering view", () => {
    const cases = [
      {
        viewId: "top",
        frame: { bounds: { minX: 0, minY: 0, maxX: 100, maxY: 100 }, viewport: VIEWPORT },
        feature: { points: [[10, 20, 30], [70, 80, 90]] },
        dimension: { measurement_points: [[10, 20, 30], [70, 80, 90]] },
      },
      {
        viewId: "meridional",
        frame: { bounds: { minX: 0, minY: 0, maxX: 20, maxY: 40 }, viewport: VIEWPORT },
        feature: { points: [[3, 4, 10], [0, 10, 30]] },
        dimension: { measurement_points: [[3, 4, 10], [0, 10, 30]] },
      },
      {
        viewId: "s_q",
        frame: { bounds: { minX: 0, minY: -20, maxX: 60, maxY: 20 }, viewport: VIEWPORT },
        feature: {
          points: [[0, 0], [1, 1]],
          display_points_s_q_mm: [[12, -8], [48, 16]],
        },
        dimension: {
          measurement_points: [[0, 0], [1, 1]],
          display_measurement_points_s_q_mm: [[12, -8], [48, 16]],
        },
      },
    ];

    for (const fixture of cases) {
      const feature = projectEngineeringFeature({
        id: `${fixture.viewId}-feature`,
        kind: "polyline",
        ...fixture.feature,
      }, fixture.viewId, fixture.frame);
      const [dimension] = layoutEngineeringDimension({
        kind: "linear",
        unit: "mm",
        resolvedValue: 1,
        ...fixture.dimension,
      }, context(fixture.viewId, fixture.frame, [feature]), VIEWPORT);

      assert.deepEqual(dimension.extensions.map((extension) => extension.points[0]), feature.points, fixture.viewId);
    }
  });

  test("projects meridional angular reference vectors from their engineering origin", () => {
    const frame = { bounds: { minX: 0, minY: 0, maxX: 20, maxY: 40 }, viewport: VIEWPORT };
    const feature = projectEngineeringFeature({
      id: "meridional-reference",
      kind: "polyline",
      points: [[3, 4, 10], [4, 4, 10]],
    }, "meridional", frame);
    const dimensions = layoutEngineeringDimension({
      kind: "angular",
      measurement_points: [[3, 4, 10], [4, 4, 10]],
      reference_direction: [1, 0, 0],
      measured_direction: [0, 0, 1],
      unit: "deg",
      resolvedValue: 90,
    }, context("meridional", frame, [feature]), VIEWPORT);

    assert.deepEqual(dimensions, [], "an angular annotation that cannot fit must fail instead of clamping anchors");
  });

  test("uses metric S-Q display vectors for angular references", () => {
    const frame = { bounds: { minX: 0, minY: -20, maxX: 60, maxY: 20 }, viewport: VIEWPORT };
    const feature = projectEngineeringFeature({
      id: "s-q-reference",
      kind: "polyline",
      points: [[0, 0], [1, 0]],
      display_points_s_q_mm: [[12, -8], [24, -8]],
    }, "s_q", frame);
    const dimensions = layoutEngineeringDimension({
      kind: "angular",
      measurement_points: [[0, 0], [1, 0]],
      display_measurement_points_s_q_mm: [[12, -8], [24, -8]],
      reference_direction: [1, 0],
      measured_direction: [0, 1],
      display_reference_direction_s_q_mm: [12, 0],
      display_measured_direction_s_q_mm: [0, 12],
      unit: "deg",
      resolvedValue: 90,
    }, context("s_q", frame, [feature]), VIEWPORT);

    assert.deepEqual(dimensions, [], "an angular annotation that cannot fit must fail instead of clamping anchors");
  });

  for (const [kind, definition] of [
    ["linear", { measurement_points: [[25, 25], [60, 25]] }],
    ["angular", {
      measurement_points: [[40, 40], [55, 40]],
      reference_direction: [1, 0],
      measured_direction: [0, 1],
    }],
    ["arc_height", { measurement_points: [[25, 25], [60, 25], [42, 50]] }],
    ["ordinate", { measurement_points: [[25, 25], [50, 45]] }],
    ["control_coordinate", { measurement_points: [[25, 25], [50, 45]] }],
  ]) {
    test(`lays out ${kind} dimensions as padded blue dimension primitives`, () => {
      const frame = { bounds: { minX: 0, minY: 0, maxX: 100, maxY: 100 }, viewport: VIEWPORT };
      const feature = projectEngineeringFeature({
        id: `${kind}-context`,
        kind: "polyline",
        points: [[20, 20], [80, 80]],
      }, "s_q", frame);
      const primitives = layoutEngineeringDimension({
        kind,
        unit: "mm",
        resolvedValue: 12.5,
        note: "secondary note",
        ...definition,
      }, context("s_q", frame, [feature]), VIEWPORT);

      assert.equal(primitives.length, kind === "angular" ? 0 : 1);
      if (kind === "angular") return;
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
    const dimensions = layoutEngineeringDimension({
      kind: "linear",
      measurement_points: [[70, 40], [140, 40]],
      unit: "mm",
      resolvedValue: 70,
      note: "outside placement note",
    }, { viewId: "s_q", primitives: context, projectPoint: (point) => [...point] }, VIEWPORT);

    const [dimension] = dimensions;
    const contextBounds = engineeringDrawingBounds(context, []);
    assert.equal(dimension.note, null);
    assert.ok(dimension.line.points.every((point) => point[1] <= contextBounds.minY));
    assertPadded([dimension]);
  });

  test("suppresses a note when a diagonal dimension segment crosses context despite outside endpoints", () => {
    const contextPrimitives = [path([[80, 50], [110, 90]])];
    const dimensions = layoutEngineeringDimension({
      kind: "linear",
      measurement_points: [[20, 20], [220, 140]],
      unit: "mm",
      resolvedValue: 1,
      note: "secondary note",
    }, { viewId: "s_q", primitives: contextPrimitives, projectPoint: (point) => [...point] }, VIEWPORT);

    assert.equal(dimensions.length, 1);
    const [dimension] = dimensions;
    assert.deepEqual(dimension.line.points, [[20, 20], [220, 140]], "measurement anchors must not be clamped");
    assert.equal(dimension.note, null);
  });

  test("retains a note when the dimension segment does not cross context", () => {
    const [dimension] = layoutEngineeringDimension({
      kind: "linear",
      measurement_points: [[20, 20], [220, 20]],
      unit: "mm",
      resolvedValue: 1,
      note: "secondary note",
    }, {
      viewId: "s_q",
      primitives: [path([[80, 50], [110, 90]])],
      projectPoint: (point) => [...point],
    }, VIEWPORT);

    assert.ok(dimension.note);
  });

  test("lays out radial dimensions from a center to one rim with a radius callout", () => {
    const [dimension] = layoutEngineeringDimension({
      kind: "radial",
      measurement_points: [[40, 70], [100, 70]],
      unit: "mm",
      resolvedValue: 60,
    }, { viewId: "s_q", primitives: [], projectPoint: (point) => [...point] }, VIEWPORT);

    assert.deepEqual(dimension.line.points, [[40, 70], [100, 70]]);
    assert.equal(dimension.arrows.length, 1);
    assert.equal(dimension.text.value, "R60 mm");
  });

  test("lays out diameter dimensions between opposed rims with two arrowheads", () => {
    const [dimension] = layoutEngineeringDimension({
      kind: "diameter",
      measurement_points: [[40, 70], [160, 70]],
      unit: "mm",
      resolvedValue: 120,
    }, { viewId: "s_q", primitives: [], projectPoint: (point) => [...point] }, VIEWPORT);

    assert.deepEqual(dimension.line.points, [[40, 70], [160, 70]]);
    assert.equal(dimension.arrows.length, 2);
    assert.equal(dimension.text.value, "DIA 120 mm");
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

test("includes a NURBS control polygon in drawing bounds", () => {
  assert.deepEqual(
    engineeringDrawingBounds([{ kind: "path", points: [[0, 0], [2, 0]], controlPoints: [[0, 0], [1, 5], [2, 0]] }], []),
    { minX: 0, minY: 0, maxX: 2, maxY: 5, width: 2, height: 5, center: [1, 2.5] },
  );
});
