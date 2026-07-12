import React, { useMemo, useState } from "react";

import {
  dimensionLayout,
  drawingContractStatus,
  fitDrawingFrame,
} from "../reviewEngineeringDrawingModel.js?v=1.1.5.1";
import { EngineeringBladePairScene } from "./EngineeringBladePairScene.js?v=1.1.5.1";

const h = React.createElement;
const VIEWS = [
  { id: "top", label: "Top + Sections" },
  { id: "meridional", label: "Meridional" },
  { id: "s_q", label: "S-Q + Blade 3D" },
  { id: "construction", label: "Construction Tables" },
];
const SHEET = { width: 1600, height: 1000 };

export function ReviewEngineeringDrawing({
  contract = null,
  loading = false,
  error = "",
  surfaceGraph = null,
  manifest = null,
  onRequestView = () => {},
}) {
  const [view, setView] = useState("top");
  const status = drawingContractStatus(contract, manifest?.generation_id || null);
  const activeViewReady = view === "construction"
    ? Boolean(contract?.construction_parameter_registry?.records?.length)
    : Boolean(contract?.views?.[view]);

  return h("section", { className: "review-engineering-workspace", "data-testid": "engineering-drawing-workspace" },
    h("div", { className: "drawing-toolbar" },
      h("div", { className: "drawing-view-tabs", role: "tablist" }, VIEWS.map((item) => h("button", {
        key: item.id,
        type: "button",
        className: view === item.id ? "selected" : "",
        onClick: () => {
          setView(item.id);
          onRequestView(item.id);
        },
        "data-testid": `drawing-${item.id}`,
      }, item.label))),
      h("p", null, contract ? `${contract.preset_id} · generation ${contract.generation_id}` : "Resolved geometry required"),
    ),
    loading ? h("div", { className: "drawing-empty" }, "Preparing semantic drawing contract...") : null,
    error ? h("div", { className: "drawing-empty drawing-error", role: "alert" }, error) : null,
    !loading && !error && status !== "ready"
      ? h("div", { className: "drawing-empty" }, status === "empty" ? "Generate a preset to create engineering drawings." : `Drawing contract ${status}.`)
      : null,
    !loading && !error && status === "ready" && !activeViewReady
      ? h("div", { className: "drawing-empty" }, "Loading selected engineering drawing view...")
      : null,
    !loading && !error && status === "ready" && activeViewReady
      ? view === "construction"
        ? h(ConstructionTables, { tables: contract.construction_tables, registry: contract.construction_parameter_registry })
        : view === "meridional"
        ? h(MeridionalDrawing, { view: contract.views.meridional })
        : view === "s_q"
          ? h(SqDrawing, { view: contract.views.s_q, surfaceGraph, manifest })
          : h(TopDrawing, { view: contract.views.top })
      : null,
  );
}

