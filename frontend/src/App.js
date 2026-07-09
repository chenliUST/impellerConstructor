import React, { useMemo, useState } from "react";

import { instantiateImpeller, modelExportUrl, synthesizeImpeller } from "./apiClient.js?v=1.1.5";
import {
  apiDefault,
  curveControlsForPreset,
  editorVisibilityForPreset,
  exportFilename,
  exportFileOptions,
  overridesAfterParameterChange,
  presets,
  selectedPreset,
} from "./appModel.js?v=1.1.5";
import { buildTransitionOverridePayload } from "./edgeTreatmentModel.js?v=1.1.5";
import { viewModeOptions } from "./simulationViewModel.js?v=1.1.5";
import { defaultVisibleLayers } from "./workspaceModel.js?v=1.1.5";
import { BladeCurveEditor } from "./components/BladeCurveEditor.js?v=1.1.5";
import { CfdManifestPanel } from "./components/CfdManifestPanel.js?v=1.1.5";
import { CurveControlPanel } from "./components/CurveControlPanel.js?v=1.1.5";
import { EdgeTreatmentPanel } from "./components/EdgeTreatmentPanel.js?v=1.1.5";
import { GenerationStagePanel } from "./components/GenerationStagePanel.js?v=1.1.5";
import { GeometryLayerPanel } from "./components/GeometryLayerPanel.js?v=1.1.5";
import { ManifestPanel } from "./components/ManifestPanel.js?v=1.1.5";
import { ModelViewer } from "./components/ModelViewer.js?v=1.1.5";
import { ParameterPanel } from "./components/ParameterPanel.js?v=1.1.5";
import { ParameterViewsPanel } from "./components/ParameterViewsPanel.js?v=1.1.6";
import { ProfileCurveEditor } from "./components/ProfileCurveEditor.js?v=1.1.5";
import { PresetList } from "./components/PresetList.js?v=1.1.5";

const h = React.createElement;

