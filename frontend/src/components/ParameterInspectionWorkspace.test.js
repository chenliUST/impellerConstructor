import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..", "..");
const workspacePath = resolve(root, "src/components/ParameterInspectionWorkspace.js");

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
    assert.match(source, /mergeInspectionSelection\(current,/);
    assert.match(source, /annotationsForView\(model, viewId, annotationLevel, selection\)/);
    assert.match(source, /sectionLoopForSelection\(model, selection\)/);
    assert.match(source, /selectionContextKey:\s*JSON\.stringify\(selection\)/);
    assert.match(source, /setProjectionError\(null\)/);
    assert.match(source, /model\.contract\?\.generation_id/);
    assert.match(source, /data-testid":\s*"inspection-workspace"/);
    assert.match(source, /inspection-tab-quad/);
    assert.match(source, /data-testid":\s*"inspection-annotation-level"/);
  });
});
