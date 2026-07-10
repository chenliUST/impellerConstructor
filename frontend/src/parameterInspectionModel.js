export const INSPECTION_TABS = [
  { id: "3d", label: "3D" },
  { id: "top", label: "Top" },
  { id: "meridional", label: "Meridional" },
  { id: "s_q", label: "S-Q" },
  { id: "quad", label: "Quad" },
];

export const ANNOTATION_LEVELS = ["key", "selected", "all"];

const SEGMENT_FACE_FAMILY = {
  pressure_side: "blade_pressure",
  suction_side: "blade_suction",
  leading_edge: "blade_leading_edge",
  trailing_edge: "blade_trailing_edge",
};

export function resolveParameterInspection(manifest) {
  if (!manifest) {
    return { status: "empty", errorCode: "parameter_inspection_not_generated" };
  }

  const contract = manifest.parameter_inspection;
  const surfaceGraph = manifest.geometry?.surface_graph;
  if (!isRecord(contract) || contract.contract_version !== "1.1.3") {
    return inspectionError("parameter_inspection_contract_unsupported");
  }
  if (!isRecord(surfaceGraph) || contract.generation_id !== surfaceGraph.generation_id || contract.generation_id !== manifest.generation_id) {
    return inspectionError("parameter_inspection_generation_id_mismatch");
  }

  const blades = contract.blade_instances;
  const surfaces = contract.surface_references;
  const stations = contract.span_stations;
  const loops = contract.section_loops;
  const profiles = contract.support_profiles;
  const dimensions = contract.resolved_dimensions;
  const continuity = contract.continuity_measurements;
  if (![blades, surfaces, stations, loops, profiles, dimensions, continuity].every(isRecord)) {
    return inspectionError("parameter_inspection_contract_unsupported");
  }
  if (
    !mappingRecordsValid(blades, "blade_instance_id")
    || !mappingRecordsValid(surfaces, "surface_id")
    || !mappingRecordsValid(stations, "span_station_id")
    || !mappingRecordsValid(loops, "section_loop_id")
    || !Object.values(loops).every((loop) => nonemptyString(loop.span_station_id))
    || !profilesValid(profiles)
    || !dimensionsValid(dimensions)
    || !Array.isArray(surfaceGraph.surfaces)
  ) {
    return inspectionError("parameter_inspection_contract_unsupported");
  }
  const graphSurfaceIds = surfaceGraph.surfaces.map((surface) => isRecord(surface) ? surface.id : null);
  if (!stringIdList(graphSurfaceIds) || !equalIdSets(graphSurfaceIds, Object.keys(surfaces))) {
    return inspectionError("parameter_inspection_surface_reference_missing");
  }
  if (!surfaceRelationshipsValid(blades, surfaces)) {
    return inspectionError("parameter_inspection_surface_reference_missing");
  }
  if (!stationRelationshipsValid(blades, stations, loops)) {
    return inspectionError("parameter_inspection_station_reference_missing");
  }
  if (!equalIdSets(Object.keys(continuity), Object.keys(loops)) || !Object.values(continuity).every(isRecord)) {
    return inspectionError("parameter_inspection_contract_unsupported");
  }

  const segmentIndex = {};
  const controlIndex = {};
  const loopValidation = validateLoops(loops, segmentIndex, controlIndex);
  if (loopValidation === "unsupported") {
    return inspectionError("parameter_inspection_contract_unsupported");
  }
  if (loopValidation === "not_closed") {
    return inspectionError("parameter_inspection_loop_not_closed");
  }

  return {
    status: "ready",
    errorCode: null,
    contract,
    surfaceGraph,
    inspectionSurfaceGraph: {
      ...surfaceGraph,
      surfaces: surfaceGraph.surfaces.filter((surface) => surfaces[surface.id]?.inspectable === true),
    },
    indices: {
      blades,
      surfaces,
      stations,
      loops,
      segments: segmentIndex,
      controls: controlIndex,
    },
  };
}

