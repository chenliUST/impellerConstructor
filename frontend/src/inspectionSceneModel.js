const GEOMETRIC_VIEW_IDS = new Set(["3d", "meridional", "top"]);
const LOOP_SEGMENT_IDS = ["pressure_side", "suction_side", "leading_edge", "trailing_edge"];

export function inspectionViewportRects(width, height, layout) {
  const viewportWidth = finiteDimension(width);
  const viewportHeight = finiteDimension(height);
  if (layout !== "quad") {
    return {
      [layout]: { x: 0, y: 0, width: viewportWidth, height: viewportHeight },
    };
  }

  const leftWidth = Math.floor(viewportWidth / 2);
  const rightWidth = viewportWidth - leftWidth;
  const bottomHeight = Math.floor(viewportHeight / 2);
  const topHeight = viewportHeight - bottomHeight;
  return {
    "3d": { x: 0, y: bottomHeight, width: leftWidth, height: topHeight },
    meridional: { x: leftWidth, y: bottomHeight, width: rightWidth, height: topHeight },
    "s_q": { x: 0, y: 0, width: leftWidth, height: bottomHeight },
    top: { x: leftWidth, y: 0, width: rightWidth, height: bottomHeight },
  };
}

export function visibleGeometricViews(layout) {
  return layout === "quad" ? ["3d", "meridional", "top"] : GEOMETRIC_VIEW_IDS.has(layout) ? [layout] : [];
}

export function viewportAtPointer(clientX, clientY, canvasRect, rects, viewIds) {
  if (!canvasRect?.width || !canvasRect?.height) {
    return null;
  }
  const allRects = Object.values(rects || {});
  const canvasWidth = Math.max(0, ...allRects.map((rect) => rect.x + rect.width));
  const canvasHeight = Math.max(0, ...allRects.map((rect) => rect.y + rect.height));
  const x = (clientX - canvasRect.left) * (canvasWidth / canvasRect.width);
  const y = (canvasRect.top + canvasRect.height - clientY) * (canvasHeight / canvasRect.height);
  for (const viewId of viewIds || []) {
    const rect = rects?.[viewId];
    if (!rect?.width || !rect?.height) {
      continue;
    }
    if (x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height) {
      return {
        viewId,
        pointer: {
          x: ((x - rect.x) / rect.width) * 2 - 1,
          y: ((y - rect.y) / rect.height) * 2 - 1,
        },
      };
    }
  }
  return null;
}

export function orthographicCameraFrame(bounds, viewId, aspect) {
  const radius = Math.max(Number(bounds.radius) || 1, 1);
  const distance = radius * 4;
  if (viewId === "top") {
    return {
      position: [0, 0, distance],
      target: [0, 0, 0],
      up: [0, 1, 0],
      halfHeight: radius * 1.15,
      aspect,
    };
  }
  return {
    position: [0, -distance, 0],
    target: [0, 0, 0],
    up: [0, 0, 1],
    halfHeight: radius * 1.15,
    aspect,
  };
}

export function resolveInspectionAnchor(anchor, manifest = null, surfaceGraph = null) {
  if (!anchor || typeof anchor !== "object") {
    return null;
  }
  if (anchor.kind === "surface_centroid" || anchor.kind === "surface") {
    return surfaceAnchorPoint(anchor, surfaceGraph);
  }
  if (anchor.kind === "span_station") {
    return spanStationAnchorPoint(anchor, manifest, surfaceGraph);
  }
  if (anchor.kind === "profile_rz") {
    const point = anchor.point || anchor.profile_rz || anchor.profileRz;
    return finitePoint(point, 2) ? [Number(point[0]), 0, Number(point[1])] : null;
  }
  if (anchor.kind === "viewport_corner") {
    return { viewportCorner: anchor.corner || "top_right" };
  }
  return null;
}

function surfaceAnchorPoint(anchor, surfaceGraph) {
  const surfaceId = anchor.surfaceId || anchor.surface_id;
  const surface = (surfaceGraph?.surfaces || []).find(
    (candidate) => (candidate.id || candidate.surface_graph_id) === surfaceId,
  );
  const points = (surface?.uv_grid || []).flatMap((row) =>
    Array.isArray(row) ? row.filter((point) => finitePoint(point, 3)) : [],
  );
  return centroid(points);
}

function spanStationAnchorPoint(anchor, manifest, surfaceGraph) {
  const stationId = anchor.spanStationId || anchor.span_station_id;
  const station = manifest?.parameter_inspection?.span_stations?.[stationId];
  if (!Number.isInteger(station?.source_blade_index) || !Number.isInteger(station?.source_loop_index)) {
    return null;
  }
  const loop = surfaceGraph?.blade_to_blade_loop_family?.blades?.[station.source_blade_index]
    ?.loops?.[station.source_loop_index];
  if (!loop) {
    return null;
  }
  const points = LOOP_SEGMENT_IDS.flatMap((segmentId) => {
    const segmentPoints = loop.segments?.[segmentId]?.points_xyz;
    return Array.isArray(segmentPoints) ? segmentPoints.filter((point) => finitePoint(point, 3)) : [];
  });
  return centroid(points);
}

function centroid(points) {
  if (!points.length) {
    return null;
  }
  const sum = points.reduce(
    (total, point) => [total[0] + Number(point[0]), total[1] + Number(point[1]), total[2] + Number(point[2])],
    [0, 0, 0],
  );
  return sum.map((value) => value / points.length);
}

function finitePoint(point, dimensions) {
  return Array.isArray(point) && point.length >= dimensions && point.slice(0, dimensions).every(Number.isFinite);
}

function finiteDimension(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.floor(number)) : 0;
}
