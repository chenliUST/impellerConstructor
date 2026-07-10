import React from "react";

const h = React.createElement;
const SLOT_HEIGHT = 28;
const DEFAULT_VIEWPORT_WIDTH = 1000;
const DEFAULT_VIEWPORT_HEIGHT = 700;
const HORIZONTAL_PADDING = 12;
const VERTICAL_PADDING = 14;
const MIN_LABEL_WIDTH = 84;
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
        h(
          "text",
          { className: `inspection-label${selectedClass}`, x: label.x + 6, y: label.y + 4 },
          h("title", null, fullText),
          visibleText,
        ),
      );
    }),
  );
}

function layoutLabels(annotations, projectAnchor, viewport) {
  const slots = new Set();
  const sorted = [...annotations].sort((left, right) => String(left.id).localeCompare(String(right.id)));
  const projected = sorted.flatMap((annotation) => {
    const anchor = resolveAnchor(annotation, projectAnchor);
    return anchor ? [{ annotation, anchor }] : [];
  });
  const slotCount = viewportSlotCount(viewport.height);
  const retained = retainSelectedWithinCapacity(projected, slotCount);

  return retained.map(({ annotation, anchor }) => {
    const desiredSlot = desiredViewportSlot(anchor.y, viewport.height, slotCount);
    const slot = nextAvailableSlot(desiredSlot, slots, slotCount);
    slots.add(slot);
    const x = labelRailX(anchor.x, viewport.width);
    return {
      annotation,
      anchor,
      label: {
        x,
        y: VERTICAL_PADDING + slot * SLOT_HEIGHT,
        maxCharacters: maxVisibleCharacters(x, viewport.width),
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
  if (projected.length <= capacity || selected.length >= capacity) {
    return selected.length >= capacity ? selected : projected;
  }
  const remaining = projected.filter(({ annotation }) => !annotation.selected).slice(0, capacity - selected.length);
  const retainedIds = new Set([...selected, ...remaining].map(({ annotation }) => annotation.id));
  return projected.filter(({ annotation }) => retainedIds.has(annotation.id));
}

function desiredViewportSlot(anchorY, viewportHeight, slotCount) {
  const clampedY = clamp(anchorY, VERTICAL_PADDING, Math.max(VERTICAL_PADDING, viewportHeight - VERTICAL_PADDING));
  return clamp(Math.round((clampedY - VERTICAL_PADDING) / SLOT_HEIGHT), 0, slotCount - 1);
}

function nextAvailableSlot(desiredSlot, slots, slotCount) {
  for (let slot = desiredSlot; slot < slotCount; slot += 1) {
    if (!slots.has(slot)) {
      return slot;
    }
  }
  for (let slot = 0; slot < desiredSlot; slot += 1) {
    if (!slots.has(slot)) {
      return slot;
    }
  }
  return desiredSlot;
}

function labelRailX(anchorX, viewportWidth) {
  const maximumRail = Math.max(HORIZONTAL_PADDING, viewportWidth - HORIZONTAL_PADDING - MIN_LABEL_WIDTH);
  const preferredRail = anchorX < viewportWidth / 2 ? viewportWidth * 0.62 : viewportWidth * 0.08;
  return clamp(preferredRail, HORIZONTAL_PADDING, maximumRail);
}

function maxVisibleCharacters(labelX, viewportWidth) {
  const availableWidth = Math.max(28, viewportWidth - HORIZONTAL_PADDING - labelX - 6);
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