export function defaultInspectionSelection(model) {
  const bladeId = Object.keys(model.indices?.blades || {})[0] || null;
  const blade = bladeId ? model.indices.blades[bladeId] : null;
  return {
    bladeId,
    surfaceId: null,
    spanStationId: blade?.span_station_ids?.[0] || null,
    sectionSegmentId: null,
    controlPointId: null,
  };
}

export function normalizeInspectionSelection(model, selection = {}) {
  if (model?.status !== "ready") {
    return { bladeId: null, surfaceId: null, spanStationId: null, sectionSegmentId: null, controlPointId: null };
  }
  const selectedSurface = model.indices.surfaces[selection.surfaceId];
  if (selectedSurface?.inspectable === true && selectedSurface.blade_instance_id == null) {
    return {
      bladeId: null,
      surfaceId: selectedSurface.surface_id,
      surfaceFamily: selectedSurface.face_family || selectedSurface.role || null,
      owner: null,
      spanStationId: null,
      sectionSegmentId: null,
      controlPointId: null,
    };
  }
  const fallback = defaultInspectionSelection(model);
  const bladeId = model.indices.blades[selection.bladeId] ? selection.bladeId : fallback.bladeId;
  const blade = bladeId ? model.indices.blades[bladeId] : null;
  const surfaceId = blade?.surface_ids?.includes(selection.surfaceId) ? selection.surfaceId : null;
  const spanStationId = blade?.span_station_ids?.includes(selection.spanStationId)
    ? selection.spanStationId
    : blade?.span_station_ids?.[0] || null;
  const station = spanStationId ? model.indices.stations[spanStationId] : null;
  const loop = station ? model.indices.loops[station.section_loop_id] : null;
  const segment = model.indices.segments[selection.sectionSegmentId];
  const sectionSegmentId = segment?.sectionLoopId === loop?.section_loop_id ? selection.sectionSegmentId : null;
  const control = model.indices.controls[selection.controlPointId];
  const controlPointId = control?.sectionSegmentId === sectionSegmentId ? selection.controlPointId : null;
  const mappedSurfaceId = sectionSegmentId
    ? surfaceForSegment(model, bladeId, segment.segmentName)?.surface_id || surfaceId
    : surfaceId;
  return { bladeId, surfaceId: mappedSurfaceId, spanStationId, sectionSegmentId, controlPointId };
}

