import React, { useEffect, useLayoutEffect, useMemo, useState } from "react";

import {
  ANNOTATION_LEVELS,
  INSPECTION_TABS,
  annotationsForView,
  defaultInspectionSelection,
  mergeInspectionSelection,
  resolveParameterInspection,
  sectionLoopForSelection,
} from "../parameterInspectionModel.js?v=1.1.5";
import { InspectionScene } from "./InspectionScene.js?v=1.1.5";
import { ParameterAnnotationOverlay } from "./ParameterAnnotationOverlay.js?v=1.1.5";
import { SectionLoopInspectionView } from "./SectionLoopInspectionView.js?v=1.1.5";

const h = React.createElement;
const GEOMETRIC_VIEW_IDS = ["3d", "top", "meridional"];
const EMPTY_INSPECTION_ERROR = "parameter_inspection_not_generated";
const INSPECTION_TAB_TEST_IDS = {
  "3d": "inspection-tab-3d",
  top: "inspection-tab-top",
  meridional: "inspection-tab-meridional",
  s_q: "inspection-tab-s_q",
  quad: "inspection-tab-quad",
};

export function ParameterInspectionWorkspace({ manifest = null, visibleLayers, viewMode }) {
  const [activeTab, setActiveTab] = useState("3d");
  const [annotationLevel, setAnnotationLevel] = useState("key");
  const [projectionError, setProjectionError] = useState(null);
  const [narrowQuad, setNarrowQuad] = useState(false);
  const model = useMemo(() => resolveParameterInspection(manifest), [manifest]);
  const [selection, setSelection] = useState(() => defaultInspectionSelection(model));
  const generationId = model.contract?.generation_id;

  useLayoutEffect(() => {
    setProjectionError(null);
    setSelection(defaultInspectionSelection(model));
    setActiveTab("3d");
  }, [generationId]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 820px)");
    const updateNarrowQuad = () => setNarrowQuad(mediaQuery.matches);
    updateNarrowQuad();
    mediaQuery.addEventListener("change", updateNarrowQuad);
    return () => mediaQuery.removeEventListener("change", updateNarrowQuad);
  }, []);

  const annotationsByView = useMemo(
    () =>
      Object.fromEntries(
        [...GEOMETRIC_VIEW_IDS, "s_q"].map((viewId) => [
          viewId,
          annotationsForView(model, viewId, annotationLevel, selection),
        ]),
      ),
    [annotationLevel, model, selection],
  );
  const selectedLoop = sectionLoopForSelection(model, selection);
  const quadLayout = narrowQuad ? "quad_stacked" : "quad";

  function handleSurfaceSelection(surfaceId) {
    setProjectionError(null);
    const reference = model.indices.surfaces[surfaceId];
    setSelection((current) =>
      mergeInspectionSelection(current, {
        surfaceId,
        bladeId: reference?.blade_instance_id || current.bladeId,
      }),
    );
  }

  function handleSectionSelection(nextSelection) {
    setProjectionError(null);
    setSelection((current) => mergeInspectionSelection(current, nextSelection));
  }

  function handleTabSelection(viewId) {
    setProjectionError(null);
    setActiveTab(viewId);
  }

  if (model.status === "empty" && model.errorCode === EMPTY_INSPECTION_ERROR) {
    return h(
      "section",
      { className: "parameter-inspection-workspace inspection-workspace-status", "data-testid": "inspection-workspace", "data-active-tab": activeTab },
      h("p", null, "Generate a model to inspect resolved geometry."),
    );
  }

  if (model.status === "error") {
    return h(
      "section",
      { className: "parameter-inspection-workspace inspection-workspace-status", "data-testid": "inspection-workspace", "data-active-tab": activeTab },
      h("p", { className: "inspection-error-banner" }, model.errorCode),
    );
  }

  return h(
    "section",
    { className: "parameter-inspection-workspace", "data-testid": "inspection-workspace", "data-active-tab": activeTab },
    h(
      "div",
      { className: "inspection-workspace-toolbar" },
      h(
        "div",
        { className: "inspection-tab-list", role: "tablist", "aria-label": "Inspection views" },
        INSPECTION_TABS.map((tab) =>
          h(
            "button",
            {
              key: tab.id,
              className: activeTab === tab.id ? "selected" : "",
              type: "button",
              role: "tab",
              "aria-selected": activeTab === tab.id,
              "data-testid": INSPECTION_TAB_TEST_IDS[tab.id],
              onClick: () => handleTabSelection(tab.id),
            },
            tab.label,
          ),
        ),
      ),
      h(
        "label",
        { className: "inspection-annotation-control" },
        h("span", null, "Annotations"),
        h(
          "select",
          {
            value: annotationLevel,
            "data-testid": "inspection-annotation-level",
            onInput: (event) => setAnnotationLevel(event.target.value),
          },
          ANNOTATION_LEVELS.map((level) => h("option", { key: level, value: level }, level)),
        ),
      ),
    ),
    projectionError ? h("div", { className: "inspection-error-banner", role: "status" }, projectionError) : null,
    activeTab === "quad"
      ? renderQuadView({
          annotationsByView,
          annotationLevel,
          handleTabSelection,
          manifest,
          model,
          onProjectionError: setProjectionError,
          onSelectSurface: handleSurfaceSelection,
          onSelectSection: handleSectionSelection,
          selectedLoop,
          selection,
          quadLayout,
          viewMode,
          visibleLayers,
        })
      : activeTab === "s_q"
        ? renderSectionLoopPane({
            annotations: annotationsByView.s_q,
            annotationLevel,
            loop: selectedLoop,
            onSelect: handleSectionSelection,
            selection,
          })
        : h(
            "div",
            { className: "inspection-workspace-content inspection-workspace-full" },
            h(InspectionScene, {
              manifest,
              surfaceGraph: model.surfaceGraph,
              layout: activeTab,
              selectedSurfaceId: selection.surfaceId,
              onSelectSurface: handleSurfaceSelection,
              onProjectionError: setProjectionError,
              visibleLayers,
              viewMode,
              annotationsByView,
              selectionContextKey: JSON.stringify(selection),
            }),
          ),
  );
}

