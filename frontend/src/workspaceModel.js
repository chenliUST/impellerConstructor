export const layerSchema = [
  { id: "shaded_surfaces", label: "Shaded surfaces" },
  { id: "hub_support", label: "Hub support" },
  { id: "tip_support", label: "Tip support" },
  { id: "blade_surfaces", label: "Blade surfaces" },
  { id: "edge_closures", label: "Edge closures" },
  { id: "surface_uv", label: "Surface UV" },
  { id: "blade_boundaries", label: "Blade boundaries" },
  { id: "passage_lines", label: "Passage lines" },
];

export function defaultVisibleLayers() {
  return Object.fromEntries(layerSchema.map((layer) => [layer.id, true]));
}

export function layerForSurface(surface = {}) {
  if (surface.kind === "edge_closure_surface") {
    return "edge_closures";
  }
  if (surface.role === "hub" || surface.ontology_id === "hub_support_surface") {
    return "hub_support";
  }
  if (
    surface.role === "shroud" ||
    surface.role === "open_tip_reference" ||
    surface.role === "reference_only" ||
    surface.role === "front_shroud_inner_surface" ||
    surface.ontology_id === "blade_tip_support_surface"
  ) {
    return "tip_support";
  }
  if (String(surface.role || "").startsWith("blade_")) {
    return "blade_surfaces";
  }
  return "shaded_surfaces";
}

export function layerForConstructionFeature(feature) {
  const featureLayers = {
    hub: "hub_support",
    shroud: "tip_support",
    blade: "blade_surfaces",
    blade_u: "blade_surfaces",
    blade_v: "blade_surfaces",
    blade_edges: "edge_closures",
    blade_boundaries: "blade_boundaries",
    named_boundary_curve: "blade_boundaries",
    passage: "passage_lines",
    surface_uv: "surface_uv",
  };
  return featureLayers[feature] || "surface_uv";
}

export function geometryStats(manifest) {
  const geometry = manifest?.geometry || {};
  const surfaceGraph = geometry.surface_graph || {};
  const constructionLines = geometry.construction_lines || {};

  return {
    surfaceCount: (surfaceGraph.surfaces || []).length,
    boundaryCount: (surfaceGraph.named_boundary_curves || []).length,
    constructionLineCount: Object.values(constructionLines).reduce((total, lines) => total + (lines || []).length, 0),
  };
}