export function reduceInspectionSelection(model, selection, patch = {}) {
  let next = normalizeInspectionSelection(model, selection);
  if (Object.hasOwn(patch, "bladeId")) {
    const blade = model.indices?.blades?.[patch.bladeId];
    next = {
      bladeId: blade ? patch.bladeId : next.bladeId,
      surfaceId: null,
      spanStationId: blade?.span_station_ids?.[0] || next.spanStationId,
      sectionSegmentId: null,
      controlPointId: null,
    };
  }
  if (Object.hasOwn(patch, "spanStationId")) {
    const station = model.indices?.stations?.[patch.spanStationId];
    if (station) {
      const sameBladeSurface = model.indices.surfaces[next.surfaceId]?.blade_instance_id === station.blade_instance_id;
      next = {
        bladeId: station.blade_instance_id,
        surfaceId: sameBladeSurface ? next.surfaceId : null,
        spanStationId: patch.spanStationId,
        sectionSegmentId: null,
        controlPointId: null,
      };
    }
  }
  if (Object.hasOwn(patch, "surfaceId")) {
    const surface = model.indices?.surfaces?.[patch.surfaceId];
    if (surface?.inspectable === true) {
      if (surface.blade_instance_id == null) {
        next = {
          bladeId: null,
          surfaceId: patch.surfaceId,
          surfaceFamily: surface.face_family || surface.role || null,
          owner: null,
          spanStationId: null,
          sectionSegmentId: null,
          controlPointId: null,
        };
      } else {
        const blade = model.indices.blades[surface.blade_instance_id];
        const sameBlade = next.bladeId === surface.blade_instance_id;
        next = {
          bladeId: surface.blade_instance_id,
          surfaceId: patch.surfaceId,
          spanStationId: sameBlade && blade.span_station_ids.includes(next.spanStationId)
            ? next.spanStationId
            : blade.span_station_ids[0] || null,
          sectionSegmentId: null,
          controlPointId: null,
        };
      }
    } else if (patch.surfaceId == null) {
      next.surfaceId = null;
    }
  }
  if (Object.hasOwn(patch, "sectionSegmentId")) {
    const segment = model.indices?.segments?.[patch.sectionSegmentId];
    if (segment) {
      const loop = model.indices.loops[segment.sectionLoopId];
      const station = model.indices.stations[loop.span_station_id];
      next = {
        bladeId: station.blade_instance_id,
        surfaceId: surfaceForSegment(model, station.blade_instance_id, segment.segmentName)?.surface_id || null,
        spanStationId: station.span_station_id,
        sectionSegmentId: patch.sectionSegmentId,
        controlPointId: null,
      };
    } else if (patch.sectionSegmentId == null) {
      next.sectionSegmentId = null;
      next.controlPointId = null;
    }
  }
  if (Object.hasOwn(patch, "controlPointId")) {
    const control = model.indices?.controls?.[patch.controlPointId];
    if (control) {
      next = reduceInspectionSelection(model, next, { sectionSegmentId: control.sectionSegmentId });
      next.controlPointId = patch.controlPointId;
    } else if (patch.controlPointId == null) {
      next.controlPointId = null;
    }
  }
  return normalizeInspectionSelection(model, next);
}

export function selectedSurfaceIdsForSelection(model, selection) {
  const normalized = normalizeInspectionSelection(model, selection);
  if (normalized.surfaceId) {
    return [normalized.surfaceId];
  }
  return [...(model.indices?.blades?.[normalized.bladeId]?.surface_ids || [])];
}

export function sectionLoopForSelection(model, selection) {
  const fallbackStationId = defaultInspectionSelection(model).spanStationId;
  const station = model.indices?.stations?.[selection.spanStationId]
    || model.indices?.stations?.[fallbackStationId];
  return station ? model.indices.loops?.[station.section_loop_id] || null : null;
}

export function annotationsForView(model, viewId, level, selection) {
  if (model.status !== "ready") {
    return [];
  }

  const annotations = annotationsForViewId(model, viewId, selection).map((annotation) => ({
    ...annotation,
    selected: annotationMatchesSelection(annotation, selection),
  }));
  if (level === "key") {
    return annotations.filter((annotation) => annotation.level === "key");
  }
  if (level === "selected") {
    return annotations.filter((annotation) => annotation.level === "key" || annotation.selected);
  }
  return level === "all" ? annotations : [];
}

function annotationsForViewId(model, viewId, selection) {
  switch (viewId) {
    case "3d":
      return [
        ...dimensionAnnotations(model, "3d", ["thickness_min_mm", "thickness_max_mm"], selection),
        ...stationAnnotations(model, "3d"),
        ...surfaceAnnotations(model, "3d"),
      ];
    case "top":
      return [
        ...dimensionAnnotations(model, "top", [
          "main_blade_count",
          "splitter_blade_count",
          "splitter_passage_fraction",
          "angular_pitch_deg",
          "pose_theta_min_deg",
          "pose_theta_max_deg",
        ], selection),
        ...surfaceAnnotations(model, "top"),
      ];
    case "meridional":
      return [
        ...profileAnnotations(model),
        ...dimensionAnnotations(model, "meridional", ["root_offset_mm", "tip_offset_mm"], selection),
        ...stationAnnotations(model, "meridional"),
      ];
    case "s_q":
      return sectionAnnotations(model, selection);
    case "quad":
      return joinAnnotations(model, selection);
    default:
      return [];
  }
}

