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

const TRANSITION_INSPECTION_CLASSES = new Set([
  "root_to_hub_blend",
  "open_tip_dome",
  "blade_leading_edge",
  "blade_trailing_edge",
  "root_to_hub_native_root_face",
  "tip_to_shroud_attachment",
]);

const TRANSITION_ROLES = new Set([
  "root_to_hub_blend",
  "open_tip_dome",
  "blade_leading_edge",
  "blade_trailing_edge",
  "blade_root_fillet",
]);

export function viewerLayerVisibility({
  simulationViewMode,
  viewMode,
  meshOverlayMode = "triangle_edges",
  visibleLayers = {},
} = {}) {
  const activeMeshOverlayMode = effectiveMeshOverlayMode(simulationViewMode, meshOverlayMode);
  const shadedSurfacesEnabled = visibleLayers.shaded_surfaces !== false;
  const activeViewMode = viewMode || "combined";

  return {
    showShadedSurfaces: shadedSurfacesEnabled && activeViewMode !== "wireframe",
    showSurfaceUvWire: activeViewMode === "wireframe" || activeViewMode === "combined",
    showMeshEdges: simulationViewMode === "mesh" && activeMeshOverlayMode !== "off" && activeViewMode !== "shaded",
    showConstructionLines: simulationViewMode === "feature_debug",
  };
}

export function viewerVisibilityForMeshOverlay(options = {}) {
  const { showShadedSurfaces, showMeshEdges } = viewerLayerVisibility(options);
  return {
    showShaded: showShadedSurfaces,
    showMeshOverlay: showMeshEdges,
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

  if (TRANSITION_INSPECTION_CLASSES.has(surface.display?.inspection_class) || TRANSITION_ROLES.has(surface.role)) {
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
  if (!meshManifest || typeof meshManifest !== "object") {
    return [];
  }
  const regions = meshManifest.transition_regions || [];
  return Array.isArray(regions)
    ? regions
    : Object.entries(regions).map(([id, region]) => ({ id, ...(region || {}) }));
}
