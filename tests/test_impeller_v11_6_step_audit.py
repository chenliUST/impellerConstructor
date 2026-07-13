from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from part_rule_synthesis.impeller_v11_6_step_audit import (
    AUDIT_CONTRACT_ID,
    AUDIT_RUNTIME_VERSION,
    CANONICAL_GEOMETRY_VERSION,
    StepAuditError,
    _atomic_json,
    classify_impeller_semantics,
    extract_v11_parameters,
    fit_profile_controls,
    load_step_source,
    resolve_canonical_frame,
    sanitize_step_filename,
    validate_step_header,
)
from step_fixtures import write_periodic_impeller_step


def test_v116_contract_keeps_v112_geometry_authority():
    assert AUDIT_CONTRACT_ID == "impeller_v1_1_6_step_reconstruction_audit"
    assert AUDIT_RUNTIME_VERSION == "1.1.6"
    assert CANONICAL_GEOMETRY_VERSION == "1.1.2"


def test_step_filename_is_sanitized_without_trusting_extension():
    assert sanitize_step_filename("../../outside/part.stp") == "part.stp"
    assert sanitize_step_filename(r"C:\customer\part name.bin") == "part_name.bin.step"


def test_support_profile_is_fitted_from_dense_targets_not_copied_as_poles():
    samples = [[float(index), (5.0 - index) ** 2 * 0.2] for index in range(11)]
    controls, residual = fit_profile_controls(samples, control_count=6, degree=3)
    assert len(controls) == 6
    assert controls[0] == samples[0]
    assert controls[-1] == samples[-1]
    assert controls != samples[:6]
    assert residual >= 0.0


def test_atomic_json_retries_transient_windows_replace_lock_with_unique_temp(tmp_path, monkeypatch):
    destination = tmp_path / "status.json"
    real_replace = os.replace
    replace_sources: list[Path] = []

    def transiently_locked(source, target):
        replace_sources.append(Path(source))
        if len(replace_sources) < 3:
            raise PermissionError(5, "Access is denied", str(target))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", transiently_locked)
    _atomic_json(destination, {"status": "RUNNING"})
    _atomic_json(destination, {"status": "PASS"})

    assert destination.read_text(encoding="utf-8").find('"PASS"') >= 0
    assert replace_sources[0] == replace_sources[1] == replace_sources[2]
    assert replace_sources[3] != replace_sources[0]
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_json_reports_persistence_failure_instead_of_step_parse_failure(tmp_path, monkeypatch):
    def persistently_locked(source, target):
        raise PermissionError(5, "Access is denied", str(target))

    monkeypatch.setattr(os, "replace", persistently_locked)
    monkeypatch.setattr("part_rule_synthesis.impeller_v11_6_step_audit.time.sleep", lambda _delay: None)

    with pytest.raises(StepAuditError) as raised:
        _atomic_json(tmp_path / "status.json", {"status": "RUNNING"})

    assert raised.value.reason == "v116_audit_persistence_failed"
    assert not list(tmp_path.glob("*.tmp"))


def test_synthetic_step_inventory_axis_and_periodicity(tmp_path):
    path = write_periodic_impeller_step(tmp_path / "synthetic.data", blade_count=8)
    header = validate_step_header(path)
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    semantics = classify_impeller_semantics(shape, source, frame)

    assert header["header_valid"] is True
    assert source["solid_count"] == 1
    assert source["closed_solid"] is True
    assert frame["scale"] == 1.0
    assert frame["primary_icp_applied"] is False
    assert semantics["main_blade_count"] == 8
    assert semantics["splitter_blade_count"] == 0
    assert semantics["classified_face_count"] == source["face_count"]


@pytest.mark.skipif(not os.environ.get("KS007G23B_STEP_PATH"), reason="local customer STEP not configured")
def test_optional_ks007g23b_exact_source_facts_and_mapping():
    path = Path(os.environ["KS007G23B_STEP_PATH"])
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    semantics = classify_impeller_semantics(shape, source, frame)
    mapping = extract_v11_parameters(shape, source, frame, semantics)

    assert (source["solid_count"], source["face_count"], source["edge_count"], source["vertex_count"]) == (1, 240, 666, 433)
    assert frame["outer_radius_mm"] == 51.6
    assert frame["main_bore_radius_mm"] == 7.9
    assert frame["axial_extent_mm"] == pytest.approx(36.5, abs=1.0e-4)
    assert semantics["main_blade_count"] == 13
    assert mapping["geometry_patch_version"] == "1.1.2"
    assert mapping["profile_fits"]["hub_profile_rz_mm"]["target_sample_count"] > 6
