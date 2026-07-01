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
const viewport = { width: 420, height: 128 };

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
  const [selectedPoint, setSelectedPoint] = useState(0);
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

  function updatePointCoordinate(pointIndex, coordinateIndex, value) {
    if (value === "") return;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    const nextPoint = [...curve.control_points[pointIndex]];
    nextPoint[coordinateIndex] = numeric;
    setSelectedPoint(pointIndex);
    onMovePoint(group, curveId, pointIndex, nextPoint);
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
        const selected = selectedPoint === index;
        return h(
          "g",
          {
            key: index,
            className: selected ? "curve-handle selected" : "curve-handle",
            onPointerDown: (event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              event.preventDefault();
              setSelectedPoint(index);
              setActivePoint(index);
            },
          },
          h("circle", { cx: x, cy: y, r: selected ? 6 : 4, fill: "#b4512a" }),
          h("text", { x: x + 7, y: y - 6, className: "svg-label" }, `P${index}`),
          h("title", null, `Drag ${curveId} control point ${index}`),
          h("rect", { x: x - 12, y: y - 12, width: 24, height: 24, fill: "transparent" }),
        );
      }),
    ),
    h(
      "div",
      { className: "curve-control-table" },
      curve.control_points.map((point, index) =>
        h(
          "div",
          {
            key: `${curveId}-${index}`,
            className: selectedPoint === index ? "coordinate-row selected" : "coordinate-row",
            onPointerDown: () => setSelectedPoint(index),
          },
          h("span", { className: "coordinate-index" }, `P${index}`),
          h(CurveInput, {
            label: point[0] === 0 || point[0] === 1 ? "t lock" : "t",
            value: point[0],
            step: "0.001",
            onChange: (value) => updatePointCoordinate(index, 0, value),
          }),
          h(CurveInput, {
            label: valueLabel(curve.coordinate_system),
            value: point[1],
            step: "0.001",
            onChange: (value) => updatePointCoordinate(index, 1, value),
          }),
        ),
      ),
    ),
  );
}

function CurveInput({ label, value, step, onChange }) {
  return h(
    "label",
    { className: "coordinate-field" },
    h("span", null, label),
    h("input", {
      type: "number",
      step,
      value,
      onChange: (event) => onChange(event.target.value),
    }),
  );
}

function valueLabel(coordinateSystem) {
  if (coordinateSystem.endsWith("_deg")) return "deg";
  if (coordinateSystem.endsWith("_mm")) return "mm";
  if (coordinateSystem === "v_support_u_offset") return "du";
  return "value";
}
