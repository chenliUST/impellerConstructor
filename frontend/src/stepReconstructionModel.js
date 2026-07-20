export const stepAuditStages = [
  "uploaded", "brep_loaded", "frame_resolved", "semantics_classified", "parameters_extracted",
  "hub_reconstructed", "blade_surfaces_reconstructed", "edge_closures_reconstructed", "comparison_preprocessing", "deviation_measured", "complete",
];

export const stepOverlayOptions = [
  { id: "axis", label: "Axis" },
  { id: "hub", label: "Hub" },
  { id: "tipSupport", label: "Tip/shroud" },
  { id: "spanSurfaces", label: "Active blade lattice" },
  { id: "representativeBlade", label: "Blade" },
  { id: "selectedLoop", label: "Source loop" },
  { id: "openTipReference", label: "Open tip reference" },
];

export const defaultStepOverlayVisibility = Object.freeze({
  axis: true, hub: true, tipSupport: true, spanSurfaces: false, representativeBlade: true,
  selectedLoop: true, openTipReference: false,
});

export function auditStageRows(status) {
  const completed = new Set(asArray(status?.completed_stages));
  return stepAuditStages.map((id) => ({
    id,
    label: id.replaceAll("_", " "),
    state: status?.status === "FAILED" && status.current_stage === id ? "failed"
      : completed.has(id) ? "complete" : status?.current_stage === id ? "active" : "pending",
  }));
}

export function auditProgressLabel(status) {
  const progress = asRecord(status?.progress);
  const phase = String(progress.phase || status?.current_stage || "STEP").replaceAll("_", " ");
  const detail = String(progress.detail || "").replaceAll("_", " ");
  const fraction = finite(progress.fraction_complete)
    ? `${Math.round(Number(progress.fraction_complete) * 100)}%`
    : "";
  return [phase, detail, fraction].filter(Boolean).join(" / ");
}

export function auditArtifactUrls(apiBase, auditId, manifest = null) {
  if (!auditId) return {};
  const root = `${String(apiBase || "").replace(/\/+$/, "")}/api/step-reconstruction-audits/${encodeURIComponent(auditId)}/artifacts`;
  const urls = {
    source: `${root}/source.stl`,
    reconstruction: `${root}/reconstruction.stl`,
    heatmap: `${root}/heatmap.json`,
  };
  if (asRecord(manifest?.artifacts).geometric_manifest) {
    urls.geometricManifest = `${root}/geometric-manifest.json`;
  }
  return urls;
}

export function comparisonViewportRects(width, height) {
  const w = Math.max(0, Math.floor(Number(width) || 0));
  const h = Math.max(0, Math.floor(Number(height) || 0));
  const left = Math.floor(w / 2);
  const bottom = Math.floor(h / 2);
  return {
    source: { x: 0, y: bottom, width: left, height: h - bottom },
    reconstruction: { x: left, y: bottom, width: w - left, height: h - bottom },
    heatmap: { x: 0, y: 0, width: left, height: bottom },
  };
}

export function heatmapLegend(manifest) {
  const metrics = asRecord(
    manifest?.comparison?.reconstruction_to_corresponding_source,
  );
  return [["Triangle-centroid min", metrics.minimum_mm], ["Triangle-centroid median", metrics.median_mm], ["Triangle-centroid P95", metrics.p95_mm], ["Triangle-centroid max", metrics.maximum_mm]]
    .filter(([, value]) => finite(value)).map(([label, value]) => ({ label, value }));
}

export function parameterDifferenceRows(manifest) {
  const reconstructed = asRecord(manifest?.reconstruction?.parameters);
  return asRecords(manifest?.parameter_mapping?.parameter_rows).map((row) => {
    const parameterId = String(row.feature_id || "").replace(/^parameter_values\./, "");
    const rebuilt = reconstructed[parameterId];
    return { ...row, parameter_id: parameterId, reconstructed_value: rebuilt,
      delta: finite(row.source_measurement) && finite(rebuilt) ? Number(rebuilt) - Number(row.source_measurement) : null };
  });
}

