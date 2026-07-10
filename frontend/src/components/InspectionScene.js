import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import {
  inspectionViewportRects,
  orthographicCameraFrame,
  projectionContextSignature,
  projectionFailureNotificationKey,
  resolveInspectionAnchor,
  selectedProjectionFailureKey,
  viewportAtPointer,
  visibleGeometricViews,
} from "../inspectionSceneModel.js?v=1.1.5";
import { viewerLayerVisibility } from "../meshOverlayModel.js?v=1.1.5";
import { defaultVisibleLayers } from "../workspaceModel.js?v=1.1.5";
import { createSurfaceGraphGroup, disposeObject, surfaceGraphBounds } from "./ModelViewer.js?v=1.1.5";
import { ParameterAnnotationOverlay } from "./ParameterAnnotationOverlay.js?v=1.1.5";

const h = React.createElement;
const SELECTED_EMISSIVE = "#f97316";
const EMPTY_SURFACE_GRAPH = { surfaces: [] };

// Task 6 passes JSON.stringify(selection) as the complete workspace selection revision.
export function InspectionScene({
  manifest = null,
  surfaceGraph = EMPTY_SURFACE_GRAPH,
  layout = "3d",
  selectedSurfaceIds = [],
  onSelectSurface = null,
  onProjectionError = null,
  visibleLayers = defaultVisibleLayers(),
  viewMode = "combined",
  annotationsByView = {},
  selectionContextKey = "",
}) {
  const containerRef = useRef(null);
  const groupRef = useRef(null);
  const camerasRef = useRef(null);
  const controlsRef = useRef(null);
  const boundsRef = useRef(null);
  const rectsRef = useRef({});
  const sizeRef = useRef({ width: 0, height: 0 });
  const resizeRef = useRef(null);
  const installedSceneRef = useRef(null);
  const rendererConstructionCountRef = useRef(0);
  const constructedContextSetRef = useRef(new Set());
  const layoutRef = useRef(layout);
  const onSelectSurfaceRef = useRef(onSelectSurface);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const [surfaceCount, setSurfaceCount] = useState(0);
  const [projectionEpoch, setProjectionEpoch] = useState(0);
  const [projectionVersion, setProjectionVersion] = useState(0);
  const [rendererStats, setRendererStats] = useState({ rendererCount: 0, contextCount: 0 });

  layoutRef.current = layout;
  onSelectSurfaceRef.current = onSelectSurface;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#eef2f0");
    const cameras = {
      "3d": new THREE.PerspectiveCamera(45, 1, 0.1, 100000),
      top: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000),
      meridional: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000),
    };
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    rendererConstructionCountRef.current += 1;
    constructedContextSetRef.current.add(renderer.getContext());
    setRendererStats({
      rendererCount: rendererConstructionCountRef.current,
      contextCount: constructedContextSetRef.current.size,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor("#eef2f0");
    renderer.setScissorTest(true);
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    container.appendChild(renderer.domElement);

    const controls = Object.fromEntries(
      Object.entries(cameras).map(([viewId, camera]) => {
        const control = new OrbitControls(camera, renderer.domElement);
        control.enableDamping = true;
        control.dampingFactor = 0.08;
        control.enableRotate = viewId === "3d";
        control.enablePan = true;
        control.enableZoom = true;
        control.enabled = false;
        return [viewId, control];
      }),
    );
    const raycaster = new THREE.Raycaster();
    const bounds = surfaceGraphBounds(surfaceGraph);
    const group = createSurfaceGraphGroup(
      surfaceGraph,
      bounds.center,
      "cad_review_360",
      new Set(),
      "off",
      manifest,
    );
    const supportProfileGroup = renderMeridionalSupportProfiles(manifest, bounds.center);
    group.traverse((child) => {
      if (!child.isMesh) {
        return;
      }
      forEachMaterial(child.material, (material) => {
        material.userData.baselineEmissive = material.emissive.clone();
        material.userData.baselineEmissiveIntensity = material.emissiveIntensity;
        material.userData.baselineOpacity = material.opacity;
      });
    });
    scene.add(group);
    scene.add(supportProfileGroup);
    scene.add(new THREE.HemisphereLight("#ffffff", "#8a928e", 2.4));
    const keyLight = new THREE.DirectionalLight("#ffffff", 2.2);
    keyLight.position.set(1200, -1800, 2200);
    scene.add(keyLight);

    groupRef.current = group;
    camerasRef.current = cameras;
    controlsRef.current = controls;
    boundsRef.current = bounds;
    let renderedSurfaceCount = 0;
    group.traverse((child) => {
      if (child.isMesh && child.userData.surfaceId) {
        renderedSurfaceCount += 1;
      }
    });
    setSurfaceCount(renderedSurfaceCount);

    const updateCameraFrames = (width, height) => {
      const rects = inspectionViewportRects(width, height, layoutRef.current);
      rectsRef.current = rects;
      const perspectiveRect = rects["3d"];
      if (perspectiveRect?.height) {
        const camera = cameras["3d"];
        const radius = Math.max(Number(bounds.radius) || 1, 1);
        const distance = radius * 2.4;
        camera.aspect = perspectiveRect.width / perspectiveRect.height;
        camera.near = Math.max(radius / 100, 0.1);
        camera.far = Math.max(distance * 20, 100000);
        camera.position.set(distance * 0.8, -distance, distance * 0.55);
        camera.updateProjectionMatrix();
        camera.updateMatrixWorld();
      }
      for (const viewId of ["top", "meridional"]) {
        const rect = rects[viewId];
        if (!rect?.height) {
          continue;
        }
        const frame = orthographicCameraFrame(bounds, viewId, rect.width / rect.height);
        const camera = cameras[viewId];
        camera.position.set(...frame.position);
        camera.up.set(...frame.up);
        camera.left = -frame.halfHeight * frame.aspect;
        camera.right = frame.halfHeight * frame.aspect;
        camera.top = frame.halfHeight;
        camera.bottom = -frame.halfHeight;
        camera.lookAt(...frame.target);
        camera.updateProjectionMatrix();
        camera.updateMatrixWorld();
      }
      Object.values(controls).forEach((control) => {
        control.target.set(0, 0, 0);
        control.update();
      });
      Object.values(cameras).forEach((camera) => camera.updateMatrixWorld());
    };

    const resize = () => {
      const width = Math.max(1, Math.floor(container.clientWidth));
      const height = Math.max(1, Math.floor(container.clientHeight));
      sizeRef.current = { width, height };
      renderer.setSize(width, height, false);
      updateCameraFrames(width, height);
      setViewportSize((current) =>
        current.width === width && current.height === height ? current : { width, height },
      );
    };
    resizeRef.current = resize;
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    installedSceneRef.current = { manifest, surfaceGraph };
    setProjectionEpoch((epoch) => epoch + 1);

    const setActiveControl = (activeViewId) => {
      Object.entries(controls).forEach(([viewId, control]) => {
        control.enabled = viewId === activeViewId;
      });
    };
    const pointerHit = (event) =>
      viewportAtPointer(
        event.clientX,
        event.clientY,
        renderer.domElement.getBoundingClientRect(),
        rectsRef.current,
        visibleGeometricViews(layoutRef.current),
      );
    const handlePointerMove = (event) => {
      setActiveControl(pointerHit(event)?.viewId || null);
    };
    const handlePointerLeave = () => setActiveControl(null);
    const handlePointerDown = (event) => {
      const hit = pointerHit(event);
      setActiveControl(hit?.viewId || null);
      if (!hit) {
        return;
      }
      const pointer = new THREE.Vector2(hit.pointer.x, hit.pointer.y);
      raycaster.setFromCamera(pointer, cameras[hit.viewId]);
      const intersection = raycaster
        .intersectObject(group, true)
        .find(
          (candidate) => candidate.object.isMesh && candidate.object.visible && candidate.object.userData.surfaceId,
        );
      const surfaceId = intersection?.object.userData.surfaceId;
      if (surfaceId) {
        onSelectSurfaceRef.current?.(surfaceId);
      }
    };
    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerleave", handlePointerLeave);
    renderer.domElement.addEventListener("pointerdown", handlePointerDown, true);

    const handleControlsChange = () => setProjectionVersion((version) => version + 1);
    Object.values(controls).forEach((control) => control.addEventListener("change", handleControlsChange));

    let frameId = 0;
    const animate = () => {
      frameId = window.requestAnimationFrame(animate);
      Object.values(controls).forEach((control) => control.update());
      const { width, height } = sizeRef.current;
      renderer.setScissorTest(false);
      renderer.setViewport(0, 0, width, height);
      renderer.clear();
      renderer.setScissorTest(true);
      const rects = rectsRef.current;
      for (const viewId of visibleGeometricViews(layoutRef.current)) {
        const rect = rects[viewId];
        if (!rect?.width || !rect?.height) {
          continue;
        }
        renderer.setViewport(rect.x, rect.y, rect.width, rect.height);
        renderer.setScissor(rect.x, rect.y, rect.width, rect.height);
        supportProfileGroup.visible = viewId === "meridional";
        renderer.render(scene, cameras[viewId]);
      }
      supportProfileGroup.visible = false;
    };
    animate();

    return () => {
      window.cancelAnimationFrame(frameId);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerleave", handlePointerLeave);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown, true);
      Object.values(controls).forEach((control) => control.removeEventListener("change", handleControlsChange));
      Object.values(controls).forEach((control) => control.dispose());
      scene.remove(group);
      scene.remove(supportProfileGroup);
      disposeObject(group);
      disposeObject(supportProfileGroup);
      renderer.dispose();
      renderer.domElement.remove();
      groupRef.current = null;
      camerasRef.current = null;
      controlsRef.current = null;
      boundsRef.current = null;
      resizeRef.current = null;
      installedSceneRef.current = null;
    };
  }, [manifest, surfaceGraph]);

  useEffect(() => {
    resizeRef.current?.();
  }, [layout]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) {
      return;
    }
    const selectedSurfaceIdSet = new Set(selectedSurfaceIds);
    group.traverse((child) => {
      if (!child.isMesh) {
        return;
      }
      const selected = selectedSurfaceIdSet.has(child.userData.surfaceId);
      forEachMaterial(child.material, (material) => {
        material.emissive.set(selected ? SELECTED_EMISSIVE : material.userData.baselineEmissive);
        material.emissiveIntensity = selected
          ? Math.max(material.userData.baselineEmissiveIntensity, 0.45)
          : material.userData.baselineEmissiveIntensity;
        material.opacity = selected ? 1 : material.userData.baselineOpacity;
      });
    });
  }, [manifest, selectedSurfaceIds, surfaceGraph]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) {
      return;
    }
    const { showShadedSurfaces, showSurfaceUvWire, showMeshEdges } = viewerLayerVisibility({
      simulationViewMode: "cad_review_360",
      viewMode,
      meshOverlayMode: "off",
      visibleLayers,
    });
    group.visible = showShadedSurfaces || showSurfaceUvWire || showMeshEdges;
    group.traverse((child) => {
      if (child.isMesh && child.userData.layer) {
        child.visible = showShadedSurfaces && visibleLayers[child.userData.layer] !== false;
      }
      if (child.isLineSegments && child.userData.isSurfaceUvWire && child.userData.layer) {
        child.visible = showSurfaceUvWire && visibleLayers[child.userData.layer] !== false;
      }
      if (child.isLineSegments && child.userData.isMeshOverlay && child.userData.layer) {
        child.visible = showMeshEdges && visibleLayers[child.userData.layer] !== false;
      }
    });
  }, [manifest, surfaceGraph, viewMode, visibleLayers]);

  const rects = inspectionViewportRects(viewportSize.width, viewportSize.height, layout);
  const geometricViews = visibleGeometricViews(layout);
  const projectionForView = (viewId) => {
    const camera = camerasRef.current?.[viewId];
    const bounds = boundsRef.current;
    const rect = rects[viewId];
    return (anchor) => projectInspectionAnchor(anchor, manifest, surfaceGraph, camera, bounds, rect);
  };
  const projectionReady =
    viewportSize.width > 0 &&
    viewportSize.height > 0 &&
    projectionEpoch > 0 &&
    installedSceneRef.current?.manifest === manifest &&
    installedSceneRef.current?.surfaceGraph === surfaceGraph &&
    Boolean(camerasRef.current && boundsRef.current);
  const projectionFailureKey = projectionReady
    ? selectedProjectionFailureKey(annotationsByView, geometricViews, projectionForView)
    : "";
  const projectionContextKey = projectionContextSignature(
    manifest,
    annotationsByView,
    geometricViews,
    selectionContextKey,
  );
  const projectionNotificationKey = projectionReady
    ? projectionFailureNotificationKey(
        projectionFailureKey,
        projectionContextKey,
        projectionEpoch,
      )
    : "";

  useEffect(() => {
    if (projectionNotificationKey) {
      onProjectionError?.("parameter_inspection_projection_failed");
    }
  }, [onProjectionError, projectionNotificationKey]);

  return h(
    "div",
    {
      className: "inspection-scene",
      style: { position: "relative", width: "100%", height: "100%", minWidth: 0, minHeight: 0 },
      "data-layout": layout,
      "data-projection-epoch": projectionEpoch,
      "data-projection-version": projectionVersion,
    },
    h("div", {
      className: "inspection-webgl",
      ref: containerRef,
      style: { position: "absolute", inset: 0, overflow: "hidden" },
      "data-testid": "inspection-webgl",
      "data-renderer-count": String(rendererStats.rendererCount),
      "data-context-count": String(rendererStats.contextCount),
      "data-scene-surface-count": String(surfaceCount),
    }),
    projectionReady
      ? geometricViews.map((viewId) => {
          const rect = rects[viewId];
          if (!rect?.width || !rect?.height) {
            return null;
          }
          return h(
            "svg",
            {
              className: `inspection-annotation-viewport inspection-annotation-${viewId}`,
              key: `${viewId}:${projectionEpoch}`,
              viewBox: `0 0 ${rect.width} ${rect.height}`,
              width: rect.width,
              height: rect.height,
              style: {
                position: "absolute",
                left: rect.x,
                top: viewportSize.height - rect.y - rect.height,
                width: rect.width,
                height: rect.height,
                overflow: "hidden",
                pointerEvents: "none",
              },
              "aria-hidden": "true",
            },
            h(ParameterAnnotationOverlay, {
              annotations: annotationsByView[viewId] || [],
              projectAnchor: projectionForView(viewId),
              viewportWidth: rect.width,
              viewportHeight: rect.height,
            }),
          );
        })
      : null,
  );
}

