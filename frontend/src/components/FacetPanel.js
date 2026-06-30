import React from "react";

import { facetSchema } from "../appModel.js";

const h = React.createElement;

export function FacetPanel({ facets, onChange }) {
  return h(
    "section",
    { className: "panel-section facet-panel" },
    h("div", { className: "section-title" }, "Ontology facets"),
    h(
      "div",
      { className: "facet-list" },
      Object.entries(facetSchema).map(([name, spec]) =>
        h(
          "label",
          { className: "facet-row", key: name },
          h("span", null, spec.label),
          h(
            "select",
            {
              value: facets[name],
              onChange: (event) => onChange(name, event.target.value),
            },
            spec.values.map((value) => h("option", { key: value, value }, value)),
          ),
        ),
      ),
    ),
  );
}
