import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

const root = resolve(import.meta.dirname, "..", "..");

describe("STEP reconstruction workspace", () => {
  test("uses one shared renderer with three scissor viewports and no UV overlay", () => {
    const source = readFileSync(resolve(root, "src/components/StepComparisonScene.js"), "utf-8");
    assert.equal((source.match(/new THREE\.WebGLRenderer/g) || []).length, 1);
    assert.match(source, /setScissorTest\(true\)/);
    assert.match(source, /\["source", "reconstruction", "heatmap"\]/);
    assert.match(source, /devicePixelRatio/);
    assert.doesNotMatch(source, /uv_grid|createSurfaceUvWireOverlay|wireframe:\s*true/);
  });

  test("keeps progress, failures, unsupported features and confidence layers visible", () => {
    const source = readFileSync(resolve(root, "src/components/StepReconstructionWorkspace.js"), "utf-8");
    assert.match(source, /auditStageRows/);
    assert.match(source, /status\.failure/);
    assert.match(source, /unsupported_source_features/);
    assert.match(source, /measurement_confidence/);
    assert.match(source, /mapping_confidence/);
    assert.match(source, /Periodic phase alignment/);
    assert.match(source, /Phase-search RMS/);
    assert.match(source, /auditInProgress/);
    assert.match(source, /stepReconstructionAuditManifest\(apiBase, accepted\.audit_id\)/);
    assert.match(source, /disabled: !file \|\| auditActive/);
  });
});
