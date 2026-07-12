import React, { useEffect, useRef } from "react";
import * as THREE from "three";

import { representativeBladeGraph } from "../reviewEngineeringDrawingModel.js?v=1.1.5.1";
import { createSurfaceGraphGroup, disposeObject, surfaceGraphBounds } from "./ModelViewer.js?v=1.1.8";

const h = React.createElement;

export function EngineeringBladePairScene({ surfaceGraph = null, rows = [], manifest = null }) {
  const containerRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !rows.length || (!surfaceGraph && !rows.some((row) => row.representative_surfaces?.length))) return undefined;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(Math.max(window.devicePixelRatio || 1, 2), 3));
    renderer.setClearColor("#ffffff");
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    container.appendChild(renderer.domElement);

    const panels = rows.map((row) => createBladePanel(surfaceGraph, row, manifest));
    let disposed = false;
    const render = () => {
      if (disposed) return;
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height, false);
      renderer.setScissorTest(true);
      panels.forEach((panel, index) => {
        const panelHeight = height / panels.length;
        const y = height - (index + 1) * panelHeight;
        const aspect = width / panelHeight;
        frameOrthographicCamera(panel.camera, panel.radius, aspect);
        renderer.setViewport(0, y, width, panelHeight);
        renderer.setScissor(0, y, width, panelHeight);
        renderer.render(panel.scene, panel.camera);
      });
      renderer.setScissorTest(false);
    };
    const observer = new ResizeObserver(render);
    observer.observe(container);
    render();

    return () => {
      disposed = true;
      observer.disconnect();
      panels.forEach((panel) => disposeObject(panel.group));
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [manifest, rows, surfaceGraph]);

  return h("div", { className: "drawing-blade-pair-scene", ref: containerRef, "data-testid": "drawing-blade-pair-scene" },
    rows.map((row, index) => h("div", { className: "drawing-blade-scene-label", key: row.blade_class, style: { top: `${index * 100 / rows.length}%`, height: `${100 / rows.length}%` } },
      h("strong", null, `${row.blade_class.toUpperCase()} BLADE · ISOMETRIC`),
      h("dl", null, (row.callouts || []).map((callout) => h(React.Fragment, { key: callout.id },
        h("dt", null, callout.label),
        h("dd", null, formatCallout(callout)),
      ))),
    )),
  );
}

function createBladePanel(surfaceGraph, row, manifest) {
  const graph = row.representative_surfaces?.length
    ? { ...(surfaceGraph || {}), geometry_version: surfaceGraph?.geometry_version || "1.1", surfaces: row.representative_surfaces }
    : representativeBladeGraph(surfaceGraph, row.surface_ids);
  const bounds = surfaceGraphBounds(graph);
  const group = createSurfaceGraphGroup(graph, bounds.center, "cad_review_360", new Set(), "off", manifest);
  styleEngineeringBlade(group);
  addSectionLoopOverlays(group, row.overlay_loops_xyz, bounds.center);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#ffffff");
  scene.add(group);
  scene.add(new THREE.HemisphereLight("#ffffff", "#b9b9b9", 2.2));
  const key = new THREE.DirectionalLight("#ffffff", 1.8);
  key.position.set(1, -2, 3);
  scene.add(key);
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000);
  const radius = Math.max(Number(bounds.radius) || 1, 1);
  camera.position.set(radius * 1.8, -radius * 2.4, radius * 1.4);
  camera.lookAt(0, 0, 0);
  return { scene, camera, group, radius };
}

function styleEngineeringBlade(group) {
  const meshes = [];
  group.traverse((child) => {
    if (child.userData.isSurfaceUvWire || child.userData.isMeshOverlay) child.visible = false;
    if (child.isMesh) meshes.push(child);
  });
  meshes.forEach((mesh) => {
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      material.color.set("#f7f7f7");
      material.emissive.set("#000000");
      material.opacity = 1;
      material.transparent = false;
      material.side = THREE.DoubleSide;
    }
    const contour = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry, 28),
      new THREE.LineBasicMaterial({ color: "#111111", depthTest: true, depthWrite: false }),
    );
    contour.renderOrder = 2;
    group.add(contour);
  });
}

function addSectionLoopOverlays(group, overlay_loops_xyz = [], center = { x: 0, y: 0, z: 0 }) {
  const colors = ["#b42318", "#d97706", "#17803d", "#1769aa", "#7137a8"];
  overlay_loops_xyz.forEach((loop, loopIndex) => {
    (loop.segments || []).forEach((segment) => {
      const points = (segment.points_xyz || []).map((point) => new THREE.Vector3(
        Number(point[0]) - Number(center.x || 0),
        Number(point[1]) - Number(center.y || 0),
        Number(point[2]) - Number(center.z || 0),
      ));
      if (points.length < 2) return;
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: colors[loopIndex % colors.length],
        depthTest: true,
        depthWrite: false,
      }));
      line.renderOrder = 4;
      line.userData.inspectionClass = "section-loop-overlay";
      line.userData.stationRole = loop.station_role;
      group.add(line);
    });
  });
}

function frameOrthographicCamera(camera, radius, aspect) {
  const halfHeight = radius * 0.9;
  camera.left = -halfHeight * aspect;
  camera.right = halfHeight * aspect;
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.near = Math.max(radius / 100, 0.1);
  camera.far = radius * 20;
  camera.updateProjectionMatrix();
}

function formatCallout(callout) {
  const value = Array.isArray(callout.value)
    ? callout.value.filter((item) => item !== null && item !== undefined).map((item) => Number(item).toFixed(1)).join(" … ")
    : Number.isFinite(Number(callout.value)) ? Number(callout.value).toFixed(2) : "n/a";
  return `${value} ${callout.unit || ""}`.trim();
}