function projectInspectionAnchor(anchor, manifest, surfaceGraph, camera, bounds, rect) {
  if (!camera || !bounds || !rect?.width || !rect?.height) {
    return null;
  }
  const resolved = resolveInspectionAnchor(anchor, manifest, surfaceGraph);
  if (resolved?.viewportCorner) {
    return viewportCornerPoint(resolved.viewportCorner, rect.width, rect.height);
  }
  if (!Array.isArray(resolved)) {
    return null;
  }
  const point = new THREE.Vector3(...resolved).sub(bounds.center);
  point.project(camera);
  if (![point.x, point.y, point.z].every(Number.isFinite) || Math.max(Math.abs(point.x), Math.abs(point.y)) > 1e6) {
    return null;
  }
  return {
    x: ((point.x + 1) / 2) * rect.width,
    y: ((1 - point.y) / 2) * rect.height,
  };
}

function viewportCornerPoint(corner, width, height) {
  const horizontalInset = Math.min(12, width / 4);
  const verticalInset = Math.min(14, height / 4);
  return {
    x: corner.endsWith("left") ? horizontalInset : width - horizontalInset,
    y: corner.startsWith("bottom") ? height - verticalInset : verticalInset,
  };
}

function forEachMaterial(material, callback) {
  for (const item of Array.isArray(material) ? material : [material]) {
    if (item) {
      callback(item);
    }
  }
}

