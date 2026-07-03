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
  working_domain: { label: "Working domain", values: ["pump", "compressor", "fan_or_blower"] },
};

export const exportFileOptions = [
  { id: "step", label: "STEP B-Rep", extension: ".step" },
  { id: "stl", label: "STL Mesh", extension: ".stl" },
  { id: "mesh_step", label: "STEP Mesh", extension: ".mesh.step" },
  { id: "obj", label: "OBJ Mesh", extension: ".obj" },
  { id: "manifest", label: "Manifest", extension: ".manifest.json" },
];

function profile(controlPoints) {
  const degree = Math.min(3, controlPoints.length - 1);
  return {
    kind: "nurbs_curve",
    degree,
    coordinate_system: "rz_meridional_mm",
    control_points: controlPoints,
    weights: Array(controlPoints.length).fill(1),
    knots: clampedUniformKnots(controlPoints.length, degree),
  };
}

function axialProfileOverrides(hubControlPoints, tipControlPoints) {
  return {
    hub_profile: profile(hubControlPoints),
    tip_or_shroud_profile: profile(tipControlPoints),
  };
}

function axialCurveOverrides(thetaPoints, leanPoints, leadingSweepPoints, trailingSweepPoints, thicknessPoints) {
  return {
    blade_mean: {
      theta_center_u_curve: { coordinate_system: "u_theta_deg", control_points: smoothCurve(thetaPoints) },
      span_lean_u_curve: { coordinate_system: "u_lean_deg", control_points: smoothCurve(leanPoints) },
    },
    blade_edges: {
      leading_edge_sweep_v_curve: { coordinate_system: "v_support_u_offset", control_points: smoothCurve(leadingSweepPoints) },
      trailing_edge_sweep_v_curve: { coordinate_system: "v_support_u_offset", control_points: smoothCurve(trailingSweepPoints) },
    },
    thickness: {
      thickness_u_curve: { coordinate_system: "u_thickness_mm", control_points: smoothCurve(thicknessPoints) },
    },
  };
}

function clampedUniformKnots(controlPointCount, degree) {
  const interiorCount = controlPointCount - degree - 1;
  const knots = Array(degree + 1).fill(0);
  for (let index = 1; index <= interiorCount; index += 1) {
    knots.push(roundForApi(index / (interiorCount + 1)));
  }
  knots.push(...Array(degree + 1).fill(1));
  return knots;
}

function boundedSweepCurve(sweepMm, inletRadiusMm, exitRadiusMm, controlPoints) {
  const radialSpan = Math.max(1, Math.abs(Number(exitRadiusMm) - Number(inletRadiusMm)));
  const scalarOffset = Math.abs(Number(sweepMm)) / (2 * radialSpan);
  const offsetLimit = scalarOffset === 0 ? 0 : Math.min(0.12, scalarOffset * 1.6);
  const currentMax = Math.max(...controlPoints.map((point) => Math.abs(point[1])));
  const scale = currentMax > 0 ? Math.min(1, offsetLimit / currentMax) : 1;
  return controlPoints.map(([t, value]) => [t, roundForApi(value * scale)]);
}

function smoothCurve(controlPoints) {
  const sorted = controlPoints.map(([t, value]) => [Number(t), Number(value)]).sort((left, right) => left[0] - right[0]);
  if (sorted.length < 3) {
    return sorted.map(([t, value]) => [roundForApi(t), roundForApi(value)]);
  }
  const slopes = pchipSlopes(sorted);
  const sampleT = [sorted[0][0]];
  for (let index = 0; index < sorted.length - 1; index += 1) {
    const leftT = sorted[index][0];
    const rightT = sorted[index + 1][0];
    sampleT.push(roundForApi(leftT + (rightT - leftT) * 0.5), rightT);
  }
  return sampleT.map((t) => [roundForApi(t), roundForApi(evaluateHermite(sorted, slopes, t))]);
}

function pchipSlopes(points) {
  const deltas = [];
  for (let index = 0; index < points.length - 1; index += 1) {
    const span = points[index + 1][0] - points[index][0];
    deltas.push((points[index + 1][1] - points[index][1]) / Math.max(span, 1e-9));
  }
  const slopes = Array(points.length).fill(0);
  slopes[0] = deltas[0];
  slopes[slopes.length - 1] = deltas[deltas.length - 1];
  for (let index = 1; index < points.length - 1; index += 1) {
    const left = deltas[index - 1];
    const right = deltas[index];
    slopes[index] = left * right <= 0 ? 0 : (2 * left * right) / (left + right);
  }
  return slopes;
}

