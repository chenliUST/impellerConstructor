import React from "react";

import { manifestSummary } from "../appModel.js";

const h = React.createElement;

export function ManifestPanel({ manifest, exportLinks }) {
  const summary = manifestSummary(manifest);

  return h(
    "aside",
    { className: "right-panel" },
    h("div", { className: "section-title" }, "Run manifest"),
    h(
      "div",
      { className: "summary-grid" },
      h(Metric, { label: "Status", value: summary.status }),
      h(Metric, { label: "Run", value: summary.runId || "Not generated" }),
      h(Metric, { label: "Parameters", value: String(summary.parameterCount) }),
      h(Metric, { label: "Ops", value: String(summary.operationCount) }),
    ),
    manifest
      ? h(
          React.Fragment,
          null,
          h(
            "div",
            { className: "export-row" },
            h("a", { href: exportLinks.stl, target: "_blank", rel: "noreferrer" }, "STL"),
            h("a", { href: exportLinks.step, target: "_blank", rel: "noreferrer" }, "STEP"),
          ),
          h(Section, {
            title: "Source refs",
            body: summary.sourceRefs.length ? summary.sourceRefs.join(", ") : "None",
          }),
          h(Section, {
            title: "Facets",
            body: h("pre", null, JSON.stringify(manifest.facets || {}, null, 2)),
          }),
          h(Section, {
            title: "Geometry kernel",
            body: h("pre", null, JSON.stringify(manifest.geometry_kernel || {}, null, 2)),
          }),
          h(Section, {
            title: "Geometry validity",
            body: h("pre", null, JSON.stringify(manifest.geometry_validity || manifest.geometry?.validity || {}, null, 2)),
          }),
          h(Section, {
            title: "Selected rules",
            body: h(
              "ol",
              { className: "op-list" },
              (manifest.selected_rules || []).map((rule) => h("li", { key: rule }, h("code", null, rule))),
            ),
          }),
          h(Section, {
            title: "Inferred regions",
            body: (manifest.unsupported_or_inferred_regions || []).length
              ? h(
                  "ol",
                  { className: "op-list" },
                  manifest.unsupported_or_inferred_regions.map((region) =>
                    h("li", { key: region }, h("code", null, region)),
                  ),
                )
              : "None",
          }),
          h(Section, {
            title: "Parameters",
            body: h("pre", null, JSON.stringify(manifest.parameters, null, 2)),
          }),
          h(Section, {
            title: "Operation graph",
            body: h(
              "ol",
              { className: "op-list" },
              (manifest.operation_graph || []).map((op, index) =>
                h("li", { key: `${op.op}-${index}` }, h("code", null, op.op), op.feature ? ` -> ${op.feature}` : ""),
              ),
            ),
          }),
        )
      : h("p", { className: "empty-state" }, "Generate a preset to inspect its manifest and exports."),
  );
}

function Metric({ label, value }) {
  return h("div", { className: "metric" }, h("span", null, label), h("strong", null, value));
}

function Section({ title, body }) {
  return h("section", { className: "manifest-section" }, h("h3", null, title), typeof body === "string" ? h("p", null, body) : body);
}
