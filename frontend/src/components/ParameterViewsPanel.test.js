import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..", "..");
const componentPath = resolve(root, "src/components/ParameterViewsPanel.js");

describe("ParameterViewsPanel source contract", () => {
  test("component exists and renders the Parameter views tab label", () => {
    assert.equal(existsSync(componentPath), true);
    const source = readFileSync(componentPath, "utf-8");
    assert.match(source, /Parameter views/);
    assert.match(source, /parameterViewTabs/);
  });

  test("component is inspection-only and does not accept mutation callbacks", () => {
    const source = readFileSync(componentPath, "utf-8");
    assert.doesNotMatch(source, /onChange/);
    assert.doesNotMatch(source, /onParameter/);
    assert.doesNotMatch(source, /setGeometry/);
  });
});
