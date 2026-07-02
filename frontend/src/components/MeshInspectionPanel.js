import React from "react";

import { transitionRegionRows } from "../meshOverlayModel.js";
import { meshQualitySummary } from "../meshViewModel.js";

const h = React.createElement;

export function MeshInspectionPanel({ meshManifest }) {
  const summary = meshQualitySummary(meshManifest);
  const transitionRows = transitionRegionRows(meshManifest);
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
    transitionRows.length > 0
      ? h("div", { key: "transition-regions", className: "patch-list" }, [
          h("div", { key: "transition-title", className: "subtle-label" }, "transition regions"),
          ...transitionRows.map((row) =>
            h(
              "div",
              { className: "patch-row transition-region-row", key: row.surfaceGraphId || row.edgeFamily },
              h("span", { title: row.transitionPolicyId || row.edgeFamily }, row.edgeFamily || "transition"),
              h("strong", null, String(row.triangleCount)),
            ),
          ),
        ])
      : null,
  ]);
}
