"""Source-only quintic corner-fairing study for two catalog defaults.

No CAD kernel, STEP export, meshing, solver, or geometry tuning is used here.
The result is a bounded mathematical proposal for review, not a training body.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
import traceback
from dataclasses import dataclass
from math import comb
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
VF_SOURCE_ROOT = REPO_ROOT / "vesselforge" / "src"
OUTPUT_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261006" / "catalog_corner_fairing_20261006"
RUNTIME = REPO_ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
EXPECTED_RUNTIME_SHA256 = "2b83f3f84ea2f51132fa1aae73815be54126a799521de85ff6ea70627cde6da7"
CATALOG_SOURCE = VF_SOURCE_ROOT / "vesselforge" / "profile_catalog.py"
SOURCE_PATHS = {
    "profile_catalog": CATALOG_SOURCE,
    "corner_fairing_source": Path(__file__).resolve(),
    "python_runtime": RUNTIME,
}

# Frozen before inspecting any fairing output; applied only to the bowl and jar defaults.
TRIM_SCALE = 0.12
MIN_ORIGINAL_SEGMENT_MM = 2.0
MAX_ADJACENT_TRIM_FRACTION = 0.25
CONTROL_FRACTIONS = (0.25, 0.50)
STRAIGHT_TURN_SKIP_DEG = 2.0
REVERSAL_REJECT_DEG = 170.0
CURVE_SUBDIVISIONS = 8
MAX_TOTAL_CURVE_PARAMETER_SAMPLES = 256
MAX_TOTAL_WALL_SECONDS = 30.0
GEOMETRY_EPSILON_MM = 1e-9
END_CURVATURE_TOLERANCE_PER_MM = 1e-8
ALLOWED_FAMILIES = ("bowl", "jar")

Point = tuple[float, float]


@dataclass(frozen=True)
class Span:
    kind: str
    start: Point
    end: Point
    source_segment_index: int | None = None
    source_vertex_index: int | None = None
    controls: tuple[Point, ...] = ()
    corner_report_index: int | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _source_pins() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for label, path in SOURCE_PATHS.items():
        if not path.is_file():
            raise FileNotFoundError(f"PINNED_SOURCE_MISSING:{label}:{path}")
        result[label] = {"path": str(path.relative_to(REPO_ROOT)), "sha256": _sha256(path)}
    if result["python_runtime"]["sha256"] != EXPECTED_RUNTIME_SHA256:
        raise ValueError("PINNED_PYTHON_RUNTIME_SHA256_MISMATCH")
    return result


def _load_catalog_builder():
    """Load only profile_catalog.py, bypassing package __init__ side effects."""
    module_name = "_vesselforge_profile_catalog_source_only_20261006"
    if module_name in sys.modules:
        module = sys.modules[module_name]
        if Path(module.__file__).resolve() != CATALOG_SOURCE.resolve():
            raise RuntimeError("UNEXPECTED_CACHED_PROFILE_CATALOG_MODULE")
        return module.build_profile
    spec = importlib.util.spec_from_file_location(module_name, CATALOG_SOURCE)
    if spec is None or spec.loader is None:
        raise ImportError("PROFILE_CATALOG_SOURCE_ONLY_IMPORT_SPEC_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.build_profile


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _scale(a: Point, value: float) -> Point:
    return (a[0] * value, a[1] * value)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _length(a: Point) -> float:
    return math.hypot(a[0], a[1])


def _unit(a: Point) -> Point:
    length = _length(a)
    if length <= GEOMETRY_EPSILON_MM:
        raise ValueError("ZERO_LENGTH_PROFILE_SEGMENT")
    return (a[0] / length, a[1] / length)


def _point_on_segment(point: Point, a: Point, b: Point, epsilon: float) -> bool:
    ab, ap = _sub(b, a), _sub(point, a)
    if abs(_cross(ab, ap)) > epsilon * max(1.0, _length(ab)):
        return False
    projection = _dot(ap, ab)
    return -epsilon <= projection <= _dot(ab, ab) + epsilon


def _make_controls(vertex: Point, tin: Point, tout: Point, trim: float) -> tuple[Point, ...]:
    a = _sub(vertex, _scale(tin, trim))
    b = _add(vertex, _scale(tout, trim))
    f1, f2 = CONTROL_FRACTIONS
    return (
        a,
        _add(a, _scale(tin, f1 * trim)),
        _add(a, _scale(tin, f2 * trim)),
        _sub(b, _scale(tout, f2 * trim)),
        _sub(b, _scale(tout, f1 * trim)),
        b,
    )


def _bezier_eval(controls: Sequence[Point], t: float) -> tuple[Point, Point, Point, float]:
    """Return point, first derivative, second derivative, and unsigned curvature."""
    if len(controls) != 6:
        raise ValueError("QUINTIC_CONTROL_COUNT_MUST_BE_SIX")
    omt = 1.0 - t
    p = [0.0, 0.0]
    d1 = [0.0, 0.0]
    d2 = [0.0, 0.0]
    for i, point in enumerate(controls):
        weight = comb(5, i) * omt ** (5 - i) * t**i
        p[0] += weight * point[0]
        p[1] += weight * point[1]
    first_differences = [_sub(controls[i + 1], controls[i]) for i in range(5)]
    for i, difference in enumerate(first_differences):
        weight = 5.0 * comb(4, i) * omt ** (4 - i) * t**i
        d1[0] += weight * difference[0]
        d1[1] += weight * difference[1]
    for i in range(4):
        second_difference = _add(
            _sub(controls[i + 2], _scale(controls[i + 1], 2.0)), controls[i]
        )
        weight = 20.0 * comb(3, i) * omt ** (3 - i) * t**i
        d2[0] += weight * second_difference[0]
        d2[1] += weight * second_difference[1]
    speed = math.hypot(d1[0], d1[1])
    curvature = abs(d1[0] * d2[1] - d1[1] * d2[0]) / speed**3 if speed > 0.0 else math.inf
    return (p[0], p[1]), (d1[0], d1[1]), (d2[0], d2[1]), curvature


def _curvature_from_controls(controls: Sequence[Point], at_end: bool) -> tuple[float, float]:
    """Compute signed curvature directly from the first three endpoint controls."""
    if at_end:
        p0, p1, p2 = controls[5], controls[4], controls[3]
    else:
        p0, p1, p2 = controls[0], controls[1], controls[2]
    d1, d2 = _sub(p1, p0), _add(_sub(p2, _scale(p1, 2.0)), p0)
    speed = 5.0 * _length(d1)
    signed_numerator = _cross(d1, d2)
    signed_curvature = 0.0 if speed <= 0.0 else (0.8 * signed_numerator / (d1[0] * d1[0] + d1[1] * d1[1]) ** 1.5)
    return signed_curvature, abs(signed_numerator)


def build_faired_profile(
    label: str,
    points: Sequence[Point],
    protected_reasons: Mapping[int, str],
    *,
    trim_scale: float = TRIM_SCALE,
) -> tuple[list[Span], list[dict[str, Any]]]:
    """Replace selected open-polyline vertices by local quintic corner spans."""
    vertices = [tuple(float(x) for x in point) for point in points]
    if len(vertices) < 3 or not (0.0 < trim_scale <= 0.12):
        raise ValueError(f"{label}_PROFILE_OR_TRIM_SCALE_INVALID")
    segment_lengths = [_length(_sub(b, a)) for a, b in zip(vertices, vertices[1:])]
    if any(not math.isfinite(length) or length < MIN_ORIGINAL_SEGMENT_MM for length in segment_lengths):
        raise ValueError(f"{label}_ORIGINAL_SEGMENT_SHORTER_THAN_{MIN_ORIGINAL_SEGMENT_MM:g}_MM")

    active: dict[int, dict[str, Any]] = {}
    corner_rows: list[dict[str, Any]] = []
    for endpoint_index in (0, len(vertices) - 1):
        corner_rows.append({
            "profile_side": label,
            "vertex_index": endpoint_index,
            "original_corner_rz_mm": list(vertices[endpoint_index]),
            "signed_turn_deg": None,
            "status": "PROTECTED_SHARP_CORNER",
            "reason": protected_reasons.get(endpoint_index, "open-profile endpoint retained"),
            "curvature_status": "UNDEFINED_AT_RETAINED_SECTION_CLOSURE_JOIN",
        })
    for index in range(1, len(vertices) - 1):
        vertex = vertices[index]
        previous, following = vertices[index - 1], vertices[index + 1]
        incoming, outgoing = _sub(vertex, previous), _sub(following, vertex)
        len_in, len_out = _length(incoming), _length(outgoing)
        tin, tout = _unit(incoming), _unit(outgoing)
        turn_rad = math.atan2(_cross(tin, tout), _dot(tin, tout))
        turn_deg = math.degrees(turn_rad)
        row: dict[str, Any] = {
            "profile_side": label,
            "vertex_index": index,
            "original_corner_rz_mm": list(vertex),
            "signed_turn_deg": turn_deg,
            "incoming_segment_length_mm": len_in,
            "outgoing_segment_length_mm": len_out,
        }
        if index in protected_reasons:
            row.update({"status": "PROTECTED_SHARP_CORNER", "reason": protected_reasons[index], "curvature_status": "UNDEFINED_AT_RETAINED_POLYLINE_CORNER"})
            corner_rows.append(row)
            continue
        if abs(turn_deg) <= STRAIGHT_TURN_SKIP_DEG:
            row.update({"status": "SKIPPED_NEAR_STRAIGHT", "reason": f"absolute turn is at most {STRAIGHT_TURN_SKIP_DEG:g} degrees"})
            corner_rows.append(row)
            continue
        if abs(turn_deg) >= REVERSAL_REJECT_DEG:
            raise ValueError(f"{label}_NEAR_REVERSAL_CORNER_REJECTED:{index}:{turn_deg:.9g}_DEG")
        trim = trim_scale * min(len_in, len_out)
        controls = _make_controls(vertex, tin, tout, trim)
        a, b = controls[0], controls[5]
        local_epsilon = 1e-9 * max(1.0, len_in, len_out)
        hull_controls_ok = all(
            _point_on_segment(controls[j], a, vertex, local_epsilon) for j in range(3)
        ) and all(
            _point_on_segment(controls[j], vertex, b, local_epsilon) for j in range(3, 6)
        )
        if not hull_controls_ok:
            raise ValueError(f"{label}_CONTROL_POLE_OUTSIDE_LOCAL_CONVEX_HULL:{index}")
        if _length(_sub(controls[1], controls[0])) <= GEOMETRY_EPSILON_MM or _length(_sub(controls[5], controls[4])) <= GEOMETRY_EPSILON_MM:
            raise ValueError(f"{label}_QUINTIC_ENDPOINT_TANGENT_DEGENERATE:{index}")
        bisector = _unit(_add(tin, tout))
        derivative_controls = [_sub(controls[j + 1], controls[j]) for j in range(5)]
        bisector_projections = [_dot(vector, bisector) for vector in derivative_controls]
        if min(bisector_projections) <= GEOMETRY_EPSILON_MM:
            raise ValueError(f"{label}_QUINTIC_GLOBAL_REGULARITY_BOUND_FAILED:{index}")
        speed_lower_bound = 5.0 * min(bisector_projections)
        second_differences = [
            _add(_sub(controls[j + 2], _scale(controls[j + 1], 2.0)), controls[j])
            for j in range(4)
        ]
        second_derivative_upper_bound = 20.0 * max(_length(vector) for vector in second_differences)
        curvature_upper_bound = second_derivative_upper_bound / (speed_lower_bound * speed_lower_bound)
        first_curvature, first_numerator = _curvature_from_controls(controls, at_end=False)
        last_curvature, last_numerator = _curvature_from_controls(controls, at_end=True)
        if abs(first_curvature) > END_CURVATURE_TOLERANCE_PER_MM or abs(last_curvature) > END_CURVATURE_TOLERANCE_PER_MM:
            raise ValueError(f"{label}_QUINTIC_ENDPOINT_CURVATURE_NOT_ZERO:{index}")
        row.update({
            "status": "QUINTIC_FAIRING",
            "trim_scale_of_shorter_adjacent_segment": trim_scale,
            "trim_distance_mm_each_side": trim,
            "control_points_rz_mm": [list(point) for point in controls],
            "all_controls_on_trimmed_adjacent_segments": hull_controls_ok,
            "curve_within_adjacent_local_convex_hull_by_bezier_hull_property": hull_controls_ok,
            "control_polygon_tangent_bisector_projections_mm": bisector_projections,
            "global_regular_for_all_parameters_by_positive_derivative_projection": True,
            "derivative_speed_lower_bound_mm_per_unit_parameter": speed_lower_bound,
            "second_derivative_norm_upper_bound_mm_per_unit_parameter2": second_derivative_upper_bound,
            "global_curvature_upper_bound_per_mm": curvature_upper_bound,
            "global_minimum_curvature_radius_lower_bound_mm": None if curvature_upper_bound <= 0.0 else 1.0 / curvature_upper_bound,
            "first_endpoint_tangent_matches_incoming_line": True,
            "last_endpoint_tangent_matches_outgoing_line": True,
            "endpoint_signed_curvature_per_mm": [first_curvature, last_curvature],
            "endpoint_cross_numerator_mm2": [first_numerator, last_numerator],
            "geometric_C2_join_by_tangent_and_zero_curvature": True,
            "parametric_C2_in_shared_span_parameters": "NOT_CLAIMED; neighboring line and Bezier parameter speeds are not matched",
        })
        active[index] = {"trim": trim, "controls": controls, "corner_report_index": len(corner_rows)}
        corner_rows.append(row)

    for segment_index, length in enumerate(segment_lengths):
        trim_at_start = active.get(segment_index, {}).get("trim", 0.0)
        trim_at_end = active.get(segment_index + 1, {}).get("trim", 0.0)
        fraction = (trim_at_start + trim_at_end) / length
        if fraction >= MAX_ADJACENT_TRIM_FRACTION:
            raise ValueError(f"{label}_ADJACENT_TRIMS_CONSUME_SEGMENT:{segment_index}:{fraction:.9g}")

    spans: list[Span] = []
    for segment_index in range(len(vertices) - 1):
        start = _add(vertices[segment_index], _scale(_unit(_sub(vertices[segment_index + 1], vertices[segment_index])), active[segment_index]["trim"])) if segment_index in active else vertices[segment_index]
        end = _sub(vertices[segment_index + 1], _scale(_unit(_sub(vertices[segment_index + 1], vertices[segment_index])), active[segment_index + 1]["trim"])) if segment_index + 1 in active else vertices[segment_index + 1]
        if _length(_sub(end, start)) <= GEOMETRY_EPSILON_MM:
            raise ValueError(f"{label}_REMAINING_STRAIGHT_SEGMENT_TOO_SHORT:{segment_index}")
        spans.append(Span("line", start, end, source_segment_index=segment_index))
        corner_index = segment_index + 1
        if corner_index in active:
            data = active[corner_index]
            spans.append(Span(
                "quintic", data["controls"][0], data["controls"][-1],
                source_vertex_index=corner_index,
                controls=data["controls"],
                corner_report_index=data["corner_report_index"],
            ))
    return spans, corner_rows


def _span_eval(span: Span, t: float) -> tuple[Point, float, float]:
    if span.kind == "line":
        point = _add(span.start, _scale(_sub(span.end, span.start), t))
        return point, 0.0, _length(_sub(span.end, span.start))
    point, d1, _, curvature = _bezier_eval(span.controls, t)
    return point, curvature, _length(d1)


def sample_spans(spans: Sequence[Span], subdivisions: int = CURVE_SUBDIVISIONS) -> tuple[list[Point], list[list[Point]], list[dict[str, Any]], int]:
    if not spans:
        raise ValueError("SMOOTHED_PROFILE_HAS_NO_SPANS")
    contour: list[Point] = [spans[0].start]
    samples_by_span: list[list[Point]] = []
    curvature_reports: list[dict[str, Any]] = []
    parameter_evaluations = 0
    for span_index, span in enumerate(spans):
        if span.kind == "line":
            points = [span.start, span.end]
            span_sample = points
        elif span.kind == "quintic":
            points = []
            curvatures: list[float] = []
            speeds: list[float] = []
            for sample_index in range(subdivisions + 1):
                t = sample_index / subdivisions
                point, curvature, speed = _span_eval(span, t)
                if not all(math.isfinite(value) for value in (*point, speed, curvature)):
                    raise ValueError(f"QUINTIC_SAMPLE_NONFINITE:{span.source_vertex_index}:{t}")
                points.append(point)
                curvatures.append(curvature)
                speeds.append(speed)
            parameter_evaluations += subdivisions + 1
            if min(speeds) <= GEOMETRY_EPSILON_MM:
                raise ValueError(f"QUINTIC_SAMPLE_NOT_REGULAR:{span.source_vertex_index}")
            start_curvature, _ = _curvature_from_controls(span.controls, at_end=False)
            end_curvature, _ = _curvature_from_controls(span.controls, at_end=True)
            if max(abs(start_curvature), abs(end_curvature)) > END_CURVATURE_TOLERANCE_PER_MM:
                raise ValueError(f"QUINTIC_ENDPOINT_CURVATURE_SAMPLE_CHECK_FAILED:{span.source_vertex_index}")
            curvature_reports.append({
                "profile_vertex_index": span.source_vertex_index,
                "sample_count_including_endpoints": subdivisions + 1,
                "minimum_sampled_speed_mm_per_unit_parameter": min(speeds),
                "maximum_sampled_curvature_per_mm": max(curvatures),
                "minimum_sampled_curvature_radius_mm": None if max(curvatures) <= 0.0 else 1.0 / max(curvatures),
                "endpoint_curvature_per_mm": [start_curvature, end_curvature],
                "regular_at_all_sampled_parameters": True,
            })
            span_sample = points
        else:
            raise ValueError(f"UNSUPPORTED_SPAN_KIND:{span.kind}")
        samples_by_span.append(span_sample)
        for point in span_sample[1:]:
            if _length(_sub(point, contour[-1])) > GEOMETRY_EPSILON_MM:
                contour.append(point)
        if _length(_sub(span.end, contour[-1])) > GEOMETRY_EPSILON_MM:
            raise ValueError(f"SPAN_CHAIN_DISCONTINUITY:{span_index}")
    return contour, samples_by_span, curvature_reports, parameter_evaluations


def _intersects(a: Point, b: Point, c: Point, d: Point, epsilon: float) -> bool:
    def on_segment(p: Point, q: Point, r: Point) -> bool:
        return (
            min(p[0], q[0]) - epsilon <= r[0] <= max(p[0], q[0]) + epsilon
            and min(p[1], q[1]) - epsilon <= r[1] <= max(p[1], q[1]) + epsilon
            and abs(_cross(_sub(q, p), _sub(r, p))) <= epsilon * max(1.0, _length(_sub(q, p)))
        )
    ab_c = _cross(_sub(b, a), _sub(c, a))
    ab_d = _cross(_sub(b, a), _sub(d, a))
    cd_a = _cross(_sub(d, c), _sub(a, c))
    cd_b = _cross(_sub(d, c), _sub(b, c))
    tol_ab = epsilon * max(1.0, _length(_sub(b, a)))
    tol_cd = epsilon * max(1.0, _length(_sub(d, c)))
    if ((ab_c > tol_ab and ab_d < -tol_ab) or (ab_c < -tol_ab and ab_d > tol_ab)) and (
        (cd_a > tol_cd and cd_b < -tol_cd) or (cd_a < -tol_cd and cd_b > tol_cd)
    ):
        return True
    return (
        (abs(ab_c) <= tol_ab and on_segment(a, b, c))
        or (abs(ab_d) <= tol_ab and on_segment(a, b, d))
        or (abs(cd_a) <= tol_cd and on_segment(c, d, a))
        or (abs(cd_b) <= tol_cd and on_segment(c, d, b))
    )


def _signed_area(points: Sequence[Point]) -> float:
    return sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    ) / 2.0


def check_simple_polyline(points: Sequence[Point], closed: bool, epsilon: float) -> dict[str, Any]:
    edges = list(zip(points, points[1:]))
    if closed:
        edges.append((points[-1], points[0]))
    if any(_length(_sub(b, a)) <= epsilon for a, b in edges):
        return {"simple": False, "reason": "ZERO_LENGTH_SAMPLED_EDGE", "crossing_edge_indices": []}
    crossings: list[list[int]] = []
    for i, (a, b) in enumerate(edges):
        for j in range(i + 1, len(edges)):
            if j == i + 1 or (closed and i == 0 and j == len(edges) - 1):
                continue
            c, d = edges[j]
            if _intersects(a, b, c, d, epsilon):
                crossings.append([i, j])
                if len(crossings) >= 8:
                    return {"simple": False, "reason": "SAMPLED_NONADJACENT_SEGMENTS_INTERSECT", "crossing_edge_indices": crossings}
    return {"simple": not crossings, "reason": None if not crossings else "SAMPLED_NONADJACENT_SEGMENTS_INTERSECT", "crossing_edge_indices": crossings}


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ab = _sub(b, a)
    denom = _dot(ab, ab)
    t = 0.0 if denom <= 0.0 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / denom))
    return _length(_sub(p, _add(a, _scale(ab, t))))


def sampled_polyline_distance(a: Sequence[Point], b: Sequence[Point], epsilon: float) -> float:
    a_edges, b_edges = list(zip(a, a[1:])), list(zip(b, b[1:]))
    minimum = math.inf
    for p0, p1 in a_edges:
        for q0, q1 in b_edges:
            if _intersects(p0, p1, q0, q1, epsilon):
                return 0.0
            minimum = min(
                minimum,
                _point_segment_distance(p0, q0, q1),
                _point_segment_distance(p1, q0, q1),
                _point_segment_distance(q0, p0, p1),
                _point_segment_distance(q1, p0, p1),
            )
    return minimum


def _sample_selected_spans(spans: Sequence[Span], samples_by_span: Sequence[Sequence[Point]], side_start: int) -> list[Point]:
    selected: list[Point] = []
    for span, samples in zip(spans, samples_by_span):
        is_side = (
            span.source_segment_index is not None and span.source_segment_index >= side_start
        ) or (
            span.source_vertex_index is not None and span.source_vertex_index >= side_start
        )
        if not is_side:
            continue
        for point in samples:
            if not selected or _length(_sub(point, selected[-1])) > GEOMETRY_EPSILON_MM:
                selected.append(point)
    return selected


def _profile_protection(family: str, side: str, points: Sequence[Point], profile: Any) -> dict[int, str]:
    protected = {
        0: (
            "outside axis/bottom endpoint at z=0; preserve axis and bottom datum"
            if side == "outer" else "inside axis/floor endpoint at declared base z; preserve axis and floor datum"
        ),
        len(points) - 1: (
            "outer lip endpoint; preserve total height and outer lip radius"
            if side == "outer" else "inside lip endpoint; preserve total height and clear mouth radius"
        ),
    }
    if side == "outer" and family == "bowl":
        maximum = float(profile.parameters["max_radius_mm"])
        indices = [i for i, (radius, _) in enumerate(points) if abs(radius - maximum) <= 1e-12]
        if len(indices) == 1 and indices[0] not in protected:
            protected[indices[0]] = "unique maximum-radius apex retained to preserve max_radius_mm; this corner remains sharp"
    return protected


def _profile_polygon_outline(outer: Sequence[Point], inner: Sequence[Point]) -> list[Point]:
    # Outer axis -> outer lip -> inner lip -> inner axis, with the axis closure implicit.
    return list(outer) + list(reversed(inner))


def _analyze_case(family: str, profile: Any) -> tuple[dict[str, Any], list[Point], list[Point]]:
    outer_original = [tuple(float(v) for v in point) for point in profile.outer_profile_mm]
    inner_original = [tuple(float(v) for v in point) for point in profile.inner_profile_mm]
    outer_protected = _profile_protection(family, "outer", outer_original, profile)
    inner_protected = _profile_protection(family, "inner", inner_original, profile)
    outer_spans, outer_corners = build_faired_profile("outer", outer_original, outer_protected)
    inner_spans, inner_corners = build_faired_profile("inner", inner_original, inner_protected)
    outer_points, outer_span_samples, outer_curvature, outer_evals = sample_spans(outer_spans)
    inner_points, inner_span_samples, inner_curvature, inner_evals = sample_spans(inner_spans)
    if outer_points[0] != outer_original[0] or outer_points[-1] != outer_original[-1]:
        raise ValueError(f"{family}_OUTER_AXIS_OR_LIP_ENDPOINT_MOVED")
    if inner_points[0] != inner_original[0] or inner_points[-1] != inner_original[-1]:
        raise ValueError(f"{family}_INNER_FLOOR_OR_MOUTH_ENDPOINT_MOVED")

    scale = max(float(profile.parameters["height_mm"]), float(profile.parameters["max_radius_mm"]))
    epsilon = scale * 1e-10
    section_original = _profile_polygon_outline(outer_original, inner_original)
    original_section_edges = list(zip(section_original, section_original[1:] + section_original[:1]))
    shortest_section_edge = min(_length(_sub(b, a)) for a, b in original_section_edges)
    if shortest_section_edge < MIN_ORIGINAL_SEGMENT_MM:
        raise ValueError(f"{family}_CLOSED_SECTION_EDGE_SHORTER_THAN_{MIN_ORIGINAL_SEGMENT_MM:g}_MM:{shortest_section_edge:.9g}")
    section_faired = _profile_polygon_outline(outer_points, inner_points)
    simple_checks = {
        "outer_profile": check_simple_polyline(outer_points, False, epsilon),
        "inner_profile": check_simple_polyline(inner_points, False, epsilon),
        "closed_material_section": check_simple_polyline(section_faired, True, epsilon),
    }
    if not all(row["simple"] for row in simple_checks.values()):
        raise ValueError(f"{family}_SAMPLED_FAIRING_SELF_INTERSECTION:{simple_checks}")

    # Side starts align with catalog outer[3:] and inner[2:]; fairings at these transitions are included.
    outer_wall = _sample_selected_spans(outer_spans, outer_span_samples, side_start=2)
    inner_wall = _sample_selected_spans(inner_spans, inner_span_samples, side_start=1)
    gap_before = sampled_polyline_distance(outer_original[2:], inner_original[1:], epsilon)
    gap_after = sampled_polyline_distance(outer_wall, inner_wall, epsilon)

    all_curvature = outer_curvature + inner_curvature
    quintic_corner_rows = [
        row for row in outer_corners + inner_corners if row.get("status") == "QUINTIC_FAIRING"
    ]
    endpoints_zero = all(
        abs(value) <= END_CURVATURE_TOLERANCE_PER_MM
        for row in all_curvature for value in row["endpoint_curvature_per_mm"]
    )
    max_sampled_curvature = max((row["maximum_sampled_curvature_per_mm"] for row in all_curvature), default=0.0)
    sample_evaluations = outer_evals + inner_evals
    params = {key: float(value) for key, value in profile.parameters.items()}
    invariants = {
        "axis_radius_mm": outer_points[0][0],
        "outer_bottom_z_mm": min(z for _, z in outer_points),
        "inner_floor_z_mm": inner_points[0][1],
        "mouth_clear_inside_diameter_mm": 2.0 * inner_points[-1][0],
        "total_height_mm": max(z for _, z in outer_points),
        "maximum_outer_radius_mm": max(r for r, _ in outer_points),
        "catalog_parameter_targets_match": (
            abs(outer_points[0][0]) <= epsilon
            and abs(min(z for _, z in outer_points)) <= epsilon
            and abs(inner_points[0][1] - params["base_thickness_declaration_mm"]) <= epsilon
            and abs(2.0 * inner_points[-1][0] - params["mouth_diameter_mm"]) <= epsilon
            and abs(max(z for _, z in outer_points) - params["height_mm"]) <= epsilon
            and abs(max(r for r, _ in outer_points) - params["max_radius_mm"]) <= epsilon
        ),
        "wall_declaration_preserved_as_profile_metadata": params["wall_thickness_declaration_mm"],
        "realized_wall_or_global_normal_minimum": "UNKNOWN_NOT_MEASURED; outer and inner profiles are faired independently",
    }
    if not invariants["catalog_parameter_targets_match"]:
        raise ValueError(f"{family}_SEMANTIC_PARAMETER_ENDPOINT_CHANGED:{invariants}")
    report = {
        "family": family,
        "status": "PASS_BOUNDED_MATH_DEFAULT_CASE_ONLY",
        "catalog_schema": profile.to_dict()["schema"],
        "units": "mm",
        "frame": "right-handed Z-up; profile points are (radius_mm,z_mm)",
        "catalog_parameters_unchanged": params,
        "parameter_ranges_mm": profile.to_dict()["parameter_ranges_mm"],
        "parameter_sources": profile.to_dict()["parameter_sources"],
        "catalog_wall_and_base_declarations": {
            "wall": profile.geometry_only_qualification["wall_declaration_interpretation"],
            "base": profile.geometry_only_qualification["base_declaration_interpretation"],
        },
        "fairing_policy": {
            "trim_scale": TRIM_SCALE,
            "trim_distance": "0.12 times the shorter adjacent segment length at each selected corner",
            "minimum_original_segment_mm": MIN_ORIGINAL_SEGMENT_MM,
            "maximum_combined_adjacent_trim_fraction": MAX_ADJACENT_TRIM_FRACTION,
            "control_fractions_on_each_trimmed_ray": list(CONTROL_FRACTIONS),
            "near_straight_skip_degrees": STRAIGHT_TURN_SKIP_DEG,
            "near_reversal_rejection_degrees": REVERSAL_REJECT_DEG,
            "curve_parameter_subdivisions_per_quintic": CURVE_SUBDIVISIONS,
            "total_curve_parameter_sample_cap_across_both_candidates": MAX_TOTAL_CURVE_PARAMETER_SAMPLES,
            "protected_corner_policy": "preserve open-profile axis/floor endpoints and both lip endpoints; retain a unique bowl max-radius apex so declared extrema remain exact",
        },
        "corner_treatment": {
            "outer_profile": outer_corners,
            "inner_profile": inner_corners,
            "quintic_controls_define_endpoint_tangent_and_zero_curvature": all(
                row.get("geometric_C2_join_by_tangent_and_zero_curvature") is True
                for row in outer_corners + inner_corners if row.get("status") == "QUINTIC_FAIRING"
            ),
            "retained_sharp_corner_count": sum(row.get("status") == "PROTECTED_SHARP_CORNER" for row in outer_corners + inner_corners),
        },
        "curvature_checks": {
            "regularity_and_curvature_sampled_at_each_quintic_parameter_grid": outer_curvature + inner_curvature,
            "all_sampled_bezier_parameters_regular": all(row["regular_at_all_sampled_parameters"] for row in all_curvature),
            "all_quintics_analytically_regular_for_all_parameters": all(
                row.get("global_regular_for_all_parameters_by_positive_derivative_projection") is True
                for row in quintic_corner_rows
            ),
            "all_quintics_have_finite_control_polygon_curvature_upper_bounds": all(
                math.isfinite(float(row.get("global_curvature_upper_bound_per_mm", math.inf)))
                and float(row.get("global_curvature_upper_bound_per_mm", 0.0)) > 0.0
                for row in quintic_corner_rows
            ),
            "remaining_straight_spans_regular_with_exact_zero_curvature": all(
                span.kind != "line" or _length(_sub(span.end, span.start)) > GEOMETRY_EPSILON_MM
                for span in outer_spans + inner_spans
            ),
            "straight_span_curvature_per_mm": 0.0,
            "per_corner_global_curvature_upper_bounds_per_mm": [
                {"profile_side": row["profile_side"], "vertex_index": row["vertex_index"], "upper_bound_per_mm": row["global_curvature_upper_bound_per_mm"]}
                for row in quintic_corner_rows
            ],
            "largest_quintic_curvature_upper_bound_per_mm": max(
                (float(row["global_curvature_upper_bound_per_mm"]) for row in quintic_corner_rows), default=0.0
            ),
            "all_endpoint_curvatures_zero_within_tolerance_per_mm": endpoints_zero,
            "endpoint_curvature_tolerance_per_mm": END_CURVATURE_TOLERANCE_PER_MM,
            "maximum_sampled_curvature_per_mm": max_sampled_curvature,
            "minimum_sampled_curvature_radius_mm": None if max_sampled_curvature <= 0.0 else 1.0 / max_sampled_curvature,
            "geometric_C2_scope": "each fairied join has matching tangent and zero geometric curvature; regular-curve arc-length reparameterization gives C2 at those joins",
            "shared_parameter_C2": "NOT_CLAIMED; parameter speed is not matched between independent line and Bezier spans",
            "whole_profile_C2": "NOT_CLAIMED; protected semantic corners remain angular",
        },
        "bounded_geometry_checks": {
            "original_section_signed_area_mm2": _signed_area(section_original),
            "shortest_original_closed_material_section_segment_mm": shortest_section_edge,
            "faired_sampled_section_signed_area_mm2": _signed_area(section_faired),
            "sampled_section_area_change_mm2": _signed_area(section_faired) - _signed_area(section_original),
            "simple_nonselfintersecting_checks": simple_checks,
            "all_control_poles_within_local_adjacent_segment_hull": all(
                row.get("all_controls_on_trimmed_adjacent_segments") is True
                for row in outer_corners + inner_corners if row.get("status") == "QUINTIC_FAIRING"
            ),
            "wall_side_sampled_polyline_pair_distance_before_mm": gap_before,
            "wall_side_sampled_polyline_pair_distance_after_mm": gap_after,
            "wall_side_sampled_pair_distance_delta_mm": gap_after - gap_before,
            "wall_distance_interpretation": "bounded 2D sampled contour-pair distance only; not normal thickness or a global minimum-wall proof",
            "curve_parameter_evaluations": sample_evaluations,
            "contour_sample_vertices_outer_plus_inner": len(outer_points) + len(inner_points),
        },
        "semantic_invariants": invariants,
        "original_outer_profile_mm": [list(point) for point in outer_original],
        "original_inner_profile_mm": [list(point) for point in inner_original],
        "faired_outer_sampled_profile_mm": [list(point) for point in outer_points],
        "faired_inner_sampled_profile_mm": [list(point) for point in inner_points],
        "native_cad": "NOT_RUN_BY_DESIGN",
        "step_export": "NOT_RUN_BY_DESIGN",
        "fracture_training_eligibility": "NOT_APPROVED_PENDING_ROOT_REVIEW_AND_FUTURE_NATIVE_VALIDATION",
        "unknowns": [
            "minimum global normal wall after independent inner/outer fairing",
            "local and global wall-thickness effects near each fairied corner",
            "stress concentration and fracture response at retained axis/lip/bowl-apex sharp corners",
            "self-intersection or curvature extrema between the bounded sample parameters (sample checks are not a global certificate)",
            "real-vessel/style correspondence and manufacturing feasibility",
            "native BRep, STEP, shell topology, mesh, material, solver, and fracture qualification",
        ],
    }
    return report, outer_points, inner_points


def _section_outline(outer: Sequence[Point], inner: Sequence[Point]) -> list[Point]:
    return list(outer) + list(reversed(inner))


def _mirror_polygon(section: Sequence[Point]) -> list[Point]:
    return list(section) + [(-radius, z) for radius, z in reversed(section)]


def _save_profile_plot(cases: Mapping[str, tuple[Any, dict[str, Any], list[Point], list[Point]]], destination: Path) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 7.0), dpi=135, facecolor="#faf8f3")
    for ax, family in zip(axes, ALLOWED_FAMILIES):
        profile, report, outer_faired, inner_faired = cases[family]
        outer_original = [tuple(point) for point in profile.outer_profile_mm]
        inner_original = [tuple(point) for point in profile.inner_profile_mm]
        original = _section_outline(outer_original, inner_original)
        proposed = _section_outline(outer_faired, inner_faired)
        ax.add_patch(Polygon(_mirror_polygon(proposed), closed=True, facecolor="#d9b377", alpha=0.20, edgecolor="none", zorder=1))
        original_mirror = [(-r, z) for r, z in reversed(original)]
        proposed_mirror = [(-r, z) for r, z in reversed(proposed)]
        ax.plot([p[0] for p in original], [p[1] for p in original], "--", color="#7c7c7c", linewidth=1.2, label="catalog polyline" if family == ALLOWED_FAMILIES[0] else None, zorder=2)
        ax.plot([p[0] for p in original_mirror], [p[1] for p in original_mirror], "--", color="#7c7c7c", linewidth=1.2, zorder=2)
        ax.plot([p[0] for p in proposed], [p[1] for p in proposed], color="#245b78", linewidth=1.8, label="proposed quintic fairing" if family == ALLOWED_FAMILIES[0] else None, zorder=3)
        ax.plot([p[0] for p in proposed_mirror], [p[1] for p in proposed_mirror], color="#245b78", linewidth=1.8, zorder=3)
        protected = report["corner_treatment"]["outer_profile"] + report["corner_treatment"]["inner_profile"]
        retained = [row["original_corner_rz_mm"] for row in protected if row.get("status") == "PROTECTED_SHARP_CORNER"]
        if retained:
            ax.scatter([p[0] for p in retained] + [-p[0] for p in retained], [p[1] for p in retained] * 2,
                       marker="x", s=28, color="#a44a3f", linewidths=1.0, label="protected sharp corner" if family == ALLOWED_FAMILIES[0] else None, zorder=4)
        radius = float(profile.parameters["max_radius_mm"])
        height = float(profile.parameters["height_mm"])
        ax.set_xlim(-radius * 1.12, radius * 1.12)
        ax.set_ylim(-2.0, height * 1.05)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("radius coordinate mirrored about axis (mm)")
        ax.set_ylabel("z (mm)")
        ax.set_title(f"{family.title()} default — source profile / fairing proposal")
        ax.grid(True, color="#dedbd3", linewidth=0.55)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.045))
    fig.suptitle("VesselForge catalog corner fairing — source-only mathematical proposal", fontsize=14, y=0.97)
    fig.text(0.5, 0.015, "No native CAD, STEP, material, solver, or fracture qualification was run.", ha="center", fontsize=8, color="#5d5a53")
    fig.tight_layout(rect=(0, 0.10, 1, 0.93))
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=135, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(destination), "bytes": destination.stat().st_size, "source": "catalog profiles plus sampled pure-Python quintic fairing", "native_CAD_used": False}


def run_source_only() -> int:
    started = time.monotonic()
    if not RUNTIME.is_file():
        raise FileNotFoundError(f"PINNED_RUNTIME_MISSING:{RUNTIME}")
    if OUTPUT_ROOT.exists():
        raise FileExistsError("CORNER_FAIRING_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE_OR_RETRY")
    OUTPUT_ROOT.mkdir(parents=True)
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["MPLCONFIGDIR"] = str(OUTPUT_ROOT / "matplotlib_config")
    before = _source_pins()
    _write_json(OUTPUT_ROOT / "PRE_RUN_SOURCE_PINS.json", before)
    result: dict[str, Any] = {
        "schema": "vesselforge.catalog_corner_fairing.source_only_design/1",
        "status": "RUNNING",
        "families": list(ALLOWED_FAMILIES),
        "native_cad_or_step_started": False,
        "source_pins_before": before,
    }
    try:
        build_profile = _load_catalog_builder()

        cases: dict[str, tuple[Any, dict[str, Any], list[Point], list[Point]]] = {}
        total_samples = 0
        total_contour_vertices = 0
        for family in ALLOWED_FAMILIES:
            profile = build_profile(family)
            outer_protected = _profile_protection(family, "outer", profile.outer_profile_mm, profile)
            inner_protected = _profile_protection(family, "inner", profile.inner_profile_mm, profile)
            # Document the protected set with reasons directly in the source report via the profile output.
            report, outer, inner = _analyze_case(family, profile)
            report["protected_vertices"] = {
                "outer": {str(k): v for k, v in outer_protected.items()},
                "inner": {str(k): v for k, v in inner_protected.items()},
            }
            total_samples += int(report["bounded_geometry_checks"]["curve_parameter_evaluations"])
            total_contour_vertices += int(report["bounded_geometry_checks"]["contour_sample_vertices_outer_plus_inner"])
            cases[family] = (profile, report, outer, inner)
        if total_samples > MAX_TOTAL_CURVE_PARAMETER_SAMPLES or total_contour_vertices > MAX_TOTAL_CURVE_PARAMETER_SAMPLES:
            raise ValueError(f"TOTAL_SOURCE_ONLY_SAMPLE_CAP_EXCEEDED:curve_parameters={total_samples};contour_vertices={total_contour_vertices}")
        if any(name == "cadquery" or name.startswith("cadquery.") or name == "OCP" or name.startswith("OCP.") for name in sys.modules):
            raise RuntimeError("NATIVE_GEOMETRY_ENGINE_IMPORTED_DURING_SOURCE_ONLY_STUDY")
        plot = _save_profile_plot(cases, OUTPUT_ROOT / "catalog_corner_fairing_profile_plot.png")
        loaded_native_modules = [
            name for name in sys.modules
            if name == "cadquery" or name.startswith("cadquery.") or name == "OCP" or name.startswith("OCP.")
        ]
        if loaded_native_modules:
            raise RuntimeError(f"NATIVE_GEOMETRY_ENGINE_IMPORTED_DURING_SOURCE_ONLY_PLOT:{loaded_native_modules[:5]}")
        after = _source_pins()
        _write_json(OUTPUT_ROOT / "POST_RUN_SOURCE_PINS.json", after)
        elapsed = time.monotonic() - started
        if elapsed > MAX_TOTAL_WALL_SECONDS:
            raise TimeoutError(f"SOURCE_ONLY_WALL_BUDGET_EXCEEDED:{elapsed:.6g}_SECONDS")
        if before != after:
            raise RuntimeError("PINNED_SOURCE_BYTES_CHANGED_DURING_SOURCE_ONLY_STUDY")
        result.update({
            "status": "PASS_BOUNDED_MATH_DESIGN_ONLY",
            "source_pins_after": after,
            "all_source_pins_unchanged": True,
            "wall_seconds": round(elapsed, 6),
            "sample_cap": {
                "limit": MAX_TOTAL_CURVE_PARAMETER_SAMPLES,
                "curve_parameter_evaluations_used": total_samples,
                "contour_sample_vertices_used": total_contour_vertices,
                "all_families_combined": True,
            },
            "cases": {family: cases[family][1] for family in ALLOWED_FAMILIES},
            "profile_plot": plot,
            "cad_imported": False,
            "step_exported": False,
            "fracture_training_eligibility": "NOT_APPROVED_PENDING_ROOT_REVIEW_AND_FUTURE_NATIVE_VALIDATION",
        })
    except Exception as exc:
        try:
            after = _source_pins()
            _write_json(OUTPUT_ROOT / "POST_RUN_SOURCE_PINS.json", after)
        except Exception:
            after = None
        result.update({
            "status": "FAIL_OR_UNKNOWN_SOURCE_ONLY_DESIGN",
            "source_pins_after": after,
            "all_source_pins_unchanged": after == before if after is not None else None,
            "failure_type": type(exc).__name__,
            "failure_reason": str(exc),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": round(time.monotonic() - started, 6),
        })
    _write_json(OUTPUT_ROOT / "DESIGN_AUDIT.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS_BOUNDED_MATH_DESIGN_ONLY" else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        return run_source_only()
    except Exception as exc:
        print(json.dumps({
            "status": "BLOCKED_BEFORE_SOURCE_ONLY_RUN",
            "failure_type": type(exc).__name__,
            "failure_reason": str(exc),
            "traceback": traceback.format_exc(),
        }, indent=2, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
