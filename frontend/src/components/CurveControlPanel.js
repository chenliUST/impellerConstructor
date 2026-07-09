import React from "react";

const h = React.createElement;

const defaultSegmentOrder = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"];

export function CurveControlPanel({ curves = {}, onChange }) {
  const entries = Object.entries(curves || {});
  if (!entries.length) {
    return null;
  }

  function emitPointChange(curveId, segmentId, pointIndex, axisIndex, rawValue) {
    const result = updateNestedPoint(curves, curveId, segmentId, pointIndex, axisIndex, rawValue);
    const nextCurve = result.curve || {};
    const payload = {};
    if (segmentId && nextCurve.coordinate_system === "blade_to_blade_s_q_mm") {
      payload.blade_to_blade_loop_family_overrides = {
        [curveId]: {
          segments: {
            [segmentId]: result.segment,
          },
        },
      };
    } else {
      payload.curve_overrides = {
        [curveId]: nextCurve,
      };
    }
    if (segmentId && nextCurve.coordinate_system !== "blade_to_blade_s_q_mm") {
      payload.section_loop_overrides = {
        [curveId]: {
          segments: {
            [segmentId]: result.segment,
          },
        },
      };
    } else if (segmentId) {
      // no-op: blade-to-blade edits intentionally emit only blade_to_blade_loop_family_overrides
    }
    onChange?.(payload);
  }

  return h(
    "section",
    { className: "panel-section curve-control-panel", "aria-label": "Curve controls" },
    h("div", { className: "section-title" }, "Curve controls"),
    entries.map(([curveId, curve]) =>
      h(
        "div",
        { className: "curve-control-group", key: curveId },
        h("h3", null, curve.label || curveId),
        curve.coordinate_system ? h("p", { className: "curve-coordinate-system" }, curve.coordinate_system) : null,
        curve.coordinate_system === "blade_to_blade_s_q_mm"
          ? renderBladeToBladeLoopFamily(curveId, curve, emitPointChange)
          : curve.segments
          ? renderSegmentedCurve(curveId, curve, emitPointChange)
          : renderControlCurve(curveId, curve.label || curveId, curve, emitPointChange),
      ),
    ),
  );
}

export function updateNestedPoint(curves, curveId, segmentId, pointIndex, axisIndex, rawValue) {
  const nextCurves = clonePlainObject(curves);
  const curve = nextCurves[curveId] || {};
  const target = segmentId ? curve.segments?.[segmentId] || {} : curve;
  const controlPoints = Array.isArray(target.control_points) ? target.control_points : [];
  const numericValue = Number(rawValue);
  const nextValue = Number.isFinite(numericValue) ? numericValue : Number(controlPoints[pointIndex]?.[axisIndex] || 0);
  const nextPoints = controlPoints.map((point, index) =>
    index === pointIndex
      ? point.map((coordinate, coordinateIndex) => (coordinateIndex === axisIndex ? nextValue : coordinate))
      : point,
  );

  target.control_points = nextPoints;
  if (segmentId) {
    curve.segments = {
      ...(curve.segments || {}),
      [segmentId]: target,
    };
  }
  nextCurves[curveId] = curve;

  return {
    curves: nextCurves,
    curve,
    segment: segmentId ? target : null,
  };
}

function renderSegmentedCurve(curveId, curve, emitPointChange) {
  const segmentEntries = orderedSegmentEntries(curve.segments || {}, curve.segment_order);
  const allPoints = segmentEntries.flatMap(([, segment]) => segment.control_points || []);
  const previewLines = [];

  if (curve.closed_loop_preview?.length > 1) {
    previewLines.push({
      id: `${curveId}:closed_loop_preview`,
      points: curve.closed_loop_preview,
      className: "closed-loop-preview",
    });
  }

  return h(
    "div",
    { className: "section-loop-curve-editor" },
    renderCurvePreview(allPoints, [], `${curve.label || curveId} control polygon`, previewLines),
    segmentEntries.map(([segmentId, segment]) =>
      h(
        "div",
        { className: "curve-segment", key: segmentId },
        h("div", { className: "curve-segment-label" }, segment.label || segmentId),
        renderCurvePreview(segment.control_points || [], segment.sampled_points || [], `${segmentId} control polygon`),
        renderPointRows(segment.control_points || [], `${segmentId} control point`, (pointIndex, axisIndex, value) =>
          emitPointChange(curveId, segmentId, pointIndex, axisIndex, value),
        ),
      ),
    ),
  );
}

function renderBladeToBladeLoopFamily(curveId, curve, emitPointChange) {
  const segmentEntries = orderedSegmentEntries(curve.segments || {}, curve.segment_order);
  const spanStations = Array.isArray(curve.span_stations_h) ? curve.span_stations_h.join(", ") : "";

  return h(
    "div",
    { className: "section-loop-curve-editor blade-to-blade-loop-family-editor" },
    h("p", { className: "curve-span-stations" }, `span stations: ${spanStations}`),
    renderBladeToBladePreview(curve.label || curveId, segmentEntries),
    segmentEntries.map(([segmentId, segment]) =>
      h(
        "div",
        { className: "curve-segment", key: segmentId },
        h(
          "div",
          { className: "curve-segment-label" },
          h("span", { className: "curve-segment-swatch", style: { color: segment.color || "#475569" } }, "■"),
          " ",
          segment.label || segmentId,
        ),
        renderPointRows(segment.control_points || [], `${segmentId} control point`, (pointIndex, axisIndex, value) =>
          emitPointChange(curveId, segmentId, pointIndex, axisIndex, value),
        ),
      ),
    ),
  );
}