function TopDrawing({ view }) {
  const mainPanel = { x: 28, y: 52, width: 950, height: 910 };
  const roles = ["active_root", "midspan", "active_tip"];
  const classes = ["main", "splitter"];
  const sectionPanels = Object.fromEntries(classes.flatMap((bladeClass, column) => roles.map((role, row) => [
    `${bladeClass}:${role}`,
    { x: 1000 + column * 290, y: 70 + row * 294, width: 270, height: 258 },
  ])));
  const allPaths = [
    ...(view.surface_projection_paths || []).map((path) => ({ points: path.points })),
    ...(view.centerlines || []).map((path) => ({ points: path.points })),
    ...(view.cut_lines || []).map((path) => ({ points: path.points })),
  ];
  const frame = fitDrawingFrame(allPaths, view.circles || [], mainPanel, 88);
  const layouts = layoutDimensions(view.dimensions || [], frame);
  return h(DrawingSheet, { title: "TOP VIEW · ORTHOGRAPHIC", caption: "RESOLVED PRESET GEOMETRY · mm" },
    h("g", { className: "drawing-top-main" },
      (view.surface_projection_paths || []).map((path) => h(DrawingPath, {
        key: path.id,
        points: path.points.map(frame.map),
        className: path.line_role === "hidden_outline" ? "drawing-hidden-outline" : "drawing-visible-outline",
      })),
      (view.circles || []).map((circle) => h("circle", {
        key: circle.id,
        className: circle.line_role === "visible_outline" ? "drawing-visible-outline" : "drawing-secondary-outline",
        cx: frame.map(circle.center)[0],
        cy: frame.map(circle.center)[1],
        r: circle.radius * frame.scale,
      })),
      (view.centerlines || []).map((line) => h(DrawingPath, { key: line.id, points: line.points.map(frame.map), className: "drawing-centerline" })),
      (view.cut_lines || []).map((line) => h("g", { key: line.id, className: "drawing-cut-line" },
        h(DrawingPath, { points: line.points.map(frame.map), className: "drawing-cut-line" }),
        h("text", { x: frame.map(line.points[1])[0] + 8, y: frame.map(line.points[1])[1] - 8 }, line.label),
      )),
      layouts.map((layout) => h(EngineeringDimension, { key: layout.id, layout })),
      h("path", { className: "drawing-rotation-arrow", d: topRotationArrow(frame, view.circles?.[0]?.radius || 1) }),
      h("text", { className: "drawing-note", x: mainPanel.x + 26, y: mainPanel.y + 32 }, "ROTATION ↺"),
    ),
    (view.cross_sections || []).map((section) => h(SectionInset, {
      key: `${section.blade_class}:${section.station_id}`,
      section,
      panel: sectionPanels[`${section.blade_class}:${section.station_role}`],
      label: `${section.blade_class === "main" ? "M" : "S"}-${roles.indexOf(section.station_role) + 1}`,
    })),
  );
}

function SectionInset({ section, panel, label }) {
  const paths = section.segments.map((segment) => ({ points: segment.points_s_q_mm }));
  const frame = fitDrawingFrame(paths, [], panel, 44);
  const dimensions = (section.dimensions || []).filter((dimension) =>
    ["streamwise_extent", "maximum_thickness", "leading_sagitta", "trailing_sagitta"].includes(dimension.id),
  );
  return h("g", { className: "drawing-section-inset" },
    h("rect", { x: panel.x, y: panel.y, width: panel.width, height: panel.height }),
    h("text", { className: "drawing-section-title", x: panel.x + 10, y: panel.y + 22 },
      `${label} | ${section.blade_class.toUpperCase()} | ${section.station_role.replace("_", " ").toUpperCase()} | h ${Number(section.h).toFixed(2)}`,
    ),
    section.segments.map((segment) => h(React.Fragment, { key: segment.id },
      h(DrawingPath, { points: segment.points_s_q_mm.map(frame.map), className: `drawing-section-curve ${segment.feature_class}` }),
      h(DrawingPath, { points: segment.control_points_s_q_mm.map(frame.map), className: "drawing-control-polygon" }),
    )),
    h(DrawingPath, { points: sectionSkeleton(section).map(frame.map), className: "drawing-centerline" }),
    layoutDimensions(dimensions, frame).map((layout) => h(EngineeringDimension, { key: layout.id, layout, compact: true })),
  );
}

