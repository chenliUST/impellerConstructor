import React, { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { inspectionRendererLifecycle } from "../inspectionSceneModel.js?v=1.1.5";
import { createSurfaceGraphGroup, disposeObject, surfaceGraphBounds } from "./ModelViewer.js?v=1.1.5";

const h = React.createElement;
const EMPTY_SURFACE_GRAPH = { surfaces: [] };
export const EMPTY_BLADE_SURFACE_IDS = Object.freeze([]);

export function BladeFeatureScene({
  surfaceGraph = EMPTY_SURFACE_GRAPH,
  bladeSurfaceIds = EMPTY_BLADE_SURFACE_IDS,
  selectedParameter = null,
  manifest = null,
}) {
  const containerRef = useRef(null);
  const [rendererStats, setRendererStats] = useState(() => inspectionRendererLifecycle.snapshot());
  const [surfaceCount, setSurfaceCount] = useState(0);
  const normalizedBladeSurfaceIds = useMemo(
    () => normalizeBladeSurfaceIds(bladeSurfaceIds),
    [bladeSurfaceIds],
  );
  const geometryStatus = bladeFeatureGeometryStatus(selectedParameter);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#ffffff");
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    const releaseRendererLifecycle = inspectionRendererLifecycle.register(renderer);
    setRendererStats(inspectionRendererLifecycle.snapshot());
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor("#ffffff");
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    const contextSurfaceGraph = bladeContextSurfaceGraph(surfaceGraph, normalizedBladeSurfaceIds);
    const bounds = surfaceGraphBounds(contextSurfaceGraph);
    const contextGroup = createSurfaceGraphGroup(
      contextSurfaceGraph,
      bounds.center,
      "cad_review_360",
      new Set(),
      "off",
      manifest,
    );
    const contextSurfaceCount = styleBladeContextGroup(contextGroup);

    const featureGroup = createEngineeringFeatureGroup(
      selectedParameter?.features || selectedParameter?.feature_geometry || [],
      bounds.center,
      Math.max(10, (Number(bounds.radius) || 1) * 0.12),
    );
    scene.add(contextGroup);
    scene.add(featureGroup);
    scene.add(new THREE.HemisphereLight("#ffffff", "#a0a0a0", 2.2));
    const keyLight = new THREE.DirectionalLight("#ffffff", 1.6);
    keyLight.position.set(1200, -1800, 2200);
    scene.add(keyLight);
    setSurfaceCount(contextSurfaceCount);

    const frameCamera = () => {
      const width = Math.max(1, Math.floor(container.clientWidth));
      const height = Math.max(1, Math.floor(container.clientHeight));
      const radius = Math.max(Number(bounds.radius) || 1, 1);
      camera.aspect = width / height;
      const distance = bladeFeatureCameraDistance(radius, width, height);
      camera.near = Math.max(radius / 100, 0.1);
      camera.far = Math.max(distance * 20, 100000);
      camera.position.set(distance * 0.8, -distance, distance * 0.55);
      camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      controls.update();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(frameCamera);
    observer.observe(container);
    frameCamera();

    let frameId = 0;
    const animate = () => {
      frameId = window.requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      window.cancelAnimationFrame(frameId);
      observer.disconnect();
      scene.remove(contextGroup);
      scene.remove(featureGroup);
      disposeBladeFeatureSceneResources({
        contextGroup,
        featureGroup,
        controls,
        renderer,
        releaseRendererLifecycle,
      });
      renderer.domElement.remove();
      setSurfaceCount(0);
      setRendererStats(inspectionRendererLifecycle.snapshot());
    };
  }, [manifest, normalizedBladeSurfaceIds, selectedParameter, surfaceGraph]);

  return h(
    "div",
    {
      className: "blade-feature-scene",
      style: { position: "relative", width: "100%", height: "100%", minWidth: 0, minHeight: 0 },
      "data-testid": "blade-feature-scene",
    },
    h("div", {
      ref: containerRef,
      style: { position: "absolute", inset: 0, overflow: "hidden" },
      "data-testid": "blade-feature-webgl",
      "data-renderer-count": String(rendererStats.liveRendererCount),
      "data-context-count": String(rendererStats.liveContextCount),
      "data-renderer-live-count": String(rendererStats.liveRendererCount),
      "data-context-live-count": String(rendererStats.liveContextCount),
      "data-scene-surface-count": String(surfaceCount),
      "data-visible-uv-overlay-count": "0",
      "data-visible-mesh-overlay-count": "0",
    }),
    geometryStatus === "geometry unavailable"
      ? h(
          "div",
          {
            className: "blade-feature-geometry-unavailable",
            role: "status",
            style: { position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "#444" },
          },
          "geometry unavailable",
        )
      : null,
  );
}

export function bladeFeatureGeometryStatus(selectedParameter) {
  if (!selectedParameter) {
    return null;
  }
  const features = selectedParameter.features || selectedParameter.feature_geometry || [];
  return features.some((feature) =>
    feature?.coordinate_system === "model_xyz"
    && feature?.rendering_role !== "drawing_context")
    ? "available"
    : "geometry unavailable";
}

export function bladeContextSurfaceGraph(surfaceGraph, bladeSurfaceIds) {
  const selectedSurfaceIdSet = new Set(normalizeBladeSurfaceIds(bladeSurfaceIds));
  return {
    ...(surfaceGraph || EMPTY_SURFACE_GRAPH),
    surfaces: (surfaceGraph?.surfaces || []).filter((surface) =>
      selectedSurfaceIdSet.has(surface.id || surface.surface_graph_id),
    ),
  };
}

