import React from "react";

import { parameterSchema } from "../appModel.js";

const h = React.createElement;

export function ParameterPanel({ parameters, onChange, onGenerate, onReset, loading }) {
  return h(
    "section",
    { className: "panel-section parameter-panel" },
    h("div", { className: "section-title" }, "Parameters"),
    h(
      "div",
      { className: "parameter-list" },
      Object.entries(parameterSchema).map(([name, spec]) =>
        h(
          "label",
          { className: "parameter-row", key: name },
          h(
            "span",
            { className: "parameter-label" },
            h("span", null, spec.label),
            spec.unit ? h("small", null, spec.unit) : null,
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
    h(
      "div",
      { className: "button-row" },
      h("button", { className: "secondary-action", onClick: onReset, disabled: loading }, "Reset preset"),
      h("button", { className: "primary-action", onClick: onGenerate, disabled: loading }, loading ? "Generating..." : "Generate"),
    ),
  );
}
