export function meshOverlayOptions() {
  return [
    { id: "off", label: "Off" },
    { id: "triangle_edges", label: "Triangle edges" },
  ];
}

export function effectiveMeshOverlayMode(simulationViewMode, meshOverlayMode = "triangle_edges") {
  if (simulationViewMode !== "mesh") {
    return "off";
  }
  return meshOverlayOptions().some((option) => option.id === meshOverlayMode) ? meshOverlayMode : "triangle_edges";
}

export function meshOverlayControlVisible(simulationViewMode) {
  return simulationViewMode === "mesh";
}

export function viewerVisibilityForMeshOverlay({
  simulationViewMode,
  viewMode,
  meshOverlayMode = "triangle_edges",
  visibleLayers = {},
} = {}) {
  const activeMeshOverlayMode = effectiveMeshOverlayMode(simulationViewMode, meshOverlayMode);
  const shadedSurfacesEnabled = visibleLayers.shaded_surfaces !== false;
  const showMeshOverlay = simulationViewMode === "mesh" && activeMeshOverlayMode !== "off" && viewMode !== "shaded";
  const showWireframeFallback =
    simulationViewMode === "mesh" && viewMode === "wireframe" && activeMeshOverlayMode === "off";

  return {
    showShaded: shadedSurfacesEnabled && (viewMode !== "wireframe" || showWireframeFallback),
    showMeshOverlay,
  };
}

export function transitionRegionRows(meshManifest = {}) {
  return transitionRegionEntries(meshManifest).map((region) => ({
    edgeFamily: region.edge_family || region.edgeFamily || region.id || "",
    transitionPolicyId: region.transition_policy_id || region.transitionPolicyId || "",
    surfaceGraphId: region.surface_graph_id || region.surfaceGraphId || "",
    triangleCount: Number(region.triangle_count || region.triangleCount || 0),
  }));
}

export function transitionSurfaceIds(meshManifest = {}) {
  return new Set(
    transitionRegionEntries(meshManifest)
      .map((region) => region.surface_graph_id || region.surfaceGraphId || region.source_id || region.sourceId || region.id)
      .filter(Boolean),
  );
}

export function isTransitionSurface(surface = {}, meshManifest = {}) {
  if (surface.transition_policy_id || surface.transitionPolicyId) {
    return true;
  }

  const surfaceId = surface.id || surface.surface_graph_id || surface.surfaceGraphId;
  if (surfaceId && transitionSurfaceIds(meshManifest).has(surfaceId)) {
    return true;
  }

  return [surface.role, surface.cfd_role, surface.kind].some((value) =>
    /transition|fillet|chamfer/.test(String(value || "").toLowerCase()),
  );
}

function transitionRegionEntries(meshManifest = {}) {
  const regions = meshManifest.transition_regions || [];
  return Array.isArray(regions)
    ? regions
    : Object.entries(regions).map(([id, region]) => ({ id, ...(region || {}) }));
}
