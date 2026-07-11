const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const moduleRoot = process.env.CODEX_NODE_MODULES;
assert.ok(moduleRoot, "CODEX_NODE_MODULES is required");
const runtimeRequire = createRequire(path.join(moduleRoot, "playwright", "package.json"));
const { chromium } = requirePlaywright();
const { PNG } = runtimeRequire("pngjs");

const DESKTOP_VIEWPORT = { width: 1440, height: 1000 };
const NARROW_VIEWPORT = { width: 760, height: 1100 };
const EXPECTED_TABS = ["inspection-tab-top", "inspection-tab-meridional", "inspection-tab-s_q_blade"];

function requirePlaywright() {
  try {
    return runtimeRequire("playwright");
  } catch (error) {
    if (error?.code !== "MODULE_NOT_FOUND" || !String(error.message).includes("playwright-core")) throw error;
    const metadata = JSON.parse(fs.readFileSync(path.join(moduleRoot, "playwright", "package.json"), "utf8"));
    const packageJson = path.join(
      moduleRoot,
      ".pnpm",
      `playwright@${metadata.version}`,
      "node_modules",
      "playwright",
      "package.json",
    );
    assert.ok(fs.existsSync(packageJson), `workspace Playwright ${metadata.version} is incomplete`);
    return createRequire(packageJson)("playwright");
  }
}

function pixelStats(buffer) {
  const png = PNG.sync.read(buffer);
  const stats = { black: 0, dark: 0, red: 0, blue: 0, orange: 0, total: png.width * png.height };
  const redPoints = [];
  for (let index = 0; index < png.data.length; index += 4) {
    const red = png.data[index];
    const green = png.data[index + 1];
    const blue = png.data[index + 2];
    if (red < 60 && green < 60 && blue < 60) stats.black += 1;
    if (red < 170 && green < 170 && blue < 170) stats.dark += 1;
    if (red > 120 && red > green * 1.8 && red > blue * 1.8) {
      stats.red += 1;
      const pixel = index / 4;
      redPoints.push([pixel % png.width, Math.floor(pixel / png.width)]);
    }
    if (blue > 90 && blue > red * 1.7 && blue > green * 1.15) stats.blue += 1;
    if (red > 180 && green > 65 && green < 155 && blue < 90) stats.orange += 1;
  }
  const redNearNeutral = redPoints.filter(([x, y]) => redPointTouchesNeutral(png, x, y, 12)).length;
  return {
    ...stats,
    redNearNeutral,
    darkRatio: stats.dark / stats.total,
    redRatio: stats.red / stats.total,
    blueRatio: stats.blue / stats.total,
    orangeRatio: stats.orange / stats.total,
  };
}

function redPointTouchesNeutral(png, x, y, radius) {
  for (let targetY = Math.max(0, y - radius); targetY <= Math.min(png.height - 1, y + radius); targetY += 1) {
    for (let targetX = Math.max(0, x - radius); targetX <= Math.min(png.width - 1, x + radius); targetX += 1) {
      const index = (targetY * png.width + targetX) * 4;
      const red = png.data[index];
      const green = png.data[index + 1];
      const blue = png.data[index + 2];
      if (Math.max(red, green, blue) - Math.min(red, green, blue) < 12 && red < 210) return true;
    }
  }
  return false;
}

async function captureElement(page, locator, outputPath) {
  await page.waitForTimeout(300);
  const box = await locator.boundingBox();
  assert.ok(box && box.width > 0 && box.height > 0, `missing screenshot bounds for ${outputPath}`);
  return locator.screenshot({ path: outputPath, animations: "disabled", timeout: 60000 });
}

function boxesOverlap(left, right) {
  return left.x < right.x + right.width
    && left.x + left.width > right.x
    && left.y < right.y + right.height
    && left.y + left.height > right.y;
}

