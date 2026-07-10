export const apiDefault = "http://127.0.0.1:8061";

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

export function editableParameterIdsForPreset(presetRef) {
  const preset = resolvePresetReference(presetRef);
  if (Array.isArray(preset?.editableParameters) && preset.editableParameters.length > 0) {
    return [...preset.editableParameters];
  }
  return Object.keys(parameterSchema);
}

export function hiddenParameterIdsForPreset(presetRef) {
  const editable = new Set(editableParameterIdsForPreset(presetRef));
  return Object.keys(parameterSchema).filter((name) => !editable.has(name));
}

export function parameterSchemaForPreset(presetRef) {
  return Object.fromEntries(
    editableParameterIdsForPreset(presetRef)
      .map((name) => [name, parameterSchema[name]])
      .filter(([, spec]) => spec),
  );
}

export function curveControlsForPreset(presetRef) {
  const preset = resolvePresetReference(presetRef);
  return clonePlainObject(preset?.curveControls || v10SectionLoopCurveControls());
}

export function canonicalParameterizationForPreset(presetRef) {
  const preset = resolvePresetReference(presetRef);
  return clonePlainObject(preset?.canonicalNurbsParameterization || {});
}

export function editorVisibilityForPreset(presetRef) {
  const preset = resolvePresetReference(presetRef);
  const presetId = String(preset?.presetId || preset?.id || "");
  const isV11 = presetId.endsWith("_v1_1");
  return {
    edgeTreatmentPanel: !isV11,
    bladeCurveEditor: !isV11,
    profileCurveEditor: true,
    curveControlPanel: true,
  };
}

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

function v10SectionLoopCurveControls() {
  return {
    blade_section_loop_template: {
      label: "Blade section loop",
      coordinate_system: "local_chord_thickness_mm",
      continuity_goal: "G2",
      segment_order: ["pressure_side", "leading_edge", "suction_side", "trailing_edge"],
      closed_loop_preview: [
        [0, -10], [30, -11], [82, -10], [108, -8], [126, -6], [137, -4], [142, 0], [137, 4],
        [126, 6], [84, 10], [32, 11], [0, 10], [-7, 7], [-10, 0], [-7, -7], [0, -10],
      ],
      segments: {
        pressure_side: { label: "pressure_side", control_points: [[0, -10], [30, -11], [82, -10], [126, -6]] },
        leading_edge: { label: "leading_edge", control_points: [[0, -10], [-7, -7], [-10, 0], [-7, 7], [0, 10]] },
        suction_side: { label: "suction_side", control_points: [[0, 10], [32, 11], [84, 10], [126, 6]] },
        trailing_edge: { label: "trailing_edge", control_points: [[126, 6], [137, 4], [142, 0], [137, -4], [126, -6]] },
      },
    },
  };
}

function v11BladeToBladeLoopCurveControls() {
  return {
    blade_to_blade_loop_family: {
      label: "Blade-to-blade loop family",
      coordinate_system: "blade_to_blade_s_q_mm",
      continuity_goal: "C2/G2",
      span_stations_h: [0, 0.25, 0.5, 0.75, 1],
      segment_order: ["pressure_side", "leading_edge", "suction_side", "trailing_edge"],
      segments: {
        pressure_side: {
          color: "#6f9b85",
          control_points: [
            [0.06, -12.75], [0.151666667, -10.872052504], [0.243333333, -3.383015991], [0.316666667, 5.551277494],
            [0.408333333, 18.680386934], [0.5, 32], [0.591666667, 43.934654874], [0.683333333, 53.835421012],
            [0.756666667, 60.228673823], [0.848333333, 66.160137889], [0.94, 69.25],
          ],
        },
        suction_side: {
          color: "#6f9b85",
          control_points: [
            [0.06, 12.75], [0.151666667, 17.360182951], [0.243333333, 27.291456155], [0.316666667, 37.794780886],
            [0.408333333, 52.229293035], [0.5, 66], [0.591666667, 77.483560975], [0.683333333, 86.078924405],
            [0.756666667, 90.90314597], [0.848333333, 94.392373344], [0.94, 94.75],
          ],
        },
        leading_edge: {
          color: "#facc15",
          control_points: [
            [0.06, -12.75], [0.051241983, -11.497052354], [0.045860059, -9.502317578], [0.031533528, -5.216688754],
            [0.01516035, -0.058862477], [0.006139942, 3.456505895], [0, 8.255446552], [0.006139942, 11.897583238],
            [0.01516035, 13.460116642], [0.031533528, 14.41402801], [0.045860059, 13.974163682], [0.051241983, 13.296224124],
            [0.06, 12.75],
          ],
        },
        trailing_edge: {
          color: "#facc15",
          control_points: [
            [0.94, 94.75], [0.948758017, 93.919098686], [0.954139941, 92.551317039], [0.968466472, 89.374190174],
            [0.98483965, 85.202514817], [0.993860058, 82.145240932], [1, 77.617662451], [0.993860058, 73.704163588],
            [0.98483965, 71.683535698], [0.968466472, 69.743473411], [0.954139941, 69.074835778], [0.948758017, 69.125822208],
            [0.94, 69.25],
          ],
        },
      },
    },
  };
}

