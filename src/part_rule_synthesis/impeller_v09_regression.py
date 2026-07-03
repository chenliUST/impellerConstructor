from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.service import RuleSynthesisService


def run_v09_batch(
    *,
    mode: str,
    output_root: Path | str,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    cases = _registry_cases(mode, case_ids)
    case_results = [_run_case(mode, output_root, case) for case in cases]
    summary = _batch_summary(mode, case_results)
    (output_root / "v09_batch_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _registry_cases(mode: str, case_ids: list[str] | None) -> list[dict[str, Any]]:
    bundle = load_impeller_dsl_bundle("v0_9")
    registry = bundle.golden_case_registries["impeller_v0_9_golden_cases"]
    selected = [
        case
        for case in registry["cases"]
        if case.get("category") == mode
    ]
    if case_ids is not None:
        requested = set(case_ids)
        selected = [case for case in selected if case["case_id"] in requested]
        missing = requested - {case["case_id"] for case in selected}
        if missing:
            raise ValueError(f"unknown V0.9 {mode} case ids: {sorted(missing)}")
    if not selected:
        raise ValueError(f"no V0.9 {mode} cases selected")
    return selected


def _run_case(mode: str, output_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    if mode == "negative":
        return _run_negative_case(case)
    service = RuleSynthesisService(output_root / "runs", model_output_root=output_root / "Model Output")
    engine = service.synthesize("impeller", case["preset_id"])
    run = service.instantiate(
        engine.engine_id,
        case.get("parameter_overrides", {}),
        transition_overrides=case.get("transition_overrides"),
    )
    manifest = run.manifest
    report = manifest.get("geometry_validation_report", {})
    case_dir = output_root / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "case_id": case["case_id"],
        "category": case.get("category"),
        "preset_id": case.get("preset_id"),
        "status": "PASS" if manifest.get("geometry_validation_status") == "PASS" else "FAIL",
        "geometry_validation_status": manifest.get("geometry_validation_status"),
        "exports_written": all(Path(path).exists() for path in manifest.get("exports", {}).values()),
        "run_id": manifest.get("run_id"),
        "transition_surface_count": report.get("transition_validation_summary", {}).get(
            "transition_surface_count",
            0,
        ),
        "blocking_failure_count": len(report.get("blocking_failures", [])),
        "step_path": manifest.get("exports", {}).get("step"),
        "stl_path": manifest.get("exports", {}).get("stl"),
    }


def _run_negative_case(case: dict[str, Any]) -> dict[str, Any]:
    if case["case_id"] == "v09_negative_inverted_fillet":
        report = _synthetic_inverted_fillet_report()
    elif case["case_id"] == "v09_negative_untrimmed_transition":
        report = _synthetic_untrimmed_transition_report()
    else:
        raise ValueError(f"unsupported V0.9 negative case: {case['case_id']}")
    failures = report.get("blocking_failures", [])
    return {
        "case_id": case["case_id"],
        "category": case.get("category"),
        "preset_id": case.get("preset_id"),
        "status": "EXPECTED_FAIL" if report["geometry_validation_status"] == "FAIL" else "UNEXPECTED_PASS",
        "geometry_validation_status": report["geometry_validation_status"],
        "exports_written": False,
        "blocking_failure_count": len(failures),
        "primary_failure_reason": failures[0]["reason"] if failures else "",
    }


def _batch_summary(mode: str, case_results: list[dict[str, Any]]) -> dict[str, Any]:
    pass_count = sum(1 for case in case_results if case["status"] == "PASS")
    expected_fail_count = sum(1 for case in case_results if case["status"] == "EXPECTED_FAIL")
    unexpected_pass_count = sum(1 for case in case_results if case["status"] == "UNEXPECTED_PASS")
    fail_count = sum(1 for case in case_results if case["status"] == "FAIL") + unexpected_pass_count
    return {
        "version": "0.9",
        "mode": mode,
        "case_count": len(case_results),
        "pass_count": pass_count,
        "expected_fail_count": expected_fail_count,
        "fail_count": fail_count,
        "warning_count": 0,
        "worst_transition_metrics": {
            "max_blocking_failure_count": max(
                (case.get("blocking_failure_count", 0) for case in case_results),
                default=0,
            ),
            "max_transition_surface_count": max(
                (case.get("transition_surface_count", 0) for case in case_results),
                default=0,
            ),
        },
        "cases": case_results,
    }


def _synthetic_inverted_fillet_report() -> dict[str, Any]:
    graph = _synthetic_valid_root_graph()
    transition = graph["surfaces"][-1]
    transition["transition_quality"]["convexity_status"] = "FAIL"
    transition["transition_quality"]["fillet_convex_signed_bulge_mm"] = -0.1
    return build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 8.0},
        facets={},
        transition_policies=_root_policy(),
        surface_graph=graph,
    )


