import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";
import vm from "node:vm";

import { curveControlsForPreset, presets } from "../appModel.js";

const root = resolve(import.meta.dirname, "..", "..");
const componentPath = resolve(root, "src/components/CurveControlPanel.js");

function loadCurveControlPanelModule() {
  const source = readFileSync(componentPath, "utf-8")
    .replace(
      'import React from "react";',
      'const React = { createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }) };',
    )
    .replace(/export function /g, "function ");
  const module = { exports: {} };
  const context = vm.createContext({ module, exports: module.exports, console, JSON, Math });
  vm.runInContext(`${source}\nmodule.exports = { CurveControlPanel, updateNestedPoint };`, context, {
    filename: componentPath,
  });
  return module.exports;
}

function collectElements(node, predicate, matches = []) {
  if (!node) {
    return matches;
  }
  if (Array.isArray(node)) {
    for (const child of node) {
      collectElements(child, predicate, matches);
    }
    return matches;
  }
  if (typeof node === "object") {
    if (predicate(node)) {
      matches.push(node);
    }
    collectElements(node.props?.children || [], predicate, matches);
  }
  return matches;
}

describe("CurveControlPanel source contract", () => {
  test("renders curve control points and control polygons", () => {
    assert.equal(existsSync(componentPath), true, "CurveControlPanel.js should exist");

    const source = readFileSync(componentPath, "utf-8");

    assert.match(source, /curve-control-panel/);
    assert.match(source, /curve-control-group/);
    assert.match(source, /curve-segment/);
    assert.match(source, /control point/i);
    assert.match(source, /polyline/);
    assert.match(source, /circle/);
    assert.match(source, /pressure_side/);
    assert.match(source, /leading_edge/);
    assert.match(source, /suction_side/);
    assert.match(source, /trailing_edge/);
  });

  test("emits structured curve and section-loop overrides", () => {
    assert.equal(existsSync(componentPath), true, "CurveControlPanel.js should exist");

    const source = readFileSync(componentPath, "utf-8");

    assert.match(source, /curve_overrides/);
    assert.match(source, /section_loop_overrides/);
    assert.match(source, /onChange/);
    assert.match(source, /updateNestedPoint/);
  });

  test("renders the closed-loop preview polyline from preset curve data", () => {
    const { CurveControlPanel } = loadCurveControlPanelModule();
    const preset = presets.find((item) => item.presetId === "radial_open_reference_v1_0");
    const bladeLoop = curveControlsForPreset(preset).blade_section_loop_template;
    const tree = CurveControlPanel({
      curves: {
        blade_section_loop_template: bladeLoop,
      },
    });

    const polylines = collectElements(tree, (node) => node.type === "polyline");
    const closedLoop = polylines.find((node) => node.props.className === "closed-loop-preview");

    assert.ok(closedLoop);
    assert.equal(closedLoop.props.points.split(" ").length, bladeLoop.closed_loop_preview.length);
  });

  test("editing a section-loop point emits a section-loop override payload", () => {
    const { CurveControlPanel } = loadCurveControlPanelModule();
    const preset = presets.find((item) => item.presetId === "radial_open_reference_v1_0");
    const bladeLoop = curveControlsForPreset(preset).blade_section_loop_template;
    let emitted = null;
    const tree = CurveControlPanel({
      curves: {
        blade_section_loop_template: bladeLoop,
      },
      onChange: (payload) => {
        emitted = payload;
      },
    });

    const pressureX = collectElements(
      tree,
      (node) => node.type === "input" && node.props?.["aria-label"] === "pressure_side control point 1 x",
    )[0];
    pressureX.props.onChange({ target: { value: "12" } });

    assert.equal(
      emitted.section_loop_overrides.blade_section_loop_template.segments.pressure_side.control_points[0][0],
      12,
    );
    assert.equal(emitted.curve_overrides.blade_section_loop_template.segments.pressure_side.control_points[0][0], 12);
  });

  test("renders V1.1 blade-to-blade loop family rows with control points", () => {
    const { CurveControlPanel } = loadCurveControlPanelModule();
    const controls = {
      blade_to_blade_loop_family: {
        label: "Blade-to-blade loop family",
        coordinate_system: "blade_to_blade_s_q_mm",
        span_stations_h: [0, 0.25, 0.5, 0.75, 1],
        segments: {
          pressure_side: { color: "#2563eb", control_points: [[0.06, -12], [0.5, -18], [0.94, -10]] },
          suction_side: { color: "#16a34a", control_points: [[0.06, 12], [0.5, 18], [0.94, 10]] },
          leading_edge: { color: "#f97316", control_points: [[0.06, -12], [0.04, 0], [0.06, 12]] },
          trailing_edge: { color: "#e11d48", control_points: [[0.94, -10], [0.97, 0], [0.94, 10]] },
        },
      },
    };

    const tree = CurveControlPanel({ curves: controls });
    const text = JSON.stringify(tree);

    assert.match(text, /Blade-to-blade loop family/);
    assert.match(text, /pressure_side/);
    assert.match(text, /suction_side/);
    assert.match(text, /leading_edge/);
    assert.match(text, /trailing_edge/);
  });

  test("editing a blade-to-blade point emits blade-to-blade loop family overrides", () => {
    const { CurveControlPanel } = loadCurveControlPanelModule();
    const controls = {
      blade_to_blade_loop_family: {
        label: "Blade-to-blade loop family",
        coordinate_system: "blade_to_blade_s_q_mm",
        span_stations_h: [0, 0.25, 0.5, 0.75, 1],
        segments: {
          pressure_side: { color: "#2563eb", control_points: [[0.06, -12], [0.5, -18], [0.94, -10]] },
          suction_side: { color: "#16a34a", control_points: [[0.06, 12], [0.5, 18], [0.94, 10]] },
          leading_edge: { color: "#f97316", control_points: [[0.06, -12], [0.04, 0], [0.06, 12]] },
          trailing_edge: { color: "#e11d48", control_points: [[0.94, -10], [0.97, 0], [0.94, 10]] },
        },
      },
    };
    let emitted = null;
    const tree = CurveControlPanel({
      curves: controls,
      onChange: (payload) => {
        emitted = payload;
      },
    });

    const pressureX = collectElements(
      tree,
      (node) => node.type === "input" && node.props?.["aria-label"] === "pressure_side control point 1 x",
    )[0];
    pressureX.props.onChange({ target: { value: "0.12" } });

    assert.equal(emitted.section_loop_overrides, undefined);
    assert.equal(emitted.curve_overrides, undefined);
    assert.equal(
      emitted.blade_to_blade_loop_family_overrides.blade_to_blade_loop_family.segments.pressure_side.control_points[0][0],
      0.12,
    );
  });

  test("renders blade-to-blade loop family using preset segment_order when provided", () => {
    const { CurveControlPanel } = loadCurveControlPanelModule();
    const controls = {
      blade_to_blade_loop_family: {
        label: "Blade-to-blade loop family",
        coordinate_system: "blade_to_blade_s_q_mm",
        span_stations_h: [0, 0.5, 1],
        segment_order: ["leading_edge", "pressure_side", "trailing_edge", "suction_side"],
        segments: {
          pressure_side: { color: "#2563eb", control_points: [[0.06, -12], [0.94, -10]] },
          suction_side: { color: "#16a34a", control_points: [[0.06, 12], [0.94, 10]] },
          leading_edge: { color: "#f97316", control_points: [[0.06, -12], [0.04, 0], [0.06, 12]] },
          trailing_edge: { color: "#e11d48", control_points: [[0.94, -10], [0.97, 0], [0.94, 10]] },
        },
      },
    };

    const tree = CurveControlPanel({ curves: controls });
    const labels = collectElements(tree, (node) => node.props?.className === "curve-segment-label").map((node) =>
      node.props.children
        .flat(Infinity)
        .filter((child) => typeof child === "string")
        .join("")
        .trim(),
    );

    assert.deepEqual(labels, ["leading_edge", "pressure_side", "trailing_edge", "suction_side"]);
  });
});
