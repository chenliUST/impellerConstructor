const DRAWING_PADDING = 16;
const LABEL_OFFSET = 18;
const ARROW_SIZE = 6;

export function projectEngineeringFeature(feature, viewId, frame) {
  if (!feature || typeof feature !== "object") {
    return null;
  }

  const className = feature.className || "engineering-feature-selected";
  const point = (coordinates) => projectPoint(coordinates, viewId);
  let drawing;

  switch (feature.kind) {
    case "nurbs_curve":
      drawing = projectPoints(sqPoints(feature, "control_points", viewId), point);
      break;
    case "polyline":
      drawing = projectPoints(sqPoints(feature, "points", viewId), point);
      break;
    case "control_point":
    case "point": {
      const projected = point(sqPoint(feature, "coordinates", viewId));
      if (!projected) {
        return null;
      }
      return {
        id: feature.id,
        kind: "point",
        point: transformPoints([projected], frame)[0],
        className,
      };
    }
    case "local_frame": {
      const origin = sqPoint(feature, "origin", viewId);
      const sAxis = sqPoint(feature, "s_axis", viewId);
      const qAxis = sqPoint(feature, "q_axis", viewId);
      if (!origin || !sAxis || !qAxis) {
        return null;
      }
      drawing = projectPoints([origin, addVectors(origin, sAxis), origin, addVectors(origin, qAxis)], point);
      break;
    }
    case "reference_axis": {
      const origin = sqPoint(feature, "origin", viewId);
      const direction = sqPoint(feature, "direction", viewId);
      if (!origin || !direction) {
        return null;
      }
      drawing = projectPoints([origin, addVectors(origin, direction)], point);
      break;
    }
    default:
      return null;
  }

  if (!drawing) {
    return null;
  }
  const points = transformPoints(drawing, frame);
  if (!points) {
    return null;
  }
  return {
    id: feature.id,
    kind: "path",
    points,
    className,
  };
}

export function layoutEngineeringDimension(dimension, projectedFeatures, viewport) {
  const rect = viewportRect(viewport);
  const points = dimension?.measurement_points;
  if (!rect || !Array.isArray(points) || points.length < 2 || !points.every(isPoint)) {
    return [];
  }

  const contextBounds = engineeringDrawingBounds(projectedFeatures, []);
  const dimensionPrimitive = dimension.kind === "angular"
    ? angularDimension(dimension, rect)
    : dimension.kind === "arc_height"
      ? arcHeightDimension(dimension, rect)
      : linearDimension(dimension, rect, contextBounds);

  return dimensionPrimitive ? [dimensionPrimitive] : [];
}

export function engineeringDrawingBounds(contextPrimitives, selectedPrimitives) {
  const points = [
    ...primitivePoints(contextPrimitives),
    ...primitivePoints(selectedPrimitives),
  ].filter(isPoint);
  if (points.length === 0) {
    return null;
  }

  const minX = Math.min(...points.map(([x]) => x));
  const maxX = Math.max(...points.map(([x]) => x));
  const minY = Math.min(...points.map(([, y]) => y));
  const maxY = Math.max(...points.map(([, y]) => y));
  return {
    minX,
    minY,
    maxX,
    maxY,
    width: maxX - minX,
    height: maxY - minY,
    center: [(minX + maxX) / 2, (minY + maxY) / 2],
  };
}

function linearDimension(dimension, rect, contextBounds) {
  const [start, end] = dimension.measurement_points.map((point) => clampPoint(point, rect));
  const vector = subtract(end, start);
  const length = Math.hypot(...vector);
  if (length === 0) {
    return null;
  }
  const normal = [-vector[1] / length, vector[0] / length];
  const candidates = [-1, 1].map((sign) => {
    const offset = normal.map((value) => value * LABEL_OFFSET * sign);
    const line = [addVectors(start, offset), addVectors(end, offset)];
    return {
      line,
      fits: line.every((point) => insidePaddedViewport(point, rect)),
      outsideContext: !contextBounds || line.every((point) => outsideBounds(point, contextBounds)),
      sign,
    };
  }).sort((left, right) =>
    Number(right.outsideContext) - Number(left.outsideContext)
    || Number(right.fits) - Number(left.fits)
    || right.sign - left.sign,
  );
  const chosen = candidates.find((candidate) => candidate.fits) || candidates[0];
  const line = chosen.line.map((point) => clampPoint(point, rect));
  const midpoint = midpointOf(line[0], line[1]);
  const notePoint = addVectors(midpoint, normal.map((value) => value * LABEL_OFFSET * chosen.sign));

  return dimensionRecord(dimension, line, [
    path([start, line[0]]),
    path([end, line[1]]),
  ], [
    arrow(line[0], line[1]),
    arrow(line[1], line[0]),
  ], midpoint, notePoint, rect, contextBounds);
}