function surfaceAnnotations(model, viewId) {
  return Object.values(model.indices.surfaces).filter((surface) => surface.inspectable).map((surface) =>
    annotation({
      id: `${viewId}:${surface.surface_id}`,
      level: "all",
      label: titleCase(surface.face_family || "surface"),
      requestedValue: surface.face_family || null,
      resolvedValue: surface.surface_id,
      anchor: { kind: "surface", surfaceId: surface.surface_id },
      selection: { bladeId: surface.blade_instance_id, surfaceId: surface.surface_id },
      targetSurfaceIds: [surface.surface_id],
    }),
  );
}

function stationAnnotations(model, viewId = "meridional") {
  return Object.values(model.indices.stations).map((station) =>
    annotation({
      id: `${viewId}:${station.span_station_id}`,
      level: "all",
      label: "Span station",
      requestedValue: station.h,
      resolvedValue: station.h,
      anchor: { kind: "span_station", spanStationId: station.span_station_id },
      selection: { spanStationId: station.span_station_id },
      targetSurfaceIds: bladeSurfaceIds(model, station.blade_instance_id),
    }),
  );
}

function dimensionAnnotations(model, viewId, dimensionIds, selection) {
  return dimensionIds.flatMap((dimensionId) => {
    const dimension = model.contract.resolved_dimensions[dimensionId];
    if (!dimension) {
      return [];
    }
    return [annotation({
      id: `${viewId}:${dimensionId}`,
      level: "key",
      label: titleCase(dimensionId.replace(/_mm$|_deg$/, "")),
      requestedValue: dimension.requested_value,
      resolvedValue: dimension.resolved_value,
      unit: dimension.unit,
      requestedUnit: dimension.requested_unit,
      anchor: { kind: "viewport_corner", corner: "top_right" },
      targetSurfaceIds: dimensionTargetSurfaceIds(model, dimensionId, selection),
    })];
  });
}

function profileAnnotations(model) {
  return Object.values(model.contract.support_profiles).map((profile) => {
    const point = profile.control_points[Math.floor(profile.control_points.length / 2)];
    return annotation({
      id: `meridional:${profile.id}`,
      level: "key",
      label: titleCase(profile.id),
      requestedValue: profile.control_points.length,
      resolvedValue: profile.control_points.length,
      unit: "controls",
      anchor: { kind: "profile_rz", point },
      targetSurfaceIds: profileTargetSurfaceIds(model, profile.id),
    });
  });
}

function sectionAnnotations(model, selection) {
  const loop = sectionLoopForSelection(model, selection);
  const dimensions = Object.entries(model.contract.resolved_dimensions || {})
    .filter(([dimensionId]) => ["thickness_min_mm", "thickness_max_mm"].includes(dimensionId))
    .map(([dimensionId, dimension]) =>
    annotation({
      id: `s_q:${dimensionId}`,
      level: "key",
      label: titleCase(dimensionId.replace(/_mm$/, "")),
      requestedValue: dimension.requested_value,
      resolvedValue: dimension.resolved_value,
      unit: dimension.unit,
      requestedUnit: dimension.requested_unit,
      anchor: { kind: "section_loop", sectionLoopId: loop?.section_loop_id || null },
      targetSurfaceIds: bladeSurfaceIds(
        model,
        model.indices.stations[loop?.span_station_id]?.blade_instance_id || selection.bladeId,
      ),
    }));
  if (!loop) {
    return dimensions;
  }

  const segments = Object.entries(loop.segment_references || {}).map(([segmentId, segment]) => {
    const sectionSegmentId = segment.section_segment_id || segmentId;
    return annotation({
      id: `s_q:${loop.section_loop_id}:${segmentId}`,
      level: "all",
      label: titleCase(segmentId),
      requestedValue: segment.points_s_q,
      resolvedValue: segment.control_points_s_q,
      anchor: { kind: "section_segment", sectionLoopId: loop.section_loop_id, sectionSegmentId },
      selection: { spanStationId: loop.span_station_id, sectionSegmentId },
      targetSurfaceIds: [surfaceForSegment(
        model,
        model.indices.stations[loop.span_station_id]?.blade_instance_id,
        segmentId,
      )?.surface_id].filter(Boolean),
    });
  });
  return [...dimensions, ...segments];
}

