export function profilesFromManifest(manifest) {
  const profiles = manifest?.geometry_kernel?.meridional_profiles || {};
  return {
    hub_profile: cloneProfile(profiles.hub || defaultHubProfile()),
    tip_or_shroud_profile: cloneProfile(profiles.tip_or_shroud || defaultTipProfile()),
  };
}

export function profileEditorBounds(profiles) {
  const points = [
    ...(profiles?.hub_profile?.control_points || []),
    ...(profiles?.tip_or_shroud_profile?.control_points || []),
  ];
  const radii = points.map((point) => point[0]);
  const zValues = points.map((point) => point[1]);
  const rMin = Math.min(...radii);
  const rMax = Math.max(...radii);
  const zMin = Math.min(...zValues);
  const zMax = Math.max(...zValues);
  return {
    rMin,
    rMax,
    zMin,
    zMax,
    rPadding: Math.max(10, (rMax - rMin) * 0.08),
    zPadding: Math.max(10, (zMax - zMin) * 0.1),
  };
}

export function rzToScreen(point, bounds, viewport) {
  const rMin = bounds.rMin - bounds.rPadding;
  const rMax = bounds.rMax + bounds.rPadding;
  const zMin = bounds.zMin - bounds.zPadding;
  const zMax = bounds.zMax + bounds.zPadding;
  return [
    ((point[0] - rMin) / (rMax - rMin)) * viewport.width,
    viewport.height - ((point[1] - zMin) / (zMax - zMin)) * viewport.height,
  ];
}

export function screenToRz(point, bounds, viewport) {
  const rMin = bounds.rMin - bounds.rPadding;
  const rMax = bounds.rMax + bounds.rPadding;
  const zMin = bounds.zMin - bounds.zPadding;
  const zMax = bounds.zMax + bounds.zPadding;
  return [
    round(rMin + (point[0] / viewport.width) * (rMax - rMin)),
    round(zMin + ((viewport.height - point[1]) / viewport.height) * (zMax - zMin)),
  ];
}

export function updateControlPoint(profiles, profileId, pointIndex, rzPoint) {
  const next = {
    hub_profile: cloneProfile(profiles.hub_profile),
    tip_or_shroud_profile: cloneProfile(profiles.tip_or_shroud_profile),
  };
  next[profileId].control_points = next[profileId].control_points.map((point, index) =>
    index === pointIndex ? [round(rzPoint[0]), round(rzPoint[1])] : point,
  );
  return next;
}

export function validateProfileOverrides(profiles) {
  for (const profileId of ["hub_profile", "tip_or_shroud_profile"]) {
    const profile = profiles?.[profileId];
    if (!profile || profile.kind !== "nurbs_curve" || profile.degree !== 3) {
      return { status: "FAIL", reason: `${profileId} must be a cubic nurbs_curve` };
    }
    if (!Array.isArray(profile.control_points) || profile.control_points.length < profile.degree + 1) {
      return { status: "FAIL", reason: `${profileId} must have at least ${profile.degree + 1} control points` };
    }
    if (!Array.isArray(profile.weights) || profile.weights.length !== profile.control_points.length) {
      return { status: "FAIL", reason: `${profileId} weights must match control point count` };
    }
    if (!Array.isArray(profile.knots) || profile.knots.length !== profile.control_points.length + profile.degree + 1) {
      return { status: "FAIL", reason: `${profileId} knot count must equal control point count + degree + 1` };
    }
    for (const point of profile.control_points) {
      if (!Number.isFinite(point[0]) || !Number.isFinite(point[1]) || point[0] <= 0) {
        return { status: "FAIL", reason: `${profileId} control points need positive finite radius` };
      }
    }
    for (const weight of profile.weights) {
      if (!Number.isFinite(weight) || weight <= 0) {
        return { status: "FAIL", reason: `${profileId} weights must be positive finite values` };
      }
    }
    for (let index = 0; index < profile.knots.length; index += 1) {
      if (!Number.isFinite(profile.knots[index]) || (index > 0 && profile.knots[index - 1] > profile.knots[index])) {
        return { status: "FAIL", reason: `${profileId} knots must be finite and non-decreasing` };
      }
    }
  }
  for (let index = 0; index <= 8; index += 1) {
    const u = index / 8;
    const hub = nurbsPoint(profiles.hub_profile, u);
    const tip = nurbsPoint(profiles.tip_or_shroud_profile, u);
    if (tip[0] <= hub[0] || tip[1] <= hub[1]) {
      return { status: "FAIL", reason: "tip profile must remain outside and above hub profile" };
    }
  }
  return { status: "PASS" };
}

