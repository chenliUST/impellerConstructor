export const apiDefault = "http://127.0.0.1:8040";

export const parameterSchema = {
  blade_count: { label: "Blade count", unit: "", step: 1, valueType: "integer", default: 7 },
  inlet_radius_mm: { label: "Inlet radius", unit: "mm", step: 1, default: 180 },
  exit_radius_mm: { label: "Exit radius", unit: "mm", step: 1, default: 620 },
  inlet_blade_height_mm: { label: "Inlet blade height", unit: "mm", step: 1, default: 150 },
  outlet_blade_height_mm: { label: "Outlet blade height", unit: "mm", step: 1, default: 72 },
  hub_curve_height_mm: { label: "Hub curve height", unit: "mm", step: 1, default: 82 },
  mounting_bore_radius_mm: { label: "Mounting bore radius", unit: "mm", step: 1, default: 40 },
  blade_wrap_deg: { label: "Blade wrap", unit: "deg", step: 1, default: 118 },
  blade_lean_deg: { label: "Blade lean", unit: "deg", step: 1, default: 8 },
  blade_thickness_mm: { label: "Blade thickness", unit: "mm", step: 0.5, default: 18 },
};

export const facetSchema = {
  flow_topology: { label: "Flow topology", values: ["axial", "mixed", "radial"] },
  shroud_topology: { label: "Shroud topology", values: ["open", "closed"] },
  suction_topology: { label: "Suction topology", values: ["single_suction"] },
  blade_exit_geometry: { label: "Blade exit geometry", values: ["backward_curved"] },
  passage_topology: { label: "Passage topology", values: ["throughflow_bladed_channel"] },
  working_domain: { label: "Working domain", values: ["pump"] },
};

export const presets = [
  {
    id: "axisymmetric-nurbs-open-throughflow",
    presetId: "axisymmetric_nurbs_open_throughflow_study",
    name: "NURBS open throughflow",
    summary: "Open impeller: revolved NURBS hub/tip profiles with conformal pressure and suction surfaces.",
    tags: ["open", "NURBS", "throughflow"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "radial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "pump",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 7,
      inlet_radius_mm: 180,
      exit_radius_mm: 620,
      inlet_blade_height_mm: 150,
      outlet_blade_height_mm: 72,
      hub_curve_height_mm: 82,
      mounting_bore_radius_mm: 40,
      blade_wrap_deg: 118,
      blade_lean_deg: 8,
      blade_thickness_mm: 18,
    },
  },
  {
    id: "axisymmetric-nurbs-closed-throughflow",
    presetId: "axisymmetric_nurbs_closed_throughflow_study",
    name: "NURBS closed throughflow",
    summary: "Closed impeller: revolved NURBS hub/shroud profiles with conformal pressure and suction surfaces.",
    tags: ["closed", "NURBS", "throughflow"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "radial",
      shroud_topology: "closed",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "pump",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 6,
      inlet_radius_mm: 190,
      exit_radius_mm: 600,
      inlet_blade_height_mm: 130,
      outlet_blade_height_mm: 68,
      hub_curve_height_mm: 74,
      mounting_bore_radius_mm: 42,
      blade_wrap_deg: 95,
      blade_lean_deg: -5,
      blade_thickness_mm: 16,
    },
  },
];

export function buildInstantiatePayload(inputParameters) {
  const parameters = {};

  for (const [name, spec] of Object.entries(parameterSchema)) {
    const rawValue = Number(inputParameters[name]);
    const fallback = presets[0].parameters[name] ?? spec.default;
    const numeric = Number.isFinite(rawValue) ? rawValue : fallback;
    parameters[name] = spec.valueType === "integer" ? Math.round(numeric) : roundForApi(numeric);
  }

  return { parameters };
}

export function buildSynthesizePayload(preset) {
  return {
    part_family_id: preset.partFamilyId,
    preset_id: preset.presetId,
    facets: { ...preset.facets },
  };
}

export function exportUrl(apiBase, runId, format) {
  const normalizedBase = String(apiBase || apiDefault).replace(/\/+$/, "");
  return `${normalizedBase}/api/model-runs/${encodeURIComponent(runId)}/exports/${encodeURIComponent(format)}`;
}

export function selectedPreset(id) {
  return presets.find((preset) => preset.id === id) || presets[0];
}

export function manifestSummary(manifest) {
  if (!manifest) {
    return {
      runId: "",
      status: "No run",
      sourceRefs: [],
      parameterCount: 0,
      operationCount: 0,
    };
  }

  return {
    runId: manifest.run_id,
    status: manifest.validation?.status || "Unknown",
    sourceRefs: manifest.source_refs || [],
    parameterCount: Object.keys(manifest.parameters || {}).length,
    operationCount: (manifest.operation_graph || []).length,
  };
}

function roundForApi(value) {
  return Math.round(value * 1000) / 1000;
}
