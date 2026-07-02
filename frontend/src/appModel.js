export const apiDefault = "http://127.0.0.1:8040";

export const parameterGroups = [
  { id: "main_dimensions", label: "Main dimensions" },
  { id: "meridional_support", label: "Meridional support" },
  { id: "shape_control", label: "Shape control" },
  { id: "blade_pattern", label: "Blade pattern" },
  { id: "blade_boundaries", label: "Blade boundaries" },
  { id: "blade_surface", label: "Blade surface" },
  { id: "blade_profile", label: "Blade profile" },
  { id: "solid_material", label: "Solid material" },
  { id: "edge_treatment", label: "Edge treatment" },
];

export const parameterSchema = {
  blade_count: { label: "Blade count", unit: "", step: 1, valueType: "integer", default: 12, group: "blade_pattern" },
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
  leading_edge_lean_deg: { label: "Leading edge lean", unit: "deg", step: 1, default: 0, group: "blade_boundaries" },
  trailing_edge_lean_deg: { label: "Trailing edge lean", unit: "deg", step: 1, default: 0, group: "blade_boundaries" },
  leading_edge_sweep_mm: { label: "Leading edge sweep", unit: "mm", step: 1, default: 0, group: "blade_boundaries" },
  trailing_edge_sweep_mm: { label: "Trailing edge sweep", unit: "mm", step: 1, default: 0, group: "blade_boundaries" },
  blade_thickness_mm: { label: "Blade thickness", unit: "mm", step: 0.5, default: 18, group: "blade_profile" },
  root_fillet_radius_mm: { label: "Root fillet radius", unit: "mm", step: 0.5, default: 8, group: "edge_treatment" },
  leading_edge_radius_mm: { label: "Leading edge radius", unit: "mm", step: 0.5, default: 3, group: "edge_treatment" },
  trailing_edge_radius_mm: { label: "Trailing edge radius", unit: "mm", step: 0.5, default: 2, group: "edge_treatment" },
  tip_edge_radius_mm: { label: "Tip edge radius", unit: "mm", step: 0.5, default: 2, group: "edge_treatment" },
  hub_wall_thickness_mm: { label: "Hub wall thickness", unit: "mm", step: 0.5, default: 18, group: "solid_material" },
  hub_bottom_thickness_mm: { label: "Hub bottom thickness", unit: "mm", step: 0.5, default: 24, group: "solid_material" },
  hub_top_cap_thickness_mm: { label: "Hub top cap thickness", unit: "mm", step: 0.5, default: 8, group: "solid_material" },
  hub_chamfer_radius_mm: { label: "Hub chamfer radius", unit: "mm", step: 0.5, default: 3, group: "edge_treatment" },
  hood_wall_thickness_mm: { label: "Hood wall thickness", unit: "mm", step: 0.5, default: 12, group: "solid_material" },
  hood_chamfer_radius_mm: { label: "Hood chamfer radius", unit: "mm", step: 0.5, default: 3, group: "edge_treatment" },
};

export const facetSchema = {
  flow_topology: { label: "Flow topology", values: ["axial", "mixed", "radial"] },
  shroud_topology: { label: "Shroud topology", values: ["open", "closed"] },
  suction_topology: { label: "Suction topology", values: ["single_suction"] },
  blade_exit_geometry: { label: "Blade exit geometry", values: ["backward_curved"] },
  passage_topology: { label: "Passage topology", values: ["throughflow_bladed_channel"] },
  working_domain: { label: "Working domain", values: ["pump"] },
};

export const exportFileOptions = [
  { id: "step", label: "STEP B-Rep", extension: ".step" },
  { id: "stl", label: "STL Mesh", extension: ".stl" },
  { id: "mesh_step", label: "STEP Mesh", extension: ".mesh.step" },
  { id: "manifest", label: "Manifest", extension: ".manifest.json" },
];

