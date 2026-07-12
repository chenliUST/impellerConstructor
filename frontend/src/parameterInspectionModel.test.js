import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { presets } from "./appModel.js";
import {
  ANNOTATION_LEVELS,
  INSPECTION_TABS,
  annotationsForView,
  defaultInspectionSelection,
  engineeringParameterById,
  engineeringParameterGroups,
  equivalentParameterId,
  normalizeInspectionSelection,
  reduceInspectionSelection,
  resolveParameterInspection,
  sectionLoopForSelection,
  selectedSurfaceIdsForSelection,
} from "./parameterInspectionModel.js";

function segmentFixture(loopId, segmentName, points) {
  const sectionSegmentId = `${loopId}:${segmentName}`;
  return {
    section_segment_id: sectionSegmentId,
    source_segment_name: segmentName,
    points_s_q: points,
    control_points_s_q: points,
    display_points_s_q_mm: points.map(([s, q]) => [s * 100, q]),
    display_control_points_s_q_mm: points.map(([s, q]) => [s * 100, q]),
    control_points: points.map(([s, q], index) => ({
      control_point_id: `${sectionSegmentId}:stable_${index}_${String(s).replace(".", "_")}_${String(q).replace(".", "_")}`,
      section_segment_id: sectionSegmentId,
      coordinates_s_q: [s, q],
      display_coordinates_s_q_mm: [s * 100, q],
    })),
  };
}

function loopFixture(bladeIndex) {
  const loopId = `blade_${bladeIndex}:span_0:loop`;
  return {
    section_loop_id: loopId,
    span_station_id: `blade_${bladeIndex}:span_0`,
    source_coordinate_units: { s: "normalized", q: "mm" },
    display_coordinate_units: { s: "mm", q: "mm" },
    streamwise_metric_scale_mm: 100,
    segment_references: {
      pressure_side: segmentFixture(loopId, "pressure_side", [[0, -1], [1, -1]]),
      leading_edge: segmentFixture(loopId, "leading_edge", [[0, -1], [-0.1, 0], [0, 1]]),
      suction_side: segmentFixture(loopId, "suction_side", [[0, 1], [1, 1]]),
      trailing_edge: segmentFixture(loopId, "trailing_edge", [[1, 1], [1.1, 0], [1, -1]]),
    },
    metrics: { join_status: "PASS" },
    join_metrics: { pressure_to_leading: { status: "PASS", position_gap_mm: 0 } },
  };
}

