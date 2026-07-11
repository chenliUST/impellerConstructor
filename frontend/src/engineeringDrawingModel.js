const DRAWING_PADDING = 16;
const LABEL_OFFSET = 18;
const ARROW_SIZE = 6;

export function projectEngineeringFeature(feature, viewId, frame) {
  if (!feature || typeof feature !== "object") {
    return null;
  }

  const className = feature.className || "engineering-feature-selected";
  const point = (coordinates) => projectPoint(coordinates, viewId, feature.coordinate_system);
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
      const points = transformPoints([projected], frame);
      if (!points) {
        return null;
      }
      return {
        id: feature.id,
        kind: "point",
        point: points[0],
        className,
        projection: { viewId, frame },
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
    projection: { viewId, frame },
  };
}

export function layoutEngineeringDimension(dimension, projectedFeatures, viewport) {
  const rect = viewportRect(viewport);
  const projection = projectionContext(projectedFeatures);
  const projectedDimension = projectDimension(dimension, projection);
  if (!rect || !projectedDimension) {
    return [];
  }

  const contextBounds = engineeringDrawingBounds(projection.primitives, []);
  const dimensionPrimitive = projectedDimension.kind === "angular"
    ? angularDimension(projectedDimension, rect)
    : projectedDimension.kind === "arc_height"
      ? arcHeightDimension(projectedDimension, rect)
      : projectedDimension.kind === "radial"
        ? radialDimension(projectedDimension, rect, contextBounds)
        : projectedDimension.kind === "diameter"
          ? diameterDimension(projectedDimension, rect, contextBounds)
          : linearDimension(projectedDimension, rect, contextBounds);

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
      crossesContext: Boolean(contextBounds && segmentIntersectsBounds(line[0], line[1], contextBounds)),
      sign,
    };
  }).sort((left, right) =>
    Number(left.crossesContext) - Number(right.crossesContext)
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
  ], midpoint, notePoint, rect, contextBounds, Boolean(contextBounds && segmentIntersectsBounds(line[0], line[1], contextBounds)));
}

function radialDimension(dimension, rect, contextBounds) {
  const [center, rim] = dimension.measurement_points.map((point) => clampPoint(point, rect));
  const direction = unitVector(subtract(rim, center));
  if (!direction) {
    return null;
  }
  const normal = [-direction[1], direction[0]];
  const line = [center, rim];
  const midpoint = midpointOf(center, rim);
  const notePoint = addVectors(midpoint, normal.map((value) => value * LABEL_OFFSET));
  const crossesContext = Boolean(contextBounds && segmentIntersectsBounds(center, rim, contextBounds));
  return dimensionRecord(dimension, line, [
    path([center, addVectors(center, normal.map((value) => value * ARROW_SIZE))]),
  ], [arrow(rim, center)], midpoint, notePoint, rect, contextBounds, crossesContext, "R");
}

function diameterDimension(dimension, rect, contextBounds) {
  const [start, end] = dimension.measurement_points.map((point) => clampPoint(point, rect));
  if (distance(start, end) === 0) {
    return null;
  }
  const line = [start, end];
  const midpoint = midpointOf(start, end);
  const crossesContext = Boolean(contextBounds && segmentIntersectsBounds(start, end, contextBounds));
  return dimensionRecord(dimension, line, [path([start, end])], [
    arrow(start, end),
    arrow(end, start),
  ], midpoint, null, rect, contextBounds, crossesContext, "⌀");
}

function angularDimension(dimension, rect) {
  const [origin, radiusPoint] = dimension.measurement_points.map((point) => clampPoint(point, rect));
  const reference = unitVector(dimension.reference_direction);
  const measured = unitVector(dimension.measured_direction);
  if (!reference || !measured) {
    return null;
  }
  const radius = distance(origin, radiusPoint);
  if (radius === 0) {
    return null;
  }
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
  ], labelPoint, null, rect, null, false);
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
  ], labelPoint, null, rect, null, false);
}

function dimensionRecord(dimension, linePoints, extensions, arrows, textPoint, notePoint, rect, contextBounds, crossesContext, valuePrefix = "") {
  const note = typeof dimension.note === "string"
    && !crossesContext
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
      value: dimensionValue(dimension, valuePrefix),
      point: clampPoint(textPoint, rect),
      className: "engineering-dimension",
    },
    note,
    className: "engineering-dimension",
  };
}

function dimensionValue(dimension, prefix = "") {
  const value = dimension.resolvedValue ?? dimension.resolved_value ?? dimension.value ?? "";
  return dimension.unit ? `${prefix}${value} ${dimension.unit}`.trim() : `${prefix}${value}`;
}

function projectionContext(projectedFeatures) {
  const supplied = Array.isArray(projectedFeatures) ? { primitives: projectedFeatures } : projectedFeatures;
  if (!supplied || typeof supplied !== "object") {
    return null;
  }
  const primitives = Array.isArray(supplied.primitives) ? supplied.primitives : [];
  const descriptor = supplied.viewId ? supplied : primitives.find((primitive) => primitive?.projection)?.projection;
  const projectPoint = typeof supplied.projectPoint === "function"
    ? supplied.projectPoint
    : descriptor?.viewId
      ? (point) => projectEngineeringPoint(point, descriptor.viewId, descriptor.frame)
      : null;
  return projectPoint ? { primitives, viewId: descriptor?.viewId || supplied.viewId, projectPoint } : null;
}

