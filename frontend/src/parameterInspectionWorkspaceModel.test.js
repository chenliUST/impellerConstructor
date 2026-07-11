import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  WORKSPACE_TABS,
  initialWorkspaceState,
  preserveEquivalentParameterId,
  transitionWorkspaceState,
  workspaceRenderProps,
} from "./parameterInspectionWorkspaceModel.js";

function parameter({
  bladeId = "blade_0",
  stationIndex = 0,
  kind,
  segmentName = null,
  controlIndex = null,
  applicableViews = ["s_q", "blade_3d"],
}) {
  const stationId = `${bladeId}:span_${stationIndex}`;
  const loopId = `${stationId}:loop`;
  const scope = {
    blade_instance_id: bladeId,
    span_station_id: stationId,
    section_loop_id: loopId,
    source_station_index: stationIndex,
  };
  if (segmentName) {
    scope.section_segment_id = `${loopId}:${segmentName}`;
    scope.source_segment_name = segmentName;
  }
  if (controlIndex != null) {
    scope.source_control_index = controlIndex;
    scope.source_control_point_id = `${loopId}:${segmentName}:control_${controlIndex}:instance`;
  }

  const semanticSuffix = kind === "thickness"
    ? "thickness"
    : kind === "sagitta"
      ? `section:${segmentName}:sagitta`
      : `section:${segmentName}:control:${controlIndex}:s`;
  return {
    id: `blade:${bladeId}:station:${stationId}:${semanticSuffix}`,
    groupId: "section_loop",
    label: kind === "thickness"
      ? "Blade thickness"
      : kind === "sagitta"
        ? `${segmentName} sagitta`
        : `${segmentName} control ${controlIndex} s`,
    applicableViews,
    selectionScope: scope,
    features: [{ id: `${bladeId}:${stationIndex}:${semanticSuffix}:feature`, kind: "control_point" }],
    dimension: { kind: kind === "sagitta" ? "arc_height" : "control_coordinate" },
  };
}

function workspaceModel(parameters) {
  return {
    status: "ready",
    engineeringParameters: parameters,
    indices: {
      blades: {
        blade_0: {
          blade_instance_id: "blade_0",
          span_station_ids: ["blade_0:span_0", "blade_0:span_1", "blade_0:span_2"],
        },
        blade_1: {
          blade_instance_id: "blade_1",
          span_station_ids: ["blade_1:span_0", "blade_1:span_1", "blade_1:span_2"],
        },
      },
      stations: Object.fromEntries(
        ["blade_0", "blade_1"].flatMap((bladeId) => [0, 1, 2].map((stationIndex) => [
          `${bladeId}:span_${stationIndex}`,
          { span_station_id: `${bladeId}:span_${stationIndex}`, blade_instance_id: bladeId },
        ])),
      ),
    },
  };
}

