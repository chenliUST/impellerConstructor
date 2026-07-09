import React, { useMemo, useRef, useState } from "react";

import {
  profileEditorBounds,
  profileOverridesPayload,
  profilesFromManifest,
  rzToScreen,
  screenToRz,
  updateControlPoint,
  validateProfileOverrides,
} from "../profileEditorModel.js?v=1.1.5";

const h = React.createElement;
const viewport = { width: 520, height: 320 };

export function ProfileCurveEditor({ manifest, profileOverrides, onProfileOverridesChange, onResetProfileOverrides }) {
  const profiles = profileOverrides || profilesFromManifest(manifest);
  const validation = validateProfileOverrides(profiles);
  const bounds = useMemo(() => profileEditorBounds(profiles), [profiles]);
  const svgRef = useRef(null);
  const [dragHandle, setDragHandle] = useState(null);
  const [selectedHandle, setSelectedHandle] = useState({ profileId: "hub_profile", pointIndex: 0 });

  function moveHandle(event) {
    if (!dragHandle || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const local = [
      ((event.clientX - rect.left) / rect.width) * viewport.width,
      ((event.clientY - rect.top) / rect.height) * viewport.height,
    ];
    const next = updateControlPoint(
      profiles,
      dragHandle.profileId,
      dragHandle.pointIndex,
      screenToRz(local, bounds, viewport),
    );
    onProfileOverridesChange(profileOverridesPayload(next));
  }

  function setPointCoordinate(profileId, pointIndex, coordinateIndex, value) {
    if (value === "") return;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    const point = profiles[profileId].control_points[pointIndex];
    const nextPoint = [...point];
    nextPoint[coordinateIndex] = numeric;
    const next = updateControlPoint(profiles, profileId, pointIndex, nextPoint);
    setSelectedHandle({ profileId, pointIndex });
    onProfileOverridesChange(profileOverridesPayload(next));
  }

  function selectHandle(handle) {
    setSelectedHandle(handle);
    setDragHandle(handle);
  }

  return h(
    "section",
    { className: "panel-section profile-curve-editor" },
    h("div", { className: "section-title" }, "Hub / tip profiles"),
    h(
      "svg",
      {
        ref: svgRef,
        viewBox: `0 0 ${viewport.width} ${viewport.height}`,
        className: validation.status === "PASS" ? "curve-editor-svg" : "curve-editor-svg invalid",
        onPointerMove: moveHandle,
        onPointerUp: () => setDragHandle(null),
        onPointerLeave: () => setDragHandle(null),
      },
      h(ProfilePolyline, { profile: profiles.hub_profile, bounds, color: "#2f7d67" }),
      h(ProfilePolyline, { profile: profiles.tip_or_shroud_profile, bounds, color: "#2f6f9e" }),
      h(ProfileHandles, {
        profileId: "hub_profile",
        profile: profiles.hub_profile,
        bounds,
        color: "#2f7d67",
        prefix: "H",
        selectedHandle,
        onPointerDown: selectHandle,
      }),
      h(ProfileHandles, {
        profileId: "tip_or_shroud_profile",
        profile: profiles.tip_or_shroud_profile,
        bounds,
        color: "#2f6f9e",
        prefix: "T",
        selectedHandle,
        onPointerDown: selectHandle,
      }),
    ),
    h(ProfileControlTable, {
      profiles,
      selectedHandle,
      onSelect: setSelectedHandle,
      onCoordinateChange: setPointCoordinate,
    }),
    h(
      "p",
      { className: validation.status === "PASS" ? "small-note" : "small-note error" },
      validation.reason || "Drag R-Z NURBS control points",
    ),
    h("button", { className: "secondary-action", type: "button", onClick: onResetProfileOverrides }, "Reset profiles"),
  );
}

function ProfilePolyline({ profile, bounds, color }) {
  if (!profile) return null;
  const points = profile.control_points.map((point) => rzToScreen(point, bounds, viewport).join(",")).join(" ");
  return h("polyline", { points, fill: "none", stroke: color, strokeWidth: 2 });
}

function ProfileHandles({ profileId, profile, bounds, color, prefix, selectedHandle, onPointerDown }) {
  if (!profile) return null;
  return profile.control_points.map((point, index) => {
    const [x, y] = rzToScreen(point, bounds, viewport);
    const selected = selectedHandle?.profileId === profileId && selectedHandle?.pointIndex === index;
    return h(
      "g",
      {
        key: `${profileId}-${index}`,
        className: selected ? "curve-handle selected" : "curve-handle",
        onPointerDown: (event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          event.preventDefault();
          onPointerDown({ profileId, pointIndex: index });
        },
      },
      h("circle", { cx: x, cy: y, r: selected ? 7 : 5, fill: color }),
      h("text", { x: x + 7, y: y - 7, className: "svg-label" }, `${prefix}${index}`),
      h("title", null, "Drag to edit the NURBS control point in R-Z coordinates."),
      h("rect", { x: x - 12, y: y - 12, width: 24, height: 24, fill: "transparent" }),
    );
  });
}

function ProfileControlTable({ profiles, selectedHandle, onSelect, onCoordinateChange }) {
  const rows = [
    ["hub_profile", "Hub", profiles.hub_profile],
    ["tip_or_shroud_profile", "Tip/support", profiles.tip_or_shroud_profile],
  ];
  return h(
    "div",
    { className: "profile-control-table" },
    rows.map(([profileId, label, profile]) =>
      h(
        "div",
        { className: "profile-control-block", key: profileId },
        h("div", { className: "curve-control-heading" }, label),
        profile.control_points.map((point, index) => {
          const selected = selectedHandle?.profileId === profileId && selectedHandle?.pointIndex === index;
          return h(
            "div",
            {
              key: `${profileId}-${index}`,
              className: selected ? "coordinate-row selected" : "coordinate-row",
              onPointerDown: () => onSelect({ profileId, pointIndex: index }),
            },
            h("span", { className: "coordinate-index" }, `P${index}`),
            h(CoordinateInput, {
              label: "R",
              value: point[0],
              onChange: (value) => onCoordinateChange(profileId, index, 0, value),
            }),
            h(CoordinateInput, {
              label: "Z",
              value: point[1],
              onChange: (value) => onCoordinateChange(profileId, index, 1, value),
            }),
          );
        }),
      ),
    ),
  );
}

function CoordinateInput({ label, value, onChange }) {
  return h(
    "label",
    { className: "coordinate-field" },
    h("span", null, `${label} mm`),
    h("input", {
      type: "number",
      step: "0.001",
      value,
      onChange: (event) => onChange(event.target.value),
    }),
  );
}
