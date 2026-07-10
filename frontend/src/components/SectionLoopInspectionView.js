import React from "react";

const h = React.createElement;

const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 700;
const PADDING = 70;

const SEGMENT_CLASS = {
  pressure_side: "pressure-side",
  suction_side: "suction-side",
  leading_edge: "leading-edge",
  trailing_edge: "trailing-edge",
};

const SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"];

export function SectionLoopInspectionView({ loop, selection = {}, annotationLevel = "key", annotations = [], onSelect }) {
  const segments = sectionSegments(loop);
  const plotTop = Math.min(260, PADDING + annotations.length * 28);
  const joinMetricCount = Object.keys(loop?.join_metrics || {}).length;
  const plotBottom = Math.max(PADDING, joinMetricCount * 22 + 40);
  const transform = fitPoints(segments.flatMap((segment) => [
    ...segment.points,
    ...segment.controls.map((control) => control.point),
  ]), plotTop, plotBottom);
  const controlsVisible = annotationLevel === "selected" || annotationLevel === "all";

  return h(
    "section",
    { className: "section-loop-inspection-view", "aria-label": "S-Q section loop inspection" },
    h(
      "svg",
      {
        className: "section-loop-inspection-svg",
        viewBox: `0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`,
        role: "img",
        "aria-label": loop?.section_loop_id ? `S-Q section loop ${loop.section_loop_id}` : "No S-Q section loop selected",
      },
      renderAxes(plotTop, plotBottom),
      segments.map((segment) => renderActualSegment(segment, transform, selection, onSelect)),
      controlsVisible ? segments.map((segment) => renderControlGeometry(segment, transform, selection, onSelect)) : null,
      renderJoinMetrics(loop?.join_metrics || {}, plotBottom),
      !segments.length ? h("text", { className: "section-loop-empty", x: 500, y: 350, textAnchor: "middle" }, "No section loop selected") : null,
    ),
  );
}

function sectionSegments(loop) {
  const entries = Object.entries(loop?.segment_references || {});
  const ordered = entries.sort(([left], [right]) => segmentRank(left) - segmentRank(right) || left.localeCompare(right));
  return ordered.map(([segmentName, segment]) => ({
    segmentName,
    sectionSegmentId: segment.section_segment_id || segmentName,
    points: finitePoints(segment.display_points_s_q_mm),
    controls: (Array.isArray(segment.control_points) ? segment.control_points : [])
      .filter((control) => typeof control?.control_point_id === "string" && finitePoints([control.display_coordinates_s_q_mm]).length)
      .map((control) => ({ id: control.control_point_id, point: control.display_coordinates_s_q_mm })),
  }));
}

function segmentRank(segmentId) {
  const index = SEGMENT_ORDER.indexOf(segmentId);
  return index === -1 ? SEGMENT_ORDER.length : index;
}

function finitePoints(points) {
  return (Array.isArray(points) ? points : []).filter(
    (point) => Array.isArray(point) && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1])),
  );
}

function fitPoints(points, plotTop = PADDING, plotBottom = PADDING) {
  const finite = finitePoints(points);
  if (!finite.length) {
    return (point) => [VIEWBOX_WIDTH / 2, VIEWBOX_HEIGHT / 2];
  }

  const sValues = finite.map((point) => Number(point[0]));
  const qValues = finite.map((point) => Number(point[1]));
  const minS = Math.min(...sValues);
  const maxS = Math.max(...sValues);
  const minQ = Math.min(...qValues);
  const maxQ = Math.max(...qValues);
  const spanS = Math.max(maxS - minS, 1e-9);
  const spanQ = Math.max(maxQ - minQ, 1e-9);
  const availableHeight = VIEWBOX_HEIGHT - plotTop - plotBottom;
  const scale = Math.min((VIEWBOX_WIDTH - PADDING * 2) / spanS, availableHeight / spanQ);
  const drawnWidth = spanS * scale;
  const drawnHeight = spanQ * scale;
  const offsetS = (VIEWBOX_WIDTH - drawnWidth) / 2 - minS * scale;
  const offsetQ = plotTop + (availableHeight - drawnHeight) / 2 + maxQ * scale;

  return (point) => [offsetS + Number(point[0]) * scale, offsetQ - Number(point[1]) * scale];
}

