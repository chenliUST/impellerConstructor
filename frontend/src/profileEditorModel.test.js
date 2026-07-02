import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  profileEditorBounds,
  profileOverridesPayload,
  profilesFromManifest,
  rzToScreen,
  screenToRz,
  updateControlPoint,
  validateProfileOverrides,
} from "./profileEditorModel.js";

const manifest = {
  geometry_kernel: {
    meridional_profiles: {
      hub: {
        kind: "nurbs_curve",
        degree: 3,
        coordinate_system: "rz_meridional_mm",
        control_points: [[150, 400], [170, 250], [220, 150], [330, 50], [480, 10], [580, 0]],
        weights: [1, 1, 1, 1, 1, 1],
        knots: [0, 0, 0, 0, 1 / 3, 2 / 3, 1, 1, 1, 1],
      },
      tip_or_shroud: {
        kind: "nurbs_curve",
        degree: 3,
        coordinate_system: "rz_meridional_mm",
        control_points: [[230, 401], [250, 270], [310, 170], [400, 90], [490, 50], [581, 30]],
        weights: [1, 1, 1, 1, 1, 1],
        knots: [0, 0, 0, 0, 1 / 3, 2 / 3, 1, 1, 1, 1],
      },
    },
  },
};

describe("profile editor model", () => {
  test("loads hub and tip profiles from manifest", () => {
    const profiles = profilesFromManifest(manifest);

    assert.equal(profiles.hub_profile.control_points.length, 6);
    assert.equal(profiles.tip_or_shroud_profile.control_points.length, 6);
  });

  test("default fallback profiles use the v0.5 six point baseline", () => {
    const profiles = profilesFromManifest({});

    assert.deepEqual(profiles.hub_profile.control_points, manifest.geometry_kernel.meridional_profiles.hub.control_points);
    assert.deepEqual(
      profiles.tip_or_shroud_profile.control_points,
      manifest.geometry_kernel.meridional_profiles.tip_or_shroud.control_points,
    );
  });

  test("round trips R-Z coordinates through screen space", () => {
    const profiles = profilesFromManifest(manifest);
    const bounds = profileEditorBounds(profiles);
    const viewport = { width: 300, height: 180 };
    const rz = [320, 90];
    const screen = rzToScreen(rz, bounds, viewport);

    assert.deepEqual(screenToRz(screen, bounds, viewport), rz);
  });

  test("updates one control point deterministically", () => {
    const profiles = profilesFromManifest(manifest);
    const changed = updateControlPoint(profiles, "hub_profile", 1, [275.1234, 62.6789]);

    assert.deepEqual(changed.hub_profile.control_points[1], [275.123, 62.679]);
    assert.deepEqual(profiles.hub_profile.control_points[1], [170, 250]);
    assert.deepEqual(profileOverridesPayload(changed).hub_profile.control_points[1], [275.123, 62.679]);
  });

  test("validates positive radii and tip outside hub", () => {
    const profiles = profilesFromManifest(manifest);
    const invalid = updateControlPoint(profiles, "hub_profile", 0, [-1, 80]);

    assert.equal(validateProfileOverrides(profiles).status, "PASS");
    assert.equal(validateProfileOverrides(invalid).status, "FAIL");
  });
});
