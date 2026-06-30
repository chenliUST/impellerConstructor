import React from "react";

import { cfdPatchGroups, cfdPatchInstances } from "../simulationViewModel.js";

const h = React.createElement;

export function CfdManifestPanel({ manifest, selectedPatch, onSelectPatch }) {
  const groups = cfdPatchGroups(manifest);
  const instances = cfdPatchInstances(manifest);
  const cfd = manifest?.simulation_manifests?.cfd_full_360;

  return h(
    "section",
    { className: "panel-section cfd-manifest-panel" },
    h("div", { className: "section-title" }, "CFD full 360 manifest"),
    h("div", { className: "status-pill" }, cfd?.validity?.status || "NO CFD MANIFEST"),
    h(
      "div",
      { className: "patch-list" },
      groups.map((group) =>
        h(
          "button",
          {
            className: selectedPatch === group.id ? "patch-row selected" : "patch-row",
            type: "button",
            onClick: () => onSelectPatch(group.id),
            key: group.id,
          },
          h("span", null, group.id),
          h("strong", null, String(group.instances?.length || 0)),
        ),
      ),
    ),
    h("div", { className: "subtle-label" }, `instances ${instances.length}`),
  );
}
