import React, { useMemo, useState } from "react";

import { instantiateImpeller, modelExportUrl, synthesizeImpeller } from "./apiClient.js";
import {
  apiDefault,
  exportFilename,
  exportFileOptions,
  overridesAfterParameterChange,
  presets,
  selectedPreset,
} from "./appModel.js";
import { buildTransitionOverridePayload } from "./edgeTreatmentModel.js";
import { viewModeOptions } from "./simulationViewModel.js";
import { defaultVisibleLayers } from "./workspaceModel.js";
import { BladeCurveEditor } from "./components/BladeCurveEditor.js";
import { CfdManifestPanel } from "./components/CfdManifestPanel.js";
import { EdgeTreatmentPanel } from "./components/EdgeTreatmentPanel.js";
import { GenerationStagePanel } from "./components/GenerationStagePanel.js";
import { GeometryLayerPanel } from "./components/GeometryLayerPanel.js";
import { ManifestPanel } from "./components/ManifestPanel.js";
import { ModelViewer } from "./components/ModelViewer.js";
import { ParameterPanel } from "./components/ParameterPanel.js";
import { ProfileCurveEditor } from "./components/ProfileCurveEditor.js";
import { PresetList } from "./components/PresetList.js";

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
  const [selectedPatch, setSelectedPatch] = useState(null);
  const [autoRotate, setAutoRotate] = useState(false);
  const [visibleLayers, setVisibleLayers] = useState(defaultVisibleLayers);
  const [profileOverrides, setProfileOverrides] = useState(() => clonePresetValue(firstPreset.profileOverrides));
  const [curveOverrides, setCurveOverrides] = useState(() => clonePresetValue(firstPreset.curveOverrides));
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
        curveOverrides,
        geometryStage,
        buildTransitionOverridePayload(transitionOverrides),
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
        parameters,
        onChange: updateParameter,
        onGenerate: generateModel,
        onReset: () => {
          setParameters({ ...activePreset.parameters });
          setFacets({ ...activePreset.facets });
          setProfileOverrides(clonePresetValue(activePreset.profileOverrides));
          setCurveOverrides(clonePresetValue(activePreset.curveOverrides));
          setTransitionOverrides({});
          setGeometryStage("edge_closures");
        },
        loading,
      }),
      h(GenerationStagePanel, {
        geometryStage,
        onChange: setGeometryStage,
      }),
      h(EdgeTreatmentPanel, {
        manifest,
        overrides: transitionOverrides,
        onChange: setTransitionOverrides,
      }),
      h(ProfileCurveEditor, {
        manifest,
        profileOverrides,
        onProfileOverridesChange: setProfileOverrides,
        onResetProfileOverrides: () => setProfileOverrides(null),
      }),
      h(BladeCurveEditor, {
        parameters,
        curveOverrides,
        onCurveOverridesChange: setCurveOverrides,
        onResetCurveOverrides: () => setCurveOverrides(null),
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