function renderControlCurve(curveId, label, curve, emitPointChange) {
  const points = curve.control_points || [];
  return h(
    "div",
    { className: "curve-control-block" },
    renderCurvePreview(points, curve.sampled_points || [], `${label} control polygon`),
    renderPointRows(points, `${label} control point`, (pointIndex, axisIndex, value) =>
      emitPointChange(curveId, null, pointIndex, axisIndex, value),
    ),
  );
}

function renderBladeToBladePreview(label, segmentEntries) {
  const controlPoints = segmentEntries.flatMap(([, segment]) => segment.control_points || []);
  const normalized = normalizePointSets(
    segmentEntries.map(([segmentId, segment]) => ({
      id: segmentId,
      color: segment.color,
      points: segment.control_points || [],
    })),
  );

  return h(
    "svg",
    { className: "curve-control-preview", viewBox: "0 0 180 92", role: "img", "aria-label": `${label} preview` },
    h("line", { x1: 18, y1: 10, x2: 18, y2: 74, stroke: "#cbd5e1", strokeWidth: 1 }),
    h("line", { x1: 18, y1: 74, x2: 170, y2: 74, stroke: "#cbd5e1", strokeWidth: 1 }),
    h("text", { x: 174, y: 82, fill: "#64748b", fontSize: 9, textAnchor: "end" }, "s"),
    h("text", { x: 10, y: 16, fill: "#64748b", fontSize: 9 }, "q mm"),
    normalized.map((segment) =>
      h("polyline", {
        key: `${segment.id}:line`,
        points: pointsAttribute(segment.points),
        fill: "none",
        stroke: segment.color,
        strokeWidth: 2,
      }),
    ),
    normalized.flatMap((segment) =>
      segment.points.map((point, index) =>
        h("circle", {
          key: `${segment.id}:${index}`,
          cx: point[0],
          cy: point[1],
          r: 2.75,
          fill: segment.color,
        }),
      ),
    ),
    controlPoints.length
      ? h("text", { x: 170, y: 16, fill: "#64748b", fontSize: 9, textAnchor: "end" }, `${controlPoints.length} pts`)
      : null,
  );
}

function renderCurvePreview(controlPoints, sampledPoints, label, extraPolylines = []) {
  const normalizedControl = normalizePoints(controlPoints);
  const normalizedSampled = normalizePoints(sampledPoints.length ? sampledPoints : controlPoints);
  const normalizedExtras = extraPolylines.map((polyline) => ({
    ...polyline,
    points: normalizePoints(polyline.points || []),
  }));

  return h(
    "svg",
    { className: "curve-control-preview", viewBox: "0 0 180 72", role: "img", "aria-label": label },
    normalizedExtras.map((polyline) =>
      h("polyline", {
        className: polyline.className,
        key: polyline.id,
        points: pointsAttribute(polyline.points),
        fill: "none",
      }),
    ),
    h("polyline", {
      className: "curve-sampled-line",
      points: pointsAttribute(normalizedSampled),
      fill: "none",
    }),
    h("polyline", {
      className: "curve-control-polygon",
      points: pointsAttribute(normalizedControl),
      fill: "none",
    }),
    normalizedControl.map((point, index) =>
      h("circle", {
        className: "curve-control-point",
        key: index,
        cx: point[0],
        cy: point[1],
        r: 3,
      }),
    ),
  );
}

function renderPointRows(points, label, onPointChange) {
  return h(
    "div",
    { className: "curve-control-table" },
    points.map((point, pointIndex) =>
      h(
        "div",
        { className: "coordinate-row", key: pointIndex },
        h("span", { className: "coordinate-index" }, pointIndex + 1),
        ["x", "y"].map((axis, axisIndex) =>
          h(
            "label",
            { className: "coordinate-field", key: axis },
            axis,
            h("input", {
              "aria-label": `${label} ${pointIndex + 1} ${axis}`,
              type: "number",
              step: 1,
              value: point[axisIndex],
              onChange: (event) => onPointChange(pointIndex, axisIndex, event.target.value),
            }),
          ),
        ),
      ),
    ),
  );
}

function orderedSegmentEntries(segments, segmentOrder = defaultSegmentOrder) {
  const knownEntries = segmentOrder.filter((segmentId) => segments[segmentId]).map((segmentId) => [segmentId, segments[segmentId]]);
  const extraEntries = Object.entries(segments).filter(([segmentId]) => !segmentOrder.includes(segmentId));
  return [...knownEntries, ...extraEntries];
}

function normalizePointSets(pointSets) {
  const points = pointSets.flatMap((item) => item.points || []);
  if (!points.length) {
    return pointSets.map((item) => ({ ...item, color: item.color || "#475569", points: [] }));
  }
  const xs = points.map((point) => Number(point[0]));
  const ys = points.map((point) => Number(point[1]));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1e-9);
  const spanY = Math.max(maxY - minY, 1e-9);

  return pointSets.map((item) => ({
    ...item,
    color: item.color || "#475569",
    points: (item.points || []).map((point) => [
      24 + ((Number(point[0]) - minX) / spanX) * 140,
      66 - ((Number(point[1]) - minY) / spanY) * 48,
    ]),
  }));
}

function normalizePoints(points) {
  if (!points.length) {
    return [];
  }
  const xs = points.map((point) => Number(point[0]));
  const ys = points.map((point) => Number(point[1]));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1e-9);
  const spanY = Math.max(maxY - minY, 1e-9);

  return points.map((point) => [
    12 + ((Number(point[0]) - minX) / spanX) * 156,
    60 - ((Number(point[1]) - minY) / spanY) * 48,
  ]);
}

function pointsAttribute(points) {
  return points.map((point) => `${round(point[0])},${round(point[1])}`).join(" ");
}

function round(value) {
  return Math.round(value * 100) / 100;
}

function clonePlainObject(value) {
  return value ? JSON.parse(JSON.stringify(value)) : {};
}
