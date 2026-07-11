import React from "react";

import { layoutEngineeringDimension, projectEngineeringFeature } from "../engineeringDrawingModel.js?v=1.1.5";

const h = React.createElement;
const VIEWBOX = { x: 0, y: 0, width: 1000, height: 700 };

export function EngineeringDrawingView({ viewId, contextPrimitives = [], selectedParameter = null }) {
  const selectedFeatures = projectSelectedFeatures(selectedParameter?.features, viewId);
  const dimensions = selectedParameter?.dimension
    ? layoutEngineeringDimension(
      selectedParameter.dimension,
      { viewId, primitives: [...contextPrimitives, ...selectedFeatures] },
      VIEWBOX,
    )
    : [];
  const label = selectedParameter?.label
    ? `${viewLabel(viewId)} engineering drawing for ${selectedParameter.label}`
    : `${viewLabel(viewId)} engineering drawing`;

  return h(
    "section",
    { className: "engineering-drawing-view", "aria-label": label },
    h(
      "svg",
      {
        className: "engineering-drawing-canvas",
        viewBox: `${VIEWBOX.x} ${VIEWBOX.y} ${VIEWBOX.width} ${VIEWBOX.height}`,
        role: "img",
        "aria-label": label,
      },
      contextPrimitives.map((primitive, index) => renderPrimitive(primitive, "engineering-context", `context:${index}`)),
      selectedFeatures.map((primitive, index) => renderSelectedFeature(primitive, `feature:${index}`)),
      dimensions.map((primitive, index) => renderPrimitive(primitive, "engineering-dimension", `dimension:${index}`)),
    ),
  );
}

function projectSelectedFeatures(features, viewId) {
  return (Array.isArray(features) ? features : []).flatMap((feature) => {
    const primitive = projectEngineeringFeature({ ...feature, className: "engineering-feature" }, viewId);
    return primitive ? [{ ...primitive, sourceKind: feature.kind }] : [];
  });
}

function renderSelectedFeature(primitive, key) {
  if (primitive.sourceKind === "nurbs_curve" && primitive.kind === "path") {
    return h("polygon", {
      key,
      className: "engineering-feature engineering-control-polygon",
      points: pointsAttribute(primitive.points),
      fill: "none",
    });
  }
  return renderPrimitive(primitive, "engineering-feature", key);
}

function renderPrimitive(primitive, className, key) {
  if (primitive?.kind === "path") {
    return h("path", { key, className, d: pathData(primitive.points), fill: "none" });
  }
  if (primitive?.kind === "point") {
    return h("circle", { key, className, cx: primitive.point?.[0], cy: primitive.point?.[1], r: 5 });
  }
  if (primitive?.kind === "dimension") {
    return h(
      "g",
      { key, className },
      renderLine(primitive.line, `${key}:line`),
      (primitive.extensions || []).map((line, index) => renderLine(line, `${key}:extension:${index}`)),
      (primitive.arrows || []).map((arrow, index) => renderArrow(arrow, `${key}:arrow:${index}`)),
      renderText(primitive.text, `${key}:text`),
      primitive.note ? renderText(primitive.note, `${key}:note`) : null,
    );
  }
  return null;
}

function renderLine(primitive, key) {
  const [start, end] = primitive?.points || [];
  return start && end
    ? h("line", { key, x1: start[0], y1: start[1], x2: end[0], y2: end[1] })
    : null;
}

function renderArrow(primitive, key) {
  return h("path", { key, d: pathData(primitive?.points), fill: "none" });
}

function renderText(text, key) {
  return text?.point
    ? h("text", { key, x: text.point[0], y: text.point[1], textAnchor: "middle" }, text.value)
    : null;
}

function pathData(points) {
  return (Array.isArray(points) ? points : [])
    .filter(finitePoint)
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point[0]} ${point[1]}`)
    .join(" ");
}

function pointsAttribute(points) {
  return (Array.isArray(points) ? points : []).filter(finitePoint).map((point) => point.join(",")).join(" ");
}

function finitePoint(point) {
  return Array.isArray(point) && point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1]);
}

function viewLabel(viewId) {
  return { top: "Top", meridional: "Meridional", s_q: "S-Q" }[viewId] || "Engineering";
}
