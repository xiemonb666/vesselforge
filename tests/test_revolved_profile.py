from __future__ import annotations

import math

import cadquery as cq
import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane

from vesselforge.revolved_profile import (
    FootedBowlDesign,
    MeridianSection,
    MeridianSegment,
    build_revolved_solid,
    make_footed_bowl_section,
    meridian_volume_mm3,
    normal_offset_point_and_derivative,
)


def test_section_validation_rejects_open_and_self_intersecting_profiles() -> None:
    open_section = MeridianSection(
        name="open",
        segments=(
            MeridianSegment("base", "line", ((1.0, 1.0), (3.0, 1.0))),
            MeridianSegment("foot", "line", ((3.0, 1.0), (3.0, 3.0))),
            MeridianSegment("body_outer", "line", ((3.0, 3.0), (1.1, 1.0))),
        ),
    )
    with pytest.raises(ValueError, match="section is open"):
        open_section.validate()

    bow_tie = MeridianSection(
        name="self_intersecting",
        segments=(
            MeridianSegment("base", "line", ((1.0, 1.0), (5.0, 5.0))),
            MeridianSegment("foot", "line", ((5.0, 5.0), (1.0, 4.0))),
            MeridianSegment("body_outer", "line", ((1.0, 4.0), (5.0, 1.0))),
            MeridianSegment("rim", "line", ((5.0, 1.0), (4.0, 0.0))),
            MeridianSegment("base", "line", ((4.0, 0.0), (1.0, 1.0))),
        ),
    )
    with pytest.raises(ValueError, match="self-intersects"):
        bow_tie.validate()


def test_true_normal_offset_matches_a_hand_checkable_circle() -> None:
    radius = 4.75
    distance = 1.25
    semicircle = MeridianSegment(
        role="body_inner",
        kind="arc",
        points=((radius, 0.0), (0.0, radius), (-radius, 0.0)),
    )
    for parameter in np.linspace(0.0, 1.0, 17):
        point, derivative = normal_offset_point_and_derivative(semicircle, float(parameter), distance)
        assert np.linalg.norm(point) == pytest.approx(radius + distance, abs=2e-12)
        assert np.isfinite(derivative).all()


def test_meridian_integral_matches_exact_sphere_volume() -> None:
    radius = 7.25
    diagonal = radius / math.sqrt(2.0)
    section = MeridianSection(
        name="solid_sphere_meridian",
        segments=(
            MeridianSegment("body_outer", "arc", ((0.0, radius), (diagonal, diagonal), (radius, 0.0))),
            MeridianSegment("body_outer", "arc", ((radius, 0.0), (diagonal, -diagonal), (0.0, -radius))),
            MeridianSegment("base", "line", ((0.0, -radius), (0.0, radius))),
        ),
    )
    assert meridian_volume_mm3(section) == pytest.approx(4.0 * math.pi * radius**3 / 3.0, rel=2e-13)


def test_footed_daily_candidate_is_one_closed_solid_with_real_contact_and_cavity() -> None:
    design = FootedBowlDesign(
        name="daily_aberdeen_size_reference_candidate_v6",
        rim_outer_diameter_mm=108.0,
        overall_height_mm=53.0,
        wall_thickness_mm=2.0,
        foot_outer_diameter_mm=31.0,
        foot_height_mm=7.0,
        body_floor_radius_mm=10.5,
        body_floor_z_mm=10.0,
        underside_recess_z_mm=6.5,
        foot_contact_width_mm=2.0,
        rim_tangent_degrees=75.0,
        body_start_handle_fraction=0.60,
        body_end_handle_height_fraction=0.22,
    )
    section, profile_info = make_footed_bowl_section(design)
    shape, lineage = build_revolved_solid(section)

    assert shape.isValid()
    assert len(shape.Solids()) == 1
    assert len(shape.Shells()) == 1
    assert shape.Shells()[0].wrapped.Closed()
    assert shape.Volume() == pytest.approx(meridian_volume_mm3(section), rel=1e-9)
    bounds = shape.BoundingBox()
    assert bounds.xlen == pytest.approx(108.0, abs=1e-5)
    assert bounds.ylen == pytest.approx(108.0, abs=1e-5)
    assert bounds.zmin == pytest.approx(0.0, abs=1e-6)
    assert bounds.zlen == pytest.approx(53.0, abs=1e-5)
    # The OCC B-rep extrema, not just the constructed points, must realize the
    # exact round-cap envelope at D/2 and H for the declared tangent angle.
    assert bounds.xmax == pytest.approx(54.0, abs=1e-5)
    assert bounds.zmax == pytest.approx(53.0, abs=1e-5)

    # A point in the open bowl cavity stays outside material; the corresponding
    # midpoint between the designed inner/outer body is inside the solid.
    assert not shape.isInside(cq.Vector(0.0, 0.0, 28.0), 1e-7)
    assert shape.isInside(cq.Vector(17.5, 0.0, 9.0), 1e-7)
    assert shape.isInside(cq.Vector(5.0, 0.0, 8.25), 1e-7)  # solid base below the cavity floor
    assert shape.isInside(cq.Vector(14.5, 0.0, 3.5), 1e-7)  # material in the attached foot ring
    assert not shape.isInside(cq.Vector(60.0, 0.0, 20.0), 1e-7)

    assert set(lineage["region_roles"]) == {"body_outer", "body_inner", "rim", "base", "foot"}
    assert lineage["face_count"] == len(shape.Faces())
    assert all(row["role"] in lineage["region_roles"] for row in lineage["faces"].values())

    # The support ring is an actual planar B-rep face at Z=0, whose source
    # section segment is the finite contact annulus.
    support_segments = [
        i
        for i, segment in enumerate(section.segments)
        if segment.role == "foot"
        and segment.kind == "line"
        and segment.start[1] == pytest.approx(0.0)
        and segment.end[1] == pytest.approx(0.0)
        and segment.start[0] > segment.end[0]
    ]
    assert len(support_segments) == 1
    support_index = support_segments[0]
    support_faces = [
        int(face_index)
        for face_index, row in lineage["faces"].items()
        if support_index in row["source_segment_indices"]
    ]
    assert len(support_faces) == 1
    support_face = shape.Faces()[support_faces[0]]
    assert BRepAdaptor_Surface(support_face.wrapped, True).GetType() == GeomAbs_Plane
    assert support_face.BoundingBox().zmin == pytest.approx(0.0, abs=1e-7)
    assert support_face.BoundingBox().zmax == pytest.approx(0.0, abs=1e-7)
    assert profile_info["foot"]["contact_width_mm"] > 0.0
    assert profile_info["base"]["central_base_thickness_mm"] > design.wall_thickness_mm
    assert profile_info["foot"]["height_mm"] == pytest.approx(7.0)


def test_footed_design_rejects_a_folded_base_wall_junction() -> None:
    design = FootedBowlDesign(
        name="invalid_thin_base",
        rim_outer_diameter_mm=108.0,
        overall_height_mm=53.0,
        wall_thickness_mm=2.0,
        foot_outer_diameter_mm=31.0,
        foot_height_mm=7.0,
        body_floor_radius_mm=10.5,
        body_floor_z_mm=8.0,
        underside_recess_z_mm=6.5,
        foot_contact_width_mm=2.0,
    )
    with pytest.raises(ValueError, match="central base thickness"):
        design.validate()