function manifestFixture() {
  const contract = {
    contract_version: "1.1.3",
    generation_id: "g1",
    source_geometry_patch_version: "1.1.2",
    source_canonical_payload_version: "1.1.2",
    blade_instances: {
      blade_0: {
        blade_instance_id: "blade_0",
        surface_ids: ["blade_0_pressure_surface", "blade_0_suction_surface", "blade_0_root_surface", "blade_0_tip_surface"],
        span_station_ids: ["blade_0:span_0"],
      },
      blade_1: {
        blade_instance_id: "blade_1",
        surface_ids: ["blade_1_pressure_surface", "blade_1_suction_surface", "blade_1_root_surface", "blade_1_tip_surface"],
        span_station_ids: ["blade_1:span_0"],
      },
    },
    surface_references: {
      blade_0_pressure_surface: {
        surface_id: "blade_0_pressure_surface",
        blade_instance_id: "blade_0",
        face_family: "blade_pressure",
        quality: {},
        inspectable: true,
      },
      blade_0_suction_surface: {
        surface_id: "blade_0_suction_surface",
        blade_instance_id: "blade_0",
        face_family: "blade_suction",
        quality: {},
        inspectable: true,
      },
      blade_0_root_surface: {
        surface_id: "blade_0_root_surface",
        blade_instance_id: "blade_0",
        face_family: "blade_root",
        quality: {},
        inspectable: true,
      },
      blade_0_tip_surface: {
        surface_id: "blade_0_tip_surface",
        blade_instance_id: "blade_0",
        face_family: "blade_tip",
        quality: {},
        inspectable: true,
      },
      blade_1_pressure_surface: {
        surface_id: "blade_1_pressure_surface",
        blade_instance_id: "blade_1",
        face_family: "blade_pressure",
        quality: {},
        inspectable: true,
      },
      blade_1_suction_surface: {
        surface_id: "blade_1_suction_surface",
        blade_instance_id: "blade_1",
        face_family: "blade_suction",
        quality: {},
        inspectable: true,
      },
      blade_1_root_surface: {
        surface_id: "blade_1_root_surface",
        blade_instance_id: "blade_1",
        face_family: "blade_root",
        quality: {},
        inspectable: true,
      },
      blade_1_tip_surface: {
        surface_id: "blade_1_tip_surface",
        blade_instance_id: "blade_1",
        face_family: "blade_tip",
        quality: {},
        inspectable: true,
      },
      hub_support_surface: {
        surface_id: "hub_support_surface",
        blade_instance_id: null,
        face_family: "hub_support",
        quality: {},
        inspectable: true,
      },
      shroud_support_surface: {
        surface_id: "shroud_support_surface",
        blade_instance_id: null,
        face_family: "shroud_support",
        quality: {},
        inspectable: true,
      },
      tip_reference_surface: {
        surface_id: "tip_reference_surface",
        blade_instance_id: null,
        face_family: "reference_only",
        quality: {},
        inspectable: false,
      },
    },
    span_stations: {
      "blade_0:span_0": { span_station_id: "blade_0:span_0", blade_instance_id: "blade_0", section_loop_id: "blade_0:span_0:loop", h: 0.1 },
      "blade_1:span_0": { span_station_id: "blade_1:span_0", blade_instance_id: "blade_1", section_loop_id: "blade_1:span_0:loop", h: 0.1 },
    },
    section_loops: {
      "blade_0:span_0:loop": loopFixture(0),
      "blade_1:span_0:loop": loopFixture(1),
    },
    support_profiles: {
      hub_profile: {
        id: "hub_profile",
        coordinate_system: "rz_meridional_mm",
        control_points: [[150, 400], [330, 50], [580, 0]],
      },
      tip_or_shroud_profile: {
        id: "tip_or_shroud_profile",
        coordinate_system: "rz_meridional_mm",
        control_points: [[230, 401], [400, 90], [581, 30]],
      },
    },
    resolved_dimensions: {
      thickness_min_mm: { requested_value: 6.8, resolved_value: 6.8, unit: "mm", requested_unit: "mm" },
      thickness_max_mm: { requested_value: 18, resolved_value: 18, unit: "mm", requested_unit: "mm" },
      main_blade_count: { requested_value: 1, resolved_value: 1, unit: "count", requested_unit: "count" },
      splitter_blade_count: { requested_value: 1, resolved_value: 1, unit: "count", requested_unit: "count" },
      splitter_passage_fraction: { requested_value: 0.5, resolved_value: 0.5, unit: "pitch fraction", requested_unit: "pitch fraction" },
      angular_pitch_deg: { requested_value: 180, resolved_value: 180, unit: "deg", requested_unit: "deg" },
      root_offset_mm: { requested_value: 0.875, resolved_value: 14, unit: "mm", requested_unit: "thickness ratio" },
      tip_offset_mm: { requested_value: 0, resolved_value: 0, unit: "mm", requested_unit: "mm" },
    },
    continuity_measurements: {
      "blade_0:span_0:loop": { pressure_to_leading: { status: "PASS" } },
      "blade_1:span_0:loop": { pressure_to_leading: { status: "PASS" } },
    },
  };
  return {
    runtime_release_version: "1.1.3",
    generation_id: "g1",
    parameter_inspection: contract,
    geometry: {
      surface_graph: {
        generation_id: "g1",
        surfaces: [
          { id: "blade_0_pressure_surface", uv_grid: [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]] },
          { id: "blade_0_suction_surface", uv_grid: [[[0, 0, 1], [1, 0, 1]], [[0, 1, 1], [1, 1, 1]]] },
          { id: "blade_0_root_surface", uv_grid: [[[0, 0, -1], [1, 0, -1]], [[0, 1, -1], [1, 1, -1]]] },
          { id: "blade_0_tip_surface", uv_grid: [[[0, 0, 1.5], [1, 0, 1.5]], [[0, 1, 1.5], [1, 1, 1.5]]] },
          { id: "blade_1_pressure_surface", uv_grid: [[[0, 0, 2], [1, 0, 2]], [[0, 1, 2], [1, 1, 2]]] },
          { id: "blade_1_suction_surface", uv_grid: [[[0, 0, 3], [1, 0, 3]], [[0, 1, 3], [1, 1, 3]]] },
          { id: "blade_1_root_surface", uv_grid: [[[0, 0, 1], [1, 0, 1]], [[0, 1, 1], [1, 1, 1]]] },
          { id: "blade_1_tip_surface", uv_grid: [[[0, 0, 3.5], [1, 0, 3.5]], [[0, 1, 3.5], [1, 1, 3.5]]] },
          { id: "hub_support_surface", role: "hub_support", display: { visible_by_default: true }, uv_grid: [[[-2, -2, -1], [2, -2, -1]], [[-2, 2, -1], [2, 2, -1]]] },
          { id: "shroud_support_surface", role: "shroud_support", display: { visible_by_default: true }, uv_grid: [[[-3, -3, 4], [3, -3, 4]], [[-3, 3, 4], [3, 3, 4]]] },
          { id: "tip_reference_surface", role: "open_tip_reference", surface_flags: { reference_only: true }, display: { reference_only: true, visible_by_default: false }, uv_grid: [[[1000, 1000, 1000], [1001, 1000, 1000]], [[1000, 1001, 1000], [1001, 1001, 1000]]] },
        ],
      },
    },
  };
}

