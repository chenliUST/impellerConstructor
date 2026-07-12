import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..");

describe("frontend application files", () => {
  test("browser entry uses import maps and the main module", () => {
    const html = readFileSync(resolve(root, "index.html"), "utf-8");

    assert.match(html, /type="importmap"/);
    assert.match(html, /src="\/src\/main\.js(?:\?v=[^"]+)?"/);
  });

  test("browser entry cache-busts the v1.1 frontend modules", () => {
    const html = readFileSync(resolve(root, "index.html"), "utf-8");
    const mainSource = readFileSync(resolve(root, "src/main.js"), "utf-8");
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(html, /src="\/src\/main\.js\?v=1\.1\.7"/);
    assert.match(mainSource, /from "\.\/App\.js\?v=1\.1\.7"/);
    assert.match(appSource, /from "\.\/apiClient\.js\?v=1\.1\.9"/);
    assert.match(appSource, /from "\.\/appModel\.js\?v=1\.1\.8"/);
    assert.match(appSource, /from "\.\/workspaceModel\.js\?v=1\.1\.5"/);
    assert.match(appSource, /from "\.\/components\/ModelViewer\.js\?v=1\.1\.8"/);
    assert.match(appSource, /from "\.\/components\/ReviewEngineeringDrawing\.js\?v=1\.1\.5\.1"/);
    assert.match(viewerSource, /from "\.\.\/meshOverlayModel\.js\?v=1\.1\.5"/);
    assert.match(viewerSource, /from "\.\.\/workspaceModel\.js\?v=1\.1\.5"/);
    assert.match(readFileSync(resolve(root, "src/apiClient.js"), "utf-8"), /from "\.\/appModel\.js\?v=1\.1\.9"/);
    assert.match(
      readFileSync(resolve(root, "src/workspaceModel.js"), "utf-8"),
      /from "\.\/meshOverlayModel\.js\?v=1\.1\.5"/,
    );
    assert.match(
      readFileSync(resolve(root, "src/simulationViewModel.js"), "utf-8"),
      /from "\.\/meshOverlayModel\.js\?v=1\.1\.5"/,
    );
  });

  test("runtime local module imports are cache-busted", () => {
    const runtimeFiles = [
      "src/main.js",
      "src/App.js",
      "src/apiClient.js",
      "src/workspaceModel.js",
      "src/simulationViewModel.js",
      "src/meshViewModel.js",
      "src/components/BladeCurveEditor.js",
      "src/components/CfdManifestPanel.js",
      "src/components/EdgeTreatmentPanel.js",
      "src/components/FacetPanel.js",
      "src/components/GeometryLayerPanel.js",
      "src/components/ManifestPanel.js",
      "src/components/MeshInspectionPanel.js",
      "src/components/ModelViewer.js",
      "src/components/ParameterPanel.js",
      "src/components/ParameterInspectionWorkspace.js",
      "src/components/ProfileCurveEditor.js",
    ];

    for (const file of runtimeFiles) {
      const source = readFileSync(resolve(root, file), "utf-8");
      const bareLocalImports = source.match(/from "\.{1,2}\/[^"]+\.js"/g) || [];
      assert.deepEqual(bareLocalImports, [], `${file} has unversioned local imports`);
    }
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
      "src/components/ParameterInspectionWorkspace.js",
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

  test("viewer retains mesh rendering internals without exposing the removed CFD workspace", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const panelSource = readFileSync(resolve(root, "src/components/MeshInspectionPanel.js"), "utf-8");
    const overlaySource = readFileSync(resolve(root, "src/meshOverlayModel.js"), "utf-8");
    const workspaceSource = readFileSync(resolve(root, "src/workspaceModel.js"), "utf-8");

    assert.match(viewerSource, /meshOverlayMode\s*=\s*"triangle_edges"/);
    assert.match(appSource, /meshOverlayMode: "triangle_edges"/);
    assert.doesNotMatch(appSource, /MeshInspectionPanel|workspace-mesh/);
    assert.match(viewerSource, /meshOverlayOptions/);
    assert.match(viewerSource, /WireframeGeometry/);
    assert.match(viewerSource, /createSurfaceGraphGroup\(\s*visibleSurfaceGraph,\s*bounds\.center,\s*simulationViewMode,\s*selectedSurfaceIds,\s*activeMeshOverlayMode,\s*manifest,\s*\)/);
    assert.match(viewerSource, /surfaceVisibleInView\(surface,\s*simulationViewMode,\s*manifest\)/);
    assert.doesNotMatch(viewerSource, /surfaceVisibleInView\(surface,\s*simulationViewMode\)/);
    assert.match(viewerSource, /transition_mesh_edges/);
    assert.match(viewerSource, /mesh_edges/);
    assert.match(panelSource, /transitionRegionRows/);
    assert.match(panelSource, /transition-region-row/);
    assert.match(overlaySource, /triangle_edges/);
    assert.match(overlaySource, /transitionSurfaceIds/);
    assert.match(overlaySource, /isTransitionSurface/);
    assert.match(workspaceSource, /transition_surfaces/);
  });

  test("viewer exports and keeps using the proven surface-graph helpers for CAD and CFD", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /export function createSurfaceGraphGroup\(/);
    assert.match(viewerSource, /export function surfaceGraphBounds\(/);
    assert.match(viewerSource, /export function disposeObject\(/);
    assert.match(
      viewerSource,
      /createSurfaceGraphGroup\(\s*visibleSurfaceGraph,\s*bounds\.center,\s*simulationViewMode,\s*selectedSurfaceIds,\s*activeMeshOverlayMode,\s*manifest,\s*\)/,
    );
  });

  test("viewer renders mesh-only surface graph geometry and bounds", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /function surfaceMeshPoints/);
    assert.match(viewerSource, /function surfaceMeshGeometry/);
    assert.match(viewerSource, /surface\.mesh/);
    assert.match(viewerSource, /surfaceGraphBounds[\s\S]*surfaceMeshPoints\(surface\.mesh,\s*surface\.uv_grid\s*\|\|\s*\[\]\)/);
    assert.match(viewerSource, /surfaceMeshGeometry\(surface\.mesh,\s*center,\s*grid\)/);
    assert.match(viewerSource, /meshPoint\(point,\s*mesh\.vertices,\s*uvGrid\)/);
    assert.match(viewerSource, /Number\.isInteger\(point\[0]\)[\s\S]*Number\.isInteger\(point\[1]\)[\s\S]*uvGrid\[point\[0]]\?\.\[point\[1]]/);
  });

  test("viewer keeps STL fallback shaded mesh out of wireframe mode", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /shaded\.userData\.layer\s*=\s*"shade_surfaces"/);
    assert.match(viewerSource, /child\.isMesh[\s\S]*showShadedSurfaces[\s\S]*visibleLayers\[child\.userData\.layer\]/);
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

  test("manifest panel exposes v0.9 geometry validation signals", () => {
    const panelSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

    assert.match(panelSource, /geometry_validation_report/);
    assert.match(panelSource, /geometry_validation_status/);
    assert.match(panelSource, /blocking_failures/);
    assert.match(panelSource, /transition_validation_summary/);
    assert.match(panelSource, /capability_claim_level/);
  });

  test("viewer gives blade boundary construction lines and named boundaries dedicated layers", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /blade_boundaries/);
    assert.match(viewerSource, /named_boundary_curve/);
    assert.match(viewerSource, /edge_closure_surface/);
  });

  test("viewer recognizes native v1.0 topology faces", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /native_topology_face/);
    assert.match(viewerSource, /face_family/);
    assert.match(viewerSource, /shared_edge/);
    assert.match(viewerSource, /defaultSurfaceOpacity/);
    assert.match(viewerSource, /createSurfaceUvWireOverlay/);
    assert.match(viewerSource, /surface\.wireframe/);
  });

  test("viewer prioritizes v1.0.2 and v1.0.3 transition inspection colors", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /root_to_hub_native_root_face/);
    assert.match(viewerSource, /tip_to_shroud_attachment/);
    assert.match(viewerSource, /root_to_hub_blend/);
    assert.match(viewerSource, /open_tip_dome/);
    assert.match(viewerSource, /#ff00cc/);
    assert.match(viewerSource, /#00e5ff/);
    assert.match(viewerSource, /#fff200/);
  });

  test("viewer renders v1.0.3 curve control overlays from manifest data", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /addCurveControlOverlays/);
    assert.match(viewerSource, /makeControlPointMarker/);
    assert.match(viewerSource, /curveControlsFromManifest/);
    assert.match(viewerSource, /curve_controls/);
    assert.match(viewerSource, /geometry\?\.curve_controls/);
  });

  test("viewer treats topology shared-edge diagnostics as mesh overlay", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /simulationViewMode === "mesh" && meshOverlayMode !== "off"[\s\S]*createSharedEdgeGroup/);
    assert.match(viewerSource, /line\.userData\.isMeshOverlay\s*=\s*true/);
    assert.match(viewerSource, /line\.userData\.layer\s*=\s*"mesh_edges"/);
  });

  test("viewer separates V1.0.4 shade uv mesh controls and diagnostic layers", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const workspaceSource = readFileSync(resolve(root, "src/workspaceModel.js"), "utf-8");

    for (const layer of [
      "shade_surfaces",
      "nurbs_uv_wire",
      "mesh_triangle_wire",
      "control_curves",
      "control_points",
      "shared_edges",
      "diagnostic_failures",
    ]) {
      assert.match(viewerSource + workspaceSource, new RegExp(layer));
    }
  });

  test("viewer recognizes V1.1 surface-family graph and hides open tip reference in normal mode", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const simulationSource = readFileSync(resolve(root, "src/simulationViewModel.js"), "utf-8");

    assert.match(viewerSource, /topology_first_blade_to_blade_5_loop_surface_family_graph/);
    assert.match(viewerSource, /v1_1_loop_family_shared_boundary_uv_mesh/);
    assert.match(simulationSource, /open_tip_reference/);
    assert.match(simulationSource, /reference_only/);
  });

  test("viewer keeps legacy opacity defaults outside V1.1 surface-family graphs", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /v11ViewerLayers\s*\|\|\s*v11SurfaceFamilyGraph[\s\S]*display\.opacity === undefined \? 0\.62 : display\.opacity/);
    assert.match(viewerSource, /surface\.role === "open_tip_reference" \|\| surface\.role === "reference_only"[\s\S]*return 0\.3/);
    assert.match(viewerSource, /if \(isEdgeClosure\)\s*\{\s*return 1\.0;\s*\}/);
    assert.match(viewerSource, /return 0\.92;\s*\}/);
  });

  test("manifest panel renders v1.0.2 feasibility and attachment metrics", () => {
    const manifestSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

    assert.match(manifestSource, /preset_feasibility_status/);
    assert.match(manifestSource, /continuous_blade_attachment_status/);
    assert.match(manifestSource, /geometry_patch_version/);
    assert.match(manifestSource, /attachment_quality/);
  });

  test("manifest panel labels v1.0.4 and v1.0.3 active graphs separately from v1.0.2 attachment", () => {
    const manifestSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

    assert.match(manifestSource, /geometry_patch_version === "1\.0\.4"/);
    assert.match(manifestSource, /V1\.0\.4 measured geometry contract graph/);
    assert.match(manifestSource, /v1_0_4_continuity_summary/);
    assert.match(manifestSource, /v1_0_4_angle_quality/);
    assert.match(manifestSource, /geometry_patch_version === "1\.0\.3"/);
    assert.match(manifestSource, /V1\.0\.3 section-loop\/root-blend graph/);
    assert.match(manifestSource, /V1\.0\.2 attachment/);
    assert.match(manifestSource, /deferred_reason/);
    assert.match(manifestSource, /surface_graph_status/);
  });

  test("application uses stable default layers without an active layer editor", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const panelSource = readFileSync(resolve(root, "src/components/GeometryLayerPanel.js"), "utf-8");
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.doesNotMatch(appSource, /GeometryLayerPanel/);
    assert.match(appSource, /visibleLayers: defaultVisibleLayers/);
    assert.match(panelSource, /layerSchema/);
    assert.match(viewerSource, /layerForSurface/);
    assert.match(viewerSource, /layerForConstructionFeature/);
  });

  test("application omits cfd simulation inspection controls", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const cfdPanelSource = readFileSync(resolve(root, "src/components/CfdManifestPanel.js"), "utf-8");
    const manifestPanelSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

    assert.match(appSource, /simulationViewMode: "cad_review_360"/);
    assert.doesNotMatch(appSource, /CfdManifestPanel|ManifestPanel/);
    assert.match(viewerSource, /surfaceVisibleInView/);
    assert.match(viewerSource, /patchSurfaceIds/);
    assert.match(cfdPanelSource, /cfdPatchGroups/);
    assert.match(cfdPanelSource, /MeshInspectionPanel/);
    assert.match(manifestPanelSource, /before/);
  });

  test("legacy editor files remain historical but the active application does not import them", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");

    for (const file of [
      "src/profileEditorModel.js",
      "src/bladeCurveEditorModel.js",
      "src/components/ProfileCurveEditor.js",
      "src/components/BladeCurveEditor.js",
      "src/components/CurveControlPanel.js",
      "src/components/GenerationStagePanel.js",
      "src/components/EdgeTreatmentPanel.js",
      "src/edgeTreatmentModel.js",
      "src/edgeTreatmentModel.test.js",
    ]) {
      assert.equal(existsSync(resolve(root, file)), true, `${file} should exist`);
    }

    assert.doesNotMatch(appSource, /curveOverrides|CurveControlPanel|transitionOverrides|geometryStage|GenerationStagePanel|EdgeTreatmentPanel/);
  });

  test("application has no editor visibility branch in preset-only review mode", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");

    assert.doesNotMatch(appSource, /editorVisibilityForPreset|ProfileCurveEditor|BladeCurveEditor|CurveControlPanel/);
    assert.match(appSource, /WORKSPACES/);
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

  test("application removes CFD and feature-debug panels from the active shell", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
    const modelSource = readFileSync(resolve(root, "src/simulationViewModel.js"), "utf-8");

    assert.doesNotMatch(appSource, /CfdManifestPanel|MeshInspectionPanel|feature_debug|cfd_full_360/);
    assert.match(modelSource, /engineering_drawing/);
  });

  test("application is preset-only and has no active parameter editors", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");

    assert.doesNotMatch(appSource, /ParameterPanel|CurveControlPanel|EdgeTreatmentPanel|ProfileCurveEditor|BladeCurveEditor/);
    assert.match(appSource, /instantiatePresetImpeller\(/);
    assert.match(appSource, /review_summary/);
    assert.doesNotMatch(appSource, /instantiateImpeller\(apiBase, synthesized\.engine_id, \{\}\)/);
  });

  test("application routes the full workspace through CAD review and engineering drawing", () => {
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");

    assert.match(appSource, /ReviewEngineeringDrawing/);
    assert.match(appSource, /h\(ModelViewer/);
    assert.doesNotMatch(appSource, /ParameterInspectionWorkspace/);
  });
});