function joinAnnotations(model, selection) {
  const loop = sectionLoopForSelection(model, selection);
  if (!loop) {
    return [];
  }
  return Object.entries(loop.join_metrics || {}).map(([joinId, metrics]) =>
    annotation({
      id: `quad:${loop.section_loop_id}:${joinId}`,
      level: "all",
      label: titleCase(joinId),
      requestedValue: metrics.status,
      resolvedValue: metrics.status,
      anchor: { kind: "section_loop", sectionLoopId: loop.section_loop_id },
      selection: { spanStationId: loop.span_station_id },
      metrics,
    }),
  );
}

function annotation({ id, level, label, requestedValue, resolvedValue, unit = "", requestedUnit = unit, anchor, selection = null, metrics = null, targetSurfaceIds = [] }) {
  return {
    id,
    level,
    label,
    requestedValue,
    resolvedValue,
    unit,
    requestedUnit,
    value: formatAnnotationValue(requestedValue, resolvedValue, requestedUnit, unit),
    anchor,
    selection,
    metrics,
    targetSurfaceIds: [...new Set(targetSurfaceIds)],
  };
}

function bladeSurfaceIds(model, bladeId, faceFamilies = null) {
  return (model.indices.blades[bladeId]?.surface_ids || []).filter((surfaceId) => {
    const surface = model.indices.surfaces[surfaceId];
    return surface?.inspectable === true && (!faceFamilies || faceFamilies.includes(surface.face_family));
  });
}

function allBladeSurfaceIds(model) {
  return Object.values(model.indices.blades).flatMap((blade) => bladeSurfaceIds(model, blade.blade_instance_id));
}

function dimensionTargetSurfaceIds(model, dimensionId, selection) {
  if (["main_blade_count", "splitter_blade_count", "splitter_passage_fraction", "angular_pitch_deg"].includes(dimensionId)) {
    return allBladeSurfaceIds(model);
  }
  const bladeId = selection.bladeId || defaultInspectionSelection(model).bladeId;
  if (dimensionId === "root_offset_mm") {
    return bladeSurfaceIds(model, bladeId, ["blade_root"]);
  }
  if (dimensionId === "tip_offset_mm") {
    return bladeSurfaceIds(model, bladeId, ["blade_tip"]);
  }
  return bladeSurfaceIds(model, bladeId);
}

function profileTargetSurfaceIds(model, profileId) {
  const wantsHub = String(profileId).includes("hub");
  return Object.values(model.indices.surfaces)
    .filter((surface) => {
      const family = `${surface.face_family || ""} ${surface.role || ""}`;
      return surface.inspectable === true
        && surface.blade_instance_id == null
        && (wantsHub ? family.includes("hub") : family.includes("tip") || family.includes("shroud"));
    })
    .map((surface) => surface.surface_id);
}

function annotationMatchesSelection(annotation, selection = {}) {
  const annotationSelection = annotation.selection || {};
  const identityKey = ["controlPointId", "sectionSegmentId", "surfaceId", "spanStationId", "bladeId"]
    .find((key) => selection[key] != null && annotationSelection[key] != null);
  return Boolean(identityKey) && annotationSelection[identityKey] === selection[identityKey];
}

function formatAnnotationValue(requestedValue, resolvedValue, requestedUnit, unit) {
  const requested = formatValue(requestedValue, requestedUnit);
  const resolved = formatValue(resolvedValue, unit);
  return requested === resolved ? resolved : `${requested} -> ${resolved}`;
}

