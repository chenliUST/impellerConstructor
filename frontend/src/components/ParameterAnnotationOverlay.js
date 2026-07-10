import React from "react";

const h = React.createElement;

export function ParameterAnnotationOverlay({
  annotations = [],
  selectedAnnotationId = null,
  onSelectAnnotation = null,
}) {
  return h(
    "div",
    { className: "parameter-annotation-overlay" },
    [...annotations]
      .sort((left, right) => String(left.id).localeCompare(String(right.id)))
      .map((annotation) => {
      const { compactText, fullText } = annotationText(annotation);
      const active = selectedAnnotationId === annotation.id;
      const actionable = annotation.targetSurfaceIds?.length > 0;
      const props = {
        key: annotation.id,
        className: `inspection-label-row${active ? " selected" : ""}`,
        title: fullText,
        "data-annotation-id": annotation.id,
      };
      return actionable
        ? h("button", {
            ...props,
            type: "button",
            "aria-pressed": active,
            onClick: () => onSelectAnnotation?.(annotation),
          }, compactText)
        : h("div", props, compactText);
      }),
  );
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
