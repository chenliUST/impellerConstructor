export function meshOverlayOptions() {
  return [
    { id: "off", label: "Off" },
    { id: "triangle_edges", label: "Triangle edges" },
    { id: "patch_groups", label: "Patch groups" },
    { id: "quality", label: "Quality" },
    { id: "transitions", label: "Transitions" },
  ];
}

export function transitionRegionRows(meshManifest = {}) {
  const regions = meshManifest.transition_regions || [];
  const entries = Array.isArray(regions)
    ? regions
    : Object.entries(regions).map(([id, region]) => ({ id, ...(region || {}) }));

  return entries.map((region) => ({
    edgeFamily: region.edge_family || region.edgeFamily || region.id || "",
    transitionPolicyId: region.transition_policy_id || region.transitionPolicyId || "",
    surfaceGraphId: region.surface_graph_id || region.surfaceGraphId || "",
    triangleCount: Number(region.triangle_count || region.triangleCount || 0),
  }));
}
