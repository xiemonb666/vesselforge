"""Exact Bernstein curvature certificates for the fixed C3 profile cases.

Source only until the caller explicitly passes root_ready=True. This module
constructs exact rational Bezier poles from fixed endpoint jets, forms
S^3-R^2 D^2 in Bernstein form, and certifies by coefficient signs and exact
midpoint de Casteljau subdivision. It does not sample curve points or use CAD.
"""

from __future__ import annotations

import hashlib
import json
import time
from fractions import Fraction
from math import comb
from pathlib import Path
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CASE_FILE = HERE / "fixed_cases.json"
OUTPUT_DIR = ROOT / "vesselforge" / "tmp" / "review_20261006" / "exact_curvature_certificate_20261006"
EXPECTED_CASE_SHA256 = "e1e9c3cf659dbc59d99a18c4b70694201518be4f3aba09a57806402e732cf95a"
PRIOR_PROFILE_SOURCE_SHA256 = "057233b930a2b8e0e3ef43a3568f1cb0e6e972baed97eeeece6459d9de8c951"
PRIOR_DIAGNOSTIC_SHA256 = "eb60138fc559d5a06ab2b4febf82fdc6654e6bbeab84f05f847c65934ffbbd4f"
MAX_DEPTH = 8
MAX_NODES_PER_TARGET = 256
MAX_GLOBAL_NODES = 1024
DEADLINE_SECONDS = 30.0

Scalar = Fraction
Point = tuple[Scalar, Scalar]
Coefficients = tuple[Scalar, ...]


def _pair(values: Sequence[str]) -> Point:
    if len(values) != 2:
        raise ValueError("RZ_POINT_MUST_HAVE_TWO_COORDINATES")
    return Fraction(values[0]), Fraction(values[1])


def _add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def _sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def _scale(a: Point, value: Scalar) -> Point:
    return a[0] * value, a[1] * value


def _controls(row: dict[str, Any], stations: dict[str, Any]) -> tuple[Point, ...]:
    """Reproduce the fixed degree-seven endpoint 0-1-2-3 Hermite formula."""
    h = Fraction(row["h_mm"])
    if h <= 0:
        raise ValueError(f"NONPOSITIVE_SPAN_LENGTH:{row['semantic']}")
    start, end = stations[row["from"]], stations[row["to"]]
    p0, p1 = _pair(start["rz_mm"]), _pair(end["rz_mm"])
    v0, v1 = _pair(start["d1"]), _pair(end["d1"])
    a0, a1 = _pair(start["d2"]), _pair(end["d2"])
    j0, j1 = _pair(start["d3"]), _pair(end["d3"])
    h7, h2_42, h2_14, h3_210 = h / 7, h * h / 42, h * h / 14, h * h * h / 210
    return (
        p0,
        _add(p0, _scale(v0, h7)),
        _add(_add(p0, _scale(v0, 2 * h7)), _scale(a0, h2_42)),
        _add(_add(_add(p0, _scale(v0, 3 * h7)), _scale(a0, h2_14)), _scale(j0, h3_210)),
        _add(_sub(p1, _scale(v1, 3 * h7)), _sub(_scale(a1, h2_14), _scale(j1, h3_210))),
        _add(_sub(p1, _scale(v1, 2 * h7)), _scale(a1, h2_42)),
        _sub(p1, _scale(v1, h7)),
        p1,
    )


def _derivative(points: Sequence[Point]) -> tuple[Point, ...]:
    degree = len(points) - 1
    return tuple(_scale(_sub(points[i + 1], points[i]), Fraction(degree)) for i in range(degree))


def _second_derivative(first: Sequence[Point]) -> tuple[Point, ...]:
    degree = len(first) - 1
    return tuple(_scale(_sub(first[i + 1], first[i]), Fraction(degree)) for i in range(degree))


def _projection_proof(points: Sequence[Point], row: dict[str, Any]) -> dict[str, Any]:
    w = _pair(row["projection_w"])
    norm_upper = Fraction(row["projection_norm_upper"])
    norm_sq = w[0] * w[0] + w[1] * w[1]
    projections = tuple(w[0] * p[0] + w[1] * p[1] for p in _derivative(points))
    minimum = min(projections)
    valid = norm_upper > 0 and norm_upper * norm_upper >= norm_sq and minimum > 0
    return {
        "status": "STRICT_SPEED_LOWER_BOUND" if valid else "UNKNOWN_STRICT_PROJECTION_NOT_PROVED",
        "projection_w": [str(w[0]), str(w[1])],
        "projection_norm_upper": str(norm_upper),
        "minimum_derivative_control_projection": str(minimum),
        "speed_lower_per_local_parameter": str(minimum / norm_upper) if valid else None,
        "reason": "positive Bernstein derivative projection proves S=||C'||^2>0" if valid else "declared projection does not prove a positive speed lower bound",
    }


