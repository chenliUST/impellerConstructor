import React, { useRef, useState } from "react";

import {
  curveEditorBounds,
  curveOverridesPayload,
  curveToScreen,
  defaultBladeCurveControls,
  screenToCurvePoint,
  updateCurvePoint,
  validateCurveOverrides,
} from "../bladeCurveEditorModel.js";

const h = React.createElement;
const viewport = { width: 260, height: 72 };

export function BladeCurveEditor({ parameters, curveOverrides, onCurveOverridesChange, onResetCurveOverrides }) {
  const controls = curveOverrides || defaultBladeCurveControls(parameters);
  const validation = validateCurveOverrides(controls);

  function movePoint(group, curveId, pointIndex, nextPoint) {
    onCurveOverridesChange(curveOverridesPayload(updateCurvePoint(controls, group, curveId, pointIndex, nextPoint)));
  }

  return h(
    "section",
    { className: "panel-section blade-curve-editor" },
    h("div", { className: "section-title" }, "Blade / edge curves"),
    Object.entries(controls).map(([group, curves]) =>
      h(
        "div",
        { className: "curve-group", key: group },
        h("h3", null, group),
        Object.entries(curves).map(([curveId, curve]) =>
          h(CurveSvg, { key: `${group}-${curveId}`, group, curveId, curve, onMovePoint: movePoint }),
        ),
      ),
    ),
    h(
      "p",
      { className: validation.status === "PASS" ? "small-note" : "small-note error" },
      validation.reason || "Drag intrinsic curve handles",
    ),
    h("button", { className: "secondary-action", type: "button", onClick: onResetCurveOverrides }, "Reset curves"),
  );
}

function CurveSvg({ group, curveId, curve, onMovePoint }) {
  const svgRef = useRef(null);
  const [activePoint, setActivePoint] = useState(null);
  const bounds = curveEditorBounds(curve);

  function handlePointerMove(event) {
    if (activePoint === null || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const local = [
      ((event.clientX - rect.left) / rect.width) * viewport.width,
      ((event.clientY - rect.top) / rect.height) * viewport.height,
    ];
    onMovePoint(group, curveId, activePoint, screenToCurvePoint(local, bounds, viewport));
  }

  return h(
    "div",
    { className: "curve-row curve-row-stacked" },
    h("div", { className: "curve-row-title" }, curveId),
    h("small", null, curve.coordinate_system),
    h(
      "svg",
      {
        ref: svgRef,
        viewBox: `0 0 ${viewport.width} ${viewport.height}`,
        className: "curve-editor-svg small-curve-editor-svg",
        onPointerMove: handlePointerMove,
        onPointerUp: () => setActivePoint(null),
        onPointerLeave: () => setActivePoint(null),
      },
      h("polyline", {
        points: curve.control_points.map((point) => curveToScreen(point, bounds, viewport).join(",")).join(" "),
        fill: "none",
        stroke: "#2f6f9e",
        strokeWidth: 2,
      }),
      curve.control_points.map((point, index) => {
        const [x, y] = curveToScreen(point, bounds, viewport);
        return h(
          "g",
          {
            key: index,
            className: "curve-handle",
            onPointerDown: (event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              setActivePoint(index);
            },
          },
          h("circle", { cx: x, cy: y, r: 4, fill: "#b4512a" }),
          h("title", null, `Drag ${curveId} control point ${index}`),
        );
      }),
    ),
  );
}
