import React from "react";

const h = React.createElement;
const SLOT_HEIGHT = 28;
const DEFAULT_VIEWPORT_WIDTH = 1000;
const DEFAULT_VIEWPORT_HEIGHT = 700;
const HORIZONTAL_PADDING = 12;
const VERTICAL_PADDING = 14;
const LABEL_HEIGHT = 22;
const LANE_GAP = 8;
const APPROXIMATE_CHARACTER_WIDTH = 7;

export function ParameterAnnotationOverlay({
  annotations = [],
  projectAnchor,
  viewportWidth = DEFAULT_VIEWPORT_WIDTH,
  viewportHeight = DEFAULT_VIEWPORT_HEIGHT,
}) {
  const viewport = {
    width: positiveDimension(viewportWidth, DEFAULT_VIEWPORT_WIDTH),
    height: positiveDimension(viewportHeight, DEFAULT_VIEWPORT_HEIGHT),
  };
  const labels = layoutLabels(annotations, projectAnchor, viewport);

  return h(
    "g",
    { className: "parameter-annotation-overlay" },
    h(
      "defs",
      null,
      labels.map(({ label }) =>
        h(
          "clipPath",
          { key: label.clipId, id: label.clipId, clipPathUnits: "userSpaceOnUse" },
          h("rect", {
            x: label.x,
            y: label.y - label.height / 2,
            width: label.width,
            height: label.height,
          }),
        ),
      ),
    ),
    labels.map(({ annotation, anchor, label }) => {
      const { compactText, fullText } = annotationText(annotation);
      const visibleText = truncateText(compactText, label.maxCharacters);
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
        h("rect", {
          className: `inspection-label-region${selectedClass}`,
          x: label.x,
          y: label.y - label.height / 2,
          width: label.width,
          height: label.height,
          rx: 2,
        }),
        h(
          "text",
          {
            className: `inspection-label${selectedClass}`,
            x: label.x + Math.min(6, label.width / 2),
            y: label.y + 4,
            clipPath: `url(#${label.clipId})`,
          },
          h("title", null, fullText),
          visibleText,
        ),
      );
    }),
  );
}

function layoutLabels(annotations, projectAnchor, viewport) {
  const sorted = [...annotations].sort((left, right) => String(left.id).localeCompare(String(right.id)));
  const projected = sorted.flatMap((annotation) => {
    const anchor = resolveAnchor(annotation, projectAnchor);
    return anchor ? [{ annotation, anchor }] : [];
  });
  const slotCount = viewportSlotCount(viewport.height);
  const selectedCount = projected.filter(({ annotation }) => annotation.selected).length;
  const laneCount = Math.max(1, Math.ceil(selectedCount / slotCount));
  const capacity = laneCount * slotCount;
  const retained = retainSelectedWithinCapacity(projected, capacity);

  return retained.map(({ annotation, anchor }, index) => {
    const lane = Math.floor(index / slotCount);
    const slot = index % slotCount;
    const region = labelRegionForLane(lane, laneCount, viewport.width);
    const height = Math.min(LABEL_HEIGHT, viewport.height);
    return {
      annotation,
      anchor,
      label: {
        ...region,
        height,
        y: labelYForSlot(slot, viewport.height, height),
        clipId: clipIdFor(annotation.id, index),
        maxCharacters: maxVisibleCharacters(region.width),
      },
    };
  });
}

function resolveAnchor(annotation, projectAnchor) {
  const projected = projectAnchor?.(annotation.anchor, annotation) || annotation.anchor;
  return Number.isFinite(projected?.x) && Number.isFinite(projected?.y) ? projected : null;
}

function viewportSlotCount(viewportHeight) {
  const availableHeight = Math.max(0, viewportHeight - VERTICAL_PADDING * 2);
  return Math.max(1, Math.floor(availableHeight / SLOT_HEIGHT) + 1);
}

function retainSelectedWithinCapacity(projected, capacity) {
  const selected = projected.filter(({ annotation }) => annotation.selected);
  if (projected.length <= capacity) {
    return projected;
  }
  const remainingCapacity = Math.max(0, capacity - selected.length);
  const remaining = projected.filter(({ annotation }) => !annotation.selected).slice(0, remainingCapacity);
  const retainedIds = new Set([...selected, ...remaining].map(({ annotation }) => annotation.id));
  return projected.filter(({ annotation }) => retainedIds.has(annotation.id));
}

function labelRegionForLane(lane, laneCount, viewportWidth) {
  const inset = Math.min(HORIZONTAL_PADDING, viewportWidth / 4);
  const availableWidth = Math.max(1, viewportWidth - inset * 2);
  const laneWidth = availableWidth / laneCount;
  const gap = Math.min(LANE_GAP, Math.max(0, laneWidth - 1));
  return {
    x: inset + lane * laneWidth,
    width: Math.max(1, laneWidth - gap),
  };
}

function labelYForSlot(slot, viewportHeight, labelHeight) {
  const minimumY = labelHeight / 2;
  const maximumY = Math.max(minimumY, viewportHeight - labelHeight / 2);
  return clamp(VERTICAL_PADDING + slot * SLOT_HEIGHT, minimumY, maximumY);
}

function clipIdFor(annotationId, index) {
  const safeId = String(annotationId).replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 48) || "annotation";
  return `inspection-label-clip-${safeId}-${index}`;
}

function maxVisibleCharacters(labelWidth) {
  const availableWidth = Math.max(7, labelWidth - 12);
  return Math.max(4, Math.floor(availableWidth / APPROXIMATE_CHARACTER_WIDTH));
}

function annotationText(annotation) {
  const compactResolvedText = withUnit(compactValue(annotation.resolvedValue), annotation.unit);
  const compactRequestedText = withUnit(compactValue(annotation.requestedValue), annotation.requestedUnit);
  const fullResolvedText = withUnit(fullValue(annotation.resolvedValue), annotation.unit);
  const fullRequestedText = withUnit(fullValue(annotation.requestedValue), annotation.requestedUnit);
  const valuesMatch = annotation.requestedValue === annotation.resolvedValue;
  return {
    compactText: valuesMatch
      ? `${annotation.label}: ${compactResolvedText}`
      : `${annotation.label}: ${compactRequestedText} -> ${compactResolvedText}`,
    fullText: valuesMatch
      ? `${annotation.label}: ${fullResolvedText}`
      : `${annotation.label}: ${fullRequestedText} -> ${fullResolvedText}`,
  };
}

function compactValue(value) {
  if (Array.isArray(value)) {
    return `[${value.length} ${value.length === 1 ? "item" : "items"}]`;
  }
  if (value && typeof value === "object") {
    const fieldCount = Object.keys(value).length;
    return `{${fieldCount} ${fieldCount === 1 ? "field" : "fields"}}`;
  }
  return String(value);
}

function fullValue(value) {
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function withUnit(value, unit) {
  return unit ? `${value} ${unit}` : value;
}

function truncateText(value, maxCharacters) {
  if (value.length <= maxCharacters) {
    return value;
  }
  return maxCharacters <= 3 ? ".".repeat(maxCharacters) : `${value.slice(0, maxCharacters - 3)}...`;
}

function positiveDimension(value, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback;
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}
