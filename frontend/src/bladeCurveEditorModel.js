export function defaultBladeCurveControls(parameters = {}) {
  const wrap = Number(parameters.blade_wrap_deg ?? 118);
  const lean = Number(parameters.blade_lean_deg ?? 0);
  const leadingLean = Number(parameters.leading_edge_lean_deg ?? lean);
  const trailingLean = Number(parameters.trailing_edge_lean_deg ?? lean);
  const leadingSweep = Number(parameters.leading_edge_sweep_mm ?? 30);
  const trailingSweep = Number(parameters.trailing_edge_sweep_mm ?? -45);
  const inlet = Number(parameters.inlet_radius_mm ?? 180);
  const exit = Number(parameters.exit_radius_mm ?? 620);
  const radialSpan = Math.max(1, exit - inlet);
  const thickness = Number(parameters.blade_thickness_mm ?? 18);
  return {
    blade_mean: {
      theta_center_u_curve: {
        coordinate_system: "u_theta_deg",
        control_points: [[0, 0], [0.33, -wrap * 0.18], [0.66, -wrap * 0.68], [1, -wrap]],
      },
      span_lean_u_curve: {
        coordinate_system: "u_lean_deg",
        control_points: [[0, leadingLean], [0.5, lean], [1, trailingLean]],
      },
    },
    blade_edges: {
      leading_edge_sweep_v_curve: {
        coordinate_system: "v_support_u_offset",
        control_points: [[0, -leadingSweep / (2 * radialSpan)], [0.5, 0], [1, leadingSweep / (2 * radialSpan)]],
      },
      trailing_edge_sweep_v_curve: {
        coordinate_system: "v_support_u_offset",
        control_points: [[0, -trailingSweep / (2 * radialSpan)], [0.5, 0], [1, trailingSweep / (2 * radialSpan)]],
      },
    },
    thickness: {
      thickness_u_curve: {
        coordinate_system: "u_thickness_mm",
        control_points: [[0, thickness], [0.5, thickness * 0.78], [1, thickness * 0.55]],
      },
    },
  };
}

export function curveEditorBounds(curve) {
  const values = curve.control_points.map((point) => point[1]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max(1, (max - min) * 0.18);
  return { min: min - padding, max: max + padding };
}

export function curveToScreen(point, bounds, viewport) {
  return [
    point[0] * viewport.width,
    viewport.height - ((point[1] - bounds.min) / (bounds.max - bounds.min)) * viewport.height,
  ];
}

export function screenToCurvePoint(point, bounds, viewport) {
  const t = Math.min(1, Math.max(0, point[0] / viewport.width));
  const value = bounds.min + ((viewport.height - point[1]) / viewport.height) * (bounds.max - bounds.min);
  return [round(t), round(value)];
}

export function updateCurvePoint(controls, group, curveId, pointIndex, point) {
  const next = cloneControls(controls);
  const points = next[group][curveId].control_points;
  const endpoint = pointIndex === 0 || pointIndex === points.length - 1;
  points[pointIndex] = [
    endpoint ? points[pointIndex][0] : clampInteriorT(points, pointIndex, point[0]),
    round(point[1]),
  ];
  return next;
}

export function validateCurveOverrides(controls) {
  for (const [group, curves] of Object.entries(controls || {})) {
    for (const [curveId, curve] of Object.entries(curves || {})) {
      let previousT = -1;
      for (const point of curve.control_points || []) {
        if (!Number.isFinite(point[0]) || !Number.isFinite(point[1]) || point[0] <= previousT || point[0] < 0 || point[0] > 1) {
          return { status: "FAIL", reason: `${group}.${curveId} t values must be finite and increasing` };
        }
        if (curve.coordinate_system === "u_thickness_mm" && point[1] <= 0) {
          return { status: "FAIL", reason: "thickness values must be positive" };
        }
        if (curve.coordinate_system === "v_support_u_offset" && Math.abs(point[1]) > 0.45) {
          return { status: "FAIL", reason: "support offsets must be <= 0.45" };
        }
        previousT = point[0];
      }
    }
  }
  return { status: "PASS" };
}

export function curveOverridesPayload(controls) {
  return cloneControls(controls);
}

function clampInteriorT(points, pointIndex, nextT) {
  const low = points[pointIndex - 1][0] + 0.001;
  const high = points[pointIndex + 1][0] - 0.001;
  return round(Math.min(high, Math.max(low, nextT)));
}

function cloneControls(controls) {
  return Object.fromEntries(
    Object.entries(controls || {}).map(([group, curves]) => [
      group,
      Object.fromEntries(
        Object.entries(curves || {}).map(([curveId, curve]) => [
          curveId,
          {
            coordinate_system: curve.coordinate_system,
            control_points: curve.control_points.map((point) => [round(point[0]), round(point[1])]),
          },
        ]),
      ),
    ]),
  );
}

function round(value) {
  return Math.round(Number(value) * 1000) / 1000;
}
