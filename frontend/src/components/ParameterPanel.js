import React from "react";

import { parameterGroups, parameterSchemaForPreset } from "../appModel.js?v=1.1.5";

const h = React.createElement;

export function ParameterPanel({ activePreset, parameters, onChange, onGenerate, onReset, loading }) {
  const visibleParameterSchema = parameterSchemaForPreset(activePreset);
  const groupedParameters = parameterGroups
    .map((group) => ({
      ...group,
      entries: Object.entries(visibleParameterSchema).filter(([, spec]) => spec.group === group.id),
    }))
    .filter((group) => group.entries.length > 0);

  return h(
    "section",
    { className: "panel-section parameter-panel" },
    h("div", { className: "section-title" }, "Parameters"),
    h(
      "div",
      { className: "parameter-list" },
      groupedParameters.map((group) =>
        h(
          "section",
          {
            className: `parameter-group${group.id === "blade_boundaries" ? " boundary-parameter-group" : ""}`,
            "data-group": group.id,
            key: group.id,
          },
          h("h3", null, group.label),
          group.entries.map(([name, spec]) =>
            h(
              "label",
              { className: "parameter-row", key: name },
              h(
                "span",
                { className: "parameter-label" },
                h("span", null, spec.label),
                h("small", null, spec.controlKind || spec.unit || ""),
              ),
              h("input", {
                className: "number-input",
                type: "number",
                step: spec.step,
                value: parameters[name],
                onChange: (event) => onChange(name, event.target.value),
              }),
            ),
          ),
        ),
      ),
    ),
    h(
      "div",
      { className: "button-row" },
      h("button", { className: "secondary-action", onClick: onReset, disabled: loading }, "Reset preset"),
      h("button", { className: "primary-action", onClick: onGenerate, disabled: loading }, loading ? "Generating..." : "Generate"),
    ),
  );
}
