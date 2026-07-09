import React, { useMemo, useState } from "react";

import { parameterViewTabs } from "../parameterViewModel.js?v=1.1.6";

const h = React.createElement;

export function ParameterViewsPanel({ activePreset, manifest }) {
  const tabs = useMemo(() => parameterViewTabs(activePreset, manifest), [activePreset, manifest]);
  const [selectedId, setSelectedId] = useState(tabs[0]?.id || "top");
  const selected = tabs.find((tab) => tab.id === selectedId) || tabs[0];

  return h(
    "section",
    { className: "panel-section parameter-views-panel" },
    h("div", { className: "section-title" }, "Parameter views"),
    h(
      "div",
      { className: "parameter-view-tabs" },
      tabs.map((tab) =>
        h(
          "button",
          {
            key: tab.id,
            type: "button",
            className: selected?.id === tab.id ? "active" : "",
            onClick: () => setSelectedId(tab.id),
          },
          tab.label,
        ),
      ),
    ),
    selected
      ? h(
          "div",
          { className: `parameter-view parameter-view-${selected.id}` },
          h("p", { className: "small-note" }, `Source: ${selected.sourceLabel}`),
          h(
            "dl",
            { className: "annotation-list" },
            selected.annotations.map((item) => [
              h("dt", { key: `${item.label}-label` }, item.label),
              h("dd", { key: `${item.label}-value` }, String(item.value)),
            ]),
          ),
        )
      : h("p", { className: "empty-state" }, "No canonical parameterization available."),
  );
}