def _synthetic_untrimmed_transition_report() -> dict[str, Any]:
    graph = _synthetic_valid_root_graph()
    graph["surfaces"][0].pop("trimmed_boundaries")
    return build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 8.0},
        facets={},
        transition_policies=_root_policy(),
        surface_graph=graph,
    )


def _synthetic_valid_root_graph() -> dict[str, Any]:
    return {
        "transition_geometry_status": "validated_transition_surface_graph",
        "surfaces": [
            {
                "id": "blade_0_pressure_surface",
                "role": "blade_pressure",
                "trimmed_boundaries": {
                    "hub_root_pressure": {"edge_treatment_site_id": "blade_0.pressure_root_to_hub"}
                },
            },
            {
                "id": "hub_revolve_surface",
                "role": "hub",
                "trim_exclusion_regions": [
                    {"edge_treatment_site_id": "blade_0.pressure_root_to_hub"},
                    {"edge_treatment_site_id": "blade_0.suction_root_to_hub"},
                ],
            },
            {
                "id": "blade_0_suction_surface",
                "role": "blade_suction",
                "trimmed_boundaries": {
                    "hub_root_suction": {"edge_treatment_site_id": "blade_0.suction_root_to_hub"}
                },
            },
            {
                "id": "blade_0_pressure_root_transition_surface",
                "role": "blade_pressure_root_fillet",
                "edge_family": "blade_root_to_hub",
                "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "radius_mm": 8.0,
                "transition_geometry": "validated_fillet_patch",
                "transition_quality": {
                    "convexity_status": "PASS",
                    "fillet_convex_signed_bulge_mm": 0.6,
                    "radius_max_error_mm": 0.0,
                    "g0_boundary_max_error_mm": 0.0,
                    "g1_tangent_max_error_deg": 12.0,
                },
            },
            {
                "id": "blade_0_suction_root_transition_surface",
                "role": "blade_suction_root_fillet",
                "edge_family": "blade_root_to_hub",
                "edge_treatment_site_id": "blade_0.suction_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "radius_mm": 8.0,
                "transition_geometry": "validated_fillet_patch",
                "transition_quality": {
                    "convexity_status": "PASS",
                    "fillet_convex_signed_bulge_mm": 0.6,
                    "radius_max_error_mm": 0.0,
                    "g0_boundary_max_error_mm": 0.0,
                    "g1_tangent_max_error_deg": 12.0,
                },
            },
        ],
        "edge_treatment_sites": [
            {
                "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "radius_mm": 8.0,
                "adjacent_surface_ids": ["blade_0_pressure_surface", "hub_revolve_surface"],
                "transition_surface_ids": ["blade_0_pressure_root_transition_surface"],
            },
            {
                "edge_treatment_site_id": "blade_0.suction_root_to_hub",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "radius_mm": 8.0,
                "adjacent_surface_ids": ["blade_0_suction_surface", "hub_revolve_surface"],
                "transition_surface_ids": ["blade_0_suction_root_transition_surface"],
            }
        ],
    }


def _root_policy() -> dict[str, dict[str, Any]]:
    return {
        "blade_root_to_hub.default": {
            "enabled": True,
            "treatment": "fillet",
            "radius_mm": 8.0,
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run V0.9 impeller kernel regression batches.")
    parser.add_argument("--mode", choices=["golden", "negative"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    args = parser.parse_args(argv)
    summary = run_v09_batch(mode=args.mode, output_root=Path(args.output), case_ids=args.case_ids)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
