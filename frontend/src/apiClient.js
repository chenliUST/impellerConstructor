import { buildInstantiatePayload, buildSynthesizePayload, exportUrl } from "./appModel.js";

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
) {
  return requestJson(`${normalizeBase(apiBase)}/api/rule-engines/${encodeURIComponent(engineId)}/instantiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildInstantiatePayload(parameters, profileOverrides, curveOverrides, transitionOverrides, geometryStage)),
  });
}

export function modelExportUrl(apiBase, runId, format) {
  return exportUrl(apiBase, runId, format);
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};

  if (!response.ok) {
    const detail = payload.detail || response.statusText || "API request failed";
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail);
  }

  return payload;
}

function normalizeBase(apiBase) {
  return String(apiBase || "http://127.0.0.1:8000").replace(/\/+$/, "");
}
