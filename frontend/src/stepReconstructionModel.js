export const stepAuditStages = [
  "uploaded",
  "brep_loaded",
  "frame_resolved",
  "semantics_classified",
  "parameters_extracted",
  "hub_reconstructed",
  "blade_surfaces_reconstructed",
  "edge_closures_reconstructed",
  "deviation_measured",
  "complete",
];

export function auditStageRows(status) {
  const completed = new Set(status?.completed_stages || []);
  const failedStage = status?.status === "FAILED" ? status.current_stage : null;
  return stepAuditStages.map((stage) => ({
    id: stage,
    label: stage.replaceAll("_", " "),
    state: failedStage === stage ? "failed" : completed.has(stage) ? "complete" : status?.current_stage === stage ? "active" : "pending",
  }));
}

export function auditArtifactUrls(apiBase, auditId) {
  if (!auditId) return {};
  const root = `${String(apiBase || "").replace(/\/+$/, "")}/api/step-reconstruction-audits/${encodeURIComponent(auditId)}/artifacts`;
  return {
    source: `${root}/source.stl`,
    reconstruction: `${root}/reconstruction.stl`,
    heatmap: `${root}/heatmap.json`,
  };
}

export function comparisonViewportRects(width, height) {
  const w = Math.max(0, Math.floor(Number(width) || 0));
  const h = Math.max(0, Math.floor(Number(height) || 0));
  const left = Math.floor(w / 2);
  const right = w - left;
  const bottom = Math.floor(h / 2);
  const top = h - bottom;
  return {
    source: { x: 0, y: bottom, width: left, height: top },
    reconstruction: { x: left, y: bottom, width: right, height: top },
    heatmap: { x: 0, y: 0, width: left, height: bottom },
  };
}

export function heatmapLegend(manifest) {
  const legend = manifest?.comparison?.bidirectional || {};
  return [
    { label: "Min", value: legend.minimum_mm },
    { label: "Median", value: legend.median_mm },
    { label: "P95", value: legend.p95_mm },
    { label: "Max", value: legend.maximum_mm },
  ].filter((row) => Number.isFinite(Number(row.value)));
}

export function parameterDifferenceRows(manifest) {
  const reconstructed = manifest?.reconstruction?.parameters || {};
  return (manifest?.parameter_mapping?.parameter_rows || []).map((row) => {
    const parameterId = String(row.feature_id || "").replace(/^parameter_values\./, "");
    const reconstructedValue = reconstructed[parameterId];
    const sourceValue = row.source_measurement;
    return {
      ...row,
      parameter_id: parameterId,
      reconstructed_value: reconstructedValue,
      delta: Number.isFinite(Number(sourceValue)) && Number.isFinite(Number(reconstructedValue))
        ? Number(reconstructedValue) - Number(sourceValue)
        : null,
    };
  });
}

export function terminalAuditStatus(status) {
  return status?.status === "PASS" || status?.status === "FAILED";
}

export function auditInProgress(status) {
  return status?.status === "UPLOADING" || status?.status === "QUEUED" || status?.status === "RUNNING";
}
