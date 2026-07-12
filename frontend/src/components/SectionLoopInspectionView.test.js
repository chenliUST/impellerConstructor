import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";
import vm from "node:vm";

const root = resolve(import.meta.dirname, "..", "..");
const sectionViewPath = resolve(root, "src/components/SectionLoopInspectionView.js");
const stylesPath = resolve(root, "src/styles.css");

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
  const segment = (sectionSegmentId, points, controlIds) => ({
    section_segment_id: sectionSegmentId,
    points_s_q: points,
    control_points_s_q: points,
    display_points_s_q_mm: points.map(([s, q]) => [s * 100, q]),
    display_control_points_s_q_mm: points.map(([s, q]) => [s * 100, q]),
    control_points: points.map(([s, q], index) => ({
      control_point_id: controlIds[index],
      section_segment_id: sectionSegmentId,
      coordinates_s_q: [s, q],
      display_coordinates_s_q_mm: [s * 100, q],
    })),
  });
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
        ...segment(
          "blade_0:span_0:loop:pressure_side",
          [[0, -1], [0.5, -1.2], [1, -0.8]],
          ["pressure-inlet", "pressure-mid", "pressure-outlet"],
        ),
      },
      leading_edge: {
        ...segment(
          "blade_0:span_0:loop:leading_edge",
          [[0, -1], [-0.12, 0], [0, 1]],
          ["leading-pressure", "leading-mid", "leading-suction"],
        ),
      },
      suction_side: {
        ...segment(
          "blade_0:span_0:loop:suction_side",
          [[0, 1], [0.5, 1.2], [1, 0.8]],
          ["suction-inlet", "suction-mid", "suction-outlet"],
        ),
      },
      trailing_edge: {
        ...segment(
          "blade_0:span_0:loop:trailing_edge",
          [[1, 0.8], [1.12, 0], [1, -0.8]],
          ["trailing-suction", "trailing-mid", "trailing-pressure"],
        ),
      },
    },
  };
}

