from __future__ import annotations

import json

import pytest

from vesselforge.profile_catalog import _assert_simple_open_profile, build_profile


@pytest.mark.parametrize("family", ("bowl", "beaker", "jar"))
def test_catalog_profiles_have_mm_opening_and_positive_simple_material_section(family: str) -> None:
    profile = build_profile(family)
    outer = profile.outer_profile_mm
    inner = profile.inner_profile_mm
    params = profile.parameters

    assert profile.units == "mm"
    assert max(z for _, z in outer) == params["height_mm"]
    assert max(r for r, _ in outer) == params["max_radius_mm"]
    assert outer[-1] == (
        params["mouth_diameter_mm"] / 2 + params["wall_thickness_declaration_mm"],
        params["height_mm"],
    )
    assert inner[-1] == (params["mouth_diameter_mm"] / 2, params["height_mm"])
    assert inner[0] == (0.0, params["base_thickness_declaration_mm"])
    assert profile.geometry_only_qualification["signed_meridian_area_mm2"] > 0.0
    assert profile.geometry_only_qualification["status"] == "GEOMETRY_ONLY_CANDIDATE"
    assert "not a global normal minimum" in profile.geometry_only_qualification[
        "wall_declaration_interpretation"
    ]
    assert profile.geometry_only_qualification["real_vessel_match"] == "NOT_VALIDATED"
    assert profile.parameter_sources["height_mm"]
    assert profile.parameter_ranges_mm["height_mm"]["unit"] == "mm"
    json.dumps(profile.to_dict(), allow_nan=False)


def test_independent_beaker_dimensions_flow_into_builder_compatible_profiles() -> None:
    profile = build_profile(
        "beaker",
        height_mm=130.0,
        max_radius_mm=52.0,
        mouth_diameter_mm=84.0,
        wall_thickness_declaration_mm=3.0,
        base_thickness_declaration_mm=7.0,
    )
    exported = profile.builder_profiles()

    assert profile.parameters["height_mm"] == 130.0
    assert max(r for r, _ in profile.outer_profile_mm) == 52.0
    assert exported["outer_profile_mm"][-1] == [45.0, 130.0]
    assert exported["inner_profile_mm"][-1] == [42.0, 130.0]
    assert exported["closed_material_section_mm"][0] == [0.0, 0.0]


def test_jar_has_distinct_neck_and_shoulder_sections() -> None:
    profile = build_profile("jar")
    outer = profile.outer_profile_mm
    params = profile.parameters
    shoulder_neck = outer[-2]
    shoulder_body = outer[-3]

    assert params["neck_height_mm"] == outer[-1][1] - shoulder_neck[1]
    assert params["shoulder_height_mm"] == shoulder_neck[1] - shoulder_body[1]
    assert shoulder_neck[0] == outer[-1][0]
    assert shoulder_body[0] > shoulder_neck[0]


def test_profile_math_rejects_a_self_intersecting_generator_line() -> None:
    crossing = ((0.0, 0.0), (3.0, 3.0), (0.0, 3.0), (3.0, 0.0), (4.0, 0.0))
    with pytest.raises(ValueError, match="self-intersects"):
        _assert_simple_open_profile("candidate", crossing, 1e-9)


@pytest.mark.parametrize(
    ("family", "overrides", "message"),
    (
        ("bowl", {"wall_thickness_declaration_mm": -1.0}, "wall_thickness_declaration_mm"),
        ("bowl", {"wall_thickness_declaration_mm": 4.0, "max_radius_mm": 30.0}, "too large"),
        ("beaker", {"base_thickness_declaration_mm": 10.0, "height_mm": 30.0}, "too large"),
        ("jar", {"neck_height_mm": 32.0, "shoulder_height_mm": 34.0}, "too large"),
        ("bowl", {"mouth_diameter_mm": 130.0}, "must not exceed max_radius_mm"),
        ("bowl", {"height_mm": True}, "finite number"),
        ("jar", {"max_radius_mm": float("nan")}, "finite number"),
    ),
)
def test_parameter_limits_fail_closed(family: str, overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_profile(family, **overrides)


def test_family_specific_parameters_are_rejected_for_other_forms() -> None:
    with pytest.raises(ValueError, match="unsupported bowl parameters"):
        build_profile("bowl", neck_height_mm=12.0)
