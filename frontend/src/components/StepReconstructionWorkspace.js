import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  createStepReconstructionAudit,
  stepReconstructionAuditManifest,
  stepReconstructionAuditStatus,
} from "../apiClient.js?v=1.1.10";
import {
  auditArtifactUrls,
  auditInProgress,
  auditStageRows,
  defaultStepOverlayVisibility,
  heatmapLegend,
  parameterDifferenceRows,
  reportSummaryRows,
  selectedInspectionProvenance,
  semanticRegionOptions,
  stepInspectionModel,
  stepOverlayOptions,
  terminalAuditStatus,
  unsupportedSourceFeatures,
} from "../stepReconstructionModel.js?v=1.1.6-r13_2";
import { StepComparisonScene } from "./StepComparisonScene.js?v=1.1.6-r22";

const h = React.createElement;

export function StepReconstructionWorkspace({ apiBase, initialAuditId = "", initialManifest = null, SceneComponent = StepComparisonScene, sceneRuntime }) {
  const [file, setFile] = useState(null);
  const [auditId, setAuditId] = useState(initialManifest?.audit_id || initialAuditId);
  const [status, setStatus] = useState(null);
  const [manifest, setManifest] = useState(initialManifest);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [readout, setReadout] = useState(null);
  const [selection, setSelection] = useState({ populationId: "main", spanStationId: "" });
  const [semanticRegion, setSemanticRegion] = useState("all");
  const [regionFilterStatus, setRegionFilterStatus] = useState({ mode: "unknown", filterable: null, message: "Region membership will be checked against the heatmap artifact." });
  const [overlays, setOverlays] = useState(defaultStepOverlayVisibility);
  const artifactUrls = useMemo(
    () => auditArtifactUrls(apiBase, manifest?.audit_id || auditId, manifest),
    [apiBase, auditId, manifest],
  );
  const reportRows = useMemo(() => parameterDifferenceRows(manifest), [manifest]);
  const legend = useMemo(() => heatmapLegend(manifest), [manifest]);
  const inspection = useMemo(() => stepInspectionModel(manifest, selection), [manifest, selection]);
  const regionOptions = useMemo(() => semanticRegionOptions(manifest), [manifest]);
  const selectedRegionAliases = useMemo(() => regionOptions.find((option) => option.id === semanticRegion)?.aliases || [semanticRegion], [regionOptions, semanticRegion]);
  const unsupportedFeatures = useMemo(() => unsupportedSourceFeatures(manifest), [manifest]);
  const updateReadout = useCallback((value) => setReadout(value), []);
  const updateRegionFilterStatus = useCallback((value) => setRegionFilterStatus(value), []);
  const auditActive = uploading || auditInProgress(status);
  const actionLabel = uploading ? "Uploading..." : status?.status === "QUEUED" ? "Queued" : status?.status === "RUNNING" ? "Reconstructing..." : "Reconstruct";

  useEffect(() => {
    if (!auditId || manifest?.audit_id === auditId) return undefined;
    let cancelled = false;
    let timer = null;
    let controller = null;
    let consecutiveFailures = 0;
    const schedule = (delay = 1200) => {
      if (!cancelled) timer = window.setTimeout(refreshAudit, delay);
    };
    async function refreshAudit() {
      controller = new AbortController();
      try {
        const next = await stepReconstructionAuditStatus(apiBase, auditId, { signal: controller.signal });
        let resolved = null;
        if (next.status === "PASS") {
          resolved = await stepReconstructionAuditManifest(apiBase, auditId, { signal: controller.signal });
        }
        if (cancelled) return;
        consecutiveFailures = 0;
        setError("");
        setStatus(next);
        if (resolved) setManifest(resolved);
        if (!terminalAuditStatus(next)) schedule();
      } catch (caught) {
        if (cancelled || caught?.name === "AbortError") return;
        if (caught?.status === 404 || caught?.status === 410) {
          setAuditId("");
          setStatus(null);
          setError(`Saved STEP audit ${auditId} is not available in the current backend. Select the source STEP and click Reconstruct to start a new audit.`);
          removeStepAuditDeepLink(auditId);
          return;
        }
        consecutiveFailures += 1;
        const message = caught instanceof Error ? caught.message : String(caught);
        if (consecutiveFailures >= 3) {
          setError(`${message}. Audit polling stopped after 3 consecutive failures.`);
          return;
        }
        setError(`${message}. Retrying audit status (${consecutiveFailures}/3).`);
        schedule(1200 * consecutiveFailures);
      }
    }
    void refreshAudit();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
      controller?.abort();
    };
  }, [apiBase, auditId, manifest?.audit_id]);

  useEffect(() => {
    if (!manifest) return;
    if (!regionOptions.some((option) => option.id === semanticRegion)) setSemanticRegion("all");
  }, [manifest, regionOptions, semanticRegion]);

  async function startAudit() {
    if (auditActive) return;
    setUploading(true);
    setError("");
    setManifest(null);
    setReadout(null);
    setRegionFilterStatus({ mode: "unknown", filterable: null, message: "Region membership will be checked against the heatmap artifact." });
    try {
      const accepted = await createStepReconstructionAudit(apiBase, file);
      setAuditId(accepted.audit_id);
      setStatus(accepted);
      if (accepted.status === "PASS") {
        const resolved = await stepReconstructionAuditManifest(apiBase, accepted.audit_id);
        setManifest(resolved);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setUploading(false);
    }
  }

  return h("section", { className: "step-reconstruction-workspace", "data-testid": "step-reconstruction-workspace" },
    h("div", { className: "step-audit-toolbar" },
      h("label", { className: "step-file-control" },
        h("span", null, "Source STEP"),
        h("input", { type: "file", accept: ".stp,.step,application/step", disabled: auditActive, onChange: (event) => setFile(event.target.files?.[0] || null) }),
      ),
      h("button", { type: "button", className: "primary-action", disabled: !file || auditActive, onClick: startAudit }, actionLabel),
      file ? h("span", { className: "step-file-fact" }, `${file.name} / ${(file.size / 1024 / 1024).toFixed(2)} MiB`) : null,
      auditId ? h("code", null, auditId) : null,
    ),
    error ? h("div", { className: "error-banner", role: "alert" }, error) : null,
    status?.failure ? h("div", { className: "error-banner", role: "alert" }, `${status.failure.reason}: ${status.failure.message}`) : null,
    manifest && (manifest.geometry_status === "REJECTED" || manifest.axis_first_algorithm_status === "REJECTED")
      ? h("div", { className: "geometry-rejected-banner", role: "alert" }, "GEOMETRY REJECTED - REVIEW ONLY")
      : null,
    h("ol", { className: "step-stage-rail", "aria-label": "STEP reconstruction stages" },
      auditStageRows(status).map((row) => h("li", { key: row.id, className: row.state }, h("span", null), row.label)),
    ),
    h("div", { className: "step-audit-grid" },
      manifest ? h(SceneErrorBoundary, { auditId: manifest?.audit_id }, h(SceneComponent, {
        artifactUrls,
        inspection,
        overlays,
        semanticRegion,
        semanticRegionAliases: selectedRegionAliases,
        onHeatmapReadout: updateReadout,
        onRegionFilterStatus: updateRegionFilterStatus,
        runtime: sceneRuntime,
      })) : h("div", { className: "step-comparison-placeholder" },
        h("strong", null, status?.status === "RUNNING" ? `Processing ${stageLabel(status.current_stage)}` : status?.status === "QUEUED" ? "Queued for reconstruction" : "Load a STEP model to begin reconstruction."),
      ),
      h("aside", { className: "step-report-pane" },
        h("header", null, h("h3", null, "Parameter & deviation report"), h("span", null, manifest?.units || "mm")),
        manifest ? h(InspectionControls, {
          inspection,
          overlays,
          semanticRegion,
          regionOptions,
          regionFilterStatus,
          onSelection: setSelection,
          onOverlays: setOverlays,
          onSemanticRegion: (value) => {
            setSemanticRegion(value);
            setRegionFilterStatus({ mode: "unknown", filterable: null, message: "Region membership will be checked against the heatmap artifact." });
          },
        }) : null,
        legend.length ? h("section", { className: "heatmap-legend", "aria-label": "Triangle-centroid reconstruction to source metrics" },
          h("h4", null, "Triangle-centroid reconstruction -> source metrics"),
          legend.map((row) => h("div", { key: row.label }, h("span", null, row.label), h("strong", null, `${formatNumber(row.value)} mm`))),
        ) : null,
        readout ? h("p", { className: "heatmap-readout" }, `Vertex-interpolated reconstruction -> source deviation ${formatNumber(readout.error_mm)} mm`) : null,
        manifest ? h(ReportSummary, { manifest, inspection }) : h("p", null, "Numeric evidence becomes available after all reconstruction stages pass."),
        reportRows.length ? h("div", { className: "step-parameter-table-wrap" }, h("table", { className: "step-parameter-table" },
          h("thead", null, h("tr", null, ["Parameter", "Source", "Mapped", "Rebuilt", "Delta", "Measure C", "Map C"].map((label) => h("th", { key: label }, label)))),
          h("tbody", null, reportRows.map((row) => h("tr", { key: row.feature_id },
            h("th", null, row.parameter_id), h("td", null, formatNumber(row.source_measurement)), h("td", null, formatNumber(row.mapped_v11_value)), h("td", null, formatNumber(row.reconstructed_value)), h("td", null, formatNumber(row.delta)), h("td", null, formatConfidence(row.measurement_confidence)), h("td", null, formatConfidence(row.mapping_confidence)),
          ))),
        )) : null,
        unsupportedFeatures.length ? h("section", { className: "unsupported-feature-list" },
          h("h4", null, `Unsupported source features (${unsupportedFeatures.length})`),
          unsupportedFeatures.map((item, index) => h("p", { key: item.source_face_id || item.feature || index },
            `${item.source_face_id || stageLabel(item.feature, "Unnamed source feature")} / ${stageLabel(item.reason, "excluded from deviation")}`,
          )),
        ) : null,
      ),
    ),
  );
}