export function profileOverridesPayload(profiles) {
  return {
    hub_profile: cloneProfile(profiles.hub_profile),
    tip_or_shroud_profile: cloneProfile(profiles.tip_or_shroud_profile),
  };
}

function nurbsPoint(profile, u) {
  const points = profile.control_points;
  const weights = profile.weights;
  const knots = profile.knots;
  const degree = profile.degree;
  const basis = points.map((_, index) => nurbsBasis(index, degree, Math.min(1, Math.max(0, u)), knots));
  const denominator = basis.reduce((total, value, index) => total + value * weights[index], 0);
  return [
    basis.reduce((total, value, index) => total + value * weights[index] * points[index][0], 0) / denominator,
    basis.reduce((total, value, index) => total + value * weights[index] * points[index][1], 0) / denominator,
  ];
}

function nurbsBasis(index, degree, u, knots) {
  if (degree === 0) {
    return (knots[index] <= u && u < knots[index + 1]) || (u === 1 && knots[index] <= u && u <= knots[index + 1])
      ? 1
      : 0;
  }
  const leftDenominator = knots[index + degree] - knots[index];
  const rightDenominator = knots[index + degree + 1] - knots[index + 1];
  const left =
    leftDenominator > 0 ? ((u - knots[index]) / leftDenominator) * nurbsBasis(index, degree - 1, u, knots) : 0;
  const right =
    rightDenominator > 0
      ? ((knots[index + degree + 1] - u) / rightDenominator) * nurbsBasis(index + 1, degree - 1, u, knots)
      : 0;
  return left + right;
}

function cloneProfile(profile) {
  const degree = profile.degree ?? 3;
  const controlPoints = (profile.control_points || []).map((point) => [round(point[0]), round(point[1])]);
  return {
    ...profile,
    degree,
    control_points: controlPoints,
    weights: profile.weights?.length === controlPoints.length ? [...profile.weights] : Array(controlPoints.length).fill(1),
    knots:
      profile.knots?.length === controlPoints.length + degree + 1
        ? [...profile.knots]
        : clampedOpenUniformKnots(controlPoints.length, degree),
    coordinate_system: profile.coordinate_system || "rz_meridional_mm",
  };
}

function clampedOpenUniformKnots(pointCount, degree) {
  const interiorCount = Math.max(0, pointCount - degree - 1);
  const interiors = Array.from({ length: interiorCount }, (_, index) => (index + 1) / (interiorCount + 1));
  return [...Array(degree + 1).fill(0), ...interiors, ...Array(degree + 1).fill(1)];
}

function defaultHubProfile() {
  return {
    kind: "nurbs_curve",
    degree: 3,
    coordinate_system: "rz_meridional_mm",
    control_points: [[150, 400], [170, 250], [220, 150], [330, 50], [480, 10], [580, 0]],
    weights: [1, 1, 1, 1, 1, 1],
    knots: [0, 0, 0, 0, 1 / 3, 2 / 3, 1, 1, 1, 1],
  };
}

function defaultTipProfile() {
  return {
    kind: "nurbs_curve",
    degree: 3,
    coordinate_system: "rz_meridional_mm",
    control_points: [[230, 401], [250, 270], [310, 170], [400, 90], [490, 50], [581, 30]],
    weights: [1, 1, 1, 1, 1, 1],
    knots: [0, 0, 0, 0, 1 / 3, 2 / 3, 1, 1, 1, 1],
  };
}

function round(value) {
  return Math.round(Number(value) * 1000) / 1000;
}
