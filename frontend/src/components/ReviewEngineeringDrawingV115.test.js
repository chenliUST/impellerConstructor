import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..", "..");

describe("V1.1.5 engineering drawing source contract", () => {
  test("top renders surface projections and class-aware section groups", () => {
    const source = readFileSync(resolve(root, "src/components/ReviewEngineeringDrawing.js"), "utf-8");
    assert.match(source, /surface_projection_paths/);
    assert.match(source, /blade_class/);
    assert.match(source, /material_regions/);
    assert.match(source, /side_view/);
    assert.match(source, /ConstructionTables/);
    assert.doesNotMatch(source, /outline_paths/);
  });

  test("3D blade scene overlays five XYZ loops and uses enlarged orthographic framing", () => {
    const source = readFileSync(resolve(root, "src/components/EngineeringBladePairScene.js"), "utf-8");
    assert.match(source, /overlay_loops_xyz/);
    assert.match(source, /section-loop-overlay/);
    assert.match(source, /Math\.min\(Math\.max\(window\.devicePixelRatio \|\| 1, 2\), 3\)/);
    assert.match(source, /radius \* 0\.9/);
  });
});
