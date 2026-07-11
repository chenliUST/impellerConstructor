import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";
import vm from "node:vm";

const root = resolve(import.meta.dirname, "..", "..");
const workspacePath = resolve(root, "src/components/ParameterInspectionWorkspace.js");
const stylesPath = resolve(root, "src/styles.css");

function loadWorkspaceHelpers() {
  const source = readFileSync(workspacePath, "utf-8")
    .replace(/^import[\s\S]*?;\r?\n/gm, "")
    .replace(/export (const|function) /g, "$1 ");
  const module = { exports: {} };
  const context = vm.createContext({
    module,
    exports: module.exports,
    Object,
    Set,
    React: { createElement: () => null },
  });
  vm.runInContext(
    `${source}\nmodule.exports = { WORKSPACE_TABS, parameterAppliesToWorkspaceView, preserveEquivalentParameterId };`,
    context,
    { filename: workspacePath },
  );
  return module.exports;
}

describe("ParameterInspectionWorkspace", () => {
  test("declares exactly the three approved inspection views", () => {
    assert.equal(existsSync(workspacePath), true, "ParameterInspectionWorkspace.js should exist");
    const { WORKSPACE_TABS } = loadWorkspaceHelpers();

    assert.deepEqual(
      Array.from(WORKSPACE_TABS, (tab) => tab.id),
      ["top", "meridional", "s_q_blade"],
    );
  });

  test("integrates the compact browser, engineering drawings, and isolated blade scene", () => {
    const source = readFileSync(workspacePath, "utf-8");
    const styles = readFileSync(stylesPath, "utf-8");

    assert.match(source, /ParameterFeatureBrowser/);
    assert.match(source, /EngineeringDrawingView/);
    assert.match(source, /BladeFeatureScene/);
    assert.match(source, /data-testid":\s*"inspection-blade-selector"/);
    assert.match(source, /data-testid":\s*"inspection-station-selector"/);
    assert.match(source, /className:\s*"inspection-drawing-grid inspection-s-q-blade-grid"/);
    assert.match(source, /viewId:\s*"s_q"/);
    assert.match(source, /selectedParameter/);
    assert.match(source, /bladeSurfaceIds/);
    assert.match(styles, /\.inspection-workspace-body\s*\{[\s\S]*grid-template-columns:/);
    assert.match(styles, /\.inspection-s-q-blade-grid\s*\{[\s\S]*grid-template-columns:/);
    assert.match(styles, /max-block-size:\s*32px/);
  });

  test("keeps one selected parameter and removes obsolete inspection interactions", () => {
    const source = readFileSync(workspacePath, "utf-8");

    assert.match(source, /const \[selectedParameterId, setSelectedParameterId\] = useState\(null\)/);
    assert.equal((source.match(/selectedParameterId, setSelectedParameterId/g) || []).length, 1);
    assert.doesNotMatch(source, /InspectionScene/);
    assert.doesNotMatch(source, /ParameterAnnotationOverlay/);
    assert.doesNotMatch(source, /SectionLoopInspectionView/);
    assert.doesNotMatch(source, /annotationLevel|activeAnnotationId|maximize|whole-face|selectedSurfaceIds/);
    assert.doesNotMatch(source, /\b3d\b|\bquad\b/);
  });

  test("preserves an equivalent selection for blade and station context changes", () => {
    const { preserveEquivalentParameterId } = loadWorkspaceHelpers();
    const calls = [];
    const equivalent = (_model, currentId, nextContext) => {
      calls.push([currentId, nextContext]);
      return "blade-2:station-50:thickness";
    };
    const model = {
      engineeringParameters: [{
        id: "blade-2:station-50:thickness",
        applicableViews: ["s_q", "blade_3d"],
      }],
    };

    assert.equal(
      preserveEquivalentParameterId(
        model,
        "blade-1:station-50:thickness",
        { bladeId: "blade-2", spanStationId: "blade-2:station-50" },
        "s_q_blade",
        equivalent,
      ),
      "blade-2:station-50:thickness",
    );
    assert.deepEqual(calls, [[
      "blade-1:station-50:thickness",
      { bladeId: "blade-2", spanStationId: "blade-2:station-50" },
    ]]);
  });

  test("clears selection when no equivalent exists or the target view is inapplicable", () => {
    const { parameterAppliesToWorkspaceView, preserveEquivalentParameterId } = loadWorkspaceHelpers();
    const topOnly = { id: "diameter", applicableViews: ["top"] };
    const sectionAndBlade = { id: "thickness", applicableViews: ["s_q", "blade_3d"] };
    const model = { engineeringParameters: [topOnly, sectionAndBlade] };

    assert.equal(parameterAppliesToWorkspaceView(topOnly, "top"), true);
    assert.equal(parameterAppliesToWorkspaceView(topOnly, "meridional"), false);
    assert.equal(parameterAppliesToWorkspaceView(sectionAndBlade, "s_q_blade"), true);
    assert.equal(preserveEquivalentParameterId(model, "diameter", {}, "top", () => null), null);
    assert.equal(preserveEquivalentParameterId(model, "diameter", {}, "meridional", () => "diameter"), null);
  });

  test("preserves the same parameter semantics across generated station indices", () => {
    const { preserveEquivalentParameterId } = loadWorkspaceHelpers();
    const model = {
      engineeringParameters: [
        {
          id: "blade:blade_0:station:blade_0:span_0:thickness",
          groupId: "section_loop",
          label: "Blade thickness",
          applicableViews: ["s_q", "blade_3d"],
          selectionScope: {
            blade_instance_id: "blade_0",
            section_loop_id: "blade_0:span_0:loop",
            source_station_index: 0,
            span_station_id: "blade_0:span_0",
          },
        },
        {
          id: "blade:blade_0:station:blade_0:span_2:thickness",
          groupId: "section_loop",
          label: "Blade thickness",
          applicableViews: ["s_q", "blade_3d"],
          selectionScope: {
            blade_instance_id: "blade_0",
            section_loop_id: "blade_0:span_2:loop",
            source_station_index: 2,
            span_station_id: "blade_0:span_2",
          },
        },
      ],
    };

    assert.equal(
      preserveEquivalentParameterId(
        model,
        "blade:blade_0:station:blade_0:span_0:thickness",
        { bladeId: "blade_0", spanStationId: "blade_0:span_2" },
        "s_q_blade",
        () => null,
      ),
      "blade:blade_0:station:blade_0:span_2:thickness",
    );
  });

  test("clears the active parameter through the browser and renders no selected evidence for null", () => {
    const source = readFileSync(workspacePath, "utf-8");

    assert.match(source, /onSelect:\s*setSelectedParameterId/);
    assert.match(source, /engineeringParameterById\(model, selectedParameterId\)/);
    assert.match(source, /selectedParameter:\s*drawingSelectedParameter/);
    assert.match(source, /selectedParameter:\s*bladeSelectedParameter/);
    assert.match(source, /selectedParameterId:\s*selectedParameterId/);
  });
});
