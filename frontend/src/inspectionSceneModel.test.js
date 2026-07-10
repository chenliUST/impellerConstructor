import assert from "node:assert/strict";
import { describe, test } from "node:test";

import * as inspectionSceneModel from "./inspectionSceneModel.js";

const {
  inspectionViewportRects,
  orthographicCameraFrame,
  projectionContextSignature,
  projectionFailureNotificationKey,
  resolveInspectionAnchor,
  selectedProjectionFailureKey,
  viewportAtPointer,
} = inspectionSceneModel;

describe("inspection scene model", () => {
  test("quad reserves one pane for S-Q and three for shared-scene cameras", () => {
    const rects = inspectionViewportRects(1200, 800, "quad");

    assert.deepEqual(Object.keys(rects), ["3d", "meridional", "s_q", "top"]);
    assert.deepEqual(rects["3d"], { x: 0, y: 400, width: 600, height: 400 });
    assert.deepEqual(rects["s_q"], { x: 0, y: 0, width: 600, height: 400 });
  });

  test("full-size layout allocates the complete viewport", () => {
    assert.deepEqual(inspectionViewportRects(900, 600, "3d")["3d"], {
      x: 0,
      y: 0,
      width: 900,
      height: 600,
    });
  });

  test("top and meridional frames are deterministic", () => {
    const bounds = { center: [0, 0, 0], radius: 500 };

    assert.deepEqual(orthographicCameraFrame(bounds, "top", 2).up, [0, 1, 0]);
    assert.deepEqual(orthographicCameraFrame(bounds, "meridional", 2).up, [0, 0, 1]);
  });

  test("surface anchors use the finite uv-grid centroid for both supported names", () => {
    const surfaceGraph = {
      surfaces: [{
        id: "blade-pressure",
        uv_grid: [
          [[0, 2, 4], [2, 4, 6]],
          [[4, 6, 8], [Number.NaN, 0, 0]],
        ],
      }],
    };

    for (const kind of ["surface_centroid", "surface"]) {
      assert.deepEqual(
        resolveInspectionAnchor({ kind, surfaceId: "blade-pressure" }, null, surfaceGraph),
        [2, 4, 6],
      );
    }
  });

  test("span-station anchors use the generated loop points_xyz centroid", () => {
    const manifest = {
      parameter_inspection: {
        span_stations: {
          "blade-2:span-1": { source_blade_index: 1, source_loop_index: 0 },
        },
      },
    };
    const surfaceGraph = {
      blade_to_blade_loop_family: {
        blades: [
          { loops: [] },
          {
            loops: [{
              segments: {
                pressure_side: { points_xyz: [[0, 0, 0], [2, 0, 0]] },
                suction_side: { points_xyz: [[2, 2, 0]] },
                leading_edge: { points_xyz: [[0, 2, 0], [Infinity, 1, 1]] },
                trailing_edge: { points_xyz: [[1, 1, 4]] },
                unrelated: { points_xyz: [[100, 100, 100]] },
              },
            }],
          },
        ],
      },
    };

    assert.deepEqual(
      resolveInspectionAnchor(
        { kind: "span_station", spanStationId: "blade-2:span-1" },
        manifest,
        surfaceGraph,
      ),
      [1, 1, 0.8],
    );
  });

  test("span-station anchors reject missing references and non-finite generated points", () => {
    const manifest = {
      parameter_inspection: {
        span_stations: {
          broken: { source_blade_index: 0, source_loop_index: 0 },
        },
      },
    };
    const surfaceGraph = {
      blade_to_blade_loop_family: {
        blades: [{ loops: [{ segments: { pressure_side: { points_xyz: [[NaN, 0, 0]] } } }] }],
      },
    };

    assert.equal(resolveInspectionAnchor({ kind: "span_station", spanStationId: "missing" }, manifest, surfaceGraph), null);
    assert.equal(resolveInspectionAnchor({ kind: "span_station", spanStationId: "broken" }, manifest, surfaceGraph), null);
  });

  test("profile-rz anchors require an explicit finite point", () => {
    assert.deepEqual(resolveInspectionAnchor({ kind: "profile_rz", point: [12, 34] }), [12, 0, 34]);
    assert.equal(resolveInspectionAnchor({ kind: "profile_rz", point: [12] }), null);
    assert.equal(resolveInspectionAnchor({ kind: "profile_rz", point: [12, NaN] }), null);
  });

  test("viewport-corner anchors preserve a deterministic label-rail corner", () => {
    assert.deepEqual(resolveInspectionAnchor({ kind: "viewport_corner" }), { viewportCorner: "top_right" });
    assert.deepEqual(
      resolveInspectionAnchor({ kind: "viewport_corner", corner: "bottom_left" }),
      { viewportCorner: "bottom_left" },
    );
  });

  test("picking maps the pointer through the matching geometric scissor viewport", () => {
    assert.equal(typeof viewportAtPointer, "function");
    const rects = inspectionViewportRects(1200, 800, "quad");
    const canvasRect = { left: 100, top: 50, width: 1200, height: 800 };

    assert.deepEqual(viewportAtPointer(400, 250, canvasRect, rects, ["3d", "meridional", "top"]), {
      viewId: "3d",
      pointer: { x: 0, y: 0 },
    });
    assert.deepEqual(viewportAtPointer(1000, 650, canvasRect, rects, ["3d", "meridional", "top"]), {
      viewId: "top",
      pointer: { x: 0, y: 0 },
    });
    assert.equal(viewportAtPointer(400, 650, canvasRect, rects, ["3d", "meridional", "top"]), null);
  });

  test("internal quad seams belong to exactly one higher-coordinate neighbor", () => {
    const rects = inspectionViewportRects(1200, 800, "quad");
    const canvasRect = { left: 100, top: 50, width: 1200, height: 800 };

    assert.deepEqual(viewportAtPointer(700, 250, canvasRect, rects, ["3d", "meridional", "top"]), {
      viewId: "meridional",
      pointer: { x: -1, y: 0 },
    });
    assert.deepEqual(viewportAtPointer(1000, 450, canvasRect, rects, ["3d", "meridional", "top"]), {
      viewId: "meridional",
      pointer: { x: 0, y: -1 },
    });
    assert.deepEqual(viewportAtPointer(700, 450, canvasRect, rects, ["3d", "meridional", "top"]), {
      viewId: "meridional",
      pointer: { x: -1, y: -1 },
    });
  });

  test("outer canvas edges remain hittable", () => {
    const rects = inspectionViewportRects(1200, 800, "quad");
    const canvasRect = { left: 100, top: 50, width: 1200, height: 800 };

    assert.deepEqual(viewportAtPointer(1300, 250, canvasRect, rects, ["3d", "meridional", "top"]), {
      viewId: "meridional",
      pointer: { x: 1, y: 0 },
    });
    assert.deepEqual(viewportAtPointer(1000, 50, canvasRect, rects, ["3d", "meridional", "top"]), {
      viewId: "meridional",
      pointer: { x: 0, y: 1 },
    });
  });

  test("selected projection failure keys distinguish failing annotation identities", () => {
    assert.equal(typeof selectedProjectionFailureKey, "function");
    const projectAnchorForView = () => (anchor) => anchor.resolvable ? { x: 10, y: 20 } : null;
    const failureKeyA = selectedProjectionFailureKey(
      { "3d": [{ id: "surface-a", selected: true, anchor: { resolvable: false } }] },
      ["3d"],
      projectAnchorForView,
    );
    const failureKeyB = selectedProjectionFailureKey(
      { "3d": [{ id: "surface-b", selected: true, anchor: { resolvable: false } }] },
      ["3d"],
      projectAnchorForView,
    );

    assert.equal(failureKeyA, '[["3d","surface-a"]]');
    assert.equal(failureKeyB, '[["3d","surface-b"]]');
    assert.notEqual(failureKeyA, failureKeyB);
  });

  test("selected projection failure keys are deterministic across view and annotation order", () => {
    assert.equal(typeof selectedProjectionFailureKey, "function");
    const projectAnchorForView = () => () => null;
    const annotationsByView = {
      top: [
        { id: "zeta", selected: true, anchor: {} },
        { id: "ignored", selected: false, anchor: {} },
      ],
      "3d": [{ id: "alpha", selected: true, anchor: {} }],
    };

    assert.equal(
      selectedProjectionFailureKey(annotationsByView, ["top", "3d"], projectAnchorForView),
      '[["3d","alpha"],["top","zeta"]]',
    );
    assert.equal(
      selectedProjectionFailureKey(annotationsByView, ["3d", "top"], projectAnchorForView),
      '[["3d","alpha"],["top","zeta"]]',
    );
  });

  test("projection notification keys distinguish the same failure across generation ids", () => {
    assert.equal(typeof projectionContextSignature, "function");
    assert.equal(typeof projectionFailureNotificationKey, "function");
    const annotations = {
      "3d": [{ id: "same-surface", selected: true, anchor: { kind: "surface", surfaceId: "same" } }],
    };
    const contextA = projectionContextSignature({ generation_id: "generation-a" }, annotations, ["3d"]);
    const contextB = projectionContextSignature({ generation_id: "generation-b" }, annotations, ["3d"]);

    assert.notEqual(contextA, contextB);
    assert.notEqual(
      projectionFailureNotificationKey('[["3d","same-surface"]]', contextA, 4),
      projectionFailureNotificationKey('[["3d","same-surface"]]', contextB, 4),
    );
  });

  test("projection notification keys distinguish changed selection and anchor context", () => {
    assert.equal(typeof projectionContextSignature, "function");
    assert.equal(typeof projectionFailureNotificationKey, "function");
    const manifest = { generation_id: "generation-a" };
    const selectedContext = projectionContextSignature(
      manifest,
      { "3d": [{ id: "same", selected: true, anchor: { kind: "surface", surfaceId: "surface-a" } }] },
      ["3d"],
    );
    const changedContext = projectionContextSignature(
      manifest,
      { "3d": [{ id: "same", selected: true, anchor: { kind: "surface", surfaceId: "surface-b" } }] },
      ["3d"],
    );

    assert.notEqual(selectedContext, changedContext);
    assert.notEqual(
      projectionFailureNotificationKey('[["3d","same"]]', selectedContext, 4),
      projectionFailureNotificationKey('[["3d","same"]]', changedContext, 4),
    );
  });

  test("stable projection context and epoch produce a stable notification key", () => {
    assert.equal(typeof projectionContextSignature, "function");
    assert.equal(typeof projectionFailureNotificationKey, "function");
    const manifest = { generation_id: "generation-a" };
    const firstContext = projectionContextSignature(
      manifest,
      { "3d": [{ id: "same", selected: true, anchor: { kind: "surface", surfaceId: "surface-a" } }] },
      ["3d"],
    );
    const equivalentContext = projectionContextSignature(
      manifest,
      { "3d": [{ id: "same", selected: true, anchor: { surfaceId: "surface-a", kind: "surface" } }] },
      ["3d"],
    );
    const stableKey = projectionFailureNotificationKey('[["3d","same"]]', firstContext, 4);

    assert.equal(firstContext, equivalentContext);
    assert.equal(stableKey, projectionFailureNotificationKey('[["3d","same"]]', equivalentContext, 4));
    assert.notEqual(stableKey, projectionFailureNotificationKey('[["3d","same"]]', equivalentContext, 5));
  });
});
