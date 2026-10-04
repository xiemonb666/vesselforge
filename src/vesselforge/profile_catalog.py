"""Geometry-only starter profiles for rotational VesselForge forms.

The profile coordinates follow ``geometry.scaled_outer_profile``: ordered
``(radius_mm, z_mm)`` meridian points in a right-handed Z-up frame. The
returned inner profile is the constant-radial-offset construction companion;
it is a declared generator setting, not a measured or global minimum wall
thickness. The output is suitable for an OCC revolve adapter, but the current
``build_components(VesselSpec)`` does not yet accept a catalog profile. The
smallest production integration point is ``geometry.scaled_outer_profile`` /
``build_components``: accept this object and revolve its closed material
section in place of the fixed ``PROFILE`` and offset helper.

All three families are analytic candidate shapes only. They have not been
matched to real vessels, archaeological measurements, material behavior, or
physical qualification.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal


ProfileFamily = Literal["bowl", "beaker", "jar"]
PointRZ = tuple[float, float]

PROFILE_CATALOG_VERSION = "vesselforge.profile_catalog/0.1.0"

_SOURCE = (
    "Analytic starter envelope chosen for this geometry-only prototype; "
    "not measured from a real or archaeological vessel."
)

_BASE_RANGES: dict[str, dict[str, float | str]] = {
    "height_mm": {"min": 30.0, "max": 240.0, "unit": "mm"},
    "max_radius_mm": {"min": 12.0, "max": 120.0, "unit": "mm"},
    "mouth_diameter_mm": {"min": 10.0, "max": 220.0, "unit": "mm"},
    "wall_thickness_declaration_mm": {"min": 0.5, "max": 10.0, "unit": "mm"},
    "base_thickness_declaration_mm": {"min": 0.5, "max": 15.0, "unit": "mm"},
}

_DEFAULTS: dict[str, dict[str, float]] = {
    "bowl": {
        "height_mm": 90.0,
        "max_radius_mm": 60.0,
        "mouth_diameter_mm": 108.0,
        "wall_thickness_declaration_mm": 3.0,
        "base_thickness_declaration_mm": 6.0,
    },
    "beaker": {
        "height_mm": 110.0,
        "max_radius_mm": 42.0,
        "mouth_diameter_mm": 70.0,
        "wall_thickness_declaration_mm": 2.5,
        "base_thickness_declaration_mm": 4.5,
    },
    "jar": {
        "height_mm": 120.0,
        "max_radius_mm": 54.0,
        "mouth_diameter_mm": 46.0,
        "wall_thickness_declaration_mm": 3.0,
        "base_thickness_declaration_mm": 5.5,
        "neck_height_mm": 18.0,
        "shoulder_height_mm": 28.0,
    },
}

_JAR_RANGES: dict[str, dict[str, float | str]] = {
    "neck_height_mm": {"min": 4.0, "max": 60.0, "unit": "mm"},
    "shoulder_height_mm": {"min": 6.0, "max": 90.0, "unit": "mm"},
}


@dataclass(frozen=True)
class VesselProfile:
    """Validated meridian profiles and their candidate-only provenance."""

    family: ProfileFamily
    units: Literal["mm"]
    parameters: dict[str, float]
    parameter_ranges_mm: dict[str, dict[str, float | str]]
    parameter_sources: dict[str, str]
    outer_profile_mm: tuple[PointRZ, ...]
    inner_profile_mm: tuple[PointRZ, ...]
    geometry_only_qualification: dict[str, Any]

    @property
    def closed_material_section_mm(self) -> tuple[PointRZ, ...]:
        """Return one closed meridian outline, without a repeated final point."""
        return self.outer_profile_mm + (self.inner_profile_mm[-1],) + tuple(
            reversed(self.inner_profile_mm[:-1])
        )

    def builder_profiles(self) -> dict[str, list[list[float]]]:
        """Return list-based ``(r, z)`` data matching the existing builder API."""
        return {
            "outer_profile_mm": [[r, z] for r, z in self.outer_profile_mm],
            "inner_profile_mm": [[r, z] for r, z in self.inner_profile_mm],
            "closed_material_section_mm": [[r, z] for r, z in self.closed_material_section_mm],
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible record for downstream retrieval manifests."""
        return {
            "schema": PROFILE_CATALOG_VERSION,
            "family": self.family,
            "units": {"length": self.units},
            "parameters": dict(self.parameters),
            "parameter_ranges_mm": {name: dict(bounds) for name, bounds in self.parameter_ranges_mm.items()},
            "parameter_sources": dict(self.parameter_sources),
            **self.builder_profiles(),
            "geometry_only_qualification": dict(self.geometry_only_qualification),
        }


