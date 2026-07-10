import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

import {
  effectiveMeshOverlayMode,
  isTransitionSurface,
  meshOverlayControlVisible,
  meshOverlayOptions,
  viewerLayerVisibility,
} from "../meshOverlayModel.js?v=1.1.5";
import { patchBoundaryCurveIds, patchSurfaceIds, surfaceVisibleInView } from "../simulationViewModel.js?v=1.1.5";
import {
  defaultVisibleLayers,
  layerForConstructionFeature,
  layerForSurface,
  usesV11ViewerLayers,
  meshOverlayLayerForV104,
  sharedEdgeLayerForV104,
  usesV104ViewerLayers,
} from "../workspaceModel.js?v=1.1.5";

const h = React.createElement;

export function ModelViewer({
  stlUrl,
  surfaceGraph = null,
  constructionLines = {},
  viewMode,
  setViewMode,
  simulationViewMode = "cad_review_360",
  meshOverlayMode = "triangle_edges",
  setMeshOverlayMode = null,
  selectedPatch = null,
  manifest = null,
  autoRotate,
  setAutoRotate,
  visibleLayers = defaultVisibleLayers(),
}) {
  const activeMeshOverlayMode = effectiveMeshOverlayMode(simulationViewMode, meshOverlayMode);
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
  }, [viewMode, visibleLayers, simulationViewMode, activeMeshOverlayMode, selectedPatch, manifest]);

  useEffect(() => {
    const selectedBoundaryIds = patchBoundaryCurveIds(manifest, selectedPatch);
    renderConstructionLines(
      mergeConstructionLines(constructionLines, surfaceGraph, simulationViewMode, selectedBoundaryIds),
      selectedBoundaryIds,
    );
    updateVisibility();
  }, [constructionLines, surfaceGraph, simulationViewMode, selectedPatch, manifest]);

  useEffect(() => {
    if (!surfaceGraph?.surfaces?.length || !sceneRef.current) {
      return;
    }

    setStatus("Rendering surface graph...");
    clearModel();
    const visibleSurfaceGraph = filterSurfaceGraph(surfaceGraph, simulationViewMode, manifest);
    const bounds = surfaceGraphBounds(visibleSurfaceGraph);
    centerRef.current.copy(bounds.center);
    const selectedSurfaceIds = patchSurfaceIds(manifest, selectedPatch);
    const selectedBoundaryIds = patchBoundaryCurveIds(manifest, selectedPatch);
    const shaded = createSurfaceGraphGroup(
      visibleSurfaceGraph,
      bounds.center,
      simulationViewMode,
      selectedSurfaceIds,
      activeMeshOverlayMode,
      manifest,
    );
    modelRef.current.shaded = shaded;
    sceneRef.current.add(shaded);
    renderConstructionLines(
      mergeConstructionLines(constructionLines, surfaceGraph, simulationViewMode, selectedBoundaryIds),
      selectedBoundaryIds,
    );
    frameCamera(bounds.radius || 1000);
    updateVisibility();
    setStatus(simulationViewMode === "mesh" ? meshInspectionStatus(manifest) : "Surface graph rendered");
  }, [surfaceGraph, simulationViewMode, activeMeshOverlayMode, selectedPatch, manifest]);

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
        shaded.userData.layer = "shade_surfaces";

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
      const { showShadedSurfaces, showSurfaceUvWire, showMeshEdges } = viewerLayerVisibility({
        simulationViewMode,
        viewMode,
        meshOverlayMode: activeMeshOverlayMode,
        visibleLayers,
      });
      shaded.visible = showShadedSurfaces || showSurfaceUvWire || showMeshEdges;
      shaded.traverse((child) => {
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
    }
    if (constructionGroup) {
      const { showConstructionLines } = viewerLayerVisibility({
        simulationViewMode,
        viewMode,
        meshOverlayMode: activeMeshOverlayMode,
        visibleLayers,
      });
      const hasCfdBoundarySelection =
        isCfdInspectionView(simulationViewMode) && constructionGroup.userData.hasCfdBoundarySelection;
      const showConstruction = showConstructionLines || hasCfdBoundarySelection;
      constructionGroup.visible = showConstruction;
      constructionGroup.traverse((child) => {
        const showChild = showConstructionLines || (hasCfdBoundarySelection && child.userData.isCfdSelectedBoundary);
        if (child.isLineSegments && child.userData.layer) {
          child.visible = showChild && visibleLayers[child.userData.layer] !== false;
        }
        if (child.isMesh && child.userData.layer) {
          child.visible = showChild && visibleLayers[child.userData.layer] !== false;
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

  function renderConstructionLines(linesByFeature, selectedBoundaryIds = new Set()) {
    if (!sceneRef.current) {
      return;
    }
    clearConstructionGroup();
    const group = createConstructionGroup(linesByFeature || {}, centerRef.current, selectedBoundaryIds);
    addCurveControlOverlays(group, curveControlsFromManifest(manifest), centerRef.current, usesV104ViewerLayers(manifest));
    group.userData.hasCfdBoundarySelection = selectedBoundaryIds.size > 0;
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
      meshOverlayControlVisible(simulationViewMode)
        ? h(
            "label",
            { className: "mesh-overlay-control" },
            h("span", null, "Mesh overlay"),
            h(
              "select",
              {
                value: activeMeshOverlayMode,
                onChange: (event) => setMeshOverlayMode?.(event.target.value),
                disabled: !setMeshOverlayMode,
              },
              meshOverlayOptions().map((option) => h("option", { key: option.id, value: option.id }, option.label)),
            ),
          )
        : null,
    ),
    h("div", { className: "viewer-canvas", ref: containerRef }),
    h("div", { className: "viewer-status" }, status),
  );
}

export function createSurfaceGraphGroup(
  surfaceGraph,
  center,
  simulationViewMode,
  selectedSurfaceIds = new Set(),
  meshOverlayMode = "triangle_edges",
  manifest = null,
) {
  const group = new THREE.Group();
  const surfaceGraphStatus =
    surfaceGraph?.transition_geometry_status ||
    manifest?.transition_geometry_status ||
    manifest?.metadata?.transitionGeometryStatus;
  const v11SurfaceFamilyGraph = surfaceGraphStatus === "topology_first_blade_to_blade_5_loop_surface_family_graph";
  const v11ViewerLayers = usesV11ViewerLayers(manifest, surfaceGraph);
  const v104ViewerLayers = usesV104ViewerLayers(manifest, surfaceGraph);
  const colors = {
    hub: "#7aa58f",
    hub_wall: "#7aa58f",
    open_tip_reference: "#b5c7a0",
    reference_only: "#b5c7a0",
    shroud: "#9db7c5",
    tip_or_shroud_wall: "#9db7c5",
    front_shroud_inner_surface: "#9db7c5",
    blade_pressure: "#6f9b85",
    blade_suction: "#5d806f",
    blade_leading_edge_closure: "#f59e0b",
    blade_trailing_edge_closure: "#ef4444",
    blade_root_hub_closure: "#22c55e",
    blade_tip_closure: "#38bdf8",
    blade_pressure: "#6f9b85",
    blade_suction: "#5d806f",
    blade_leading_edge: "#f59e0b",
    blade_trailing_edge: "#ef4444",
    blade_root: "#ff00cc",
    blade_tip: "#38bdf8",
    hub_shell: "#7aa58f",
    hub_cap: "#8aa883",
    hub_bevel: "#f59e0b",
    mounting_bore: "#425563",
  };

  for (const surface of surfaceGraph.surfaces || []) {
    if (!surfaceVisibleInView(surface, simulationViewMode, manifest)) {
      continue;
    }
    const grid = surface.uv_grid || [];
    const hasGrid = hasRectangularSurfaceGrid(grid);
    const geometry = surfaceMeshGeometry(surface.mesh, center, grid) || (hasGrid ? surfaceGridGeometry(grid, center) : null);
    if (!geometry) {
      continue;
    }
    geometry.computeVertexNormals();
    const display = surface.display || {};
    const isEdgeClosure = surface.kind === "edge_closure_surface";
    const surfaceId = surface.id || surface.surface_graph_id;
    const isSelected = selectedSurfaceIds.has(surfaceId);
    const hasSelection = selectedSurfaceIds.size > 0;
    const priorityColor = inspectionColor(surface, isSelected);
    const material = new THREE.MeshStandardMaterial({
      color: priorityColor || display.color || colors[surface.face_family] || colors[surface.cfd_role] || colors[surface.role] || "#7aa58f",
      emissive: isSelected ? "#7c2d12" : "#000000",
      emissiveIntensity: isSelected ? 0.18 : 0,
      roughness: 0.58,
      metalness: 0.16,
      side: THREE.DoubleSide,
      transparent: true,
      opacity:
        isSelected
          ? 1.0
          : hasSelection
            ? 0.42
            : v11ViewerLayers || v11SurfaceFamilyGraph
              ? (display.opacity === undefined ? 0.62 : display.opacity)
              : defaultSurfaceOpacity(surface, display, isEdgeClosure),
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.layer = v104ViewerLayers ? "shade_surfaces" : layerForSurface(surface, cfdSurfaceMeshManifest(manifest));
    mesh.userData.surfaceId = surfaceId;
    group.add(mesh);

    if (hasGrid) {
      group.add(createSurfaceUvWireOverlay(grid, center, surface, cfdSurfaceMeshManifest(manifest), v104ViewerLayers));
    }

    if (simulationViewMode === "mesh" && meshOverlayMode !== "off") {
      const overlay = createMeshEdgeOverlay(geometry, surface, cfdSurfaceMeshManifest(manifest), v104ViewerLayers);
      group.add(overlay);
    }
  }

  if (simulationViewMode === "mesh" && meshOverlayMode !== "off") {
    const sharedEdgeGroup = createSharedEdgeGroup(surfaceGraph, center, v104ViewerLayers);
    if (sharedEdgeGroup.children.length > 0) {
      group.add(sharedEdgeGroup);
    }
  }

  return group;
}

function defaultSurfaceOpacity(surface, display, isEdgeClosure) {
  if (display.opacity !== undefined) {
    return display.opacity;
  }
  if (surface.role === "open_tip_reference" || surface.role === "reference_only") {
    return 0.3;
  }
  if (isEdgeClosure) {
    return 1.0;
  }
  return 0.92;
}

function createSurfaceUvWireOverlay(grid, center, surface, meshManifest = null, v104ViewerLayers = false) {
  const positions = [];
  for (let rowIndex = 0; rowIndex < grid.length; rowIndex += 1) {
    for (let columnIndex = 0; columnIndex < grid[rowIndex].length - 1; columnIndex += 1) {
      pushPoint(positions, grid[rowIndex][columnIndex], center);
      pushPoint(positions, grid[rowIndex][columnIndex + 1], center);
    }
  }
  const columnCount = grid[0]?.length || 0;
  for (let columnIndex = 0; columnIndex < columnCount; columnIndex += 1) {
    for (let rowIndex = 0; rowIndex < grid.length - 1; rowIndex += 1) {
      pushPoint(positions, grid[rowIndex][columnIndex], center);
      pushPoint(positions, grid[rowIndex + 1][columnIndex], center);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const display = surface.display || {};
  const line = new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({
      color: display.wire_color || surface.wireframe?.color || "#315f72",
      transparent: true,
      opacity: surface.face_family === "hub" ? 0.42 : 0.58,
      depthTest: true,
      depthWrite: false,
    }),
  );
  line.userData.isSurfaceUvWire = true;
  line.userData.layer = v104ViewerLayers ? "nurbs_uv_wire" : layerForSurface(surface, meshManifest);
  line.userData.surfaceId = surface.id || surface.surface_graph_id;
  return line;
}

function createMeshEdgeOverlay(geometry, surface, meshManifest = null, v104ViewerLayers = false) {
  const transitionSurface = isTransitionSurface(surface, meshManifest);
  const display = surface.display || {};
  const inspectionClass = display.inspection_class || "";
  const inspectionWire = ["root_to_hub_native_root_face", "tip_to_shroud_attachment", "root_to_hub_blend", "open_tip_dome"].includes(
    inspectionClass,
  );
  const isNativeRootFace = surface.kind === "native_topology_face" && surface.face_family === "blade_root";
  const material = new THREE.LineBasicMaterial({
    color:
      inspectionWire || isNativeRootFace
        ? display.wire_color || "#fff200"
        : transitionSurface
          ? "#f97316"
          : display.wire_color || "#1f2933",
    transparent: true,
    opacity: inspectionWire || isNativeRootFace || transitionSurface ? 0.92 : 0.28,
    depthTest: true,
    depthWrite: false,
  });
  const overlay = new THREE.LineSegments(new THREE.WireframeGeometry(geometry), material);
  overlay.userData.isMeshOverlay = true;
  overlay.userData.layer = v104ViewerLayers
    ? meshOverlayLayerForV104(surface)
    : inspectionWire || transitionSurface
      ? "transition_mesh_edges"
      : "mesh_edges";
  overlay.userData.surfaceId = surface.id || surface.surface_graph_id;
  return overlay;
}

function inspectionColor(surface, selected) {
  const display = surface.display || {};
  if (selected) {
    return "#f97316";
  }
  if (display.inspection_class === "root_to_hub_native_root_face") {
    return display.color || "#ff00cc";
  }
  if (display.inspection_class === "root_to_hub_blend") {
    return display.color || "#ff00cc";
  }
  if (display.inspection_class === "tip_to_shroud_attachment") {
    return display.color || "#00e5ff";
  }
  if (display.inspection_class === "open_tip_dome") {
    return display.color || "#6f8fb8";
  }
  return null;
}

function createSharedEdgeGroup(surfaceGraph, center, v104ViewerLayers = false) {
  const group = new THREE.Group();
  const facesById = new Map((surfaceGraph.surfaces || []).map((surface) => [surface.id || surface.surface_graph_id, surface]));
  const sharedEdges = surfaceGraph.topology_graph?.shared_edges || [];
  for (const shared_edge of sharedEdges) {
    const face = facesById.get(shared_edge.first_face_id);
    const points = face?.edge_samples?.[shared_edge.first_edge_role] || [];
    if (points.length < 2) {
      continue;
    }
    const positions = [];
    for (let index = 0; index < points.length - 1; index += 1) {
      pushPoint(positions, points[index], center);
      pushPoint(positions, points[index + 1], center);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    const line = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({
        color: "#fff200",
        transparent: true,
        opacity: 0.48,
        depthWrite: false,
      }),
    );
    line.userData.isMeshOverlay = true;
    if (v104ViewerLayers) {
      line.userData.layer = sharedEdgeLayerForV104(shared_edge);
    } else {
      line.userData.layer = "mesh_edges";
    }
    line.userData.sharedEdgeId = shared_edge.id;
    group.add(line);
  }
  return group;
}

function isCfdInspectionView(simulationViewMode) {
  return simulationViewMode === "cfd_full_360" || simulationViewMode === "mesh";
}

function meshInspectionStatus(manifest) {
  const meshManifest = manifest?.simulation_manifests?.cfd_surface_mesh;
  if (!meshManifest) {
    return "CFD360 mesh manifest not available.";
  }
  const meshStrategyStatus =
    meshManifest.mesh_strategy_status ||
    meshManifest.mesh_generation_status ||
    meshManifest.mesh_status ||
    meshManifest.status;
  const triangles = Number(meshManifest.triangle_count || 0);
  const degenerate = Number(meshManifest.degenerate_triangle_count || 0);
  if (meshStrategyStatus === "v1_1_loop_family_shared_boundary_uv_mesh") {
    return `CFD360 mesh inspection: ${triangles} triangles, ${degenerate} degenerate.`;
  }
  return `CFD360 mesh inspection: ${triangles} triangles, ${degenerate} degenerate.`;
}

function cfdSurfaceMeshManifest(manifest) {
  return manifest?.simulation_manifests?.cfd_surface_mesh;
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

function surfaceMeshGeometry(mesh, center, uvGrid = []) {
  const points = surfaceMeshPoints(mesh, uvGrid);
  if (points.length < 3) {
    return null;
  }

  const positions = [];
  for (const point of points) {
    pushPoint(positions, point, center);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geometry;
}

function surfaceMeshPoints(mesh, uvGrid = []) {
  if (!mesh || typeof mesh !== "object") {
    return [];
  }

  const points = [];
  const pushFace = (face) => {
    const facePoints = face?.points || face?.vertices || face?.indices || face;
    if (!Array.isArray(facePoints) || facePoints.length < 3) {
      return;
    }
    const normalized = facePoints.map((point) => meshPoint(point, mesh.vertices, uvGrid)).filter(Boolean);
    if (normalized.length < 3) {
      return;
    }
    for (let index = 1; index < normalized.length - 1; index += 1) {
      points.push(normalized[0], normalized[index], normalized[index + 1]);
    }
  };

  for (const triangle of mesh.triangles || []) {
    pushFace(triangle);
  }
  for (const quad of mesh.quads || []) {
    pushFace(quad);
  }
  for (const face of mesh.faces || []) {
    pushFace(face);
  }
  if (Array.isArray(mesh.indices)) {
    for (let index = 0; index < mesh.indices.length - 2; index += 3) {
      pushFace([mesh.indices[index], mesh.indices[index + 1], mesh.indices[index + 2]]);
    }
  }

  return points;
}

function meshPoint(point, vertices = [], uvGrid = []) {
  if (Number.isInteger(point) && Array.isArray(vertices)) {
    return meshPoint(vertices[point], [], uvGrid);
  }
  if (Array.isArray(point) && point.length >= 3) {
    const x = Number(point[0]);
    const y = Number(point[1]);
    const z = Number(point[2]);
    if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
      return [x, y, z];
    }
  }
  if (
    Array.isArray(point) &&
    point.length >= 2 &&
    Number.isInteger(point[0]) &&
    Number.isInteger(point[1]) &&
    hasRectangularSurfaceGrid(uvGrid) &&
    uvGrid[point[0]]?.[point[1]]
  ) {
    return meshPoint(uvGrid[point[0]][point[1]], [], []);
  }
  const x = Number(Array.isArray(point) ? point[0] : point?.x);
  const y = Number(Array.isArray(point) ? point[1] : point?.y);
  const z = Number(Array.isArray(point) ? point[2] : point?.z);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
    return null;
  }
  return [x, y, z];
}

function hasRectangularSurfaceGrid(grid) {
  if (!Array.isArray(grid) || grid.length < 2 || !Array.isArray(grid[0]) || grid[0].length < 2) {
    return false;
  }
  const columnCount = grid[0].length;
  return grid.every((row) => Array.isArray(row) && row.length === columnCount);
}

function filterSurfaceGraph(surfaceGraph, simulationViewMode, manifest) {
  return {
    ...(surfaceGraph || {}),
    surfaces: (surfaceGraph?.surfaces || []).filter((surface) => surfaceVisibleInView(surface, simulationViewMode, manifest)),
  };
}

export function surfaceGraphBounds(surfaceGraph) {
  const box = new THREE.Box3();
  let hasPoint = false;

  for (const surface of surfaceGraph.surfaces || []) {
    for (const row of hasRectangularSurfaceGrid(surface.uv_grid) ? surface.uv_grid : []) {
      for (const point of row) {
        box.expandByPoint(new THREE.Vector3(point[0], point[1], point[2]));
        hasPoint = true;
      }
    }
    for (const point of surfaceMeshPoints(surface.mesh, surface.uv_grid || [])) {
      box.expandByPoint(new THREE.Vector3(point[0], point[1], point[2]));
      hasPoint = true;
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

function createConstructionGroup(linesByFeature, center, selectedBoundaryIds = new Set()) {
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
      const isSelectedBoundary = selectedBoundaryIds.has(line.name);
      const material = new THREE.LineBasicMaterial({
        color: isSelectedBoundary ? "#f97316" : line.color || colors[feature] || "#1d2a32",
        transparent: true,
        opacity: isSelectedBoundary ? 1.0 : feature === "blade_boundaries" || feature === "blade_edges" || feature === "named_boundary_curve" ? 1.0 : feature === "blade_u" || feature === "blade_v" || feature === "blade" || feature === "surface_uv" ? 0.82 : 0.72,
      });
      const lineSegments = new THREE.LineSegments(geometry, material);
      lineSegments.userData.layer = layerForConstructionFeature(feature);
      lineSegments.userData.isCfdSelectedBoundary = isSelectedBoundary;
      group.add(lineSegments);
    }
  }

  return group;
}

function addCurveControlOverlays(group, curveControls, center, v104ViewerLayers = false) {
  for (const [curveId, curve] of Object.entries(curveControls || {})) {
    if (curve.segments) {
      for (const [segmentId, segment] of orderedSegmentEntries(curve.segments)) {
        addCurveControlPolyline(group, segment.control_points || [], center, `${curveId}:${segmentId}`, "#ff00cc", v104ViewerLayers);
        for (const point of segment.control_points || []) {
          group.add(makeControlPointMarker(point, center, `${curveId}:${segmentId}`, v104ViewerLayers));
        }
      }
      continue;
    }

    addCurveControlPolyline(group, curve.sampled_points || curve.control_points || [], center, curveId, "#1f6f66", v104ViewerLayers);
    addCurveControlPolyline(group, curve.control_points || [], center, curveId, "#ff00cc", v104ViewerLayers);
    for (const point of curve.control_points || []) {
      group.add(makeControlPointMarker(point, center, curveId, v104ViewerLayers));
    }
  }
}

function addCurveControlPolyline(group, points, center, curveId, color = "#ff00cc", v104ViewerLayers = false) {
  if (!Array.isArray(points) || points.length < 2) {
    return;
  }
  const positions = [];
  for (let index = 0; index < points.length - 1; index += 1) {
    pushPoint(positions, curveControlPoint3d(points[index]), center);
    pushPoint(positions, curveControlPoint3d(points[index + 1]), center);
  }
  if (!positions.length) {
    return;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const line = new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.92,
      depthWrite: false,
    }),
  );
  line.userData.layer = v104ViewerLayers ? "control_curves" : "blade_boundaries";
  line.userData.curveControlId = curveId;
  group.add(line);
}

function makeControlPointMarker(point, center, curveId, v104ViewerLayers = false) {
  const vector = curveControlPoint3d(point);
  const geometry = new THREE.SphereGeometry(5, 12, 8);
  const material = new THREE.MeshStandardMaterial({
    color: "#fff200",
    emissive: "#ff00cc",
    emissiveIntensity: 0.18,
    roughness: 0.42,
    metalness: 0.05,
  });
  const marker = new THREE.Mesh(geometry, material);
  marker.position.set(vector[0] - center.x, vector[1] - center.y, vector[2] - center.z);
  marker.userData.layer = v104ViewerLayers ? "control_points" : "blade_boundaries";
  marker.userData.curveControlId = curveId;
  return marker;
}

function curveControlPoint3d(point) {
  if (Array.isArray(point) && point.length >= 3) {
    return [Number(point[0]) || 0, Number(point[1]) || 0, Number(point[2]) || 0];
  }
  return [Number(point?.[0]) || 0, 0, Number(point?.[1]) || 0];
}

function orderedSegmentEntries(segments = {}) {
  const order = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"];
  const knownEntries = order.filter((segmentId) => segments[segmentId]).map((segmentId) => [segmentId, segments[segmentId]]);
  const extraEntries = Object.entries(segments).filter(([segmentId]) => !order.includes(segmentId));
  return [...knownEntries, ...extraEntries];
}

function curveControlsFromManifest(manifest) {
  return manifest?.curve_controls || manifest?.geometry?.curve_controls || {};
}

function mergeConstructionLines(constructionLines, surfaceGraph, simulationViewMode = "cad_review_360", selectedBoundaryIds = new Set()) {
  const merged = isCfdInspectionView(simulationViewMode) ? {} : { ...(constructionLines || {}) };
  const namedBoundaryCurves = surfaceGraph?.named_boundary_curves || [];
  const visibleBoundaryCurves =
    isCfdInspectionView(simulationViewMode) && selectedBoundaryIds.size > 0
      ? namedBoundaryCurves.filter((curve) => selectedBoundaryIds.has(curve.id))
      : namedBoundaryCurves;
  const shouldEmitBoundaryCurves =
    visibleBoundaryCurves.length > 0 &&
    (!isCfdInspectionView(simulationViewMode) || selectedBoundaryIds.size > 0);
  if (shouldEmitBoundaryCurves) {
    merged.named_boundary_curve = visibleBoundaryCurves.map((curve) => ({
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

export function disposeObject(object) {
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
