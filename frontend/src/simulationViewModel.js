const CFD_HIDDEN_ROLES = new Set([
  "construction_support_only",
  "reference_only",
  "mounting_bore",
  "shaft_seat",
  "keyway",
  "rear_hub_groove",
]);
const CFD_SURFACE_VIEWS = new Set(["cfd_full_360", "mesh"]);

export function viewModeOptions() {
  return [
    { id: "cad_review_360", label: "CAD review" },
    { id: "cfd_full_360", label: "CFD full 360" },
    { id: "mesh", label: "CFD360 mesh" },
    { id: "feature_debug", label: "Feature debug" },
  ];
}

export function surfaceVisibleInView(surface, viewMode, manifest = null) {
  if (!CFD_SURFACE_VIEWS.has(viewMode)) {
    return true;
  }
  if ([surface?.role, surface?.cfd_role, surface?.kind, surface?.assembly_role].some((role) => CFD_HIDDEN_ROLES.has(role))) {
    return false;
  }
  if (viewMode === "mesh" && (surface?.transition_policy_id || surface?.edge_family)) {
    return true;
  }
  const patchSurfaceIds = cfdPatchSurfaceIds(manifest);
  if (patchSurfaceIds.size > 0) {
    return patchSurfaceIds.has(surface?.id || surface?.surface_graph_id);
  }
  return Boolean(surface?.cfd_role);
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

export function patchBoundaryCurveIds(manifest, selectedPatch) {
  const cfd = cfdFull360Manifest(manifest);
  const group = cfd?.patch_groups?.[selectedPatch];
  const instances = cfd?.patch_instances || {};
  const boundaryIds = new Set();

  for (const instanceId of group?.instances || []) {
    const metadata = instances[instanceId] || {};
    const boundaryId =
      metadata.boundary_curve_id ||
      (metadata.source_type === "boundary_curve" ? unscopedInstanceId(instanceId) : null);
    if (boundaryId) {
      boundaryIds.add(boundaryId);
    }
  }

  return boundaryIds;
}

export function cfdPatchSurfaceIds(manifest) {
  const surfaceIds = new Set();
  for (const instance of cfdPatchInstances(manifest)) {
    const surfaceId =
      instance.surface_graph_id ||
      (instance.source_type === "surface" ? unscopedInstanceId(instance.id) : null);
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
