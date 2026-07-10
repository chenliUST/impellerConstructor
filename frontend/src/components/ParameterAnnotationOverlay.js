import React from "react";

const h = React.createElement;
const SLOT_HEIGHT = 28;
const VIEWPORT_MIDPOINT = 500;
const LEFT_LABEL_RAIL = 120;
const RIGHT_LABEL_RAIL = 720;

export function ParameterAnnotationOverlay({ annotations = [], projectAnchor }) {
  const labels = layoutLabels(annotations, projectAnchor);

  return h(
    "g",
    { className: "parameter-annotation-overlay" },
    labels.map(({ annotation, anchor, label }) => {
      const resolvedText = `${annotation.resolvedValue}${annotation.unit ? ` ${annotation.unit}` : ""}`;
      const requestedText = `${annotation.requestedValue}${annotation.requestedUnit ? ` ${annotation.requestedUnit}` : ""}`;
      const formattedValue = annotation.requestedValue === annotation.resolvedValue
        ? `${annotation.label}: ${resolvedText}`
        : `${annotation.label}: ${requestedText} -> ${resolvedText}`;
      const selectedClass = annotation.selected ? " selected" : "";

      return h(
        "g",
        { key: annotation.id },
        h("line", {
          className: `inspection-leader${selectedClass}`,
          x1: anchor.x,
          y1: anchor.y,
          x2: label.x,
          y2: label.y,
        }),
        h("text", { className: `inspection-label${selectedClass}`, x: label.x + 6, y: label.y + 4 }, formattedValue),
      );
    }),
  );
}

function layoutLabels(annotations, projectAnchor) {
  const slots = new Set();
  const sorted = [...annotations].sort((left, right) => String(left.id).localeCompare(String(right.id)));
  return sorted.flatMap((annotation) => {
    const anchor = resolveAnchor(annotation, projectAnchor);
    if (!anchor) {
      return [];
    }
    const desiredSlot = Math.max(0, Math.round(anchor.y / SLOT_HEIGHT));
    const slot = nextAvailableSlot(desiredSlot, slots);
    slots.add(slot);
    return [{
      annotation,
      anchor,
      label: {
        x: anchor.x < VIEWPORT_MIDPOINT ? RIGHT_LABEL_RAIL : LEFT_LABEL_RAIL,
        y: slot * SLOT_HEIGHT + SLOT_HEIGHT / 2,
      },
    }];
  });
}

function resolveAnchor(annotation, projectAnchor) {
  const projected = projectAnchor?.(annotation.anchor, annotation) || annotation.anchor;
  return Number.isFinite(projected?.x) && Number.isFinite(projected?.y) ? projected : null;
}

function nextAvailableSlot(desiredSlot, slots) {
  let slot = desiredSlot;
  while (slots.has(slot)) {
    slot += 1;
  }
  return slot;
}