def _finite_number(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number; received {value!r}")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number; received {value!r}") from exc
    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number; received {value!r}")
    return number


def _cross(a: PointRZ, b: PointRZ, c: PointRZ) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: PointRZ, b: PointRZ, p: PointRZ, epsilon: float) -> bool:
    return (
        min(a[0], b[0]) - epsilon <= p[0] <= max(a[0], b[0]) + epsilon
        and min(a[1], b[1]) - epsilon <= p[1] <= max(a[1], b[1]) + epsilon
        and abs(_cross(a, b, p)) <= epsilon
    )


def _segments_intersect(a: PointRZ, b: PointRZ, c: PointRZ, d: PointRZ, epsilon: float) -> bool:
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if ((ab_c > epsilon and ab_d < -epsilon) or (ab_c < -epsilon and ab_d > epsilon)) and (
        (cd_a > epsilon and cd_b < -epsilon) or (cd_a < -epsilon and cd_b > epsilon)
    ):
        return True
    return (
        (abs(ab_c) <= epsilon and _on_segment(a, b, c, epsilon))
        or (abs(ab_d) <= epsilon and _on_segment(a, b, d, epsilon))
        or (abs(cd_a) <= epsilon and _on_segment(c, d, a, epsilon))
        or (abs(cd_b) <= epsilon and _on_segment(c, d, b, epsilon))
    )


def _assert_simple_open_profile(name: str, points: tuple[PointRZ, ...], epsilon: float) -> None:
    if len(points) < 2:
        raise ValueError(f"{name} must contain at least two points")
    for index, (a, b) in enumerate(zip(points, points[1:])):
        if (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 <= epsilon**2:
            raise ValueError(f"{name} contains a zero-length segment at index {index}")
    segments = list(zip(points, points[1:]))
    for i, (a, b) in enumerate(segments):
        for j in range(i + 2, len(segments)):
            c, d = segments[j]
            if _segments_intersect(a, b, c, d, epsilon):
                raise ValueError(f"{name} self-intersects between segments {i} and {j}")


def _signed_area(points: tuple[PointRZ, ...]) -> float:
    return sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    ) / 2.0


