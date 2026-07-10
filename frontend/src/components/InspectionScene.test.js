import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..", "..");
const scenePath = resolve(root, "src/components/InspectionScene.js");

describe("InspectionScene source contract", () => {
  test("uses one renderer and one shared scene with three scissor cameras", () => {
    assert.equal(existsSync(scenePath), true, "InspectionScene.js should exist");
    const source = readFileSync(scenePath, "utf-8");

    assert.equal((source.match(/new THREE\.WebGLRenderer/g) || []).length, 1);
    assert.equal((source.match(/new THREE\.Scene/g) || []).length, 1);
    assert.match(source, /renderer\.setScissorTest\(true\)/);
    assert.match(source, /"3d":\s*new THREE\.PerspectiveCamera\(45,\s*1,\s*0\.1,\s*100000\)/);
    assert.match(source, /top:\s*new THREE\.OrthographicCamera\(-1,\s*1,\s*1,\s*-1,\s*0\.1,\s*100000\)/);
    assert.match(source, /meridional:\s*new THREE\.OrthographicCamera\(-1,\s*1,\s*1,\s*-1,\s*0\.1,\s*100000\)/);
    assert.match(source, /new THREE\.Raycaster\(\)/);
    assert.match(source, /new ResizeObserver\(/);
    assert.match(source, /visibleGeometricViews\(layoutRef\.current\)/);
    assert.match(source, /renderer\.setViewport\(rect\.x,\s*rect\.y,\s*rect\.width,\s*rect\.height\)/);
    assert.match(source, /renderer\.setScissor\(rect\.x,\s*rect\.y,\s*rect\.width,\s*rect\.height\)/);
    assert.match(source, /renderer\.render\(scene,\s*cameras\[viewId\]\)/);
  });

  test("builds one monochrome surface group and updates mesh and contour selection in place", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.equal((source.match(/createSurfaceGraphGroup\(/g) || []).length, 1);
    assert.match(source, /createSurfaceGraphGroup\(\s*surfaceGraph,\s*bounds\.center,\s*"cad_review_360",\s*new Set\(\),\s*"off",\s*manifest,?\s*\)/);
    assert.match(source, /new THREE\.EdgesGeometry\(mesh\.geometry,\s*35\)/);
    assert.match(source, /isInspectionContour\s*=\s*true/);
    assert.match(source, /material\.color\.set\(selected \? "#111111" : "#ffffff"\)/);
    assert.match(source, /child\.material\.color\.set\(selected \? "#ffffff" : "#111111"\)/);
    assert.match(source, /depthTest:\s*true/);
    assert.doesNotMatch(source, /new THREE\.WireframeGeometry/);
    assert.match(source, /group\.traverse\(\(child\)/);
    assert.match(source, /selectedSurfaceIds/);
    assert.match(source, /selectedSurfaceIdSet\.has\(child\.userData\.surfaceId\)/);
    assert.match(source, /material\.transparent\s*=\s*false/);
    assert.match(source, /material\.opacity\s*=\s*1/);
  });

  test("picks only through the pointer viewport and synchronizes active controls", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.match(source, /viewportAtPointer/);
    assert.match(source, /raycaster\.setFromCamera\(pointer,\s*cameras\[hit\.viewId\]\)/);
    assert.match(source, /raycaster\s*\.intersectObject\(group,\s*true\)/);
    assert.match(source, /candidate\.object\.isMesh\s*&&\s*candidate\.object\.visible/);
    assert.match(source, /onSelectSurfaceRef\.current\?\.\(surfaceId\)/);
    assert.match(source, /control\.enableRotate\s*=\s*viewId === "3d"/);
    assert.match(source, /control\.enabled\s*=\s*viewId === activeViewId/);
    assert.match(source, /addEventListener\("pointerdown",\s*handlePointerDown,\s*true\)/);
    assert.match(source, /removeEventListener\("pointerdown",\s*handlePointerDown,\s*true\)/);
  });

  test("renders annotation buttons without geometry projection or leader errors", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.match(source, /ParameterAnnotationOverlay/);
    assert.match(source, /annotationsByView\[viewId\]/);
    assert.doesNotMatch(source, /resolveInspectionAnchor/);
    assert.doesNotMatch(source, /point\.project\(camera\)/);
    assert.doesNotMatch(source, /selectedProjectionFailureKey/);
    assert.doesNotMatch(source, /onProjectionError/);
    assert.doesNotMatch(source, /projectionEpoch/);
  });

  test("uses parameter clicks instead of colored meridional control overlays", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.doesNotMatch(source, /renderMeridionalSupportProfiles/);
    assert.doesNotMatch(source, /meridional-support-profile/);
    assert.doesNotMatch(source, /meridional-support-control/);
  });

  test("renders parameter overlays after viewport sizing without a selection revision key", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.doesNotMatch(source, /selectionContextKey/);
    assert.match(source, /viewportSize\.width > 0\s*&&\s*viewportSize\.height > 0/);
    assert.match(source, /geometricViews\.map\(\(viewId\) =>/);
    assert.match(source, /:\s*null,?\s*\n\s*\);/);
  });

  test("does not retain obsolete projection epoch state", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.doesNotMatch(source, /projectionEpoch/);
    assert.doesNotMatch(source, /projectionVersion/);
    assert.match(source, /key:\s*viewId/);
  });

  test("reapplies selection and visibility after manifest-driven scene rebuilds", () => {
    const source = readFileSync(scenePath, "utf-8");
    const buildIndex = source.indexOf("const group = createSurfaceGraphGroup(");
    const selectionIndex = source.indexOf("selectedSurfaceIdSet.has(child.userData.surfaceId)");
    const visibilityIndex = source.indexOf("group.visible = true;");

    assert.ok(buildIndex >= 0 && buildIndex < selectionIndex);
    assert.ok(selectionIndex < visibilityIndex);
    assert.match(source, /\}, \[manifest, selectedSurfaceIds, surfaceGraph\]\);/);
    assert.match(source, /\}, \[manifest, surfaceGraph, visibleLayers\]\);/);
  });

  test("applies viewer layer visibility and fully cleans up the scene lifecycle", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.doesNotMatch(source, /viewerLayerVisibility\(/);
    assert.match(source, /group\.visible = true/);
    assert.match(source, /renderer\.setClearColor\("#f5f5f5"\)/);
    assert.match(source, /camera\.updateMatrixWorld\(\)/);
    assert.match(source, /window\.cancelAnimationFrame\(frameId\)/);
    assert.match(source, /observer\.disconnect\(\)/);
    assert.match(source, /Object\.values\(controls\)\.forEach\(\(control\) => control\.dispose\(\)\)/);
    assert.match(source, /scene\.remove\(group\)/);
    assert.match(source, /disposeObject\(group\)/);
    assert.match(source, /renderer\.dispose\(\)/);
    assert.match(source, /renderer\.domElement\.remove\(\)/);
    assert.match(source, /"data-testid":\s*"inspection-webgl"/);
    assert.match(source, /inspectionRendererLifecycle\.register\(renderer\)/);
    assert.match(source, /releaseRendererLifecycle\(\)/);
    assert.match(source, /"data-renderer-created-count":/);
    assert.match(source, /"data-renderer-live-count":/);
    assert.match(source, /"data-context-created-count":/);
    assert.match(source, /"data-context-live-count":/);
    assert.match(source, /"data-scene-surface-count":/);
    assert.match(source, /"data-visible-uv-overlay-count":\s*"0"/);
    assert.match(source, /child\.userData\.isSurfaceUvWire\)\s*\{\s*child\.visible = false/);
    assert.match(source, /child\.userData\.isInspectionContour/);
  });
});