function MeridionalDrawing({ view }) {
  const panel = { x: 34, y: 60, width: 1040, height: 880 };
  const sidePanel = { x: 1110, y: 72, width: 450, height: 390 };
  const profilePaths = (view.profiles || []).flatMap((profile) => [
    { ...profile, points: profile.points_r_z },
    { ...profile, id: `${profile.id}:mirror`, points: profile.points_r_z.map(([r, z]) => [-r, z]) },
  ]);
  const materialRegions = (view.material_regions || []).flatMap((region) => [
    { ...region, points: region.points_r_z },
    { ...region, id: `${region.id}:mirror`, points: region.points_r_z.map(([r, z]) => [-r, z]) },
  ]);
  const controlPaths = (view.control_polygons || []).map((profile) => ({ ...profile, points: profile.control_points_r_z }));
  const axisPaths = (view.centerlines || []).map((path) => ({ ...path, points: path.points_r_z }));
  const frame = fitDrawingFrame([...profilePaths, ...materialRegions, ...controlPaths, ...axisPaths], [], panel, 105);
  const sidePaths = (view.side_view?.surface_projection_paths || []).map((path) => ({ ...path, points: path.points_x_z }));
  const sideFrame = fitDrawingFrame(sidePaths, [], sidePanel, 34);
  const dimensions = layoutDimensions(view.dimensions || [], frame);
  return h(DrawingSheet, { title: "MERIDIONAL SECTION A-A", caption: "SOLID · FLOWPATH · NURBS CONSTRUCTION · mm" },
    materialRegions.map((region) => h("polygon", {
      key: region.id,
      className: "drawing-material-region",
      points: region.points.map(frame.map).map((point) => point.join(",")).join(" "),
      fill: "url(#section-hatch)",
    })),
    profilePaths.map((path) => h(DrawingPath, { key: path.id, points: path.points.map(frame.map), className: "drawing-visible-outline" })),
    axisPaths.map((path) => h(DrawingPath, { key: path.id, points: path.points.map(frame.map), className: "drawing-centerline" })),
    controlPaths.map((profile) => h("g", { key: profile.id },
      h(DrawingPath, { points: profile.points.map(frame.map), className: "drawing-control-polygon" }),
      profile.points.map((point, index) => {
        const mapped = frame.map(point);
        return h("g", { key: `${profile.id}:${index}` },
          h("circle", { className: "drawing-control-point", cx: mapped[0], cy: mapped[1], r: 4 }),
          h("text", { className: "drawing-control-label", x: mapped[0] + 7, y: mapped[1] - 7 }, `P${index}`),
        );
      }),
    )),
    dimensions.map((layout) => h(EngineeringDimension, { key: layout.id, layout })),
    h("g", { className: "drawing-side-view" },
      h("rect", { x: sidePanel.x, y: sidePanel.y, width: sidePanel.width, height: sidePanel.height }),
      h("text", { x: sidePanel.x + 12, y: sidePanel.y + 24 }, "ORTHOGRAPHIC SIDE VIEW"),
      sidePaths.map((path) => h(DrawingPath, { key: path.id, points: path.points.map(sideFrame.map), className: "drawing-secondary-outline" })),
    ),
    h(ControlPointTable, { profiles: view.control_polygons || [], x: 1120, y: 505 }),
  );
}

function SqDrawing({ view, surfaceGraph, manifest }) {
  const rows = view.blade_rows || [];
  return h("section", { className: "drawing-sq-sheet" },
    h("header", null,
      h("h3", null, "BLADE-TO-BLADE S-Q SECTIONS + ISOMETRIC BLADES"),
      h("p", null, "Five resolved span loops · C2 join evidence · mm / deg"),
    ),
    h("div", { className: "drawing-sq-grid", style: { gridTemplateRows: `repeat(${Math.max(rows.length, 1)}, minmax(360px, 1fr))` } },
      h("div", { className: "drawing-sq-curves" }, rows.map((row) => h(SqFiveSpanRowDrawing, { key: row.blade_class, row }))),
      h(EngineeringBladePairScene, { surfaceGraph, rows, manifest }),
    ),
  );
}

function SqFiveSpanRowDrawing({ row }) {
  const sections = row.sections || [];
  return h("article", { className: "drawing-sq-row drawing-sq-five-span" },
    h("header", null,
      h("strong", null, `${row.blade_class.toUpperCase()} BLADE`),
      h("span", null, "FIVE SPAN STATIONS | S-Q DOMAIN"),
    ),
    h("div", { className: "drawing-sq-section-grid" }, sections.map((section) => h(SqSectionMiniature, {
      key: `${row.blade_class}:${section.station_id}:${section.station_role}`,
      section,
    }))),
    h("footer", null,
      `C2 ${row.continuity?.status || "n/a"} | gap ${format(row.continuity?.max_position_gap_mm)} mm | tangent ${format(row.continuity?.max_tangent_angle_deg)} deg`,
    ),
  );
}

