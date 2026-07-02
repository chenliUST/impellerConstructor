import React, { useMemo } from "react";

import { edgeTreatmentRows, updateTransitionRow } from "../edgeTreatmentModel.js";

const h = React.createElement;
const treatments = ["none", "chamfer", "fillet"];

export function EdgeTreatmentPanel({ manifest, overrides = {}, onChange }) {
  const rows = useMemo(() => edgeTreatmentRows(manifest), [manifest]);

  return h(
    "section",
    { className: "panel-section edge-treatment-panel" },
    h("div", { className: "section-title" }, "Edge treatments"),
    rows.length
      ? h(
          "div",
          { className: "edge-treatment-list" },
          rows.map((row) =>
            h(EdgeTreatmentRow, {
              key: row.policyId,
              row,
              override: overrides[row.policyId] || {},
              onChange: (patch) => onChange(updateTransitionRow(overrides, row.policyId, patch)),
            }),
          ),
        )
      : h("p", { className: "small-note" }, "No transition policies in the current manifest."),
  );
}

function EdgeTreatmentRow({ row, override, onChange }) {
  const enabled = override.enabled ?? row.enabled;
  const treatment = override.treatment ?? row.treatment;
  const radiusMm = override.radius_mm ?? row.radiusMm;
  const status = edgeStatus(enabled, treatment, Number(radiusMm));

  return h(
    "div",
    { className: "edge-treatment-row" },
    h(
      "label",
      { className: "edge-toggle" },
      h("input", {
        type: "checkbox",
        checked: enabled,
        onChange: (event) => onChange({ enabled: event.target.checked }),
      }),
      h("span", null, row.edgeFamily.replaceAll("_", " ")),
    ),
    h(
      "select",
      {
        value: treatment,
        onChange: (event) => onChange({ treatment: event.target.value }),
      },
      treatments.map((option) => h("option", { key: option, value: option }, option)),
    ),
    h("input", {
      className: "edge-radius-input",
      type: "number",
      step: "0.001",
      value: radiusMm,
      onChange: (event) => {
        const next = Number(event.target.value);
        if (Number.isFinite(next)) {
          onChange({ radiusMm: next });
        }
      },
    }),
    h("span", { className: status === "OK" ? "edge-status" : "edge-status warning" }, status),
  );
}

function edgeStatus(enabled, treatment, radiusMm) {
  if (!enabled || treatment === "none") {
    return "OFF";
  }
  if (radiusMm < 0) {
    return "INVALID";
  }
  return "OK";
}