def _assert_simple_closed_outline(name: str, points: tuple[PointRZ, ...], epsilon: float) -> float:
    if len(points) < 3:
        raise ValueError(f"{name} must contain at least three points")
    if any((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 <= epsilon**2 for a, b in zip(points, points[1:] + points[:1])):
        raise ValueError(f"{name} contains a zero-length segment")
    segments = list(zip(points, points[1:] + points[:1]))
    for i, (a, b) in enumerate(segments):
        for j in range(i + 1, len(segments)):
            if j == i + 1 or (i == 0 and j == len(segments) - 1):
                continue
            c, d = segments[j]
            if _segments_intersect(a, b, c, d, epsilon):
                raise ValueError(f"{name} self-intersects between segments {i} and {j}")
    area = _signed_area(points)
    if not isfinite(area) or area <= epsilon**2:
        raise ValueError(f"{name} must have positive oriented meridian area")
    return area


def _validate_parameters(family: str, values: dict[str, object]) -> tuple[ProfileFamily, dict[str, float]]:
    if family not in _DEFAULTS:
        raise ValueError(f"unsupported vessel profile family {family!r}; choose bowl, beaker, or jar")
    allowed = set(_DEFAULTS[family])
    supplied_unknown = set(values) - allowed
    if supplied_unknown:
        raise ValueError(f"unsupported {family} parameters: {', '.join(sorted(supplied_unknown))}")
    params = {name: _finite_number(name, value) for name, value in values.items()}
    for name, bounds in _BASE_RANGES.items():
        value = params[name]
        if not (float(bounds["min"]) <= value <= float(bounds["max"])):
            raise ValueError(f"{name} must be between {bounds['min']} and {bounds['max']} mm")
    height = params["height_mm"]
    radius = params["max_radius_mm"]
    mouth_radius = params["mouth_diameter_mm"] / 2.0
    wall = params["wall_thickness_declaration_mm"]
    base = params["base_thickness_declaration_mm"]
    outer_mouth_radius = mouth_radius + wall
    if wall > min(10.0, 0.10 * radius):
        raise ValueError("wall_thickness_declaration_mm is too large for the selected vessel radius")
    if base >= min(15.0, 0.25 * height):
        raise ValueError("base_thickness_declaration_mm is too large for the selected vessel height")
    if outer_mouth_radius > radius:
        raise ValueError("mouth radius plus wall declaration must not exceed max_radius_mm")
    if family in ("bowl", "beaker") and outer_mouth_radius < 0.78 * radius:
        raise ValueError(f"{family} mouth is too narrow relative to max_radius_mm")

    if family == "jar":
        neck = params["neck_height_mm"]
        shoulder = params["shoulder_height_mm"]
        for name, bounds in _JAR_RANGES.items():
            value = params[name]
            if not (float(bounds["min"]) <= value <= float(bounds["max"])):
                raise ValueError(f"{name} must be between {bounds['min']} and {bounds['max']} mm")
        if neck + shoulder > 0.54 * height:
            raise ValueError("jar neck plus shoulder height is too large relative to height_mm")
        if outer_mouth_radius > 0.72 * radius:
            raise ValueError("jar mouth/neck radius must be smaller than the shoulder body radius")
    return family, params  # type: ignore[return-value]


def _make_outer_profile(family: ProfileFamily, params: dict[str, float]) -> tuple[PointRZ, ...]:
    h = params["height_mm"]
    r = params["max_radius_mm"]
    base = params["base_thickness_declaration_mm"]
    lip_r = params["mouth_diameter_mm"] / 2.0 + params["wall_thickness_declaration_mm"]
    foot_r = 0.22 * r if family == "bowl" else 0.30 * r if family == "beaker" else 0.24 * r
    points: list[PointRZ] = [(0.0, 0.0), (foot_r, 0.0), (foot_r, base)]

    if family == "bowl":
        z1 = max(0.12 * h, base + 0.04 * h)
        z2 = max(0.34 * h, z1 + 0.08 * h)
        z3 = max(0.62 * h, z2 + 0.08 * h)
        z4 = max(0.86 * h, z3 + 0.08 * h)
        points.extend(((0.44 * r, z1), (0.72 * r, z2), (0.94 * r, z3), (r, z4), (lip_r, h)))
    elif family == "beaker":
        z1 = max(0.12 * h, base + 0.04 * h)
        z2 = max(0.88 * h, z1 + 0.25 * h)
        points.extend(((0.94 * r, z1), (r, z2), (lip_r, h)))
    else:
        neck_h = params["neck_height_mm"]
        shoulder_h = params["shoulder_height_mm"]
        shoulder_top = h - neck_h
        shoulder_bottom = shoulder_top - shoulder_h
        body_top = shoulder_bottom - 0.10 * h
        points.extend(
            (
                (0.64 * r, max(0.14 * h, base + 0.05 * h)),
                (r, max(0.34 * h, base + 0.10 * h)),
                (r, body_top),
                (0.92 * r, shoulder_bottom),
                (lip_r, shoulder_top),
                (lip_r, h),
            )
        )
    return tuple((float(rad), float(z)) for rad, z in points)


def build_profile(
    family: str,
    *,
    height_mm: float | None = None,
    max_radius_mm: float | None = None,
    mouth_diameter_mm: float | None = None,
    wall_thickness_declaration_mm: float | None = None,
    base_thickness_declaration_mm: float | None = None,
    neck_height_mm: float | None = None,
    shoulder_height_mm: float | None = None,
) -> VesselProfile:
    """Build one validated bowl, beaker, or jar meridian in millimetres.

    ``mouth_diameter_mm`` is the clear inside opening diameter. The outer lip
    radius is that opening radius plus the declared radial wall setting. Jar
    neck and shoulder heights are measured vertically from the bottom datum.
    """
    if not isinstance(family, str):
        raise ValueError(f"unsupported vessel profile family {family!r}; choose bowl, beaker, or jar")
    family_key = family.strip().lower()
    supplied: dict[str, float | None] = {
        "height_mm": height_mm,
        "max_radius_mm": max_radius_mm,
        "mouth_diameter_mm": mouth_diameter_mm,
        "wall_thickness_declaration_mm": wall_thickness_declaration_mm,
        "base_thickness_declaration_mm": base_thickness_declaration_mm,
        "neck_height_mm": neck_height_mm,
        "shoulder_height_mm": shoulder_height_mm,
    }
    defaults = _DEFAULTS.get(family_key)
    if defaults is None:
        raise ValueError(f"unsupported vessel profile family {family!r}; choose bowl, beaker, or jar")
    overrides = {name: value for name, value in supplied.items() if value is not None}
    unsupported = set(overrides) - set(defaults)
    if unsupported:
        raise ValueError(f"unsupported {family_key} parameters: {', '.join(sorted(unsupported))}")
    values: dict[str, object] = {**defaults, **overrides}
    normalized_family, params = _validate_parameters(family_key, values)

    outer = _make_outer_profile(normalized_family, params)
    wall = params["wall_thickness_declaration_mm"]
    base = params["base_thickness_declaration_mm"]
    # The floor is represented by its own declaration. The vessel side uses a
    # horizontal (radial) offset at corresponding control heights.
    inner: tuple[PointRZ, ...] = (
        (0.0, base),
        (outer[2][0] - wall, base),
        *((rad - wall, z) for rad, z in outer[3:]),
    )
    epsilon = max(params["height_mm"], params["max_radius_mm"]) * 1e-10
    for name, profile in (("outer_profile_mm", outer), ("inner_profile_mm", inner)):
        for index, (rad, z) in enumerate(profile):
            if not isfinite(rad) or not isfinite(z) or rad < 0.0:
                raise ValueError(f"{name} has an invalid radius or height at point {index}")
        _assert_simple_open_profile(name, profile, epsilon)
    section = outer + (inner[-1],) + tuple(reversed(inner[:-1]))
    area = _assert_simple_closed_outline("closed_material_section_mm", section, epsilon)
    qualification = {
        "status": "GEOMETRY_ONLY_CANDIDATE",
        "scope": "analytic rotational generator profile; no CAD solid, mesh, or physical validation is implied",
        "wall_declaration_interpretation": "constant radial meridian offset at corresponding control heights; not a global normal minimum or measured material thickness",
        "base_declaration_interpretation": "inside floor datum is base_thickness_declaration_mm above the outside floor datum; not a full-solid minimum-wall measurement",
        "self_intersection_check": "finite 2D segment-intersection check on both profiles and the closed material meridian outline",
        "signed_meridian_area_mm2": area,
        "real_vessel_match": "NOT_VALIDATED",
        "material_or_physical_qualification": "NOT_VALIDATED",
        "source": _SOURCE,
    }
    ranges = {name: dict(bounds) for name, bounds in _BASE_RANGES.items()}
    if normalized_family == "jar":
        ranges.update({name: dict(bounds) for name, bounds in _JAR_RANGES.items()})
    sources = {name: _SOURCE for name in params}
    return VesselProfile(
        family=normalized_family,
        units="mm",
        parameters=params,
        parameter_ranges_mm=ranges,
        parameter_sources=sources,
        outer_profile_mm=outer,
        inner_profile_mm=inner,
        geometry_only_qualification=qualification,
    )


__all__ = ["PROFILE_CATALOG_VERSION", "VesselProfile", "build_profile"]
