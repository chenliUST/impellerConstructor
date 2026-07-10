import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..", "..");
const workspacePath = resolve(root, "src/components/ParameterInspectionWorkspace.js");
const stylesPath = resolve(root, "src/styles.css");

describe("ParameterInspectionWorkspace source contract", () => {
  test("integrates the approved read-only inspection views and controls", () => {
    assert.equal(existsSync(workspacePath), true, "ParameterInspectionWorkspace.js should exist");
    const source = readFileSync(workspacePath, "utf-8");

    assert.match(source, /INSPECTION_TABS/);
    assert.match(source, /ANNOTATION_LEVELS/);
    assert.match(source, /useState\("3d"\)/);
    assert.match(source, /InspectionScene/);
    assert.match(source, /SectionLoopInspectionView/);
    assert.match(source, /ParameterAnnotationOverlay/);
    assert.match(source, /parameter_inspection_not_generated/);
    assert.match(source, /maximize/);
    assert.doesNotMatch(source, /onChange/);
    assert.doesNotMatch(source, /onGeometry/);
  });

  test("keeps one selection context across views without obsolete projection state", () => {
    const source = readFileSync(workspacePath, "utf-8");

    assert.match(source, /resolveParameterInspection\(manifest\)/);
    assert.match(source, /defaultInspectionSelection\(model\)/);
    assert.match(source, /reduceInspectionSelection\(model, current,/);
    assert.match(source, /annotationsForView\(model, viewId, annotationLevel, selection\)/);
    assert.match(source, /sectionLoopForSelection\(model, selection\)/);
    assert.doesNotMatch(source, /selectionContextKey/);
    assert.doesNotMatch(source, /projectionError/);
    assert.match(source, /model\.contract\?\.generation_id/);
    assert.match(source, /data-testid":\s*"inspection-workspace"/);
    assert.match(source, /inspection-tab-quad/);
    assert.match(source, /data-testid":\s*"inspection-annotation-level"/);
    assert.match(source, /data-testid":\s*"inspection-blade-selector"/);
    assert.match(source, /data-testid":\s*"inspection-station-selector"/);
    assert.match(source, /Resolved manifest \| runtime 1\.1\.3 \| geometry 1\.1\.2/);
    assert.match(source, /reduceInspectionSelection/);
    assert.match(source, /selectedSurfaceIdsForSelection/);
    assert.match(source, /model\.inspectionSurfaceGraph/);
    assert.match(source, /navigationSelection/);
    assert.match(source, /activeAnnotationId/);
    assert.match(source, /handleAnnotationSelection/);
    assert.match(source, /current === annotation\.id \? null : annotation\.id/);
    assert.match(source, /activeAnnotation\?\.targetSurfaceIds/);
    assert.match(source, /selectedAnnotationId/);
    assert.match(source, /onSelectAnnotation/);
  });

  test("clears active parameter selection before geometry and navigation changes", () => {
    const source = readFileSync(workspacePath, "utf-8");
    const surfaceSelection = source.match(/function handleSurfaceSelection\(surfaceId\) \{([\s\S]*?)\n  \}/)?.[1] || "";
    const sectionSelection = source.match(/function handleSectionSelection\(nextSelection\) \{([\s\S]*?)\n  \}/)?.[1] || "";
    const tabSelection = source.match(/function handleTabSelection\(viewId\) \{([\s\S]*?)\n  \}/)?.[1] || "";
    const bladeSelection = source.match(/function handleBladeSelection\(bladeId\) \{([\s\S]*?)\n  \}/)?.[1] || "";
    const stationSelection = source.match(/function handleStationSelection\(spanStationId\) \{([\s\S]*?)\n  \}/)?.[1] || "";

    assert.match(source, /import React, \{ useEffect, useLayoutEffect, useMemo, useState \}/);
    for (const handler of [surfaceSelection, sectionSelection, bladeSelection, stationSelection, tabSelection]) {
      assert.match(handler, /setActiveAnnotationId\(null\)/);
    }
    assert.match(source, /onClick: \(\) => handleTabSelection\(tab\.id\)/);
    assert.match(source, /onClick: \(\) => handleTabSelection\(viewId\)/);
    assert.doesNotMatch(surfaceSelection, /setActiveTab/);
    assert.doesNotMatch(sectionSelection, /setActiveTab/);
  });

  test("selects stacked Quad at the CSS breakpoint and cleans up matchMedia", () => {
    const source = readFileSync(workspacePath, "utf-8");
    const styles = readFileSync(stylesPath, "utf-8");

    assert.match(source, /window\.matchMedia\("\(max-width: 820px\)"\)/);
    assert.match(source, /mediaQuery\.addEventListener\("change", updateNarrowQuad\)/);
    assert.match(source, /mediaQuery\.removeEventListener\("change", updateNarrowQuad\)/);
    assert.match(source, /const quadLayout = narrowQuad \? "quad_stacked" : "quad"/);
    assert.match(source, /layout: quadLayout/);
    assert.match(styles, /\.inspection-quad-pane-3d\s*\{\s*grid-row: 1;/);
    assert.match(styles, /\.inspection-quad-pane-meridional\s*\{\s*grid-row: 2;/);
    assert.match(styles, /\.inspection-quad-pane-s_q\s*\{\s*grid-row: 3;/);
    assert.match(styles, /\.inspection-quad-pane-top\s*\{\s*grid-row: 4;/);
    assert.match(styles, /\.inspection-tab-list,\s*\.inspection-entity-selectors\s*\{\s*width: 100%;\s*flex: 0 0 auto;/);
  });
});
