import React, { useLayoutEffect, useMemo, useState } from "react";

import {
  defaultInspectionSelection,
  engineeringParameterById,
  engineeringParameterGroups,
  equivalentParameterId,
  resolveParameterInspection,
} from "../parameterInspectionModel.js?v=1.1.5";
import {
  engineeringDrawingBounds,
  projectEngineeringFeature,
} from "../engineeringDrawingModel.js?v=1.1.5";
import { BladeFeatureScene } from "./BladeFeatureScene.js?v=1.1.5";
import { EngineeringDrawingView } from "./EngineeringDrawingView.js?v=1.1.5";
import { ParameterFeatureBrowser } from "./ParameterFeatureBrowser.js?v=1.1.5";

const h = React.createElement;
const EMPTY_INSPECTION_ERROR = "parameter_inspection_not_generated";
const DRAWING_VIEWPORT = { x: 0, y: 0, width: 1000, height: 700 };
const NAVIGATION_SCOPE_KEYS = new Set([
  "blade_instance_id",
  "section_loop_id",
  "source_attachment_surface_id",
  "source_control_point_id",
  "source_station_index",
  "span_station_id",
]);

export const WORKSPACE_TABS = Object.freeze([
  { id: "top", label: "Top" },
  { id: "meridional", label: "Meridional" },
  { id: "s_q_blade", label: "S-Q + Blade" },
]);

