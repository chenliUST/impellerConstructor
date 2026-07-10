import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import {
  inspectionViewportRects,
  inspectionRendererLifecycle,
  orthographicCameraFrame,
  viewportAtPointer,
  visibleGeometricViews,
} from "../inspectionSceneModel.js?v=1.1.5";
import { defaultVisibleLayers } from "../workspaceModel.js?v=1.1.5";
import { createSurfaceGraphGroup, disposeObject, surfaceGraphBounds } from "./ModelViewer.js?v=1.1.5";
import { ParameterAnnotationOverlay } from "./ParameterAnnotationOverlay.js?v=1.1.5";

const h = React.createElement;
const EMPTY_SURFACE_GRAPH = { surfaces: [] };

export function InspectionScene({
  manifest = null,
  surfaceGraph = EMPTY_SURFACE_GRAPH,
  layout = "3d",
  selectedSurfaceIds = [],
  onSelectSurface = null,
  visibleLayers = defaultVisibleLayers(),
  viewMode = "combined",
  annotationsByView = {},
  selectedAnnotationId = null,
  onSelectAnnotation = null,
}) {
  const containerRef = useRef(null);
  const groupRef = useRef(null);
  const camerasRef = useRef(null);
  const controlsRef = useRef(null);
  const rectsRef = useRef({});
  const sizeRef = useRef({ width: 0, height: 0 });
  const resizeRef = useRef(null);
  const layoutRef = useRef(layout);
  const onSelectSurfaceRef = useRef(onSelectSurface);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const [surfaceCount, setSurfaceCount] = useState(0);
  const [rendererStats, setRendererStats] = useState(() => inspectionRendererLifecycle.snapshot());

  layoutRef.current = layout;
  onSelectSurfaceRef.current = onSelectSurface;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#f5f5f5");
    const cameras = {
      "3d": new THREE.PerspectiveCamera(45, 1, 0.1, 100000),
      top: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000),
      meridional: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000),
    };
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    const releaseRendererLifecycle = inspectionRendererLifecycle.register(renderer);
    setRendererStats(inspectionRendererLifecycle.snapshot());
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor("#f5f5f5");
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
    const surfaceMeshes = [];
    group.traverse((child) => {
      if (child.isLineSegments && child.userData.isSurfaceUvWire) {
        child.visible = false;
      }
      if (!child.isMesh || !child.userData.surfaceId) {
        return;
      }
      surfaceMeshes.push(child);
      forEachMaterial(child.material, (material) => {
        material.color.set("#ffffff");
        material.emissive.set("#000000");
        material.emissiveIntensity = 0;
        material.opacity = 1;
        material.transparent = false;
        material.polygonOffset = true;
        material.polygonOffsetFactor = 1;
        material.polygonOffsetUnits = 1;
      });
    });
    for (const mesh of surfaceMeshes) {
      const contour = new THREE.LineSegments(
        new THREE.EdgesGeometry(mesh.geometry, 35),
        new THREE.LineBasicMaterial({ color: "#111111", depthTest: true, depthWrite: false }),
      );
      contour.renderOrder = 1;
      contour.userData.isInspectionContour = true;
      contour.userData.surfaceId = mesh.userData.surfaceId;
      contour.userData.layer = mesh.userData.layer;
      group.add(contour);
    }
    scene.add(group);
    scene.add(new THREE.HemisphereLight("#ffffff", "#8a928e", 2.4));
    const keyLight = new THREE.DirectionalLight("#ffffff", 2.2);
    keyLight.position.set(1200, -1800, 2200);
    scene.add(keyLight);

    groupRef.current = group;
    camerasRef.current = cameras;
    controlsRef.current = controls;
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
        renderer.render(scene, cameras[viewId]);
      }
    };
    animate();

    return () => {
      window.cancelAnimationFrame(frameId);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerleave", handlePointerLeave);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown, true);
      Object.values(controls).forEach((control) => control.dispose());
      scene.remove(group);
      disposeObject(group);
      renderer.dispose();
      releaseRendererLifecycle();
      renderer.domElement.remove();
      groupRef.current = null;
      camerasRef.current = null;
      controlsRef.current = null;
      resizeRef.current = null;
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
      const selected = selectedSurfaceIdSet.has(child.userData.surfaceId);
      if (child.isMesh && child.userData.surfaceId) {
        forEachMaterial(child.material, (material) => {
          material.color.set(selected ? "#111111" : "#ffffff");
        });
      }
      if (child.isLineSegments && child.userData.isInspectionContour) {
        child.material.color.set(selected ? "#ffffff" : "#111111");
      }
    });
  }, [manifest, selectedSurfaceIds, surfaceGraph]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) {
      return;
    }
    group.visible = true;
    group.traverse((child) => {
      if (child.isMesh && child.userData.layer) {
        child.visible = visibleLayers[child.userData.layer] !== false;
      }
      if (child.isLineSegments && child.userData.isSurfaceUvWire) {
        child.visible = false;
      }
      if (child.isLineSegments && child.userData.isMeshOverlay) {
        child.visible = false;
      }
      if (child.isLineSegments && child.userData.isInspectionContour) {
        child.visible = visibleLayers[child.userData.layer] !== false;
      }
    });
  }, [manifest, surfaceGraph, visibleLayers]);

  const rects = inspectionViewportRects(viewportSize.width, viewportSize.height, layout);
  const geometricViews = visibleGeometricViews(layout);

  return h(
    "div",
    {
      className: "inspection-scene",
      style: { position: "relative", width: "100%", height: "100%", minWidth: 0, minHeight: 0 },
      "data-layout": layout,
    },
    h("div", {
      className: "inspection-webgl",
      ref: containerRef,
      style: { position: "absolute", inset: 0, overflow: "hidden" },
      "data-testid": "inspection-webgl",
      "data-renderer-count": String(rendererStats.liveRendererCount),
      "data-context-count": String(rendererStats.liveContextCount),
      "data-renderer-created-count": String(rendererStats.createdRendererCount),
      "data-renderer-live-count": String(rendererStats.liveRendererCount),
      "data-context-created-count": String(rendererStats.createdContextCount),
      "data-context-live-count": String(rendererStats.liveContextCount),
      "data-scene-surface-count": String(surfaceCount),
      "data-visible-uv-overlay-count": "0",
    }),
    viewportSize.width > 0 && viewportSize.height > 0
      ? geometricViews.map((viewId) => {
          const rect = rects[viewId];
          if (!rect?.width || !rect?.height) {
            return null;
          }
          return h(
            "div",
            {
              className: `inspection-annotation-viewport inspection-annotation-${viewId}`,
              key: viewId,
              style: {
                position: "absolute",
                left: rect.x,
                top: viewportSize.height - rect.y - rect.height,
                width: rect.width,
                height: rect.height,
                overflow: "hidden",
                pointerEvents: "none",
              },
              "aria-label": `${viewId} inspection parameters`,
            },
            h(ParameterAnnotationOverlay, {
              annotations: annotationsByView[viewId] || [],
              selectedAnnotationId,
              onSelectAnnotation,
            }),
          );
        })
      : null,
  );
}

function forEachMaterial(material, callback) {
  for (const item of Array.isArray(material) ? material : [material]) {
    if (item) {
      callback(item);
    }
  }
}