async function assertWorkspaceRegionsDoNotOverlap(page, label) {
  const toolbar = page.locator(".inspection-workspace-toolbar");
  const browser = page.locator(".inspection-workspace-body > .engineering-parameter-browser");
  const drawing = page.locator(".inspection-drawing-grid");
  const [toolbarBox, browserBox, drawingBox] = await Promise.all([
    toolbar.boundingBox(),
    browser.boundingBox(),
    drawing.boundingBox(),
  ]);
  assert.ok(toolbarBox && browserBox && drawingBox, `${label} regions must have measurable bounds`);
  const bounds = { toolbarBox, browserBox, drawingBox };
  assert.equal(boxesOverlap(toolbarBox, drawingBox), false, `${label} toolbar/drawing overlap: ${JSON.stringify(bounds)}`);
  assert.equal(boxesOverlap(browserBox, drawingBox), false, `${label} browser/drawing overlap: ${JSON.stringify(bounds)}`);
  console.log(`${label} workspace bounds: ${JSON.stringify(bounds)}`);
}

async function assertComputedColor(page, selector, property, expected, message) {
  await page.locator(selector).first().waitFor({ state: "attached" });
  const color = await page.evaluate(
    ({ selector: target, property: name }) => getComputedStyle(document.querySelector(target))[name],
    { selector, property },
  );
  assert.equal(color, expected, message);
}

async function openAndSelectParameter(page, parameterId, groupId) {
  const button = page.locator(`[data-parameter-id="${parameterId}"]`);
  if (await button.count() === 0) {
    const summary = page.locator(`[data-parameter-group-id="${groupId}"] > summary`);
    await summary.evaluate((element) => element.click());
  }
  await button.waitFor({ state: "attached" });
  assert.equal(await button.isDisabled(), false, `${parameterId} is disabled in the active view`);
  await button.click();
  await page.locator(`[data-testid="inspection-workspace"][data-selected-parameter-id="${parameterId}"]`).waitFor();
  assert.equal(await button.getAttribute("aria-pressed"), "true");
  return button;
}

function contractParameter(manifest, predicate, description) {
  const parameters = manifest?.parameter_inspection?.parameters || [];
  const parameter = parameters.find(predicate);
  assert.ok(parameter, `missing generated parameter: ${description}`);
  return parameter;
}

function surfaceById(manifest, surfaceId) {
  return (manifest?.geometry?.surface_graph?.surfaces || []).find((surface) =>
    (surface.id || surface.surface_graph_id) === surfaceId);
}

async function webglLifecycle(page) {
  return page.evaluate(() => {
    const metrics = window.__task8WebglLifecycle || {};
    const scene = document.querySelector('[data-testid="blade-feature-webgl"]');
    return {
      createdRenderers: Number(metrics.createdRenderers || 0),
      createdContexts: Number(metrics.createdContexts || 0),
      lostContexts: Number(metrics.lostContexts || 0),
      restoredContexts: Number(metrics.restoredContexts || 0),
      liveRenderers: Number(scene?.getAttribute("data-renderer-live-count") || 0),
      liveContexts: Number(scene?.getAttribute("data-context-live-count") || 0),
      liveCanvasElements: scene?.querySelectorAll("canvas").length || 0,
    };
  });
}

async function assertBladeScene(page, label) {
  const scene = page.locator('[data-testid="blade-feature-webgl"]');
  await scene.waitFor({ state: "visible" });
  await page.waitForFunction(() => {
    const element = document.querySelector('[data-testid="blade-feature-webgl"]');
    return Number(element?.getAttribute("data-scene-surface-count")) > 0
      && Number(element?.getAttribute("data-renderer-live-count")) === 1
      && Number(element?.getAttribute("data-context-live-count")) === 1
      && element?.querySelectorAll("canvas").length === 1;
  }, { timeout: 300000 });
  assert.equal(await scene.getAttribute("data-visible-uv-overlay-count"), "0");
  assert.equal(await scene.getAttribute("data-visible-mesh-overlay-count"), "0");
  const stats = pixelStats(await scene.screenshot({ animations: "disabled" }));
  assert.ok(stats.darkRatio >= 0.01, `${label} blade viewport is blank: ${JSON.stringify(stats)}`);
  assert.ok(stats.red >= 6, `${label} blade feature line is not visibly red: ${JSON.stringify(stats)}`);
  assert.ok(stats.redNearNeutral >= 1, `${label} blade feature is detached from blade context: ${JSON.stringify(stats)}`);
  assert.ok(stats.redRatio < 0.03, `${label} blade selection is surface-sized, not feature-sized: ${JSON.stringify(stats)}`);
  assert.ok(stats.orangeRatio < 0.005, `${label} blade contains selected mesh material: ${JSON.stringify(stats)}`);
  return stats;
}

