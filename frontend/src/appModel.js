export const apiDefault = "http://127.0.0.1:8040";

export const parameterGroups = [
  { id: "main_dimensions", label: "Main dimensions" },
  { id: "meridional_support", label: "Meridional support" },
  { id: "shape_control", label: "Shape control" },
  { id: "blade_pattern", label: "Blade pattern" },
  { id: "blade_boundaries", label: "Blade boundaries" },
  { id: "blade_surface", label: "Blade surface" },
  { id: "blade_profile", label: "Blade profile" },
  { id: "edge_treatment", label: "Edge treatment" },
];

export const parameterSchema = {
  blade_count: { label: "Blade count", unit: "", step: 1, valueType: "integer", default: 7, group: "blade_pattern" },
  inlet_radius_mm: { label: "Inlet radius", unit: "mm", step: 1, default: 180, group: "main_dimensions" },
  exit_radius_mm: { label: "Exit radius", unit: "mm", step: 1, default: 620, group: "main_dimensions" },
  inlet_blade_height_mm: { label: "Inlet blade height", unit: "mm", step: 1, default: 150, group: "meridional_support" },
  outlet_blade_height_mm: { label: "Outlet blade height", unit: "mm", step: 1, default: 72, group: "meridional_support" },
  hub_curve_height_mm: { label: "Hub curve height", unit: "mm", step: 1, default: 82, group: "meridional_support" },
  mounting_bore_radius_mm: { label: "Mounting bore radius", unit: "mm", step: 1, default: 40, group: "main_dimensions" },
  hub_base_radius_mm: { label: "Hub base radius", unit: "mm", step: 1, default: 190, group: "shape_control", controlKind: "semantic_handle" },
  hub_nose_radius_mm: { label: "Hub nose radius", unit: "mm", step: 1, default: 72, group: "shape_control", controlKind: "semantic_handle" },
  hub_profile_convexity: { label: "Hub profile convexity", unit: "", step: 0.05, default: 0.35, group: "shape_control", controlKind: "semantic_handle" },
  blade_wrap_deg: { label: "Blade wrap", unit: "deg", step: 1, default: 118, group: "blade_surface" },
  blade_lean_deg: { label: "Blade lean", unit: "deg", step: 1, default: 8, group: "blade_surface" },
  leading_edge_lean_deg: { label: "Leading edge lean", unit: "deg", step: 1, default: 12, group: "blade_boundaries" },
  trailing_edge_lean_deg: { label: "Trailing edge lean", unit: "deg", step: 1, default: -8, group: "blade_boundaries" },
  leading_edge_sweep_mm: { label: "Leading edge sweep", unit: "mm", step: 1, default: 30, group: "blade_boundaries" },
  trailing_edge_sweep_mm: { label: "Trailing edge sweep", unit: "mm", step: 1, default: -45, group: "blade_boundaries" },
  blade_thickness_mm: { label: "Blade thickness", unit: "mm", step: 0.5, default: 18, group: "blade_profile" },
  root_fillet_radius_mm: { label: "Root fillet radius", unit: "mm", step: 0.5, default: 8, group: "edge_treatment" },
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
    presetId: "radial_open_reference",
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
      leading_edge_lean_deg: 12,
      trailing_edge_lean_deg: -8,
      leading_edge_sweep_mm: 30,
      trailing_edge_sweep_mm: -45,
      blade_thickness_mm: 18,
      root_fillet_radius_mm: 8,
    },
  },
  {
    id: "axisymmetric-nurbs-closed-throughflow",
    presetId: "radial_closed_reference",
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
      leading_edge_lean_deg: 8,
      trailing_edge_lean_deg: -6,
      leading_edge_sweep_mm: 24,
      trailing_edge_sweep_mm: -36,
      blade_thickness_mm: 16,
      root_fillet_radius_mm: 7,
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