function engineeringManifestFixture() {
  const manifest = manifestFixture();
  const contract = manifest.parameter_inspection;
  const loopId = "blade_0:span_0:loop";
  const segmentId = `${loopId}:pressure_side`;
  const controlPointId = contract.section_loops[loopId].segment_references.pressure_side.control_points[1].control_point_id;
  const baseScope = {
    blade_instance_id: "blade_0",
    span_station_id: "blade_0:span_0",
    section_loop_id: loopId,
    section_segment_id: segmentId,
  };
  const feature = (kind, id, fields) => ({
    id,
    kind,
    coordinate_system: "s_q_mm",
    rendering_role: "selected_feature",
    ...fields,
  });
  const dimensions = [
    { kind: "linear", measurement_points: [[0, 0], [1, 0]] },
    { kind: "radial", measurement_points: [[0, 0], [1, 0]] },
    { kind: "diameter", measurement_points: [[0, 0], [1, 0]] },
    {
      kind: "angular",
      measurement_points: [[0, 0], [1, 0]],
      reference_direction: [1, 0],
      measured_direction: [0, 1],
    },
    { kind: "arc_height", measurement_points: [[0, 0], [1, 0], [0.5, 1]] },
    { kind: "ordinate", measurement_points: [[0, 0], [1, 0]] },
    { kind: "control_coordinate", measurement_points: [[0, 0], [1, 0]] },
  ].map((definition) => ({ ...definition, unit: "mm", tolerance: 0.001 }));
  const features = [
    feature("nurbs_curve", "feature:curve", { control_points: [[0, 0], [0.5, 1], [1, 0]] }),
    feature("polyline", "feature:polyline", { points: [[0, 0], [1, 0]] }),
    feature("control_point", "feature:control", { coordinates: [0.5, 1] }),
    feature("point", "feature:point", { coordinates: [0.5, 1] }),
    feature("local_frame", "feature:frame", { origin: [0, 0], s_axis: [1, 0], q_axis: [0, 1] }),
    feature("reference_axis", "feature:axis", { origin: [0, 0], direction: [1, 0] }),
  ];
  const parameter = (id, index, overrides = {}) => ({
    parameter_id: id,
    group_id: "section_loop",
    label: `Parameter ${index}`,
    requested_value: index + 1,
    resolved_value: index + 1,
    unit: "mm",
    applicable_views: ["s_q"],
    feature_geometry: [{
      ...features[index % features.length],
      id: `feature:${index}:${features[index % features.length].kind}`,
    }],
    dimension_definition: dimensions[index],
    selection_scope: baseScope,
    order: index,
    ...overrides,
  });

  contract.parameter_groups = [
    { group_id: "section_loop", label: "Section Loop", order: 10, collapsed: false },
    { group_id: "hub", label: "Hub", order: 0, collapsed: true },
  ];
  contract.parameters = dimensions.map((_, index) => parameter(
    index === 4
      ? "blade:blade_0:station:blade_0:span_0:section:leading:sagitta"
      : `parameter:${index}`,
    index,
  ));
  const sagitta = contract.parameters.find((item) => item.parameter_id.endsWith(":leading:sagitta"));
  sagitta.applicable_views = ["s_q", "blade_3d"];
  sagitta.feature_geometry = [feature("polyline", "feature:4:polyline", {
    coordinate_system: "model_xyz",
    points: [[0, 0, 0], [1, 0, 0]],
    display_points_s_q_mm: [[0, 0], [1, 0]],
  })];
  contract.parameters.push(
    parameter("blade:blade_0:station:blade_0:span_0:section:pressure:control:2:s", 7, {
      dimension_definition: null,
      feature_geometry: [feature("control_point", "feature:pressure-control-2", { coordinates: [0.4, -1] })],
      selection_scope: { ...baseScope, source_segment_name: "pressure_side", source_control_index: 2, source_control_point_id: controlPointId },
    }),
  );
  return manifest;
}

