const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const moduleRoot = process.env.CODEX_NODE_MODULES;
assert.ok(moduleRoot, "CODEX_NODE_MODULES is required");
const runtimeRequire = createRequire(path.join(moduleRoot, "playwright", "package.json"));
const { chromium } = runtimeRequire("playwright");
const { PNG } = runtimeRequire("pngjs");

function nonBackgroundRatio(buffer) {
  const png = PNG.sync.read(buffer);
  let changed = 0;
  for (let index = 0; index < png.data.length; index += 4) {
    const red = png.data[index];
    const green = png.data[index + 1];
    const blue = png.data[index + 2];
    if (Math.abs(red - 245) + Math.abs(green - 245) + Math.abs(blue - 245) > 24) changed += 1;
  }
  return changed / (png.width * png.height);
}

async function captureElement(page, locator, outputPath) {
  await locator.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  const clip = await locator.boundingBox();
  assert.ok(clip && clip.width > 0 && clip.height > 0, `missing screenshot bounds for ${outputPath}`);
  await page.screenshot({ path: outputPath, clip, animations: "disabled", timeout: 60000 });
}

async function rendererLifecycle(locator) {
  const values = await Promise.all([
    "data-renderer-created-count",
    "data-renderer-live-count",
    "data-context-created-count",
    "data-context-live-count",
  ].map((name) => locator.getAttribute(name)));
  return {
    createdRenderers: Number(values[0]),
    liveRenderers: Number(values[1]),
    createdContexts: Number(values[2]),
    liveContexts: Number(values[3]),
  };
}

