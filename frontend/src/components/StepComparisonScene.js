import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

import {
  comparisonViewportRects,
  heatmapTriangleSelection,
  inspectionPolylinePoints,
} from "../stepReconstructionModel.js?v=1.1.6-r4";

const h = React.createElement;
const defaultRuntime = { THREE, OrbitControls, STLLoader };

export function StepComparisonScene({ artifactUrls, inspection, overlays, semanticRegion, semanticRegionAliases, onHeatmapReadout, onRegionFilterStatus, runtime = defaultRuntime }) {
  const containerRef = useRef(null);
  const [status, setStatus] = useState("Waiting for a completed reconstruction audit.");

  useEffect(() => {
    if (!artifactUrls?.source || !artifactUrls?.reconstruction || !artifactUrls?.heatmap) return undefined;
    const container = containerRef.current;
    if (!container) return undefined;
    const { THREE: Three, OrbitControls: Controls, STLLoader: Loader } = runtime;
    const renderer = new Three.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.max(2, Math.min(window.devicePixelRatio || 1, 2.5)));
    renderer.setScissorTest(true);
    renderer.outputColorSpace = Three.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    const scenes = { source: comparisonScene(Three), reconstruction: comparisonScene(Three), heatmap: comparisonScene(Three) };
    const camera = new Three.PerspectiveCamera(38, 1, 0.01, 100000);
    camera.position.set(120, -160, 95);
    const controls = new Controls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    const bounds = new Three.Box3();
    const raycaster = new Three.Raycaster();
    let loadedCount = 0;
    let heatmapMesh = null;
    let disposed = false;
    let frameId = 0;

    const registerObject = (sceneId, object) => {
      scenes[sceneId].add(object);
      bounds.expandByObject(object);
      loadedCount += 1;
      if (loadedCount >= 3 && !bounds.isEmpty()) frameComparisonCamera(Three, camera, controls, bounds);
    };

    const loader = new Loader();
    loader.load(artifactUrls.source, (geometry) => {
      if (disposed) return geometry.dispose();
      registerObject("source", neutralMesh(Three, geometry));
      addInspectionOverlays(Three, scenes.source, inspection, overlays, "source");
    }, undefined, (error) => {
      if (disposed) return;
      setStatus(error?.message || "Source STL failed to load");
    });
    loader.load(artifactUrls.reconstruction, (geometry) => {
      if (disposed) return geometry.dispose();
      registerObject("reconstruction", neutralMesh(Three, geometry));
      addInspectionOverlays(Three, scenes.reconstruction, inspection, overlays, "reconstruction");
    }, undefined, (error) => {
      if (disposed) return;
      setStatus(error?.message || "Reconstruction STL failed to load");
    });
    fetch(artifactUrls.heatmap)
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} heatmap failed to load`);
        return response.json();
      })
      .then((payload) => {
        if (disposed) return;
        const selection = heatmapTriangleSelection(payload, semanticRegion, semanticRegionAliases);
        heatmapMesh = heatmapObject(Three, payload, selection.indexes);
        registerObject("heatmap", heatmapMesh);
        onRegionFilterStatus?.(selection);
        setStatus("Source, reconstruction and deviation heatmap loaded");
      })
      .catch((error) => {
        if (disposed) return;
        setStatus(error instanceof Error ? error.message : String(error));
      });

    const resize = () => {
      const width = Math.max(container.clientWidth, 640);
      const height = Math.max(container.clientHeight, 520);
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    const animate = () => {
      frameId = window.requestAnimationFrame(animate);
      controls.update();
      const width = renderer.domElement.clientWidth;
      const height = renderer.domElement.clientHeight;
      const rects = comparisonViewportRects(width, height);
      for (const sceneId of ["source", "reconstruction", "heatmap"]) {
        const rect = rects[sceneId];
        if (!rect.width || !rect.height) continue;
        renderer.setViewport(rect.x, rect.y, rect.width, rect.height);
        renderer.setScissor(rect.x, rect.y, rect.width, rect.height);
        renderer.setClearColor("#ffffff", 1);
        renderer.clear(true, true, true);
        camera.aspect = rect.width / Math.max(rect.height, 1);
        camera.updateProjectionMatrix();
        renderer.render(scenes[sceneId], camera);
      }
    };
    animate();

    const pointerMove = (event) => {
      if (!heatmapMesh || !onHeatmapReadout) return;
      const canvasRect = renderer.domElement.getBoundingClientRect();
      const rects = comparisonViewportRects(renderer.domElement.clientWidth, renderer.domElement.clientHeight);
      const heat = rects.heatmap;
      const localX = (event.clientX - canvasRect.left) * (renderer.domElement.clientWidth / canvasRect.width);
      const localYFromBottom = (canvasRect.bottom - event.clientY) * (renderer.domElement.clientHeight / canvasRect.height);
      if (localX < heat.x || localX > heat.x + heat.width || localYFromBottom < heat.y || localYFromBottom > heat.y + heat.height) return;
      const pointer = new Three.Vector2(((localX - heat.x) / heat.width) * 2 - 1, ((localYFromBottom - heat.y) / heat.height) * 2 - 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObject(heatmapMesh, false)[0];
      if (!hit?.face) return;
      const errors = heatmapMesh.geometry.getAttribute("errorMm");
      const error = errors?.getX(hit.face.a);
      onHeatmapReadout({ error_mm: error, point_mm: hit.point.toArray() });
    };
    renderer.domElement.addEventListener("pointermove", pointerMove);

    return () => {
      disposed = true;
      window.cancelAnimationFrame(frameId);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointermove", pointerMove);
      controls.dispose();
      Object.values(scenes).forEach(disposeScene);
      renderer.renderLists.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      if (renderer.domElement.parentNode === container) container.removeChild(renderer.domElement);
    };
  }, [artifactUrls?.source, artifactUrls?.reconstruction, artifactUrls?.heatmap, inspection, overlays, semanticRegion, semanticRegionAliases, onHeatmapReadout, onRegionFilterStatus, runtime]);

  return h("div", { className: "step-comparison-scene", ref: containerRef, "data-testid": "step-comparison-scene" },
    h("span", { className: "comparison-pane-label source" }, "SOURCE STEP"),
    h("span", { className: "comparison-pane-label reconstruction" }, "V1.1.2 RECONSTRUCTION"),
    h("span", { className: "comparison-pane-label heatmap" }, "DEVIATION HEATMAP"),
    h("p", { className: "comparison-load-status", role: "status" }, status),
  );
}

function comparisonScene(Three) {
  const scene = new Three.Scene();
  scene.background = new Three.Color("#ffffff");
  scene.add(new Three.HemisphereLight("#ffffff", "#b8c0bd", 2.0));
  const light = new Three.DirectionalLight("#ffffff", 2.4);
  light.position.set(100, -120, 180);
  scene.add(light);
  return scene;
}

function neutralMesh(Three, geometry) {
  geometry.computeVertexNormals();
  const group = new Three.Group();
  const mesh = new Three.Mesh(geometry, new Three.MeshStandardMaterial({ color: "#e8ecea", roughness: 0.72, metalness: 0.05, side: Three.DoubleSide }));
  const edges = new Three.LineSegments(new Three.EdgesGeometry(geometry, 30), new Three.LineBasicMaterial({ color: "#1d2723" }));
  group.add(mesh, edges);
  return group;
}

function heatmapObject(Three, payload, included) {
  const positions = Array.isArray(payload?.vertices) ? payload.vertices : [];
  const colors = Array.isArray(payload?.colors_rgb) ? payload.colors_rgb : [];
  const errors = Array.isArray(payload?.errors_mm) ? payload.errors_mm : [];
  const triangles = Array.isArray(payload?.triangles) ? payload.triangles : [];
  const geometry = new Three.BufferGeometry();
  geometry.setAttribute("position", new Three.Float32BufferAttribute(positions.flat(), 3));
  geometry.setAttribute("color", new Three.Float32BufferAttribute(colors.flat(), 3));
  geometry.setAttribute("errorMm", new Three.Float32BufferAttribute(errors, 1));
  geometry.setIndex(included.flatMap((index) => triangleVertexIndexes(triangles[index])));
  geometry.computeVertexNormals();
  return new Three.Mesh(geometry, new Three.MeshStandardMaterial({ vertexColors: true, roughness: 0.76, metalness: 0, side: Three.DoubleSide }));
}

function triangleVertexIndexes(triangle) {
  if (Array.isArray(triangle)) return triangle.filter(validTriangleIndex);
  if (!triangle || typeof triangle !== "object") return [];
  const indexes = triangle.vertex_indices || triangle.indices || triangle.vertices || [];
  return Array.isArray(indexes) ? indexes.filter(validTriangleIndex) : [];
}

function validTriangleIndex(value) {
  return Number.isInteger(value) && value >= 0;
}

function addInspectionOverlays(Three, scene, inspection, overlays, pane) {
  if (!inspection) return;
  if (overlays?.axis && inspection.axis) scene.add(axisOverlay(Three, inspection.axis));
  if (overlays?.hub) addRzEvidence(Three, scene, inspection.supportGeometry?.hub, "#b4512a", false);
  if (overlays?.tipSupport && inspection.hasMaterialShroud) {
    inspection.supportGeometry?.closedShroud?.forEach((profile, index) => addShroudMaterial(Three, scene, profile, index));
  } else if (overlays?.openTipReference && !inspection.hasMaterialShroud) {
    addRzEvidence(Three, scene, inspection.supportGeometry?.openTip, "#52635e", true, "open-tip-reference");
  }
  if (overlays?.spanSurfaces) addSpanSurfaces(Three, scene, inspection.stations);
  if (overlays?.representativeBlade) addRepresentativeEvidence(Three, scene, inspection.representative);
  if (overlays?.selectedLoop && pane === "source") addPointEvidence(Three, scene, inspection.selectedLoop, "#a92525", "source-loop-evidence");
}

function axisOverlay(Three, axis) {
  const origin = vectorFrom(Three, axis.origin_mm || axis.origin || [0, 0, 0]);
  const direction = vectorFrom(Three, axis.direction || [0, 0, 1]).normalize();
  const points = [origin.clone().addScaledVector(direction, -150), origin.clone().addScaledVector(direction, 150)];
  const line = new Three.Line(new Three.BufferGeometry().setFromPoints(points), new Three.LineDashedMaterial({ color: "#005ea8", dashSize: 4, gapSize: 2 }));
  line.computeLineDistances();
  return line;
}

function addRzEvidence(Three, scene, evidence, color, dashed, overlayKind = "support-evidence") {
  const points = [evidence?.control_points_rz_mm, evidence?.points_rz_mm, evidence?.profile_rz_mm]
    .find((value) => Array.isArray(value))
    ?.filter((point) => Array.isArray(point) && point.length >= 2 && point.slice(0, 2).every((value) => Number.isFinite(Number(value)))) || [];
  if (points.length < 2) return;
  const line = new Three.Line(new Three.BufferGeometry().setFromPoints(points.map(([r, z]) => new Three.Vector3(Number(r), 0, Number(z)))), dashed ? new Three.LineDashedMaterial({ color, dashSize: 2, gapSize: 1.2 }) : new Three.LineBasicMaterial({ color }));
  if (dashed) line.computeLineDistances();
  line.userData.overlayKind = overlayKind;
  scene.add(line);
}

function addShroudMaterial(Three, scene, evidence, profileIndex) {
  const points = [evidence?.control_points_rz_mm, evidence?.points_rz_mm, evidence?.profile_rz_mm]
    .find((value) => Array.isArray(value))
    ?.filter((point) => Array.isArray(point) && point.length >= 2 && point.slice(0, 2).every((value) => Number.isFinite(Number(value)))) || [];
  if (points.length < 2) return;
  const profile = points.map(([r, z]) => new Three.Vector2(Number(r), Number(z)));
  const material = new Three.MeshStandardMaterial({ color: "#176b58", roughness: 0.72, metalness: 0.03, transparent: true, opacity: 0.38, side: Three.DoubleSide });
  const shroud = new Three.Mesh(new Three.LatheGeometry(profile, 40), material);
  shroud.rotation.x = -Math.PI / 2;
  shroud.userData.overlayKind = "closed-shroud-material";
  shroud.userData.profileIndex = profileIndex;
  scene.add(shroud);
}

function addSpanSurfaces(Three, scene, stations) {
  for (const station of stations || []) {
    const profileRecord = station.profile && typeof station.profile === "object" && !Array.isArray(station.profile) ? station.profile : {};
    const profile = rzPoints(station.support_profile_rz_mm || station.profile_rz_mm || profileRecord.points_rz_mm || profileRecord.control_points_rz_mm || station.profile);
    if (profile.length >= 2) {
      const geometry = new Three.LatheGeometry(profile.map(([r, z]) => new Three.Vector2(Number(r), Number(z))), 40);
      const material = new Three.MeshBasicMaterial({ color: "#8a9691", transparent: true, opacity: 0.12, side: Three.DoubleSide, depthWrite: false });
      const surface = new Three.Mesh(geometry, material);
      surface.rotation.x = -Math.PI / 2;
      surface.userData.overlayKind = "span-surface-evidence";
      surface.userData.stationId = station.id;
      scene.add(surface);
      continue;
    }
    const z = Number(station.z_mm ?? station.axial_position_mm);
    const radius = Number(station.radius_mm ?? station.outer_radius_mm);
    if (!Number.isFinite(z) || !Number.isFinite(radius) || radius <= 0) continue;
    const geometry = new Three.RingGeometry(radius * 0.12, radius, 48);
    const material = new Three.MeshBasicMaterial({ color: "#8a9691", transparent: true, opacity: 0.12, side: Three.DoubleSide, depthWrite: false });
    const surface = new Three.Mesh(geometry, material);
    surface.rotation.x = Math.PI / 2;
    surface.position.z = z;
    surface.userData.overlayKind = "span-surface-evidence";
    surface.userData.stationId = station.id;
    scene.add(surface);
  }
}

function addRepresentativeEvidence(Three, scene, representative) {
  const loops = Array.isArray(representative?.section_loops) ? representative.section_loops : [];
  if (loops.length) {
    loops.forEach((loop) => addPointEvidence(Three, scene, loop, "#005ea8", "representative-blade-evidence"));
    return;
  }
  addPointEvidence(Three, scene, representative, "#005ea8", "representative-blade-evidence");
}

function addPointEvidence(Three, scene, evidence, color, overlayKind) {
  const points = pointTable(evidence);
  if (points.length < 2) return;
  const line = new Three.Line(new Three.BufferGeometry().setFromPoints(points.map((point) => vectorFrom(Three, point))), new Three.LineBasicMaterial({ color }));
  line.userData.overlayKind = overlayKind;
  scene.add(line);
}

function pointTable(evidence) {
  return inspectionPolylinePoints(evidence);
}

function rzPoints(value) {
  return (Array.isArray(value) ? value : []).filter((point) => Array.isArray(point) && point.length >= 2 && point.slice(0, 2).every((number) => Number.isFinite(Number(number))));
}

function vectorFrom(Three, value) {
  return new Three.Vector3(Number(value?.[0]) || 0, Number(value?.[1]) || 0, Number(value?.[2]) || 0);
}

function frameComparisonCamera(Three, camera, controls, bounds) {
  const sphere = new Three.Sphere();
  bounds.getBoundingSphere(sphere);
  const radius = Math.max(sphere.radius, 1);
  const distance = radius * 2.8;
  camera.near = Math.max(radius / 1000, 0.01);
  camera.far = distance * 20;
  camera.position.copy(sphere.center).add(new Three.Vector3(distance * 0.7, -distance, distance * 0.55));
  camera.updateProjectionMatrix();
  controls.target.copy(sphere.center);
  controls.update();
}

function disposeScene(scene) {
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose());
    else object.material?.dispose?.();
  });
}
