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

export function SectionLoopInspectionView({ loop, selection = {}, annotationLevel = "key", onSelect }) {
  const segments = sectionSegments(loop);
  const transform = fitPoints(segments.flatMap((segment) => [...segment.points, ...segment.controlPoints]));
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
      renderAxes(),
      segments.map((segment) => renderActualSegment(segment, transform, selection)),
      controlsVisible ? segments.map((segment) => renderControlGeometry(segment, transform, selection, onSelect)) : null,
      renderJoinMetrics(loop?.join_metrics || {}),
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
    points: finitePoints(segment.points_s_q),
    controlPoints: finitePoints(segment.control_points_s_q),
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

function fitPoints(points) {
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
  const scale = Math.min((VIEWBOX_WIDTH - PADDING * 2) / spanS, (VIEWBOX_HEIGHT - PADDING * 2) / spanQ);
  const drawnWidth = spanS * scale;
  const drawnHeight = spanQ * scale;
  const offsetS = (VIEWBOX_WIDTH - drawnWidth) / 2 - minS * scale;
  const offsetQ = (VIEWBOX_HEIGHT - drawnHeight) / 2 + maxQ * scale;

  return (point) => [offsetS + Number(point[0]) * scale, offsetQ - Number(point[1]) * scale];
}

function renderAxes() {
  return h(
    "g",
    { className: "section-loop-axes" },
    h("line", { x1: PADDING, y1: VIEWBOX_HEIGHT - PADDING, x2: VIEWBOX_WIDTH - PADDING, y2: VIEWBOX_HEIGHT - PADDING }),
    h("line", { x1: PADDING, y1: PADDING, x2: PADDING, y2: VIEWBOX_HEIGHT - PADDING }),
    h("text", { x: VIEWBOX_WIDTH - PADDING, y: VIEWBOX_HEIGHT - 36, textAnchor: "end" }, "S"),
    h("text", { x: PADDING + 12, y: PADDING + 16 }, "Q"),
  );
}

function renderActualSegment(segment, transform, selection) {
  const className = ["actual-section-loop", SEGMENT_CLASS[segment.segmentName] || "section-segment"]
    .concat(selection.sectionSegmentId === segment.sectionSegmentId ? ["selected"] : [])
    .join(" ");
  return h("polyline", {
    key: `${segment.sectionSegmentId}:actual`,
    className,
    points: pointsAttribute(segment.points, transform),
    fill: "none",
  });
}

function renderControlGeometry(segment, transform, selection, onSelect) {
  const className = ["control-polygon", SEGMENT_CLASS[segment.segmentName] || "section-segment"]
    .concat(selection.sectionSegmentId === segment.sectionSegmentId ? ["selected"] : [])
    .join(" ");
  return h(
    "g",
    { key: `${segment.sectionSegmentId}:control` },
    h("polyline", { className, points: pointsAttribute(segment.controlPoints, transform), fill: "none" }),
    segment.controlPoints.map((point, pointIndex) => {
      const [cx, cy] = transform(point);
      const isSelected = selection.controlPointId === `${segment.sectionSegmentId}:cp_${pointIndex}`;
      const nextSelection = {
        sectionSegmentId: segment.sectionSegmentId,
        controlPointId: `${segment.sectionSegmentId}:cp_${pointIndex}`,
      };
      return h("circle", {
        key: `${segment.sectionSegmentId}:cp_${pointIndex}`,
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

function renderJoinMetrics(joinMetrics) {
  return h(
    "g",
    { className: "section-loop-join-metrics" },
    Object.entries(joinMetrics).map(([joinId, metrics], index) =>
      h(
        "text",
        { key: joinId, x: PADDING, y: PADDING + 34 + index * 22 },
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