function renderQuadView({
  annotationsByView,
  annotationLevel,
  handleTabSelection,
  manifest,
  model,
  onProjectionError,
  onSelectSurface,
  onSelectSection,
  selectedLoop,
  selection,
  quadLayout,
  viewMode,
  visibleLayers,
}) {
  return h(
    "div",
    { className: "inspection-workspace-content inspection-workspace-quad" },
    h(
      "div",
      { className: "inspection-quad-scene" },
      h(InspectionScene, {
        manifest,
        surfaceGraph: model.surfaceGraph,
        layout: quadLayout,
        selectedSurfaceId: selection.surfaceId,
        onSelectSurface,
        onProjectionError,
        visibleLayers,
        viewMode,
        annotationsByView,
        selectionContextKey: JSON.stringify(selection),
      }),
    ),
    ["3d", "meridional", "s_q", "top"].map((viewId) =>
      h(
        "div",
        { key: viewId, className: `inspection-quad-pane inspection-quad-pane-${viewId}` },
        h(
          "button",
          {
            className: "inspection-maximize",
            type: "button",
            title: `Maximize ${viewLabel(viewId)}`,
            "aria-label": `Maximize ${viewLabel(viewId)}`,
            onClick: () => handleTabSelection(viewId),
          },
          "maximize",
        ),
        viewId === "s_q"
          ? renderSectionLoopPane({
            annotations: annotationsByView.s_q,
              annotationLevel,
              loop: selectedLoop,
              onSelect: onSelectSection,
              selection,
            })
          : null,
      ),
    ),
  );
}

function renderSectionLoopPane({ annotations, annotationLevel, loop, onSelect, selection }) {
  return h(
    "div",
    { className: "inspection-section-loop-pane" },
    h(SectionLoopInspectionView, {
      loop,
      selection,
      annotationLevel,
      annotations,
      onSelect,
    }),
    h(
      "svg",
      {
        className: "inspection-section-annotations",
        viewBox: "0 0 1000 700",
        preserveAspectRatio: "none",
        "aria-hidden": "true",
      },
      h(ParameterAnnotationOverlay, {
        annotations,
        projectAnchor: sectionAnnotationRailAnchor,
        viewportWidth: 1000,
        viewportHeight: 700,
      }),
    ),
  );
}

function sectionAnnotationRailAnchor(anchor) {
  return anchor?.kind === "section_segment" ? { x: 760, y: 56 } : { x: 18, y: 56 };
}

function viewLabel(viewId) {
  return INSPECTION_TABS.find((tab) => tab.id === viewId)?.label || viewId;
}
