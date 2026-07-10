export const INSPECTION_TABS = [
  { id: "3d", label: "3D" },
  { id: "top", label: "Top" },
  { id: "meridional", label: "Meridional" },
  { id: "s_q", label: "S-Q" },
  { id: "quad", label: "Quad" },
];

export const ANNOTATION_LEVELS = ["key", "selected", "all"];

export function resolveParameterInspection(manifest) {
  if (!manifest) {
    return { status: "empty", errorCode: "parameter_inspection_not_generated" };
  }

  const contract = manifest.parameter_inspection;
  const surfaceGraph = manifest.geometry?.surface_graph;
  if (contract?.contract_version !== "1.1.3") {
    return { status: "error", errorCode: "parameter_inspection_contract_unsupported" };
  }
  if (!surfaceGraph || contract.generation_id !== surfaceGraph.generation_id || contract.generation_id !== manifest.generation_id) {
    return { status: "error", errorCode: "parameter_inspection_generation_id_mismatch" };
  }

  const graphSurfaceIds = new Set((surfaceGraph.surfaces || []).map((surface) => surface.id));
  const contractSurfaceIds = Object.keys(contract.surface_references || {});
  if (contractSurfaceIds.some((surfaceId) => !graphSurfaceIds.has(surfaceId))) {
    return { status: "error", errorCode: "parameter_inspection_surface_reference_missing" };
  }

  const loops = contract.section_loops || {};
  if (Object.values(contract.span_stations || {}).some((station) => !loops[station.section_loop_id])) {
    return { status: "error", errorCode: "parameter_inspection_station_reference_missing" };
  }

  return {
    status: "ready",
    errorCode: null,
    contract,
    surfaceGraph,
    indices: {
      blades: contract.blade_instances || {},
      surfaces: contract.surface_references || {},
      stations: contract.span_stations || {},
      loops,
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

export function mergeInspectionSelection(selection, patch) {
  return { ...selection, ...patch };
}

export function sectionLoopForSelection(model, selection) {
  const station = model.indices?.stations?.[selection.spanStationId];
  return station ? model.indices.loops?.[station.section_loop_id] || null : null;
}

export function annotationsForView(model, viewId, level, selection) {
  if (model.status !== "ready") {
    return [];
  }

  const annotations = annotationsForViewId(model, viewId, selection);
  if (level === "key") {
    return annotations.filter((annotation) => annotation.level === "key");
  }
  if (level === "selected") {
    return annotations.filter((annotation) => annotation.level === "key" || annotationMatchesSelection(annotation, selection));
  }
  return level === "all" ? annotations : [];
}

function annotationsForViewId(model, viewId, selection) {
  switch (viewId) {
    case "3d":
      return surfaceAnnotations(model, "3d");
    case "top":
      return surfaceAnnotations(model, "top");
    case "meridional":
      return stationAnnotations(model);
    case "s_q":
      return sectionAnnotations(model, selection);
    case "quad":
      return joinAnnotations(model, selection);
    default:
      return [];
  }
}

function surfaceAnnotations(model, viewId) {
  return Object.values(model.indices.surfaces).map((surface) =>
    annotation({
      id: `${viewId}:${surface.surface_id}`,
      level: "all",
      label: titleCase(surface.face_family || "surface"),
      requestedValue: surface.face_family || null,
      resolvedValue: surface.surface_id,
      anchor: { kind: "surface", surfaceId: surface.surface_id },
      selection: { bladeId: surface.blade_instance_id, surfaceId: surface.surface_id },
    }),
  );
}

function stationAnnotations(model) {
  return Object.values(model.indices.stations).map((station) =>
    annotation({
      id: `meridional:${station.span_station_id}`,
      level: "all",
      label: "Span station",
      requestedValue: station.h,
      resolvedValue: station.h,
      anchor: { kind: "span_station", spanStationId: station.span_station_id },
      selection: { spanStationId: station.span_station_id },
    }),
  );
}

function sectionAnnotations(model, selection) {
  const loop = sectionLoopForSelection(model, selection);
  const dimensions = Object.entries(model.contract.resolved_dimensions || {}).map(([dimensionId, dimension]) =>
    annotation({
      id: `s_q:${dimensionId}`,
      level: "key",
      label: titleCase(dimensionId.replace(/_mm$/, "")),
      requestedValue: dimension.requested_value,
      resolvedValue: dimension.resolved_value,
      unit: dimension.unit,
      requestedUnit: dimension.requested_unit,
      anchor: { kind: "section_loop", sectionLoopId: loop?.section_loop_id || null },
    }),
  );
  if (!loop) {
    return dimensions;
  }

  const segments = Object.entries(loop.segment_references || {}).map(([segmentId, segment]) =>
    annotation({
      id: `s_q:${loop.section_loop_id}:${segmentId}`,
      level: "all",
      label: titleCase(segmentId),
      requestedValue: segment.points_s_q,
      resolvedValue: segment.control_points_s_q,
      anchor: { kind: "section_segment", sectionLoopId: loop.section_loop_id, sectionSegmentId: segmentId },
      selection: { spanStationId: loop.span_station_id, sectionSegmentId: segmentId },
    }),
  );
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

function annotation({ id, level, label, requestedValue, resolvedValue, unit = "", requestedUnit = unit, anchor, selection = null, metrics = null }) {
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
  };
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