async function assertDrawingColors(page) {
  await assertComputedColor(
    page,
    ".engineering-feature",
    "stroke",
    "rgb(196, 0, 0)",
    "selected construction evidence must be red",
  );
  await assertComputedColor(
    page,
    ".engineering-dimension line, .engineering-dimension path",
    "stroke",
    "rgb(0, 94, 168)",
    "engineering dimensions must be blue",
  );
  await assertComputedColor(
    page,
    ".engineering-context",
    "stroke",
    "rgb(17, 17, 17)",
    "engineering context must be thin black geometry",
  );
}

async function assertForbiddenInspectionUiAbsent(page) {
  const workspace = page.locator('[data-testid="inspection-workspace"]');
  const tabIds = await page.evaluate(() => [...document.querySelectorAll(
    '[data-testid="inspection-workspace"] [role="tab"][data-testid]',
  )].map((tab) => tab.getAttribute("data-testid")));
  assert.deepEqual(tabIds, EXPECTED_TABS);
  assert.equal(await workspace.locator('[data-testid="inspection-tab-3d"]').count(), 0);
  assert.equal(await workspace.locator('[data-testid="inspection-tab-quad"]').count(), 0);
  assert.equal(await workspace.locator(".inspection-leader").count(), 0);
  assert.equal(await workspace.locator('input, textarea, [contenteditable="true"]').count(), 0);
  assert.doesNotMatch(await workspace.innerText(), /\b(?:UV|triangle|Quad)\b/i);
}

async function runAcceptanceCheck(failures, label, callback) {
  try {
    const result = await callback();
    console.log(`${label}: PASS`);
    return result;
  } catch (error) {
    failures.push(`${label}: ${error.message}`);
    console.error(`${label}: FAIL\n${error.stack || error}`);
    return null;
  }
}

