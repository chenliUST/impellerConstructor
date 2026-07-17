from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (  # noqa: E402
    _blend_measured_cap_target,
)


def test_measured_cap_target_changes_interior_without_breaking_c2_boundary_stencil():
    scaffold = [
        [0.0, -1.0],
        [-0.05, -0.75],
        [-0.15, -0.50],
        [-0.25, 0.0],
        [-0.15, 0.50],
        [-0.05, 0.75],
        [0.0, 1.0],
    ]
    target = {
        "degree": 2,
        "knots": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        "weights": [1.0, 1.0, 1.0],
        "control_points_local_mm": [[0.0, -1.0], [-1.0, 0.0], [0.0, 1.0]],
    }

    resolved, evidence = _blend_measured_cap_target(
        scaffold,
        target,
        streamwise_metric_scale_mm=1.0,
    )

    assert evidence["status"] == "APPLIED"
    assert resolved[:3] == scaffold[:3]
    assert resolved[-3:] == scaffold[-3:]
    assert resolved[len(resolved) // 2][0] < scaffold[len(scaffold) // 2][0]
    assert evidence["maximum_interior_adjustment_mm"] > 0.0


def test_invalid_measured_cap_target_falls_back_without_mutating_scaffold():
    scaffold = [[0.0, -1.0], [-0.2, 0.0], [0.0, 1.0]]

    resolved, evidence = _blend_measured_cap_target(
        scaffold,
        {"degree": 3, "control_points_local_mm": []},
        streamwise_metric_scale_mm=10.0,
    )

    assert resolved == scaffold
    assert evidence["status"] == "FALLBACK"
    assert evidence["reason"] == "v116_measured_cap_target_invalid"
