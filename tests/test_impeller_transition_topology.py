from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_transition_topology import PatchComplex


def test_add_node_accepts_points_within_tolerance():
    patch_complex = PatchComplex()

    patch_complex.add_node("shared", (0.5e-6, 0.0, 0.0))
    patch_complex.add_node("shared", (1.4e-6, 0.0, 0.0))

    assert patch_complex.boundary_node_identity_failures == []
