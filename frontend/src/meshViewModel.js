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
