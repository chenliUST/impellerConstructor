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
    if (Math.abs(red - 238) + Math.abs(green - 242) + Math.abs(blue - 240) > 24) changed += 1;
  }
  return changed / (png.width * png.height);
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
      return Number(element?.getAttribute("data-scene-surface-count")) > 0;
    }, { timeout: 300000 });

    const rendererCount = await canvas.getAttribute("data-renderer-count");
    const surfaceCount = await canvas.getAttribute("data-scene-surface-count");
    const devicePixelRatio = await page.evaluate(() => window.devicePixelRatio);
    assert.equal(rendererCount, "1");
    assert.ok(Number(surfaceCount) > 0);

    const canvasBuffer = await canvas.screenshot();
    const ratio = nonBackgroundRatio(canvasBuffer);
    assert.ok(ratio >= 0.05, `inspection canvas ratio ${ratio} is below 0.05`);
    await page.locator('[data-testid="inspection-workspace"]').screenshot({
      path: path.join(outputDir, "desktop-3d.png"),
    });
    console.log("parameter inspection desktop 3D: PASS");

    await page.locator('[data-testid="inspection-tab-quad"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="quad"]').waitFor();
    await page.locator('[data-testid="inspection-workspace"]').screenshot({
      path: path.join(outputDir, "desktop-quad.png"),
    });
    console.log("parameter inspection desktop Quad: PASS");

    await page.setViewportSize({ width: 768, height: 1100 });
    await page.locator('[data-testid="inspection-tab-s_q"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="s_q"]').waitFor();
    await page.locator('[data-testid="inspection-workspace"]').screenshot({
      path: path.join(outputDir, "narrow-s-q.png"),
    });
    console.log("parameter inspection narrow S-Q: PASS");
    console.log(`inspection renderer count: ${rendererCount}`);
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
