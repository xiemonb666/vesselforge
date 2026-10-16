from __future__ import annotations

import hashlib

import numpy as np
import pytest

from vesselforge.reference_mesh import (
    DeformationControls,
    SourceProvenance,
    deform_reference_mesh,
    jacobian_at_points,
)


def _provenance(component_count: int | None = None) -> SourceProvenance:
    return SourceProvenance(
        source_name="synthetic test mesh",
        source_url="https://example.invalid/mesh",
        license_id="CC0-1.0",
        attribution="test fixture",
        raw_source_sha256=hashlib.sha256(b"test source").hexdigest(),
        scale_evidence="synthetic coordinates are defined in millimetres",
        source_component_count=component_count,
    )


def test_identity_controls_preserve_coordinates_and_face_indices() -> None:
    vertices = np.array(
        [[1.0, 2.0, -1.0], [2.0, 2.0, 0.0], [1.0, 3.0, 1.0], [1.5, 2.5, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int32)
    attributes = np.arange(12, dtype=np.uint8).reshape(4, 3)

    result = deform_reference_mesh(
        vertices,
        faces,
        center=(0.0, 0.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        source_unit_scale_to_mm=1.0,
        controls=DeformationControls(),
        provenance=_provenance(),
        vertex_attributes=attributes,
    )

    np.testing.assert_allclose(result.vertices_mm, vertices, atol=0.0, rtol=0.0)
    np.testing.assert_array_equal(result.faces, faces)
    np.testing.assert_array_equal(result.vertex_attributes, attributes)
    assert result.faces.dtype == faces.dtype
    assert result.receipt["mesh"]["parts_discarded"] is False
    assert result.receipt["mesh"]["vertex_attributes_preserved"] is True
    assert result.receipt["mesh"]["source_face_count"] == 2


def test_known_affine_transform_scales_height_and_radius_as_documented() -> None:
    vertices = np.array(
        [[1.0, 0.0, -2.0], [0.0, 2.0, 0.0], [-1.0, 0.0, 2.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    controls = DeformationControls(height_scale=1.02, radial_scale=1.03)
    result = deform_reference_mesh(
        vertices,
        faces,
        center=(0.0, 0.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        source_unit_scale_to_mm=2.0,
        controls=controls,
        provenance=_provenance(),
    )

    radial_factor = 2.0 * 1.03
    axial_factor = 2.0 * 1.02
    np.testing.assert_allclose(
        result.vertices_mm,
        vertices * np.array([radial_factor, radial_factor, axial_factor]),
        atol=1e-12,
        rtol=1e-12,
    )
    assert result.receipt["transform"]["source_unit_scale_to_mm"] == 2.0
    assert result.receipt["transform"]["target_height_mm"] == pytest.approx(8.16)


def test_arbitrary_axis_uses_the_same_affine_scale_in_its_local_frame() -> None:
    direction = np.array([1.0, 2.0, 3.0])
    direction /= np.linalg.norm(direction)
    center = np.array([4.0, -2.0, 1.0])
    controls = DeformationControls(height_scale=1.01, radial_scale=1.02)
    jacobian = jacobian_at_points(
        np.array([[4.2, -1.7, 1.6], [3.1, -2.2, 2.4]]),
        center=center,
        axis=direction,
        source_axial_bounds=(-1.0, 1.0),
        source_unit_scale_to_mm=2.0,
        controls=controls,
    )
    radial_scale = 2.0 * 1.02
    axial_scale = 2.0 * 1.01
    projector = np.eye(3) - np.outer(direction, direction)
    expected = radial_scale * projector + axial_scale * np.outer(direction, direction)
    np.testing.assert_allclose(jacobian, np.broadcast_to(expected, jacobian.shape), atol=1e-12)


def test_height_scale_changes_only_axial_coordinates_and_bounds() -> None:
    vertices = np.array(
        [[1.0, 0.0, -1.0], [2.0, 1.0, 0.0], [-1.0, 2.0, 1.0], [0.0, -2.0, 0.25]]
    )
    faces = np.empty((0, 3), dtype=np.int64)
    common = {
        "center": (0.0, 0.0, 0.0),
        "axis": (0.0, 0.0, 1.0),
        "source_unit_scale_to_mm": 10.0,
        "provenance": _provenance(),
    }
    baseline = deform_reference_mesh(
        vertices, faces, controls=DeformationControls(), **common
    )
    taller = deform_reference_mesh(
        vertices, faces, controls=DeformationControls(height_scale=1.05), **common
    )

    np.testing.assert_allclose(taller.vertices_mm[:, :2], baseline.vertices_mm[:, :2])
    np.testing.assert_allclose(
        np.ptp(taller.vertices_mm[:, :2], axis=0),
        np.ptp(baseline.vertices_mm[:, :2], axis=0),
    )
    assert np.ptp(taller.vertices_mm[:, 2]) == pytest.approx(
        1.05 * np.ptp(baseline.vertices_mm[:, 2])
    )
    assert taller.receipt["transform"]["target_height_mm"] == pytest.approx(21.0)


def test_width_scale_changes_only_radial_coordinates_and_bounds() -> None:
    vertices = np.array(
        [[1.0, 0.0, -1.0], [2.0, 1.0, 0.0], [-1.0, 2.0, 1.0], [0.0, -2.0, 0.25]]
    )
    faces = np.empty((0, 3), dtype=np.int64)
    common = {
        "center": (0.0, 0.0, 0.0),
        "axis": (0.0, 0.0, 1.0),
        "source_unit_scale_to_mm": 10.0,
        "provenance": _provenance(),
    }
    baseline = deform_reference_mesh(
        vertices, faces, controls=DeformationControls(), **common
    )
    wider = deform_reference_mesh(
        vertices, faces, controls=DeformationControls(radial_scale=1.08), **common
    )

    np.testing.assert_allclose(wider.vertices_mm[:, 2], baseline.vertices_mm[:, 2])
    assert np.ptp(wider.vertices_mm[:, 2]) == pytest.approx(
        np.ptp(baseline.vertices_mm[:, 2])
    )
    assert np.ptp(wider.vertices_mm[:, :2], axis=0).max() > np.ptp(
        baseline.vertices_mm[:, :2], axis=0
    ).max()


def test_analytic_jacobian_matches_finite_difference_and_has_positive_determinant() -> None:
    direction = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    direction /= np.linalg.norm(direction)
    tangent_one = np.cross(direction, np.array([0.0, 0.0, 1.0]))
    tangent_one /= np.linalg.norm(tangent_one)
    tangent_two = np.cross(direction, tangent_one)
    center = np.array([0.2, -0.1, 0.3], dtype=np.float64)
    points = np.array(
        [
            center + 0.7 * direction + 0.3 * tangent_one - 0.1 * tangent_two,
            center - 0.6 * direction + 0.2 * tangent_one + 0.2 * tangent_two,
        ],
        dtype=np.float64,
    )
    controls = DeformationControls(
        height_scale=1.01,
        radial_scale=0.98,
        belly_fullness=0.045,
        upperbody_width=-0.02,
        mouth_width=0.015,
        foot_width=0.03,
    )
    axis = direction
    bounds = (-1.0, 1.0)
    unit_scale = 1.25
    jacobian = jacobian_at_points(
        points,
        center=center,
        axis=axis,
        source_axial_bounds=bounds,
        source_unit_scale_to_mm=unit_scale,
        controls=controls,
    )
    assert np.isfinite(jacobian).all()
    assert np.linalg.det(jacobian).min() > 0.0

    epsilon = 1e-6
    for point_index, point in enumerate(points):
        numeric = np.empty((3, 3), dtype=np.float64)
        for coordinate in range(3):
            offset = np.zeros(3)
            offset[coordinate] = epsilon
            probe_vertices = np.array(
                [center - direction, center + direction, point + offset]
            )
            probe_vertices_minus = np.array(
                [center - direction, center + direction, point - offset]
            )
            plus = deform_reference_mesh(
                probe_vertices,
                np.empty((0, 3), dtype=np.int64),
                center=center,
                axis=axis,
                source_unit_scale_to_mm=unit_scale,
                controls=controls,
                provenance=_provenance(),
            ).vertices_mm
            minus = deform_reference_mesh(
                probe_vertices_minus,
                np.empty((0, 3), dtype=np.int64),
                center=center,
                axis=axis,
                source_unit_scale_to_mm=unit_scale,
                controls=controls,
                provenance=_provenance(),
            ).vertices_mm
            numeric[:, coordinate] = (plus[2] - minus[2]) / (2 * epsilon)
        np.testing.assert_allclose(jacobian[point_index], numeric, atol=2e-6, rtol=2e-6)


def test_invalid_scale_frame_and_controls_are_rejected() -> None:
    with pytest.raises(ValueError, match="exploration range"):
        DeformationControls(height_scale=1.2)
    with pytest.raises(ValueError, match="exploration range"):
        DeformationControls(height_scale=0.0)

    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 2.0]])
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    kwargs = {
        "center": (0.0, 0.0, 0.0),
        "axis": (0.0, 0.0, 1.0),
        "controls": DeformationControls(),
        "provenance": _provenance(),
    }
    with pytest.raises(ValueError, match="source_unit_scale_to_mm must be positive"):
        deform_reference_mesh(vertices, faces, source_unit_scale_to_mm=0.0, **kwargs)
    with pytest.raises(ValueError, match="non-zero length"):
        deform_reference_mesh(
            vertices,
            faces,
            source_unit_scale_to_mm=1.0,
            **{**kwargs, "axis": (0.0, 0.0, 0.0)},
        )


def test_disconnected_components_and_all_vertex_payloads_are_retained() -> None:
    # Two remote triangle islands stand in for a main body plus small scan
    # fragments. The deformer retains the original indexed topology verbatim.
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.5],
            [0.0, 1.0, 1.0],
            [20.0, 0.0, 0.0],
            [21.0, 0.0, 0.5],
            [20.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    colors = np.array([[i, i + 1, i + 2] for i in range(6)], dtype=np.uint8)
    result = deform_reference_mesh(
        vertices,
        faces,
        center=(0.0, 0.0, 0.5),
        axis=(0.0, 0.0, 1.0),
        source_unit_scale_to_mm=1.0,
        controls=DeformationControls(),
        provenance=_provenance(component_count=2),
        vertex_attributes=colors,
    )

    np.testing.assert_array_equal(result.faces, faces)
    np.testing.assert_array_equal(result.vertex_attributes, colors)
    assert result.vertices_mm.shape == vertices.shape
    assert result.receipt["mesh"]["derived_face_count"] == 2
    assert result.receipt["mesh"]["source_component_count_reported"] == 2
    assert result.receipt["mesh"]["parts_discarded"] is False
