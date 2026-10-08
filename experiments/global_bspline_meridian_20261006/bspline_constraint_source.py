"""Exact linear-constraint source for a fixed-knot degree-5 meridian proposal.

This module is deliberately inert: it imports no CAD, NumPy, or solver and
does not build a control net unless a later approved caller invokes the
constraint-row functions. No function in this file has been executed here.
All rational weights are fixed to one so the interpolation and tangent rows
remain linear in the RZ control points.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence


Scalar = Fraction
DEGREE = 5
CONTROL_COUNT = 11
DOMAIN_START = Fraction(0)
DOMAIN_END = Fraction(1)
INTERNAL_KNOTS = tuple(Fraction(k, 6) for k in range(1, 6))
KNOT_VECTOR = (Fraction(0),) * 6 + INTERNAL_KNOTS + (Fraction(1),) * 6


@dataclass(frozen=True)
class ScalarEquation:
    name: str
    coordinate: str
    coefficients: tuple[Scalar, ...]
    rhs: Scalar


@dataclass(frozen=True)
class ScalarInequality:
    name: str
    coordinate: str
    coefficients: tuple[Scalar, ...]
    relation: str
    rhs: Scalar
    meaning: str


def _fraction(value: str | int) -> Scalar:
    return Fraction(str(value))


def _basis_value(index: int, degree: int, u: Scalar) -> Scalar:
    """Cox-de Boor basis value on the fixed knot vector; exact Fraction math."""

    if u == DOMAIN_END:
        last_basis_index = len(KNOT_VECTOR) - degree - 2
        return Fraction(int(index == last_basis_index))
    if degree == 0:
        return Fraction(
            int(KNOT_VECTOR[index] <= u < KNOT_VECTOR[index + 1])
        )

    left_denominator = KNOT_VECTOR[index + degree] - KNOT_VECTOR[index]
    right_denominator = (
        KNOT_VECTOR[index + degree + 1] - KNOT_VECTOR[index + 1]
    )
    left = Fraction(0)
    right = Fraction(0)
    if left_denominator:
        left = (u - KNOT_VECTOR[index]) / left_denominator * _basis_value(
            index, degree - 1, u
        )
    if right_denominator:
        right = (
            KNOT_VECTOR[index + degree + 1] - u
        ) / right_denominator * _basis_value(index + 1, degree - 1, u)
    return left + right


def _basis_derivative(index: int, degree: int, order: int, u: Scalar) -> Scalar:
    """Derivative of one basis function for internal-knot feature rows."""

    if order == 0:
        return _basis_value(index, degree, u)
    if order > degree:
        return Fraction(0)
    left_denominator = KNOT_VECTOR[index + degree] - KNOT_VECTOR[index]
    right_denominator = (
        KNOT_VECTOR[index + degree + 1] - KNOT_VECTOR[index + 1]
    )
    left = Fraction(0)
    right = Fraction(0)
    if left_denominator:
        left = Fraction(degree, 1) / left_denominator * _basis_derivative(
            index, degree - 1, order - 1, u
        )
    if right_denominator:
        right = Fraction(degree, 1) / right_denominator * _basis_derivative(
            index + 1, degree - 1, order - 1, u
        )
    return left - right


def basis_row(u: Scalar) -> tuple[Scalar, ...]:
    if not DOMAIN_START <= u <= DOMAIN_END:
        raise ValueError("PARAMETER_OUTSIDE_FIXED_DOMAIN")
    return tuple(_basis_value(i, DEGREE, u) for i in range(CONTROL_COUNT))


def derivative_row(u: Scalar, order: int = 1) -> tuple[Scalar, ...]:
    if u in {DOMAIN_START, DOMAIN_END}:
        raise ValueError("USE_CLAMPED_ENDPOINT_DIFFERENCE_FOR_ENDPOINT_TANGENTS")
    if not DOMAIN_START < u < DOMAIN_END or order not in {1, 2}:
        raise ValueError("ONLY_INTERNAL_FIRST_OR_SECOND_DERIVATIVE_ROWS_SUPPORTED")
    return tuple(
        _basis_derivative(i, DEGREE, order, u) for i in range(CONTROL_COUNT)
    )


def _point(record: Mapping[str, Sequence[str]]) -> tuple[Scalar, Scalar]:
    values = record["rz_mm"]
    if len(values) != 2:
        raise ValueError("RZ_STATION_REQUIRES_TWO_COORDINATES")
    return _fraction(values[0]), _fraction(values[1])


def _endpoint_tangent_rows() -> tuple[ScalarEquation, ScalarEquation]:
    first_nonzero_span = KNOT_VECTOR[DEGREE + 1] - KNOT_VECTOR[DEGREE]
    last_nonzero_span = KNOT_VECTOR[CONTROL_COUNT] - KNOT_VECTOR[CONTROL_COUNT - 1]
    start_scale = Fraction(DEGREE, 1) / first_nonzero_span
    end_scale = Fraction(DEGREE, 1) / last_nonzero_span
    start_z = [Fraction(0)] * CONTROL_COUNT
    start_z[0], start_z[1] = -start_scale, start_scale
    end_r = [Fraction(0)] * CONTROL_COUNT
    end_r[-2], end_r[-1] = -end_scale, end_scale
    return (
        ScalarEquation(
            "axis_bottom_horizontal_tangent_dz_du_zero",
            "z",
            tuple(start_z),
            Fraction(0),
        ),
        ScalarEquation(
            "outer_mouth_vertical_tangent_dr_du_zero",
            "r",
            tuple(end_r),
            Fraction(0),
        ),
    )


def build_case_constraint_rows(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return exact linear rows and named inequalities; perform no solve."""

    features = case["fixed_feature_constraints"]
    if len(features) != 3:
        raise ValueError("EXPECTED_AXIS_APEX_MOUTH_FEATURE_CONSTRAINTS")
    equalities: list[ScalarEquation] = []
    for feature in features:
        u = _fraction(feature["u"])
        r_value, z_value = _point(feature)
        row = basis_row(u)
        equalities.extend(
            (
                ScalarEquation(f"{feature['name']}_r_interpolation", "r", row, r_value),
                ScalarEquation(f"{feature['name']}_z_interpolation", "z", row, z_value),
            )
        )

    equalities.extend(_endpoint_tangent_rows())
    apex_feature = next(row for row in features if row["name"] == case["apex_feature"])
    apex_u = _fraction(apex_feature["u"])
    apex_dr = derivative_row(apex_u, 1)
    equalities.append(
        ScalarEquation("fixed_apex_vertical_tangent_dr_du_zero", "r", apex_dr, Fraction(0))
    )

    axis_r_positive = [Fraction(0)] * CONTROL_COUNT
    axis_r_positive[0], axis_r_positive[1] = Fraction(-1), Fraction(1)
    mouth_z_positive = [Fraction(0)] * CONTROL_COUNT
    mouth_z_positive[-2], mouth_z_positive[-1] = Fraction(-1), Fraction(1)
    apex_dz = derivative_row(apex_u, 1)
    apex_radial_second = derivative_row(apex_u, 2)
    inequalities = (
        ScalarInequality(
            "axis_tangent_points_outward",
            "r",
            tuple(axis_r_positive),
            ">",
            Fraction(0),
            "the endpoint curve derivative has positive radial component",
        ),
        ScalarInequality(
            "mouth_tangent_points_upward",
            "z",
            tuple(mouth_z_positive),
            ">",
            Fraction(0),
            "the endpoint curve derivative has positive vertical component",
        ),
        ScalarInequality(
            "apex_tangent_points_upward",
            "z",
            apex_dz,
            ">",
            Fraction(0),
            "the fixed-apex tangent is vertical and upward",
        ),
        ScalarInequality(
            "apex_is_strict_radial_maximum_to_second_order",
            "r",
            apex_radial_second,
            "<",
            Fraction(0),
            "with r'=0, r''<0 removes a radial plateau at the fixed apex",
        ),
    )

    targets = case["curvature_targets"]
    curvature_screens = {
        key: {
            "radius_target_mm": _fraction(targets[key]),
            "polynomial_condition": "S(u)^3 - R^2*D(u)^2 >= 0 on every full knot span, with S(u)>0",
            "status": "NONLINEAR_CONTINUUM_CONSTRAINT_NOT_ASSEMBLED_OR_CHECKED",
        }
        for key in ("body_and_shoulder_radius_mm", "outer_base_turn_radius_mm")
    }
    return {
        "family": case["family"],
        "degree": DEGREE,
        "control_point_count": CONTROL_COUNT,
        "weights": tuple(Fraction(1) for _ in range(CONTROL_COUNT)),
        "knot_vector": KNOT_VECTOR,
        "unknowns": tuple(f"Q{i}.{coordinate}" for i in range(CONTROL_COUNT) for coordinate in ("r", "z")),
        "linear_equalities": tuple(equalities),
        "linear_inequalities": inequalities,
        "curvature_screens": curvature_screens,
        "required_future_checks": (
            "exact Bernstein-piece extraction for each simple-knot span",
            "strict projection or another regularity lower bound on every full span",
            "curvature positivity certificate S^3-R^2D^2 >= 0 for each fixed region target R",
            "signed inward-offset factor 1-3*kappa > 0 on every proposed offset span",
            "global section self-intersection and reach/minimum-wall analysis",
        ),
    }
