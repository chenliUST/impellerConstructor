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
    if (!Array.isArray(profile.control_points) || profile.control_points.length !== 4) {
      return { status: "FAIL", reason: `${profileId} must have 4 control points` };
    }
    for (const point of profile.control_points) {
      if (!Number.isFinite(point[0]) || !Number.isFinite(point[1]) || point[0] <= 0) {
        return { status: "FAIL", reason: `${profileId} control points need positive finite radius` };
      }
    }
  }
  for (let index = 0; index <= 8; index += 1) {
    const u = index / 8;
    const hub = cubicPoint(profiles.hub_profile, u);
    const tip = cubicPoint(profiles.tip_or_shroud_profile, u);
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

function cubicPoint(profile, u) {
  const points = profile.control_points;
  const weights = profile.weights || [1, 1, 1, 1];
  const one = 1 - u;
  const basis = [one ** 3, 3 * one * one * u, 3 * one * u * u, u ** 3];
  const denominator = basis.reduce((total, value, index) => total + value * weights[index], 0);
  return [
    basis.reduce((total, value, index) => total + value * weights[index] * points[index][0], 0) / denominator,
    basis.reduce((total, value, index) => total + value * weights[index] * points[index][1], 0) / denominator,
  ];
}

function cloneProfile(profile) {
  return {
    ...profile,
    control_points: (profile.control_points || []).map((point) => [round(point[0]), round(point[1])]),
    weights: [...(profile.weights || [1, 1, 1, 1])],
    knots: [...(profile.knots || [0, 0, 0, 0, 1, 1, 1, 1])],
    coordinate_system: profile.coordinate_system || "rz_meridional_mm",
  };
}

function defaultHubProfile() {
  return {
    kind: "nurbs_curve",
    degree: 3,
    coordinate_system: "rz_meridional_mm",
    control_points: [[120, 80], [260, 60], [460, 24], [570, 0]],
    weights: [1, 1, 1, 1],
    knots: [0, 0, 0, 0, 1, 1, 1, 1],
  };
}

function defaultTipProfile() {
  return {
    kind: "nurbs_curve",
    degree: 3,
    coordinate_system: "rz_meridional_mm",
    control_points: [[180, 230], [320, 226], [500, 128], [620, 72]],
    weights: [1, 1, 1, 1],
    knots: [0, 0, 0, 0, 1, 1, 1, 1],
  };
}

function round(value) {
  return Math.round(Number(value) * 1000) / 1000;
}