function removeStepAuditDeepLink(auditId) {
  if (!globalThis.window?.location || !globalThis.window?.history) return;
  const url = new URL(globalThis.window.location.href);
  if (url.searchParams.get("stepAudit") !== auditId) return;
  url.searchParams.delete("stepAudit");
  globalThis.window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function InspectionControls({ inspection, overlays, semanticRegion, regionOptions, regionFilterStatus, onSelection, onOverlays, onSemanticRegion }) {
  return h("div", { className: "step-inspection-controls" },
    h("label", null, "Population", h("select", { value: inspection.populationId, onChange: (event) => onSelection((current) => ({ ...current, populationId: event.target.value, spanStationId: "" })) }, inspection.populations.map((population) => h("option", { key: population.id, value: population.id }, population.label)))),
    h("label", null, "Span", h("select", { value: inspection.spanStationId, onChange: (event) => onSelection((current) => ({ ...current, spanStationId: event.target.value })) },
      inspection.spanStationId && !inspection.stations.some((station) => station.id === inspection.spanStationId) ? h("option", { value: inspection.spanStationId }, `Unavailable: ${inspection.spanStationId}`) : null,
      inspection.stations.map((station) => h("option", { key: station.id, value: station.id }, station.label)),
    )),
    h("label", null, "Heatmap", h("select", { value: semanticRegion, onChange: (event) => onSemanticRegion(event.target.value) }, regionOptions.map((region) => h("option", { key: region.id, value: region.id }, region.label)))),
    semanticRegion !== "all" ? h("p", {
      className: `step-region-filter-status ${regionFilterStatus?.filterable === false ? "evidence-only" : regionFilterStatus?.filterable === true ? "filterable" : "unknown"}`,
      role: "status",
    }, regionFilterStatus?.message || "Region membership is unavailable.") : null,
    h("fieldset", { className: "step-overlay-toggles" }, h("legend", null, "Overlays"), stepOverlayOptions.map((option) => h("label", { key: option.id }, h("input", { type: "checkbox", checked: Boolean(overlays[option.id]), onChange: (event) => onOverlays((current) => ({ ...current, [option.id]: event.target.checked })) }), option.label))),
  );
}

function ReportSummary({ manifest, inspection }) {
  const summaryRows = reportSummaryRows(manifest, inspection);
  const provenance = selectedInspectionProvenance(inspection);
  return h(React.Fragment, null,
    h("dl", { className: "step-report-summary" },
      summaryRows.map((row) => h(React.Fragment, { key: row.id }, h("dt", null, row.label), h("dd", null, row.value))),
    ),
    inspection.selectedLoop ? h("dl", { className: "step-selected-provenance" },
      h("dt", null, "Selected source loop"), h("dd", null, `${provenance.representative_source_component_id || "Unavailable"} / ${provenance.span_station_id || "Unavailable"} / ${provenance.loop_id || "Unavailable"}`),
      h("dt", null, "Source face IDs"), h("dd", null, provenance.source_face_ids.length ? provenance.source_face_ids.join(", ") : "Unavailable in this manifest"),
      h("dt", null, "Coordinate frame"), h("dd", null, provenance.coordinate_frame || "Unavailable in this manifest"),
      h("dt", null, "Measurement method"), h("dd", null, provenance.measurement_method || "Unavailable in this manifest"),
      h("dt", null, "Selected mapping evidence"), h("dd", null, provenance.mapping_term_count ? `${provenance.mapping_term_count} bound record(s)` : "Unavailable for this population/station/loop"),
    ) : h("p", { className: "step-selection-unavailable", role: "status" }, inspection.selectionEvidence?.message || "Selected source-loop evidence is unavailable."),
    inspection.attachmentRows?.length ? h("section", { className: "step-attachment-report", "aria-label": "Attachment mapping evidence" },
      h("h4", null, "Root attachment mapping"),
      inspection.attachmentRows.map((row) => h("dl", { key: row.id },
        h("dt", null, "Lift"), h("dd", null, `${formatNumber(row.measured_lift_mm)} source / ${formatNumber(row.fitted_lift_mm)} fitted mm`),
        h("dt", null, "Width"), h("dd", null, `${formatNumber(row.measured_width_mm)} source / ${formatNumber(row.fitted_width_mm)} fitted mm`),
        h("dt", null, "Residual / gate"), h("dd", null, `${formatPercent(row.maximum_relative_residual)} / ${row.status}`),
        h("dt", null, "Measurement promotability"), h("dd", null, row.promotable === true ? "Locally promotable" : row.promotable === false ? "Diagnostic only" : "Unavailable"),
        h("dt", null, "Source provenance"), h("dd", null, row.source_ids.length ? row.source_ids.join(", ") : "Unavailable"),
        h("dt", null, "Method / frame"), h("dd", null, `${row.method || "Unavailable"} / ${row.coordinate_frame || "Unavailable"}`),
      )),
    ) : null,
    inspection.metricRows.length ? h("dl", { className: "step-metric-summary" }, inspection.metricRows.map((row) => h(React.Fragment, { key: row.id }, h("dt", null, row.label), h("dd", null, `${formatNumber(row.value)}${row.state ? ` / ${row.state}` : ""}`)))) : null,
  );
}

class SceneErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, auditId: props.auditId };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  static getDerivedStateFromProps(props, state) {
    return props.auditId !== state.auditId ? { error: null, auditId: props.auditId } : null;
  }

  render() {
    if (this.state.error) return h("div", { className: "step-comparison-placeholder error-banner", role: "alert" }, this.state.error.message || "STEP inspection renderer failed");
    return this.props.children;
  }
}

function formatNumber(value) {
  const number = Number(value);
  return value !== null && value !== "" && value !== undefined && Number.isFinite(number) ? number.toFixed(Math.abs(number) >= 100 ? 1 : 3) : "--";
}

function formatConfidence(value) {
  const number = Number(value);
  return value !== null && value !== "" && value !== undefined && Number.isFinite(number) ? `${Math.round(number * 100)}%` : "--";
}

function formatPercent(value) {
  const number = Number(value);
  return value !== null && value !== "" && value !== undefined && Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : "--";
}

function stageLabel(value, fallback = "STEP") {
  return typeof value === "string" && value ? value.replaceAll("_", " ") : fallback;
}