export function terminalAuditStatus(status) { return status?.status === "PASS" || status?.status === "FAILED"; }
export function auditInProgress(status) { return ["UPLOADING", "QUEUED", "RUNNING"].includes(status?.status); }

export function stepInspectionModel(manifest, selection = {}) {
  const root = asRecord(manifest);
  const mapping = asRecord(root.parameter_mapping);
  const overlay = asRecord(root.section_overlay_contract);
  const sourceOverlay = asRecord(overlay.source);
  const generatedOverlay = asRecord(overlay.generated);
  const axisFirst = asRecord(root.axis_first_section_reconstruction);
  const support = asRecord(mapping.support_recovery);
  const periodic = asRecord(mapping.periodic_provenance);
  const overlaySourceLoops = sourceOverlay.status === "AVAILABLE" ? asRecords(sourceOverlay.stations) : [];
  const loops = overlaySourceLoops.length ? overlaySourceLoops : asRecords(mapping.source_section_loops);
  const generatedLoops = generatedOverlay.status === "AVAILABLE" ? asRecords(generatedOverlay.stations) : [];
  const populations = populationOptions(periodic, asRecord(root.semantics), loops, axisFirst);
  const requestedPopulation = selection.populationId || populations[0]?.id || "main";
  const populationId = populations.some((population) => population.id === requestedPopulation) ? requestedPopulation : requestedPopulation;
  const stations = stationsForPopulation(loops, populationId);
  const requestedStation = selection.spanStationId || stations[0]?.id || "";
  const selectedLoop = selectLoop(loops, populationId, requestedStation);
  const generatedLoop = selectLoop(generatedLoops, populationId, requestedStation);
  const selectedMappingTerms = mappingTermsForSelection(mapping.objective_terms, { populationId, spanStationId: requestedStation, selectedLoop });
  const topology = topologyDecision(support);
  const activeSupport = support;
  const unavailableReason = selectedLoop ? null : stationUnavailableReason(loops, populationId, requestedStation);
  return {
    auditId: root.audit_id || "",
    comparisonPhaseDeg: finite(root?.comparison_alignment?.rotation_about_axis_deg)
      ? Number(root.comparison_alignment.rotation_about_axis_deg)
      : 0,
    reconstructionVariant: String(
      asRecord(root.reconstruction).reconstruction_variant || "V1.1.2"
    ),
    axis: asRecord(root.frame).axis || asRecord(axisFirst.canonical_frame).axis || null,
    support: activeSupport,
    supportGeometry: supportOverlayEvidence(activeSupport, topology),
    topology,
    hasMaterialShroud: topology === "closed",
    populations,
    populationId,
    stations,
    spanStationId: requestedStation,
    selectedLoop,
    sourceSectionLoop: selectedLoop,
    generatedSectionLoop: generatedLoop,
    sectionOverlayStatus: {
      contractId: overlay.contract_id || null,
      source: sourceOverlay.status || (selectedLoop ? "LEGACY_SOURCE_ONLY" : "UNAVAILABLE"),
      generated: generatedOverlay.status || "UNAVAILABLE",
    },
    selectedMappingTerms,
    representative: representativeForPopulation(periodic, populationId, axisFirst, generatedLoops),
    regionalDeviation: regionalDeviationRecords(root),
    selectionEvidence: selectedLoop
      ? { state: "available", message: `Exact source loop bound to ${populationId} / ${requestedStation}.` }
      : { state: "unavailable", message: unavailableReason },
    metricRows: inspectionMetricRows({ support: activeSupport, selectedLoop, selectedMappingTerms }),
    attachmentRows: attachmentReportRows(root),
  };
}

export function semanticRegionOptions(manifest) {
  const seen = new Set();
  const regions = regionalDeviationRecords(asRecord(manifest)).map((record) => {
    const aliases = regionAliases(record);
    return { id: aliases[0], label: record.label || record.semantic_role || record.semantic_region || aliases[0], aliases };
  }).filter((record) => record.id && !seen.has(record.id) && seen.add(record.id));
  return [{ id: "all", label: "All regions", aliases: ["all"] }, ...regions];
}

