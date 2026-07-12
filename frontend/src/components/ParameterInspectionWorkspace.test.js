import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { projectEngineeringFeature } from "../engineeringDrawingModel.js";
import {
  engineeringContextFeatures,
  inspectionWorkspaceBodyStyle,
} from "../parameterInspectionWorkspaceModel.js";

describe("ParameterInspectionWorkspace drawing context", () => {
  test("bounds the workspace body to the viewport so narrow drawing panes do not stretch with the parameter list", () => {
    assert.deepEqual(inspectionWorkspaceBodyStyle(), {
      height: "calc(100vh - 92px)",
      maxHeight: "calc(100vh - 92px)",
    });
  });

  test("builds nonblank Top and Meridional context from context-role geometry only", () => {
    const groups = [{
      parameters: [{
        applicableViews: ["top", "meridional"],
        features: [
          {
            id: "top-blade-contour",
            kind: "polyline",
            coordinate_system: "model_xyz",
            rendering_role: "drawing_context",
            points: [[10, 0, 0], [20, 10, 5]],
          },
          {
            id: "hub-profile",
            kind: "nurbs_curve",
            coordinate_system: "profile_rz_mm",
            rendering_role: "drawing_context",
            control_points: [[10, 20], [30, 0]],
          },
          {
            id: "selected-axis",
            kind: "reference_axis",
            coordinate_system: "model_xyz",
            rendering_role: "selected_feature",
            origin: [0, 0, 0],
            direction: [1, 0, 0],
          },
        ],
      }],
    }];

    const top = engineeringContextFeatures(groups, "top")
      .map((feature) => projectEngineeringFeature({ ...feature, className: "engineering-context" }, "top"))
      .filter(Boolean);
    const meridional = engineeringContextFeatures(groups, "meridional")
      .map((feature) => projectEngineeringFeature({ ...feature, className: "engineering-context" }, "meridional"))
      .filter(Boolean);

    assert.equal(top.length, 1);
    assert.equal(meridional.length, 2);
    assert.equal(top.every((primitive) => primitive.className === "engineering-context"), true);
    assert.equal(meridional.every((primitive) => primitive.className === "engineering-context"), true);
    assert.equal([...top, ...meridional].some((primitive) => primitive.id === "selected-axis"), false);
  });
});