function SqSectionMiniature({ section }) {
  const panel = { x: 18, y: 42, width: 264, height: 206 };
  const paths = (section.segments || []).map((segment) => ({ points: segment.points_s_q_mm }));
  const frame = fitDrawingFrame(paths, [], panel, 30);
  return h("svg", { viewBox: "0 0 300 280", role: "img", "aria-label": `${section.blade_class} ${section.station_role} S-Q section` },
    h("defs", null, drawingDefinitions()),
    h("text", { className: "drawing-section-title", x: 12, y: 20 }, `${section.station_role.replaceAll("_", " ").toUpperCase()} | h ${Number(section.h).toFixed(2)}`),
    (section.segments || []).map((segment) => h(React.Fragment, { key: segment.id },
      h(DrawingPath, { points: segment.points_s_q_mm.map(frame.map), className: `drawing-section-curve ${segment.feature_class}` }),
      h(DrawingPath, { points: segment.control_points_s_q_mm.map(frame.map), className: "drawing-control-polygon" }),
      segment.control_points_s_q_mm.map((point, index) => {
        const mapped = frame.map(point);
        return h("circle", { key: `${segment.id}:cp:${index}`, className: "drawing-control-point", cx: mapped[0], cy: mapped[1], r: 2.2 });
      }),
    )),
    h(DrawingPath, { points: sectionSkeleton(section).map(frame.map), className: "drawing-centerline" }),
  );
}

function SqRowDrawing({ row }) {
  const panel = { x: 24, y: 34, width: 920, height: 520 };
  const paths = row.segments.map((segment) => ({ points: segment.points_s_q_mm }));
  const frame = fitDrawingFrame(paths, [], panel, 72);
  const selectedDimensions = (row.dimensions || []).filter((dimension) =>
    ["streamwise_extent", "maximum_thickness", "leading_sagitta", "trailing_sagitta", "blade_angle_le", "blade_angle_mid", "blade_angle_te"].includes(dimension.id),
  );
  return h("article", { className: "drawing-sq-row" },
    h("svg", { viewBox: "0 0 980 600", role: "img", "aria-label": `${row.blade_class} S-Q engineering section` },
      h("defs", null, drawingDefinitions()),
      h("text", { className: "drawing-section-title", x: 24, y: 25 }, `${row.blade_class.toUpperCase()} BLADE · MIDSPAN`),
      row.segments.map((segment) => h(React.Fragment, { key: segment.id },
        h(DrawingPath, { points: segment.points_s_q_mm.map(frame.map), className: `drawing-section-curve ${segment.feature_class}` }),
        h(DrawingPath, { points: segment.control_points_s_q_mm.map(frame.map), className: "drawing-control-polygon" }),
        segment.control_points_s_q_mm.map((point, index) => {
          const mapped = frame.map(point);
          return h("circle", { key: `${segment.id}:cp:${index}`, className: "drawing-control-point", cx: mapped[0], cy: mapped[1], r: 3 });
        }),
      )),
      h(DrawingPath, { points: rowSkeleton(row).map(frame.map), className: "drawing-centerline" }),
      layoutDimensions(selectedDimensions, frame).map((layout) => h(EngineeringDimension, { key: layout.id, layout, compact: true })),
      h("text", { className: "drawing-quality-note", x: 24, y: 585 },
        `C2 ${row.continuity.status} · gap ${format(row.continuity.max_position_gap_mm)} mm · tangent ${format(row.continuity.max_tangent_angle_deg)}° · κ proxy ${format(row.continuity.max_curvature_proxy_mismatch)}`,
      ),
    ),
  );
}

function DrawingSheet({ title, caption, children }) {
  return h("svg", {
    className: "review-engineering-canvas",
    viewBox: `0 0 ${SHEET.width} ${SHEET.height}`,
    role: "img",
    "aria-label": title,
  },
    h("defs", null, drawingDefinitions()),
    h("text", { x: 28, y: 34, className: "drawing-title" }, title),
    children,
    h("text", { x: SHEET.width - 28, y: SHEET.height - 20, textAnchor: "end", className: "drawing-caption" }, caption),
  );
}

