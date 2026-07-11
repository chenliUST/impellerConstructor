import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..", "..");
const scenePath = resolve(root, "src/components/BladeFeatureScene.js");

function source() {
  assert.equal(existsSync(scenePath), true, "BladeFeatureScene.js should exist");
  return readFileSync(scenePath, "utf-8");
}

describe("BladeFeatureScene source contract", () => {
  test("filters the graph to the selected blade context before creating its group", () => {
    const component = source();

    assert.match(component, /function bladeContextSurfaceGraph\(surfaceGraph, bladeSurfaceIds\)/);
    assert.match(component, /const selectedSurfaceIdSet = new Set\(bladeSurfaceIds\)/);
    assert.match(component, /surfaces:\s*\(surfaceGraph\?\.surfaces \|\| \[\]\)\.filter\(/);
    assert.match(component, /selectedSurfaceIdSet\.has\(surface\.id \|\| surface\.surface_graph_id\)/);
    assert.match(component, /const contextSurfaceGraph = bladeContextSurfaceGraph\(surfaceGraph, bladeSurfaceIds\)/);
    assert.match(component, /createSurfaceGraphGroup\(\s*contextSurfaceGraph,\s*bounds\.center,\s*"cad_review_360",\s*new Set\(\),\s*"off",\s*manifest,?\s*\)/);
  });

  test("keeps context monochrome and renders selected features separately in red", () => {
    const component = source();

    assert.match(component, /material\.color\.set\("#ffffff"\)/);
    assert.match(component, /material\.emissive\.set\("#000000"\)/);
    assert.match(component, /new THREE\.EdgesGeometry\(mesh\.geometry, 35\)/);
    assert.match(component, /new THREE\.LineBasicMaterial\(\{ color: "#111111"/);
    assert.doesNotMatch(component, /selected \? "#111111" : "#ffffff"/);
    assert.match(component, /const featureGroup = new THREE\.Group\(\)/);
    assert.match(component, /featureGroup\.userData\.isEngineeringFeature = true/);
    assert.match(component, /feature\.kind === "nurbs_curve"/);
    assert.match(component, /feature\.kind === "polyline"/);
    assert.match(component, /feature\.kind === "control_point" \|\| feature\.kind === "point"/);
    assert.match(component, /color: "#c40000"/);
    assert.match(component, /new THREE\.Points\(/);
  });

  test("suppresses source overlays and releases the renderer and context on cleanup", () => {
    const component = source();

    assert.match(component, /child\.userData\.isSurfaceUvWire \|\| child\.userData\.isMeshOverlay/);
    assert.match(component, /child\.visible = false/);
    assert.match(component, /inspectionRendererLifecycle\.register\(renderer\)/);
    assert.match(component, /disposeObject\(contextGroup\)/);
    assert.match(component, /disposeObject\(featureGroup\)/);
    assert.match(component, /renderer\.dispose\(\)/);
    assert.match(component, /releaseRendererLifecycle\(\)/);
    assert.match(component, /data-renderer-live-count/);
    assert.match(component, /data-context-live-count/);
  });
});