function angularDimension(dimension, rect) {
  const [origin, radiusPoint] = dimension.measurement_points.map((point) => clampPoint(point, rect));
  const reference = unitVector(dimension.reference_direction);
  const measured = unitVector(dimension.measured_direction);
  if (!reference || !measured) {
    return null;
  }
  const radius = Math.max(12, Math.min(distance(origin, radiusPoint), 30));
  const startAngle = Math.atan2(reference[1], reference[0]);
  const endAngle = Math.atan2(measured[1], measured[0]);
  const sweep = normalizedSweep(startAngle, endAngle);
  const line = Array.from({ length: 9 }, (_, index) => {
    const angle = startAngle + (sweep * index) / 8;
    return clampPoint([origin[0] + Math.cos(angle) * radius, origin[1] + Math.sin(angle) * radius], rect);
  });
  const labelAngle = startAngle + sweep / 2;
  const labelPoint = clampPoint([
    origin[0] + Math.cos(labelAngle) * (radius + LABEL_OFFSET),
    origin[1] + Math.sin(labelAngle) * (radius + LABEL_OFFSET),
  ], rect);

  return dimensionRecord(dimension, line, [
    path([origin, line[0]]),
    path([origin, line.at(-1)]),
  ], [
    arrow(line[0], line[1]),
    arrow(line.at(-1), line.at(-2)),
  ], labelPoint, null, rect, null);
}

function arcHeightDimension(dimension, rect) {
  const [start, end, apex] = dimension.measurement_points.map((point) => clampPoint(point, rect));
  const chordMidpoint = midpointOf(start, end);
  const labelPoint = midpointOf(chordMidpoint, apex);
  return dimensionRecord(dimension, [chordMidpoint, apex], [
    path([start, end]),
    path([chordMidpoint, apex]),
  ], [
    arrow(chordMidpoint, apex),
    arrow(apex, chordMidpoint),
  ], labelPoint, null, rect, null);
}

function dimensionRecord(dimension, linePoints, extensions, arrows, textPoint, notePoint, rect, contextBounds) {
  const note = typeof dimension.note === "string"
    && insidePaddedViewport(notePoint, rect)
    && (!contextBounds || outsideBounds(notePoint, contextBounds))
    ? { value: dimension.note, point: notePoint, className: "engineering-dimension" }
    : null;
  return {
    id: dimension.id,
    kind: "dimension",
    dimensionKind: dimension.kind,
    line: path(linePoints),
    extensions,
    arrows,
    text: {
      value: dimensionValue(dimension),
      point: clampPoint(textPoint, rect),
      className: "engineering-dimension",
    },
    note,
    className: "engineering-dimension",
  };
}

function dimensionValue(dimension) {
  const value = dimension.resolvedValue ?? dimension.resolved_value ?? dimension.value ?? "";
  return dimension.unit ? `${value} ${dimension.unit}`.trim() : String(value);
}

function path(points) {
  return { kind: "path", points, className: "engineering-dimension" };
}

function arrow(tip, toward) {
  const direction = unitVector(subtract(toward, tip)) || [1, 0];
  return path([tip, addVectors(tip, direction.map((value) => value * ARROW_SIZE))]);
}

function sqPoints(feature, field, viewId) {
  if (viewId === "s_q") {
    return feature[`display_${field}_s_q_mm`] || feature[field];
  }
  return feature[field];
}

function sqPoint(feature, field, viewId) {
  if (viewId === "s_q") {
    return feature[`display_${field}_s_q_mm`] || feature[field];
  }
  return feature[field];
}

function projectPoints(points, project) {
  return Array.isArray(points) ? points.map(project) : null;
}

