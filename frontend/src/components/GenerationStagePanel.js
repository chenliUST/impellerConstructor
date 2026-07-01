import React from "react";

const h = React.createElement;

const stages = [
  { id: "hub_support", label: "Hub" },
  { id: "blade_surfaces", label: "Blades" },
  { id: "edge_closures", label: "Edges" },
];

export function GenerationStagePanel({ geometryStage, onChange }) {
  return h(
    "section",
    { className: "panel-section generation-stage-panel" },
    h("div", { className: "section-title" }, "Generation stage"),
    h(
      "div",
      { className: "stage-row" },
      stages.map((stage) =>
        h(
          "button",
          {
            key: stage.id,
            className: geometryStage === stage.id ? "stage-button active" : "stage-button",
            onClick: () => onChange(stage.id),
            type: "button",
          },
          stage.label,
        ),
      ),
    ),
  );
}
