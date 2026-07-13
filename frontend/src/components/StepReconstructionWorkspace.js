import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  createStepReconstructionAudit,
  stepReconstructionAuditManifest,
  stepReconstructionAuditStatus,
} from "../apiClient.js?v=1.1.6";
import {
  auditArtifactUrls,
  auditInProgress,
  auditStageRows,
  heatmapLegend,
  parameterDifferenceRows,
  terminalAuditStatus,
} from "../stepReconstructionModel.js?v=1.1.6-r2";
import { StepComparisonScene } from "./StepComparisonScene.js?v=1.1.6";

const h = React.createElement;

export function StepReconstructionWorkspace({ apiBase }) {
  const [file, setFile] = useState(null);
  const [auditId, setAuditId] = useState("");
  const [status, setStatus] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [readout, setReadout] = useState(null);
  const artifactUrls = useMemo(() => auditArtifactUrls(apiBase, manifest?.audit_id), [apiBase, manifest?.audit_id]);
  const reportRows = useMemo(() => parameterDifferenceRows(manifest), [manifest]);
  const legend = useMemo(() => heatmapLegend(manifest), [manifest]);
  const updateReadout = useCallback((value) => setReadout(value), []);
  const auditActive = uploading || auditInProgress(status);
  const actionLabel = uploading ? "Uploading..." : status?.status === "QUEUED" ? "Queued" : status?.status === "RUNNING" ? "Reconstructing..." : "Reconstruct";

  useEffect(() => {
    if (!auditId || terminalAuditStatus(status)) return undefined;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await stepReconstructionAuditStatus(apiBase, auditId);
        if (cancelled) return;
        setStatus(next);
        if (next.status === "PASS") {
          const resolved = await stepReconstructionAuditManifest(apiBase, auditId);
          if (!cancelled) setManifest(resolved);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      }
    }, 1200);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [apiBase, auditId, status?.status]);

  async function startAudit() {
    if (auditActive) return;
    setUploading(true);
    setError("");
    setManifest(null);
    setReadout(null);
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
    h("ol", { className: "step-stage-rail", "aria-label": "STEP reconstruction stages" },
      auditStageRows(status).map((row) => h("li", { key: row.id, className: row.state }, h("span", null), row.label)),
    ),
    h("div", { className: "step-audit-grid" },
      manifest ? h(StepComparisonScene, { artifactUrls, onHeatmapReadout: updateReadout }) : h("div", { className: "step-comparison-placeholder" },
        h("strong", null, status?.status === "RUNNING" ? `Processing ${status.current_stage?.replaceAll("_", " ") || "STEP"}` : status?.status === "QUEUED" ? "Queued for reconstruction" : "Load a STEP model to begin reconstruction."),
        h("p", null, "The source B-Rep remains authoritative. The reconstructed pane uses unchanged V1.1.2 geometry rules."),
      ),
      h("aside", { className: "step-report-pane" },
        h("header", null, h("h3", null, "Parameter & deviation report"), h("span", null, manifest?.units || "mm")),
        legend.length ? h("div", { className: "heatmap-legend" }, legend.map((row) => h("div", { key: row.label }, h("span", null, row.label), h("strong", null, formatNumber(row.value))))) : null,
        readout ? h("p", { className: "heatmap-readout" }, `Cursor deviation ${formatNumber(readout.error_mm)} mm`) : null,
        manifest ? h(ReportSummary, { manifest }) : h("p", null, "Numeric evidence becomes available after all reconstruction stages pass."),
        reportRows.length ? h("div", { className: "step-parameter-table-wrap" }, h("table", { className: "step-parameter-table" },
          h("thead", null, h("tr", null, ["Parameter", "Source", "Mapped", "Rebuilt", "Delta", "Measure C", "Map C"].map((label) => h("th", { key: label }, label)))),
          h("tbody", null, reportRows.map((row) => h("tr", { key: row.feature_id },
            h("th", null, row.parameter_id),
            h("td", null, formatNumber(row.source_measurement)),
            h("td", null, formatNumber(row.mapped_v11_value)),
            h("td", null, formatNumber(row.reconstructed_value)),
            h("td", null, formatNumber(row.delta)),
            h("td", null, formatConfidence(row.measurement_confidence)),
            h("td", null, formatConfidence(row.mapping_confidence)),
          ))),
        )) : null,
        manifest?.parameter_mapping?.unsupported_source_features?.length ? h("section", { className: "unsupported-feature-list" },
          h("h4", null, "Unsupported source features"),
          manifest.parameter_mapping.unsupported_source_features.map((item) => h("p", { key: item.feature }, item.feature.replaceAll("_", " "))),
        ) : null,
      ),
    ),
  );
}

function ReportSummary({ manifest }) {
  const source = manifest.source || {};
  const comparison = manifest.comparison?.bidirectional || {};
  const alignment = manifest.comparison_alignment || {};
  return h("dl", { className: "step-report-summary" },
    h("dt", null, "Source topology"), h("dd", null, `${source.solid_count} solid / ${source.face_count} faces / ${source.edge_count} edges`),
    h("dt", null, "Blade population"), h("dd", null, `${manifest.semantics?.main_blade_count || 0} main + ${manifest.semantics?.splitter_blade_count || 0} splitter`),
    h("dt", null, "Geometry authority"), h("dd", null, manifest.canonical_geometry_version),
    h("dt", null, "Periodic phase alignment"), h("dd", null, `${formatNumber(alignment.rotation_about_axis_deg)} deg about confirmed axis`),
    h("dt", null, "Phase-search RMS"), h("dd", null, `${formatNumber(alignment.objective_rms_before_mm)} -> ${formatNumber(alignment.objective_rms_after_mm)} mm`),
    h("dt", null, "RMS deviation"), h("dd", null, `${formatNumber(comparison.rms_mm)} mm`),
    h("dt", null, "P95 deviation"), h("dd", null, `${formatNumber(comparison.p95_mm)} mm`),
  );
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(Math.abs(number) >= 100 ? 1 : 3) : "--";
}

function formatConfidence(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : "--";
}