function v11ProfileOverrides() {
  return axialProfileOverrides(
    [[150, 400], [170, 250], [220, 150], [330, 50], [480, 10], [580, 0]],
    [[230, 401], [250, 270], [310, 170], [400, 90], [490, 50], [581, 30]],
  );
}

function v11OpenReferenceProfileOverrides() {
  return axialProfileOverrides(
    [[150, 400], [170, 250], [220, 150], [330, 50], [480, 10], [580, 0]],
    [[300, 407], [320, 305], [350, 218], [400, 130], [490, 70], [581, 34]],
  );
}

function v11ClosedReferenceProfileOverrides() {
  return axialProfileOverrides(
    [[180, 300], [210, 220], [270, 145], [380, 75], [500, 24], [610, 0]],
    [[260, 306], [290, 240], [350, 165], [450, 95], [540, 50], [615, 34]],
  );
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

const v111TransitionGeometryStatus = "topology_first_blade_to_blade_5_loop_surface_family_graph";

function v111Metadata() {
  return {
    geometryVersion: "1.1",
    geometryPatchVersion: "1.1.1",
    transitionGeometryStatus: v111TransitionGeometryStatus,
  };
}

function v112CanonicalFromPreset({ parameters, profileOverrides, loopFamilyDefaults }) {
  const hub = profileOverrides?.hub_profile?.control_points || [];
  const tip = profileOverrides?.tip_or_shroud_profile?.control_points || [];
  return {
    canonical_payload_version: "1.1.2",
    math_parameterization: "v1_1_2_canonical_nurbs_parameterization",
    canonical_input_source: "translated_from_legacy_v1_1",
    support_profiles: {
      hub_profile: profile(hub),
      tip_or_shroud_profile: profile(tip),
    },
    active_span_policy: {
      root_offset: {
        mode: "thickness_ratio",
        resolved_constant_mm: loopFamilyDefaults.root_attachment_lift_mm || parameters.root_fillet_radius_mm || 0,
      },
      tip_offset: {
        mode: "closed_shroud_thickness_ratio_or_open_zero",
        resolved_constant_mm: loopFamilyDefaults.shroud_blade_inset_mm || 0,
      },
    },
    blade_population: { ...loopFamilyDefaults },
    section_loop_family: {
      mode: "skeleton_thickness_caps",
      span_stations_h: loopFamilyDefaults.span_stations_h || [0, 0.25, 0.5, 0.75, 1],
    },
  };
}

function withV112CanonicalPreset(preset) {
  return {
    ...preset,
    geometryPatchVersion: "1.1.2",
    metadata: {
      ...v111Metadata(),
      geometryPatchVersion: "1.1.2",
      mathParameterization: "v1_1_2_canonical_nurbs_parameterization",
    },
    canonicalNurbsParameterization: v112CanonicalFromPreset(preset),
  };
}

export const presets = [
  {
    id: "axisymmetric-nurbs-open-throughflow",
    presetId: "radial_open_reference_v1_1",
    geometryPatchVersion: "1.1.1",
    name: "Topology first open throughflow V1.1.3",
    summary: "Open impeller: runtime V1.1.3 with inspection contract V1.1.3 over canonical V1.1.2 geometry and the representative main/splitter population.",
    tags: ["open", "topology-first", "v1.1.3", "representative"],
    metadata: v111Metadata(),
    editableParameters: [
      "mounting_bore_radius_mm",
      "blade_wrap_deg",
      "blade_thickness_mm",
      "hub_wall_thickness_mm",
      "hub_bottom_thickness_mm",
    ],
    loopFamilyDefaults: { main_blade_count: 8, splitter_blade_count: 8 },
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
      blade_count: 16,
      inlet_radius_mm: 150,
      exit_radius_mm: 580,
      inlet_blade_height_mm: 170,
      outlet_blade_height_mm: 30,
      hub_curve_height_mm: 400,
      mounting_bore_radius_mm: 44,
      blade_wrap_deg: 216,
      blade_lean_deg: 18,
      leading_edge_lean_deg: 6,
      trailing_edge_lean_deg: -10,
      leading_edge_sweep_mm: 0,
      trailing_edge_sweep_mm: 0,
      blade_thickness_mm: 16,
      root_fillet_radius_mm: 14,
      leading_edge_radius_mm: 4,
      trailing_edge_radius_mm: 3,
      tip_edge_radius_mm: 6,
      hub_wall_thickness_mm: 24,
      hub_bottom_thickness_mm: 32,
      hub_top_cap_thickness_mm: 8,
      hub_chamfer_radius_mm: 6,
      hood_wall_thickness_mm: 12,
      hood_chamfer_radius_mm: 3,
    },
    profileOverrides: v11OpenReferenceProfileOverrides(),
    curveControls: v11BladeToBladeLoopCurveControls(),
  },
  {
    id: "axisymmetric-nurbs-closed-throughflow",
    presetId: "radial_closed_reference_v1_1",
    geometryPatchVersion: "1.1.1",
    name: "Topology first closed throughflow V1.1.3",
    summary: "Closed impeller: runtime V1.1.3 with inspection contract V1.1.3 over canonical V1.1.2 geometry and the representative closed-loop population.",
    tags: ["closed", "topology-first", "v1.1.3", "representative"],
    metadata: v111Metadata(),
    editableParameters: [
      "mounting_bore_radius_mm",
      "blade_wrap_deg",
      "blade_thickness_mm",
      "hub_wall_thickness_mm",
      "hub_bottom_thickness_mm",
      "hood_wall_thickness_mm",
    ],
    loopFamilyDefaults: { main_blade_count: 12, splitter_blade_count: 0 },
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
      inlet_radius_mm: 180,
      exit_radius_mm: 610,
      inlet_blade_height_mm: 120,
      outlet_blade_height_mm: 60,
      hub_curve_height_mm: 300,
      mounting_bore_radius_mm: 42,
      blade_wrap_deg: 136,
      blade_lean_deg: 7,
      leading_edge_lean_deg: 0,
      trailing_edge_lean_deg: 0,
      leading_edge_sweep_mm: 0,
      trailing_edge_sweep_mm: 0,
      blade_thickness_mm: 24,
      root_fillet_radius_mm: 14,
      leading_edge_radius_mm: 4,
      trailing_edge_radius_mm: 3,
      tip_edge_radius_mm: 6,
      hub_wall_thickness_mm: 24,
      hub_bottom_thickness_mm: 32,
      hub_top_cap_thickness_mm: 8,
      hub_chamfer_radius_mm: 6,
      hood_wall_thickness_mm: 24,
      hood_chamfer_radius_mm: 6,
    },
    profileOverrides: v11ClosedReferenceProfileOverrides(),
    curveControls: v11BladeToBladeLoopCurveControls(),
  },
  {
    id: "public-nasa-stage37-stator-ring",
    presetId: "nasa_stage37_stator_ring_v1_1",
    geometryPatchVersion: "1.1.1",
    name: "NASA Stage 37 stator ring V1.1.3",
    summary: "Representative public axial stator-ring approximation: runtime V1.1.3 with inspection contract V1.1.3 over canonical V1.1.2 geometry.",
    tags: ["public-data", "axial", "stator", "stage37", "v1.1.3"],
    metadata: v111Metadata(),
    editableParameters: [
      "mounting_bore_radius_mm",
      "blade_thickness_mm",
      "blade_wrap_deg",
      "hub_wall_thickness_mm",
      "hub_bottom_thickness_mm",
      "hood_wall_thickness_mm",
    ],
    loopFamilyDefaults: { main_blade_count: 46, splitter_blade_count: 0 },
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "closed",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "compressor",
      passage_topology: "throughflow_bladed_channel",
    },
    synthesizeFacets: {},
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
      [[0, 0], [0.2, 4], [0.55, 14], [0.85, 20], [1, 24]],
      [[0, -4], [0.45, 1], [1, 5]],
      boundedSweepCurve(2, 176.4, 253.7, [[0, -0.03], [0.5, 0], [1, 0.04]]),
      boundedSweepCurve(-3, 176.4, 253.7, [[0, 0.04], [0.5, 0], [1, -0.05]]),
      [[0, 2.3], [0.45, 2], [1, 1.2]],
    ),
  },
  {
    id: "public-rr-ultrafan-cti-fan",
    presetId: "rr_ultrafan_cti_fan_v1_1",
    geometryPatchVersion: "1.1.1",
    name: "RR UltraFan CTi fan V1.1.3",
    summary: "Representative public UltraFan CTi fan approximation: runtime V1.1.3 with inspection contract V1.1.3 over canonical V1.1.2 geometry.",
    tags: ["public-data", "axial", "fan", "ultrafan", "v1.1.3"],
    metadata: v111Metadata(),
    editableParameters: [
      "mounting_bore_radius_mm",
      "blade_thickness_mm",
      "blade_wrap_deg",
      "hub_wall_thickness_mm",
      "hub_bottom_thickness_mm",
    ],
    loopFamilyDefaults: { main_blade_count: 18, splitter_blade_count: 0 },
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "fan_or_blower",
      passage_topology: "throughflow_bladed_channel",
    },
    synthesizeFacets: {},
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
    id: "public-liquid-rocket-turbopump-inducer",
    presetId: "public_rocket_turbopump_inducer_v1_1",
    geometryPatchVersion: "1.1.1",
    name: "Public rocket turbopump inducer V1.1.3",
    summary: "Representative public liquid-rocket turbopump inducer approximation: runtime V1.1.3 with inspection contract V1.1.3 over canonical V1.1.2 geometry.",
    tags: ["public-data", "axial", "inducer", "pump", "v1.1.3"],
    metadata: v111Metadata(),
    editableParameters: [
      "mounting_bore_radius_mm",
      "blade_thickness_mm",
      "blade_wrap_deg",
      "hub_wall_thickness_mm",
      "hub_bottom_thickness_mm",
    ],
    loopFamilyDefaults: { main_blade_count: 3, splitter_blade_count: 0 },
    partFamilyId: "impeller",
    facets: {
      flow_topology: "axial",
      shroud_topology: "open",
      suction_topology: "single_suction",
      blade_exit_geometry: "backward_curved",
      working_domain: "pump",
      passage_topology: "throughflow_bladed_channel",
    },
    synthesizeFacets: {},
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
].map(withV112CanonicalPreset).sort((left, right) => presetDisplayRank(left) - presetDisplayRank(right));

