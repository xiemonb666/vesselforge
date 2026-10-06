"""Declarative degree-seven Hermite source for the 2026-10-06 review.

This file intentionally contains no CLI, catalog mutation, CAD imports, solver,
or diagnostic invocation. The exact pole constructor is provided for source
review; it has not been run in this proposal phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Sequence


Scalar = Fraction
Point = tuple[Scalar, Scalar]


def _fraction_pair(values: Sequence[str]) -> Point:
    if len(values) != 2:
        raise ValueError("RZ_POINT_MUST_HAVE_TWO_COORDINATES")
    return (Fraction(values[0]), Fraction(values[1]))


@dataclass(frozen=True)
class Jet3:
    """A point and its first three derivatives with respect to global s.

    The shared global parameter s is measured in mm but is not assumed to be
    arc length. Position is mm; d1 has units mm/mm (dimensionless), d2 has
    units mm/mm^2 (1/mm), and d3 has units mm/mm^3 (1/mm^2). Fractions preserve
    the decimal/rational source values exactly.
    """

    rz_mm: Point
    d1: Point
    d2: Point
    d3: Point

    @classmethod
    def from_record(cls, record: Mapping[str, Sequence[str]]) -> "Jet3":
        return cls(
            rz_mm=_fraction_pair(record["rz_mm"]),
            d1=_fraction_pair(record["d1"]),
            d2=_fraction_pair(record["d2"]),
            d3=_fraction_pair(record["d3"]),
        )


@dataclass(frozen=True)
class SpanJet3:
    semantic: str
    parameter_length_mm: Scalar
    start: Jet3
    end: Jet3


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _scale(a: Point, value: Scalar) -> Point:
    return (a[0] * value, a[1] * value)


def degree7_controls(span: SpanJet3) -> tuple[Point, ...]:
    """Return the eight exact Bezier poles for endpoint position/1-2-3 jets.

    Adjacent spans have a shared global parameter s. If their knot jets match,
    these controls produce a C3 join exactly in rational arithmetic. This
    function only constructs poles; it does not assess regularity, curvature,
    monotonicity, offset feasibility, or section intersections.
    """

    h = span.parameter_length_mm
    if h <= 0:
        raise ValueError("SPAN_PARAMETER_LENGTH_MUST_BE_POSITIVE")
    seventh = h / 7
    forty_second = h * h / 42
    fourteenth = h * h / 14
    two_hundred_tenth = h * h * h / 210

    p0, p1 = span.start.rz_mm, span.end.rz_mm
    v0, a0, j0 = span.start.d1, span.start.d2, span.start.d3
    v1, a1, j1 = span.end.d1, span.end.d2, span.end.d3

    return (
        p0,
        _add(p0, _scale(v0, seventh)),
        _add(_add(p0, _scale(v0, 2 * seventh)), _scale(a0, forty_second)),
        _add(
            _add(_add(p0, _scale(v0, 3 * seventh)), _scale(a0, fourteenth)),
            _scale(j0, two_hundred_tenth),
        ),
        _add(
            _sub(p1, _scale(v1, 3 * seventh)),
            _sub(_scale(a1, fourteenth), _scale(j1, two_hundred_tenth)),
        ),
        _add(
            _sub(p1, _scale(v1, 2 * seventh)),
            _scale(a1, forty_second),
        ),
        _sub(p1, _scale(v1, seventh)),
        p1,
    )


def span_from_records(
    semantic: str,
    parameter_length_mm: str,
    start_record: Mapping[str, Sequence[str]],
    end_record: Mapping[str, Sequence[str]],
) -> SpanJet3:
    """Build one source span record without loading files or running checks."""

    return SpanJet3(
        semantic=semantic,
        parameter_length_mm=Fraction(parameter_length_mm),
        start=Jet3.from_record(start_record),
        end=Jet3.from_record(end_record),
    )
