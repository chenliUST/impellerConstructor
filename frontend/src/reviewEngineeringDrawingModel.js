export function drawingContractStatus(contract, expectedGenerationId = null) {
  if (!contract) return "empty";
  if (contract.contract_version !== "1.1.5") return "unsupported";
  if (expectedGenerationId && contract.generation_id !== expectedGenerationId) return "stale";
  return "ready";
}

export function fitDrawingFrame(paths, circles, viewport, margin = 30) {
  const points = (paths || []).flatMap((path) => path.points || path.points_r_z || path);
  for (const circle of circles || []) {
    const [cx, cy] = circle.center || [0, 0];
    const radius = Number(circle.radius) || 0;
    points.push([cx - radius, cy - radius], [cx + radius, cy + radius]);
  }
  const extent = drawingBounds(points) || { minX: 0, maxX: 1, minY: 0, maxY: 1 };
  const dataWidth = Math.max(extent.maxX - extent.minX, 1e-9);
  const dataHeight = Math.max(extent.maxY - extent.minY, 1e-9);
  const scale = Math.min(
    (viewport.width - margin * 2) / dataWidth,
    (viewport.height - margin * 2) / dataHeight,
  );
  const contentWidth = dataWidth * scale;
  const contentHeight = dataHeight * scale;
  const offsetX = viewport.x + (viewport.width - contentWidth) / 2 - extent.minX * scale;
  const offsetY = viewport.y + (viewport.height - contentHeight) / 2 + extent.maxY * scale;
  return {
    scale,
    extent,
    viewport,
    map: ([x, y]) => [Number(x) * scale + offsetX, offsetY - Number(y) * scale],
  };
}

export function drawingBounds(points) {
  const finite = (points || []).filter((point) =>
    Array.isArray(point)
    && point.length >= 2
    && Number.isFinite(Number(point[0]))
    && Number.isFinite(Number(point[1])),
  );
  if (!finite.length) return null;
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const point of finite) {
    const x = Number(point[0]);
    const y = Number(point[1]);
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  return { minX, maxX, minY, maxY };
}

export function dimensionLayout(dimension, frame, laneIndex = 0) {
  if (dimension.kind === "note") {
    return { ...dimension, kind: "note", point: [frame.viewport.x + 12, frame.viewport.y + 56 + laneIndex * 22] };
  }
  const witnesses = (dimension.witness_points || []).map(frame.map);
  if (witnesses.length < 2) return null;
  if (dimension.kind === "angular" && witnesses.length >= 3) {
    const [origin, first, second] = witnesses;
    const radius = 54 + laneIndex * 16;
    const firstAngle = Math.atan2(first[1] - origin[1], first[0] - origin[0]);
    const secondAngle = Math.atan2(second[1] - origin[1], second[0] - origin[0]);
    return { ...dimension, kind: "angular", origin, first, second, radius, firstAngle, secondAngle };
  }
  const [first, second] = [witnesses[0], witnesses[witnesses.length - 1]];
  const horizontal = Math.abs(second[0] - first[0]) >= Math.abs(second[1] - first[1]);
  if (horizontal) {
    const lineY = frame.viewport.y + frame.viewport.height - 16 - laneIndex * 24;
    return {
      ...dimension,
      kind: "linear",
      witnessStart: first,
      witnessEnd: second,
      lineStart: [first[0], lineY],
      lineEnd: [second[0], lineY],
      textPoint: [(first[0] + second[0]) / 2, lineY - 7],
    };
  }
  const lineX = frame.viewport.x + frame.viewport.width - 16 - laneIndex * 24;
  return {
    ...dimension,
    kind: "linear",
    witnessStart: first,
    witnessEnd: second,
    lineStart: [lineX, first[1]],
    lineEnd: [lineX, second[1]],
    textPoint: [lineX - 7, (first[1] + second[1]) / 2],
    vertical: true,
  };
}

export function representativeBladeGraph(surfaceGraph, surfaceIds) {
  const ids = new Set(surfaceIds || []);
  return {
    ...(surfaceGraph || {}),
    surfaces: (surfaceGraph?.surfaces || []).filter((surface) => ids.has(surface.id || surface.surface_graph_id)),
  };
}
