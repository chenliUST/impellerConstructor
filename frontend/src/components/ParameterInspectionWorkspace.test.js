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

  test("keeps one selection context across views and clears transient projection errors", () => {
    const source = readFileSync(workspacePath, "utf-8");

    assert.match(source, /resolveParameterInspection\(manifest\)/);
    assert.match(source, /defaultInspectionSelection\(model\)/);
    assert.match(source, /reduceInspectionSelection\(model, current,/);
    assert.match(source, /annotationsForView\(model, viewId, annotationLevel, selection\)/);
    assert.match(source, /sectionLoopForSelection\(model, selection\)/);
    assert.match(source, /selectionContextKey:\s*JSON\.stringify\(selection\)/);
    assert.match(source, /setProjectionError\(null\)/);
    assert.match(source, /model\.contract\?\.generation_id/);
    assert.match(source, /data-testid":\s*"inspection-workspace"/);
    assert.match(source, /inspection-tab-quad/);
    assert.match(source, /data-testid":\s*"inspection-annotation-level"/);
    assert.match(source, /data-testid":\s*"inspection-blade-selector"/);
    assert.match(source, /data-testid":\s*"inspection-station-selector"/);
    assert.match(source, /Resolved manifest \| runtime 1\.1\.3 \| geometry 1\.1\.2/);
    assert.match(source, /reduceInspectionSelection/);
    assert.match(source, /selectedSurfaceIdsForSelection/);
  });

  test("clears projection errors before selection and tab changes without a passive clear race", () => {
    const source = readFileSync(workspacePath, "utf-8");
    const generationReset = source.match(/useLayoutEffect\(\(\) => \{([\s\S]*?)\}, \[generationId\]\);/)?.[1] || "";
    const surfaceSelection = source.match(/function handleSurfaceSelection\(surfaceId\) \{([\s\S]*?)\n  \}/)?.[1] || "";
    const sectionSelection = source.match(/function handleSectionSelection\(nextSelection\) \{([\s\S]*?)\n  \}/)?.[1] || "";
    const tabSelection = source.match(/function handleTabSelection\(viewId\) \{([\s\S]*?)\n  \}/)?.[1] || "";

    assert.match(source, /import React, \{ useEffect, useLayoutEffect, useMemo, useState \}/);
    assert.ok(generationReset.indexOf("setProjectionError(null)") < generationReset.indexOf("setSelection("));
    assert.ok(surfaceSelection.indexOf("setProjectionError(null)") < surfaceSelection.indexOf("setSelection("));
    assert.ok(sectionSelection.indexOf("setProjectionError(null)") < sectionSelection.indexOf("setSelection("));
    assert.ok(tabSelection.indexOf("setProjectionError(null)") < tabSelection.indexOf("setActiveTab("));
    assert.doesNotMatch(source, /useEffect\(\(\) => \{\s*setProjectionError\(null\);\s*\}, \[activeTab, generationId, selection\]\)/);
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
  });
});
