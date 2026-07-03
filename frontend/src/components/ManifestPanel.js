import React from "react";

import { manifestSummary } from "../appModel.js";

const h = React.createElement;

export function ManifestPanel({ manifest, exportLinks, before = null }) {
  const summary = manifestSummary(manifest);
  const ontology_slice = manifest?.ontology_slice || "";
  const constructor_family = manifest?.constructor_family || "";
  const constructor_id = manifest?.constructor_id || "";
  const shape_control = manifest?.shape_control || {};
  const optimization_stage = shape_control.optimization_stage || "unset";
  const validityContracts = manifest?.validity || {};
  const exportStrategy = manifest?.export_strategy || {};
  const exportManifests = manifest?.export_manifests || {};
  const stlExport = exportManifests.stl || {};
  const stepExport = exportManifests.step || {};
  const geometryValidationReport = manifest?.geometry_validation_report || {};
  const geometryValidationStatus =
    manifest?.geometry_validation_status || geometryValidationReport.geometry_validation_status || "Unknown";
  const transitionValidationSummary = geometryValidationReport.transition_validation_summary || {};
  const blockingValidationFailures = geometryValidationReport.blocking_failures || [];
  const capabilityClaimLevel =
    manifest?.capability_claim_level || geometryValidationReport.capability_claim_level || "unset";

  return h(
    "aside",
    { className: "right-panel" },
    before,
    h("div", { className: "section-title" }, "Run manifest"),
    h(
      "div",
      { className: "summary-grid" },
      h(Metric, { label: "Status", value: summary.status }),
      h(Metric, { label: "Run", value: summary.runId || "Not generated" }),
      h(Metric, { label: "Parameters", value: String(summary.parameterCount) }),
      h(Metric, { label: "Ops", value: String(summary.operationCount) }),
      h(Metric, { label: "Slice", value: ontology_slice || "None" }),
      h(Metric, { label: "Constructor", value: constructor_id || constructor_family || "None" }),
      h(Metric, { label: "Shape stage", value: optimization_stage }),
      h(Metric, { label: "Geom validation", value: geometryValidationStatus }),
      h(Metric, { label: "Claim", value: capabilityClaimLevel }),
      h(Metric, { label: "Export mode", value: exportStrategy.mode || "unset" }),
      h(Metric, { label: "STL exactness", value: stlExport.export_exactness || "legacy" }),
      h(Metric, {
        label: "Contracts",
        value: String(
          (validityContracts.geometry_contracts || []).length +
            (validityContracts.topology_contracts || []).length +
            (validityContracts.engineering_contracts || []).length,
        ),
      }),
    ),
    manifest
      ? h(
          React.Fragment,
          null,
          h(
            "div",
            { className: "export-row" },
            exportLinks.map((option) =>
              h(
                "a",
                {
                  key: option.id,
                  href: option.href,
                  download: option.download,
                  target: "_blank",
                  rel: "noreferrer",
                },
                option.label,
              ),
            ),
          ),
          h(Section, {
            title: "Source refs",
            body: summary.sourceRefs.length ? summary.sourceRefs.join(", ") : "None",
          }),
          h(Section, {
            title: "Export fidelity",
            body: h(
              "pre",
              null,
              JSON.stringify(
                {
                  strategy: exportStrategy.mode || "legacy",
                  source: exportStrategy.source || "legacy export path",
                  view: exportStrategy.view || "legacy",
                  stl_exactness: stlExport.export_exactness || "legacy",
                  step_exactness: stepExport.export_exactness || "legacy",
                  stl_surface_count: stlExport.surface_count || 0,
                  stl_triangle_count: stlExport.triangle_count || 0,
                  step_face_count: stepExport.face_count || 0,
                  surface_graph_faithful: exportStrategy.mode === "surface_graph_faithful",
                  export_manifests: Boolean(manifest.export_manifests),
                },
                null,
                2,
              ),
            ),
          }),
          h(Section, {
            title: "Geometry validation report",
            body: h(
              "pre",
              null,
              JSON.stringify(
                {
                  status: geometryValidationStatus,
                  kernel_capability_matrix_id:
                    manifest.kernel_capability_matrix_id ||
                    geometryValidationReport.kernel_capability_matrix_id ||
                    "unset",
                  capability_claim_level: capabilityClaimLevel,
                  unsupported_claims: manifest.unsupported_claims || geometryValidationReport.unsupported_claims || [],
                  blocking_failure_count: blockingValidationFailures.length,
                  blocking_failures: blockingValidationFailures,
                  transition_validation_summary: transitionValidationSummary,
                },
                null,
                2,
              ),
            ),
          }),
          h(Section, {
            title: "Ontology constructor",
            body: h(
              "pre",
              null,
              JSON.stringify(
                {
                  ontology_slice,
                  constructor_family,
                  constructor_id,
                  dsl_version: manifest.dsl_version,
                },
                null,
                2,
              ),
            ),
          }),
          h(Section, {
            title: "Shape control",
            body: h("pre", null, JSON.stringify(shape_control, null, 2)),
          }),
          h(Section, {
            title: "Validity contracts",
            body: h("pre", null, JSON.stringify(validityContracts, null, 2)),
          }),
          h(Section, {
            title: "Loss records",
            body: h("pre", null, JSON.stringify(manifest.loss_records || {}, null, 2)),
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
