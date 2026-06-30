import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

import { defaultVisibleLayers, layerForConstructionFeature, layerForSurface } from "../workspaceModel.js";

const h = React.createElement;

export function ModelViewer({
  stlUrl,
  surfaceGraph = null,
  constructionLines = {},
  viewMode,
  setViewMode,
  autoRotate,
  setAutoRotate,
  visibleLayers = defaultVisibleLayers(),
}) {
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);
  const controlsRef = useRef(null);
  const centerRef = useRef(new THREE.Vector3());
  const modelRef = useRef({ shaded: null, constructionGroup: null });
  const [status, setStatus] = useState("Generate a model to load STL geometry.");

  useEffect(() => {
    const container = containerRef.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#eef2f0");

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100000);
    camera.position.set(1400, -2200, 1200);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotateSpeed = 0.8;

    scene.add(new THREE.HemisphereLight("#ffffff", "#8a928e", 2.4));
    const keyLight = new THREE.DirectionalLight("#ffffff", 2.2);
    keyLight.position.set(1200, -1800, 2200);
    scene.add(keyLight);
    scene.add(new THREE.AxesHelper(900));

    sceneRef.current = scene;
    cameraRef.current = camera;
    rendererRef.current = renderer;
    controlsRef.current = controls;

    const resize = () => {
      const width = Math.max(320, container.clientWidth);
      const height = Math.max(360, container.clientHeight);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

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
      clearModel();
      controls.dispose();
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.autoRotate = autoRotate;
    }
  }, [autoRotate]);

  useEffect(() => {
    updateVisibility();
  }, [viewMode, visibleLayers]);

  useEffect(() => {
    renderConstructionLines(mergeConstructionLines(constructionLines, surfaceGraph));
    updateVisibility();
  }, [constructionLines, surfaceGraph]);

  useEffect(() => {
    if (!surfaceGraph?.surfaces?.length || !sceneRef.current) {
      return;
    }

    setStatus("Rendering surface graph...");
    clearModel();
    const bounds = surfaceGraphBounds(surfaceGraph);
    centerRef.current.copy(bounds.center);
    const shaded = createSurfaceGraphGroup(surfaceGraph, bounds.center);
    modelRef.current.shaded = shaded;
    sceneRef.current.add(shaded);
    renderConstructionLines(mergeConstructionLines(constructionLines, surfaceGraph));
    frameCamera(bounds.radius || 1000);
    updateVisibility();
    setStatus("Surface graph rendered");
  }, [surfaceGraph]);

  useEffect(() => {
    if (surfaceGraph?.surfaces?.length) {
      return undefined;
    }
    if (!stlUrl || !sceneRef.current) {
      return undefined;
    }

    let cancelled = false;
    setStatus("Loading STL...");
    clearModel();

    const loader = new STLLoader();
    loader.load(
      stlUrl,
      (geometry) => {
        if (cancelled) {
          geometry.dispose();
          return;
        }

        geometry.computeVertexNormals();
        geometry.computeBoundingBox();
        const center = new THREE.Vector3();
        geometry.boundingBox.getCenter(center);
        centerRef.current.copy(center);
        geometry.translate(-center.x, -center.y, -center.z);
        geometry.computeBoundingSphere();

        const shaded = new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({
            color: "#7aa58f",
            roughness: 0.55,
            metalness: 0.18,
            side: THREE.DoubleSide,
          }),
        );

        modelRef.current.shaded = shaded;
        sceneRef.current.add(shaded);
        renderConstructionLines(mergeConstructionLines(constructionLines, surfaceGraph));
        frameCamera(geometry.boundingSphere?.radius || 1000);
        updateVisibility();
        setStatus("STL loaded");
      },
      undefined,
      (loadError) => {
        setStatus(loadError?.message || "STL loading failed");
      },
    );

    return () => {
      cancelled = true;
    };
  }, [stlUrl]);

  function updateVisibility() {
    const shaded = modelRef.current.shaded;
    const constructionGroup = modelRef.current.constructionGroup;
    if (shaded) {
      const showShaded = viewMode !== "wireframe" && visibleLayers.shaded_surfaces !== false;
      shaded.visible = showShaded;
      shaded.traverse((child) => {
        if (child.isMesh && child.userData.layer) {
          child.visible = showShaded && visibleLayers[child.userData.layer] !== false;
        }
      });
    }
    if (constructionGroup) {
      const showConstruction = viewMode !== "shaded";
      constructionGroup.visible = showConstruction;
      constructionGroup.traverse((child) => {
        if (child.isLineSegments && child.userData.layer) {
          child.visible = showConstruction && visibleLayers[child.userData.layer] !== false;
        }
      });
    }
  }

  function clearModel() {
    const scene = sceneRef.current;
    if (modelRef.current.shaded && scene) {
      scene.remove(modelRef.current.shaded);
      disposeObject(modelRef.current.shaded);
    }
    clearConstructionGroup();
    modelRef.current = { shaded: null, constructionGroup: null };
  }

  function clearConstructionGroup() {
    const scene = sceneRef.current;
    const group = modelRef.current.constructionGroup;
    if (!group || !scene) {
      return;
    }
    scene.remove(group);
    group.traverse((child) => {
      if (child.geometry) {
        child.geometry.dispose();
      }
      if (child.material) {
        child.material.dispose();
      }
    });
    modelRef.current.constructionGroup = null;
  }

  function renderConstructionLines(linesByFeature) {
    if (!sceneRef.current) {
      return;
    }
    clearConstructionGroup();
    const group = createConstructionGroup(linesByFeature || {}, centerRef.current);
    if (group.children.length === 0) {
      return;
    }
    modelRef.current.constructionGroup = group;
    sceneRef.current.add(group);
  }

  function frameCamera(radius) {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) {
      return;
    }

    const distance = Math.max(radius * 2.4, 800);
    camera.near = Math.max(radius / 100, 0.1);
    camera.far = distance * 20;
    camera.position.set(distance * 0.8, -distance, distance * 0.55);
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.update();
  }

  return h(
    "div",
    { className: "viewer-shell" },
    h(
      "div",
      { className: "viewer-toolbar" },
      h(
        "div",
        { className: "segmented" },
        ["shaded", "wireframe", "combined"].map((mode) =>
          h(
            "button",
            {
              key: mode,
              className: viewMode === mode ? "active" : "",
              onClick: () => setViewMode(mode),
            },
            mode,
          ),
        ),
      ),
      h(
        "label",
        { className: "toggle" },
        h("input", {
          type: "checkbox",
          checked: autoRotate,
          onChange: (event) => setAutoRotate(event.target.checked),
        }),
        "Auto rotate",
      ),
    ),
    h("div", { className: "viewer-canvas", ref: containerRef }),
    h("div", { className: "viewer-status" }, status),
  );
}

