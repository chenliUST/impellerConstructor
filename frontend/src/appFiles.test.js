import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..");

describe("frontend application files", () => {
  test("browser entry uses import maps and the main module", () => {
    const html = readFileSync(resolve(root, "index.html"), "utf-8");

    assert.match(html, /type="importmap"/);
    assert.match(html, /src="\/src\/main\.js"/);
  });

  test("application shell files exist", () => {
    for (const file of [
      "scripts/build-check.js",
      "src/main.js",
      "src/App.js",
      "src/apiClient.js",
      "src/components/PresetList.js",
      "src/components/FacetPanel.js",
      "src/components/ParameterPanel.js",
      "src/components/ModelViewer.js",
      "src/components/ManifestPanel.js",
      "src/styles.css",
    ]) {
      assert.equal(existsSync(resolve(root, file)), true, `${file} should exist`);
    }
  });

  test("viewer renders construction lines instead of mesh triangle wireframe", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
    const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");

    assert.doesNotMatch(viewerSource, /GridHelper/);
    assert.doesNotMatch(viewerSource, /wireframe:\s*true/);
    assert.match(viewerSource, /LineSegments/);
    assert.match(appSource, /useState\(false\)/);
  });

  test("parameter panel uses direct numeric inputs without range sliders", () => {
    const panelSource = readFileSync(resolve(root, "src/components/ParameterPanel.js"), "utf-8");

    assert.doesNotMatch(panelSource, /type:\s*"range"/);
    assert.match(panelSource, /type:\s*"number"/);
  });

  test("viewer gives blade edge construction lines a dedicated visible layer", () => {
    const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");

    assert.match(viewerSource, /blade_edges/);
    assert.match(viewerSource, /edge_closure_surface/);
  });
});
