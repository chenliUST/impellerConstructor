import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

import { createRendererLifecycleRegistry } from "../inspectionSceneModel.js";

const root = resolve(import.meta.dirname, "..", "..");
const scenePath = resolve(root, "src/components/BladeFeatureScene.js");

async function loadSceneHelpers() {
  globalThis.__bladeFeatureSceneTestRuntime = {
    React: { createElement: () => null },
    useEffect: () => undefined,
    useMemo: (factory) => factory(),
    useRef: (value) => ({ current: value }),
    useState: (value) => [typeof value === "function" ? value() : value, () => undefined],
    THREE: createThreeHarness(),
    OrbitControls: class {},
    inspectionRendererLifecycle: createRendererLifecycleRegistry(),
    createSurfaceGraphGroup: () => new globalThis.__bladeFeatureSceneTestRuntime.THREE.Group(),
    disposeObject,
    surfaceGraphBounds: () => ({ center: { x: 0, y: 0, z: 0 }, radius: 100 }),
  };
  const source = readFileSync(scenePath, "utf-8")
    .replace(
      /import React, \{[^}]+\} from "react";/,
      "const { React, useEffect, useMemo, useRef, useState } = globalThis.__bladeFeatureSceneTestRuntime;",
    )
    .replace('import * as THREE from "three";', "const { THREE } = globalThis.__bladeFeatureSceneTestRuntime;")
    .replace(
      'import { OrbitControls } from "three/addons/controls/OrbitControls.js";',
      "const { OrbitControls } = globalThis.__bladeFeatureSceneTestRuntime;",
    )
    .replace(
      'import { inspectionRendererLifecycle } from "../inspectionSceneModel.js?v=1.1.5";',
      "const { inspectionRendererLifecycle } = globalThis.__bladeFeatureSceneTestRuntime;",
    )
    .replace(
      'import { createSurfaceGraphGroup, disposeObject, surfaceGraphBounds } from "./ModelViewer.js?v=1.1.5";',
      "const { createSurfaceGraphGroup, disposeObject, surfaceGraphBounds } = globalThis.__bladeFeatureSceneTestRuntime;",
    );
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}#${Date.now()}`);
}

describe("BladeFeatureScene behavior", () => {
  test("keeps only the selected blade context and preserves the stable empty surface-id value", async () => {
    const {
      EMPTY_BLADE_SURFACE_IDS,
      bladeContextSurfaceGraph,
      bladeFeatureCameraDistance,
      normalizeBladeSurfaceIds,
    } = await loadSceneHelpers();
    const graph = {
      surfaces: [
        { id: "blade_0_pressure" },
        { id: "blade_0_root_attachment" },
        { id: "blade_1_pressure" },
      ],
    };

    assert.deepEqual(
      bladeContextSurfaceGraph(graph, ["blade_0_pressure", "blade_0_root_attachment"]).surfaces.map((surface) => surface.id),
      ["blade_0_pressure", "blade_0_root_attachment"],
    );
    assert.equal(normalizeBladeSurfaceIds(), EMPTY_BLADE_SURFACE_IDS);
    assert.equal(normalizeBladeSurfaceIds([]), EMPTY_BLADE_SURFACE_IDS);
    assert.deepEqual(normalizeBladeSurfaceIds(["blade_0_pressure", "blade_0_pressure"]), ["blade_0_pressure"]);
    assert.ok(Math.abs(bladeFeatureCameraDistance(100, 400, 400) - 220) < 1e-9);
    assert.ok(Math.abs(bladeFeatureCameraDistance(100, 100, 400) - 880) < 1e-9);
  });

  test("builds red geometry only from model XYZ primitives", async () => {
    const { bladeFeatureGeometryStatus, createEngineeringFeatureGroup } = await loadSceneHelpers();
    const features = [
      { id: "curve", kind: "nurbs_curve", coordinate_system: "model_xyz", control_points: [[0, 0, 0], [10, 0, 0]] },
      { id: "polyline", kind: "polyline", coordinate_system: "model_xyz", points: [[0, 1, 0], [10, 1, 0]] },
      { id: "control", kind: "control_point", coordinate_system: "model_xyz", coordinates: [2, 3, 4] },
      { id: "point", kind: "point", coordinate_system: "model_xyz", coordinates: [4, 3, 2] },
      { id: "thickness-frame", kind: "local_frame", coordinate_system: "s_q_mm", origin: [1, 1], s_axis: [1, 0], q_axis: [0, 1] },
      { id: "s-q-point", kind: "point", coordinate_system: "s_q_mm", coordinates: [4, 3] },
      { id: "axis", kind: "reference_axis", coordinate_system: "model_xyz", origin: [0, 0, 0], direction: [0, 0, 1] },
      { id: "invalid", kind: "local_frame", coordinate_system: "s_q_mm", origin: [0, 0], s_axis: [Number.NaN, 0], q_axis: [0, 1] },
    ];
    const group = createEngineeringFeatureGroup(
      features,
      { x: 0, y: 0, z: 0 },
      20,
    );
    const lines = group.children.filter((child) => child.isLine);
    const points = group.children.filter((child) => child.isPoints);

    assert.equal(group.userData.isEngineeringFeature, true);
    assert.equal(lines.length, 3);
    assert.equal(points.length, 2);
    assert.equal(lines.every((line) => line.material.color.value === "#c40000"), true);
    assert.equal(points.every((point) => point.material.color.value === "#c40000"), true);
    assert.equal(lines.every((line) => line.material.depthTest === false), true);
    assert.equal(points.every((point) => point.material.depthTest === false), true);
    assert.equal(group.children.some((child) => child.userData.featureId === "thickness-frame"), false);
    assert.equal(group.children.some((child) => child.userData.featureId === "s-q-point"), false);
    assert.equal(group.children.some((child) => child.userData.featureId === "invalid"), false);
    assert.equal(bladeFeatureGeometryStatus({ features }), "available");
    assert.equal(
      bladeFeatureGeometryStatus({ features: features.filter((feature) => feature.coordinate_system === "s_q_mm") }),
      "geometry unavailable",
    );
    assert.equal(bladeFeatureGeometryStatus(null), null);
  });

  test("styles context meshes and disposes all scene resources", async () => {
    const { styleBladeContextGroup, disposeBladeFeatureSceneResources } = await loadSceneHelpers();
    const { THREE } = globalThis.__bladeFeatureSceneTestRuntime;
    const contextGroup = new THREE.Group();
    const mesh = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshStandardMaterial({ color: "#123456", emissive: "#ffffff" }));
    mesh.userData.surfaceId = "blade_0_pressure";
    const uvOverlay = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: "#00ff00" }));
    uvOverlay.userData.isSurfaceUvWire = true;
    const meshOverlay = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: "#00ff00" }));
    meshOverlay.userData.isMeshOverlay = true;
    contextGroup.add(mesh, uvOverlay, meshOverlay);
    const featureGroup = new THREE.Group();
    featureGroup.add(new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: "#c40000" })));

    assert.equal(styleBladeContextGroup(contextGroup), 1);
    const contour = contextGroup.children.find((child) => child.userData.isBladeContextContour);
    assert.equal(mesh.material.color.value, "#ffffff");
    assert.equal(mesh.material.emissive.value, "#000000");
    assert.equal(uvOverlay.visible, false);
    assert.equal(meshOverlay.visible, false);
    assert.equal(contour.material.color.value, "#111111");

    const registry = createRendererLifecycleRegistry();
    const release = registry.register({ getContext: () => ({}) });
    let controlsDisposed = false;
    let rendererDisposed = false;
    disposeBladeFeatureSceneResources({
      contextGroup,
      featureGroup,
      controls: { dispose: () => { controlsDisposed = true; } },
      renderer: { dispose: () => { rendererDisposed = true; } },
      releaseRendererLifecycle: release,
    });

    assert.equal(controlsDisposed, true);
    assert.equal(rendererDisposed, true);
    assert.equal(mesh.geometry.disposed, true);
    assert.equal(mesh.material.disposed, true);
    assert.equal(featureGroup.children[0].geometry.disposed, true);
    assert.deepEqual(registry.snapshot(), {
      createdRendererCount: 1,
      liveRendererCount: 0,
      createdContextCount: 1,
      liveContextCount: 0,
    });
  });
});