function renderAxes(plotTop, plotBottom) {
  return h(
    "g",
    { className: "section-loop-axes" },
    h("line", { x1: PADDING, y1: VIEWBOX_HEIGHT - plotBottom, x2: VIEWBOX_WIDTH - PADDING, y2: VIEWBOX_HEIGHT - plotBottom }),
    h("line", { x1: PADDING, y1: plotTop, x2: PADDING, y2: VIEWBOX_HEIGHT - plotBottom }),
    h("text", { x: VIEWBOX_WIDTH - PADDING, y: VIEWBOX_HEIGHT - 36, textAnchor: "end" }, "S (mm)"),
    h("text", { x: PADDING + 12, y: plotTop + 16 }, "Q (mm)"),
  );
}

function renderActualSegment(segment, transform, selection, onSelect) {
  const className = ["actual-section-loop", SEGMENT_CLASS[segment.segmentName] || "section-segment"]
    .concat(selection.sectionSegmentId === segment.sectionSegmentId ? ["selected"] : [])
    .join(" ");
  const nextSelection = { sectionSegmentId: segment.sectionSegmentId, controlPointId: null };
  return h("polyline", {
    key: `${segment.sectionSegmentId}:actual`,
    className,
    points: pointsAttribute(segment.points, transform),
    fill: "none",
    role: "button",
    tabIndex: 0,
    "aria-label": `Select ${segment.segmentName}`,
    onClick: () => onSelect?.(nextSelection),
    onKeyDown: (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect?.(nextSelection);
      }
    },
  });
}

function renderControlGeometry(segment, transform, selection, onSelect) {
  const className = ["control-polygon", SEGMENT_CLASS[segment.segmentName] || "section-segment"]
    .concat(selection.sectionSegmentId === segment.sectionSegmentId ? ["selected"] : [])
    .join(" ");
  return h(
    "g",
    { key: `${segment.sectionSegmentId}:control` },
    h("polyline", { className, points: pointsAttribute(segment.controls.map((control) => control.point), transform), fill: "none" }),
    segment.controls.map((control, pointIndex) => {
      const point = control.point;
      const [cx, cy] = transform(point);
      const isSelected = selection.controlPointId === control.id;
      const nextSelection = {
        sectionSegmentId: segment.sectionSegmentId,
        controlPointId: control.id,
      };
      return h("circle", {
        key: control.id,
        className: `control-point ${SEGMENT_CLASS[segment.segmentName] || "section-segment"}${isSelected ? " selected" : ""}`,
        cx,
        cy,
        r: 7,
        role: "button",
        tabIndex: 0,
        "aria-label": `${segment.segmentName} control point ${pointIndex + 1}`,
        onClick: () => onSelect?.(nextSelection),
        onKeyDown: (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect?.(nextSelection);
          }
        },
      });
    }),
  );
}

function renderJoinMetrics(joinMetrics, plotBottom) {
  const entries = Object.entries(joinMetrics);
  const lineHeight = 22;
  const firstLineY = VIEWBOX_HEIGHT - plotBottom + 24;
  return h(
    "g",
    { className: "section-loop-join-metrics" },
    entries.map(([joinId, metrics], index) =>
      h(
        "text",
        { key: joinId, x: PADDING, y: firstLineY + index * lineHeight },
        `${joinId}: ${metrics.status || "UNKNOWN"} | gap ${metrics.position_gap_mm} mm | angle ${metrics.tangent_angle_deg} deg | curvature ${metrics.curvature_proxy_mismatch}`,
      ),
    ),
  );
}

function pointsAttribute(points, transform) {
  return points.map((point) => transform(point).map(round).join(",")).join(" ");
}

function round(value) {
  return Math.round(value * 100) / 100;
}
