import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..", "..");

describe("ReviewEngineeringDrawing", () => {
  test("uses semantic drawing data instead of raw surface bounds", () => {
    const source = readFileSync(resolve(root, "src/components/ReviewEngineeringDrawing.js"), "utf-8");
    assert.match(source, /contract\.views\.top/);
    assert.match(source, /cross_sections/);
    assert.match(source, /control_polygons/);
    assert.match(source, /EngineeringBladePairScene/);
    assert.doesNotMatch(source, /surfaceBoundary|rawBounds|FLOWPATH WIDTH|uv_grid/);
  });

  test("shared blade scene is high-DPI orthographic and hides UV overlays", () => {
    const source = readFileSync(resolve(root, "src/components/EngineeringBladePairScene.js"), "utf-8");
    assert.match(source, /OrthographicCamera/);
    assert.match(source, /setScissor/);
    assert.match(source, /devicePixelRatio/);
    assert.match(source, /isSurfaceUvWire/);
    assert.match(source, /EdgesGeometry/);
  });
});
