from __future__ import annotations

import numpy as np
import pytest
import cadquery as cq

from part_rule_synthesis.impeller_v11_6_section_recovery import (
    SectionRecoveryError,
    measure_root_attachment,
    measure_shroud_attachment,
)


def _rectangle(z: float, *, half_width: float = 1.0) -> np.ndarray:
    return np.asarray(
        [
            (-3.0, -half_width, z),
            (3.0, -half_width, z),
            (3.0, half_width, z),
            (-3.0, half_width, z),
        ],
        dtype=float,
    )


def _source_fixture(kind: str) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    if kind == "root":
        footprint = _rectangle(0.0, half_width=1.0)
        retained = _rectangle(1.4, half_width=0.65)
        shape = (
            cq.Workplane("XY")
            .rect(6.0, 2.0)
            .workplane(offset=1.4)
            .rect(6.0, 1.3)
            .loft(combine=True)
            .val()
        )
        footprint_z, retained_z = 0.0, 1.4
    else:
        footprint = _rectangle(10.0, half_width=0.8)
        retained = _rectangle(9.35, half_width=0.55)
        shape = (
            cq.Workplane("XY")
            .rect(6.0, 1.1)
            .workplane(offset=0.65)
            .rect(6.0, 1.6)
            .loft(combine=True)
            .val()
            .translate((0.0, 0.0, 9.35))
        )
        footprint_z, retained_z = 10.0, 9.35
    edges = {f"edge_{index}": edge for index, edge in enumerate(shape.Edges())}
    faces = {f"face_{index}": face for index, face in enumerate(shape.Faces())}
    footprint_edges = tuple(
        edge_id
        for edge_id, edge in edges.items()
        if edge.BoundingBox().zlen < 1.0e-8
        and abs(edge.BoundingBox().zmin - footprint_z) < 1.0e-8
    )
    retained_edges = tuple(
        edge_id
        for edge_id, edge in edges.items()
        if edge.BoundingBox().zlen < 1.0e-8
        and abs(edge.BoundingBox().zmin - retained_z) < 1.0e-8
    )
    span_edge_ids = tuple(
        edge_id for edge_id, edge in edges.items() if edge.BoundingBox().zlen > 0.6
    )
    termination_edge_id = span_edge_ids[0]
    termination_vertices = edges[termination_edge_id].Vertices()
    termination = np.asarray(
        [
            (vertex.X, vertex.Y, vertex.Z)
            for vertex in termination_vertices
        ]
    )
    return footprint, retained, {
        "source_face_ids": tuple(faces),
        "footprint_source_edge_ids": footprint_edges,
        "retained_source_edge_ids": retained_edges,
        "span_direction_source_ids": span_edge_ids,
        "termination_boundary_xyz_mm": termination,
        "termination_source_edge_ids": (termination_edge_id,),
        "source_shape": shape,
        "source_edges_by_id": edges,
        "source_faces_by_id": faces,
        "provenance_kind": "occt_source_adjacency",
    }


def test_root_lift_and_attachment_width_are_measured_from_source_boundaries():
    footprint, retained, evidence = _source_fixture("root")
    result = measure_root_attachment(
        footprint,
        retained,
        width_direction_xyz=(0.0, 1.0, 0.0),
        **evidence,
    )

    assert result.attachment_kind == "root"
    assert result.lift_mm == pytest.approx(float(np.hypot(1.4, 0.35)))
    assert result.attachment_width_mm == pytest.approx(2.0)
    assert result.copied_from_preset is False
    assert result.correspondence_method == "nearest_support_tangent_projection"
    assert result.source_measurement is True
    assert result.promotable is True
    assert result.termination_point_count == 2
    assert len(result.source_face_ids) == 6
    assert all(len(faces) == 2 for faces in result.adjacency_evidence.values())
    assert result.span_direction_angular_residual_max_deg <= 1.0e-6
    assert result.span_direction_angular_tolerance_deg == pytest.approx(5.0)
    assert len(result.span_direction_evidence) == len(retained)
    assert all(item["source_entity_id"] in evidence["span_direction_source_ids"] for item in result.span_direction_evidence)
    assert all(len(item["sample_xyz_mm"]) == 3 for item in result.span_direction_evidence)
    assert all(len(item["measured_direction_xyz"]) == 3 for item in result.span_direction_evidence)