def _bernstein_product(a: Coefficients, b: Coefficients) -> Coefficients:
    m, n = len(a) - 1, len(b) - 1
    out = [Fraction(0) for _ in range(m + n + 1)]
    for i, av in enumerate(a):
        for j, bv in enumerate(b):
            k = i + j
            out[k] += av * bv * Fraction(comb(m, i) * comb(n, j), comb(m + n, k))
    return tuple(out)


def _bernstein_sum(a: Coefficients, b: Coefficients) -> Coefficients:
    if len(a) != len(b):
        raise ValueError("BERNSTEIN_DEGREE_MISMATCH")
    return tuple(x + y for x, y in zip(a, b))


def _bernstein_difference(a: Coefficients, b: Coefficients) -> Coefficients:
    if len(a) != len(b):
        raise ValueError("BERNSTEIN_DEGREE_MISMATCH")
    return tuple(x - y for x, y in zip(a, b))


def _elevate(a: Coefficients, target_degree: int) -> Coefficients:
    result = tuple(a)
    while len(result) - 1 < target_degree:
        degree = len(result) - 1
        next_row = [result[0]] + [Fraction(0)] * degree + [result[-1]]
        for i in range(1, degree + 1):
            next_row[i] = Fraction(i, degree + 1) * result[i - 1] + Fraction(degree + 1 - i, degree + 1) * result[i]
        result = tuple(next_row)
    if len(result) - 1 != target_degree:
        raise ValueError("BERNSTEIN_ELEVATION_TARGET_BELOW_DEGREE")
    return result


def _curvature_polynomial(points: Sequence[Point], radius: Scalar) -> Coefficients:
    first = _derivative(points)
    second = _second_derivative(first)
    x1, y1 = tuple(p[0] for p in first), tuple(p[1] for p in first)
    x2, y2 = tuple(p[0] for p in second), tuple(p[1] for p in second)
    speed_sq = _bernstein_sum(_bernstein_product(x1, x1), _bernstein_product(y1, y1))
    det = _bernstein_difference(_bernstein_product(x1, y2), _bernstein_product(y1, x2))
    speed_cubed = _bernstein_product(_bernstein_product(speed_sq, speed_sq), speed_sq)
    det_sq = _elevate(_bernstein_product(det, det), 36)
    return tuple(a - radius * radius * b for a, b in zip(speed_cubed, det_sq))


def _split_midpoint(values: Coefficients) -> tuple[Coefficients, Coefficients]:
    levels = [list(values)]
    while len(levels[-1]) > 1:
        prior = levels[-1]
        levels.append([(prior[i] + prior[i + 1]) / 2 for i in range(len(prior) - 1)])
    return tuple(level[0] for level in levels), tuple(level[-1] for level in reversed(levels))


