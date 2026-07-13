import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";
import vm from "node:vm";

import {
  engineeringDrawingBounds,
  layoutEngineeringDimension,
  projectEngineeringFeature,
} from "../engineeringDrawingModel.js";

const root = resolve(import.meta.dirname, "..", "..");
const drawingPath = resolve(root, "src/components/EngineeringDrawingView.js");

function loadComponent(path, exportName) {
  const source = readFileSync(path, "utf-8")
    .replace(
      'import React from "react";',
      'const React = { createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }) };',
    )
    .replace(/import \{[\s\S]*?\} from "\.\.\/engineeringDrawingModel\.js\?v=[^"]+";\r?\n/, '')
    .replace(/export function /g, "function ");
  const module = { exports: {} };
  const context = vm.createContext({
    module,
    exports: module.exports,
    Array,
    Math,
    Number,
    Object,
    String,
    engineeringDrawingBounds,
    layoutEngineeringDimension,
    projectEngineeringFeature,
  });
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

describe("EngineeringDrawingView", () => {
  test("declares the red, blue, and black SVG source contract", () => {
    assert.equal(existsSync(drawingPath), true, "EngineeringDrawingView.js should exist");
    if (!existsSync(drawingPath)) {
      return;
    }

    const source = readFileSync(drawingPath, "utf-8");
    assert.match(source, /engineering-context/);
    assert.match(source, /engineering-feature/);
    assert.match(source, /engineering-dimension/);
    assert.match(source, /contextPrimitives\.map\(\(primitive, index\) => renderPrimitive/);
    assert.doesNotMatch(source, /projectFeatures\(contextPrimitives/);
    assert.match(source, /"path"/);
    assert.match(source, /"circle"/);
    assert.match(source, /"line"/);
    assert.match(source, /"polygon"/);
    assert.match(source, /"text"/);
    assert.doesNotMatch(source, /material|uv|triangle|leader/i);
  });

  test("preserves projected context and uses its Task 4 descriptor for selected geometry", () => {
    if (!existsSync(drawingPath)) {
      return;
    }

    const EngineeringDrawingView = loadComponent(drawingPath, "EngineeringDrawingView");
    const frame = {
      bounds: { minX: 0, minY: 0, maxX: 100, maxY: 50 },
      viewport: { x: 0, y: 0, width: 1000, height: 700 },
    };
    const contextPrimitives = [
      projectEngineeringFeature({ id: "context-path", kind: "polyline", points: [[0, 0], [100, 0]] }, "s_q", frame),
      projectEngineeringFeature({ id: "context-point", kind: "point", coordinates: [0, 0] }, "s_q", frame),
    ];
    const tree = EngineeringDrawingView({
      viewId: "s_q",
      contextPrimitives,
      selectedParameter: {
        id: "curve",
        label: "Blade curve",
        features: [
          { id: "curve", kind: "nurbs_curve", control_points: [[0, 0], [50, 50], [100, 0]] },
          { id: "control", kind: "control_point", coordinates: [50, 50] },
        ],
        dimension: { id: "chord", kind: "linear", measurement_points: [[0, 0], [100, 0]], resolvedValue: 100, unit: "mm" },
      },
    });
    const svg = collectElements(tree, (node) => node.type === "svg")[0];
    const paths = collectElements(tree, (node) => node.type === "path");
    const featurePath = paths.find((node) => /engineering-feature/.test(node.props.className));
    const polygon = collectElements(tree, (node) => node.type === "polygon")[0];
    const points = collectElements(tree, (node) => node.type === "circle");
    const contextPoint = points.find((node) => /engineering-context/.test(node.props.className));
    const featurePoint = points.find((node) => /engineering-feature/.test(node.props.className));
    const dimensionLines = collectElements(tree, (node) => node.type === "line");
    const dimensionPaths = paths.filter((node) => !node.props.className);
    const dimensionText = collectElements(tree, (node) => node.type === "text")[0];

    assert.equal(svg.props.role, "img");
    assert.match(paths[0].props.className, /engineering-context/);
    assert.equal(paths[0].props.d, "M 16 108 L 984 108");
    assert.match(featurePath.props.className, /engineering-feature/);
    assert.notEqual(featurePath.props.d, "M 16 108 L 500 592 L 984 108");
    assert.match(featurePath.props.d, /^M 16 108 L /);
    assert.match(polygon.props.className, /engineering-feature/);
    assert.equal(polygon.props.points, "16,108 500,592 984,108");
    assert.deepEqual([contextPoint.props.cx, contextPoint.props.cy], [16, 108]);
    assert.deepEqual([featurePoint.props.cx, featurePoint.props.cy], [500, 592]);
    assert.equal(dimensionLines.length, 2);
    assert.deepEqual([dimensionLines[0].props.x1, dimensionLines[0].props.y1], [16, 108]);
    assert.deepEqual([dimensionLines[1].props.x1, dimensionLines[1].props.y1], [984, 108]);
    assert.equal(dimensionPaths.length, 3);
    assert.equal(dimensionText.props.children[0], "100 mm");
    assert.equal(collectElements(tree, (node) => node.type === "canvas").length, 0);
  });

  test("uses a valid unframed Task 4 descriptor for context, selected geometry, and dimensions", () => {
    const EngineeringDrawingView = loadComponent(drawingPath, "EngineeringDrawingView");
    const contextPrimitives = [
      projectEngineeringFeature({ id: "context-path", kind: "polyline", points: [[0, 0], [100, 0]] }, "s_q"),
      projectEngineeringFeature({ id: "context-point", kind: "point", coordinates: [0, 0] }, "s_q"),
    ];
    const tree = EngineeringDrawingView({
      viewId: "s_q",
      contextPrimitives,
      selectedParameter: {
        id: "curve",
        label: "Blade curve",
        features: [
          { id: "curve", kind: "nurbs_curve", control_points: [[0, 0], [50, 50], [100, 0]] },
          { id: "control", kind: "control_point", coordinates: [50, 50] },
        ],
        dimension: { id: "chord", kind: "linear", measurement_points: [[0, 0], [100, 0]], resolvedValue: 100, unit: "mm" },
      },
    });
    const paths = collectElements(tree, (node) => node.type === "path");
    const contextPath = paths.find((node) => /engineering-context/.test(node.props.className));
    const featurePath = paths.find((node) => /engineering-feature/.test(node.props.className));
    const featurePoint = collectElements(tree, (node) => node.type === "circle")
      .find((node) => /engineering-feature/.test(node.props.className));
    const dimension = collectElements(tree, (node) => node.type === "g")
      .find((node) => node.props.className === "engineering-dimension");

    assert.ok(contextPath, "expected black Task 4 context path");
    assert.ok(featurePath, "expected red selected feature path");
    assert.ok(featurePoint, "expected red selected control point");
    assert.equal(contextPath.props.d, "M 0 0 L 100 0");
    assert.notEqual(featurePath.props.d, "M 0 0 L 50 50 L 100 0");
    assert.match(featurePath.props.d, /^M 0 0 L /);
    assert.deepEqual([featurePoint.props.cx, featurePoint.props.cy], [50, 50]);
    assert.ok(dimension);
    assert.equal(collectElements(dimension, (node) => node.type === "line").length, 2);
    assert.equal(collectElements(dimension, (node) => node.type === "path").length, 3);
    assert.equal(collectElements(dimension, (node) => node.type === "text")[0].props.children[0], "100 mm");
  });

  test("keeps attachment boundaries black while measurement points are red and dimensions blue", () => {
    const EngineeringDrawingView = loadComponent(drawingPath, "EngineeringDrawingView");
    const boundary = {
      id: "hub-boundary",
      kind: "polyline",
      coordinate_system: "model_xyz",
      rendering_role: "drawing_context",
      points: [[10, 0, 0], [20, 0, 10]],
    };
    const contextPrimitives = [projectEngineeringFeature(boundary, "meridional")];
    const tree = EngineeringDrawingView({
      viewId: "meridional",
      contextPrimitives,
      selectedParameter: {
        id: "root-lift",
        features: [
          boundary,
          { id: "start", kind: "point", coordinate_system: "model_xyz", rendering_role: "selected_feature", coordinates: [10, 0, 0] },
          { id: "end", kind: "point", coordinate_system: "model_xyz", rendering_role: "selected_feature", coordinates: [20, 0, 10] },
        ],
        dimension: { kind: "linear", measurement_points: [[10, 0, 0], [20, 0, 10]], unit: "mm", resolvedValue: 14.142 },
      },
    });

    const contextPaths = collectElements(tree, (node) => node.type === "path" && /engineering-context/.test(node.props.className));
    const selectedPaths = collectElements(tree, (node) => node.type === "path" && /engineering-feature/.test(node.props.className));
    const selectedPoints = collectElements(tree, (node) => node.type === "circle" && /engineering-feature/.test(node.props.className));
    const dimensions = collectElements(tree, (node) => node.type === "g" && node.props.className === "engineering-dimension");

    assert.equal(contextPaths.length, 1);
    assert.equal(selectedPaths.length, 0);
    assert.equal(selectedPoints.length, 2);
    assert.equal(dimensions.length, 1);
  });
});
