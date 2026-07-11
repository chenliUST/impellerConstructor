import {
  defaultInspectionSelection,
  engineeringParameterById,
  equivalentParameterId,
} from "./parameterInspectionModel.js?v=1.1.5";

const INSTANCE_SCOPE_KEYS = new Set([
  "blade_instance_id",
  "section_loop_id",
  "section_segment_id",
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

export function initialWorkspaceState(model) {
  const selection = defaultInspectionSelection(model);
  return {
    activeTab: "top",
    navigation: {
      bladeId: selection.bladeId,
      spanStationId: selection.spanStationId,
    },
    selectedParameterId: null,
  };
}

export function transitionWorkspaceState(model, state, event) {
  switch (event?.type) {
    case "parameter":
      return transitionParameter(model, state, event.parameterId);
    case "tab":
      return transitionTab(model, state, event.viewId);
    case "blade":
      return transitionBlade(model, state, event.bladeId);
    case "station":
      return transitionStation(model, state, event.spanStationId);
    default:
      return state;
  }
}

export function workspaceRenderProps(model, state) {
  const selectedParameter = engineeringParameterById(model, state.selectedParameterId);
  const drawingViewId = state.activeTab === "s_q_blade" ? "s_q" : state.activeTab;
  const drawingSelectedParameter = selectedParameter?.applicableViews.includes(drawingViewId)
    ? selectedParameter
    : null;
  const bladeSelectedParameter = state.activeTab === "s_q_blade"
    && selectedParameter?.applicableViews.includes("blade_3d")
    ? selectedParameter
    : null;

  return {
    drawing: {
      viewId: drawingViewId,
      selectedParameter: drawingSelectedParameter,
      selectedParameterId: drawingSelectedParameter?.id || null,
    },
    blade: {
      selectedParameter: bladeSelectedParameter,
      selectedParameterId: bladeSelectedParameter?.id || null,
    },
  };
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
    || contextualEquivalentParameterId(model, currentId, nextContext);
  const nextParameter = engineeringParameterById(model, nextId);
  return parameterAppliesToWorkspaceView(nextParameter, viewId) ? nextId : null;
}

function transitionParameter(model, state, parameterId) {
  if (state.selectedParameterId === parameterId) {
    return { ...state, selectedParameterId: null };
  }
  const parameter = engineeringParameterById(model, parameterId);
  return {
    ...state,
    selectedParameterId: parameterAppliesToWorkspaceView(parameter, state.activeTab) ? parameterId : null,
  };
}

function transitionTab(model, state, viewId) {
  const parameter = engineeringParameterById(model, state.selectedParameterId);
  return {
    ...state,
    activeTab: viewId,
    selectedParameterId: parameterAppliesToWorkspaceView(parameter, viewId)
      ? state.selectedParameterId
      : null,
  };
}

function transitionBlade(model, state, bladeId) {
  const blade = model.indices?.blades?.[bladeId];
  if (!blade) {
    return state;
  }
  const currentStations = model.indices?.blades?.[state.navigation.bladeId]?.span_station_ids || [];
  const currentStationIndex = Math.max(0, currentStations.indexOf(state.navigation.spanStationId));
  const spanStationId = blade.span_station_ids?.[currentStationIndex]
    || blade.span_station_ids?.[0]
    || null;
  return transitionNavigation(model, state, { bladeId, spanStationId });
}

function transitionStation(model, state, spanStationId) {
  const station = model.indices?.stations?.[spanStationId];
  return station
    ? transitionNavigation(model, state, {
        bladeId: station.blade_instance_id,
        spanStationId,
      })
    : state;
}

function transitionNavigation(model, state, navigation) {
  return {
    ...state,
    navigation,
    selectedParameterId: preserveEquivalentParameterId(
      model,
      state.selectedParameterId,
      navigation,
      state.activeTab,
    ),
  };
}

function contextualEquivalentParameterId(model, currentId, nextContext) {
  if (!nextContext?.spanStationId) {
    return null;
  }
  const parameters = Array.isArray(model?.engineeringParameters) ? model.engineeringParameters : [];
  const current = engineeringParameterById(model, currentId);
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
    Object.entries(scope || {}).filter(([key]) => !INSTANCE_SCOPE_KEYS.has(key)),
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