export function normalizeBladeSurfaceIds(bladeSurfaceIds) {
  if (!Array.isArray(bladeSurfaceIds) || bladeSurfaceIds.length === 0) {
    return EMPTY_BLADE_SURFACE_IDS;
  }
  return [...new Set(bladeSurfaceIds.filter((surfaceId) => typeof surfaceId === "string" && surfaceId.length > 0))];
}

export function bladeFeatureCameraDistance(radius, width, height) {
  const safeRadius = Math.max(Number(radius) || 1, 1);
  const aspect = Math.max(1, Number(width)) / Math.max(1, Number(height));
  return safeRadius * 2.2 / Math.min(1, aspect);
}

export function styleBladeContextGroup(contextGroup) {
  let contextSurfaceCount = 0;
  contextGroup.traverse((child) => {
    if (child.userData.isSurfaceUvWire || child.userData.isMeshOverlay) {
      child.visible = false;
    }
    if (!child.isMesh || !child.userData.surfaceId) {
      return;
    }
    const mesh = child;
    contextSurfaceCount += 1;
    forEachMaterial(mesh.material, (material) => {
      material.color.set("#ffffff");
      material.emissive.set("#000000");
      material.emissiveIntensity = 0;
      material.opacity = 1;
      material.transparent = false;
    });
    const contour = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry, 35),
      new THREE.LineBasicMaterial({ color: "#111111", depthTest: true, depthWrite: false }),
    );
    contour.renderOrder = 1;
    contour.userData.isBladeContextContour = true;
    contour.userData.surfaceId = mesh.userData.surfaceId;
    contextGroup.add(contour);
  });
  return contextSurfaceCount;
}

export function createEngineeringFeatureGroup(features, center, vectorLength = 10) {
  const featureGroup = new THREE.Group();
  featureGroup.userData.isEngineeringFeature = true;
  for (const feature of features) {
    if (feature?.coordinate_system !== "model_xyz" || feature?.rendering_role === "drawing_context") {
      continue;
    }
    if (feature.kind === "nurbs_curve") {
      addEngineeringLine(featureGroup, feature.control_points, feature, center);
    }
    if (feature.kind === "polyline") {
      addEngineeringLine(featureGroup, feature.points, feature, center);
    }
    if (feature.kind === "control_point" || feature.kind === "point") {
      addEngineeringPoint(featureGroup, feature.coordinates, feature, center);
    }
    if (feature.kind === "local_frame" && localFrameVectorsAreFinite(feature)) {
      addEngineeringVector(featureGroup, feature.origin, feature.s_axis, feature, center, vectorLength);
      addEngineeringVector(featureGroup, feature.origin, feature.q_axis, feature, center, vectorLength);
    }
    if (feature.kind === "reference_axis") {
      addEngineeringVector(featureGroup, feature.origin, feature.direction, feature, center, vectorLength);
    }
  }
  return featureGroup;
}

function addEngineeringLine(group, points, feature, center) {
  const positions = [];
  for (const point of points || []) {
    const vector = featurePointVector(point, feature.coordinate_system);
    if (vector) {
      positions.push(vector[0] - center.x, vector[1] - center.y, vector[2] - center.z);
    }
  }
  if (positions.length < 6) {
    return;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const line = new THREE.Line(
    geometry,
    new THREE.LineBasicMaterial({ color: "#c40000", depthTest: false, depthWrite: false }),
  );
  line.renderOrder = 2;
  line.userData.isEngineeringFeature = true;
  line.userData.featureId = feature.id;
  group.add(line);
}

function addEngineeringPoint(group, point, feature, center) {
  const vector = featurePointVector(point, feature.coordinate_system);
  if (!vector) {
    return;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute([vector[0] - center.x, vector[1] - center.y, vector[2] - center.z], 3),
  );
  const marker = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({ color: "#c40000", size: 10, sizeAttenuation: true, depthTest: false, depthWrite: false }),
  );
  marker.renderOrder = 3;
  marker.userData.isEngineeringFeature = true;
  marker.userData.featureId = feature.id;
  group.add(marker);
}

function addEngineeringVector(group, origin, direction, feature, center, vectorLength) {
  const originVector = featurePointVector(origin, feature.coordinate_system);
  const directionVector = featureDirectionVector(direction, feature.coordinate_system);
  const magnitude = directionVector && Math.hypot(...directionVector);
  if (!originVector || !directionVector || !Number.isFinite(magnitude) || magnitude <= 1.0e-9) {
    return;
  }
  const endpoint = originVector.map(
    (coordinate, index) => coordinate + (directionVector[index] * vectorLength) / magnitude,
  );
  addEngineeringLine(group, [originVector, endpoint], feature, center);
}

function featurePointVector(point, coordinateSystem) {
  if (coordinateSystem !== "model_xyz" || !Array.isArray(point) || point.length < 3 || !point.every(Number.isFinite)) {
    return null;
  }
  return point.slice(0, 3);
}

function featureDirectionVector(direction, coordinateSystem) {
  return featurePointVector(direction, coordinateSystem);
}

function localFrameVectorsAreFinite(feature) {
  return [feature.origin, feature.s_axis, feature.q_axis].every((vector) =>
    featurePointVector(vector, feature.coordinate_system),
  );
}

export function disposeBladeFeatureSceneResources({
  contextGroup,
  featureGroup,
  controls = null,
  renderer = null,
  releaseRendererLifecycle = null,
}) {
  controls?.dispose();
  if (contextGroup) {
    disposeObject(contextGroup);
  }
  if (featureGroup) {
    disposeObject(featureGroup);
  }
  renderer?.dispose();
  releaseRendererLifecycle?.();
}

function forEachMaterial(material, callback) {
  for (const item of Array.isArray(material) ? material : [material]) {
    if (item) {
      callback(item);
    }
  }
}
