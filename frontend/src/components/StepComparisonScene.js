import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

import {
  heatmapTriangleSelection,
  inspectionPolylinePoints,
} from "../stepReconstructionModel.js?v=1.1.6-r13_2";

const h = React.createElement;
const defaultRuntime = { THREE, OrbitControls, STLLoader };

export function StepComparisonScene({ artifactUrls, inspection, overlays, semanticRegion, semanticRegionAliases, onHeatmapReadout, onRegionFilterStatus, runtime = defaultRuntime }) {
  const containerRef = useRef(null);
  const sourcePaneRef = useRef(null);
  const reconstructionPaneRef = useRef(null);
  const heatmapPaneRef = useRef(null);
  const sessionRef = useRef(null);
  const latestRef = useRef(null);
  const [status, setStatus] = useState("Waiting for a completed reconstruction audit.");
  const [heatmapLegend, setHeatmapLegend] = useState(null);
  latestRef.current = {
    inspection,
    overlays,
    semanticRegion,
    semanticRegionAliases,
    onHeatmapReadout,
    onRegionFilterStatus,
  };

  useEffect(() => {
    if (!artifactUrls?.source || !artifactUrls?.reconstruction || !artifactUrls?.heatmap) return undefined;
    const container = containerRef.current;
    if (!container) return undefined;
    const { THREE: Three, OrbitControls: Controls, STLLoader: Loader } = runtime;
    const paneElements = { source: sourcePaneRef.current, reconstruction: reconstructionPaneRef.current, heatmap: heatmapPaneRef.current };
    const renderers = Object.fromEntries(Object.entries(paneElements).map(([sceneId, pane]) => {
      const renderer = new Three.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setPixelRatio(Math.max(1, Math.min(window.devicePixelRatio || 1, 2.5)));
      renderer.outputColorSpace = Three.SRGBColorSpace;
      pane.appendChild(renderer.domElement);
      return [sceneId, renderer];
    }));
    const scenes = { source: comparisonScene(Three), reconstruction: comparisonScene(Three), heatmap: comparisonScene(Three) };
    const cameras = Object.fromEntries(Object.keys(scenes).map((sceneId) => {
      const paneCamera = new Three.PerspectiveCamera(38, 1, 0.01, 100000);
      paneCamera.position.set(120, -160, 95);
      return [sceneId, paneCamera];
    }));
    const controls = new Controls(cameras.source, renderers.source.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    const paneBounds = Object.fromEntries(Object.keys(scenes).map((sceneId) => [sceneId, new Three.Box3()]));
    const raycaster = new Three.Raycaster();
    let heatmapMesh = null;
    let heatmapBase = null;
    let heatmapFilterData = null;
    const overlayGroups = { source: null, reconstruction: null };
    const paneStates = { source: "loading", reconstruction: "loading", heatmap: "loading" };
    const paneErrors = { source: null, reconstruction: null, heatmap: null };
    const fetchController = new AbortController();
    let disposed = false;
    let frameId = 0;
    setHeatmapLegend(null);
    setStatus("Loaded 0 of 3 comparison panes");

    const updateLoadStatus = () => {
      const failures = Object.entries(paneErrors).filter(([, error]) => error);
      if (failures.length) {
        setStatus(failures.map(([pane, error]) => `${pane}: ${error}`).join(" | "));
        return;
      }
      const loaded = Object.values(paneStates).filter((state) => state === "loaded").length;
      setStatus(loaded >= 3
        ? "Source, reconstruction and deviation heatmap loaded"
        : `Loaded ${loaded} of 3 comparison panes`);
    };

    const markLoadError = (sceneId, error) => {
      paneStates[sceneId] = "failed";
      paneErrors[sceneId] = error?.message || String(error || `${sceneId} failed to load`);
      updateLoadStatus();
    };

    const registerObject = (sceneId, object, markLoaded = true) => {
      scenes[sceneId].add(object);
      paneBounds[sceneId].expandByObject(object);
      frameComparisonCamera(Three, cameras[sceneId], sceneId === "source" ? controls : null, paneBounds[sceneId]);
      if (markLoaded) {
        paneStates[sceneId] = "loaded";
        paneErrors[sceneId] = null;
        updateLoadStatus();
      }
    };

    const replaceOverlays = () => {
      for (const pane of ["source", "reconstruction"]) {
        if (overlayGroups[pane]) {
          scenes[pane].remove(overlayGroups[pane]);
          disposeScene(overlayGroups[pane]);
        }
        const group = new Three.Group();
        group.userData.overlayKind = "inspection-overlays";
        const current = latestRef.current || {};
        addInspectionOverlays(
          Three,
          group,
          current.inspection,
          current.overlays,
          pane,
        );
        overlayGroups[pane] = group;
        scenes[pane].add(group);
      }
    };

    const replaceHeatmap = (payload = null) => {
      if (disposed) return;
      const isNewArtifact = Array.isArray(payload?.vertices);
      if (isNewArtifact) heatmapFilterData = heatmapFilterPayload(payload);
      if (!heatmapFilterData) return;
      const current = latestRef.current || {};
      const selection = heatmapTriangleSelection(
        heatmapFilterData,
        current.semanticRegion,
        current.semanticRegionAliases,
      );
      if (isNewArtifact) {
        if (heatmapMesh) {
          scenes.heatmap.remove(heatmapMesh);
          disposeScene(heatmapMesh);
        }
        heatmapMesh = heatmapObject(Three, payload, selection.indexes);
        registerObject("heatmap", heatmapMesh);
        setHeatmapLegend(payload?.legend || null);
      } else if (heatmapMesh) {
        applyHeatmapSelection(
          heatmapMesh.geometry,
          heatmapFilterData.triangles,
          selection.indexes,
        );
      }
      current.onRegionFilterStatus?.(selection);
    };

    sessionRef.current = { replaceOverlays, replaceHeatmap };
    replaceOverlays();

    const loader = new Loader();
    const loadStl = (sceneId, url, failureMessage) => {
      fetch(url, { signal: fetchController.signal })
        .then((response) => {
          if (!response.ok) throw new Error(`${response.status} ${failureMessage}`);
          return response.arrayBuffer();
        })
        .then((buffer) => {
          if (disposed || fetchController.signal.aborted) return;
          const geometry = loader.parse(buffer);
          if (disposed) return geometry.dispose();
          registerObject(sceneId, neutralMesh(Three, geometry));
        })
        .catch((error) => {
          if (disposed || error?.name === "AbortError") return;
          markLoadError(sceneId, error || new Error(failureMessage));
        });
    };
    loadStl("source", artifactUrls.source, "Source STL failed to load");
    if (artifactUrls.geometricManifest) {
      fetch(artifactUrls.geometricManifest, { signal: fetchController.signal })
        .then((response) => {
          if (!response.ok) throw new Error(`${response.status} Geometric Manifest failed to load`);
          return response.json();
        })
        .then((payload) => {
          if (disposed) return;
          registerObject("reconstruction", geometricManifestObject(Three, payload));
          if (heatmapBase) {
            scenes.heatmap.remove(heatmapBase);
            disposeScene(heatmapBase);
          }
          heatmapBase = geometricManifestObject(Three, payload, {
            mode: "heatmap-neutral-base",
          });
          registerObject("heatmap", heatmapBase, false);
        })
        .catch((error) => {
          if (disposed || error?.name === "AbortError") return;
          markLoadError("reconstruction", error);
        });
    } else {
      loadStl("reconstruction", artifactUrls.reconstruction, "Reconstruction STL failed to load");
    }
    fetch(artifactUrls.heatmap, { signal: fetchController.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} heatmap failed to load`);
        return response.json();
      })
      .then((payload) => {
        if (disposed) return;
        replaceHeatmap(payload);
      })
      .catch((error) => {
        if (disposed || error?.name === "AbortError") return;
        markLoadError("heatmap", error);
      });

    const resize = () => Object.entries(renderers).forEach(([sceneId, renderer]) => {
      const pane = paneElements[sceneId];
      renderer.setSize(Math.max(pane.clientWidth, 320), Math.max(pane.clientHeight, 260), true);
    });
    const observer = new ResizeObserver(resize);
    Object.values(paneElements).forEach((pane) => observer.observe(pane));
    resize();

    const animate = () => {
      frameId = window.requestAnimationFrame(animate);
      controls.update();
      synchronizeComparisonCameras(Three, cameras, paneBounds, controls.target);
      for (const sceneId of ["source", "reconstruction", "heatmap"]) {
        const renderer = renderers[sceneId];
        const width = renderer.domElement.clientWidth;
        const height = renderer.domElement.clientHeight;
        if (!width || !height) continue;
        const camera = cameras[sceneId];
        camera.aspect = width / Math.max(height, 1);
        camera.updateProjectionMatrix();
        renderer.render(scenes[sceneId], camera);
      }
    };
    animate();

    const pointerMove = (event) => {
      const readout = latestRef.current?.onHeatmapReadout;
      if (!heatmapMesh || !readout) return;
      const canvasRect = renderers.heatmap.domElement.getBoundingClientRect();
      const pointer = new Three.Vector2(
        ((event.clientX - canvasRect.left) / canvasRect.width) * 2 - 1,
        ((canvasRect.bottom - event.clientY) / canvasRect.height) * 2 - 1,
      );
      raycaster.setFromCamera(pointer, cameras.heatmap);
      const hit = raycaster.intersectObject(heatmapMesh, false)[0];
      if (!hit?.face) return;
      const errors = heatmapMesh.geometry.getAttribute("errorMm");
      const error = interpolateFaceAttribute(Three, heatmapMesh, hit, errors);
      readout({ error_mm: error, point_mm: hit.point.toArray() });
    };
    renderers.heatmap.domElement.addEventListener("pointermove", pointerMove);

    return () => {
      disposed = true;
      fetchController.abort();
      if (sessionRef.current?.replaceHeatmap === replaceHeatmap) sessionRef.current = null;
      window.cancelAnimationFrame(frameId);
      observer.disconnect();
      renderers.heatmap.domElement.removeEventListener("pointermove", pointerMove);
      controls.dispose();
      Object.values(scenes).forEach(disposeScene);
      Object.entries(renderers).forEach(([sceneId, renderer]) => {
        renderer.renderLists.dispose();
        renderer.dispose();
        renderer.forceContextLoss();
        const pane = paneElements[sceneId];
        if (renderer.domElement.parentNode === pane) pane.removeChild(renderer.domElement);
      });
    };
  }, [artifactUrls?.source, artifactUrls?.reconstruction, artifactUrls?.heatmap, artifactUrls?.geometricManifest, runtime]);

  useEffect(() => {
    sessionRef.current?.replaceOverlays();
  }, [inspection, overlays]);

  useEffect(() => {
    sessionRef.current?.replaceHeatmap();
  }, [semanticRegion, semanticRegionAliases]);

  return h("div", { className: "step-comparison-scene", ref: containerRef, "data-testid": "step-comparison-scene" },
    h("div", { className: "comparison-pane source", ref: sourcePaneRef }, h("span", { className: "comparison-pane-label" }, "SOURCE STEP")),
    h("div", { className: "comparison-pane reconstruction", ref: reconstructionPaneRef }, h("span", { className: "comparison-pane-label" }, `${inspection?.reconstructionVariant || "V1.1.2"} RECONSTRUCTION`)),
    h("div", { className: "comparison-pane heatmap", ref: heatmapPaneRef },
      h("span", { className: "comparison-pane-label" }, "DEVIATION HEATMAP"),
      h(HeatmapColorBar, { legend: heatmapLegend }),
    ),
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
  return new Three.Mesh(geometry, new Three.MeshStandardMaterial({ color: "#e8ecea", roughness: 0.72, metalness: 0.05, side: Three.DoubleSide }));
}

export function geometricManifestObject(Three, payload, options = {}) {
  const group = new Three.Group();
  const neutralBase = options.mode === "heatmap-neutral-base";
  group.userData.overlayKind = neutralBase
    ? "heatmap-neutral-base"
    : "geometric-manifest";
  const surfaces = Array.isArray(payload?.surfaces) ? payload.surfaces : [];
  for (const surface of surfaces) {
    const grid = rectangularUvGrid(surface?.uv_grid);
    if (!grid) continue;
    const rows = grid.length;
    const columns = grid[0].length;
    const points = grid.flat();
    const geometry = new Three.BufferGeometry();
    geometry.setAttribute("position", new Three.Float32BufferAttribute(points.flat(), 3));
    const indices = [];
    for (let row = 0; row < rows - 1; row += 1) {
      for (let column = 0; column < columns - 1; column += 1) {
        const a = row * columns + column;
        const b = a + 1;
        const c = (row + 1) * columns + column;
        const d = c + 1;
        indices.push(a, c, b, b, c, d);
      }
    }
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const color = neutralBase
      ? "#d9dddb"
      : surface?.display?.color || manifestSurfaceColor(surface?.role);
    if (!neutralBase) {
      const depthMesh = new Three.Mesh(geometry.clone(), new Three.MeshBasicMaterial({
        colorWrite: false,
        depthWrite: true,
        depthTest: true,
        side: Three.DoubleSide,
      }));
      depthMesh.userData = {
        overlayKind: "geometric-manifest-depth",
        surfaceId: surface?.id,
        surfaceRole: surface?.role,
      };
      depthMesh.renderOrder = 0;
      group.add(depthMesh);
    }
    const mesh = new Three.Mesh(geometry, new Three.MeshStandardMaterial({
      color,
      roughness: 0.72,
      metalness: 0.02,
      transparent: !neutralBase,
      opacity: neutralBase ? 1.0 : 0.42,
      depthWrite: neutralBase,
      depthTest: true,
      side: Three.DoubleSide,
    }));
    mesh.renderOrder = neutralBase ? 0 : 1;
    mesh.userData = {
      overlayKind: neutralBase
        ? "heatmap-neutral-surface"
        : "geometric-manifest-surface",
      surfaceId: surface?.id,
      surfaceRole: surface?.role,
      comparisonDisposition: surface?.comparison?.disposition || null,
    };
    group.add(mesh);
    if (!neutralBase) {
      const wireMaterial = new Three.LineBasicMaterial({ color: surface?.display?.wire_color || "#263d37", transparent: true, opacity: 0.72, depthTest: true });
      const wires = manifestUvSegments(Three, grid, wireMaterial, surface);
      wires.renderOrder = 2;
      group.add(wires);
    }
  }
  if (!group.children.length) throw new Error("Geometric Manifest contains no renderable UV surfaces");
  return group;
}

function rectangularUvGrid(value) {
  if (!Array.isArray(value) || value.length < 2) return null;
  const columns = Array.isArray(value[0]) ? value[0].length : 0;
  if (columns < 2) return null;
  const grid = value.map((row) => Array.isArray(row) ? row.filter(validManifestPoint).map((point) => point.slice(0, 3).map(Number)) : []);
  return grid.every((row) => row.length === columns) ? grid : null;
}

function validManifestPoint(point) {
  return Array.isArray(point) && point.length >= 3 && point.slice(0, 3).every((value) => Number.isFinite(Number(value)));
}

function manifestUvSegments(Three, grid, material, surface) {
  const segmentPoints = [];
  for (const row of grid) {
    for (let index = 0; index < row.length - 1; index += 1) {
      segmentPoints.push(new Three.Vector3(...row[index]), new Three.Vector3(...row[index + 1]));
    }
  }
  for (let column = 0; column < grid[0].length; column += 1) {
    for (let row = 0; row < grid.length - 1; row += 1) {
      segmentPoints.push(
        new Three.Vector3(...grid[row][column]),
        new Three.Vector3(...grid[row + 1][column]),
      );
    }
  }
  const lines = new Three.LineSegments(
    new Three.BufferGeometry().setFromPoints(segmentPoints),
    material,
  );
  lines.userData = { overlayKind: "geometric-manifest-uv", surfaceId: surface?.id, surfaceRole: surface?.role };
  return lines;
}

function manifestSurfaceColor(role) {
  if (["blade_pressure", "blade_suction", "hub_support", "shroud_support"].includes(role)) return "#759b7d";
  return "#e0b33e";
}

function HeatmapColorBar({ legend }) {
  if (!legend) return null;
  const values = [
    ["MIN", legend.minimum_mm],
    ["COLOR MAX (P95)", legend.clip_p95_mm ?? legend.p95_mm],
  ].filter(([, value]) => Number.isFinite(Number(value)));
  if (!values.length) return null;
  return h("div", { className: "heatmap-colorbar", "data-testid": "heatmap-colorbar" },
    h("div", { className: "heatmap-colorbar-gradient" }),
    h("div", { className: "heatmap-colorbar-values" },
      values.map(([label, value]) => h("span", { key: label }, `${label} ${Number(value).toFixed(3)} mm`)),
    ),
    Number.isFinite(Number(legend.maximum_mm))
      ? h("span", { className: "heatmap-colorbar-clipped-max" }, `DATA MAX ${Number(legend.maximum_mm).toFixed(3)} mm (clipped)`)
      : null,
  );
}

function heatmapObject(Three, payload, included) {
  const positions = Array.isArray(payload?.vertices) ? payload.vertices : [];
  const colors = Array.isArray(payload?.colors_rgb) ? payload.colors_rgb : [];
  const errors = Array.isArray(payload?.errors_mm) ? payload.errors_mm : [];
  const triangles = Array.isArray(payload?.triangles) ? payload.triangles : [];
  const geometry = new Three.BufferGeometry();
  geometry.setAttribute("position", new Three.Float32BufferAttribute(positions.flat(), 3));
  const linearColors = colors.flatMap((rgb) => {
    const color = new Three.Color().setRGB(
      Number(rgb?.[0]) || 0,
      Number(rgb?.[1]) || 0,
      Number(rgb?.[2]) || 0,
      Three.SRGBColorSpace,
    );
    return color.toArray();
  });
  geometry.setAttribute("color", new Three.Float32BufferAttribute(linearColors, 3));
  geometry.setAttribute("errorMm", new Three.Float32BufferAttribute(errors, 1));
  const fullIndexes = triangles.flatMap(triangleVertexIndexes);
  const IndexArray = positions.length > 65535 ? Uint32Array : Uint16Array;
  const indexAttribute = new Three.BufferAttribute(new IndexArray(fullIndexes.length), 1);
  indexAttribute.setUsage(Three.DynamicDrawUsage);
  geometry.setIndex(indexAttribute);
  applyHeatmapSelection(geometry, triangles, included);
  return new Three.Mesh(geometry, new Three.MeshBasicMaterial({
    vertexColors: true,
    side: Three.DoubleSide,
    toneMapped: false,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1,
  }));
}

function applyHeatmapSelection(geometry, triangles, included) {
  const indexes = included.flatMap((index) => triangleVertexIndexes(triangles[index]));
  const attribute = geometry.getIndex();
  if (!attribute || indexes.length > attribute.array.length) {
    throw new Error("Heatmap selection exceeds the immutable index capacity");
  }
  attribute.array.set(indexes, 0);
  attribute.clearUpdateRanges?.();
  attribute.addUpdateRange?.(0, indexes.length);
  attribute.needsUpdate = true;
  geometry.setDrawRange(0, indexes.length);
}

function triangleVertexIndexes(triangle) {
  if (Array.isArray(triangle)) return triangle.filter(validTriangleIndex);
  if (!triangle || typeof triangle !== "object") return [];
  const indexes = triangle.vertex_indices || triangle.indices || triangle.vertices || [];
  return Array.isArray(indexes) ? indexes.filter(validTriangleIndex) : [];
}

function heatmapFilterPayload(payload) {
  const keys = [
    "triangles",
    "triangle_source_region_ids",
    "triangle_region_ids",
    "triangle_regions",
    "triangle_metadata",
    "regions",
    "regional_records",
    "semantic_regions",
  ];
  return Object.fromEntries(
    keys.filter((key) => payload?.[key] !== undefined).map((key) => [key, payload[key]]),
  );
}

function validTriangleIndex(value) {
  return Number.isInteger(value) && value >= 0;
}

function interpolateFaceAttribute(Three, mesh, hit, attribute) {
  if (!hit?.face || !attribute) return null;
  const barycentric = hit.barycoord?.clone?.() || new Three.Vector3();
  if (!hit.barycoord) {
    const positions = mesh.geometry.getAttribute("position");
    const first = new Three.Vector3().fromBufferAttribute(positions, hit.face.a);
    const second = new Three.Vector3().fromBufferAttribute(positions, hit.face.b);
    const third = new Three.Vector3().fromBufferAttribute(positions, hit.face.c);
    Three.Triangle.getBarycoord(hit.point, first, second, third, barycentric);
  }
  return (
    barycentric.x * attribute.getX(hit.face.a)
    + barycentric.y * attribute.getX(hit.face.b)
    + barycentric.z * attribute.getX(hit.face.c)
  );
}

function addInspectionOverlays(Three, scene, inspection, overlays, pane) {
  if (!inspection) return;
  if (overlays?.axis && inspection.axis) scene.add(axisOverlay(Three, inspection.axis));
  if (pane === "source") {
    if (overlays?.selectedLoop) addPointEvidence(Three, scene, inspection.selectedLoop, "#a92525", "source-loop-evidence");
    return;
  }
  if (pane !== "reconstruction") return;
  if (overlays?.hub) addRzEvidence(Three, scene, inspection.supportGeometry?.hub, "#b4512a", false);
  if (overlays?.tipSupport && inspection.hasMaterialShroud) {
    inspection.supportGeometry?.closedShroud?.forEach((profile, index) => addShroudMaterial(Three, scene, profile, index));
  } else if (overlays?.openTipReference && !inspection.hasMaterialShroud) {
    addRzEvidence(Three, scene, inspection.supportGeometry?.openTip, "#52635e", true, "open-tip-reference");
  }
  if (overlays?.spanSurfaces) addSpanSurfaces(Three, scene, inspection.stations);
  if (overlays?.representativeBlade) {
    addRepresentativeEvidence(
      Three,
      scene,
      inspection.representative,
      inspection.comparisonPhaseDeg,
    );
  }
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
  shroud.rotation.x = Math.PI / 2;
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
      surface.rotation.x = Math.PI / 2;
      surface.userData.overlayKind = "span-surface-evidence";
      surface.userData.latticeKind = "active-blade-lattice";
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
    surface.userData.latticeKind = "active-blade-lattice";
    surface.userData.stationId = station.id;
    scene.add(surface);
  }
}

function addRepresentativeEvidence(Three, scene, representative, phaseDeg = 0) {
  const loops = Array.isArray(representative?.section_loops) ? representative.section_loops : [];
  if (loops.length) {
    loops.forEach((loop) => {
      const line = addPointEvidence(Three, scene, loop, "#005ea8", "representative-blade-evidence");
      applyPeriodicPhase(line, phaseDeg);
    });
    return;
  }
  const line = addPointEvidence(Three, scene, representative, "#005ea8", "representative-blade-evidence");
  applyPeriodicPhase(line, phaseDeg);
}

function addPointEvidence(Three, scene, evidence, color, overlayKind) {
  const points = pointTable(evidence);
  if (points.length < 2) return null;
  const line = new Three.Line(new Three.BufferGeometry().setFromPoints(points.map((point) => vectorFrom(Three, point))), new Three.LineBasicMaterial({ color }));
  line.userData.overlayKind = overlayKind;
  scene.add(line);
  return line;
}

function applyPeriodicPhase(object, phaseDeg) {
  if (!object || !Number.isFinite(Number(phaseDeg))) return;
  object.rotation.z = Number(phaseDeg) * Math.PI / 180;
  object.userData.periodicPhaseAppliedDeg = Number(phaseDeg);
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
  camera.lookAt(sphere.center);
  camera.updateProjectionMatrix();
  if (controls) {
    controls.target.copy(sphere.center);
    controls.update();
  }
}

export function synchronizeComparisonCameras(Three, cameras, paneBounds, sourceTarget) {
  const sourceSphere = new Three.Sphere();
  paneBounds.source.getBoundingSphere(sourceSphere);
  if (!Number.isFinite(sourceSphere.radius) || sourceSphere.radius <= 0) return;
  for (const sceneId of ["reconstruction", "heatmap"]) {
    const camera = cameras[sceneId];
    camera.position.copy(cameras.source.position);
    camera.up.copy(cameras.source.up);
    camera.near = cameras.source.near;
    camera.far = cameras.source.far;
    camera.zoom = cameras.source.zoom;
    camera.lookAt(sourceTarget);
    camera.updateProjectionMatrix();
  }
}

function disposeScene(scene) {
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose());
    else object.material?.dispose?.();
  });
}
