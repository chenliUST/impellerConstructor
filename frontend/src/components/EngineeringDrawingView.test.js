import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";
import vm from "node:vm";

const root = resolve(import.meta.dirname, "..", "..");
const drawingPath = resolve(root, "src/components/EngineeringDrawingView.js");

function loadComponent(path, exportName) {
  const source = readFileSync(path, "utf-8")
    .replace(
      'import React from "react";',
      'const React = { createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }) };',
    )
    .replace(/import \{[\s\S]*?\} from "\.\.\/engineeringDrawingModel\.js\?v=1\.1\.5";\n/, '')
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
    projectEngineeringFeature: (feature) => feature.kind === "control_point"
      ? { id: feature.id, kind: "point", point: feature.coordinates, className: "engineering-feature" }
      : { id: feature.id, kind: "path", points: feature.control_points || feature.points, className: "engineering-feature" },
    layoutEngineeringDimension: () => [],
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
    assert.match(source, /"path"/);
    assert.match(source, /"circle"/);
    assert.match(source, /"line"/);
    assert.match(source, /"polygon"/);
    assert.match(source, /"text"/);
    assert.doesNotMatch(source, /material|uv|triangle|leader/i);
  });

  test("renders SVG context, selected feature geometry, and dimensions without non-SVG graphics", () => {
    if (!existsSync(drawingPath)) {
      return;
    }

    const EngineeringDrawingView = loadComponent(drawingPath, "EngineeringDrawingView");
    const tree = EngineeringDrawingView({
      viewId: "s_q",
      contextPrimitives: [{ id: "context", kind: "path", points: [[20, 20], [80, 80]] }],
      selectedParameter: {
        id: "curve",
        label: "Blade curve",
        features: [
          { id: "curve", kind: "nurbs_curve", control_points: [[20, 20], [50, 70], [80, 20]] },
          { id: "control", kind: "control_point", coordinates: [50, 70] },
        ],
      },
    });
    const svg = collectElements(tree, (node) => node.type === "svg")[0];
    const paths = collectElements(tree, (node) => node.type === "path");
    const polygon = collectElements(tree, (node) => node.type === "polygon")[0];
    const point = collectElements(tree, (node) => node.type === "circle")[0];

    assert.equal(svg.props.role, "img");
    assert.match(paths[0].props.className, /engineering-context/);
    assert.match(polygon.props.className, /engineering-feature/);
    assert.match(point.props.className, /engineering-feature/);
    assert.equal(collectElements(tree, (node) => node.type === "canvas").length, 0);
  });
});
