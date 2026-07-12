from __future__ import annotations

GEOMETRY_VERSION = "1.1"
GEOMETRY_PATCH_VERSION = "1.1.2"
MATH_PARAMETERIZATION = "v1_1_2_canonical_nurbs_parameterization"
TRANSITION_GEOMETRY_STATUS = "topology_first_blade_to_blade_5_loop_surface_family_graph"
MESH_STRATEGY = "v1_1_1_all_surface_uv_grid_mesh"
SOURCE_KERNEL = "v1_1_blade_to_blade_surface_family_kernel"
LOOP_FAMILY_ID = "v1_1_default_blade_to_blade_loop_family"
DOMAIN_ID = "v1_1_blade_to_blade_s_q_domain"
COORDINATE_SYSTEM = "blade_to_blade_s_q_mm"

SPAN_STATIONS_H = [0.0, 0.25, 0.5, 0.75, 1.0]
SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
FACE_SEGMENTS = ["pressure_side", "suction_side", "leading_edge", "trailing_edge"]
JOIN_ORDER = [
    "pressure_to_leading",
    "leading_to_suction",
    "suction_to_trailing",
    "trailing_to_pressure",
]

POSITION_GAP_TOLERANCE_MM = 1.0e-6
TANGENT_ANGLE_TOLERANCE_DEG = 2.0
NORMAL_ANGLE_TOLERANCE_DEG = 20.0
CURVATURE_PROXY_MISMATCH_TOLERANCE = 0.25
