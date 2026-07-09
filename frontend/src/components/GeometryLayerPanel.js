import React from "react";

import { geometryStats, layerSchema } from "../workspaceModel.js?v=1.1.5";

const h = React.createElement;

export function GeometryLayerPanel({ manifest, visibleLayers, onToggle }) {
  const stats = geometryStats(manifest);

  return h(
    "section",
    { className: "panel-section geometry-layer-panel" },
    h("div", { className: "section-title" }, "Geometry layers"),
    h(
      "div",
      { className: "geometry-stats" },
      h(MiniStat, { label: "Surfaces", value: stats.surfaceCount }),
      h(MiniStat, { label: "Boundaries", value: stats.boundaryCount }),
      h(MiniStat, { label: "Lines", value: stats.constructionLineCount }),
    ),
    h(
      "div",
      { className: "layer-list" },
      layerSchema.map((layer) =>
        h(
          "label",
          { className: "layer-row", key: layer.id },
          h("input", {
            type: "checkbox",
            checked: visibleLayers[layer.id] !== false,
            onChange: (event) => onToggle(layer.id, event.target.checked),
          }),
          h("span", null, layer.label),
        ),
      ),
    ),
  );
}

function MiniStat({ label, value }) {
  return h("div", { className: "mini-stat" }, h("span", null, label), h("strong", null, String(value)));
}
