import {
  buildInstantiatePayload,
  buildPresetInstantiatePayload,
  buildSynthesizePayload,
  exportUrl,
} from "./appModel.js?v=1.1.9";

export async function synthesizeImpeller(apiBase, preset) {
  return requestJson(`${normalizeBase(apiBase)}/api/rule-engines/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildSynthesizePayload(preset)),
  });
}

export async function instantiateImpeller(
  apiBase,
  engineId,
  parameters,
  profileOverrides = null,
  curveOverrides = null,
  geometryStage = "edge_closures",
  transitionOverrides = null,
  sectionLoopOverrides = null,
  bladeToBladeLoopFamilyOverrides = null,
) {
  return requestJson(`${normalizeBase(apiBase)}/api/rule-engines/${encodeURIComponent(engineId)}/instantiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      buildInstantiatePayload(
        parameters,
        profileOverrides,
        curveOverrides,
        transitionOverrides,
        geometryStage,
        sectionLoopOverrides,
        bladeToBladeLoopFamilyOverrides,
      ),
    ),
  });
}

export async function instantiatePresetImpeller(
  apiBase,
  engineId,
  geometryStage = "edge_closures",
  responseMode = "full",
) {
  const payload = buildPresetInstantiatePayload(geometryStage);
  if (responseMode !== "full") payload.response_mode = responseMode;
  return requestJson(`${normalizeBase(apiBase)}/api/rule-engines/${encodeURIComponent(engineId)}/instantiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function engineeringDrawing(apiBase, runId) {
  return requestJson(
    `${normalizeBase(apiBase)}/api/model-runs/${encodeURIComponent(runId)}/engineering-drawing`,
    { method: "GET" },
  );
}

export async function engineeringDrawingView(apiBase, runId, viewId) {
  return requestJson(
    `${normalizeBase(apiBase)}/api/model-runs/${encodeURIComponent(runId)}/engineering-drawing/views/${encodeURIComponent(viewId)}`,
    { method: "GET" },
  );
}

export async function engineeringDrawingConstructionTables(apiBase, runId) {
  return requestJson(
    `${normalizeBase(apiBase)}/api/model-runs/${encodeURIComponent(runId)}/engineering-drawing/construction-tables`,
    { method: "GET" },
  );
}

export function modelExportUrl(apiBase, runId, format) {
  return exportUrl(apiBase, runId, format);
}

export async function createStepReconstructionAudit(apiBase, file) {
  if (!file) throw new Error("Select a STEP file before starting reconstruction.");
  return requestJson(
    `${normalizeBase(apiBase)}/api/step-reconstruction-audits?filename=${encodeURIComponent(file.name || "source.step")}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/step" },
      body: file,
    },
  );
}

export async function stepReconstructionAuditStatus(apiBase, auditId, options = {}) {
  return requestJson(
    `${normalizeBase(apiBase)}/api/step-reconstruction-audits/${encodeURIComponent(auditId)}`,
    { method: "GET", signal: options.signal },
  );
}

export async function stepReconstructionAuditManifest(apiBase, auditId, options = {}) {
  return requestJson(
    `${normalizeBase(apiBase)}/api/step-reconstruction-audits/${encodeURIComponent(auditId)}/manifest`,
    { method: "GET", signal: options.signal },
  );
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text.slice(0, 1000) };
    }
  }

  if (!response.ok) {
    const detail = payload.detail || response.statusText || "API request failed";
    const message = Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : String(detail);
    const error = new Error(`${response.status} ${message}`);
    error.status = response.status;
    throw error;
  }

  return payload;
}

function normalizeBase(apiBase) {
  return String(apiBase || "http://127.0.0.1:8000").replace(/\/+$/, "");
}
