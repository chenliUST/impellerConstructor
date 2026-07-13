import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  auditArtifactUrls,
  auditInProgress,
  auditStageRows,
  comparisonViewportRects,
  heatmapLegend,
  parameterDifferenceRows,
} from "./stepReconstructionModel.js";

describe("STEP reconstruction model", () => {
  test("keeps three geometry panes in a stable 2x2 comparison grid", () => {
    assert.deepEqual(comparisonViewportRects(1001, 801), {
      source: { x: 0, y: 400, width: 500, height: 401 },
      reconstruction: { x: 500, y: 400, width: 501, height: 401 },
      heatmap: { x: 0, y: 0, width: 500, height: 400 },
    });
  });

  test("reports persistent progress and terminal failure state", () => {
    const rows = auditStageRows({ status: "FAILED", current_stage: "frame_resolved", completed_stages: ["uploaded", "brep_loaded"] });
    assert.equal(rows.find((row) => row.id === "uploaded").state, "complete");
    assert.equal(rows.find((row) => row.id === "frame_resolved").state, "failed");
    assert.equal(auditInProgress({ status: "QUEUED" }), true);
    assert.equal(auditInProgress({ status: "RUNNING" }), true);
    assert.equal(auditInProgress({ status: "PASS" }), false);
    assert.equal(auditInProgress({ status: "FAILED" }), false);
  });

  test("artifact urls and report values remain audit scoped", () => {
    const urls = auditArtifactUrls("http://127.0.0.1:8061/", "step-audit-abc");
    assert.match(urls.source, /step-audit-abc\/artifacts\/source\.stl$/);
    const manifest = {
      comparison: { bidirectional: { minimum_mm: 0, median_mm: 0.2, p95_mm: 1.2, maximum_mm: 2.5 } },
      reconstruction: { parameters: { blade_count: 13 } },
      parameter_mapping: { parameter_rows: [{ feature_id: "parameter_values.blade_count", source_measurement: 13 }] },
    };
    assert.deepEqual(heatmapLegend(manifest).map((row) => row.label), ["Min", "Median", "P95", "Max"]);
    assert.equal(parameterDifferenceRows(manifest)[0].delta, 0);
  });
});
