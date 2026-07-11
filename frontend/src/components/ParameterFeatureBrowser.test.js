import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";
import vm from "node:vm";

const root = resolve(import.meta.dirname, "..", "..");
const browserPath = resolve(root, "src/components/ParameterFeatureBrowser.js");

function loadComponent(path, exportName) {
  const source = readFileSync(path, "utf-8")
    .replace(
      'import React from "react";',
      'const React = { createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }) };',
    )
    .replace(/export function /g, "function ");
  const module = { exports: {} };
  const context = vm.createContext({ module, exports: module.exports, Array, Object, String });
  vm.runInContext(`${source}\nmodule.exports = { ${exportName} };`, context, { filename: path });
  return module.exports[exportName];
}

function collectElements(node, predicate, matches = []) {
  if (!node) {
    return matches;
  }
  if (Array.isArray(node)) {
    for (const child of node) {
      collectElements(child, predicate, matches);
    }
    return matches;
  }
  if (typeof node === "object") {
    if (predicate(node)) {
      matches.push(node);
    }
    collectElements(node.props?.children || [], predicate, matches);
  }
  return matches;
}

function browserFixture() {
  return [
    {
      groupId: "dimensions",
      label: "Dimensions",
      order: 0,
      collapsed: true,
      parameters: [{ id: "diameter", label: "Diameter", order: 0, applicableViews: ["top"] }],
    },
    {
      groupId: "blade_curve",
      label: "Blade Curve",
      order: 1,
      collapsed: false,
      parameters: [
        { id: "curve:control:0", label: "Control point 1", order: 0, applicableViews: ["s_q"], features: [{ kind: "control_point" }] },
        { id: "curve:control:1", label: "Control point 2", order: 1, applicableViews: ["s_q"], features: [{ kind: "control_point" }] },
        { id: "curve:restricted", label: "Restricted curve", order: 2, disabled: true, applicableViews: ["meridional", "s_q"] },
      ],
    },
  ];
}

describe("ParameterFeatureBrowser", () => {
  test("declares the compact native browser contract", () => {
    assert.equal(existsSync(browserPath), true, "ParameterFeatureBrowser.js should exist");
    if (!existsSync(browserPath)) {
      return;
    }

    const source = readFileSync(browserPath, "utf-8");
    assert.match(source, /"details"/);
    assert.match(source, /"summary"/);
    assert.match(source, /"button"/);
    assert.match(source, /type:\s*"button"/);
    assert.match(source, /aria-pressed/);
    assert.match(source, /onSelect\?\.\(active \? null : parameter\.id\)/);
  });

  test("renders collapsed defaults, expanded curve groups, and independent control buttons", () => {
    if (!existsSync(browserPath)) {
      return;
    }

    const ParameterFeatureBrowser = loadComponent(browserPath, "ParameterFeatureBrowser");
    const tree = ParameterFeatureBrowser({ groups: browserFixture() });
    const groups = collectElements(tree, (node) => node.type === "details");
    const buttons = collectElements(tree, (node) => node.type === "button");

    assert.equal(groups.length, 2);
    assert.equal(groups[0].props.open, false);
    assert.equal(groups[1].props.open, true);
    assert.equal(buttons.length, 4);
    assert.equal(buttons[1].props["data-parameter-id"], "curve:control:0");
    assert.equal(buttons[2].props["data-parameter-id"], "curve:control:1");
  });

  test("exposes applicable views for disabled parameters and clears the active selection", () => {
    if (!existsSync(browserPath)) {
      return;
    }

    const selected = [];
    const ParameterFeatureBrowser = loadComponent(browserPath, "ParameterFeatureBrowser");
    const tree = ParameterFeatureBrowser({
      groups: browserFixture(),
      selectedParameterId: "curve:control:0",
      onSelect: (id) => selected.push(id),
    });
    const buttons = collectElements(tree, (node) => node.type === "button");
    const active = buttons.find((button) => button.props["data-parameter-id"] === "curve:control:0");
    const disabled = buttons.find((button) => button.props["data-parameter-id"] === "curve:restricted");

    assert.equal(active.props["aria-pressed"], true);
    active.props.onClick();
    assert.deepEqual(selected, [null]);
    assert.equal(disabled.props.disabled, true);
    assert.match(disabled.props.title, /Meridional, S-Q/);
  });
});