function renderMeridionalSupportProfiles(manifest, center) {
  const group = new THREE.Group();
  group.name = "meridional-support-profiles";
  group.visible = false;
  const profiles = manifest?.parameter_inspection?.support_profiles;
  if (!profiles || typeof profiles !== "object") {
    return group;
  }
  for (const profile of Object.values(profiles)) {
    const points = profile && Array.isArray(profile.control_points)
      ? profile.control_points.filter((point) => Array.isArray(point) && point.length >= 2 && point.every(Number.isFinite))
      : [];
    if (!points.length) {
      continue;
    }
    const vectors = points.map(([r, z]) => new THREE.Vector3(r - center.x, -center.y, z - center.z));
    const lineGeometry = new THREE.BufferGeometry().setFromPoints(vectors);
    const line = new THREE.Line(lineGeometry, new THREE.LineBasicMaterial({ color: "#0f766e" }));
    line.name = `meridional-support-profile:${profile.id}`;
    line.userData.inspectionClass = "meridional-support-profile";
    group.add(line);
    const controlGeometry = new THREE.BufferGeometry().setFromPoints(vectors);
    const controls = new THREE.Points(
      controlGeometry,
      new THREE.PointsMaterial({ color: "#be123c", size: 8, sizeAttenuation: false }),
    );
    controls.name = `meridional-support-control:${profile.id}`;
    controls.userData.inspectionClass = "meridional-support-control";
    group.add(controls);
  }
  return group;
}