function drawingDefinitions() {
  return [
    h("marker", { id: "dimension-arrow", key: "dimension-arrow", viewBox: "0 0 10 10", refX: 5, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" },
      h("path", { d: "M 0 1 L 10 5 L 0 9 z", className: "drawing-arrow" }),
    ),
    h("pattern", { id: "section-hatch", key: "section-hatch", width: 10, height: 10, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
      h("line", { className: "drawing-hatch-line", x1: 0, y1: 0, x2: 0, y2: 10 }),
    ),
  ];
}

function ConstructionTables({ tables = {}, registry = {} }) {
  return h("section", { className: "drawing-construction-tables", "data-testid": "drawing-construction-tables" },
    h("header", null,
      h("div", null, h("h3", null, "RESOLVED CONSTRUCTION TABLES"), h("p", null, "Canonical V1.1.2 parameters presented by semantic destination.")),
      h("dl", null,
        h("dt", null, "Accounted"), h("dd", null, String(registry.records?.length || 0)),
        h("dt", null, "Unaccounted"), h("dd", null, String(registry.unaccounted_parameter_ids?.length || 0)),
      ),
    ),
    h("div", { className: "drawing-construction-table-grid" }, Object.entries(tables).map(([tableId, table]) => h("article", { key: tableId },
      h("h4", null, table.title || tableId.replaceAll("_", " ").toUpperCase()),
      h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Record"), h("th", null, "Resolved value"))),
        h("tbody", null, constructionRows(table).map((row, index) => h("tr", { key: `${tableId}:${index}` },
          h("th", { scope: "row" }, row.label),
          h("td", null, row.value),
        ))),
      ),
    ))),
  );
}

function constructionRows(table) {
  const rows = Array.isArray(table?.rows) ? table.rows : [];
  const flattened = rows.flatMap((row, rowIndex) => Object.entries(row || {}).map(([key, value]) => ({
    label: `${rowIndex + 1}.${key}`,
    value: displayTableValue(value),
  })));
  if (table?.policy) flattened.unshift({ label: "policy", value: displayTableValue(table.policy) });
  return flattened.length ? flattened : [{ label: "status", value: "No resolved records" }];
}

function displayTableValue(value) {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "number") return Number(value).toPrecision(6).replace(/\.?0+$/, "");
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function EngineeringDimension({ layout, compact = false }) {
  if (!layout) return null;
  if (layout.kind === "note") {
    return h("text", { className: "drawing-dimension-note", x: layout.point[0], y: layout.point[1] }, layout.label);
  }
  if (layout.kind === "angular") {
    const start = [layout.origin[0] + Math.cos(layout.firstAngle) * layout.radius, layout.origin[1] + Math.sin(layout.firstAngle) * layout.radius];
    const end = [layout.origin[0] + Math.cos(layout.secondAngle) * layout.radius, layout.origin[1] + Math.sin(layout.secondAngle) * layout.radius];
    const midAngle = (layout.firstAngle + layout.secondAngle) / 2;
    return h("g", { className: "drawing-dimension" },
      h("line", { x1: layout.origin[0], y1: layout.origin[1], x2: start[0], y2: start[1] }),
      h("line", { x1: layout.origin[0], y1: layout.origin[1], x2: end[0], y2: end[1] }),
      h("path", { d: arcPath(layout.origin, layout.radius, layout.firstAngle, layout.secondAngle), markerStart: "url(#dimension-arrow)", markerEnd: "url(#dimension-arrow)" }),
      h("text", { x: layout.origin[0] + Math.cos(midAngle) * (layout.radius + 18), y: layout.origin[1] + Math.sin(midAngle) * (layout.radius + 18), textAnchor: "middle" }, layout.label),
    );
  }
  return h("g", { className: compact ? "drawing-dimension compact" : "drawing-dimension" },
    h("line", { x1: layout.witnessStart[0], y1: layout.witnessStart[1], x2: layout.lineStart[0], y2: layout.lineStart[1] }),
    h("line", { x1: layout.witnessEnd[0], y1: layout.witnessEnd[1], x2: layout.lineEnd[0], y2: layout.lineEnd[1] }),
    h("line", { x1: layout.lineStart[0], y1: layout.lineStart[1], x2: layout.lineEnd[0], y2: layout.lineEnd[1], markerStart: "url(#dimension-arrow)", markerEnd: "url(#dimension-arrow)" }),
    h("text", {
      x: layout.textPoint[0],
      y: layout.textPoint[1],
      textAnchor: layout.vertical ? "end" : "middle",
      transform: layout.vertical ? `rotate(-90 ${layout.textPoint[0]} ${layout.textPoint[1]})` : undefined,
    }, layout.label),
  );
}

function ControlPointTable({ profiles, x, y }) {
  let row = 0;
  return h("g", { className: "drawing-control-table" },
    h("text", { x, y }, "NURBS CONTROL POLYGONS"),
    profiles.flatMap((profile) => [
      h("text", { key: `${profile.id}:head`, x, y: y + 24 + row++ * 18 }, `${profile.role.toUpperCase()}  p=${profile.degree}`),
      ...(profile.control_points_r_z || []).map((point, index) => h("text", {
        key: `${profile.id}:${index}`,
        x: x + 12,
        y: y + 24 + row++ * 18,
      }, `P${index}  R ${point[0].toFixed(2)}  Z ${point[1].toFixed(2)}  w ${Number(profile.weights?.[index] ?? 1).toFixed(3)}`)),
    ]),
  );
}

function layoutDimensions(dimensions, frame) {
  let linearLane = 0;
  let angularLane = 0;
  let noteLane = 0;
  return dimensions.map((dimension) => {
    const lane = dimension.kind === "note" ? noteLane++ : dimension.kind === "angular" ? angularLane++ : linearLane++;
    return dimensionLayout(dimension, frame, lane);
  }).filter(Boolean);
}

function sectionSkeleton(section) {
  const pressure = section.segments.find((segment) => segment.feature_class === "pressure_side")?.points_s_q_mm || [];
  const suction = section.segments.find((segment) => segment.feature_class === "suction_side")?.points_s_q_mm || [];
  return midpointPath(pressure, suction);
}

function rowSkeleton(row) {
  const pressure = row.segments.find((segment) => segment.feature_class === "pressure_side")?.points_s_q_mm || [];
  const suction = row.segments.find((segment) => segment.feature_class === "suction_side")?.points_s_q_mm || [];
  return midpointPath(pressure, suction);
}

function midpointPath(first, second) {
  const length = Math.min(first.length, second.length);
  return Array.from({ length }, (_, index) => [
    (first[index][0] + second[index][0]) / 2,
    (first[index][1] + second[index][1]) / 2,
  ]);
}

function DrawingPath({ points, className }) {
  if (!points || points.length < 2) return null;
  return h("path", { className, d: pathData(points), fill: "none" });
}

function pathData(points) {
  return points.map((point, index) => `${index ? "L" : "M"} ${Number(point[0]).toFixed(2)} ${Number(point[1]).toFixed(2)}`).join(" ");
}

function arcPath(origin, radius, startAngle, endAngle) {
  const start = [origin[0] + Math.cos(startAngle) * radius, origin[1] + Math.sin(startAngle) * radius];
  const end = [origin[0] + Math.cos(endAngle) * radius, origin[1] + Math.sin(endAngle) * radius];
  const delta = Math.abs(endAngle - startAngle);
  return `M ${start[0]} ${start[1]} A ${radius} ${radius} 0 ${delta > Math.PI ? 1 : 0} 1 ${end[0]} ${end[1]}`;
}

function topRotationArrow(frame, radius) {
  const center = frame.map([0, 0]);
  const r = radius * frame.scale * 0.83;
  return arcPath(center, r, -0.45, 0.75);
}

function format(value) {
  return Number.isFinite(Number(value)) ? Number(value).toExponential(2) : "n/a";
}
