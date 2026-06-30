const CFD_HIDDEN_ROLES = new Set([
  "construction_support_only",
  "reference_only",
  "mounting_bore",
  "shaft_seat",
  "keyway",
  "rear_hub_groove",
]);

export function viewModeOptions() {
  return [
    { id: "cad_review_360", label: "CAD review" },
    { id: "cfd_full_360", label: "CFD full 360" },
    { id: "feature_debug", label: "Feature debug" },
  ];
}

export function surfaceVisibleInView(surface, viewMode) {
  if (viewMode !== "cfd_full_360") {
    return true;
  }
  return ![surface?.role, surface?.cfd_role, surface?.kind, surface?.assembly_role].some((role) =>
    CFD_HIDDEN_ROLES.has(role),
  );
}

export function cfdPatchGroups(manifest) {
  const groups = cfdFull360Manifest(manifest)?.patch_groups || {};
  return Object.entries(groups)
    .map(([id, value]) => ({ id, ...value }))
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function cfdPatchInstances(manifest) {
  const instances = cfdFull360Manifest(manifest)?.patch_instances || {};
  return Object.entries(instances)
    .map(([id, value]) => ({ id, ...value }))
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function patchSurfaceIds(manifest, selectedPatch) {
  const cfd = cfdFull360Manifest(manifest);
  const group = cfd?.patch_groups?.[selectedPatch];
  const instances = cfd?.patch_instances || {};
  const surfaceIds = new Set();

  for (const instanceId of group?.instances || []) {
    const metadata = instances[instanceId] || {};
    const surfaceId =
      metadata.surface_graph_id ||
      metadata.source_id ||
      (metadata.source_type === "surface" ? unscopedInstanceId(instanceId) : null) ||
      (!metadata.source_type && !metadata.boundary_curve_id ? unscopedInstanceId(instanceId) : null);
    if (surfaceId) {
      surfaceIds.add(surfaceId);
    }
  }

  return surfaceIds;
}

function cfdFull360Manifest(manifest) {
  return manifest?.simulation_manifests?.cfd_full_360;
}

function unscopedInstanceId(instanceId) {
  const segments = String(instanceId || "").split(":");
  return segments[segments.length - 1];
}