function addEquivalentPressureControl(manifest, bladeId = "blade_1") {
  const contract = manifest.parameter_inspection;
  const source = contract.parameters.find((parameter) => parameter.parameter_id.endsWith("pressure:control:2:s"));
  const loopId = `${bladeId}:span_0:loop`;
  const sectionSegmentId = `${loopId}:pressure_side`;
  const controlPointId = contract.section_loops[loopId].segment_references.pressure_side.control_points[1].control_point_id;
  contract.parameters.push({
    ...source,
    parameter_id: `blade:${bladeId}:station:${bladeId}:span_0:section:pressure:control:2:s`,
    feature_geometry: [{ ...source.feature_geometry[0], id: `feature:${bladeId}:pressure-control-2` }],
    selection_scope: {
      ...source.selection_scope,
      blade_instance_id: bladeId,
      span_station_id: `${bladeId}:span_0`,
      section_loop_id: loopId,
      section_segment_id: sectionSegmentId,
      source_control_point_id: controlPointId,
    },
    order: source.order + 1,
  });
}

function addAttachmentEvidence(manifest) {
  const contract = manifest.parameter_inspection;
  for (const bladeId of ["blade_0", "blade_1"]) {
    const surfaceId = `${bladeId}_root_attachment_surface`;
    contract.blade_instances[bladeId].surface_ids.push(surfaceId);
    contract.surface_references[surfaceId] = {
      surface_id: surfaceId,
      blade_instance_id: bladeId,
      face_family: "blade_root",
      role: "root_to_hub_attachment",
      quality: {},
      inspectable: true,
    };
    manifest.geometry.surface_graph.surfaces.push({
      id: surfaceId,
      uv_grid: [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]],
    });
  }
  contract.parameter_groups.push({ group_id: "attachments", label: "Attachments", order: 11, collapsed: true });
  contract.parameters.push({
    parameter_id: "blade:blade_0:attachment:root:width",
    group_id: "attachments",
    label: "Root attachment width",
    requested_value: 1,
    resolved_value: 1,
    unit: "mm",
    applicable_views: ["s_q"],
    feature_geometry: [{
      id: "feature:root-attachment-width",
      kind: "point",
      coordinate_system: "s_q_mm",
      rendering_role: "selected_feature",
      coordinates: [0, 0],
    }],
    dimension_definition: {
      kind: "linear",
      measurement_points: [[0, 0], [1, 0]],
      unit: "mm",
      tolerance: 0.001,
    },
    selection_scope: {
      blade_instance_id: "blade_0",
      span_station_id: "blade_0:span_0",
      section_loop_id: "blade_0:span_0:loop",
      source_attachment_surface_id: "blade_0_root_attachment_surface",
      source_attachment_measurement: "root_width",
    },
    order: 8,
  });
}

