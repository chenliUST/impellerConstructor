import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  curveEditorBounds,
  curveOverridesPayload,
  curveToScreen,
  defaultBladeCurveControls,
  screenToCurvePoint,
  updateCurvePoint,
  validateCurveOverrides,
} from "./bladeCurveEditorModel.js";

describe("blade curve editor model", () => {
  test("creates default intrinsic blade curve controls from scalar parameters", () => {
    const controls = defaultBladeCurveControls({ blade_wrap_deg: 118, blade_thickness_mm: 18 });

    assert.equal(controls.blade_mean.theta_center_u_curve.coordinate_system, "u_theta_deg");
    assert.equal(controls.thickness.thickness_u_curve.coordinate_system, "u_thickness_mm");
    assert.equal(controls.blade_mean.theta_center_u_curve.control_points.length, 7);
    assert.equal(controls.blade_mean.span_lean_u_curve.control_points.length, 5);
    assert.deepEqual(controls.blade_edges.leading_edge_sweep_v_curve.control_points, [[0, 0], [0.25, 0], [0.5, 0], [0.75, 0], [1, 0]]);
    assert.deepEqual(controls.blade_edges.trailing_edge_sweep_v_curve.control_points, [[0, 0], [0.25, 0], [0.5, 0], [0.75, 0], [1, 0]]);
    assert.equal(controls.thickness.thickness_u_curve.control_points.length, 5);
    assert.equal(validateCurveOverrides(controls).status, "PASS");
  });

  test("round trips intrinsic curve coordinates through screen space", () => {
    const controls = defaultBladeCurveControls({ blade_wrap_deg: 118, blade_thickness_mm: 18 });
    const curve = controls.blade_mean.theta_center_u_curve;
    const bounds = curveEditorBounds(curve);
    const viewport = { width: 260, height: 72 };
    const point = [0.5, -60];

    assert.deepEqual(screenToCurvePoint(curveToScreen(point, bounds, viewport), bounds, viewport), point);
  });

  test("clamps interior curve point between neighbors and preserves endpoints", () => {
    const controls = defaultBladeCurveControls({ blade_wrap_deg: 118, blade_thickness_mm: 18 });
    const changed = updateCurvePoint(controls, "blade_mean", "theta_center_u_curve", 1, [0.99, -40]);

    assert.equal(changed.blade_mean.theta_center_u_curve.control_points[0][0], 0);
    assert.equal(changed.blade_mean.theta_center_u_curve.control_points.at(-1)[0], 1);
    assert.ok(changed.blade_mean.theta_center_u_curve.control_points[1][0] < changed.blade_mean.theta_center_u_curve.control_points[2][0]);
  });

  test("rejects nonpositive thickness and excessive support offsets", () => {
    const controls = defaultBladeCurveControls({ blade_wrap_deg: 118, blade_thickness_mm: 18 });
    const badThickness = updateCurvePoint(controls, "thickness", "thickness_u_curve", 1, [0.5, 0]);
    const badSweep = updateCurvePoint(controls, "blade_edges", "leading_edge_sweep_v_curve", 1, [0.5, 0.5]);

    assert.equal(validateCurveOverrides(badThickness).status, "FAIL");
    assert.equal(validateCurveOverrides(badSweep).status, "FAIL");
  });

  test("emits deterministic payload shape", () => {
    const controls = defaultBladeCurveControls({ blade_wrap_deg: 118, blade_thickness_mm: 18 });
    const payload = curveOverridesPayload(controls);

    assert.deepEqual(payload.blade_mean.theta_center_u_curve.control_points[0], [0, 0]);
    assert.equal(payload.blade_edges.leading_edge_sweep_v_curve.coordinate_system, "v_support_u_offset");
  });
});
