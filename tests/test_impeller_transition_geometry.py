from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from part_rule_synthesis.service import RuleSynthesisService


def _surface_by_id(run, surface_id: str) -> dict:
    return {
        surface["id"]: surface
        for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]
    }[surface_id]


def _grid_digest(surface: dict) -> str:
    return json.dumps(surface["uv_grid"], sort_keys=True)


def test_v08_blade_root_radius_override_changes_transition_geometry():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        baseline = service.instantiate(engine.engine_id, {})
        enlarged = service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "fillet",
                    "radius_mm": 20.0,
                }
            },
        )

    baseline_root = _surface_by_id(baseline, "blade_0_root_transition_surface")
    enlarged_root = _surface_by_id(enlarged, "blade_0_root_transition_surface")

    assert baseline_root["radius_mm"] == 8.0
    assert enlarged_root["radius_mm"] == 20.0
    assert _grid_digest(enlarged_root) != _grid_digest(baseline_root)


def test_v08_blade_root_chamfer_override_changes_transition_geometry_and_role():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        baseline = service.instantiate(engine.engine_id, {})
        chamfered = service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "chamfer",
                    "radius_mm": 8.0,
                }
            },
        )

    baseline_root = _surface_by_id(baseline, "blade_0_root_transition_surface")
    chamfered_root = _surface_by_id(chamfered, "blade_0_root_transition_surface")

    assert baseline_root["role"] == "blade_root_fillet"
    assert chamfered_root["role"] == "blade_root_chamfer"
    assert chamfered_root["treatment"] == "chamfer"
    assert _grid_digest(chamfered_root) != _grid_digest(baseline_root)