describe("parameter inspection model", () => {
  test("declares the five approved tabs and three annotation levels", () => {
    assert.deepEqual(INSPECTION_TABS.map((tab) => tab.id), ["3d", "top", "meridional", "s_q", "quad"]);
    assert.deepEqual(ANNOTATION_LEVELS, ["key", "selected", "all"]);
  });

  test("resolves one matched manifest and rejects stale evidence", () => {
    const resolved = resolveParameterInspection(manifestFixture());
    assert.equal(resolved.status, "ready", resolved.errorCode);
    const stale = manifestFixture();
    stale.geometry.surface_graph.generation_id = "g2";
    assert.equal(resolveParameterInspection(stale).errorCode, "parameter_inspection_generation_id_mismatch");
    const missingSurface = manifestFixture();
    missingSurface.geometry.surface_graph.surfaces = [];
    assert.equal(resolveParameterInspection(missingSurface).errorCode, "parameter_inspection_surface_reference_missing");
  });

  test("normalizes additive engineering evidence without changing legacy contracts", () => {
    const legacy = resolveParameterInspection(manifestFixture());
    assert.equal(legacy.status, "ready");
    assert.deepEqual(legacy.engineeringParameters, []);

    const model = resolveParameterInspection(engineeringManifestFixture());
    assert.equal(model.status, "ready", model.errorCode);
    assert.deepEqual(model.engineeringParameters.map((parameter) => parameter.id), [
      "parameter:0",
      "parameter:1",
      "parameter:2",
      "parameter:3",
      "blade:blade_0:station:blade_0:span_0:section:leading:sagitta",
      "parameter:5",
      "parameter:6",
      "blade:blade_0:station:blade_0:span_0:section:pressure:control:2:s",
    ]);
    assert.deepEqual(model.engineeringParameters.map((parameter) => parameter.features[0].kind), [
      "nurbs_curve", "polyline", "control_point", "point", "polyline", "reference_axis", "nurbs_curve", "control_point",
    ]);
    assert.deepEqual(model.engineeringParameters.slice(0, 7).map((parameter) => parameter.dimension?.kind), [
      "linear", "radial", "diameter", "angular", "arc_height", "ordinate", "control_coordinate",
    ]);

    const groups = engineeringParameterGroups(model, {
      bladeId: "blade_0",
      spanStationId: "blade_0:span_0",
      viewId: "s_q",
    });
    assert.equal(groups.find((group) => group.groupId === "section_loop").parameters.length > 0, true);
    assert.equal(
      engineeringParameterById(model, "blade:blade_0:station:blade_0:span_0:section:leading:sagitta").dimension.kind,
      "arc_height",
    );
  });

  test("rejects malformed additive engineering ids coordinates views references and values", () => {
    const cases = [
      ["parameter id", (contract) => { contract.parameters[0].parameter_id = ""; }],
      ["primitive id", (contract) => { contract.parameters[0].feature_geometry[0].id = ""; }],
      ["coordinates", (contract) => { contract.parameters[0].feature_geometry[0].control_points[0][0] = Number.NaN; }],
      ["views", (contract) => { contract.parameters[0].applicable_views = []; }],
      ["selection reference", (contract) => { contract.parameters[0].selection_scope.span_station_id = "missing"; }],
      ["dimension value", (contract) => { contract.parameters[0].resolved_value = Number.POSITIVE_INFINITY; }],
    ];
    for (const [, mutate] of cases) {
      const manifest = engineeringManifestFixture();
      mutate(manifest.parameter_inspection);
      assert.equal(resolveParameterInspection(manifest).errorCode, "parameter_inspection_contract_unsupported");
    }
  });

  test("rejects missing or ambiguous coordinate spaces for view-applicable primitives", () => {
    const mutations = [
      (feature) => { delete feature.coordinate_system; },
      (feature, parameter) => {
        feature.coordinate_system = "s_q_mm";
        delete feature.display_points_s_q_mm;
        feature.points = [[0, 0], [1, 0]];
        parameter.applicable_views = ["s_q", "blade_3d"];
      },
      (feature, parameter) => {
        feature.coordinate_system = "model_xyz";
        delete feature.display_points_s_q_mm;
        parameter.applicable_views = ["s_q", "blade_3d"];
      },
    ];
    for (const mutate of mutations) {
      const manifest = engineeringManifestFixture();
      const parameter = manifest.parameter_inspection.parameters.find((item) => item.parameter_id.endsWith(":leading:sagitta"));
      mutate(parameter.feature_geometry[0], parameter);
      assert.equal(resolveParameterInspection(manifest).errorCode, "parameter_inspection_contract_unsupported");
    }
  });

  test("rejects nonexistent and cross-blade attachment surface provenance", () => {
    const cases = [
      "missing_attachment_surface",
      "blade_1_root_attachment_surface",
    ];
    for (const sourceAttachmentSurfaceId of cases) {
      const manifest = engineeringManifestFixture();
      addAttachmentEvidence(manifest);
      assert.equal(resolveParameterInspection(manifest).status, "ready");
      const attachment = manifest.parameter_inspection.parameters.find((parameter) =>
        parameter.parameter_id === "blade:blade_0:attachment:root:width");
      attachment.selection_scope.source_attachment_surface_id = sourceAttachmentSurfaceId;
      assert.equal(resolveParameterInspection(manifest).errorCode, "parameter_inspection_contract_unsupported");
    }
  });

  test("finds a deterministic equivalent parameter in the next selection context", () => {
    const manifest = engineeringManifestFixture();
    addEquivalentPressureControl(manifest);
    const model = resolveParameterInspection(manifest);
    const currentId = "blade:blade_0:station:blade_0:span_0:section:pressure:control:2:s";

    assert.equal(
      equivalentParameterId(model, currentId, { bladeId: "blade_1", spanStationId: "blade_1:span_0" }),
      "blade:blade_1:station:blade_1:span_0:section:pressure:control:2:s",
    );
    assert.equal(equivalentParameterId(model, currentId, { bladeId: "missing", spanStationId: "missing" }), null);
  });

  test("selects the first blade and station without mutation", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    const updated = reduceInspectionSelection(model, selection, { surfaceId: "blade_0_pressure_surface" });
    assert.equal(selection.surfaceId, null);
    assert.equal(updated.surfaceId, "blade_0_pressure_surface");
    assert.equal(sectionLoopForSelection(model, updated).section_loop_id, "blade_0:span_0:loop");
  });

  test("filters annotation levels deterministically", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    assert.ok(annotationsForView(model, "s_q", "key", selection).length > 0);
    assert.ok(annotationsForView(model, "s_q", "all", selection).length >= annotationsForView(model, "s_q", "key", selection).length);
    assert.deepEqual(
      annotationsForView(model, "s_q", "key", selection).map((annotation) => annotation.id),
      ["s_q:thickness_min_mm", "s_q:thickness_max_mm"],
    );
  });

  test("selected surface excludes sibling surfaces on the same blade", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = reduceInspectionSelection(model, defaultInspectionSelection(model), {
      surfaceId: "blade_0_pressure_surface",
    });

    assert.deepEqual(
      annotationsForView(model, "3d", "selected", selection)
        .filter((annotation) => annotation.anchor.kind === "surface")
        .map((annotation) => annotation.id),
      ["3d:blade_0_pressure_surface"],
    );
  });

  test("selected section segment excludes siblings while retaining key annotations", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = reduceInspectionSelection(model, defaultInspectionSelection(model), {
      sectionSegmentId: "blade_0:span_0:loop:pressure_side",
    });

    const annotations = annotationsForView(model, "s_q", "selected", selection);
    assert.deepEqual(
      annotations.filter((annotation) => annotation.level === "all").map((annotation) => annotation.id),
      ["s_q:blade_0:span_0:loop:pressure_side"],
    );
    const pressureSide = annotations.find((annotation) => annotation.level === "all");
    assert.equal(pressureSide.label, "Pressure Side");
    assert.equal(pressureSide.anchor.sectionSegmentId, "blade_0:span_0:loop:pressure_side");
    assert.equal(pressureSide.selection.sectionSegmentId, "blade_0:span_0:loop:pressure_side");
  });

  test("decorates key selected and all levels with deterministic selected flags", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = reduceInspectionSelection(model, defaultInspectionSelection(model), {
      sectionSegmentId: "blade_0:span_0:loop:pressure_side",
    });

    const keyAnnotations = annotationsForView(model, "s_q", "key", selection);
    assert.ok(keyAnnotations.every((annotation) => annotation.selected === false));

    const selectedAnnotations = annotationsForView(model, "s_q", "selected", selection);
    assert.equal(selectedAnnotations.filter((annotation) => annotation.level === "all").length, 1);
    assert.equal(selectedAnnotations.find((annotation) => annotation.level === "all").selected, true);

    const allAnnotations = annotationsForView(model, "s_q", "all", selection);
    assert.equal(allAnnotations.find((annotation) => annotation.label === "Pressure Side").selected, true);
    assert.ok(
      allAnnotations
        .filter((annotation) => annotation.level === "all" && annotation.label !== "Pressure Side")
        .every((annotation) => annotation.selected === false),
    );
  });

  test("blade-only selection expands to all annotations on the blade", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = {
      bladeId: "blade_0",
      surfaceId: null,
      spanStationId: null,
      sectionSegmentId: null,
      controlPointId: null,
    };

    assert.deepEqual(
      annotationsForView(model, "3d", "selected", selection)
        .filter((annotation) => annotation.level === "all")
        .map((annotation) => annotation.id),
      model.indices.blades.blade_0.surface_ids.map((surfaceId) => `3d:${surfaceId}`),
    );
  });

  test("default selection keeps blade-linked 3D and Top annotations visible", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    assert.equal(selection.spanStationId, "blade_0:span_0");

    for (const viewId of ["3d", "top"]) {
      assert.deepEqual(
        annotationsForView(model, viewId, "selected", selection)
          .filter((annotation) => annotation.anchor.kind === "surface")
          .map((annotation) => annotation.id),
        model.indices.blades.blade_0.surface_ids.map((surfaceId) => `${viewId}:${surfaceId}`),
      );
    }
    assert.ok(annotationsForView(model, "3d", "selected", selection).some((annotation) => annotation.anchor.kind === "span_station"));
  });

  test("normalizes cross-blade surface picks and clears dependent identities", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selected = reduceInspectionSelection(model, defaultInspectionSelection(model), {
      sectionSegmentId: "blade_0:span_0:loop:pressure_side",
      controlPointId: "blade_0:span_0:loop:pressure_side:stable_0_0_-1",
    });
    const crossBlade = reduceInspectionSelection(model, selected, { surfaceId: "blade_1_suction_surface" });

    assert.deepEqual(crossBlade, {
      bladeId: "blade_1",
      surfaceId: "blade_1_suction_surface",
      spanStationId: "blade_1:span_0",
      sectionSegmentId: null,
      controlPointId: null,
    });
  });

  test("excludes hidden reference samples from scene input and annotations while retaining visible supports", () => {
    const baseline = resolveParameterInspection(manifestFixture());
    const mutatedManifest = manifestFixture();
    mutatedManifest.geometry.surface_graph.surfaces.find(({ id }) => id === "tip_reference_surface").uv_grid = [
      [[-1e9, -1e9, -1e9], [1e9, -1e9, -1e9]],
      [[-1e9, 1e9, 1e9], [1e9, 1e9, 1e9]],
    ];
    const mutated = resolveParameterInspection(mutatedManifest);

    assert.equal(baseline.status, "ready");
    assert.equal(mutated.status, "ready");
    assert.deepEqual(mutated.inspectionSurfaceGraph, baseline.inspectionSurfaceGraph);
    assert.deepEqual(
      baseline.inspectionSurfaceGraph.surfaces.map(({ id }) => id),
      [
        "blade_0_pressure_surface",
        "blade_0_suction_surface",
        "blade_0_root_surface",
        "blade_0_tip_surface",
        "blade_1_pressure_surface",
        "blade_1_suction_surface",
        "blade_1_root_surface",
        "blade_1_tip_surface",
        "hub_support_surface",
        "shroud_support_surface",
      ],
    );
    for (const viewId of ["3d", "top"]) {
      const annotationIds = annotationsForView(baseline, viewId, "all", defaultInspectionSelection(baseline))
        .map(({ id }) => id);
      assert.ok(annotationIds.includes(`${viewId}:hub_support_surface`));
      assert.ok(annotationIds.includes(`${viewId}:shroud_support_surface`));
      assert.ok(!annotationIds.includes(`${viewId}:tip_reference_surface`));
    }
  });

  test("selects unowned hub and shroud supports without stale blade dependencies and keeps an S-Q fallback", () => {
    const model = resolveParameterInspection(manifestFixture());
    const bladeSelection = reduceInspectionSelection(model, defaultInspectionSelection(model), {
      sectionSegmentId: "blade_1:span_0:loop:pressure_side",
    });

    for (const [surfaceId, surfaceFamily] of [
      ["hub_support_surface", "hub_support"],
      ["shroud_support_surface", "shroud_support"],
    ]) {
      const supportSelection = reduceInspectionSelection(model, bladeSelection, { surfaceId });
      assert.deepEqual(supportSelection, {
        bladeId: null,
        surfaceId,
        surfaceFamily,
        owner: null,
        spanStationId: null,
        sectionSegmentId: null,
        controlPointId: null,
      });
      assert.deepEqual(selectedSurfaceIdsForSelection(model, supportSelection), [surfaceId]);
      assert.equal(sectionLoopForSelection(model, supportSelection).section_loop_id, "blade_0:span_0:loop");
    }
  });

  test("switches stations through the owning blade and maps segments to face families", () => {
    const model = resolveParameterInspection(manifestFixture());
    const stationSelection = reduceInspectionSelection(model, defaultInspectionSelection(model), {
      spanStationId: "blade_1:span_0",
    });
    assert.equal(stationSelection.bladeId, "blade_1");
    assert.equal(sectionLoopForSelection(model, stationSelection).section_loop_id, "blade_1:span_0:loop");

    const segmentSelection = reduceInspectionSelection(model, stationSelection, {
      sectionSegmentId: "blade_1:span_0:loop:pressure_side",
    });
    assert.equal(segmentSelection.surfaceId, "blade_1_pressure_surface");
    assert.deepEqual(selectedSurfaceIdsForSelection(model, segmentSelection), ["blade_1_pressure_surface"]);
    assert.deepEqual(
      selectedSurfaceIdsForSelection(model, reduceInspectionSelection(model, segmentSelection, { bladeId: "blade_0" })),
      model.indices.blades.blade_0.surface_ids,
    );
  });

  test("normalizer removes invalid dependent ids without mutating input", () => {
    const model = resolveParameterInspection(manifestFixture());
    const input = {
      bladeId: "blade_0",
      surfaceId: "blade_1_pressure_surface",
      spanStationId: "missing_station",
      sectionSegmentId: "missing_segment",
      controlPointId: "missing_control",
    };
    const normalized = normalizeInspectionSelection(model, input);

    assert.equal(input.surfaceId, "blade_1_pressure_surface");
    assert.deepEqual(normalized, defaultInspectionSelection(model));
  });

  test("deeply rejects malformed containers ids references controls and closure", () => {
    const cases = [];
    const wrongContainer = manifestFixture();
    wrongContainer.parameter_inspection.blade_instances = null;
    cases.push([wrongContainer, "parameter_inspection_contract_unsupported"]);
    const wrongArray = manifestFixture();
    wrongArray.parameter_inspection.section_loops = [];
    cases.push([wrongArray, "parameter_inspection_contract_unsupported"]);
    const extraSurface = manifestFixture();
    extraSurface.geometry.surface_graph.surfaces.push({ id: "extra_surface", uv_grid: [] });
    cases.push([extraSurface, "parameter_inspection_surface_reference_missing"]);
    const invalidLoopReference = manifestFixture();
    invalidLoopReference.parameter_inspection.section_loops["blade_0:span_0:loop"].span_station_id = "blade_1:span_0";
    cases.push([invalidLoopReference, "parameter_inspection_station_reference_missing"]);
    const malformedLoopStation = manifestFixture();
    malformedLoopStation.parameter_inspection.section_loops["blade_0:span_0:loop"].span_station_id = [];
    cases.push([malformedLoopStation, "parameter_inspection_contract_unsupported"]);
    const malformedControl = manifestFixture();
    malformedControl.parameter_inspection.section_loops["blade_0:span_0:loop"].segment_references.pressure_side.control_points[0] = null;
    cases.push([malformedControl, "parameter_inspection_contract_unsupported"]);
    const duplicateControl = manifestFixture();
    const controls = duplicateControl.parameter_inspection.section_loops["blade_0:span_0:loop"].segment_references.pressure_side.control_points;
    controls[1].control_point_id = controls[0].control_point_id;
    cases.push([duplicateControl, "parameter_inspection_contract_unsupported"]);
    const stringCoordinate = manifestFixture();
    stringCoordinate.parameter_inspection.section_loops["blade_0:span_0:loop"].segment_references.pressure_side.control_points[0].coordinates_s_q[0] = "0";
    cases.push([stringCoordinate, "parameter_inspection_contract_unsupported"]);
    const nonclosed = manifestFixture();
    nonclosed.parameter_inspection.section_loops["blade_0:span_0:loop"].metrics.join_status = "FAIL";
    cases.push([nonclosed, "parameter_inspection_loop_not_closed"]);

    for (const [manifest, errorCode] of cases) {
      assert.doesNotThrow(() => resolveParameterInspection(manifest));
      assert.equal(resolveParameterInspection(manifest).errorCode, errorCode);
    }
  });

  test("key annotations provide useful evidence in every geometric view", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    for (const viewId of ["3d", "top", "meridional"]) {
      const keyAnnotations = annotationsForView(model, viewId, "key", selection);
      assert.ok(keyAnnotations.length > 0, viewId);
      assert.ok(keyAnnotations.every((annotation) => annotation.level === "key"), viewId);
    }
    assert.match(annotationsForView(model, "top", "key", selection).map(({ label }) => label).join(" "), /Blade Count/);
    assert.match(annotationsForView(model, "meridional", "key", selection).map(({ label }) => label).join(" "), /Hub Profile/);
  });

  test("maps parameter rows to their generated inspectable surfaces", () => {
    const model = resolveParameterInspection(manifestFixture());
    const selection = defaultInspectionSelection(model);
    const byId = (viewId, level = "key") => Object.fromEntries(
      annotationsForView(model, viewId, level, selection).map((item) => [item.id, item]),
    );

    const view3d = byId("3d");
    assert.deepEqual(view3d["3d:thickness_max_mm"].targetSurfaceIds, model.indices.blades.blade_0.surface_ids);

    const top = byId("top");
    assert.deepEqual(top["top:main_blade_count"].targetSurfaceIds, [
      ...model.indices.blades.blade_0.surface_ids,
      ...model.indices.blades.blade_1.surface_ids,
    ]);
    assert.deepEqual(top["top:angular_pitch_deg"].targetSurfaceIds, [
      ...model.indices.blades.blade_0.surface_ids,
      ...model.indices.blades.blade_1.surface_ids,
    ]);

    const meridional = byId("meridional");
    assert.deepEqual(meridional["meridional:root_offset_mm"].targetSurfaceIds, ["blade_0_root_surface"]);
    assert.deepEqual(meridional["meridional:tip_offset_mm"].targetSurfaceIds, ["blade_0_tip_surface"]);
    assert.deepEqual(meridional["meridional:hub_profile"].targetSurfaceIds, ["hub_support_surface"]);
    assert.deepEqual(meridional["meridional:tip_or_shroud_profile"].targetSurfaceIds, ["shroud_support_surface"]);

    const section = byId("s_q", "all");
    assert.deepEqual(
      section["s_q:blade_0:span_0:loop:pressure_side"].targetSurfaceIds,
      ["blade_0_pressure_surface"],
    );
    assert.ok(
      Object.values({ ...view3d, ...top, ...meridional, ...section })
        .flatMap((item) => item.targetSurfaceIds)
        .every((surfaceId) => model.indices.surfaces[surfaceId]?.inspectable === true),
    );
  });

  test("active display names identify v1.1.5 while backend preset ids remain stable", () => {
    for (const preset of presets) {
      assert.match(preset.name, /v1\.1\.5/i);
      assert.match(preset.summary, /V1\.1\.5/);
      assert.match(preset.summary, /runtime/i);
      assert.match(preset.summary, /review/i);
      assert.ok(preset.tags.includes("v1.1.5"));
      assert.match(preset.presetId, /_v1_1$/);
    }
  });
});