function createSurfaceGraphGroup(surfaceGraph, center) {
  const group = new THREE.Group();
  const colors = {
    hub: "#7aa58f",
    open_tip_reference: "#b5c7a0",
    reference_only: "#b5c7a0",
    shroud: "#9db7c5",
    front_shroud_inner_surface: "#9db7c5",
    blade_pressure: "#6f9b85",
    blade_suction: "#5d806f",
    blade_leading_edge_closure: "#f59e0b",
    blade_trailing_edge_closure: "#ef4444",
    blade_root_hub_closure: "#22c55e",
    blade_tip_closure: "#38bdf8",
  };

  for (const surface of surfaceGraph.surfaces || []) {
    const grid = surface.uv_grid || [];
    if (grid.length < 2 || grid[0].length < 2) {
      continue;
    }
    const geometry = surfaceGridGeometry(grid, center);
    geometry.computeVertexNormals();
    const display = surface.display || {};
    const isEdgeClosure = surface.kind === "edge_closure_surface";
    const material = new THREE.MeshStandardMaterial({
      color: display.color || colors[surface.role] || "#7aa58f",
      roughness: 0.58,
      metalness: 0.16,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: display.opacity ?? (surface.role === "open_tip_reference" || surface.role === "reference_only" ? 0.3 : isEdgeClosure ? 1.0 : 0.92),
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.layer = layerForSurface(surface);
    group.add(mesh);
  }

  return group;
}

function surfaceGridGeometry(grid, center) {
  const positions = [];
  const indices = [];
  const vCount = grid[0].length;

  for (const row of grid) {
    for (const point of row) {
      positions.push(point[0] - center.x, point[1] - center.y, point[2] - center.z);
    }
  }

  for (let u = 0; u < grid.length - 1; u += 1) {
    for (let v = 0; v < vCount - 1; v += 1) {
      const a = u * vCount + v;
      const b = (u + 1) * vCount + v;
      const c = (u + 1) * vCount + v + 1;
      const d = u * vCount + v + 1;
      indices.push(a, b, d, b, c, d);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  return geometry;
}

function surfaceGraphBounds(surfaceGraph) {
  const box = new THREE.Box3();
  let hasPoint = false;

  for (const surface of surfaceGraph.surfaces || []) {
    for (const row of surface.uv_grid || []) {
      for (const point of row) {
        box.expandByPoint(new THREE.Vector3(point[0], point[1], point[2]));
        hasPoint = true;
      }
    }
  }

  if (!hasPoint) {
    return { center: new THREE.Vector3(), radius: 1000 };
  }

  const center = new THREE.Vector3();
  box.getCenter(center);
  const size = new THREE.Vector3();
  box.getSize(size);
  return { center, radius: size.length() * 0.5 };
}

function createConstructionGroup(linesByFeature, center) {
  const group = new THREE.Group();
  const colors = {
    hub: "#0f766e",
    blade: "#162b36",
    blade_u: "#0f2f3f",
    blade_v: "#28666e",
    blade_boundaries: "#f59e0b",
    blade_edges: "#f59e0b",
    named_boundary_curve: "#f59e0b",
    shroud: "#b4512a",
    passage: "#b86125",
    surface_uv: "#315f72",
  };

  for (const [feature, lines] of Object.entries(linesByFeature)) {
    for (const line of lines || []) {
      const points = line.points || [];
      const positions = [];
      for (let index = 0; index < points.length - 1; index += 1) {
        pushPoint(positions, points[index], center);
        pushPoint(positions, points[index + 1], center);
      }
      if (positions.length === 0) {
        continue;
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      const material = new THREE.LineBasicMaterial({
        color: line.color || colors[feature] || "#1d2a32",
        transparent: true,
        opacity: feature === "blade_boundaries" || feature === "blade_edges" || feature === "named_boundary_curve" ? 1.0 : feature === "blade_u" || feature === "blade_v" || feature === "blade" || feature === "surface_uv" ? 0.82 : 0.72,
      });
      const lineSegments = new THREE.LineSegments(geometry, material);
      lineSegments.userData.layer = layerForConstructionFeature(feature);
      group.add(lineSegments);
    }
  }

  return group;
}

function mergeConstructionLines(constructionLines, surfaceGraph) {
  const merged = { ...(constructionLines || {}) };
  const namedBoundaryCurves = surfaceGraph?.named_boundary_curves || [];
  if (namedBoundaryCurves.length > 0) {
    merged.named_boundary_curve = namedBoundaryCurves.map((curve) => ({
      name: curve.id,
      role: curve.role,
      blade_index: curve.blade_index,
      source: "surface_graph.named_boundary_curve",
      points: curve.points || [],
      color: boundaryCurveColor(curve.role),
    }));
  }
  return merged;
}

function boundaryCurveColor(role) {
  const colors = {
    blade_root_boundary: "#22c55e",
    blade_tip_boundary: "#38bdf8",
    leading_edge_boundary: "#f59e0b",
    trailing_edge_boundary: "#ef4444",
  };
  return colors[role] || "#f59e0b";
}

function pushPoint(positions, point, center) {
  positions.push(point[0] - center.x, point[1] - center.y, point[2] - center.z);
}

function disposeObject(object) {
  object.traverse((child) => {
    if (child.geometry) {
      child.geometry.dispose();
    }
    if (Array.isArray(child.material)) {
      child.material.forEach((material) => material.dispose());
    } else if (child.material) {
      child.material.dispose();
    }
  });
}