function projectPoint(point, viewId) {
  if (!Array.isArray(point) || !point.every(isFiniteNumber)) {
    return null;
  }
  if (viewId === "top" && point.length >= 3) {
    return [point[0], point[1]];
  }
  if (viewId === "meridional" && point.length >= 3) {
    return [Math.hypot(point[0], point[1]), point[2]];
  }
  if (viewId === "s_q" && point.length >= 2) {
    return [point[0], point[1]];
  }
  return null;
}

function transformPoints(points, frame) {
  if (!Array.isArray(points) || !points.every(isPoint)) {
    return null;
  }
  const bounds = frame?.bounds || frame;
  const viewport = viewportRect(frame?.viewport || frame);
  if (!bounds || !viewport || ![bounds.minX, bounds.minY, bounds.maxX, bounds.maxY].every(isFiniteNumber)) {
    return points.map((point) => [...point]);
  }
  const rangeX = Math.max(bounds.maxX - bounds.minX, 1);
  const rangeY = Math.max(bounds.maxY - bounds.minY, 1);
  const width = Math.max(viewport.width - DRAWING_PADDING * 2, 1);
  const height = Math.max(viewport.height - DRAWING_PADDING * 2, 1);
  const scale = Math.min(width / rangeX, height / rangeY);
  const offsetX = viewport.x + DRAWING_PADDING + (width - rangeX * scale) / 2 - bounds.minX * scale;
  const offsetY = viewport.y + DRAWING_PADDING + (height - rangeY * scale) / 2 - bounds.minY * scale;
  return points.map(([x, y]) => [x * scale + offsetX, y * scale + offsetY]);
}

function primitivePoints(primitives) {
  if (Array.isArray(primitives)) {
    return primitives.flatMap(primitivePoints);
  }
  if (!primitives || typeof primitives !== "object") {
    return [];
  }
  if (primitives.kind === "path") {
    return primitives.points || [];
  }
  if (primitives.kind === "point") {
    return [primitives.point];
  }
  if (primitives.kind === "dimension") {
    return [
      ...primitivePoints(primitives.line),
      ...primitivePoints(primitives.extensions),
      ...primitivePoints(primitives.arrows),
      primitives.text?.point,
      primitives.note?.point,
    ];
  }
  return [];
}

function viewportRect(viewport) {
  if (!viewport || typeof viewport !== "object") {
    return null;
  }
  const x = Number(viewport.x || 0);
  const y = Number(viewport.y || 0);
  const width = Number(viewport.width);
  const height = Number(viewport.height);
  return [x, y, width, height].every(isFiniteNumber) && width > DRAWING_PADDING * 2 && height > DRAWING_PADDING * 2
    ? { x, y, width, height }
    : null;
}

function clampPoint(point, viewport) {
  return [
    clamp(point[0], viewport.x + DRAWING_PADDING, viewport.x + viewport.width - DRAWING_PADDING),
    clamp(point[1], viewport.y + DRAWING_PADDING, viewport.y + viewport.height - DRAWING_PADDING),
  ];
}

function insidePaddedViewport(point, viewport) {
  return isPoint(point)
    && point[0] >= viewport.x + DRAWING_PADDING
    && point[0] <= viewport.x + viewport.width - DRAWING_PADDING
    && point[1] >= viewport.y + DRAWING_PADDING
    && point[1] <= viewport.y + viewport.height - DRAWING_PADDING;
}

function outsideBounds([x, y], bounds) {
  return x <= bounds.minX || x >= bounds.maxX || y <= bounds.minY || y >= bounds.maxY;
}

function normalizedSweep(start, end) {
  let sweep = end - start;
  while (sweep <= -Math.PI) sweep += Math.PI * 2;
  while (sweep > Math.PI) sweep -= Math.PI * 2;
  return sweep;
}

function addVectors(left, right) {
  return left.map((value, index) => value + right[index]);
}

function subtract(left, right) {
  return left.map((value, index) => value - right[index]);
}

function midpointOf(left, right) {
  return [(left[0] + right[0]) / 2, (left[1] + right[1]) / 2];
}

function unitVector(vector) {
  if (!Array.isArray(vector) || vector.length < 2 || !vector.every(isFiniteNumber)) {
    return null;
  }
  const length = Math.hypot(...vector);
  return length > 0 ? vector.map((value) => value / length) : null;
}

function distance(left, right) {
  return Math.hypot(...subtract(left, right));
}

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function isPoint(point) {
  return Array.isArray(point) && point.length >= 2 && point.every(isFiniteNumber);
}

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}
