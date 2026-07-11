import React, { useLayoutEffect, useMemo, useState } from "react";

import {
  engineeringParameterGroups,
  resolveParameterInspection,
} from "../parameterInspectionModel.js?v=1.1.5";
import {
  WORKSPACE_TABS,
  engineeringContextFeatures,
  inspectionWorkspaceBodyStyle,
  initialWorkspaceState,
  parameterAppliesToWorkspaceView,
  transitionWorkspaceState,
  workspaceRenderProps,
} from "../parameterInspectionWorkspaceModel.js?v=1.1.5";
import {
  engineeringDrawingBounds,
  projectEngineeringDimensionEvidence,
  projectEngineeringFeature,
} from "../engineeringDrawingModel.js?v=1.1.7";
import { BladeFeatureScene } from "./BladeFeatureScene.js?v=1.1.5";
import { EngineeringDrawingView } from "./EngineeringDrawingView.js?v=1.1.7";
import { ParameterFeatureBrowser } from "./ParameterFeatureBrowser.js?v=1.1.5";

const h = React.createElement;
const EMPTY_INSPECTION_ERROR = "parameter_inspection_not_generated";
const DRAWING_VIEWPORT = { x: 0, y: 0, width: 1000, height: 700 };

export function ParameterInspectionWorkspace({ manifest = null }) {
  const model = useMemo(() => resolveParameterInspection(manifest), [manifest]);
  const [workspaceState, setWorkspaceState] = useState(() => initialWorkspaceState(model));
  const generationId = model.contract?.generation_id;
  const { activeTab, navigation, selectedParameterId } = workspaceState;

  useLayoutEffect(() => {
    setWorkspaceState(initialWorkspaceState(model));
  }, [generationId, model]);

  const context = {
    bladeId: navigation.bladeId,
    spanStationId: navigation.spanStationId,
  };
  const parameterGroups = useMemo(
    () => engineeringParameterGroups(model, context),
    [model, navigation.bladeId, navigation.spanStationId],
  );
  const browserGroups = useMemo(
    () => parameterGroups.map((group) => ({
      ...group,
      parameters: group.parameters.map((parameter) => ({
        ...parameter,
        disabled: !parameterAppliesToWorkspaceView(parameter, activeTab),
      })),
    })),
    [activeTab, parameterGroups],
  );
  const renderProps = workspaceRenderProps(model, workspaceState);
  const drawingContext = useMemo(
    () => engineeringContextPrimitives(parameterGroups, renderProps.drawing.viewId, renderProps.drawing.selectedParameter),
    [parameterGroups, renderProps.drawing.viewId, renderProps.drawing.selectedParameter],
  );
  const selectedBlade = model.indices?.blades?.[navigation.bladeId];
  const bladeSurfaceIds = selectedBlade?.surface_ids || [];

  function handleBladeSelection(bladeId) {
    setWorkspaceState((current) =>
      transitionWorkspaceState(model, current, { type: "blade", bladeId }));
  }

  function handleStationSelection(spanStationId) {
    setWorkspaceState((current) =>
      transitionWorkspaceState(model, current, { type: "station", spanStationId }));
  }

  function handleTabSelection(viewId) {
    setWorkspaceState((current) =>
      transitionWorkspaceState(model, current, { type: "tab", viewId }));
  }

  function handleParameterSelection(parameterId) {
    setWorkspaceState((current) =>
      transitionWorkspaceState(model, current, { type: "parameter", parameterId }));
  }

  if (model.status === "empty" && model.errorCode === EMPTY_INSPECTION_ERROR) {
    return h(
      "section",
      { className: "parameter-inspection-workspace inspection-workspace-status", "data-testid": "inspection-workspace" },
      h("p", null, "Generate a model to inspect resolved geometry."),
    );
  }

  if (model.status === "error") {
    return h(
      "section",
      { className: "parameter-inspection-workspace inspection-workspace-status", "data-testid": "inspection-workspace" },
      h("p", { className: "inspection-error-banner" }, model.errorCode),
    );
  }

  return h(
    "section",
    {
      className: "parameter-inspection-workspace",
      "data-testid": "inspection-workspace",
      "data-active-tab": activeTab,
      "data-selected-blade-id": navigation.bladeId || "",
      "data-selected-station-id": navigation.spanStationId || "",
      "data-selected-parameter-id": selectedParameterId || "",
    },
    h(
      "div",
      { className: "inspection-provenance-badge", "data-testid": "inspection-provenance" },
      "Resolved manifest | runtime 1.1.3 | geometry 1.1.2",
    ),
    h(
      "div",
      { className: "inspection-workspace-toolbar" },
      h(
        "div",
        { className: "inspection-tab-list", role: "tablist", "aria-label": "Inspection views" },
        WORKSPACE_TABS.map((tab) => h(
          "button",
          {
            key: tab.id,
            className: activeTab === tab.id ? "selected" : "",
            type: "button",
            role: "tab",
            "aria-selected": activeTab === tab.id,
            "data-testid": `inspection-tab-${tab.id}`,
            onClick: () => handleTabSelection(tab.id),
          },
          tab.label,
        )),
      ),
      h(
        "div",
        { className: "inspection-entity-selectors" },
        h(
          "label",
          null,
          h("span", null, "Blade"),
          h(
            "select",
            {
              value: navigation.bladeId || "",
              "data-testid": "inspection-blade-selector",
              onInput: (event) => handleBladeSelection(event.target.value),
            },
            Object.values(model.indices.blades).map((blade) =>
              h("option", { key: blade.blade_instance_id, value: blade.blade_instance_id }, bladeLabel(blade))),
          ),
        ),
        h(
          "label",
          null,
          h("span", null, "Station"),
          h(
            "select",
            {
              value: navigation.spanStationId || "",
              "data-testid": "inspection-station-selector",
              onInput: (event) => handleStationSelection(event.target.value),
            },
            (selectedBlade?.span_station_ids || []).map((stationId) =>
              h("option", { key: stationId, value: stationId }, stationLabel(model.indices.stations[stationId]))),
          ),
        ),
      ),
    ),
    h(
      "div",
      { className: "inspection-workspace-body", style: inspectionWorkspaceBodyStyle() },
      h(ParameterFeatureBrowser, {
        groups: browserGroups,
        selectedParameterId: selectedParameterId,
        onSelect: handleParameterSelection,
      }),
      activeTab === "s_q_blade"
        ? h(
            "div",
            { className: "inspection-drawing-grid inspection-s-q-blade-grid" },
            h(EngineeringDrawingView, {
              contextPrimitives: drawingContext,
              ...renderProps.drawing,
            }),
            h(BladeFeatureScene, {
              surfaceGraph: model.inspectionSurfaceGraph,
              bladeSurfaceIds,
              ...renderProps.blade,
              manifest,
            }),
          )
        : h(
            "div",
            { className: "inspection-drawing-grid" },
            h(EngineeringDrawingView, {
              contextPrimitives: drawingContext,
              ...renderProps.drawing,
            }),
          ),
    ),
  );
}