export function ParameterInspectionWorkspace({ manifest = null }) {
  const [activeTab, setActiveTab] = useState("top");
  const model = useMemo(() => resolveParameterInspection(manifest), [manifest]);
  const [navigation, setNavigation] = useState(() => defaultInspectionSelection(model));
  const [selectedParameterId, setSelectedParameterId] = useState(null);
  const generationId = model.contract?.generation_id;

  useLayoutEffect(() => {
    setActiveTab("top");
    setNavigation(defaultInspectionSelection(model));
    setSelectedParameterId(null);
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
  const selectedParameter = engineeringParameterById(model, selectedParameterId);
  const drawingViewId = activeTab === "s_q_blade" ? "s_q" : activeTab;
  const drawingContext = useMemo(
    () => engineeringContextPrimitives(parameterGroups, drawingViewId),
    [drawingViewId, parameterGroups],
  );
  const drawingSelectedParameter = selectedParameter?.applicableViews.includes(drawingViewId)
    ? selectedParameter
    : null;
  const bladeSelectedParameter = activeTab === "s_q_blade"
    && selectedParameter?.applicableViews.includes("blade_3d")
    ? selectedParameter
    : null;
  const selectedBlade = model.indices?.blades?.[navigation.bladeId];
  const bladeSurfaceIds = selectedBlade?.surface_ids || [];

  function handleBladeSelection(bladeId) {
    const blade = model.indices.blades[bladeId];
    if (!blade) {
      return;
    }
    const nextContext = {
      bladeId,
      spanStationId: blade.span_station_ids?.[0] || null,
    };
    setNavigation((current) => ({ ...current, ...nextContext }));
    setSelectedParameterId((current) =>
      preserveEquivalentParameterId(model, current, nextContext, activeTab));
  }

  function handleStationSelection(spanStationId) {
    const station = model.indices.stations[spanStationId];
    if (!station) {
      return;
    }
    const nextContext = {
      bladeId: station.blade_instance_id,
      spanStationId,
    };
    setNavigation((current) => ({ ...current, ...nextContext }));
    setSelectedParameterId((current) =>
      preserveEquivalentParameterId(model, current, nextContext, activeTab));
  }

  function handleTabSelection(viewId) {
    setActiveTab(viewId);
    setSelectedParameterId((current) => {
      const parameter = engineeringParameterById(model, current);
      return parameterAppliesToWorkspaceView(parameter, viewId) ? current : null;
    });
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
      { className: "inspection-workspace-body" },
      h(ParameterFeatureBrowser, {
        groups: browserGroups,
        selectedParameterId: selectedParameterId,
        onSelect: setSelectedParameterId,
      }),
      activeTab === "s_q_blade"
        ? h(
            "div",
            { className: "inspection-drawing-grid inspection-s-q-blade-grid" },
            h(EngineeringDrawingView, {
              viewId: "s_q",
              contextPrimitives: drawingContext,
              selectedParameter: drawingSelectedParameter,
              selectedParameterId: selectedParameterId,
            }),
            h(BladeFeatureScene, {
              surfaceGraph: model.inspectionSurfaceGraph,
              bladeSurfaceIds,
              selectedParameter: bladeSelectedParameter,
              selectedParameterId: selectedParameterId,
              manifest,
            }),
          )
        : h(
            "div",
            { className: "inspection-drawing-grid" },
            h(EngineeringDrawingView, {
              viewId: drawingViewId,
              contextPrimitives: drawingContext,
              selectedParameter: drawingSelectedParameter,
              selectedParameterId: selectedParameterId,
            }),
          ),
    ),
  );
}

export function parameterAppliesToWorkspaceView(parameter, viewId) {
  const applicableViews = Array.isArray(parameter?.applicableViews) ? parameter.applicableViews : [];
  return viewId === "s_q_blade"
    ? applicableViews.includes("s_q") || applicableViews.includes("blade_3d")
    : applicableViews.includes(viewId);
}

export function preserveEquivalentParameterId(
  model,
  currentId,
  nextContext,
  viewId,
  resolveEquivalent = equivalentParameterId,
) {
  if (!currentId) {
    return null;
  }
  const nextId = resolveEquivalent(model, currentId, nextContext)
    || stationEquivalentParameterId(model, currentId, nextContext);
  const nextParameter = model?.engineeringParameters?.find((parameter) => parameter.id === nextId) || null;
  return parameterAppliesToWorkspaceView(nextParameter, viewId) ? nextId : null;
}

function stationEquivalentParameterId(model, currentId, nextContext) {
  if (!nextContext?.spanStationId) {
    return null;
  }
  const parameters = Array.isArray(model?.engineeringParameters) ? model.engineeringParameters : [];
  const current = parameters.find((parameter) => parameter.id === currentId);
  if (!current) {
    return null;
  }
  const currentScope = semanticScope(current.selectionScope);
  const match = parameters.find((parameter) =>
    parameter.groupId === current.groupId
    && parameter.label === current.label
    && scopeMatchesNavigation(parameter.selectionScope, nextContext)
    && engineeringValuesEqual(semanticScope(parameter.selectionScope), currentScope));
  return match?.id || null;
}

function scopeMatchesNavigation(scope, context) {
  return (!context.bladeId || scope?.blade_instance_id === context.bladeId)
    && (!context.spanStationId || scope?.span_station_id === context.spanStationId);
}

function semanticScope(scope) {
  return Object.fromEntries(
    Object.entries(scope || {}).filter(([key]) => !NAVIGATION_SCOPE_KEYS.has(key)),
  );
}

function engineeringValuesEqual(left, right) {
  if (left === right) {
    return true;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left)
      && Array.isArray(right)
      && left.length === right.length
      && left.every((value, index) => engineeringValuesEqual(value, right[index]));
  }
  if (!left || !right || typeof left !== "object" || typeof right !== "object") {
    return false;
  }
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  return [...keys].every((key) => engineeringValuesEqual(left[key], right[key]));
}

function engineeringContextPrimitives(groups, viewId) {
  const features = uniqueFeatures(
    groups.flatMap((group) => group.parameters)
      .filter((parameter) => parameter.applicableViews.includes(viewId))
      .flatMap((parameter) => parameter.features),
  );
  const unframed = features
    .map((feature) => projectEngineeringFeature(feature, viewId))
    .filter(Boolean);
  const bounds = engineeringDrawingBounds(unframed, []);
  if (!bounds) {
    return [];
  }
  const frame = { bounds, viewport: DRAWING_VIEWPORT };
  return features
    .map((feature) => projectEngineeringFeature(feature, viewId, frame))
    .filter(Boolean);
}

function uniqueFeatures(features) {
  const byId = new Map();
  for (const feature of features) {
    if (feature?.id && !byId.has(feature.id)) {
      byId.set(feature.id, feature);
    }
  }
  return [...byId.values()];
}

function bladeLabel(blade) {
  const bladeClass = String(blade.blade_class || "blade").replaceAll("_", " ");
  return `${bladeClass} ${Number(blade.blade_index) + 1}`;
}

function stationLabel(station) {
  const hValue = Number(station?.h);
  return Number.isFinite(hValue) ? `h ${hValue.toFixed(3)}` : station?.span_station_id || "station";
}
