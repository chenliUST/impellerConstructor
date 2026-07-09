import { isTransitionSurface } from "./meshOverlayModel.js?v=1.1.5";

export const layerSchema = [
  { id: "shaded_surfaces", label: "Shaded surfaces" },
  { id: "shade_surfaces", label: "Shade surfaces", defaultVisible: true },
  { id: "hub_support", label: "Hub support" },
  { id: "tip_support", label: "Tip support" },
  { id: "blade_surfaces", label: "Blade surfaces" },
  { id: "edge_closures", label: "Edge closures" },
  { id: "transition_surfaces", label: "Transition surfaces" },
  { id: "mesh_edges", label: "Mesh edges" },
  { id: "transition_mesh_edges", label: "Transition mesh edges" },
  { id: "nurbs_uv_wire", label: "NURBS UV wire", defaultVisible: true },
  { id: "mesh_triangle_wire", label: "Mesh triangle wire", defaultVisible: false },
  { id: "control_curves", label: "Control curves", defaultVisible: true },
  { id: "control_points", label: "Control points", defaultVisible: true },
  { id: "shared_edges", label: "Shared edges", defaultVisible: false },
  { id: "diagnostic_failures", label: "Diagnostic failures", defaultVisible: true },
  { id: "solid_context", label: "Solid context" },
  { id: "fluid_boundary", label: "Fluid boundary" },
  { id: "surface_uv", label: "Surface UV" },
  { id: "blade_boundaries", label: "Blade boundaries" },
  { id: "passage_lines", label: "Passage lines" },
];

export function defaultVisibleLayers() {
  return Object.fromEntries(layerSchema.map((layer) => [layer.id, layer.defaultVisible ?? true]));
}

export function buildWorkspaceModel({ manifest = null, visibleLayers = null } = {}) {
  return {
    visibleLayers: visibleLayers || defaultVisibleLayers(),
    stats: geometryStats(manifest),
    curveControls: clonePlainObject(manifest?.curve_controls || manifest?.geometry?.curve_controls || {}),
    sectionLoopControls: clonePlainObject(manifest?.section_loop_controls || manifest?.geometry?.section_loop_controls || {}),
  };
}

export function layerForSurface(surface = {}, meshManifest = null) {
  const cfdRole = surface.cfd_role || "";
  if (isV102AttachmentInspectionSurface(surface)) {
    return "edge_closures";
  }
  if (surface.source_kernel === "v1_1_blade_to_blade_surface_family_kernel") {
    if (["root_to_hub_attachment", "open_tip_dome", "closed_shroud_attachment"].includes(surface.role)) {
      return "transition_surfaces";
    }
    if (["blade_leading_edge", "blade_trailing_edge"].includes(surface.role)) {
      return "edge_closures";
    }
    if (["blade_pressure", "blade_suction"].includes(surface.role)) {
      return "blade_surfaces";
    }
  }
  if (isTransitionSurface(surface, meshManifest)) {
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
  if (surface.kind === "native_topology_face") {
    if (["blade_leading_edge", "blade_trailing_edge", "blade_root", "blade_tip"].includes(surface.face_family)) {
      return "edge_closures";
    }
    if (String(surface.face_family || "").startsWith("blade_")) {
      return "blade_surfaces";
    }
    if (["hub_bevel", "mounting_bore"].includes(surface.face_family)) {
      return "solid_context";
    }
    if (String(surface.face_family || "").startsWith("hub_")) {
      return "hub_support";
    }
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

export { isTransitionSurface } from "./meshOverlayModel.js?v=1.1.5";

export function usesV11ViewerLayers(manifest, surfaceGraph = null) {
  const graph = surfaceGraph || manifest?.geometry?.surface_graph || {};
  const status =
    graph.transition_geometry_status ||
    manifest?.transition_geometry_status ||
    manifest?.metadata?.transitionGeometryStatus;
  return status === "topology_first_blade_to_blade_5_loop_surface_family_graph";
}

export function usesV104ViewerLayers(manifest, surfaceGraph = null) {
  const graph = surfaceGraph || manifest?.geometry?.surface_graph || {};
  const patchVersion =
    graph.geometry_patch_version ||
    manifest?.geometryPatchVersion ||
    manifest?.geometry_patch_version ||
    manifest?.metadata?.geometryPatchVersion;
  const transitionStatus =
    graph.transition_geometry_status ||
    manifest?.transition_geometry_status ||
    manifest?.metadata?.transitionGeometryStatus;
  return (
    String(patchVersion || "") === "1.0.4" ||
    transitionStatus === "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
  );
}

export function meshOverlayLayerForV104(surface = {}) {
  return surfaceHasDiagnosticFailure(surface) ? "diagnostic_failures" : "mesh_triangle_wire";
}

export function sharedEdgeLayerForV104(sharedEdge = {}) {
  return sharedEdgeHasDiagnosticFailure(sharedEdge) ? "diagnostic_failures" : "shared_edges";
}

function isV102AttachmentInspectionSurface(surface = {}) {
  const inspectionClass = surface.display?.inspection_class || "";
  return (
    surface.role === "root_pedestal_ring_surface" ||
    surface.role === "tip_to_shroud_attachment_surface" ||
    inspectionClass === "root_to_hub_native_root_face" ||
    inspectionClass === "tip_to_shroud_attachment"
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

function clonePlainObject(value) {
  return value ? JSON.parse(JSON.stringify(value)) : {};
}

function surfaceHasDiagnosticFailure(surface = {}) {
  const status = String(
    surface.validation_status ||
      surface.display?.validation_status ||
      surface.display?.inspection_status ||
      surface.status ||
      "",
  ).toLowerCase();
  return (
    surface.failed === true ||
    surface.has_failure === true ||
    surface.display?.has_failure === true ||
    surface.display?.diagnostic_failure === true ||
    status.includes("fail") ||
    status.includes("error")
  );
}

function sharedEdgeHasDiagnosticFailure(sharedEdge = {}) {
  const status = String(sharedEdge.status || sharedEdge.validation_status || sharedEdge.result || "").toLowerCase();
  return (
    sharedEdge.failed === true ||
    sharedEdge.is_failure === true ||
    sharedEdge.blocking === true ||
    status.includes("fail") ||
    status.includes("error")
  );
}
