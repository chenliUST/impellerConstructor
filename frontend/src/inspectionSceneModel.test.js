import assert from "node:assert/strict";
import { describe, test } from "node:test";

import * as inspectionSceneModel from "./inspectionSceneModel.js";

const {
  inspectionViewportRects,
  orthographicCameraFrame,
  viewportAtPointer,
  visibleGeometricViews,
} = inspectionSceneModel;

describe("inspection scene model", () => {
  test("renderer lifecycle registry reports cumulative and live renderer-context counts", () => {
    const registry = inspectionSceneModel.createRendererLifecycleRegistry();
    const releaseA = registry.register({ getContext: () => ({ id: "context-a" }) });
    assert.deepEqual(registry.snapshot(), {
      createdRendererCount: 1,
      liveRendererCount: 1,
      createdContextCount: 1,
      liveContextCount: 1,
    });
    releaseA();
    assert.equal(registry.snapshot().liveRendererCount, 0);
    assert.equal(registry.snapshot().liveContextCount, 0);

    const releaseB = registry.register({ getContext: () => ({ id: "context-b" }) });
    assert.deepEqual(registry.snapshot(), {
      createdRendererCount: 2,
      liveRendererCount: 1,
      createdContextCount: 2,
      liveContextCount: 1,
    });
    releaseB();
    releaseB();
    assert.equal(registry.snapshot().liveRendererCount, 0);
    assert.equal(registry.snapshot().liveContextCount, 0);
  });

  test("quad reserves one pane for S-Q and three for shared-scene cameras", () => {
    const rects = inspectionViewportRects(1200, 800, "quad");

    assert.deepEqual(Object.keys(rects), ["3d", "meridional", "s_q", "top"]);
    assert.deepEqual(rects["3d"], { x: 0, y: 400, width: 600, height: 400 });
    assert.deepEqual(rects["s_q"], { x: 0, y: 0, width: 600, height: 400 });
  });

  test("stacked quad maps visual top-to-bottom panes into lower-left WebGL rectangles", () => {
    const rects = inspectionViewportRects(820, 1000, "quad_stacked");

    assert.deepEqual(Object.keys(rects), ["3d", "meridional", "s_q", "top"]);
    assert.deepEqual(rects["3d"], { x: 0, y: 750, width: 820, height: 250 });
    assert.deepEqual(rects.meridional, { x: 0, y: 500, width: 820, height: 250 });
    assert.deepEqual(rects["s_q"], { x: 0, y: 250, width: 820, height: 250 });
    assert.deepEqual(rects.top, { x: 0, y: 0, width: 820, height: 250 });
    assert.deepEqual(visibleGeometricViews("quad_stacked"), ["3d", "meridional", "top"]);
  });

  test("stacked quad seams belong to the upper visual pane exactly once", () => {
    const rects = inspectionViewportRects(820, 1000, "quad_stacked");
    const canvasRect = { left: 0, top: 0, width: 820, height: 1000 };
    const viewIds = ["3d", "meridional", "s_q", "top"];

    assert.equal(viewportAtPointer(410, 250, canvasRect, rects, viewIds).viewId, "3d");
    assert.equal(viewportAtPointer(410, 500, canvasRect, rects, viewIds).viewId, "meridional");
    assert.equal(viewportAtPointer(410, 750, canvasRect, rects, viewIds).viewId, "s_q");
    assert.equal(
      viewportAtPointer(410, 750, canvasRect, rects, visibleGeometricViews("quad_stacked")),
      null,
    );
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

});
