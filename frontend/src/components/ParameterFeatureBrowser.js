import React from "react";

const h = React.createElement;

export function ParameterFeatureBrowser({ groups = [], selectedParameterId = null, onSelect = null }) {
  return h(
    "aside",
    { className: "engineering-parameter-browser", "aria-label": "Engineering parameters" },
    [...groups]
      .sort(compareRecords)
      .map((group) => h(
        "details",
        { key: group.groupId, className: "engineering-parameter-group", open: group.collapsed === false },
        h("summary", null, group.label),
        h(
          "div",
          { className: "engineering-parameter-list" },
          [...(group.parameters || [])].sort(compareRecords).map((parameter) => {
            const active = selectedParameterId === parameter.id;
            const disabled = parameter.disabled === true;
            const views = applicableViews(parameter.applicableViews);
            return h(
              "button",
              {
                key: parameter.id,
                className: `engineering-parameter-button${active ? " selected" : ""}${hasControlPoint(parameter) ? " control-point" : ""}`,
                type: "button",
                disabled,
                "aria-disabled": disabled,
                "aria-pressed": active,
                "aria-label": `${parameter.label}${views ? `, available in ${views}` : ""}`,
                title: views ? `${parameter.label} - available in ${views}` : parameter.label,
                "data-parameter-id": parameter.id,
                onClick: () => onSelect?.(active ? null : parameter.id),
              },
              parameter.label,
            );
          }),
        ),
      )),
  );
}

function compareRecords(left, right) {
  return Number(left?.order || 0) - Number(right?.order || 0)
    || String(left?.label || left?.id || left?.groupId).localeCompare(String(right?.label || right?.id || right?.groupId));
}

function hasControlPoint(parameter) {
  return Array.isArray(parameter.features) && parameter.features.some((feature) => feature?.kind === "control_point");
}

function applicableViews(views) {
  return (Array.isArray(views) ? views : []).map(viewLabel).join(", ");
}

function viewLabel(viewId) {
  return {
    top: "Top",
    meridional: "Meridional",
    s_q: "S-Q",
    blade_3d: "3D",
  }[viewId] || String(viewId);
}
