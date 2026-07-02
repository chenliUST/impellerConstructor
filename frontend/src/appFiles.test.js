import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..");

describe("frontend application files", () => {
  test("browser entry uses import maps and the main module", () => {
    const html = readFileSync(resolve(root, "index.html"), "utf-8");

    assert.match(html, /type="importmap"/);
    assert.match(html, /src="\/src\/main\.js"/);
  });

  test("application shell files exist", () => {
    for (const file of [
      "scripts/build-check.js",
      "src/main.js",
      "src/App.js",
      "src/apiClient.js",
      "src/components/PresetList.js",
      "src/components/FacetPanel.js",
      "src/components/ParameterPanel.js",
      "src/components/GeometryLayerPanel.js",
      "src/components/CfdManifestPanel.js",
      "src/components/MeshInspectionPanel.js",
      "src/components/ModelViewer.js",
      "src/components/ManifestPanel.js",
      "src/meshOverlayModel.js",
      "src/meshViewModel.js",
      "src/simulationViewModel.js",
      "src/workspaceModel.js",
      "src/styles.css",
    ]) {
      assert.equal(existsSync(resolve(root, file)), true, `${file} should exist`);
    }
  });

  test("viewer renders construction lines instead of mesh triangle wireframe", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");

    assert.doesNotMatch(viewerSource, /GridHelper/);
    assert.doesNotMatch(viewerSource, /wireframe:\s*true/);
    assert.match(viewerSource, /LineSegments/);
    assert.match(appSource, /useState\(false\)/);
  });

  test("viewer exposes mesh overlay layers for CFD360 mesh inspection", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const panelSource = readFileSync(resolve(root, "src/components/MeshInspectionPanel.js"), "utf-8");
    const overlaySource = readFileSync(resolve(root, "src/meshOverlayModel.js"), "utf-8");
    const workspaceSource = readFileSync(resolve(root, "src/workspaceModel.js"), "utf-8");

    assert.match(viewerSource, /meshOverlayMode\s*=\s*"triangle_edges"/);
    assert.match(viewerSource, /WireframeGeometry/);
    assert.match(viewerSource, /createSurfaceGraphGroup\(\s*visibleSurfaceGraph,\s*bounds\.center,\s*simulationViewMode,\s*selectedSurfaceIds,\s*meshOverlayMode,\s*manifest,\s*\)/);
    assert.match(viewerSource, /surfaceVisibleInView\(surface,\s*simulationViewMode,\s*manifest\)/);
    assert.doesNotMatch(viewerSource, /surfaceVisibleInView\(surface,\s*simulationViewMode\)/);
    assert.match(viewerSource, /transition_mesh_edges/);
    assert.match(viewerSource, /mesh_edges/);
    assert.match(panelSource, /transitionRegionRows/);
    assert.match(panelSource, /transition-region-row/);
    assert.match(overlaySource, /triangle_edges/);
    assert.match(overlaySource, /transitions/);
    assert.match(workspaceSource, /transition_surfaces/);
  });

  test("parameter panel uses direct numeric inputs without range sliders", () => {
    const panelSource = readFileSync(resolve(root, "src/components/ParameterPanel.js"), "utf-8");

    assert.doesNotMatch(panelSource, /type:\s*"range"/);
    assert.match(panelSource, /type:\s*"number"/);
  });

  test("parameter panel renders ontology DSL parameter groups", () => {
    const panelSource = readFileSync(resolve(root, "src/components/ParameterPanel.js"), "utf-8");

    assert.match(panelSource, /parameterGroups/);
    assert.match(panelSource, /parameter-group/);
    assert.match(panelSource, /blade_boundaries/);
    assert.match(panelSource, /controlKind/);
  });

  test("manifest panel exposes ontology constructor and shape-control metadata", () => {
    const panelSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

    assert.match(panelSource, /ontology_slice/);
    assert.match(panelSource, /constructor_family/);
    assert.match(panelSource, /constructor_id/);
    assert.match(panelSource, /shape_control/);
    assert.match(panelSource, /optimization_stage/);
  });

  test("manifest panel exposes export fidelity metadata", () => {
    const panelSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

    assert.match(panelSource, /export_manifests/);
    assert.match(panelSource, /export_exactness/);
    assert.match(panelSource, /surface_graph_faithful/);
  });

  test("viewer gives blade boundary construction lines and named boundaries dedicated layers", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /blade_boundaries/);
    assert.match(viewerSource, /named_boundary_curve/);
    assert.match(viewerSource, /edge_closure_surface/);
  });

  test("application exposes geometry layer controls to the model viewer", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const panelSource = readFileSync(resolve(root, "src/components/GeometryLayerPanel.js"), "utf-8");
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(appSource, /GeometryLayerPanel/);
    assert.match(appSource, /visibleLayers/);
    assert.match(panelSource, /layerSchema/);
    assert.match(viewerSource, /layerForSurface/);
    assert.match(viewerSource, /layerForConstructionFeature/);
  });

  test("application includes cfd simulation inspection view controls", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const cfdPanelSource = readFileSync(resolve(root, "src/components/CfdManifestPanel.js"), "utf-8");
    const manifestPanelSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

    assert.match(appSource, /simulationViewMode/);
    assert.match(appSource, /CfdManifestPanel/);
    assert.match(appSource, /h\(ManifestPanel,\s*\{[\s\S]*before:\s*h\(CfdManifestPanel,/);
    assert.match(viewerSource, /surfaceVisibleInView/);
    assert.match(viewerSource, /patchSurfaceIds/);
    assert.match(cfdPanelSource, /cfdPatchGroups/);
    assert.match(cfdPanelSource, /MeshInspectionPanel/);
    assert.match(manifestPanelSource, /before/);
  });

  test("application includes curve editors and staged generation controls", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");

    for (const file of [
      "src/profileEditorModel.js",
      "src/bladeCurveEditorModel.js",
      "src/components/ProfileCurveEditor.js",
      "src/components/BladeCurveEditor.js",
      "src/components/GenerationStagePanel.js",
      "src/components/EdgeTreatmentPanel.js",
      "src/edgeTreatmentModel.js",
      "src/edgeTreatmentModel.test.js",
    ]) {
      assert.equal(existsSync(resolve(root, file)), true, `${file} should exist`);
    }

    assert.match(appSource, /profileOverrides/);
    assert.match(appSource, /curveOverrides/);
    assert.match(appSource, /transitionOverrides/);
    assert.match(appSource, /geometryStage/);
    assert.match(appSource, /GenerationStagePanel/);
    assert.match(appSource, /EdgeTreatmentPanel/);
  });

  test("curve editors expose engineering-unit numeric control-point inputs", () => {
    const profileSource = readFileSync(resolve(root, "src/components/ProfileCurveEditor.js"), "utf-8");
    const bladeSource = readFileSync(resolve(root, "src/components/BladeCurveEditor.js"), "utf-8");
    const styles = readFileSync(resolve(root, "src/styles.css"), "utf-8");

    assert.match(profileSource, /width:\s*520/);
    assert.match(profileSource, /height:\s*320/);
    assert.match(profileSource, /profile-control-table/);
    assert.match(profileSource, /type:\s*"number"/);
    assert.match(bladeSource, /width:\s*420/);
    assert.match(bladeSource, /height:\s*128/);
    assert.match(bladeSource, /curve-control-table/);
    assert.match(bladeSource, /type:\s*"number"/);
    assert.match(styles, /profile-control-table/);
    assert.match(styles, /curve-control-table/);
  });

  test("application includes CFD manifest panel and simulation view model", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const modelSource = readFileSync(resolve(root, "src/simulationViewModel.js"), "utf-8");

    assert.match(appSource, /CfdManifestPanel/);
    assert.match(modelSource, /cfdPatchGroups/);
    assert.match(modelSource, /surfaceVisibleInView/);
  });
});