async function main() {
  const outputDir = path.resolve("docs/evidence/assets/v1.1.3-parameter-inspection");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.goto("http://127.0.0.1:5199", { waitUntil: "networkidle" });
    await page.locator('[data-testid="generate-model"]').click();
    await page.locator('[data-testid="generate-model"]:not([disabled])').waitFor({ timeout: 300000 });
    await page.locator('[data-testid="simulation-mode-parameter_inspection"]').click();
    const canvas = page.locator('[data-testid="inspection-webgl"]');
    await canvas.waitFor({ state: "visible", timeout: 300000 });
    await page.waitForFunction(() => {
      const element = document.querySelector('[data-testid="inspection-webgl"]');
      return Number(element?.getAttribute("data-scene-surface-count")) > 0
        && Number(element?.getAttribute("data-renderer-live-count")) > 0
        && Number(element?.getAttribute("data-context-live-count")) > 0;
    }, { timeout: 300000 });

    const initialLifecycle = await rendererLifecycle(canvas);
    const surfaceCount = await canvas.getAttribute("data-scene-surface-count");
    const devicePixelRatio = await page.evaluate(() => window.devicePixelRatio);
    assert.deepEqual(initialLifecycle, {
      createdRenderers: 1,
      liveRenderers: 1,
      createdContexts: 1,
      liveContexts: 1,
    });
    assert.ok(Number(surfaceCount) > 0);
    assert.equal(await canvas.getAttribute("data-visible-uv-overlay-count"), "0");
    assert.equal(await page.locator(".inspection-leader").count(), 0);

    const workspace = page.locator('[data-testid="inspection-workspace"]');
    const bladeSelector = page.locator('[data-testid="inspection-blade-selector"]');
    const bladeOptions = await bladeSelector.locator("option").evaluateAll((options) => options.map((option) => option.value));
    assert.ok(bladeOptions.length > 1, "cross-blade smoke requires at least two blades");
    await bladeSelector.selectOption(bladeOptions[1]);
    await page.waitForFunction((bladeId) =>
      document.querySelector('[data-testid="inspection-workspace"]')?.getAttribute("data-selected-blade-id") === bladeId,
    bladeOptions[1]);
    assert.ok(Number(await workspace.getAttribute("data-selected-surface-count")) > 1);

    const stationSelector = page.locator('[data-testid="inspection-station-selector"]');
    const stationOptions = await stationSelector.locator("option").evaluateAll((options) => options.map((option) => option.value));
    assert.ok(stationOptions.length > 1, "station smoke requires at least two span stations");
    await stationSelector.selectOption(stationOptions.at(-1));
    assert.equal(await workspace.getAttribute("data-selected-station-id"), stationOptions.at(-1));

    const annotationSelector = page.locator('[data-testid="inspection-annotation-level"]');
    await annotationSelector.selectOption("all");
    assert.equal(await annotationSelector.inputValue(), "all");
    await annotationSelector.selectOption("key");

    const parameterRow = page.locator('[data-annotation-id="3d:thickness_max_mm"]');
    await parameterRow.waitFor({ state: "visible" });
    await parameterRow.click();
    assert.equal(await parameterRow.getAttribute("aria-pressed"), "true");
    assert.equal(await workspace.getAttribute("data-selected-annotation-id"), "3d:thickness_max_mm");
    assert.ok(Number(await workspace.getAttribute("data-selected-surface-count")) > 0);

    const canvasBuffer = await canvas.screenshot();
    const ratio = nonBackgroundRatio(canvasBuffer);
    assert.ok(ratio >= 0.05, `inspection canvas ratio ${ratio} is below 0.05`);
    await captureElement(page, workspace, path.join(outputDir, "desktop-3d.png"));
    console.log("parameter inspection desktop 3D: PASS");
    await parameterRow.click();
    assert.equal(await workspace.getAttribute("data-selected-annotation-id"), "");

    await page.locator('[data-testid="inspection-tab-quad"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="quad"]').waitFor();
    await page.waitForFunction(() =>
      Number(document.querySelector('[data-testid="inspection-webgl"]')?.getAttribute("data-renderer-created-count")) >= 2,
    );
    const quadLifecycle = await rendererLifecycle(canvas);
    assert.equal(quadLifecycle.liveRenderers, 1);
    assert.equal(quadLifecycle.liveContexts, 1);
    assert.ok(quadLifecycle.createdRenderers > initialLifecycle.createdRenderers);
    assert.ok(quadLifecycle.createdContexts > initialLifecycle.createdContexts);
    await captureElement(page, workspace, path.join(outputDir, "desktop-quad.png"));
    console.log("parameter inspection desktop Quad: PASS");

    await page.setViewportSize({ width: 768, height: 1100 });
    await page.locator(".inspection-workspace-toolbar.narrow .inspection-entity-selectors.narrow").waitFor({ timeout: 30000 });
    await page.locator('[data-testid="inspection-tab-s_q"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="s_q"]').waitFor();
    await annotationSelector.selectOption("all");
    const workspaceBox = await workspace.boundingBox();
    const annotationBox = await annotationSelector.boundingBox();
    const sectionPaneBox = await page.locator(".inspection-section-loop-pane").boundingBox();
    assert.ok(workspaceBox && annotationBox && sectionPaneBox, "narrow inspection regions must have measurable bounds");
    const narrowBounds = { workspaceBox, annotationBox, sectionPaneBox };
    console.log(`narrow toolbar bounds: ${JSON.stringify(narrowBounds)}`);
    assert.ok(
      annotationBox.x >= workspaceBox.x && annotationBox.x + annotationBox.width <= workspaceBox.x + workspaceBox.width,
      JSON.stringify(narrowBounds),
    );
    assert.ok(
      annotationBox.y >= workspaceBox.y && annotationBox.y + annotationBox.height <= workspaceBox.y + workspaceBox.height,
      JSON.stringify(narrowBounds),
    );
    assert.ok(annotationBox.y + annotationBox.height <= sectionPaneBox.y, JSON.stringify(narrowBounds));
    assert.equal(await bladeSelector.inputValue(), bladeOptions[1]);
    assert.equal(await annotationSelector.inputValue(), "all");
    await captureElement(page, workspace, path.join(outputDir, "narrow-s-q.png"));
    console.log("parameter inspection narrow S-Q: PASS");
    await page.locator('[data-testid="inspection-tab-3d"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="3d"]').waitFor();
    await page.waitForFunction((previousCreated) =>
      Number(document.querySelector('[data-testid="inspection-webgl"]')?.getAttribute("data-renderer-created-count")) > previousCreated,
    quadLifecycle.createdRenderers);
    const finalLifecycle = await rendererLifecycle(canvas);
    assert.equal(finalLifecycle.liveRenderers, 1);
    assert.equal(finalLifecycle.liveContexts, 1);
    assert.ok(finalLifecycle.createdContexts > quadLifecycle.createdContexts);
    console.log(`inspection renderer lifecycle: ${JSON.stringify(finalLifecycle)}`);
    console.log(`inspection scene surface count: ${surfaceCount}`);
    console.log(`browser device pixel ratio: ${devicePixelRatio}`);
    console.log(`inspection canvas non-background ratio: ${ratio.toFixed(4)}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
