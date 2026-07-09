import { transitionRegionRows } from "./meshOverlayModel.js?v=1.1.5";

export const meshViewModes = [
  { id: "patches", label: "Patch view" },
  { id: "mesh", label: "Mesh view" },
  { id: "quality", label: "Quality overlay" },
];

export function meshQualitySummary(meshManifest = {}) {
  const metrics = meshManifest.quality_metrics || {};
  return {
    triangleCount: Number(meshManifest.triangle_count || 0),
    degenerateTriangleCount: Number(meshManifest.degenerate_triangle_count || 0),
    minArea: Number(metrics.min_area || 0),
    maxArea: Number(metrics.max_area || 0),
    maxAspectRatio: Number(metrics.max_aspect_ratio || 0),
  };
}

export function meshInspectionSummary(meshManifest = {}) {
  const quality = meshQualitySummary(meshManifest);
  const transitionRows = transitionRegionRows(meshManifest);
  const transitionTriangleCount = transitionRows.reduce((total, row) => total + row.triangleCount, 0);

  return {
    meshType: meshManifest.mesh_type || "unknown",
    ...quality,
    transitionRegionCount: transitionRows.length,
    transitionTriangleCount,
    hasTransitionRegions: transitionRows.length > 0,
  };
}