function disposeObject(object) {
  object.traverse((child) => {
    child.geometry?.dispose();
    for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
      material?.dispose();
    }
  });
}

function createThreeHarness() {
  class Object3D {
    constructor() {
      this.children = [];
      this.userData = {};
      this.visible = true;
    }

    add(...children) {
      this.children.push(...children);
    }

    traverse(callback) {
      callback(this);
      for (const child of [...this.children]) {
        child.traverse(callback);
      }
    }
  }

  class Color {
    constructor(value) {
      this.value = value;
    }

    set(value) {
      this.value = value;
    }
  }

  class BufferGeometry {
    constructor() {
      this.attributes = {};
      this.disposed = false;
    }

    setAttribute(name, value) {
      this.attributes[name] = value;
    }

    dispose() {
      this.disposed = true;
    }
  }

  class EdgesGeometry extends BufferGeometry {}

  class Float32BufferAttribute {
    constructor(values, itemSize) {
      this.values = values;
      this.itemSize = itemSize;
    }
  }

  class Material {
    constructor(options = {}) {
      const { color, emissive, ...properties } = options;
      this.color = new Color(color);
      this.emissive = new Color(emissive);
      this.disposed = false;
      Object.assign(this, properties);
    }

    dispose() {
      this.disposed = true;
    }
  }

  class Mesh extends Object3D {
    constructor(geometry, material) {
      super();
      this.geometry = geometry;
      this.material = material;
      this.isMesh = true;
    }
  }

  class Line extends Object3D {
    constructor(geometry, material) {
      super();
      this.geometry = geometry;
      this.material = material;
      this.isLine = true;
    }
  }

  class LineSegments extends Line {
    constructor(geometry, material) {
      super(geometry, material);
      this.isLineSegments = true;
    }
  }

  class Points extends Object3D {
    constructor(geometry, material) {
      super();
      this.geometry = geometry;
      this.material = material;
      this.isPoints = true;
    }
  }

  return {
    BufferGeometry,
    EdgesGeometry,
    Float32BufferAttribute,
    Group: class Group extends Object3D {},
    Line,
    LineBasicMaterial: class LineBasicMaterial extends Material {},
    LineSegments,
    Mesh,
    MeshStandardMaterial: class MeshStandardMaterial extends Material {},
    Points,
    PointsMaterial: class PointsMaterial extends Material {},
  };
}