export function selectedLoopAlignmentMetadata(model) {
  const loop = asRecord(model?.selectedLoop);
  return {
    population: model?.populationId || null,
    span_station_id: stationId(loop) || model?.spanStationId || null,
    representative_source_component_id: loop.representative_source_component_id || loop.source_instance_id || model?.representative?.representative_component_id || model?.representative?.source_component_id || null,
    source_face_ids: sourceFaceIds(loop),
  };
}

export function selectedInspectionProvenance(model) {
  const loop = asRecord(model?.selectedLoop);
  const terms = asRecords(model?.selectedMappingTerms);
  const ids = new Set(sourceFaceIds(loop));
  terms.forEach((term) => sourceFaceIds(term).forEach((id) => ids.add(id)));
  return {
    ...selectedLoopAlignmentMetadata(model),
    loop_id: loop.loop_id || loop.source_loop_id || null,
    source_face_ids: [...ids].sort(),
    coordinate_frame: unique(terms.map(mappingCoordinateFrame).concat([loop.coordinate_frame, asRecord(loop.exact_section).coordinate_frame])).join(", ") || null,
    measurement_method: unique(terms.map(mappingMethod).concat([loop.measurement_method, asRecord(loop.exact_section).method])).join(", ") || null,
    mapping_term_count: terms.length,
  };
}

export function reportSummaryRows(manifest, inspection) {
  const source = asRecord(manifest?.source);
  const semantics = asRecord(manifest?.semantics);
  const comparison = asRecord(
    manifest?.comparison?.reconstruction_to_corresponding_source,
  );
  const alignment = asRecord(manifest?.comparison_alignment);
  const comparisonScope = asRecord(manifest?.comparison_scope);
  const periodic = asRecord(manifest?.parameter_mapping?.periodic_provenance);
  const acceptance = asRecord(manifest?.acceptance_evaluation);
  const globalPromotable = manifest?.promotable;
  return [
    { id: "audit_process", label: "Audit process (not acceptance)", value: display(manifest?.process_status || manifest?.status) },
    { id: "geometry_status", label: "Geometry status", value: display(manifest?.geometry_status) },
    { id: "algorithm_status", label: "Axis-first algorithm", value: display(manifest?.axis_first_algorithm_status) },
    { id: "reconstruction_disposition", label: "Reconstruction disposition", value: display(manifest?.reconstruction_disposition) },
    { id: "global_promotability", label: "Global promotability", value: globalPromotable === true ? "PROMOTABLE" : globalPromotable === false ? "NOT PROMOTABLE" : "Unavailable" },
    { id: "acceptance_status", label: "Acceptance contract", value: `${display(acceptance.status)} / ${display(acceptance.contract)}` },
    { id: "source_topology", label: "Source topology", value: `${display(source.solid_count)} solid / ${display(source.face_count)} faces / ${display(source.edge_count)} edges` },
    { id: "blade_population", label: "Blade population", value: `${display(semantics.main_blade_count, 0)} main + ${display(semantics.splitter_blade_count, 0)} splitter` },
    { id: "geometry_authority", label: "Geometry authority", value: display(manifest?.canonical_geometry_version) },
    { id: "support_topology", label: "Support topology", value: display(inspection?.topology) },
    {
      id: "comparison_scope",
      label: "Corresponding-surface scope",
      value: `${display(comparisonScope.status)}${asArray(comparisonScope.missing_required_roles).length ? ` / missing ${asArray(comparisonScope.missing_required_roles).join(", ")}` : ""}`,
    },
    { id: "periodic_provenance", label: "Periodic provenance", value: periodicSummary(periodic) },
    { id: "periodic_phase", label: "Periodic phase alignment", value: `${number(alignment.rotation_about_axis_deg)} deg about confirmed axis` },
    { id: "phase_rms", label: "Phase-search RMS", value: `${number(alignment.objective_rms_before_mm)} -> ${number(alignment.objective_rms_after_mm)} mm` },
    { id: "rms", label: "Triangle-centroid RMS reconstruction -> source", value: `${number(comparison.rms_mm)} mm` },
    { id: "p95", label: "Triangle-centroid P95 reconstruction -> source", value: `${number(comparison.p95_mm)} mm` },
  ];
}