function actualOpenPresetLoopFixture() {
  const loop = loopFixture();
  loop.section_loop_id = "blade_0:span_0:loop";
  loop.streamwise_metric_scale_mm = 667.5320490261993;
  loop.source_coordinate_units = { s: "normalized", q: "mm" };
  loop.display_coordinate_units = { s: "mm", q: "mm" };
  loop.join_metrics = Object.fromEntries([
    "pressure_to_leading",
    "leading_to_suction",
    "suction_to_trailing",
    "trailing_to_pressure",
  ].map((joinId) => [joinId, {
    status: "PASS",
    position_gap_mm: 0,
    tangent_angle_deg: 0.001,
    curvature_proxy_mismatch: 0.01,
  }]));
  const actualDisplayPoints = {
    pressure_side: [[40.05192294157195, -7.7], [186.90897372733582, 35.753125], [333.76602451309964, 132.925], [480.62307529886345, 231.109375], [627.4801260846273, 277.6]],
    leading_edge: [[40.05192294157195, -7.7], [34.60720045381796, -5.444722215], [32.351922732689424, 0], [34.60720045381796, 5.444722215], [40.05192294157195, 7.7]],
    suction_side: [[40.05192294157195, 7.7], [186.90897372733582, 52.371875], [333.76602451309964, 149.075], [480.62307529886345, 244.765625], [627.4801260846273, 286.4]],
    trailing_edge: [[627.4801260846273, 286.4], [630.5913961729913, 285.111269837], [631.8801262039888, 282], [630.5913961729913, 278.888730163], [627.4801260846273, 277.6]],
  };
  for (const [segmentName, points] of Object.entries(actualDisplayPoints)) {
    loop.segment_references[segmentName].display_points_s_q_mm = points;
    loop.segment_references[segmentName].display_control_points_s_q_mm = points;
    loop.segment_references[segmentName].control_points = points.map((point, index) => ({
      control_point_id: `open-${segmentName}-${index}`,
      section_segment_id: loop.segment_references[segmentName].section_segment_id,
      coordinates_s_q: [point[0] / loop.streamwise_metric_scale_mm, point[1]],
      display_coordinates_s_q_mm: point,
    }));
  }
  return loop;
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
    assert.match(source, /display_points_s_q_mm/);
    assert.match(source, /display_coordinates_s_q_mm/);
    assert.doesNotMatch(source, /controlPointId:\s*`\$\{segment\.sectionSegmentId\}:cp_\$\{pointIndex\}`/);
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

    actualCurves[0].props.onClick();
    assert.deepEqual(JSON.parse(JSON.stringify(selected)), {
      sectionSegmentId: "blade_0:span_0:loop:pressure_side",
      controlPointId: null,
    });

    controlPoints[0].props.onClick();
    assert.deepEqual(JSON.parse(JSON.stringify(selected)), {
      sectionSegmentId: "blade_0:span_0:loop:pressure_side",
      controlPointId: "pressure-inlet",
    });
  });

  test("renders millimetric axes and a non-degenerate equal-aspect open-preset loop", () => {
    const SectionLoopInspectionView = loadComponent(sectionViewPath, "SectionLoopInspectionView");
    const tree = SectionLoopInspectionView({ loop: actualOpenPresetLoopFixture(), annotationLevel: "all" });
    const curves = collectElements(tree, (node) => node.type === "polyline" && /actual-section-loop/.test(node.props.className));
    const coordinates = curves.flatMap((curve) => curve.props.points.split(" ").map((point) => point.split(",").map(Number)));
    const xs = coordinates.map(([x]) => x);
    const ys = coordinates.map(([, y]) => y);
    const drawnWidth = Math.max(...xs) - Math.min(...xs);
    const drawnHeight = Math.max(...ys) - Math.min(...ys);

    assert.match(JSON.stringify(tree), /S \(mm\)/);
    assert.match(JSON.stringify(tree), /Q \(mm\)/);
    assert.ok(drawnWidth > 700, drawnWidth);
    assert.ok(drawnHeight > 300, drawnHeight);
    assert.ok(drawnWidth / drawnHeight > 1.8 && drawnWidth / drawnHeight < 2.2, drawnWidth / drawnHeight);
  });

  test("reserves a deterministic upper rail for visible annotations", () => {
    const SectionLoopInspectionView = loadComponent(sectionViewPath, "SectionLoopInspectionView");
    const annotations = Array.from({ length: 6 }, (_, index) => ({ id: `annotation-${index}` }));
    const tree = SectionLoopInspectionView({
      loop: actualOpenPresetLoopFixture(),
      annotationLevel: "all",
      annotations,
    });
    const curves = collectElements(tree, (node) => node.type === "polyline" && /actual-section-loop/.test(node.props.className));
    const ys = curves.flatMap((curve) => curve.props.points.split(" ").map((point) => Number(point.split(",")[1])));

    assert.ok(Math.min(...ys) >= 200, Math.min(...ys));
  });

  test("keeps continuity metrics in a lower rail outside the loop", () => {
    const SectionLoopInspectionView = loadComponent(sectionViewPath, "SectionLoopInspectionView");
    const tree = SectionLoopInspectionView({
      loop: actualOpenPresetLoopFixture(),
      annotationLevel: "all",
      annotations: Array.from({ length: 6 }, (_, index) => ({ id: `annotation-${index}` })),
    });
    const curves = collectElements(tree, (node) => node.type === "polyline" && /actual-section-loop/.test(node.props.className));
    const curveYs = curves.flatMap((curve) => curve.props.points.split(" ").map((point) => Number(point.split(",")[1])));
    const metricYs = collectElements(tree, (node) => node.type === "text" && /_to_/.test(visibleText(node)))
      .map((node) => node.props.y);

    assert.ok(Math.min(...metricYs) > Math.max(...curveYs), `${Math.min(...metricYs)} <= ${Math.max(...curveYs)}`);
  });

  test("keeps join metrics below the top annotation lanes", () => {
    const SectionLoopInspectionView = loadComponent(sectionViewPath, "SectionLoopInspectionView");
    const tree = SectionLoopInspectionView({ loop: loopFixture() });
    const metrics = collectElements(
      tree,
      (node) => node.type === "text" && /pressure_to_leading: PASS/.test(visibleText(node)),
    );

    assert.equal(metrics.length, 1);
    assert.ok(metrics[0].props.y >= 500);
  });
});