export function App() {
  const firstPreset = presets[0];
  const [apiBase, setApiBase] = useState(apiDefault);
  const [selectedPresetId, setSelectedPresetId] = useState(firstPreset.id);
  const [parameters, setParameters] = useState({ ...firstPreset.parameters });
  const [facets, setFacets] = useState({ ...firstPreset.facets });
  const [engineId, setEngineId] = useState("");
  const [manifest, setManifest] = useState(null);
  const [stlUrl, setStlUrl] = useState("");
  const [viewMode, setViewMode] = useState("combined");
  const [simulationViewMode, setSimulationViewMode] = useState("cad_review_360");
  const [meshOverlayMode, setMeshOverlayMode] = useState("triangle_edges");
  const [selectedPatch, setSelectedPatch] = useState(null);
  const [autoRotate, setAutoRotate] = useState(false);
  const [visibleLayers, setVisibleLayers] = useState(defaultVisibleLayers);
  const [profileOverrides, setProfileOverrides] = useState(() => clonePresetValue(firstPreset.profileOverrides));
  const [curveOverrides, setCurveOverrides] = useState(() => clonePresetValue(firstPreset.curveOverrides));
  const [curveControlOverrides, setCurveControlOverrides] = useState(null);
  const [sectionLoopOverrides, setSectionLoopOverrides] = useState(null);
  const [bladeToBladeLoopFamilyOverrides, setBladeToBladeLoopFamilyOverrides] = useState({});
  const [transitionOverrides, setTransitionOverrides] = useState({});
  const [geometryStage, setGeometryStage] = useState("edge_closures");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const activePreset = useMemo(() => selectedPreset(selectedPresetId), [selectedPresetId]);
  const facetsChanged = useMemo(
    () => JSON.stringify(facets) !== JSON.stringify(activePreset.facets),
    [activePreset, facets],
  );
  const facetLabel = useMemo(() => Object.values(facets).join(" / ").replaceAll("_", " "), [facets]);
  const exportLinks = useMemo(() => {
    if (!manifest?.run_id) {
      return [];
    }
    const exportKeys = Object.keys(manifest.exports || {});
    const options = exportKeys.length
      ? exportFileOptions.filter((option) => exportKeys.includes(option.id))
      : exportFileOptions;

    return options.map((option) => ({
      ...option,
      href: modelExportUrl(apiBase, manifest.run_id, option.id),
      download: exportFilename(manifest.preset_id || activePreset.presetId, manifest.run_id, option.id),
    }));
  }, [activePreset, apiBase, manifest]);
  const simulationModes = viewModeOptions();
  const editorVisibility = useMemo(() => editorVisibilityForPreset(activePreset), [activePreset]);
  const activeCurveControls = useMemo(
    () =>
      mergePlainObjects(
        mergePlainObjects(curveControlsForPreset(activePreset), curveControlOverrides),
        bladeToBladeLoopFamilyOverrides,
      ),
    [activePreset, bladeToBladeLoopFamilyOverrides, curveControlOverrides],
  );
  const instantiateCurveOverrides = useMemo(
    () => mergePlainObjects(curveOverrides, curveControlOverrides),
    [curveOverrides, curveControlOverrides],
  );

  async function generateModel() {
    setLoading(true);
    setError("");

    try {
      const synthesized = await synthesizeImpeller(apiBase, { ...activePreset, facets });
      const currentEngineId = synthesized.engine_id;
      setEngineId(currentEngineId);

      const run = await instantiateImpeller(
        apiBase,
        currentEngineId,
        parameters,
        profileOverrides,
        instantiateCurveOverrides,
        geometryStage,
        buildTransitionOverridePayload(transitionOverrides),
        sectionLoopOverrides,
        bladeToBladeLoopFamilyOverrides,
      );
      setManifest(run.manifest);
      setStlUrl(modelExportUrl(apiBase, run.run_id, "stl"));
      setSelectedPatch(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  function choosePreset(preset) {
    setSelectedPresetId(preset.id);
    setParameters({ ...preset.parameters });
    setFacets({ ...preset.facets });
    setEngineId("");
    setManifest(null);
    setStlUrl("");
    setSelectedPatch(null);
    setProfileOverrides(clonePresetValue(preset.profileOverrides));
    setCurveOverrides(clonePresetValue(preset.curveOverrides));
    setCurveControlOverrides(null);
    setSectionLoopOverrides(null);
    setBladeToBladeLoopFamilyOverrides({});
    setTransitionOverrides({});
    setGeometryStage("edge_closures");
  }

  function updateParameter(name, value) {
    setParameters((current) => ({ ...current, [name]: value }));
    const nextOverrides = overridesAfterParameterChange(name, profileOverrides, curveOverrides);
    if (nextOverrides.profileOverrides !== profileOverrides) {
      setProfileOverrides(nextOverrides.profileOverrides);
    }
    if (nextOverrides.curveOverrides !== curveOverrides) {
      setCurveOverrides(nextOverrides.curveOverrides);
      setCurveControlOverrides(null);
      setSectionLoopOverrides(null);
      setBladeToBladeLoopFamilyOverrides({});
    }
  }

  function updateFacet(name, value) {
    setFacets((current) => ({ ...current, [name]: value }));
    setEngineId("");
    setSelectedPatch(null);
  }

  function updateLayer(layerId, visible) {
    setVisibleLayers((current) => ({ ...current, [layerId]: visible }));
  }

  function handleCurveControlChange(payload) {
    setCurveControlOverrides((current) => mergePlainObjects(current, payload?.curve_overrides || {}));
    setSectionLoopOverrides((current) => mergePlainObjects(current, payload?.section_loop_overrides || {}));
    setBladeToBladeLoopFamilyOverrides((current) =>
      mergePlainObjects(current, payload?.blade_to_blade_loop_family_overrides || {}),
    );
  }

  return h(
    "main",
    { className: "app-shell" },
    h(
      "aside",
      { className: "left-panel" },
      h("div", { className: "brand" }, h("span", { className: "brand-mark" }, "IR"), h("div", null, h("h1", null, "Impeller Rule Lab"), h("p", null, "Deterministic STL visual testing"))),
      h(
        "label",
        { className: "api-field" },
        h("span", null, "API base"),
        h("input", {
          value: apiBase,
          onChange: (event) => {
            setApiBase(event.target.value);
            setEngineId("");
          },
        }),
      ),
      h(PresetList, {
        presets,
        selectedId: selectedPresetId,
        onSelect: choosePreset,
      }),
      h(ParameterPanel, {
        activePreset,
        parameters,
        onChange: updateParameter,
        onGenerate: generateModel,
        onReset: () => {
          setParameters({ ...activePreset.parameters });
          setFacets({ ...activePreset.facets });
          setProfileOverrides(clonePresetValue(activePreset.profileOverrides));
          setCurveOverrides(clonePresetValue(activePreset.curveOverrides));
          setCurveControlOverrides(null);
          setSectionLoopOverrides(null);
          setBladeToBladeLoopFamilyOverrides({});
          setTransitionOverrides({});
          setGeometryStage("edge_closures");
        },
        loading,
      }),
      h(GenerationStagePanel, {
        geometryStage,
        onChange: setGeometryStage,
      }),
      editorVisibility.edgeTreatmentPanel
        ? h(EdgeTreatmentPanel, {
            manifest,
            overrides: transitionOverrides,
            onChange: setTransitionOverrides,
          })
        : null,
      editorVisibility.profileCurveEditor
        ? h(ProfileCurveEditor, {
            manifest,
            profileOverrides,
            onProfileOverridesChange: setProfileOverrides,
            onResetProfileOverrides: () => setProfileOverrides(null),
          })
        : null,
      editorVisibility.bladeCurveEditor
        ? h(BladeCurveEditor, {
            parameters,
            curveOverrides,
            onCurveOverridesChange: setCurveOverrides,
            onResetCurveOverrides: () => setCurveOverrides(null),
          })
        : null,
      editorVisibility.curveControlPanel
        ? h(CurveControlPanel, {
            curves: activeCurveControls,
            onChange: handleCurveControlChange,
          })
        : null,
      h(ParameterViewsPanel, {
        activePreset,
        manifest,
      }),
      h(GeometryLayerPanel, {
        manifest,
        visibleLayers,
        onToggle: updateLayer,
      }),
    ),
    h(
      "section",
      { className: "viewer-column" },
      h(
        "div",
        { className: "viewer-header" },
        h(
          "div",
          null,
          h("p", { className: "eyebrow" }, facetLabel),
          h("h2", null, facetsChanged ? "Custom impeller facet study" : activePreset.name),
          h(
            "p",
            null,
            facetsChanged
              ? `Base preset: ${activePreset.name}. Parameters remain editable independently of facets.`
              : activePreset.summary,
          ),
        ),
        h(
          "div",
          { className: "viewer-header-actions" },
          h(
            "div",
            { className: "view-mode-tabs" },
            simulationModes.map((mode) =>
              h(
                "button",
                {
                  key: mode.id,
                  className: simulationViewMode === mode.id ? "selected" : "",
                  type: "button",
                  onClick: () => setSimulationViewMode(mode.id),
                },
                mode.label,
              ),
            ),
          ),
          h(
            "button",
            { className: "primary-action", onClick: generateModel, disabled: loading },
            loading ? "Generating..." : "Generate",
          ),
        ),
      ),
      error ? h("div", { className: "error-banner" }, error) : null,
      h(ModelViewer, {
        stlUrl,
        surfaceGraph: manifest?.geometry?.surface_graph || null,
        constructionLines: manifest?.geometry?.construction_lines || {},
        viewMode,
        setViewMode,
        simulationViewMode,
        meshOverlayMode,
        setMeshOverlayMode,
        selectedPatch,
        manifest,
        autoRotate,
        setAutoRotate,
        visibleLayers,
      }),
    ),
    h(ManifestPanel, {
      manifest,
      exportLinks,
      before: h(CfdManifestPanel, {
        manifest,
        selectedPatch,
        onSelectPatch: setSelectedPatch,
      }),
    }),
  );
}

function clonePresetValue(value) {
  return value ? JSON.parse(JSON.stringify(value)) : null;
}

function mergePlainObjects(left, right) {
  if (!left && !right) {
    return null;
  }
  if (!left) {
    return clonePresetValue(right);
  }
  if (!right) {
    return clonePresetValue(left);
  }
  const merged = clonePresetValue(left) || {};
  for (const [key, value] of Object.entries(right)) {
    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = mergePlainObjects(merged[key], value);
    } else {
      merged[key] = clonePresetValue(value);
    }
  }
  return merged;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