describe("parameter inspection workspace model", () => {
  test("declares exactly the approved workspace tabs", () => {
    assert.deepEqual(WORKSPACE_TABS.map((tab) => tab.id), ["top", "meridional", "s_q_blade"]);
  });

  test("maps generated thickness across station instances", () => {
    const current = parameter({ kind: "thickness", stationIndex: 0 });
    const target = parameter({ kind: "thickness", stationIndex: 2 });
    const model = workspaceModel([current, target]);

    assert.equal(
      preserveEquivalentParameterId(
        model,
        current.id,
        { bladeId: "blade_0", spanStationId: "blade_0:span_2" },
        "s_q_blade",
      ),
      target.id,
    );
  });

  test("maps generated control coordinates across blade instances while preserving segment and control index", () => {
    const current = parameter({ kind: "control", bladeId: "blade_0", stationIndex: 1, segmentName: "pressure_side", controlIndex: 2 });
    const wrongSegment = parameter({ kind: "control", bladeId: "blade_1", stationIndex: 1, segmentName: "suction_side", controlIndex: 2 });
    const wrongControl = parameter({ kind: "control", bladeId: "blade_1", stationIndex: 1, segmentName: "pressure_side", controlIndex: 3 });
    const target = parameter({ kind: "control", bladeId: "blade_1", stationIndex: 1, segmentName: "pressure_side", controlIndex: 2 });
    const model = workspaceModel([current, wrongSegment, wrongControl, target]);

    assert.equal(
      preserveEquivalentParameterId(
        model,
        current.id,
        { bladeId: "blade_1", spanStationId: "blade_1:span_1" },
        "s_q_blade",
      ),
      target.id,
    );
  });

  test("maps generated sagitta across station segment instances", () => {
    const current = parameter({ kind: "sagitta", stationIndex: 0, segmentName: "leading_edge" });
    const wrong = parameter({ kind: "sagitta", stationIndex: 2, segmentName: "trailing_edge" });
    const target = parameter({ kind: "sagitta", stationIndex: 2, segmentName: "leading_edge" });
    const model = workspaceModel([current, wrong, target]);

    assert.equal(
      preserveEquivalentParameterId(
        model,
        current.id,
        { bladeId: "blade_0", spanStationId: "blade_0:span_2" },
        "s_q_blade",
      ),
      target.id,
    );
  });

  test("active parameter click clears and tab transition clears inapplicable selection", () => {
    const topParameter = parameter({ kind: "thickness", applicableViews: ["top"] });
    const model = workspaceModel([topParameter]);
    const selected = {
      ...initialWorkspaceState(model),
      activeTab: "top",
      selectedParameterId: topParameter.id,
    };

    assert.equal(
      transitionWorkspaceState(model, selected, { type: "parameter", parameterId: null }).selectedParameterId,
      null,
    );
    assert.equal(
      transitionWorkspaceState(model, selected, { type: "tab", viewId: "meridional" }).selectedParameterId,
      null,
    );
  });

  test("synchronizes selected drawing and blade props and emits null selected evidence", () => {
    const selectedParameter = parameter({ kind: "thickness" });
    const model = workspaceModel([selectedParameter]);
    const selectedState = {
      ...initialWorkspaceState(model),
      activeTab: "s_q_blade",
      selectedParameterId: selectedParameter.id,
    };
    const selectedProps = workspaceRenderProps(model, selectedState);

    assert.equal(selectedProps.drawing.selectedParameter, selectedParameter);
    assert.equal(selectedProps.blade.selectedParameter, selectedParameter);
    assert.equal(selectedProps.drawing.selectedParameterId, selectedParameter.id);
    assert.equal(selectedProps.blade.selectedParameterId, selectedParameter.id);

    const emptyProps = workspaceRenderProps(model, { ...selectedState, selectedParameterId: null });
    assert.equal(emptyProps.drawing.selectedParameter, null);
    assert.equal(emptyProps.blade.selectedParameter, null);
    assert.equal(emptyProps.drawing.selectedParameterId, null);
    assert.equal(emptyProps.blade.selectedParameterId, null);
  });

  test("maps blade and station events before preserving equivalent parameters", () => {
    const current = parameter({ kind: "thickness", bladeId: "blade_0", stationIndex: 1 });
    const bladeTarget = parameter({ kind: "thickness", bladeId: "blade_1", stationIndex: 1 });
    const stationTarget = parameter({ kind: "thickness", bladeId: "blade_1", stationIndex: 2 });
    const model = workspaceModel([current, bladeTarget, stationTarget]);
    const state = {
      activeTab: "s_q_blade",
      navigation: { bladeId: "blade_0", spanStationId: "blade_0:span_1" },
      selectedParameterId: current.id,
    };

    const bladeState = transitionWorkspaceState(model, state, { type: "blade", bladeId: "blade_1" });
    assert.deepEqual(bladeState.navigation, { bladeId: "blade_1", spanStationId: "blade_1:span_1" });
    assert.equal(bladeState.selectedParameterId, bladeTarget.id);

    const stationState = transitionWorkspaceState(model, bladeState, {
      type: "station",
      spanStationId: "blade_1:span_2",
    });
    assert.deepEqual(stationState.navigation, { bladeId: "blade_1", spanStationId: "blade_1:span_2" });
    assert.equal(stationState.selectedParameterId, stationTarget.id);
  });
});
