export const layerSchema = [
  { id: "shaded_surfaces", label: "Shaded surfaces" },
  { id: "hub_support", label: "Hub support" },
  { id: "tip_support", label: "Tip support" },
  { id: "blade_surfaces", label: "Blade surfaces" },
  { id: "edge_closures", label: "Edge closures" },
  { id: "transition_surfaces", label: "Transition surfaces" },
  { id: "mesh_edges", label: "Mesh edges" },
  { id: "transition_mesh_edges", label: "Transition mesh edges" },
  { id: "solid_context", label: "Solid context" },
  { id: "fluid_boundary", label: "Fluid boundary" },
  { id: "surface_uv", label: "Surface UV" },
  { id: "blade_boundaries", label: "Blade boundaries" },
  { id: "passage_lines", label: "Passage lines" },
];

export function defaultVisibleLayers() {
  return Object.fromEntries(layerSchema.map((layer) => [layer.id, true]));
}

export function layerForSurface(surface = {}) {
  const cfdRole = surface.cfd_role || "";
  if (isTransitionSurface(surface)) {
    return "transition_surfaces";
  }
  if (surface.role === "solid_context" || cfdRole === "solid_context") {
    return "solid_context";
  }
  if (surface.role === "fluid_boundary" || cfdRole === "fluid_boundary") {
    return "fluid_boundary";
  }
  if (surface.kind === "edge_closure_surface") {
    return "edge_closures";
  }
  if (
    cfdRole === "leading_edge_transition" ||
    cfdRole === "trailing_edge_transition" ||
    cfdRole === "root_transition" ||
    cfdRole === "tip_transition"
  ) {
    return "edge_closures";
  }
  if (surface.role === "hub" || cfdRole === "hub_wall" || surface.ontology_id === "hub_support_surface") {
    return "hub_support";
  }
  if (
    surface.role === "shroud" ||
    surface.role === "open_tip_reference" ||
    surface.role === "reference_only" ||
    surface.role === "front_shroud_inner_surface" ||
    cfdRole === "tip_or_shroud_wall" ||
    surface.ontology_id === "blade_tip_support_surface"
  ) {
    return "tip_support";
  }
  if (String(surface.role || "").startsWith("blade_") || cfdRole.startsWith("blade_")) {
    return "blade_surfaces";
  }
  return "shaded_surfaces";
}

export function isTransitionSurface(surface = {}) {
  const role = String(surface.role || "");
  const cfdRole = String(surface.cfd_role || "");
  return (
    Boolean(surface.transition_policy_id || surface.edge_family) ||
    role.includes("fillet") ||
    role.includes("chamfer") ||
    cfdRole.includes("transition")
  );
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
