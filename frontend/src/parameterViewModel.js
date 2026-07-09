function clonePlainObject(value) {
  return value ? JSON.parse(JSON.stringify(value)) : {};
}

function topAnnotations(canonical) {
  const population = canonical?.blade_population || {};
  return [
    { kind: "population", label: "Main blades", value: population.main_blade_count ?? "unset" },
    { kind: "population", label: "Splitter blades", value: population.splitter_blade_count ?? "unset" },
    { kind: "population", label: "Splitter fraction", value: population.splitter_passage_fraction ?? "unset" },
  ];
}

function meridionalAnnotations(canonical) {
  const profiles = canonical?.support_profiles || {};
  const rootOffset = canonical?.active_span_policy?.root_offset?.resolved_constant_mm;
  const tipOffset = canonical?.active_span_policy?.tip_offset?.resolved_constant_mm;
  return [
    { kind: "support_profile", label: "Hub controls", value: profiles.hub_profile?.control_points?.length ?? "unset" },
    { kind: "support_profile", label: "Tip controls", value: profiles.tip_or_shroud_profile?.control_points?.length ?? "unset" },
    { kind: "span_policy", label: "Root offset (mm)", value: rootOffset ?? "unset" },
    { kind: "span_policy", label: "Tip offset (mm)", value: tipOffset ?? "unset" },
  ];
}

function bladeToBladeAnnotations(canonical) {
  const loopFamily = canonical?.section_loop_family || {};
  return [
    { kind: "loop_family", label: "Loop mode", value: loopFamily.mode ?? "unset" },
    { kind: "loop_family", label: "Span stations", value: loopFamily.span_stations_h?.length ?? "unset" },
  ];
}

function spanAnnotations(canonical) {
  const spanStations = canonical?.section_loop_family?.span_stations_h || [];
  return [
    { kind: "span_station", label: "Stations", value: spanStations.length || "unset" },
    { kind: "span_station", label: "Values", value: spanStations.length > 0 ? spanStations.join(", ") : "unset" },
  ];
}

export function resolvedCanonicalParameterization(activePreset, manifest) {
  const manifestCanonical = manifest?.geometry?.surface_graph?.canonical_nurbs_parameterization;
  if (manifestCanonical?.canonical_payload_version === "1.1.2") {
    return { sourceLabel: "resolved manifest", canonical: clonePlainObject(manifestCanonical) };
  }
  return {
    sourceLabel: "preset defaults",
    canonical: clonePlainObject(activePreset?.canonicalNurbsParameterization || {}),
  };
}

export function parameterViewTabs(activePreset, manifest) {
  const { canonical, sourceLabel } = resolvedCanonicalParameterization(activePreset, manifest);
  return [
    { id: "top", label: "Top", sourceLabel, annotations: topAnnotations(canonical) },
    { id: "meridional", label: "Meridional", sourceLabel, annotations: meridionalAnnotations(canonical) },
    { id: "blade_to_blade", label: "S-Q", sourceLabel, annotations: bladeToBladeAnnotations(canonical) },
    { id: "span_station", label: "Span", sourceLabel, annotations: spanAnnotations(canonical) },
  ];
}
