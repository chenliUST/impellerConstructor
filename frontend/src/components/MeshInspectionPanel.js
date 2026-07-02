import React from "react";

import { meshQualitySummary } from "../meshViewModel.js";

const h = React.createElement;

export function MeshInspectionPanel({ meshManifest }) {
  const summary = meshQualitySummary(meshManifest);
  return h("section", { className: "panel-section" }, [
    h("h3", { key: "title" }, "CFD360 Mesh"),
    h("dl", { key: "metrics", className: "metric-grid" }, [
      h("dt", { key: "tri-label" }, "Triangles"),
      h("dd", { key: "tri-value" }, String(summary.triangleCount)),
      h("dt", { key: "deg-label" }, "Degenerate"),
      h("dd", { key: "deg-value" }, String(summary.degenerateTriangleCount)),
      h("dt", { key: "aspect-label" }, "Max aspect"),
      h("dd", { key: "aspect-value" }, String(summary.maxAspectRatio)),
    ]),
  ]);
}