def _cover_certificate(
    coefficients: Coefficients, *, strict: bool, budget: dict[str, Any]
) -> dict[str, Any]:
    stack = [(coefficients, Fraction(0), Fraction(1), 0)]
    leaves: list[dict[str, Any]] = []
    target_nodes = 0
    while stack:
        coeffs, lo, hi, depth = stack.pop()
        if target_nodes >= MAX_NODES_PER_TARGET:
            leaves.append(_leaf(coeffs, lo, hi, depth, "UNKNOWN", "MAX_NODES_PER_TARGET"))
            for pending, a, b, d in stack:
                leaves.append(_leaf(pending, a, b, d, "UNKNOWN", "MAX_NODES_PER_TARGET"))
            stack.clear()
            break
        if budget["nodes"] >= MAX_GLOBAL_NODES:
            leaves.append(_leaf(coeffs, lo, hi, depth, "UNKNOWN", "MAX_GLOBAL_NODES"))
            for pending, a, b, d in stack:
                leaves.append(_leaf(pending, a, b, d, "UNKNOWN", "MAX_GLOBAL_NODES"))
            stack.clear()
            break
        if time.monotonic() - budget["started"] >= DEADLINE_SECONDS:
            leaves.append(_leaf(coeffs, lo, hi, depth, "UNKNOWN", "DEADLINE_30S"))
            for pending, a, b, d in stack:
                leaves.append(_leaf(pending, a, b, d, "UNKNOWN", "DEADLINE_30S"))
            stack.clear()
            break
        target_nodes += 1
        budget["nodes"] += 1
        left_endpoint, right_endpoint = coeffs[0], coeffs[-1]
        if (strict and (left_endpoint <= 0 or right_endpoint <= 0)) or (not strict and (left_endpoint < 0 or right_endpoint < 0)):
            leaves.append(_leaf(coeffs, lo, hi, depth, "FAIL_CERTIFIED", "EXACT_ENDPOINT_VIOLATION"))
            continue
        if all(c >= 0 for c in coeffs) and (not strict or (left_endpoint > 0 and right_endpoint > 0)):
            leaves.append(_leaf(coeffs, lo, hi, depth, "PASS", "BERNSTEIN_COEFFICIENTS_PROVE_SIGN"))
            continue
        if all(c <= 0 for c in coeffs) and any(c < 0 for c in coeffs):
            leaves.append(_leaf(coeffs, lo, hi, depth, "FAIL_CERTIFIED", "NEGATIVE_ON_OPEN_INTERVAL"))
            continue
        if strict and all(c == 0 for c in coeffs):
            leaves.append(_leaf(coeffs, lo, hi, depth, "FAIL_CERTIFIED", "IDENTICALLY_ZERO_NOT_STRICT"))
            continue
        if depth >= MAX_DEPTH:
            leaves.append(_leaf(coeffs, lo, hi, depth, "UNKNOWN", "MAX_DEPTH_8"))
            continue
        left, right = _split_midpoint(coeffs)
        middle = (lo + hi) / 2
        stack.append((right, middle, hi, depth + 1))
        stack.append((left, lo, middle, depth + 1))
    leaves.sort(key=lambda leaf: Fraction(leaf["interval"][0]))
    _assert_complete_cover(leaves)
    statuses = {leaf["status"] for leaf in leaves}
    status = "FAIL_CERTIFIED" if "FAIL_CERTIFIED" in statuses else "PASS" if statuses == {"PASS"} else "UNKNOWN"
    return {"status": status, "nodes": target_nodes, "cover": leaves}


def _leaf(coefficients: Coefficients, lo: Scalar, hi: Scalar, depth: int, status: str, reason: str) -> dict[str, Any]:
    return {
        "interval": [str(lo), str(hi)],
        "depth": depth,
        "status": status,
        "reason": reason,
        "bernstein_coefficients": [str(value) for value in coefficients],
    }


def _assert_complete_cover(leaves: Sequence[dict[str, Any]]) -> None:
    if not leaves or Fraction(leaves[0]["interval"][0]) != 0 or Fraction(leaves[-1]["interval"][1]) != 1:
        raise ValueError("INCOMPLETE_CERTIFICATE_COVER")
    for left, right in zip(leaves, leaves[1:]):
        if Fraction(left["interval"][1]) != Fraction(right["interval"][0]):
            raise ValueError("GAP_OR_OVERLAP_IN_CERTIFICATE_COVER")


def _target_radius(region: str, family: str, targets: dict[str, Any]) -> Scalar | None:
    if region in {"base", "base_transition"}:
        return Fraction(targets["base_and_inner_base_fairing_minimum_radius_mm"][family])
    if region == "lip_closure":
        return None
    return Fraction(targets["body_and_shoulder_minimum_radius_mm"])


def _unstarted(reason: str, **fields: Any) -> dict[str, Any]:
    return {
        "status": "UNKNOWN",
        **fields,
        "cover": [{"interval": ["0", "1"], "depth": 0, "status": "UNKNOWN", "reason": reason, "bernstein_coefficients": None}],
    }