function periodicSummary(periodic) {
  if (periodic.collision_status === "UNKNOWN") return "TOPOLOGY PASS / COLLISION UNKNOWN";
  if (periodic.collision_status === "FAIL") return "COLLISION FAIL";
  return display(periodic.status || periodic.method || periodic.population_count);
}

export function unsupportedSourceFeatures(manifest) {
  const scoped = asRecords(manifest?.comparison_scope?.excluded_surfaces).map((record) => ({
    ...record,
    feature: record.feature || record.semantic_role || record.source_role_hint || record.reason,
  }));
  const legacy = asRecords(manifest?.parameter_mapping?.unsupported_source_features);
  const records = [...scoped, ...legacy];
  const seen = new Set();
  return records.filter((record, index) => {
    const key = record.source_face_id || record.feature || `unsupported-${index}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function attachmentReportRows(manifest) {
  const mapping = asRecord(manifest?.parameter_mapping);
  const measurement = asRecord(asRecord(asRecord(mapping.measurement_bundle).attachments).root);
  const term = asRecord(asRecord(mapping.objective_terms).attachment);
  const record = asRecords(term.records).find((candidate) => candidate.attachment === "root") || {};
  if (!Object.keys(measurement).length && !Object.keys(record).length) return [];
  const provenanceIds = unique([sourceIds(record), sourceIds(measurement), sourceIds(term)]);
  const frame = asRecord(record.frame || term.frame);
  const provenance = asRecord(record.provenance || term.provenance);
  const promotion = asRecord(mapping.promotion);
  const maximumRelative = maximumFinite([record.lift_relative, record.width_relative, asRecord(term.residual).maximum_relative]);
  return [{
    id: "root",
    label: "Root attachment",
    measured_lift_mm: firstFinite(record.target_lift_mm, median(measurement.lift_samples_mm)),
    fitted_lift_mm: firstFinite(record.fitted_lift_mm),
    measured_width_mm: firstFinite(record.target_width_mm, median(measurement.width_samples_mm)),
    fitted_width_mm: firstFinite(record.fitted_width_mm),
    maximum_relative_residual: maximumRelative,
    status: record.status || asRecord(term.gate).status || "--",
    promotable: measurement.promotable ?? record.promotable ?? promotion.promotable ?? null,
    source_ids: provenanceIds.sort(),
    method: record.method || term.method || provenance.method || null,
    coordinate_frame: frame.coordinate_system || frame.coordinate_frame || record.coordinate_frame || term.coordinate_frame || null,
    provenance,
  }];
}

export function inspectionPolylinePoints(evidence) {
  const record = asRecord(evidence);
  const exactLoop = asRecord(asRecord(record.exact_section).accepted_loop);
  for (const points of [exactLoop.points_xyz_mm, record.points_xyz_mm, record.points_mm, record.points, record.loop_points_mm, record.polyline_points_mm, record.curve_points_mm]) {
    if (Array.isArray(points)) return points.filter(validPoint);
  }
  return [];
}

export function heatmapTriangleSelection(payload, semanticRegion, aliases = []) {
  const root = asRecord(payload);
  const triangles = asArray(root.triangles);
  const all = triangles.map((_, index) => index);
  if (!semanticRegion || semanticRegion === "all") return { indexes: all, mode: "all", filterable: true, message: "Showing all heatmap triangles." };
  const requested = new Set(unique([semanticRegion, ...asArray(aliases)]));
  const membership = firstArray(root, ["triangle_source_region_ids", "triangle_region_ids", "triangle_regions", "triangle_metadata"]);
  if (membership?.some(hasRegionMembership)) return filterResult(membership.slice(0, triangles.length).flatMap((value, index) => membershipMatches(value, requested) ? [index] : []), semanticRegion, "triangle metadata", all);
  const regions = [root.regions, root.regional_records, root.semantic_regions].find(Array.isArray);
  const record = asRecords(regions).find((candidate) => regionAliases(candidate).some((id) => requested.has(id)));
  const indexes = firstArray(record, ["triangle_indices", "triangle_indexes", "triangleIndexes", "triangles"]);
  if (indexes) return filterResult(indexes.filter((index) => Number.isInteger(index) && index >= 0 && index < triangles.length), semanticRegion, "regional records", all);
  if (triangles.some((triangle) => membershipRegionAliases(asRecord(triangle)).length)) return filterResult(triangles.flatMap((triangle, index) => membershipRegionAliases(asRecord(triangle)).some((id) => requested.has(id)) ? [index] : []), semanticRegion, "triangle records", all);
  return { indexes: all, mode: "evidence-only", filterable: false, message: `${semanticRegion} is evidence-only; this heatmap artifact has no triangle-to-region membership and cannot be filtered.` };
}

function populationOptions(periodic, semantics, loops, axisFirst) {
  const records = populationRecords(periodic);
  const fromRecords = records.map(({ id, record }) => ({ id, label: record.label, count: record.count }));
  const ids = unique([...fromRecords.map((record) => record.id), ...loops.map(populationOf)]);
  const legacy = asRecord(axisFirst.periodic_populations);
  return (ids.length ? ids : ["main", ...(Number(semantics.splitter_blade_count || legacy.splitter_optional?.count) > 0 ? ["splitter"] : [])])
    .map((id) => {
      const record = fromRecords.find((candidate) => candidate.id === id);
      const count = record?.count ?? (id === "splitter" ? semantics.splitter_blade_count ?? legacy.splitter_optional?.count : semantics.main_blade_count ?? legacy.main?.count ?? 0);
      return { id, label: record?.label || `${id === "main" ? "Main" : "Splitter"} (${count})`, count };
    });
}

function stationsForPopulation(loops, populationId) {
  const seen = new Set();
  return loops.filter((loop) => populationOf(loop) === populationId).map((loop) => {
    const h = stationSpanValue(loop);
    return { ...loop, id: stationId(loop), h, label: `h ${span(h)}` };
  })
    .filter((station) => station.id && !seen.has(station.id) && seen.add(station.id));
}

function selectLoop(loops, populationId, requestedStation) {
  return loops.find((loop) => populationOf(loop) === populationId && stationId(loop) === String(requestedStation)) || null;
}

function stationUnavailableReason(loops, populationId, station) {
  if (!station) return `No exact source-section station is available for ${populationId}.`;
  if (!loops.some((loop) => populationOf(loop) === populationId)) return `No exact source-section evidence is available for population ${populationId}.`;
  return `Station ${station} has no exact source-loop evidence for population ${populationId}; no fallback loop was selected.`;
}

function topologyDecision(support) {
  if (support.status !== "PASS") return "undetermined";
  const topology = asRecord(support.topology);
  if (topology.status !== "PASS") return "undetermined";
  return topology.decision || topology.mode || "undetermined";
}

function representativeForPopulation(periodic, populationId, axisFirst, loops) {
  const match = populationRecords(periodic).find((candidate) => candidate.id === populationId)?.record;
  if (match) return { ...match, ...asRecord(match.representative_instance), section_loops: loops.filter((loop) => populationOf(loop) === populationId) };
  const legacy = asRecord(axisFirst.periodic_populations);
  const record = populationId === "splitter" ? asRecord(legacy.splitter_optional) : asRecord(legacy.main);
  return { ...record, section_loops: loops.filter((loop) => populationOf(loop) === populationId) };
}

function populationRecords(periodic) {
  const records = asRecords(periodic.populations).map((record) => ({ id: populationOf(record), record }));
  for (const id of ["main", "splitter"]) {
    const record = asRecord(periodic[id]);
    if (Object.keys(record).length && !records.some((candidate) => candidate.id === id)) records.push({ id, record });
  }
  return records.filter((candidate) => candidate.id);
}

function supportOverlayEvidence(support, topology) {
  const tip = asRecord(support.tip_reference_or_shroud);
  const hub = supportProfileFit(support.hub_profile);
  if (topology === "closed") {
    return {
      hub,
      openTip: null,
      closedShroud: [supportProfileFit(asRecord(tip.inner_flowpath).profile_fit), supportProfileFit(asRecord(tip.outer_material).profile_fit)].filter(Boolean),
    };
  }
  return { hub, openTip: supportProfileFit(tip.profile_fit || tip), closedShroud: [] };
}

function supportProfileFit(value) {
  const record = asRecord(value);
  const fit = asRecord(record.profile_fit);
  const candidate = Object.keys(fit).length ? fit : record;
  return supportProfilePoints(candidate).length >= 2 ? candidate : null;
}

function supportProfilePoints(record) {
  for (const points of [record?.control_points_rz_mm, record?.points_rz_mm, record?.profile_rz_mm]) if (Array.isArray(points)) return points;
  return [];
}

function mappingTermsForSelection(objectiveTerms, selection) {
  return flattenObjectiveTerms(objectiveTerms).filter((term) => termMatches(term, selection));
}

function flattenObjectiveTerms(terms) {
  const roots = Array.isArray(terms) ? terms.map((term) => [null, term]) : Object.entries(asRecord(terms));
  return roots.flatMap(([role, value]) => {
    const term = asRecord(value);
    const inherited = { ...term, mapping_role: term.mapping_role || role };
    const records = asRecords(term.records);
    return records.length ? records.map((record) => ({ ...inherited, ...record, mapping_role: record.mapping_role || inherited.mapping_role, source_face_ids: sourceFaceIds(record).length ? sourceFaceIds(record) : sourceFaceIds(inherited) })) : [inherited];
  });
}

function termMatches(term, { populationId, spanStationId, selectedLoop }) {
  const population = populationOf(term);
  if (population && population !== populationId) return false;
  const termLoop = String(term.loop_id || term.source_loop_id || term.section_loop_id || "");
  const selectedLoopId = String(selectedLoop?.loop_id || selectedLoop?.source_loop_id || "");
  if (termLoop) return Boolean(selectedLoopId) && termLoop === selectedLoopId;
  return Boolean(selectedLoop) && stationId(term) === String(spanStationId);
}

function inspectionMetricRows({ support, selectedLoop, selectedMappingTerms }) {
  const thickness = asRecord(selectedLoop?.normal_thickness || selectedLoop?.thickness_measurement || selectedLoop?.thickness);
  const thicknessTerms = selectedMappingTerms.filter((term) => /thickness/i.test(String(term.mapping_role || "")));
  return [
    { id: "measured_thickness", label: "Measured thickness", value: firstMetric(thickness, ["mean_mm", "measured_mm", "median_mm", "value_mm"]) },
    { id: "fitted_thickness", label: "Fitted thickness", value: average(thicknessTerms, ["fitted", "fitted_mm"]) },
    { id: "mapping_residual", label: "Mapping residual RMS", value: rms(thicknessTerms, ["residual", "residual_mm"]) },
    { id: "support_residual", label: "Support residual", value: firstMetric(asRecord(support.hub_profile).residual || asRecord(support.tip_reference_or_shroud).residual, ["rms_mm", "orthogonal_rms_mm"]), state: support.status },
  ].filter((row) => row.value !== null || row.state);
}

function regionalDeviationRecords(manifest) {
  const mappingRegions = asRecord(manifest.parameter_mapping?.regional_deviation).regions;
  const axisRegions = asRecord(manifest.axis_first_section_reconstruction?.regional_deviation).regions;
  const candidates = [mappingRegions, axisRegions, manifest.comparison?.regions];
  for (const candidate of candidates) {
    const records = normalizedRegionRecords(candidate);
    if (records.length) return records;
  }
  return [];
}
function populationOf(record) { return String(record?.population || record?.family || record?.blade_population || record?.population_id || ""); }
function stationId(record) { const value = record?.span_station_id ?? record?.station_id ?? record?.active_h ?? record?.h ?? record?.span_fraction; return value === undefined || value === null ? "" : String(value); }
function stationSpanValue(record) { return record?.active_h ?? record?.h ?? record?.span_fraction ?? record?.support_span_h; }
function span(value) { return finite(value) ? Number(value).toFixed(2) : "--"; }
function firstMetric(record, keys) { for (const key of keys) if (finite(record?.[key])) return Number(record[key]); return null; }
function average(records, keys) { const values = records.map((record) => firstMetric(record, keys)).filter((value) => value !== null); return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null; }
function rms(records, keys) { const values = records.map((record) => firstMetric(record, keys)).filter((value) => value !== null); return values.length ? Math.sqrt(values.reduce((sum, value) => sum + value ** 2, 0) / values.length) : null; }
function regionAliases(record) { return unique([record.source_region_id, record.region_id, record.semantic_role, record.semantic_region, record.region, record.id]); }
function membershipMatches(value, requested) { return isRecord(value) ? membershipRegionAliases(value).some((id) => requested.has(id)) : requested.has(String(value)); }
function hasRegionMembership(value) { return isRecord(value) ? membershipRegionAliases(value).length > 0 : value !== null && value !== undefined && String(value) !== ""; }
function membershipRegionAliases(record) { const metadata = asRecord(record.metadata); const provenance = asRecord(record.provenance); return unique([record.source_region_id, record.region_id, record.semantic_role, record.semantic_region, record.region, metadata.source_region_id, metadata.region_id, metadata.semantic_role, provenance.source_region_id, provenance.region_id]); }
function filterResult(indexes, semanticRegion, source, all) {
  if (!indexes.length) return { indexes: all, mode: "evidence-only", filterable: false, message: `${semanticRegion} has comparison evidence but no matching heatmap triangles.` };
  return { indexes, mode: "filtered", filterable: true, message: `${semanticRegion} filtered by ${source} (${indexes.length} triangles).` };
}
function normalizedRegionRecords(value) {
  if (Array.isArray(value)) return asRecords(value);
  return Object.entries(asRecord(value)).map(([id, record]) => ({
    region_id: id,
    semantic_role: id,
    ...asRecord(record),
  }));
}
function firstArray(record, keys) { for (const key of keys) if (Array.isArray(record?.[key])) return record[key]; return null; }
function mappingCoordinateFrame(term) { const frame = asRecord(term.frame); return term.coordinate_frame || term.coordinate_system || frame.coordinate_frame || frame.coordinate_system || null; }
function mappingMethod(term) { return term.measurement_method || term.method || asRecord(term.fit_evidence).method || null; }
function sourceIds(record) {
  const value = asRecord(record);
  const provenance = asRecord(value.provenance);
  return unique([value.source_ids, value.source_face_ids, value.source_edge_ids, value.source_entity_ids, provenance.source_ids, provenance.source_face_ids, provenance.source_entity_ids]);
}
function sourceFaceIds(record) { return sourceIds(record); }
function validPoint(point) { return Array.isArray(point) && point.length >= 3 && point.slice(0, 3).every(finite); }
function finite(value) { return value !== null && value !== "" && value !== undefined && Number.isFinite(Number(value)); }
function firstFinite(...values) { const value = values.find(finite); return value === undefined ? null : Number(value); }
function maximumFinite(values) { const finiteValues = values.filter(finite).map(Number); return finiteValues.length ? Math.max(...finiteValues) : null; }
function median(values) { const numbers = asArray(values).filter(finite).map(Number).sort((a, b) => a - b); if (!numbers.length) return null; const middle = Math.floor(numbers.length / 2); return numbers.length % 2 ? numbers[middle] : 0.5 * (numbers[middle - 1] + numbers[middle]); }
function number(value) { return finite(value) ? Number(value).toFixed(Math.abs(Number(value)) >= 100 ? 1 : 3) : "--"; }
function display(value, fallback = "--") { return value === undefined || value === null || value === "" ? fallback : String(value); }
function unique(values) { return [...new Set(asArray(values).flat().filter((value) => value !== undefined && value !== null && String(value)).map(String))]; }
function asArray(value) { return Array.isArray(value) ? value : []; }
function asRecords(value) { return asArray(value).filter(isRecord); }
function asRecord(value) { return isRecord(value) ? value : {}; }
function isRecord(value) { return Boolean(value) && typeof value === "object" && !Array.isArray(value); }
