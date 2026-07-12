import { isTransitionSurface } from "./meshOverlayModel.js?v=1.1.5";

const CFD_HIDDEN_ROLES = new Set([
  "construction_support_only",
  "reference_only",
  "mounting_bore",
  "shaft_seat",
  "keyway",
  "rear_hub_groove",
]);
const MESH_HIDDEN_ROLES = new Set(["open_tip_reference", "reference_only", "construction_support_only"]);

export function viewModeOptions() {
  return [
    { id: "cad_review_360", label: "CAD review" },
    { id: "engineering_drawing", label: "Engineering Drawing" },
  ];
}

export function buildSimulationViewModel(manifest, { simulationViewMode = "cad_review_360", selectedPatch = null } = {}) {
  const surfaceGraph = manifest?.geometry?.surface_graph || {};
  return {
    simulationViewMode,
    surfaces: (surfaceGraph.surfaces || []).filter((surface) => surfaceVisibleInView(surface, simulationViewMode, manifest)),
    patchGroups: cfdPatchGroups(manifest),
    patchInstances: cfdPatchInstances(manifest),
    selectedPatchSurfaceIds: [...patchSurfaceIds(manifest, selectedPatch)],
    selectedPatchBoundaryCurveIds: [...patchBoundaryCurveIds(manifest, selectedPatch)],
  };
}

export function surfaceVisibleInView(surface, viewMode, manifest = null) {
  if (surface?.display?.visible_by_default === false && viewMode !== "feature_debug") {
    return false;
  }
  if (["open_tip_reference", "reference_only"].includes(surface?.role) && viewMode !== "feature_debug") {
    return false;
  }
  if (viewMode === "mesh") {
    if ([surface?.role, surface?.cfd_role, surface?.kind, surface?.assembly_role].some((role) => MESH_HIDDEN_ROLES.has(role))) {
      return false;
    }
    return hasRenderableMeshReviewGeometry(surface);
  }
  if (viewMode !== "cfd_full_360") {
    return true;
  }
  if ([surface?.role, surface?.cfd_role, surface?.kind, surface?.assembly_role].some((role) => CFD_HIDDEN_ROLES.has(role))) {
    return false;
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
  if (surfaceIds.size > 0) {
    return surfaceIds;
  }
  const meshManifest = cfdSurfaceMeshManifest(manifest);
  for (const region of meshManifest?.patch_regions || []) {
    const surfaceId = region?.surface_graph_id || region?.surfaceGraphId || region?.source_id || region?.sourceId;
    if (surfaceId && Number(region?.triangle_count ?? 1) > 0) {
      surfaceIds.add(surfaceId);
    }
  }
  return surfaceIds;
}

function cfdFull360Manifest(manifest) {
  return manifest?.simulation_manifests?.cfd_full_360;
}

function cfdSurfaceMeshManifest(manifest) {
  return manifest?.simulation_manifests?.cfd_surface_mesh;
}

function hasRenderableMeshReviewGeometry(surface = {}) {
  return hasRectangularUvGrid(surface.uv_grid) || Boolean(surface.mesh);
}

function hasRectangularUvGrid(grid) {
  if (!Array.isArray(grid) || grid.length < 2 || !Array.isArray(grid[0]) || grid[0].length < 2) {
    return false;
  }
  const columnCount = grid[0].length;
  return grid.every((row) => Array.isArray(row) && row.length === columnCount);
}

function unscopedInstanceId(instanceId) {
  const segments = String(instanceId || "").split(":");
  return segments[segments.length - 1];
}
