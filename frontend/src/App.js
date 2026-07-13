import React, { Component, useEffect, useMemo, useState } from "react";

import {
  engineeringDrawingConstructionTables,
  engineeringDrawingView,
  instantiatePresetImpeller,
  modelExportUrl,
  synthesizeImpeller,
} from "./apiClient.js?v=1.1.9";
import { apiDefault, exportFilename, exportFileOptions, presets, selectedPreset } from "./appModel.js?v=1.1.11";
import { defaultVisibleLayers } from "./workspaceModel.js?v=1.1.5";
import { ModelViewer } from "./components/ModelViewer.js?v=1.1.8";
import { ReviewEngineeringDrawing } from "./components/ReviewEngineeringDrawing.js?v=1.1.5.1";
import { StepReconstructionWorkspace } from "./components/StepReconstructionWorkspace.js?v=1.1.6-r2";

const h = React.createElement;
const WORKSPACES = [
  { id: "cad_review", label: "CAD Review" },
  { id: "engineering_drawing", label: "Engineering Drawing" },
  { id: "step_reconstruction", label: "STEP Reconstruction" },
];

export function App() {
  const [apiBase, setApiBase] = useState(apiDefault);
  const [selectedPresetId, setSelectedPresetId] = useState(presets[0].id);
  const [manifest, setManifest] = useState(null);
  const [drawingContract, setDrawingContract] = useState(null);
  const [drawingLoading, setDrawingLoading] = useState(false);
  const [drawingError, setDrawingError] = useState("");
  const [drawingRevision, setDrawingRevision] = useState(0);
  const [stlUrl, setStlUrl] = useState("");
  const [workspace, setWorkspace] = useState("cad_review");
  const [viewMode, setViewMode] = useState("shaded");
  const [autoRotate, setAutoRotate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const activePreset = useMemo(() => selectedPreset(selectedPresetId), [selectedPresetId]);
  const exportLinks = useMemo(() => resolvedExportLinks(apiBase, manifest, activePreset), [apiBase, manifest, activePreset]);

  useEffect(() => {
    if (workspace !== "engineering_drawing" || !manifest?.run_id) return undefined;
    let cancelled = false;
    setDrawingLoading(true);
    setDrawingError("");
    engineeringDrawingView(apiBase, manifest.run_id, "top")
      .then((payload) => {
        if (!cancelled) setDrawingContract(mergeDrawingView(null, payload));
      })
      .catch((caught) => {
        if (!cancelled) setDrawingError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => {
        if (!cancelled) setDrawingLoading(false);
      });
    return () => { cancelled = true; };
  }, [apiBase, drawingRevision, manifest?.run_id, workspace]);

  async function requestDrawingView(viewId) {
    if (!manifest?.run_id) return;
    if (viewId === "construction" && drawingContract?.construction_parameter_registry?.records?.length) return;
    if (viewId !== "construction" && drawingContract?.views?.[viewId]) return;
    setDrawingLoading(true);
    setDrawingError("");
    try {
      if (viewId === "construction") {
        const payload = await engineeringDrawingConstructionTables(apiBase, manifest.run_id);
        setDrawingContract((current) => mergeConstructionTables(current, payload));
      } else {
        const payload = await engineeringDrawingView(apiBase, manifest.run_id, viewId);
        setDrawingContract((current) => mergeDrawingView(current, payload));
      }
    } catch (caught) {
      setDrawingError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setDrawingLoading(false);
    }
  }

  async function generateModel() {
    setLoading(true);
    setError("");
    try {
      const synthesized = await synthesizeImpeller(apiBase, activePreset);
      const run = await instantiatePresetImpeller(
        apiBase,
        synthesized.engine_id,
        "edge_closures",
        workspace === "engineering_drawing" ? "review_summary" : "full",
      );
      setManifest(run.manifest);
      setDrawingContract(null);
      setDrawingError("");
      setDrawingRevision((revision) => revision + 1);
      setStlUrl(modelExportUrl(apiBase, run.run_id, "stl"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  function choosePreset(event) {
    setSelectedPresetId(event.target.value);
    setManifest(null);
    setDrawingContract(null);
    setDrawingError("");
    setStlUrl("");
    setError("");
  }

  return h(
    "main",
    { className: "review-app-shell", "data-release": "1.1.6" },
    h(
      "header",
      { className: "review-toolbar" },
      h("div", { className: "review-brand" }, h("span", { className: "brand-mark" }, "IR"), h("div", null,
        h("h1", null, "Impeller Rule Lab"),
        h("p", null, "V1.1.6 STEP audit / V1.1.5 preset review"),
      )),
      h("label", { className: "review-preset-select" },
        h("span", null, "Preset"),
        h("select", { value: selectedPresetId, onChange: choosePreset, "data-testid": "preset-select" },
          presets.map((preset) => h("option", { key: preset.id, value: preset.id }, preset.name)),
        ),
      ),
      h("nav", { className: "review-workspace-tabs", "aria-label": "Review workspaces" },
        WORKSPACES.map((item) => h("button", {
          key: item.id,
          type: "button",
          className: workspace === item.id ? "selected" : "",
          onClick: () => setWorkspace(item.id),
          "data-testid": `workspace-${item.id}`,
        }, item.label)),
      ),
      workspace !== "step_reconstruction" ? h("button", { className: "primary-action", onClick: generateModel, disabled: loading, "data-testid": "generate-model" },
        loading ? "Generating..." : "Generate",
      ) : null,
      h("details", { className: "review-disclosure" },
        h("summary", null, "Preset data"),
        h("div", { className: "review-disclosure-content" },
          h("strong", null, activePreset.name),
          h("p", null, activePreset.summary),
          h("pre", null, JSON.stringify({
            preset_id: activePreset.presetId,
            parameters: activePreset.parameters,
            loop_family: activePreset.loopFamilyDefaults,
            support_profiles: activePreset.profileOverrides,
          }, null, 2)),
        ),
      ),
      h("details", { className: "review-disclosure" },
        h("summary", null, manifest ? "Resolved manifest" : "Connection"),
        h("div", { className: "review-disclosure-content" },
          h("label", { className: "compact-api-field" }, h("span", null, "API base"), h("input", {
            value: apiBase,
            onChange: (event) => setApiBase(event.target.value),
          })),
          manifest ? h(ManifestSummary, { manifest, exportLinks }) : h("p", null, "No resolved model."),
        ),
      ),
    ),
    h("section", { className: "review-titlebar" }, workspace === "step_reconstruction"
      ? h("div", null,
          h("p", { className: "eyebrow" }, "SOURCE B-REP / V1.1.2 RECONSTRUCTION / DEVIATION"),
          h("h2", null, "STEP Reconstruction Audit"),
          h("p", null, "Load one STEP solid, recover current-rule parameters, reconstruct with unchanged V1.1.2 geometry, and compare the result."),
        )
      : [
          h("div", { key: "title" }, h("p", { className: "eyebrow" }, activePreset.tags.join(" / ")), h("h2", null, activePreset.name)),
          h("p", { key: "summary" }, activePreset.summary),
        ],
    ),
    h("div", { className: "review-message-slot" },
      error ? h("div", { className: "error-banner review-error", role: "alert" }, error) : null,
    ),
    h(
      ReviewErrorBoundary,
      { resetKey: `${selectedPresetId}:${workspace}:${manifest?.run_id || "empty"}` },
      workspace === "step_reconstruction"
        ? h(StepReconstructionWorkspace, { apiBase })
        : workspace === "engineering_drawing"
        ? h(ReviewEngineeringDrawing, {
            key: manifest?.run_id || selectedPresetId,
            contract: drawingContract,
            loading: drawingLoading,
            error: drawingError,
            surfaceGraph: manifest?.geometry?.surface_graph || null,
            manifest,
            onRequestView: requestDrawingView,
          })
        : h(ModelViewer, {
            stlUrl,
            surfaceGraph: manifest?.geometry?.surface_graph || null,
            constructionLines: manifest?.geometry?.construction_lines || {},
            viewMode,
            setViewMode,
            simulationViewMode: "cad_review_360",
            meshOverlayMode: "triangle_edges",
            setMeshOverlayMode: () => {},
            selectedPatch: null,
            manifest,
            autoRotate,
            setAutoRotate,
            visibleLayers: defaultVisibleLayers,
          }),
    ),
  );
}

function mergeDrawingView(current, payload) {
  return {
    ...(current || {}),
    contract_version: payload.contract_version,
    generation_id: payload.generation_id,
    geometry_patch_version: payload.geometry_patch_version,
    preset_id: payload.preset_id,
    units: payload.units,
    views: { ...(current?.views || {}), [payload.view_id]: payload.view },
    construction_tables: { ...(current?.construction_tables || {}), ...(payload.construction_tables || {}) },
    construction_parameter_registry: current?.construction_parameter_registry || {
      records: [],
      unaccounted_parameter_ids: payload.registry_summary?.unaccounted_parameter_ids || [],
    },
  };
}

function mergeConstructionTables(current, payload) {
  return {
    ...(current || {}),
    contract_version: payload.contract_version,
    generation_id: payload.generation_id,
    preset_id: payload.preset_id,
    views: current?.views || {},
    construction_tables: payload.construction_tables || {},
    construction_parameter_registry: payload.construction_parameter_registry || { records: [], unaccounted_parameter_ids: [] },
  };
}

function ManifestSummary({ manifest, exportLinks }) {
  return h("div", { className: "manifest-summary" },
    h("dl", null,
      h("dt", null, "Runtime"), h("dd", null, manifest.runtime_release_version || "unknown"),
      h("dt", null, "Geometry"), h("dd", null, manifest.geometry_patch_version || "unknown"),
      h("dt", null, "Validation"), h("dd", null, manifest.geometry_validation_status || "unknown"),
      h("dt", null, "Run"), h("dd", null, manifest.run_id || "unknown"),
    ),
    h("div", { className: "manifest-export-links" }, exportLinks.map((link) => h("a", {
      key: link.id,
      href: link.href,
      download: link.download,
    }, link.label))),
  );
}

class ReviewErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, resetKey: props.resetKey };
  }

  static getDerivedStateFromProps(props, state) {
    return props.resetKey !== state.resetKey ? { error: null, resetKey: props.resetKey } : null;
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    return this.state.error
      ? h("section", { className: "review-render-error", role: "alert" },
          h("h2", null, "View rendering failed"),
          h("p", null, this.state.error.message || String(this.state.error)),
        )
      : this.props.children;
  }
}

function resolvedExportLinks(apiBase, manifest, activePreset) {
  if (!manifest?.run_id) return [];
  const available = new Set(Object.keys(manifest.exports || {}));
  return exportFileOptions
    .filter((option) => available.size === 0 || available.has(option.id))
    .map((option) => ({
      ...option,
      href: modelExportUrl(apiBase, manifest.run_id, option.id),
      download: exportFilename(manifest.preset_id || activePreset.presetId, manifest.run_id, option.id),
    }));
}
