import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const html = readFileSync(resolve(root, "index.html"), "utf-8");

assert.match(html, /type="importmap"/);
assert.match(html, /src="\/src\/main\.js"/);

for (const file of [
  "src/main.js",
  "src/App.js",
  "src/apiClient.js",
  "src/appModel.js",
  "src/components/PresetList.js",
  "src/components/FacetPanel.js",
  "src/components/ParameterPanel.js",
  "src/components/ModelViewer.js",
  "src/components/ManifestPanel.js",
  "src/styles.css",
]) {
  assert.equal(existsSync(resolve(root, file)), true, `${file} should exist`);
}

console.log("frontend build check passed");