function formatValue(value, unit) {
  const formatted = typeof value === "string" ? value : JSON.stringify(value);
  return unit ? `${formatted} ${unit}` : formatted;
}

function titleCase(value) {
  return String(value)
    .split("_")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

function inspectionError(errorCode) {
  return { status: "error", errorCode };
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonemptyString(value) {
  return typeof value === "string" && value.length > 0;
}

function mappingRecordsValid(records, idField) {
  return Object.entries(records).every(([id, record]) => nonemptyString(id) && isRecord(record) && record[idField] === id);
}

function stringIdList(value) {
  return Array.isArray(value)
    && value.every(nonemptyString)
    && new Set(value).size === value.length;
}

function equalIdSets(left, right) {
  return stringIdList(left)
    && stringIdList(right)
    && left.length === right.length
    && left.every((id) => right.includes(id));
}

function finitePoint(point) {
  return Array.isArray(point) && point.length === 2 && point.every(Number.isFinite);
}

function finitePointArray(points) {
  return Array.isArray(points) && points.length > 0 && points.every(finitePoint);
}

function profilesValid(profiles) {
  return Object.entries(profiles).every(([profileId, profile]) =>
    nonemptyString(profileId)
    && isRecord(profile)
    && profile.id === profileId
    && profile.coordinate_system === "rz_meridional_mm"
    && finitePointArray(profile.control_points));
}

function dimensionsValid(dimensions) {
  return Object.entries(dimensions).every(([dimensionId, dimension]) =>
    nonemptyString(dimensionId)
    && isRecord(dimension)
    && nonemptyString(dimension.unit)
    && nonemptyString(dimension.requested_unit));
}

function surfaceRelationshipsValid(blades, surfaces) {
  for (const [bladeId, blade] of Object.entries(blades)) {
    if (!stringIdList(blade.surface_ids)) {
      return false;
    }
    if (blade.surface_ids.some((surfaceId) => !surfaces[surfaceId] || surfaces[surfaceId].blade_instance_id !== bladeId)) {
      return false;
    }
  }
  return Object.entries(surfaces).every(([surfaceId, surface]) => {
    if (!isRecord(surface.quality) || typeof surface.inspectable !== "boolean") {
      return false;
    }
    const bladeId = surface.blade_instance_id;
    return bladeId == null || Boolean(blades[bladeId]?.surface_ids?.includes(surfaceId));
  });
}

function stationRelationshipsValid(blades, stations, loops) {
  for (const [bladeId, blade] of Object.entries(blades)) {
    if (!stringIdList(blade.span_station_ids)) {
      return false;
    }
    if (blade.span_station_ids.some((stationId) => !stations[stationId] || stations[stationId].blade_instance_id !== bladeId)) {
      return false;
    }
  }
  for (const [stationId, station] of Object.entries(stations)) {
    if (
      !blades[station.blade_instance_id]?.span_station_ids?.includes(stationId)
      || !loops[station.section_loop_id]
      || loops[station.section_loop_id].span_station_id !== stationId
    ) {
      return false;
    }
  }
  return Object.entries(loops).every(([loopId, loop]) =>
    Boolean(stations[loop.span_station_id]) && stations[loop.span_station_id].section_loop_id === loopId);
}

function validateLoops(loops, segmentIndex, controlIndex) {
  const segmentIds = new Set();
  const controlIds = new Set();
  for (const [loopId, loop] of Object.entries(loops)) {
    if (
      loop.source_coordinate_units?.s !== "normalized"
      || loop.source_coordinate_units?.q !== "mm"
      || loop.display_coordinate_units?.s !== "mm"
      || loop.display_coordinate_units?.q !== "mm"
      || !Number.isFinite(loop.streamwise_metric_scale_mm)
      || loop.streamwise_metric_scale_mm <= 0
      || !isRecord(loop.metrics)
      || !isRecord(loop.join_metrics)
      || !isRecord(loop.segment_references)
      || Object.keys(loop.segment_references).length === 0
    ) {
      return "unsupported";
    }
    for (const [segmentName, segment] of Object.entries(loop.segment_references)) {
      const segmentId = segment?.section_segment_id;
      if (
        !isRecord(segment)
        || segment.source_segment_name !== segmentName
        || !nonemptyString(segmentId)
        || segmentIds.has(segmentId)
        || !finitePointArray(segment.points_s_q)
        || !finitePointArray(segment.control_points_s_q)
        || !finitePointArray(segment.display_points_s_q_mm)
        || !finitePointArray(segment.display_control_points_s_q_mm)
        || !metricPointsMatch(segment.points_s_q, segment.display_points_s_q_mm, loop.streamwise_metric_scale_mm)
        || !metricPointsMatch(segment.control_points_s_q, segment.display_control_points_s_q_mm, loop.streamwise_metric_scale_mm)
        || !Array.isArray(segment.control_points)
        || segment.control_points.length !== segment.control_points_s_q.length
      ) {
        return "unsupported";
      }
      segmentIds.add(segmentId);
      segmentIndex[segmentId] = { sectionLoopId: loopId, segmentName, record: segment };
      for (let index = 0; index < segment.control_points.length; index += 1) {
        const control = segment.control_points[index];
        const controlId = control?.control_point_id;
        if (
          !isRecord(control)
          || !nonemptyString(controlId)
          || controlIds.has(controlId)
          || control.section_segment_id !== segmentId
          || !finitePoint(control.coordinates_s_q)
          || !finitePoint(control.display_coordinates_s_q_mm)
          || !pointsEqual(control.coordinates_s_q, segment.control_points_s_q[index])
          || !metricPointsMatch([control.coordinates_s_q], [control.display_coordinates_s_q_mm], loop.streamwise_metric_scale_mm)
        ) {
          return "unsupported";
        }
        controlIds.add(controlId);
        controlIndex[controlId] = { sectionSegmentId: segmentId, record: control };
      }
    }
    if (!loopClosed(loop)) {
      return "not_closed";
    }
  }
  return "valid";
}

function metricPointsMatch(source, display, scale) {
  return source.length === display.length && source.every((point, index) =>
    nearlyEqual(display[index][0], Number(point[0]) * Number(scale))
    && nearlyEqual(display[index][1], Number(point[1])));
}

function pointsEqual(left, right) {
  return finitePoint(left) && finitePoint(right) && nearlyEqual(left[0], right[0]) && nearlyEqual(left[1], right[1]);
}

function nearlyEqual(left, right) {
  return Math.abs(Number(left) - Number(right)) <= 1e-7;
}

function loopClosed(loop) {
  if (loop.metrics.join_status !== "PASS") {
    return false;
  }
  const pressure = loop.segment_references.pressure_side?.points_s_q;
  const leading = loop.segment_references.leading_edge?.points_s_q;
  const suction = loop.segment_references.suction_side?.points_s_q;
  const trailing = loop.segment_references.trailing_edge?.points_s_q;
  return [pressure, leading, suction, trailing].every(finitePointArray)
    && pointsEqual(pressure[0], leading[0])
    && pointsEqual(leading.at(-1), suction[0])
    && pointsEqual(suction.at(-1), trailing[0])
    && pointsEqual(trailing.at(-1), pressure.at(-1));
}

function surfaceForSegment(model, bladeId, segmentName) {
  const faceFamily = SEGMENT_FACE_FAMILY[segmentName];
  const blade = model.indices?.blades?.[bladeId];
  return (blade?.surface_ids || [])
    .map((surfaceId) => model.indices.surfaces[surfaceId])
    .find((surface) => surface?.face_family === faceFamily) || null;
}
