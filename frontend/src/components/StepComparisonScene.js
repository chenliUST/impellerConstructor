import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

import { comparisonViewportRects } from "../stepReconstructionModel.js?v=1.1.6";

const h = React.createElement;

export function StepComparisonScene({ artifactUrls, onHeatmapReadout }) {
  const containerRef = useRef(null);
  const [status, setStatus] = useState("Waiting for a completed reconstruction audit.");

  useEffect(() => {
    if (!artifactUrls?.source || !artifactUrls?.reconstruction || !artifactUrls?.heatmap) return undefined;
    const container = containerRef.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.max(2, Math.min(window.devicePixelRatio || 1, 2.5)));
    renderer.setScissorTest(true);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    const scenes = {
      source: comparisonScene(),
      reconstruction: comparisonScene(),
      heatmap: comparisonScene(),
    };
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100000);
    camera.position.set(120, -160, 95);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    const bounds = new THREE.Box3();
    let loadedCount = 0;
    let heatmapMesh = null;
    let disposed = false;

    const registerObject = (sceneId, object) => {
      scenes[sceneId].add(object);
      bounds.expandByObject(object);
      loadedCount += 1;
      if (loadedCount >= 3) frameComparisonCamera(camera, controls, bounds);
    };

    const loader = new STLLoader();
    loader.load(artifactUrls.source, (geometry) => {
      if (disposed) return geometry.dispose();
      registerObject("source", neutralMesh(geometry));
    }, undefined, (error) => setStatus(error?.message || "Source STL failed to load"));
    loader.load(artifactUrls.reconstruction, (geometry) => {
      if (disposed) return geometry.dispose();
      registerObject("reconstruction", neutralMesh(geometry));
    }, undefined, (error) => setStatus(error?.message || "Reconstruction STL failed to load"));
    fetch(artifactUrls.heatmap)
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} heatmap failed to load`);
        return response.json();
      })
      .then((payload) => {
        if (disposed) return;
        heatmapMesh = heatmapObject(payload);
        registerObject("heatmap", heatmapMesh);
        setStatus("Source, reconstruction and deviation heatmap loaded");
      })
      .catch((error) => setStatus(error instanceof Error ? error.message : String(error)));

    const resize = () => {
      const width = Math.max(container.clientWidth, 640);
      const height = Math.max(container.clientHeight, 520);
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    let frameId = 0;
    const animate = () => {
      frameId = window.requestAnimationFrame(animate);
      controls.update();
      const width = renderer.domElement.clientWidth;
      const height = renderer.domElement.clientHeight;
      const rects = comparisonViewportRects(width, height);
      for (const sceneId of ["source", "reconstruction", "heatmap"]) {
        const rect = rects[sceneId];
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
      const pointer = new THREE.Vector2(
        ((localX - heat.x) / heat.width) * 2 - 1,
        ((localYFromBottom - heat.y) / heat.height) * 2 - 1,
      );
      const raycaster = new THREE.Raycaster();
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObject(heatmapMesh, false)[0];
      if (!hit?.face) return;
      const errors = heatmapMesh.geometry.getAttribute("errorMm");
      const error = errors.getX(hit.face.a);
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
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, [artifactUrls?.source, artifactUrls?.reconstruction, artifactUrls?.heatmap, onHeatmapReadout]);

  return h("div", { className: "step-comparison-scene", ref: containerRef, "data-testid": "step-comparison-scene" },
    h("span", { className: "comparison-pane-label source" }, "SOURCE STEP"),
    h("span", { className: "comparison-pane-label reconstruction" }, "V1.1.2 RECONSTRUCTION"),
    h("span", { className: "comparison-pane-label heatmap" }, "DEVIATION HEATMAP"),
    h("p", { className: "comparison-load-status" }, status),
  );
}

function comparisonScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#ffffff");
  scene.add(new THREE.HemisphereLight("#ffffff", "#b8c0bd", 2.0));
  const light = new THREE.DirectionalLight("#ffffff", 2.4);
  light.position.set(100, -120, 180);
  scene.add(light);
  return scene;
}

function neutralMesh(geometry) {
  geometry.computeVertexNormals();
  const group = new THREE.Group();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: "#e8ecea", roughness: 0.72, metalness: 0.05, side: THREE.DoubleSide }));
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30), new THREE.LineBasicMaterial({ color: "#1d2723" }));
  group.add(mesh, edges);
  return group;
}

function heatmapObject(payload) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute((payload.vertices || []).flat(), 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute((payload.colors_rgb || []).flat(), 3));
  geometry.setAttribute("errorMm", new THREE.Float32BufferAttribute(payload.errors_mm || [], 1));
  geometry.setIndex((payload.triangles || []).flat());
  geometry.computeVertexNormals();
  return new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.76, metalness: 0, side: THREE.DoubleSide }));
}

function frameComparisonCamera(camera, controls, bounds) {
  const sphere = new THREE.Sphere();
  bounds.getBoundingSphere(sphere);
  const radius = Math.max(sphere.radius, 1);
  const distance = radius * 2.8;
  camera.near = Math.max(radius / 1000, 0.01);
  camera.far = distance * 20;
  camera.position.copy(sphere.center).add(new THREE.Vector3(distance * 0.7, -distance, distance * 0.55));
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