function engineeringContextPrimitives(groups, viewId, selectedParameter) {
  const features = engineeringContextFeatures(groups, viewId)
    .map((feature) => ({ ...feature, className: "engineering-context" }));
  const unframed = features
    .map((feature) => projectEngineeringFeature(feature, viewId))
    .filter(Boolean);
  const selected = (selectedParameter?.features || [])
    .filter((feature) => feature?.rendering_role !== "drawing_context")
    .map((feature) => projectEngineeringFeature(feature, viewId))
    .filter(Boolean);
  const dimensionEvidence = projectEngineeringDimensionEvidence(selectedParameter?.dimension, viewId);
  const bounds = expandDrawingBounds(engineeringDrawingBounds(unframed, [...selected, ...dimensionEvidence]));
  if (!bounds) {
    return [];
  }
  const frame = { bounds, viewport: DRAWING_VIEWPORT };
  return features
    .map((feature) => projectEngineeringFeature(feature, viewId, frame))
    .filter(Boolean);
}

function expandDrawingBounds(bounds) {
  if (!bounds) return null;
  const marginX = Math.max(bounds.width * 0.12, 1);
  const marginY = Math.max(bounds.height * 0.12, 1);
  return {
    ...bounds,
    minX: bounds.minX - marginX,
    maxX: bounds.maxX + marginX,
    minY: bounds.minY - marginY,
    maxY: bounds.maxY + marginY,
  };
}

function bladeLabel(blade) {
  const bladeClass = String(blade.blade_class || "blade").replaceAll("_", " ");
  return `${bladeClass} ${Number(blade.blade_index) + 1}`;
}

function stationLabel(station) {
  const hValue = Number(station?.h);
  return Number.isFinite(hValue) ? `h ${hValue.toFixed(3)}` : station?.span_station_id || "station";
}
