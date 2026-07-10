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

  test("builds the surface group once and updates selection materials in place", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.equal((source.match(/createSurfaceGraphGroup\(/g) || []).length, 1);
    assert.match(source, /createSurfaceGraphGroup\(\s*surfaceGraph,\s*bounds\.center,\s*"cad_review_360",\s*new Set\(\),\s*"off",\s*manifest,?\s*\)/);
    assert.match(source, /baselineEmissive/);
    assert.match(source, /baselineEmissiveIntensity/);
    assert.match(source, /baselineOpacity/);
    assert.match(source, /group\.traverse\(\(child\)/);
    assert.match(source, /child\.userData\.surfaceId === selectedSurfaceId/);
    assert.match(source, /material\.emissive\.set\(/);
    assert.match(source, /material\.emissiveIntensity\s*=/);
    assert.match(source, /material\.opacity\s*=/);
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

  test("projects annotations and reports selected anchor failures", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.match(source, /ParameterAnnotationOverlay/);
    assert.match(source, /resolveInspectionAnchor\(anchor,\s*manifest,\s*surfaceGraph\)/);
    assert.match(source, /point\.project\(camera\)/);
    assert.match(source, /annotation\.selected/);
    assert.match(source, /onProjectionError\?\.\("parameter_inspection_projection_failed"\)/);
    assert.match(source, /annotationsByView\[viewId\]/);
    assert.match(source, /const projectionReady\s*=/);
    assert.match(source, /selectedProjectionFailed\s*=\s*projectionReady\s*&&/);
  });

  test("applies viewer layer visibility and fully cleans up the scene lifecycle", () => {
    const source = readFileSync(scenePath, "utf-8");

    assert.match(source, /viewerLayerVisibility\(/);
    assert.match(source, /showShadedSurfaces/);
    assert.match(source, /showSurfaceUvWire/);
    assert.match(source, /showMeshEdges/);
    assert.match(source, /renderer\.setClearColor\("#eef2f0"\)/);
    assert.match(source, /camera\.updateMatrixWorld\(\)/);
    assert.match(source, /window\.cancelAnimationFrame\(frameId\)/);
    assert.match(source, /observer\.disconnect\(\)/);
    assert.match(source, /Object\.values\(controls\)\.forEach\(\(control\) => control\.dispose\(\)\)/);
    assert.match(source, /scene\.remove\(group\)/);
    assert.match(source, /disposeObject\(group\)/);
    assert.match(source, /renderer\.dispose\(\)/);
    assert.match(source, /renderer\.domElement\.remove\(\)/);
    assert.match(source, /"data-testid":\s*"inspection-webgl"/);
    assert.match(source, /"data-renderer-count":\s*"1"/);
    assert.match(source, /"data-scene-surface-count":/);
  });
});
