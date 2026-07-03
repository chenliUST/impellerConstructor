from __future__ import annotations

from pathlib import Path

from part_rule_synthesis.impeller_v09_regression import run_v09_batch


def test_v09_golden_batch_writes_summary_for_selected_case(tmp_path: Path):
    summary = run_v09_batch(
        mode="golden",
        output_root=tmp_path,
        case_ids=["v09_open_default"],
    )

    assert summary["mode"] == "golden"
    assert summary["case_count"] == 1
    assert summary["pass_count"] == 1
    assert summary["fail_count"] == 0
    assert summary["cases"][0]["case_id"] == "v09_open_default"
    assert summary["cases"][0]["geometry_validation_status"] == "PASS"
    assert summary["cases"][0]["exports_written"] is True
    assert (tmp_path / "v09_batch_summary.json").exists()


def test_v09_negative_batch_records_expected_validation_failures(tmp_path: Path):
    summary = run_v09_batch(
        mode="negative",
        output_root=tmp_path,
        case_ids=["v09_negative_inverted_fillet", "v09_negative_untrimmed_transition"],
    )

    assert summary["mode"] == "negative"
    assert summary["case_count"] == 2
    assert summary["pass_count"] == 0
    assert summary["expected_fail_count"] == 2
    assert summary["fail_count"] == 0
    assert {
        case["geometry_validation_status"]
        for case in summary["cases"]
    } == {"FAIL"}
    assert {
        case["primary_failure_reason"]
        for case in summary["cases"]
    } == {"fillet_convexity_failed", "adjacent_surface_not_trimmed"}
