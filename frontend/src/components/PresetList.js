import React from "react";

const h = React.createElement;

export function PresetList({ presets, selectedId, onSelect }) {
  return h(
    "section",
    { className: "panel-section" },
    h("div", { className: "section-title" }, "Visual presets"),
    h(
      "div",
      { className: "preset-list" },
      presets.map((preset) =>
        h(
          "button",
          {
            key: preset.id,
            className: preset.id === selectedId ? "preset-button selected" : "preset-button",
            onClick: () => onSelect(preset),
          },
          h("span", { className: "preset-name" }, preset.name),
          h("span", { className: "preset-summary" }, preset.summary),
          h(
            "span",
            { className: "tag-row" },
            preset.tags.map((tag) => h("span", { className: "tag", key: tag }, tag)),
          ),
        ),
      ),
    ),
  );
}
