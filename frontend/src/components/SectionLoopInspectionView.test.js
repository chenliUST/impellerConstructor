import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";
import vm from "node:vm";

const root = resolve(import.meta.dirname, "..", "..");
const sectionViewPath = resolve(root, "src/components/SectionLoopInspectionView.js");
const overlayPath = resolve(root, "src/components/ParameterAnnotationOverlay.js");

function loadComponent(path, exportName) {
  const source = readFileSync(path, "utf-8")
    .replace(
      'import React from "react";',
      'const React = { createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }) };',
    )
    .replace(/export function /g, "function ");
  const module = { exports: {} };
  const context = vm.createContext({ module, exports: module.exports, Math, Number, String, Array, Object, Set });
  vm.runInContext(`${source}\nmodule.exports = { ${exportName} };`, context, { filename: path });
  return module.exports[exportName];
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

function visibleText(node) {
  return (node.props?.children || []).filter((child) => typeof child === "string").join("");
}

function loopFixture() {
  return {
    section_loop_id: "blade_0:span_0:loop",
    join_metrics: {
      pressure_to_leading: {
        status: "PASS",
        position_gap_mm: 0.03,
        tangent_angle_deg: 1.25,
        curvature_proxy_mismatch: 0.008,
      },
    },
    segment_references: {
      pressure_side: {
        section_segment_id: "blade_0:span_0:loop:pressure_side",
        points_s_q: [[0, -1], [0.5, -1.2], [1, -0.8]],
        control_points_s_q: [[0, -1], [0.5, -1.3], [1, -0.8]],
      },
      leading_edge: {
        section_segment_id: "blade_0:span_0:loop:leading_edge",
        points_s_q: [[0, 1], [-0.12, 0], [0, -1]],
        control_points_s_q: [[0, 1], [-0.12, 0], [0, -1]],
      },
      suction_side: {
        section_segment_id: "blade_0:span_0:loop:suction_side",
        points_s_q: [[1, 0.8], [0.5, 1.2], [0, 1]],
        control_points_s_q: [[1, 0.8], [0.5, 1.3], [0, 1]],
      },
      trailing_edge: {
        section_segment_id: "blade_0:span_0:loop:trailing_edge",
        points_s_q: [[1, -0.8], [1.12, 0], [1, 0.8]],
        control_points_s_q: [[1, -0.8], [1.12, 0], [1, 0.8]],
      },
    },
  };
}

describe("SectionLoopInspectionView source contract", () => {
  test("declares the required read-only S-Q rendering primitives", () => {
    assert.equal(existsSync(sectionViewPath), true, "SectionLoopInspectionView.js should exist");

    const source = readFileSync(sectionViewPath, "utf-8");
    assert.match(source, /actual-section-loop/);
    assert.match(source, /control-polygon/);
    assert.match(source, /control-point/);
    assert.match(source, /pressure_side/);
    assert.match(source, /suction_side/);
    assert.match(source, /leading_edge/);
    assert.match(source, /trailing_edge/);
    assert.match(source, /onSelect/);
    assert.doesNotMatch(source, /onChange/);
    assert.doesNotMatch(source, /drag/);
  });

  test("renders actual semantic curves, selectable control points, and contract join metrics", () => {
    const SectionLoopInspectionView = loadComponent(sectionViewPath, "SectionLoopInspectionView");
    let selected = null;
    const tree = SectionLoopInspectionView({
      loop: loopFixture(),
      selection: { sectionSegmentId: "blade_0:span_0:loop:pressure_side" },
      annotationLevel: "selected",
      onSelect: (nextSelection) => {
        selected = nextSelection;
      },
    });

    const actualCurves = collectElements(tree, (node) => node.type === "polyline" && /actual-section-loop/.test(node.props.className));
    const controlPolygons = collectElements(tree, (node) => node.type === "polyline" && /control-polygon/.test(node.props.className));
    const controlPoints = collectElements(tree, (node) => node.type === "circle" && /control-point/.test(node.props.className));

    assert.equal(actualCurves.length, 4);
    assert.equal(controlPolygons.length, 4);
    assert.equal(controlPoints.length, 12);
    assert.match(actualCurves[0].props.className, /pressure-side/);
    assert.match(controlPolygons[0].props.className, /pressure-side/);
    assert.match(controlPoints[0].props.className, /pressure-side/);
    assert.match(JSON.stringify(tree), /pressure_to_leading: PASS/);
    assert.doesNotMatch(JSON.stringify(tree), /pressure_to_leading: UNKNOWN/);
    assert.match(JSON.stringify(tree), /0.03/);
    assert.match(JSON.stringify(tree), /1.25/);
    assert.match(JSON.stringify(tree), /0.008/);

    controlPoints[0].props.onClick();
    assert.deepEqual(JSON.parse(JSON.stringify(selected)), {
      sectionSegmentId: "blade_0:span_0:loop:pressure_side",
      controlPointId: "blade_0:span_0:loop:pressure_side:cp_0",
    });
  });
});

describe("ParameterAnnotationOverlay source contract", () => {
  test("declares deterministic leader and label classes without mutation callbacks", () => {
    assert.equal(existsSync(overlayPath), true, "ParameterAnnotationOverlay.js should exist");

    const source = readFileSync(overlayPath, "utf-8");
    assert.match(source, /inspection-leader/);
    assert.match(source, /inspection-label/);
    assert.match(source, /sort\(.*id/);
    assert.doesNotMatch(source, /onChange/);
    assert.doesNotMatch(source, /onMutate/);
    assert.doesNotMatch(source, /onEdit/);
  });

  test("sorts colliding labels into slots and preserves requested and resolved values", () => {
    const ParameterAnnotationOverlay = loadComponent(overlayPath, "ParameterAnnotationOverlay");
    const tree = ParameterAnnotationOverlay({
      annotations: [
        {
          id: "b",
          label: "Thickness max",
          requestedValue: 20,
          requestedUnit: "mm",
          resolvedValue: 18,
          unit: "mm",
          anchor: { id: "second" },
          selected: true,
        },
        {
          id: "a",
          label: "Thickness min",
          requestedValue: 6.8,
          requestedUnit: "mm",
          resolvedValue: 6.8,
          unit: "mm",
          anchor: { id: "first" },
        },
      ],
      projectAnchor: () => ({ x: 320, y: 140 }),
    });

    const leaders = collectElements(tree, (node) => node.type === "line");
    const labels = collectElements(tree, (node) => node.type === "text");

    assert.equal(leaders.length, 2);
    assert.equal(labels.length, 2);
    assert.equal(leaders[1].props.y2 - leaders[0].props.y2, 28);
    assert.match(visibleText(labels[0]), /Thickness min: 6.8 mm/);
    assert.match(visibleText(labels[1]), /Thickness max: 20 mm -> 18 mm/);
    assert.match(leaders[1].props.className, /selected/);
    assert.match(labels[1].props.className, /selected/);
  });

  test("compacts structured values while preserving their full text in titles", () => {
    const ParameterAnnotationOverlay = loadComponent(overlayPath, "ParameterAnnotationOverlay");
    const requestedValue = Array.from({ length: 12 }, (_, index) => index);
    const resolvedValue = { first: "resolved-a", second: "resolved-b" };
    const tree = ParameterAnnotationOverlay({
      annotations: [{
        id: "structured",
        label: "Points",
        requestedValue,
        resolvedValue,
        anchor: { id: "structured" },
      }],
      projectAnchor: () => ({ x: 700, y: 140 }),
    });

    const label = collectElements(tree, (node) => node.type === "text")[0];
    const title = collectElements(tree, (node) => node.type === "title")[0];

    assert.equal(visibleText(label), "Points: [12 items] -> {2 fields}");
    assert.match(title.props.children.join(""), /\[0,1,2,3,4,5,6,7,8,9,10,11\]/);
    assert.match(title.props.children.join(""), /resolved-b/);
  });

  test("clamps narrow viewport labels and retains selected annotations when slots overflow", () => {
    const ParameterAnnotationOverlay = loadComponent(overlayPath, "ParameterAnnotationOverlay");
    const annotations = ["a", "b", "c", "z"].map((id) => ({
      id,
      label: id === "z" ? "Selected annotation with a deliberately long visible label" : `Annotation ${id}`,
      requestedValue: id === "z" ? Array.from({ length: 20 }, (_, index) => `requested-${index}`) : id,
      resolvedValue: id === "z" ? { final: "long-final-value" } : id,
      anchor: { id },
      selected: id === "z",
    }));
    const tree = ParameterAnnotationOverlay({
      annotations,
      projectAnchor: () => ({ x: 40, y: 40 }),
      viewportWidth: 240,
      viewportHeight: 84,
    });

    const leaders = collectElements(tree, (node) => node.type === "line");
    const labels = collectElements(tree, (node) => node.type === "text");
    const selectedLabel = labels.find((label) => /selected/.test(label.props.className));
    const selectedTitle = collectElements(selectedLabel, (node) => node.type === "title")[0];

    assert.ok(labels.length <= 3);
    assert.ok(leaders.every((leader) => leader.props.x2 >= 12 && leader.props.x2 <= 228));
    assert.ok(leaders.every((leader) => leader.props.y2 >= 14 && leader.props.y2 <= 70));
    assert.ok(selectedLabel, "selected annotation must remain rendered");
    assert.match(visibleText(selectedLabel), /\.\.\.$/);
    assert.ok(visibleText(selectedLabel).length <= 16);
    assert.match(selectedTitle.props.children.join(""), /long-final-value/);
  });
});
