import React, { useEffect, useMemo, useState } from "react";

import { edgeTreatmentRows, effectiveTransitionRow, updateTransitionRow } from "../edgeTreatmentModel.js";

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
              onChange: (patch) => onChange(updateTransitionRow(overrides, row.policyId, patch, row)),
            }),
          ),
        )
      : h("p", { className: "small-note" }, "No transition policies in the current manifest."),
  );
}

function EdgeTreatmentRow({ row, override, onChange }) {
  const effective = effectiveTransitionRow(row, override);
  const [radiusText, setRadiusText] = useState(() => formatRadius(effective.radiusMm));

  useEffect(() => {
    setRadiusText(formatRadius(effective.radiusMm));
  }, [effective.radiusMm, row.policyId]);

  function commitRadius() {
    const trimmed = radiusText.trim();
    if (!trimmed) {
      setRadiusText(formatRadius(effective.radiusMm));
      return;
    }

    const next = Number(trimmed);
    if (Number.isFinite(next)) {
      onChange({ radiusMm: next });
    } else {
      setRadiusText(formatRadius(effective.radiusMm));
    }
  }

  return h(
    "div",
    { className: "edge-treatment-row" },
    h(
      "label",
      { className: "edge-toggle" },
      h("input", {
        type: "checkbox",
        checked: effective.enabled,
        onChange: (event) => onChange({ enabled: event.target.checked }),
      }),
      h("span", null, row.edgeFamily.replaceAll("_", " ")),
    ),
    h(
      "select",
      {
        value: effective.treatment,
        onChange: (event) => onChange({ treatment: event.target.value }),
      },
      treatments.map((option) => h("option", { key: option, value: option }, option)),
    ),
    h("input", {
      className: "edge-radius-input",
      type: "number",
      min: "0",
      step: "0.001",
      value: radiusText,
      onBlur: commitRadius,
      onChange: (event) => setRadiusText(event.target.value),
      onKeyDown: (event) => {
        if (event.key === "Enter") {
          commitRadius();
        }
      },
    }),
    h("span", { className: effective.status === "OK" ? "edge-status" : "edge-status warning" }, effective.status),
  );
}

function formatRadius(radiusMm) {
  return Number.isFinite(radiusMm) ? String(radiusMm) : "";
}