function evaluateHermite(points, slopes, t) {
  for (let index = 0; index < points.length - 1; index += 1) {
    const left = points[index];
    const right = points[index + 1];
    if (t <= right[0]) {
      const span = Math.max(right[0] - left[0], 1e-9);
      const s = (t - left[0]) / span;
      const h00 = 2 * s ** 3 - 3 * s ** 2 + 1;
      const h10 = s ** 3 - 2 * s ** 2 + s;
      const h01 = -2 * s ** 3 + 3 * s ** 2;
      const h11 = s ** 3 - s ** 2;
      return h00 * left[1] + h10 * span * slopes[index] + h01 * right[1] + h11 * span * slopes[index + 1];
    }
  }
  return points.at(-1)[1];
}

export const presets = [
  {
    id: "axisymmetric-nurbs-open-throughflow",
    presetId: "radial_open_reference_v0_7",
    name: "B-Rep open throughflow v0.7",
    summary: "Open impeller: bounded transition topology, mesh inspection, CFD full-360 manifest, and STEP/STL exports.",
    tags: ["open", "B-Rep", "v0.7", "mesh inspection", "export"],
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
    presetId: "radial_closed_reference_v0_7",
    name: "B-Rep closed throughflow v0.7",
    summary: "Closed impeller: bounded transition topology, mesh inspection, CFD full-360 manifest, and STEP/STL exports.",
    tags: ["closed", "B-Rep", "v0.7", "mesh inspection", "export"],
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
  {
    id: "public-nasa-rotor67-axial-blisk",
    presetId: "radial_open_reference_v0_7",
    name: "Public NASA Rotor 67 axial blisk",
    summary: "Axial blisk approximation using public NASA Rotor 67 annulus and blade-count data.",
    tags: ["public-data", "axial", "blisk", "rotor", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "fan_or_blower",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 22,
      inlet_radius_mm: 95.9,
      exit_radius_mm: 255.7,
      inlet_blade_height_mm: 159.8,
      outlet_blade_height_mm: 126.6,
      hub_curve_height_mm: 92,
      mounting_bore_radius_mm: 36,
      blade_wrap_deg: 74,
      blade_lean_deg: 18,
      leading_edge_lean_deg: 8,
      trailing_edge_lean_deg: -10,
      leading_edge_sweep_mm: 8,
      trailing_edge_sweep_mm: -10,
      blade_thickness_mm: 4.8,
      root_fillet_radius_mm: 1.8,
      leading_edge_radius_mm: 0.8,
      trailing_edge_radius_mm: 0.45,
      tip_edge_radius_mm: 0.45,
      hub_wall_thickness_mm: 7,
      hub_bottom_thickness_mm: 10,
      hub_top_cap_thickness_mm: 4,
      hub_chamfer_radius_mm: 1,
      hood_wall_thickness_mm: 4,
      hood_chamfer_radius_mm: 1,
    },
    profileOverrides: axialProfileOverrides(
      [[95.9, 92], [99, 72], [105, 48], [110, 25], [114, 10], [115.9, 0]],
      [[255.7, 93], [253.2, 73], [249.8, 49], [246.4, 26], [244.1, 11], [242.5, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.2, -7], [0.55, -38], [0.82, -61], [1, -74]],
      [[0, 8], [0.35, 24], [0.7, 12], [1, -10]],
      boundedSweepCurve(8, 95.9, 255.7, [[0, -0.05], [0.5, 0], [1, 0.07]]),
      boundedSweepCurve(-10, 95.9, 255.7, [[0, 0.06], [0.5, 0], [1, -0.08]]),
      [[0, 4.8], [0.45, 3.9], [1, 2.4]],
    ),
  },
  {
    id: "public-nasa-rotor37-compressor-blisk",
    presetId: "radial_open_reference_v0_7",
    name: "Public NASA Rotor 37 compressor blisk",
    summary: "High-load axial compressor blisk approximation using public NASA Rotor 37 stage data.",
    tags: ["public-data", "axial", "blisk", "compressor", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "compressor",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 36,
      inlet_radius_mm: 176.4,
      exit_radius_mm: 253.7,
      inlet_blade_height_mm: 77.3,
      outlet_blade_height_mm: 75.6,
      hub_curve_height_mm: 64,
      mounting_bore_radius_mm: 70,
      blade_wrap_deg: 56,
      blade_lean_deg: 10,
      leading_edge_lean_deg: 5,
      trailing_edge_lean_deg: -8,
      leading_edge_sweep_mm: 4,
      trailing_edge_sweep_mm: -6,
      blade_thickness_mm: 2.8,
      root_fillet_radius_mm: 1.1,
      leading_edge_radius_mm: 0.45,
      trailing_edge_radius_mm: 0.3,
      tip_edge_radius_mm: 0.3,
      hub_wall_thickness_mm: 5,
      hub_bottom_thickness_mm: 7,
      hub_top_cap_thickness_mm: 3,
      hub_chamfer_radius_mm: 1,
      hood_wall_thickness_mm: 3,
      hood_chamfer_radius_mm: 1,
    },
    profileOverrides: axialProfileOverrides(
      [[176.4, 64], [176.8, 51], [177.4, 38], [178, 24], [178.5, 12], [179, 0]],
      [[253.7, 65], [253.4, 52], [253, 39], [252.6, 25], [252.3, 13], [252, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.2, -6], [0.55, -29], [0.82, -48], [1, -56]],
      [[0, 5], [0.45, 16], [1, -8]],
      boundedSweepCurve(4, 176.4, 253.7, [[0, -0.035], [0.5, 0], [1, 0.055]]),
      boundedSweepCurve(-6, 176.4, 253.7, [[0, 0.045], [0.5, 0], [1, -0.06]]),
      [[0, 2.8], [0.5, 2.2], [1, 1.4]],
    ),
  },
  {
    id: "public-nasa-stage37-stator-ring",
    presetId: "radial_closed_reference_v0_7",
    name: "Public NASA Stage 37 stator ring",
    summary: "Axial compressor stator ring approximation using public NASA Stage 37 vane-count and annulus data.",
    tags: ["public-data", "axial", "stator", "ring", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "closed",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "compressor",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 46,
      inlet_radius_mm: 176.4,
      exit_radius_mm: 253.7,
      inlet_blade_height_mm: 77.3,
      outlet_blade_height_mm: 75.6,
      hub_curve_height_mm: 60,
      mounting_bore_radius_mm: 82,
      blade_wrap_deg: 24,
      blade_lean_deg: 2,
      leading_edge_lean_deg: -4,
      trailing_edge_lean_deg: 5,
      leading_edge_sweep_mm: 2,
      trailing_edge_sweep_mm: -3,
      blade_thickness_mm: 2.3,
      root_fillet_radius_mm: 0.9,
      leading_edge_radius_mm: 0.35,
      trailing_edge_radius_mm: 0.25,
      tip_edge_radius_mm: 0.25,
      hub_wall_thickness_mm: 4.5,
      hub_bottom_thickness_mm: 6,
      hub_top_cap_thickness_mm: 3,
      hub_chamfer_radius_mm: 0.8,
      hood_wall_thickness_mm: 3,
      hood_chamfer_radius_mm: 0.8,
    },
    profileOverrides: axialProfileOverrides(
      [[176.4, 60], [176.8, 48], [177.3, 36], [177.8, 23], [178.2, 11], [178.6, 0]],
      [[253.7, 61], [253.4, 49], [253, 37], [252.6, 24], [252.3, 12], [252, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.25, 4], [0.6, 15], [1, 24]],
      [[0, -6], [0.5, 2], [1, 5]],
      boundedSweepCurve(2, 176.4, 253.7, [[0, -0.02], [0.5, 0], [1, 0.03]]),
      boundedSweepCurve(-3, 176.4, 253.7, [[0, 0.04], [0.5, 0], [1, -0.04]]),
      [[0, 2.3], [0.4, 2], [1, 1.2]],
    ),
  },
  {
    id: "public-nasa-sdt-r4-turbofan-fan",
    presetId: "radial_open_reference_v0_7",
    name: "Public NASA SDT R4 turbofan fan",
    summary: "First-stage turbofan fan approximation from the public NASA 22-inch Source Diagnostic Test fan.",
    tags: ["public-data", "axial", "fan", "turbofan", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "fan_or_blower",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 22,
      inlet_radius_mm: 81,
      exit_radius_mm: 279.4,
      inlet_blade_height_mm: 198.4,
      outlet_blade_height_mm: 190,
      hub_curve_height_mm: 140,
      mounting_bore_radius_mm: 33,
      blade_wrap_deg: 86,
      blade_lean_deg: 24,
      leading_edge_lean_deg: 14,
      trailing_edge_lean_deg: -12,
      leading_edge_sweep_mm: 18,
      trailing_edge_sweep_mm: -22,
      blade_thickness_mm: 8,
      root_fillet_radius_mm: 2.4,
      leading_edge_radius_mm: 1.2,
      trailing_edge_radius_mm: 0.8,
      tip_edge_radius_mm: 0.8,
      hub_wall_thickness_mm: 10,
      hub_bottom_thickness_mm: 14,
      hub_top_cap_thickness_mm: 5,
      hub_chamfer_radius_mm: 1.5,
      hood_wall_thickness_mm: 4,
      hood_chamfer_radius_mm: 1,
    },
    profileOverrides: axialProfileOverrides(
      [[81, 140], [82.2, 112], [84, 84], [85.5, 54], [86.4, 24], [87, 0]],
      [[279.4, 141], [279.2, 113], [278.9, 85], [278.6, 55], [278.3, 25], [278, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.15, -8], [0.45, -42], [0.75, -72], [1, -86]],
      [[0, 14], [0.35, 30], [0.7, 20], [1, -12]],
      boundedSweepCurve(18, 81, 279.4, [[0, -0.08], [0.5, 0], [1, 0.11]]),
      boundedSweepCurve(-22, 81, 279.4, [[0, 0.1], [0.5, 0], [1, -0.12]]),
      [[0, 8], [0.35, 7.2], [0.7, 5.2], [1, 3.5]],
    ),
  },
  {
    id: "public-rr-ultrafan-cti-fan",
    presetId: "radial_open_reference_v0_7",
    name: "Public RR UltraFan CTi fan",
    summary: "UltraFan front-fan approximation anchored on the public 140-inch fan system and CTi fan-blade demonstrator data.",
    tags: ["public-data", "axial", "fan", "ultrafan", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "fan_or_blower",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 18,
      inlet_radius_mm: 533,
      exit_radius_mm: 1778,
      inlet_blade_height_mm: 1245,
      outlet_blade_height_mm: 1170,
      hub_curve_height_mm: 850,
      mounting_bore_radius_mm: 90,
      blade_wrap_deg: 92,
      blade_lean_deg: 28,
      leading_edge_lean_deg: 16,
      trailing_edge_lean_deg: -14,
      leading_edge_sweep_mm: 90,
      trailing_edge_sweep_mm: -120,
      blade_thickness_mm: 45,
      root_fillet_radius_mm: 14,
      leading_edge_radius_mm: 7,
      trailing_edge_radius_mm: 4,
      tip_edge_radius_mm: 4,
      hub_wall_thickness_mm: 55,
      hub_bottom_thickness_mm: 75,
      hub_top_cap_thickness_mm: 24,
      hub_chamfer_radius_mm: 8,
      hood_wall_thickness_mm: 12,
      hood_chamfer_radius_mm: 3,
    },
    profileOverrides: axialProfileOverrides(
      [[140, 850], [255, 790], [430, 650], [530, 430], [575, 170], [600, 0]],
      [[1778, 851], [1776, 791], [1773, 651], [1770, 431], [1765, 171], [1760, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.15, -10], [0.45, -45], [0.75, -78], [1, -92]],
      [[0, 16], [0.35, 34], [0.7, 25], [1, -14]],
      boundedSweepCurve(90, 533, 1778, [[0, -0.09], [0.5, 0], [1, 0.12]]),
      boundedSweepCurve(-120, 533, 1778, [[0, 0.11], [0.5, 0], [1, -0.14]]),
      [[0, 45], [0.35, 37], [0.7, 24], [1, 16]],
    ),
  },
  {
    id: "public-rr-ultrafan-ogv-ring",
    presetId: "radial_closed_reference_v0_7",
    name: "Public RR UltraFan OGV ring",
    summary: "UltraFan-scale outlet-guide-vane ring approximation using the public 140-inch fan annulus as the outer-radius anchor.",
    tags: ["public-data", "axial", "stator", "ultrafan", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "closed",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "fan_or_blower",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 44,
      inlet_radius_mm: 600,
      exit_radius_mm: 1778,
      inlet_blade_height_mm: 1178,
      outlet_blade_height_mm: 1148,
      hub_curve_height_mm: 520,
      mounting_bore_radius_mm: 260,
      blade_wrap_deg: 32,
      blade_lean_deg: 3,
      leading_edge_lean_deg: -8,
      trailing_edge_lean_deg: 8,
      leading_edge_sweep_mm: 25,
      trailing_edge_sweep_mm: -35,
      blade_thickness_mm: 28,
      root_fillet_radius_mm: 9,
      leading_edge_radius_mm: 4,
      trailing_edge_radius_mm: 2.5,
      tip_edge_radius_mm: 2.5,
      hub_wall_thickness_mm: 40,
      hub_bottom_thickness_mm: 55,
      hub_top_cap_thickness_mm: 18,
      hub_chamfer_radius_mm: 6,
      hood_wall_thickness_mm: 18,
      hood_chamfer_radius_mm: 5,
    },
    profileOverrides: axialProfileOverrides(
      [[600, 520], [603, 416], [608, 312], [612, 205], [616, 90], [620, 0]],
      [[1778, 521], [1776, 417], [1774, 313], [1772, 206], [1770, 91], [1768, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.25, 5], [0.6, 19], [1, 32]],
      [[0, -8], [0.45, 3], [1, 8]],
      boundedSweepCurve(25, 600, 1778, [[0, -0.025], [0.5, 0], [1, 0.035]]),
      boundedSweepCurve(-35, 600, 1778, [[0, 0.04], [0.5, 0], [1, -0.045]]),
      [[0, 28], [0.45, 24], [1, 15]],
    ),
  },
  {
    id: "public-liquid-rocket-turbopump-inducer",
    presetId: "radial_open_reference_v0_7",
    name: "Public liquid rocket turbopump inducer",
    summary: "Axial screw-inducer approximation based on public liquid-rocket turbopump inducer references.",
    tags: ["public-data", "axial", "inducer", "pump", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "pump",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 3,
      inlet_radius_mm: 35,
      exit_radius_mm: 72.5,
      inlet_blade_height_mm: 35,
      outlet_blade_height_mm: 32.5,
      hub_curve_height_mm: 120,
      mounting_bore_radius_mm: 4,
      blade_wrap_deg: 230,
      blade_lean_deg: 10,
      leading_edge_lean_deg: 4,
      trailing_edge_lean_deg: 14,
      leading_edge_sweep_mm: 10,
      trailing_edge_sweep_mm: -8,
      blade_thickness_mm: 2.5,
      root_fillet_radius_mm: 0.8,
      leading_edge_radius_mm: 0.35,
      trailing_edge_radius_mm: 0.25,
      tip_edge_radius_mm: 0.25,
      hub_wall_thickness_mm: 4,
      hub_bottom_thickness_mm: 6,
      hub_top_cap_thickness_mm: 2,
      hub_chamfer_radius_mm: 0.6,
      hood_wall_thickness_mm: 2,
      hood_chamfer_radius_mm: 0.5,
    },
    profileOverrides: axialProfileOverrides(
      [[10, 120], [15, 110], [25, 92], [34, 62], [39, 26], [42, 0]],
      [[70, 121], [70.5, 111], [71, 93], [71.5, 63], [72, 27], [72.5, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.25, -55], [0.6, -150], [1, -230]],
      [[0, 4], [0.5, 9], [1, 14]],
      boundedSweepCurve(10, 35, 72.5, [[0, -0.12], [0.5, 0], [1, 0.16]]),
      boundedSweepCurve(-8, 35, 72.5, [[0, 0.1], [0.5, 0], [1, -0.14]]),
      [[0, 2.5], [0.45, 2.1], [1, 1.2]],
    ),
  },
  {
    id: "public-nasa-sr7l-propfan",
    presetId: "radial_open_reference_v0_7",
    name: "Public NASA SR-7L propfan",
    summary: "Eight-blade advanced propeller/propfan approximation using public NASA SR-7L geometry references.",
    tags: ["public-data", "axial", "propeller", "propfan", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "fan_or_blower",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 8,
      inlet_radius_mm: 220,
      exit_radius_mm: 1370,
      inlet_blade_height_mm: 1150,
      outlet_blade_height_mm: 1110,
      hub_curve_height_mm: 500,
      mounting_bore_radius_mm: 95,
      blade_wrap_deg: 130,
      blade_lean_deg: 36,
      leading_edge_lean_deg: 20,
      trailing_edge_lean_deg: -8,
      leading_edge_sweep_mm: 120,
      trailing_edge_sweep_mm: -160,
      blade_thickness_mm: 20,
      root_fillet_radius_mm: 6,
      leading_edge_radius_mm: 3,
      trailing_edge_radius_mm: 1.5,
      tip_edge_radius_mm: 1.5,
      hub_wall_thickness_mm: 24,
      hub_bottom_thickness_mm: 35,
      hub_top_cap_thickness_mm: 10,
      hub_chamfer_radius_mm: 4,
      hood_wall_thickness_mm: 8,
      hood_chamfer_radius_mm: 2,
    },
    profileOverrides: axialProfileOverrides(
      [[220, 500], [225, 400], [235, 300], [245, 190], [255, 80], [260, 0]],
      [[1370, 501], [1369, 401], [1368, 301], [1367, 191], [1366, 81], [1365, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.2, -15], [0.55, -70], [0.85, -115], [1, -130]],
      [[0, 20], [0.4, 42], [0.75, 30], [1, -8]],
      boundedSweepCurve(120, 220, 1370, [[0, -0.18], [0.5, 0], [1, 0.22]]),
      boundedSweepCurve(-160, 220, 1370, [[0, 0.16], [0.5, 0], [1, -0.22]]),
      [[0, 20], [0.35, 16], [0.7, 10], [1, 6]],
    ),
  },
  {
    id: "reference-spur-gear-tooth-ring",
    presetId: "radial_open_reference_v0_7",
    name: "Reference spur gear tooth ring",
    summary: "Mechanical analogy preset: a straight-tooth gear-like ring generated with the same radial blade pattern rules.",
    tags: ["mechanical-analogy", "gear", "radial", "v0.7"],
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
      blade_count: 24,
      inlet_radius_mm: 36,
      exit_radius_mm: 48,
      inlet_blade_height_mm: 14,
      outlet_blade_height_mm: 14,
      hub_curve_height_mm: 18,
      mounting_bore_radius_mm: 12,
      blade_wrap_deg: 4,
      blade_lean_deg: 0,
      leading_edge_lean_deg: 0,
      trailing_edge_lean_deg: 0,
      leading_edge_sweep_mm: 0,
      trailing_edge_sweep_mm: 0,
      blade_thickness_mm: 4,
      root_fillet_radius_mm: 0.8,
      leading_edge_radius_mm: 0.5,
      trailing_edge_radius_mm: 0.5,
      tip_edge_radius_mm: 0.5,
      hub_wall_thickness_mm: 6,
      hub_bottom_thickness_mm: 6,
      hub_top_cap_thickness_mm: 3,
      hub_chamfer_radius_mm: 0.8,
      hood_wall_thickness_mm: 1,
      hood_chamfer_radius_mm: 0.5,
    },
    profileOverrides: axialProfileOverrides(
      [[28, 18], [32, 16], [36, 12], [38, 8], [39, 4], [40, 0]],
      [[48, 19], [48, 17], [48, 13], [48, 9], [48, 5], [48, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.3, -1], [0.7, -3], [1, -4]],
      boundedSweepCurve(0, 36, 48, [[0, 0], [0.5, 0], [1, 0]]),
      boundedSweepCurve(0, 36, 48, [[0, 0], [0.5, 0], [1, 0]]),
      [[0, 0], [0.5, 0], [1, 0]],
      [[0, 4], [0.5, 4], [1, 3.2]],
    ),
  },
  {
    id: "reference-axial-turbine-rotor",
    presetId: "radial_open_reference_v0_7",
    name: "Reference axial turbine rotor",
    summary: "Mechanical analogy preset: an axial turbine rotor-like bladed disk using the V0.7 hub/tip and twisted blade curves.",
    tags: ["mechanical-analogy", "turbine", "axial", "rotor", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "compressor",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 54,
      inlet_radius_mm: 155,
      exit_radius_mm: 275,
      inlet_blade_height_mm: 120,
      outlet_blade_height_mm: 105,
      hub_curve_height_mm: 95,
      mounting_bore_radius_mm: 60,
      blade_wrap_deg: 48,
      blade_lean_deg: 18,
      leading_edge_lean_deg: 12,
      trailing_edge_lean_deg: -18,
      leading_edge_sweep_mm: 12,
      trailing_edge_sweep_mm: -18,
      blade_thickness_mm: 4,
      root_fillet_radius_mm: 1.5,
      leading_edge_radius_mm: 0.7,
      trailing_edge_radius_mm: 0.4,
      tip_edge_radius_mm: 0.4,
      hub_wall_thickness_mm: 8,
      hub_bottom_thickness_mm: 12,
      hub_top_cap_thickness_mm: 4,
      hub_chamfer_radius_mm: 1.2,
      hood_wall_thickness_mm: 3,
      hood_chamfer_radius_mm: 0.8,
    },
    profileOverrides: axialProfileOverrides(
      [[155, 95], [158, 76], [160, 57], [164, 38], [168, 18], [170, 0]],
      [[275, 96], [274, 77], [273, 58], [272, 39], [271, 19], [270, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.2, 8], [0.55, 28], [0.85, 42], [1, 48]],
      [[0, 12], [0.45, 24], [1, -18]],
      boundedSweepCurve(12, 155, 275, [[0, -0.05], [0.5, 0], [1, 0.07]]),
      boundedSweepCurve(-18, 155, 275, [[0, 0.08], [0.5, 0], [1, -0.09]]),
      [[0, 4], [0.45, 3.4], [1, 2]],
    ),
  },
  {
    id: "reference-double-start-worm",
    presetId: "radial_open_reference_v0_7",
    name: "Reference double-start worm",
    summary: "Mechanical analogy preset: a worm screw represented as two high-wrap helical blades on a shaft.",
    tags: ["mechanical-analogy", "worm", "screw", "v0.7"],
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "pump",
      passage_topology: "throughflow_bladed_channel",
    },
    parameters: {
      blade_count: 2,
      inlet_radius_mm: 18,
      exit_radius_mm: 45,
      inlet_blade_height_mm: 27,
      outlet_blade_height_mm: 27,
      hub_curve_height_mm: 160,
      mounting_bore_radius_mm: 5,
      blade_wrap_deg: 720,
      blade_lean_deg: 0,
      leading_edge_lean_deg: 0,
      trailing_edge_lean_deg: 0,
      leading_edge_sweep_mm: 0,
      trailing_edge_sweep_mm: 0,
      blade_thickness_mm: 5,
      root_fillet_radius_mm: 1,
      leading_edge_radius_mm: 0.5,
      trailing_edge_radius_mm: 0.5,
      tip_edge_radius_mm: 0.5,
      hub_wall_thickness_mm: 5,
      hub_bottom_thickness_mm: 7,
      hub_top_cap_thickness_mm: 3,
      hub_chamfer_radius_mm: 0.8,
      hood_wall_thickness_mm: 1,
      hood_chamfer_radius_mm: 0.5,
    },
    profileOverrides: axialProfileOverrides(
      [[18, 160], [18, 128], [18, 96], [18, 64], [18, 32], [18, 0]],
      [[45, 161], [45, 129], [45, 97], [45, 65], [45, 33], [45, 1]],
    ),
    curveOverrides: axialCurveOverrides(
      [[0, 0], [0.25, -180], [0.5, -360], [0.75, -540], [1, -720]],
      boundedSweepCurve(0, 18, 45, [[0, 0], [0.5, 0], [1, 0]]),
      boundedSweepCurve(0, 18, 45, [[0, 0], [0.5, 0], [1, 0]]),
      [[0, 0], [0.5, 0], [1, 0]],
      [[0, 5], [0.5, 5], [1, 5]],
    ),
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
