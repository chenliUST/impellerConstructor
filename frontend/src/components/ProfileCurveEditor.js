import React, { useMemo, useRef, useState } from "react";

import {
  profileEditorBounds,
  profileOverridesPayload,
  profilesFromManifest,
  rzToScreen,
  screenToRz,
  updateControlPoint,
  validateProfileOverrides,
} from "../profileEditorModel.js";

const h = React.createElement;
const viewport = { width: 300, height: 180 };

export function ProfileCurveEditor({ manifest, profileOverrides, onProfileOverridesChange, onResetProfileOverrides }) {
  const profiles = profileOverrides || profilesFromManifest(manifest);
  const validation = validateProfileOverrides(profiles);
  const bounds = useMemo(() => profileEditorBounds(profiles), [profiles]);
  const svgRef = useRef(null);
  const [activeHandle, setActiveHandle] = useState(null);

  function moveHandle(event) {
    if (!activeHandle || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const local = [
      ((event.clientX - rect.left) / rect.width) * viewport.width,
      ((event.clientY - rect.top) / rect.height) * viewport.height,
    ];
    const next = updateControlPoint(
      profiles,
      activeHandle.profileId,
      activeHandle.pointIndex,
      screenToRz(local, bounds, viewport),
    );
    onProfileOverridesChange(profileOverridesPayload(next));
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
        onPointerUp: () => setActiveHandle(null),
        onPointerLeave: () => setActiveHandle(null),
      },
      h(ProfilePolyline, { profile: profiles.hub_profile, bounds, color: "#2f7d67" }),
      h(ProfilePolyline, { profile: profiles.tip_or_shroud_profile, bounds, color: "#2f6f9e" }),
      h(ProfileHandles, {
        profileId: "hub_profile",
        profile: profiles.hub_profile,
        bounds,
        color: "#2f7d67",
        prefix: "H",
        onPointerDown: setActiveHandle,
      }),
      h(ProfileHandles, {
        profileId: "tip_or_shroud_profile",
        profile: profiles.tip_or_shroud_profile,
        bounds,
        color: "#2f6f9e",
        prefix: "T",
        onPointerDown: setActiveHandle,
      }),
    ),
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

function ProfileHandles({ profileId, profile, bounds, color, prefix, onPointerDown }) {
  if (!profile) return null;
  return profile.control_points.map((point, index) => {
    const [x, y] = rzToScreen(point, bounds, viewport);
    return h(
      "g",
      {
        key: `${profileId}-${index}`,
        className: "curve-handle",
        onPointerDown: (event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          onPointerDown({ profileId, pointIndex: index });
        },
      },
      h("circle", { cx: x, cy: y, r: 5, fill: color }),
      h("text", { x: x + 7, y: y - 7, className: "svg-label" }, `${prefix}${index}`),
      h("title", null, "Drag to edit the NURBS control point in R-Z coordinates."),
      h("rect", { x: x - 8, y: y - 8, width: 16, height: 16, fill: "transparent" }),
    );
  });
}
