import sys
from pathlib import Path

# ruff: noqa: E402

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_axis_first_pipeline import (
    _support_profile_sample_frames,
)


def test_profile_normals_follow_meridional_support_and_point_toward_blade():
    root_half = 2.0**-0.5
    footprint = [[15.0, 0.0, 5.0], [16.0, 0.0, 6.0]]
    retained = [
        [15.0 - 2.0 * root_half + 0.5 * root_half, 0.0, 5.0 + 2.0 * root_half + 0.5 * root_half],
        [16.0 - 2.0 * root_half + 0.5 * root_half, 0.0, 6.0 + 2.0 * root_half + 0.5 * root_half],
    ]

    normals, streamwise = _support_profile_sample_frames(
        np.eye(4),
        [[10.0, 0.0], [20.0, 10.0]],
        footprint,
        retained,
    )

    np.testing.assert_allclose(
        normals,
        [[-root_half, 0.0, root_half], [-root_half, 0.0, root_half]],
        atol=1.0e-9,
    )
    np.testing.assert_allclose(streamwise, [0.5, 0.6], atol=1.0e-6)


def test_compact_v112_support_fit_uses_its_cubic_profile_without_optional_arrays():
    controls = [
        [10.0, 20.0],
        [11.0, 16.0],
        [13.0, 12.0],
        [16.0, 8.0],
        [20.0, 4.0],
        [25.0, 0.0],
    ]
    normals, streamwise = _support_profile_sample_frames(
        np.eye(4),
        {"control_points_rz_mm": controls},
        [[15.0, 0.0, 9.0]],
        [[14.0, 0.0, 10.0]],
    )

    assert len(normals) == 1
    np.testing.assert_allclose(np.linalg.norm(normals[0]), 1.0, atol=1.0e-9)
    assert 0.0 <= streamwise[0] <= 1.0