def test_closed_shroud_reuses_attachment_measurement_with_reversed_material_side():
    footprint, retained, evidence = _source_fixture("shroud")
    result = measure_shroud_attachment(
        footprint,
        retained,
        width_direction_xyz=(0.0, 1.0, 0.0),
        **evidence,
    )

    assert result.attachment_kind == "shroud"
    assert result.material_side == -1
    assert result.local_span_direction_xyz == (0.0, 0.0, -1.0)
    assert result.lift_mm == pytest.approx(float(np.hypot(0.65, 0.25)))
    assert result.attachment_width_mm == pytest.approx(1.6)


def test_first_blade_body_boundary_must_be_above_the_source_root_blend():
    with pytest.raises(SectionRecoveryError) as caught:
        measure_root_attachment(
            _rectangle(0.0),
            _rectangle(0.0, half_width=0.7),
            local_span_direction_xyz=(0.0, 0.0, 1.0),
            allow_synthetic=True,
        )

    assert caught.value.reason == "v116_root_attachment_measurement_failed"


def test_arbitrary_arrays_without_adjacency_ids_cannot_claim_source_measurement():
    with pytest.raises(SectionRecoveryError) as caught:
        measure_root_attachment(
            _rectangle(0.0),
            _rectangle(1.0, half_width=0.7),
            local_span_directions_xyz=[(0.0, 0.0, 1.0)] * 4,
        )
    assert caught.value.reason == "v116_root_attachment_measurement_failed"
    assert "provenance" in str(caught.value)


def test_synthetic_attachment_is_explicitly_non_promotable():
    result = measure_root_attachment(
        _rectangle(0.0),
        _rectangle(1.0, half_width=0.7),
        local_span_direction_xyz=(0.0, 0.0, 1.0),
        width_direction_xyz=(0.0, 1.0, 0.0),
        allow_synthetic=True,
    )
    assert result.source_measurement is False
    assert result.promotable is False
    assert result.provenance_kind == "synthetic_caller_arrays"
    assert result.footprint_source == "synthetic_caller_array"


def test_existing_arbitrary_face_id_cannot_authenticate_caller_span_directions():
    footprint, retained, evidence = _source_fixture("root")
    evidence["span_direction_source_ids"] = (next(iter(evidence["source_faces_by_id"])),)

    with pytest.raises(SectionRecoveryError) as caught:
        measure_root_attachment(
            footprint,
            retained,
            local_span_directions_xyz=[(0.0, 0.0, 1.0)] * 4,
            width_direction_xyz=(0.0, 1.0, 0.0),
            **evidence,
        )

    assert caught.value.reason == "v116_root_attachment_measurement_failed"
    assert "edge tangent" in str(caught.value)


def test_caller_span_direction_must_match_authenticated_occt_edge_tangent():
    footprint, retained, evidence = _source_fixture("root")

    with pytest.raises(SectionRecoveryError) as caught:
        measure_root_attachment(
            footprint,
            retained,
            local_span_directions_xyz=[(1.0, 0.0, 0.0)] * 4,
            width_direction_xyz=(0.0, 1.0, 0.0),
            **evidence,
        )

    assert caught.value.reason == "v116_root_attachment_measurement_failed"
    assert caught.value.details["angular_residual_max_deg"] > 5.0


def test_shroud_wrapper_rejects_positive_material_side_override():
    footprint, retained, evidence = _source_fixture("shroud")

    with pytest.raises(ValueError, match="material_side=-1"):
        measure_shroud_attachment(
            footprint,
            retained,
            local_span_directions_xyz=[(0.0, 0.0, 1.0)] * 4,
            width_direction_xyz=(0.0, 1.0, 0.0),
            material_side=1,
            **evidence,
        )