function projectDimension(dimension, context) {
  if (!dimension || typeof dimension !== "object" || !context) {
    return null;
  }
  const rawPoints = dimensionPoints(dimension, context.viewId);
  if (!Array.isArray(rawPoints) || rawPoints.length < 2 || !rawPoints.every(isPoint)) {
    return null;
  }
  const measurementPoints = rawPoints.map(context.projectPoint);
  if (!measurementPoints.every(isPoint)) {
    return null;
  }
  const origin = rawPoints[0];
  const projectedOrigin = measurementPoints[0];
  const rawReferenceDirection = dimensionDirection(dimension, "reference_direction", context.viewId);
  const rawMeasuredDirection = dimensionDirection(dimension, "measured_direction", context.viewId);
  const referenceDirection = projectDirection(rawReferenceDirection, origin, projectedOrigin, context.projectPoint);
  const measuredDirection = projectDirection(rawMeasuredDirection, origin, projectedOrigin, context.projectPoint);
  if ((rawReferenceDirection && !referenceDirection) || (rawMeasuredDirection && !measuredDirection)) {
    return null;
  }
  return {
    ...dimension,
    measurement_points: measurementPoints,
    ...(referenceDirection ? { reference_direction: referenceDirection } : {}),
    ...(measuredDirection ? { measured_direction: measuredDirection } : {}),
  };
}

function dimensionPoints(dimension, viewId) {
  if (viewId === "s_q") {
    return dimension.display_measurement_points_s_q_mm || dimension.measurement_points;
  }
  return dimension.model_measurement_points || dimension.measurement_points;
}

function dimensionDirection(dimension, field, viewId) {
  return viewId === "s_q"
    ? dimension[`display_${field}_s_q_mm`] || dimension[field]
    : dimension[field];
}

function projectDirection(direction, origin, projectedOrigin, project) {
  if (direction == null) {
    return null;
  }
  if (!Array.isArray(direction) || direction.length !== origin.length || !direction.every(isFiniteNumber)) {
    return null;
  }
  const projectedEnd = project(addVectors(origin, direction));
  return isPoint(projectedEnd) ? subtract(projectedEnd, projectedOrigin) : null;
}

function projectEngineeringPoint(point, viewId, frame) {
  const projected = projectPoint(point, viewId);
  const points = projected ? transformPoints([projected], frame) : null;
  return points?.[0] || null;
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
    return feature[`display_${field}_s_q_mm`]
      || (feature.coordinate_system === "s_q_mm" || feature.coordinate_system == null ? feature[field] : null);
  }
  return featureCoordinateSystemSupportsView(feature.coordinate_system, viewId) ? feature[field] : null;
}

function sqPoint(feature, field, viewId) {
  if (viewId === "s_q") {
    return feature[`display_${field}_s_q_mm`]
      || (feature.coordinate_system === "s_q_mm" || feature.coordinate_system == null ? feature[field] : null);
  }
  return featureCoordinateSystemSupportsView(feature.coordinate_system, viewId) ? feature[field] : null;
}

function featureCoordinateSystemSupportsView(coordinateSystem, viewId) {
  if (coordinateSystem == null) {
    return true;
  }
  if (viewId === "top") {
    return coordinateSystem === "model_xyz";
  }
  if (viewId === "meridional") {
    return coordinateSystem === "model_xyz" || coordinateSystem === "profile_rz_mm";
  }
  return viewId === "s_q" && coordinateSystem === "s_q_mm";
}

function projectPoints(points, project) {
  return Array.isArray(points) ? points.map(project) : null;
}

function projectPoint(point, viewId, coordinateSystem = null) {
  if (!Array.isArray(point) || !point.every(isFiniteNumber)) {
    return null;
  }
  if (viewId === "top" && point.length >= 3) {
    return [point[0], point[1]];
  }
  if (viewId === "meridional" && point.length >= 3) {
    return [Math.hypot(point[0], point[1]), point[2]];
  }
  if (viewId === "meridional" && coordinateSystem !== "s_q_mm" && point.length === 2) {
    return [point[0], point[1]];
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

function segmentIntersectsBounds(start, end, bounds) {
  let minimumT = 0;
  let maximumT = 1;
  for (let axis = 0; axis < 2; axis += 1) {
    const delta = end[axis] - start[axis];
    const minimum = axis === 0 ? bounds.minX : bounds.minY;
    const maximum = axis === 0 ? bounds.maxX : bounds.maxY;
    if (delta === 0) {
      if (start[axis] < minimum || start[axis] > maximum) {
        return false;
      }
      continue;
    }
    const first = (minimum - start[axis]) / delta;
    const second = (maximum - start[axis]) / delta;
    minimumT = Math.max(minimumT, Math.min(first, second));
    maximumT = Math.min(maximumT, Math.max(first, second));
    if (minimumT > maximumT) {
      return false;
    }
  }
  return true;
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