async function main() {
  const outputDir = path.resolve(__dirname, "..", "..", "docs/evidence/assets/v1.1.3-engineering-parameter-inspection");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const failures = [];
  try {
    const page = await browser.newPage({ viewport: DESKTOP_VIEWPORT });
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
    });
    await page.addInitScript(() => {
      const originalGetContext = HTMLCanvasElement.prototype.getContext;
      const seenRenderers = new WeakSet();
      const seenContexts = new WeakSet();
      const metrics = {
        createdRenderers: 0,
        createdContexts: 0,
        lostContexts: 0,
        restoredContexts: 0,
      };
      Object.defineProperty(window, "__task8WebglLifecycle", { value: metrics });
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (...args) => {
        const response = await originalFetch(...args);
        if (/\/api\/rule-engines\/[^/]+\/instantiate$/.test(response.url)) {
          response.clone().json().then((payload) => {
            const manifest = payload?.manifest || {};
            const parameters = (manifest.parameter_inspection?.parameters || []).filter((parameter) =>
              parameter.parameter_id === "blade.angular_pitch"
              || parameter.parameter_id.includes(":attachment:root:lift")
              || parameter.parameter_id.endsWith(":section:leading_edge:sagitta"));
            const rootSurfaceIds = new Set(parameters
              .map((parameter) => parameter.selection_scope?.source_attachment_surface_id)
              .filter(Boolean));
            const surfaces = (manifest.geometry?.surface_graph?.surfaces || [])
              .filter((surface) => rootSurfaceIds.has(surface.id || surface.surface_graph_id))
              .map((surface) => ({
                id: surface.id || surface.surface_graph_id,
                role: surface.role,
                v1_1_root_domain_samples: {
                  hub_outer_loop_s_q: surface.v1_1_root_domain_samples?.hub_outer_loop_s_q?.slice(0, 2) || [],
                  blade_inner_loop_s_q: surface.v1_1_root_domain_samples?.blade_inner_loop_s_q?.slice(0, 2) || [],
                },
              }));
            window.__task8InstantiateEvidence = {
              preset_id: manifest.preset_id,
              parameter_inspection: { parameters },
              geometry: { surface_graph: { surfaces } },
            };
          }).catch((error) => {
            window.__task8InstantiateEvidenceError = String(error?.stack || error);
          });
        }
        return response;
      };
      HTMLCanvasElement.prototype.getContext = function getContext(type, ...args) {
        const context = originalGetContext.call(this, type, ...args);
        if (/^webgl/i.test(String(type))) {
          if (!seenRenderers.has(this)) {
            seenRenderers.add(this);
            metrics.createdRenderers += 1;
            this.addEventListener("webglcontextlost", () => { metrics.lostContexts += 1; });
            this.addEventListener("webglcontextrestored", () => { metrics.restoredContexts += 1; });
          }
          if (context && !seenContexts.has(context)) {
            seenContexts.add(context);
            metrics.createdContexts += 1;
          }
        }
        return context;
      };
    });

    await page.goto("http://127.0.0.1:5199", { waitUntil: "networkidle" });
    const instantiateResponse = page.waitForResponse((response) =>
      response.request().method() === "POST" && /\/api\/rule-engines\/[^/]+\/instantiate$/.test(response.url()),
    { timeout: 600000 });
    await page.locator('[data-testid="generate-model"]').click();
    const response = await instantiateResponse;
    assert.equal(response.status(), 200, `instantiate returned HTTP ${response.status()}`);
    await page.waitForFunction(() =>
      Boolean(window.__task8InstantiateEvidence || window.__task8InstantiateEvidenceError),
    { timeout: 600000 });
    const evidenceError = await page.evaluate(() => window.__task8InstantiateEvidenceError || "");
    assert.equal(evidenceError, "", evidenceError);
    const manifest = await page.evaluate(() => window.__task8InstantiateEvidence);
    assert.equal(manifest?.preset_id, "radial_open_reference_v1_1", "smoke must generate the first V1.1 preset");
    await page.locator('[data-testid="generate-model"]:not([disabled])').waitFor({ timeout: 300000 });
    await page.locator('[data-testid="simulation-mode-parameter_inspection"]').click();
    const workspace = page.locator('[data-testid="inspection-workspace"]');
    try {
      await workspace.locator(".engineering-drawing-canvas").waitFor({ state: "visible", timeout: 30000 });
    } catch (error) {
      throw new Error(`${error.message}\nBrowser errors:\n${browserErrors.join("\n") || "none"}`);
    }
    await assertForbiddenInspectionUiAbsent(page);
    const lifecycleBaseline = await webglLifecycle(page);

    const topParameter = contractParameter(
      manifest,
      (parameter) => parameter.parameter_id === "blade.angular_pitch",
      "blade.angular_pitch",
    );
    await runAcceptanceCheck(failures, "parameter inspection desktop Top context", async () => {
      const stats = pixelStats(await page.locator(".engineering-drawing-canvas").screenshot({ animations: "disabled" }));
      assert.ok(stats.black >= 20, `Top drawing viewport is blank: ${JSON.stringify(stats)}`);
    });
    await runAcceptanceCheck(failures, "parameter inspection desktop Top", async () => {
      assert.equal(await workspace.getAttribute("data-active-tab"), "top");
      assert.ok(topParameter.applicable_views.includes("top"), "blade.angular_pitch is not applicable in Top");
      assert.equal(topParameter.feature_geometry.every((feature) => feature.coordinate_system === "model_xyz"), true);
      assert.equal(topParameter.feature_geometry.some((feature) => feature.kind === "reference_axis"), true);
      assert.equal(topParameter.dimension_definition?.kind, "angular");
      await openAndSelectParameter(page, topParameter.parameter_id, topParameter.group_id);
      assert.ok(await page.locator("path.engineering-feature").count() >= 2, "Top lacks red angular reference evidence");
      assert.ok(await page.locator(".engineering-dimension line").count() >= 1, "Top lacks blue angular dimension");
      assert.ok(await page.locator(".engineering-dimension text").count() >= 1, "Top lacks dimension text");
      assert.match(
        (await page.locator(".engineering-dimension text").first().textContent())?.trim() || "",
        /\d.*deg/,
        "Top dimension text lacks its resolved value",
      );
      await assertDrawingColors(page);
      await assertWorkspaceRegionsDoNotOverlap(page, "desktop Top");
      const stats = pixelStats(await page.locator(".engineering-drawing-canvas").screenshot({ animations: "disabled" }));
      assert.ok(stats.blue >= 4, `Top blue dimension is not visible: ${JSON.stringify(stats)}`);
    });
    const topBuffer = await captureElement(page, workspace, path.join(outputDir, "desktop-top.png"));
    assert.ok(pixelStats(topBuffer).darkRatio >= 0.001, "desktop Top screenshot is blank");

    await page.locator('[data-testid="inspection-tab-meridional"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="meridional"]').waitFor();
    const bladeId = await workspace.getAttribute("data-selected-blade-id");
    const stationId = await workspace.getAttribute("data-selected-station-id");
    const rootLift = contractParameter(
      manifest,
      (parameter) => parameter.parameter_id.includes(`blade:${bladeId}:attachment:root:lift`),
      `root attachment lift for ${bladeId}`,
    );
    await runAcceptanceCheck(failures, "parameter inspection desktop Meridional", async () => {
      assert.ok(rootLift.applicable_views.includes("meridional"));
      assert.equal(rootLift.dimension_definition?.kind, "linear");
      assert.equal(rootLift.feature_geometry.filter((feature) => feature.kind === "point").length, 2);
      const rootSurface = surfaceById(manifest, rootLift.selection_scope?.source_attachment_surface_id);
      assert.ok(rootSurface, "root lift does not identify its authoritative attachment surface");
      assert.ok(rootSurface.v1_1_root_domain_samples?.hub_outer_loop_s_q?.length > 1, "missing hub root boundary");
      assert.ok(rootSurface.v1_1_root_domain_samples?.blade_inner_loop_s_q?.length > 1, "missing blade root boundary");
      await openAndSelectParameter(page, rootLift.parameter_id, rootLift.group_id);
      assert.ok(await page.locator(".engineering-context").count() >= 2, "Meridional lacks hub/blade root context boundaries");
      assert.equal(await page.locator("circle.engineering-feature").count(), 2, "Meridional root lift must identify two red endpoints");
      assert.ok(await page.locator(".engineering-dimension line").count() >= 1, "Meridional lacks blue normal dimension");
      assert.ok(await page.locator(".engineering-dimension text").count() >= 1, "Meridional lacks dimension text");
      assert.match(
        (await page.locator(".engineering-dimension text").first().textContent())?.trim() || "",
        /\d.*mm/,
        "Meridional dimension text lacks its resolved value",
      );
      await assertDrawingColors(page);
      await assertWorkspaceRegionsDoNotOverlap(page, "desktop Meridional");
      const stats = pixelStats(await page.locator(".engineering-drawing-canvas").screenshot({ animations: "disabled" }));
      assert.ok(stats.black >= 20, `Meridional lacks visible black hub/blade root boundaries: ${JSON.stringify(stats)}`);
      assert.ok(stats.blue >= 4, `Meridional blue dimension is not visible: ${JSON.stringify(stats)}`);
    });
    const meridionalBuffer = await captureElement(page, workspace, path.join(outputDir, "desktop-meridional.png"));
    assert.ok(pixelStats(meridionalBuffer).darkRatio >= 0.001, "desktop Meridional screenshot is blank");

    await page.locator('[data-testid="inspection-tab-s_q_blade"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="s_q_blade"]').waitFor();
    const leadingSagitta = contractParameter(
      manifest,
      (parameter) => parameter.parameter_id.endsWith(":section:leading_edge:sagitta")
        && parameter.selection_scope?.blade_instance_id === bladeId
        && parameter.selection_scope?.span_station_id === stationId,
      `leading-edge sagitta for ${bladeId}/${stationId}`,
    );
    let desktopBladeStats = null;
    await runAcceptanceCheck(failures, "parameter inspection desktop S-Q + Blade", async () => {
      assert.ok(leadingSagitta.applicable_views.includes("s_q"));
      assert.ok(leadingSagitta.applicable_views.includes("blade_3d"));
      assert.equal(leadingSagitta.feature_geometry.some((feature) => feature.kind === "polyline"), true);
      assert.equal(leadingSagitta.dimension_definition?.kind, "arc_height");
      assert.equal(leadingSagitta.dimension_definition?.measurement_points?.length, 3);
      await openAndSelectParameter(page, leadingSagitta.parameter_id, leadingSagitta.group_id);
      assert.ok(await page.locator("path.engineering-feature").count() >= 1, "S-Q lacks red leading-edge geometry");
      const dimension = page.locator(".engineering-dimension");
      assert.ok(await dimension.locator("line").count() >= 1, "S-Q lacks blue sagitta ordinate");
      assert.ok(await dimension.locator("path").count() >= 2, "S-Q lacks blue chord/sagitta construction");
      assert.equal(await dimension.locator("text").count(), 1, "S-Q lacks sagitta value");
      await assertDrawingColors(page);
      const stats = pixelStats(await page.locator(".engineering-drawing-canvas").screenshot({ animations: "disabled" }));
      assert.ok(stats.red >= 4 && stats.blue >= 4, `S-Q red/blue construction evidence is not visible: ${JSON.stringify(stats)}`);
      desktopBladeStats = await assertBladeScene(page, "desktop S-Q + Blade");
      await assertWorkspaceRegionsDoNotOverlap(page, "desktop S-Q + Blade");
    });
    const desktopSqBuffer = await captureElement(page, workspace, path.join(outputDir, "desktop-s-q-blade.png"));
    assert.ok(pixelStats(desktopSqBuffer).darkRatio >= 0.001, "desktop S-Q + Blade screenshot is blank");

    await page.setViewportSize(NARROW_VIEWPORT);
    await runAcceptanceCheck(failures, "parameter inspection narrow S-Q + Blade", async () => {
      assert.equal(await workspace.getAttribute("data-active-tab"), "s_q_blade");
      assert.equal(await workspace.getAttribute("data-selected-parameter-id"), leadingSagitta.parameter_id);
      assert.ok(await page.locator("path.engineering-feature").count() >= 1, "narrow S-Q lost red edge geometry");
      assert.ok(await page.locator(".engineering-dimension line").count() >= 1, "narrow S-Q lost blue dimension");
      await assertDrawingColors(page);
      await assertBladeScene(page, "narrow S-Q + Blade");
      await assertWorkspaceRegionsDoNotOverlap(page, "narrow S-Q + Blade");
    });
    const narrowSqBuffer = await captureElement(page, workspace, path.join(outputDir, "narrow-s-q-blade.png"));
    assert.ok(pixelStats(narrowSqBuffer).darkRatio >= 0.001, "narrow S-Q + Blade screenshot is blank");

    await assertForbiddenInspectionUiAbsent(page);
    const finalLifecycle = await webglLifecycle(page);
    const lifecycleDelta = {
      createdRenderers: finalLifecycle.createdRenderers - lifecycleBaseline.createdRenderers,
      createdContexts: finalLifecycle.createdContexts - lifecycleBaseline.createdContexts,
      lostContexts: finalLifecycle.lostContexts - lifecycleBaseline.lostContexts,
      restoredContexts: finalLifecycle.restoredContexts - lifecycleBaseline.restoredContexts,
      liveRenderers: finalLifecycle.liveRenderers,
      liveContexts: finalLifecycle.liveContexts,
      liveCanvasElements: finalLifecycle.liveCanvasElements,
    };
    assert.ok(lifecycleDelta.createdRenderers >= 1 && lifecycleDelta.createdRenderers <= 3, JSON.stringify(lifecycleDelta));
    assert.ok(lifecycleDelta.createdContexts >= 1 && lifecycleDelta.createdContexts <= 3, JSON.stringify(lifecycleDelta));
    assert.equal(lifecycleDelta.liveRenderers, 1);
    assert.equal(lifecycleDelta.liveContexts, 1);
    assert.equal(lifecycleDelta.liveCanvasElements, 1);
    assert.equal(lifecycleDelta.restoredContexts, 0);

    console.log(`generated preset: ${manifest.preset_id}`);
    console.log(`selected Top parameter: ${topParameter.parameter_id}`);
    console.log(`selected Meridional parameter: ${rootLift.parameter_id}`);
    console.log(`selected S-Q + Blade parameter: ${leadingSagitta.parameter_id}`);
    console.log(`inspection renderer/context lifecycle: ${JSON.stringify(lifecycleDelta)}`);
    console.log(`desktop blade pixel evidence: ${JSON.stringify(desktopBladeStats)}`);
    console.log(`browser device pixel ratio: ${await page.evaluate(() => window.devicePixelRatio)}`);

    if (failures.length > 0) {
      throw new Error(`Task 8 acceptance failed:\n- ${failures.join("\n- ")}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
