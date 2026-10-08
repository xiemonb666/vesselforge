"""Source-only exact minimum-jerk KKT/Bezier plan; inert on import and root-ready gated."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction as F
from math import comb
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from .bspline_constraint_source import CONTROL_COUNT, DEGREE, INTERNAL_KNOTS, KNOT_VECTOR, ScalarEquation, build_case_constraint_rows
except ImportError:
    from bspline_constraint_source import CONTROL_COUNT, DEGREE, INTERNAL_KNOTS, KNOT_VECTOR, ScalarEquation, build_case_constraint_rows

HERE = Path(__file__).resolve().parent
CASE_FILE = HERE / "fixed_cases.json"
OUTPUT_ROOT = HERE.parents[1] / "tmp" / "review_20261006" / "global_bspline_meridian_20261006" / "minimum_jerk_candidate"
BREAKS = (F(0), *INTERNAL_KNOTS, F(1))
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
Vector = tuple[F, ...]
Matrix = tuple[tuple[F, ...], ...]
Point = tuple[F, F]
Span = tuple[Point, ...]


def _add(a: Vector, b: Vector) -> Vector:
    return tuple(x + y for x, y in zip(a, b, strict=True))


def _blend(a: Vector, b: Vector, t: F) -> Vector:
    return _add(tuple(t * x for x in a), tuple((1 - t) * x for x in b))


def _find_span(knots: Sequence[F], p: int, n: int, u: F) -> int:
    for k in range(p, n + 1):
        if knots[k] <= u < knots[k + 1]:
            return k
    raise ValueError("KNOT_INSERTION_PARAMETER_HAS_NO_SPAN")


def boehm_insert_once(controls: Sequence[Vector], knots: Sequence[F], p: int, u: F) -> tuple[tuple[Vector, ...], tuple[F, ...]]:
    """One exact Boehm insertion; input rows may be scalar basis vectors."""
    n = len(controls) - 1
    s = sum(knot == u for knot in knots)
    if s >= p:
        raise ValueError("KNOT_ALREADY_HAS_BEZIER_MULTIPLICITY")
    k = _find_span(knots, p, n, u)
    q: list[Vector | None] = [None] * (n + 2)
    for i in range(k - p + 1):
        q[i] = controls[i]
    for i in range(k - s, n + 1):
        q[i + 1] = controls[i]
    for i in range(k - p + 1, k - s + 1):
        den = knots[i + p] - knots[i]
        if den <= 0:
            raise ValueError("NONPOSITIVE_BOEHM_DENOMINATOR")
        q[i] = _blend(controls[i], controls[i - 1], (u - knots[i]) / den)
    if any(row is None for row in q):
        raise ValueError("BOEHM_INSERTION_LEFT_UNFILLED_CONTROL")
    return tuple(row for row in q if row is not None), tuple(knots[:k + 1]) + (u,) + tuple(knots[k + 1:])


def exact_bezier_extraction() -> tuple[Matrix, ...]:
    """Exact map from 11 B-spline poles to six overlapping 6-pole spans."""
    controls: tuple[Vector, ...] = tuple(tuple(F(i == j) for j in range(CONTROL_COUNT)) for i in range(CONTROL_COUNT))
    knots = KNOT_VECTOR
    for u in INTERNAL_KNOTS:
        while sum(knot == u for knot in knots) < DEGREE:
            controls, knots = boehm_insert_once(controls, knots, DEGREE, u)
    if len(controls) != 1 + (len(BREAKS) - 1) * DEGREE:
        raise ValueError("UNEXPECTED_BEZIER_EXTRACTION_CONTROL_COUNT")
    return tuple(tuple(controls[i * DEGREE:i * DEGREE + DEGREE + 1]) for i in range(len(BREAKS) - 1))


def _prod(a: Sequence[F], b: Sequence[F]) -> tuple[F, ...]:
    m, n = len(a) - 1, len(b) - 1
    return tuple(sum((F(comb(m, i) * comb(n, k - i), comb(m + n, k)) * a[i] * b[k - i]
                      for i in range(max(0, k - n), min(m, k) + 1)), F(0))
                 for k in range(m + n + 1))


def _sum(a: Sequence[F], b: Sequence[F]) -> tuple[F, ...]:
    if len(a) != len(b):
        raise ValueError("BERNSTEIN_DEGREE_MISMATCH")
    return tuple(x + y for x, y in zip(a, b, strict=True))


def _elevate(a: Sequence[F], degree: int) -> tuple[F, ...]:
    out = tuple(a)
    while len(out) - 1 < degree:
        p = len(out) - 1
        out = tuple((F(i, p + 1) * out[i - 1] if i else F(0)) +
                    (F(p + 1 - i, p + 1) * out[i] if i <= p else F(0))
                    for i in range(p + 2))
    if len(out) - 1 != degree:
        raise ValueError("BERNSTEIN_ELEVATION_TARGET_TOO_SMALL")
    return out


def exact_minimum_jerk_hessian(extraction: Sequence[Matrix]) -> Matrix:
    """H such that x.T H x is sum integral ||C'''(u)||^2 du."""
    p, n = DEGREE, CONTROL_COUNT
    hessian = [[F(0) for _ in range(n)] for _ in range(n)]
    differences = tuple(tuple(F(-1 if j == i else 3 if j == i + 1 else -3 if j == i + 2 else 1 if j == i + 3 else 0)
                              for j in range(p + 1)) for i in range(p - 2))
    gram = tuple(tuple(F(comb(2, i) * comb(2, j), 5 * comb(4, i + j)) for j in range(3)) for i in range(3))
    for index, span in enumerate(extraction):
        h = BREAKS[index + 1] - BREAKS[index]
        scale = F((p * (p - 1) * (p - 2)) ** 2) / h ** 5
        rows = tuple(tuple(sum((diff[a] * span[a][c] for a in range(p + 1)), F(0)) for c in range(n)) for diff in differences)
        for i in range(n):
            for j in range(n):
                hessian[i][j] += scale * sum((gram[a][b] * rows[a][i] * rows[b][j]
                                                for a in range(3) for b in range(3)), F(0))
    return tuple(tuple(row) for row in hessian)


def _rank(a: Sequence[Sequence[F]]) -> int:
    w = [list(row) for row in a]
    if not w:
        return 0
    r = 0
    for c in range(len(w[0])):
        pivot = next((i for i in range(r, len(w)) if w[i][c]), None)
        if pivot is None:
            continue
        w[r], w[pivot] = w[pivot], w[r]
        value = w[r][c]
        w[r] = [x / value for x in w[r]]
        for i in range(r + 1, len(w)):
            factor = w[i][c]
            if factor:
                w[i] = [x - factor * y for x, y in zip(w[i], w[r], strict=True)]
        r += 1
        if r == len(w):
            break
    return r


def _solve(a: Sequence[Sequence[F]], b: Sequence[F]) -> tuple[F, ...]:
    n = len(a)
    if not n or len(b) != n or any(len(row) != n for row in a):
        raise ValueError("FRACTION_SYSTEM_MUST_BE_NONEMPTY_AND_SQUARE")
    w = [list(row) + [v] for row, v in zip(a, b, strict=True)]
    for c in range(n):
        pivot = next((i for i in range(c, n) if w[i][c]), None)
        if pivot is None:
            raise ValueError("SINGULAR_KKT_NO_RIDGE_OR_PSEUDOINVERSE")
        w[c], w[pivot] = w[pivot], w[c]
        v = w[c][c]
        w[c] = [x / v for x in w[c]]
        for i in range(n):
            if i != c and w[i][c]:
                f = w[i][c]
                w[i] = [x - f * y for x, y in zip(w[i], w[c], strict=True)]
    return tuple(w[i][-1] for i in range(n))


def _dot(a: Sequence[F], b: Sequence[F]) -> F:
    return sum((x * y for x, y in zip(a, b, strict=True)), F(0))


def _matrix_hash(matrix: Sequence[Sequence[F]], rhs: Sequence[F]) -> str:
    text = "\n".join(",".join(map(str, row)) for row in matrix) + "\n|" + ",".join(map(str, rhs))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _coordinate_rows(plan: Mapping[str, Any], coordinate: str) -> tuple[Matrix, tuple[F, ...]]:
    equations: tuple[ScalarEquation, ...] = tuple(e for e in plan["linear_equalities"] if e.coordinate == coordinate)
    return tuple(e.coefficients for e in equations), tuple(e.rhs for e in equations)


def _solve_coordinate(h: Matrix, plan: Mapping[str, Any], coordinate: str) -> dict[str, Any]:
    a, b = _coordinate_rows(plan, coordinate)
    n, m = CONTROL_COUNT, len(a)
    rank = _rank(a)
    if rank != m:
        raise ValueError("LINEAR_EQUALITY_ROWS_RANK_DEFICIENT")
    kkt = [[F(0) for _ in range(n + m)] for _ in range(n + m)]
    for i in range(n):
        for j in range(n):
            kkt[i][j] = 2 * h[i][j]
    for r, row in enumerate(a):
        for c, value in enumerate(row):
            kkt[c][n + r] = kkt[n + r][c] = value
    rhs = (F(0),) * n + b
    solution = _solve(kkt, rhs)
    x, lagrange = solution[:n], solution[n:]
    if any(_dot(row, x) != value for row, value in zip(a, b, strict=True)):
        raise ValueError("EXACT_EQUALITY_RESIDUAL_NONZERO")
    if any(_dot(row, solution) != value for row, value in zip(kkt, rhs, strict=True)):
        raise ValueError("EXACT_KKT_RESIDUAL_NONZERO")
    objective = sum((x[i] * h[i][j] * x[j] for i in range(n) for j in range(n)), F(0))
    return {"controls": x, "multipliers": tuple(map(str, lagrange)), "equalities": m, "equality_rank": rank,
            "kkt_dimension": n + m, "objective": objective, "exact_residuals_zero": True,
            "kkt_matrix_rhs_sha256": _matrix_hash(kkt, rhs)}


def _derivatives(span: Span, h: F) -> tuple[tuple[Point, ...], tuple[Point, ...]]:
    p = DEGREE
    first = tuple(tuple(F(p) * (span[i + 1][a] - span[i][a]) / h for a in range(2)) for i in range(p))
    second = tuple(tuple(F(p * (p - 1)) * (span[i + 2][a] - 2 * span[i + 1][a] + span[i][a]) / h ** 2
                         for a in range(2)) for i in range(p - 1))
    return first, second


def _endpoint_jet(span: Span, h: F, order: int, at_end: bool) -> Point:
    values = tuple(span)
    for _ in range(order):
        degree = len(values) - 1
        values = tuple(tuple(F(degree) * (values[i + 1][axis] - values[i][axis]) / h
                             for axis in range(2)) for i in range(degree))
    return values[-1] if at_end else values[0]


def radius_polynomial(span: Span, h: F, radius: F) -> tuple[F, ...]:
    """Exact degree-24 Bernstein coefficients of S^3-R^2 D^2."""
    first, second = _derivatives(span, h)
    r1, z1 = tuple(v[0] for v in first), tuple(v[1] for v in first)
    r2, z2 = tuple(v[0] for v in second), tuple(v[1] for v in second)
    speed2 = _sum(_prod(r1, r1), _prod(z1, z1))
    det = tuple(x - y for x, y in zip(_prod(r1, z2), _prod(z1, r2), strict=True))
    speed6 = _prod(_prod(speed2, speed2), speed2)
    det2 = _elevate(_prod(det, det), 24)
    return tuple(x - radius * radius * y for x, y in zip(speed6, det2, strict=True))


def _ineq_results(plan: Mapping[str, Any], controls: Mapping[str, Sequence[F]]) -> list[dict[str, Any]]:
    rows = []
    for item in plan["linear_inequalities"]:
        value = _dot(item.coefficients, controls[item.coordinate])
        passed = value > item.rhs if item.relation == ">" else value < item.rhs
        rows.append({"name": item.name, "coordinate": item.coordinate, "value": str(value),
                     "relation": item.relation, "rhs": str(item.rhs), "strict_status": "PASS" if passed else "FAIL"})
    return rows


def _span_checks(case: Mapping[str, Any], spans: Sequence[Span]) -> dict[str, Any]:
    max_r = F(case["fixed_dimensions"]["max_outer_radius_mm"])
    mouth_z = F(case["fixed_dimensions"]["mouth_datum_z_mm"])
    apex_u = F(next(row["u"] for row in case["fixed_feature_constraints"] if row["name"] == case["apex_feature"]))
    apex_index = BREAKS.index(apex_u)
    targets = (("body_shoulder", F(case["curvature_targets"]["body_and_shoulder_radius_mm"])),
               ("base_turn_unassigned", F(case["curvature_targets"]["outer_base_turn_radius_mm"])))
    records = []
    for i, span in enumerate(spans):
        h = BREAKS[i + 1] - BREAKS[i]
        first, _ = _derivatives(span, h)
        dz_ok, dz_positive = all(v[1] >= 0 for v in first), any(v[1] > 0 for v in first)
        dr_ok = all(v[0] >= 0 for v in first) if i < apex_index else all(v[0] <= 0 for v in first)
        regular_open = dz_ok and dz_positive
        endpoint_regular = first[0] != (F(0), F(0)) and first[-1] != (F(0), F(0))
        hull_ok = all(0 <= r <= max_r and 0 <= z <= mouth_z for r, z in span)
        screens = {}
        for name, radius in targets:
            coeff = radius_polynomial(span, h, radius)
            if all(v >= 0 for v in coeff) and regular_open and endpoint_regular:
                status = "PROVED_RADIUS_SCREEN_ON_CLOSED_SPAN"
            elif all(v >= 0 for v in coeff):
                status = "POLYNOMIAL_NONNEGATIVE_BUT_REGULARITY_NOT_CERTIFIED"
            elif coeff[0] < 0 or coeff[-1] < 0:
                status = "POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT"
            else:
                status = "UNKNOWN_MIXED_BERNSTEIN_COEFFICIENTS"
            screens[name] = {"radius_mm": str(radius), "degree": 24, "coefficients": list(map(str, coeff)), "status": status,
                             "regularity_status": "PROVED_CLOSED_SPAN" if regular_open and endpoint_regular else "NOT_CERTIFIED"}
        records.append({"span": i, "u": [str(BREAKS[i]), str(BREAKS[i + 1])], "base_region": "UNASSIGNED",
                        "bezier_poles_rz_mm": [[str(r), str(z)] for r, z in span],
                        "hull_bounds_rz_mm": [str(min(p[0] for p in span)), str(max(p[0] for p in span)),
                                              str(min(p[1] for p in span)), str(max(p[1] for p in span))],
                        "hull_poles_in_fixed_bbox": hull_ok,
                        "hull_certificate_status": "PROVED_BY_CONTROL_HULL" if hull_ok else "NOT_CERTIFIED_BY_CONTROL_HULL",
                        "z_derivative_poles_nonnegative": dz_ok,
                        "vertical_monotonicity_status": "PROVED_BY_POLE_SIGNS" if dz_ok else "NOT_CERTIFIED_BY_POLE_SIGNS",
                        "z_derivative_has_positive_pole": dz_positive,
                        "radial_derivative_poles_match_apex_side": dr_ok,
                        "radial_direction_status": "PROVED_BY_POLE_SIGNS" if dr_ok else "NOT_CERTIFIED_BY_POLE_SIGNS",
                        "span_interior_regular": regular_open,
                        "endpoint_tangents_nonzero": endpoint_regular,
                        "endpoint_regular_status": "PROVED" if endpoint_regular else "FAIL_ZERO_ENDPOINT_TANGENT",
                        "radius_screens": screens})
    joins = []
    for i, (left, right) in enumerate(zip(spans, spans[1:])):
        hl, hr = BREAKS[i + 1] - BREAKS[i], BREAKS[i + 2] - BREAKS[i + 1]
        checks = tuple(_endpoint_jet(left, hl, order, True) == _endpoint_jet(right, hr, order, False)
                       for order in range(5))
        joins.append({"at_u": str(BREAKS[i + 1]), "derivative_orders_0_to_4_equal": list(checks),
                      "exact_C4": all(checks)})
    return {"family": case["family"], "outer_bbox_height_role": "mouth/body datum; lip absent",
            "accepted_candidate_total_height_mm": case["accepted_candidate_total_height_mm"],
            "total_height_check": "NOT_CHECKED_LIP_NOT_CONSTRUCTED",
            "spans": records, "joins": joins, "all_C4": all(row["exact_C4"] for row in joins),
            "all_hulls_proved_in_bbox": all(row["hull_certificate_status"] == "PROVED_BY_CONTROL_HULL" for row in records),
            "all_open_spans_regular_proved": all(row["span_interior_regular"] for row in records),
            "all_span_endpoint_tangents_nonzero": all(row["endpoint_tangents_nonzero"] for row in records),
            "global_wall": "UNKNOWN_NOT_COMPUTED", "inner_profile": "NOT_CONSTRUCTED"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _solve_family(case: Mapping[str, Any], extraction: Sequence[Matrix], hessian: Matrix) -> dict[str, Any]:
    plan = build_case_constraint_rows(case)
    solved = {axis: _solve_coordinate(hessian, plan, axis) for axis in ("r", "z")}
    controls = {axis: solved[axis]["controls"] for axis in ("r", "z")}
    points = tuple((controls["r"][i], controls["z"][i]) for i in range(CONTROL_COUNT))
    spans = tuple(tuple((_dot(row, controls["r"]), _dot(row, controls["z"])) for row in poles) for poles in extraction)
    inequalities = _ineq_results(plan, controls)
    return {"control_points_rz_mm": [[str(r), str(z)] for r, z in points],
            "minimum_jerk_integral": str(solved["r"]["objective"] + solved["z"]["objective"]),
            "coordinate_solve": {axis: {k: (str(v) if isinstance(v, F) else v) for k, v in row.items() if k != "controls"}
                                 | {"control_values": list(map(str, row["controls"]))} for axis, row in solved.items()},
            "all_nine_equalities_exact": all(row["exact_residuals_zero"] for row in solved.values()),
            "strict_linear_inequalities": inequalities,
            "all_strict_linear_inequalities_pass": all(row["strict_status"] == "PASS" for row in inequalities),
            "geometry": _span_checks(case, spans), "candidate_qualification": "NOT_PROMOTED"}


def run_fixed_minimum_jerk_source_plan(*, root_ready: bool = False) -> dict[str, Any]:
    """Future bounded call only after root authorization; refuse overwrite."""
    if root_ready is not True:
        raise PermissionError("ROOT_READY_REQUIRED_FOR_MINIMUM_JERK_KKT")
    if OUTPUT_ROOT.exists():
        raise FileExistsError("FIXED_VF_OUTPUT_PATH_EXISTS_REFUSING_OVERWRITE")
    cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]
    extraction = exact_bezier_extraction()
    hessian = exact_minimum_jerk_hessian(extraction)
    results = {family: _solve_family(cases[family], extraction, hessian) for family in ("bowl", "jar")}
    pins = (Path(__file__).resolve(), HERE / "bspline_constraint_source.py", CASE_FILE)
    receipt = {"schema": "vesselforge.global_bspline_meridian.minimum_jerk_result.v1",
               "status": "EXACT_RATIONAL_MINIMUM_JERK_RESULTS_REQUIRE_REVIEW",
               "objective": "minimize integral ||C'''(u)||^2 du using exact piecewise Bernstein Gram matrix",
               "systems": "four exact Fraction KKT solves: r(16),z(15) per family; full equality-row rank required",
               "solver": "exact Gauss-Jordan; singular KKT fails closed; no ridge/pseudoinverse/float/optimizer",
               "bezier_extraction": "exact Boehm insertion to multiplicity 5; six degree-5 spans",
               "curvature": "P_R=S^3-R^2D^2, degree 24 exact Bernstein coefficients; all spans screened against both targets because base interval is unassigned",
               "source_sha256": {str(path): _sha(path) for path in pins}, "cases": results,
               "limitations": ["No inner profile, lip, normal offset, global reach/wall, CAD, STEP, mesh, or style qualification.",
                               "Mixed-sign Bernstein coefficients are UNKNOWN unless an endpoint value is negative.",
                               "A radius-screen failure is distinct from signed offset singularity 1-3*kappa<=0."]}
    encoded = (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ValueError("SYMBOLIC_OUTPUT_EXCEEDS_8MIB_BUDGET")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    (OUTPUT_ROOT / "minimum_jerk_exact_result.json").write_bytes(encoded)
    return receipt