export const presets = [
  {
    id: "axisymmetric-nurbs-open-throughflow",
    presetId: "radial_open_reference_v0_6",
    name: "B-Rep open throughflow v0.6",
    summary: "Open impeller: B-Rep edge treatment, mesh inspection, CFD full-360 manifest, and STEP/STL exports.",
    tags: ["open", "B-Rep", "v0.6", "mesh inspection", "export"],
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
      blade_count: 12,
      inlet_radius_mm: 180,
      exit_radius_mm: 620,
      inlet_blade_height_mm: 150,
      outlet_blade_height_mm: 72,
      hub_curve_height_mm: 82,
      mounting_bore_radius_mm: 40,
      blade_wrap_deg: 118,
      blade_lean_deg: 8,
      leading_edge_lean_deg: 0,
      trailing_edge_lean_deg: 0,
      leading_edge_sweep_mm: 0,
      trailing_edge_sweep_mm: 0,
      blade_thickness_mm: 18,
      root_fillet_radius_mm: 8,
      leading_edge_radius_mm: 3,
      trailing_edge_radius_mm: 2,
      tip_edge_radius_mm: 2,
      hub_wall_thickness_mm: 18,
      hub_bottom_thickness_mm: 24,
      hub_top_cap_thickness_mm: 8,
      hub_chamfer_radius_mm: 3,
      hood_wall_thickness_mm: 12,
      hood_chamfer_radius_mm: 3,
    },
  },
  {
    id: "axisymmetric-nurbs-closed-throughflow",
    presetId: "radial_closed_reference_v0_6",
    name: "B-Rep closed throughflow v0.6",
    summary: "Closed impeller: B-Rep edge treatment, mesh inspection, CFD full-360 manifest, and STEP/STL exports.",
    tags: ["closed", "B-Rep", "v0.6", "mesh inspection", "export"],
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
      blade_count: 12,
      inlet_radius_mm: 190,
      exit_radius_mm: 600,
      inlet_blade_height_mm: 130,
      outlet_blade_height_mm: 68,
      hub_curve_height_mm: 74,
      mounting_bore_radius_mm: 42,
      blade_wrap_deg: 95,
      blade_lean_deg: -5,
      leading_edge_lean_deg: 0,
      trailing_edge_lean_deg: 0,
      leading_edge_sweep_mm: 0,
      trailing_edge_sweep_mm: 0,
      blade_thickness_mm: 16,
      root_fillet_radius_mm: 8,
      leading_edge_radius_mm: 3,
      trailing_edge_radius_mm: 2,
      tip_edge_radius_mm: 2,
      hub_wall_thickness_mm: 18,
      hub_bottom_thickness_mm: 22,
      hub_top_cap_thickness_mm: 8,
      hub_chamfer_radius_mm: 3,
      hood_wall_thickness_mm: 12,
      hood_chamfer_radius_mm: 3,
    },
  },
];

export function buildInstantiatePayload(
  inputParameters,
  profileOverrides = null,
  curveOverrides = null,
  transitionOverrides = null,
  geometryStage = "edge_closures",
) {
  const parameters = {};

  for (const [name, spec] of Object.entries(parameterSchema)) {
    const rawValue = Number(inputParameters[name]);
    const fallback = presets[0].parameters[name] ?? spec.default;
    const numeric = Number.isFinite(rawValue) ? rawValue : fallback;
    parameters[name] = spec.valueType === "integer" ? Math.round(numeric) : roundForApi(numeric);
  }

  const payload = { parameters, geometry_stage: geometryStage };
  if (profileOverrides) {
    payload.profile_overrides = profileOverrides;
  }
  if (curveOverrides) {
    payload.curve_overrides = curveOverrides;
  }
  if (transitionOverrides) {
    payload.transition_overrides = transitionOverrides;
  }
  return payload;
}

export function buildSynthesizePayload(preset) {
  return {
    part_family_id: preset.partFamilyId,
    preset_id: preset.presetId,
    facets: { ...preset.facets },
  };
}

export function overridesAfterParameterChange(name, profileOverrides, curveOverrides) {
  return {
    profileOverrides: profileDriverParameters.has(name) ? null : profileOverrides,
    curveOverrides: curveDriverParameters.has(name) ? null : curveOverrides,
  };
}

export function exportUrl(apiBase, runId, format) {
  const normalizedBase = String(apiBase || apiDefault).replace(/\/+$/, "");
  return `${normalizedBase}/api/model-runs/${encodeURIComponent(runId)}/exports/${encodeURIComponent(format)}`;
}

export function exportFilename(presetId, runId, exportKind) {
  const option = exportFileOptions.find((item) => item.id === exportKind) || exportFileOptions[0];
  const safePreset = String(presetId || "impeller").replace(/[^A-Za-z0-9_-]/g, "_");
  const safeRun = String(runId || "run").replace(/[^A-Za-z0-9_-]/g, "_");
  return `${safePreset}_${safeRun}${option.extension}`;
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

const profileDriverParameters = new Set([
  "inlet_radius_mm",
  "exit_radius_mm",
  "inlet_blade_height_mm",
  "outlet_blade_height_mm",
  "hub_curve_height_mm",
  "mounting_bore_radius_mm",
  "hub_base_radius_mm",
  "hub_nose_radius_mm",
  "hub_profile_convexity",
]);

const curveDriverParameters = new Set([
  "inlet_radius_mm",
  "exit_radius_mm",
  "blade_wrap_deg",
  "blade_lean_deg",
  "leading_edge_lean_deg",
  "trailing_edge_lean_deg",
  "leading_edge_sweep_mm",
  "trailing_edge_sweep_mm",
  "blade_thickness_mm",
]);