function presetDisplayRank(preset) {
  const preferredOrder = {
    radial_open_reference_v1_1: 0,
    radial_closed_reference_v1_1: 1,
    nasa_stage37_stator_ring_v1_1: 2,
    rr_ultrafan_cti_fan_v1_1: 3,
    public_rocket_turbopump_inducer_v1_1: 4,
  };
  return preferredOrder[preset.presetId] ?? 100;
}

export function buildInstantiatePayload(
  inputParameters,
  profileOverrides = null,
  curveOverrides = null,
  transitionOverrides = null,
  geometryStage = "edge_closures",
  sectionLoopOverrides = null,
  bladeToBladeLoopFamilyOverrides = null,
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
  if (sectionLoopOverrides) {
    payload.section_loop_overrides = sectionLoopOverrides;
  }
  if (bladeToBladeLoopFamilyOverrides && Object.keys(bladeToBladeLoopFamilyOverrides).length > 0) {
    payload.blade_to_blade_loop_family_overrides = bladeToBladeLoopFamilyOverrides;
  }
  return payload;
}

export function buildSynthesizePayload(preset) {
  const facets = Object.hasOwn(preset, "synthesizeFacets") ? preset.synthesizeFacets : preset.facets;
  return {
    part_family_id: preset.partFamilyId,
    preset_id: preset.presetId,
    facets: { ...facets },
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

function resolvePresetReference(presetRef) {
  if (presetRef && typeof presetRef === "object") {
    return presetRef;
  }
  return presets.find((preset) => preset.id === presetRef || preset.presetId === presetRef) || null;
}

function clonePlainObject(value) {
  return value ? JSON.parse(JSON.stringify(value)) : {};
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