def _certify_radius(points: Sequence[Point], radius: Scalar, proof: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    if proof["status"] != "STRICT_SPEED_LOWER_BOUND":
        return _unstarted("STRICT_SPEED_LOWER_BOUND_NOT_PROVED", radius_mm=str(radius))
    if time.monotonic() - budget["started"] >= DEADLINE_SECONDS:
        return _unstarted("DEADLINE_30S_BEFORE_POLYNOMIAL", radius_mm=str(radius))
    polynomial = _curvature_polynomial(points, radius)
    result = _cover_certificate(polynomial, strict=False, budget=budget)
    return {"radius_mm": str(radius), "polynomial": "S^3 - R^2 D^2", "degree": 36, **result}


def _certify_offset(points: Sequence[Point], proof: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    if proof["status"] != "STRICT_SPEED_LOWER_BOUND":
        return _unstarted("STRICT_SPEED_LOWER_BOUND_NOT_PROVED", offset_distance_mm="3")
    if time.monotonic() - budget["started"] >= DEADLINE_SECONDS:
        return _unstarted("DEADLINE_30S_BEFORE_POLYNOMIAL", offset_distance_mm="3")
    polynomial = _curvature_polynomial(points, Fraction(3))
    result = _cover_certificate(polynomial, strict=True, budget=budget)
    return {"offset_distance_mm": "3", "condition": "S^3 - 9 D^2 > 0", "degree": 36, **result}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_exact_curvature_certificate(*, root_ready: bool = False) -> dict[str, Any]:
    """Run once after root review; output path and case input are fixed."""
    if root_ready is not True:
        raise PermissionError("ROOT_READY_REQUIRED_FOR_EXACT_CURVATURE_CERTIFICATE")
    if CASE_FILE.resolve() != (HERE / "fixed_cases.json").resolve():
        raise ValueError("FIXED_CASE_PATH_REQUIRED")
    case_sha = _sha256(CASE_FILE)
    if case_sha != EXPECTED_CASE_SHA256:
        raise ValueError("FIXED_CASE_SHA256_MISMATCH")
    output_file = OUTPUT_DIR / "exact_curvature_certificate.json"
    if output_file.exists():
        raise FileExistsError("FIXED_CERTIFICATE_OUTPUT_ALREADY_EXISTS")
    source = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    budget: dict[str, Any] = {"started": time.monotonic(), "nodes": 0}
    cases: dict[str, Any] = {}
    for family in ("bowl", "jar"):
        case = source["cases"][family]
        prior_end = None
        span_rows = []
        wall_names = set(case["normal_offset_side_spans"])
        for row in case["outer_spans"]:
            start, end = case["outer_stations"][row["from"]], case["outer_stations"][row["to"]]
            if prior_end is not None and prior_end != start:
                raise ValueError(f"SHARED_C3_JET_MISMATCH:{family}:{row['semantic']}")
            prior_end = end
            controls = _controls(row, case["outer_stations"])
            projection = _projection_proof(controls, row)
            radius = _target_radius(row["region"], family, source["curvature_targets"])
            radius_result = (
                {"status": "REPORT_ONLY_NO_RADIUS_TARGET", "radius_mm": None, "cover": []}
                if radius is None
                else _certify_radius(controls, radius, projection, budget)
            )
            offset_result = _certify_offset(controls, projection, budget) if row["semantic"] in wall_names else None
            span_rows.append({
                "semantic": row["semantic"],
                "region": row["region"],
                "strict_projection_proof": projection,
                "curvature_radius_certificate": radius_result,
                "three_mm_local_offset_certificate": offset_result,
            })
        if len(span_rows) != len(case["outer_spans"]) or len(span_rows) != 8:
            raise ValueError(f"FIXED_OUTER_SPAN_COUNT_MISMATCH:{family}")
        cases[family] = {"outer_span_count": len(span_rows), "spans": span_rows}
    payload = {
        "status": "PURE_EXACT_LOCAL_CURVATURE_CERTIFICATE",
        "phase": "SYMBOLIC_CERTIFICATE_ONLY",
        "units": "mm",
        "curvature_identity": "kappa = D / S^(3/2), S=||C'||^2, D=det(C',C'')",
        "radius_criterion": "S^3 - R^2 D^2 >= 0, with strict projection proving S>0",
        "offset_criterion": "S^3 - 9 D^2 > 0 on each declared 3 mm side-wall span",
        "algorithm": "exact Fraction Bernstein products, degree elevation, coefficient sign tests, midpoint de Casteljau covers",
        "limits": {"max_depth_per_target": MAX_DEPTH, "max_nodes_per_target": MAX_NODES_PER_TARGET, "max_global_nodes": MAX_GLOBAL_NODES, "deadline_seconds": DEADLINE_SECONDS, "global_nodes_used": budget["nodes"]},
        "provenance": {"fixed_cases_sha256": case_sha, "prior_profile_design_sha256": PRIOR_PROFILE_SOURCE_SHA256, "prior_math_diagnostic_sha256": PRIOR_DIAGNOSTIC_SHA256},
        "cases": cases,
        "global_minimum_wall_status": "UNKNOWN",
        "self_intersection_status": "UNKNOWN",
        "material_thickness_claim": "NONE",
        "cad_step_solver_status": "NOT_RUN",
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return payload
