"""Inert exact degree-5 semantic base/neck B-spline candidate builder."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction as F
from math import comb
from pathlib import Path
from typing import Any, Mapping, Sequence

DEGREE = 5
CONTROL_COUNT = 17
INTERNAL_KNOTS = tuple(F(k, 12) for k in range(1, 12))
KNOT_VECTOR = (F(0),) * 6 + INTERNAL_KNOTS + (F(1),) * 6
BREAKS = (F(0), *INTERNAL_KNOTS, F(1))
HERE = Path(__file__).resolve().parent
CASE_FILE = HERE / "fixed_cases.json"
OUTPUT_ROOT = HERE.parents[1] / "tmp" / "review_20261006" / "semantic_base_neck_bspline_20261006" / "minimum_jerk_candidate"
MAX_JSON_BYTES = 8 * 1024 * 1024
Vector = tuple[F, ...]
Matrix = tuple[tuple[F, ...], ...]
Point = tuple[F, F]
Span = tuple[Point, ...]


def _basis(i: int, degree: int, u: F) -> F:
    if u == 1:
        return F(i == len(KNOT_VECTOR) - degree - 2)
    if degree == 0:
        return F(KNOT_VECTOR[i] <= u < KNOT_VECTOR[i + 1])
    left_den = KNOT_VECTOR[i + degree] - KNOT_VECTOR[i]
    right_den = KNOT_VECTOR[i + degree + 1] - KNOT_VECTOR[i + 1]
    left = ((u - KNOT_VECTOR[i]) / left_den * _basis(i, degree - 1, u)) if left_den else F(0)
    right = ((KNOT_VECTOR[i + degree + 1] - u) / right_den * _basis(i + 1, degree - 1, u)) if right_den else F(0)
    return left + right

def _basis_derivative(i: int, degree: int, order: int, u: F) -> F:
    if order == 0:
        return _basis(i, degree, u)
    if order > degree:
        return F(0)
    left_den = KNOT_VECTOR[i + degree] - KNOT_VECTOR[i]
    right_den = KNOT_VECTOR[i + degree + 1] - KNOT_VECTOR[i + 1]
    left = (F(degree) / left_den * _basis_derivative(i, degree - 1, order - 1, u)) if left_den else F(0)
    right = (F(degree) / right_den * _basis_derivative(i + 1, degree - 1, order - 1, u)) if right_den else F(0)
    return left - right
def basis_row(u: F, order: int = 0) -> Vector:
    if not 0 <= u <= 1 or order not in range(DEGREE + 1):
        raise ValueError("PARAMETER_OR_DERIVATIVE_ORDER_OUT_OF_RANGE")
    if order and u in {F(0), F(1)}:
        raise ValueError("USE_CLAMPED_POLE_DIFFERENCES_AT_ENDPOINTS")
    fn = _basis if order == 0 else _basis_derivative
    return tuple(fn(i, DEGREE, u) if order == 0 else fn(i, DEGREE, order, u) for i in range(CONTROL_COUNT))

def exact_case_rows(case: Mapping[str, Any], coordinate: str) -> tuple[tuple[str, Vector, F], ...]:
    return tuple((row["name"], basis_row(F(row["u"]), int(row["order"])), F(row["rhs"]))
                 for row in case["linear_equalities"] if row["coordinate"] == coordinate)

def _blend(a: Vector, b: Vector, t: F) -> Vector:
    return tuple(t * x + (1 - t) * y for x, y in zip(a, b, strict=True))

def _find_span(knots: Sequence[F], degree: int, n: int, u: F) -> int:
    for k in range(degree, n + 1):
        if knots[k] <= u < knots[k + 1]:
            return k
    raise ValueError("KNOT_INSERTION_PARAMETER_HAS_NO_SPAN")

def boehm_insert_once(controls: Sequence[Vector], knots: Sequence[F], degree: int, u: F) -> tuple[tuple[Vector, ...], tuple[F, ...]]:
    n = len(controls) - 1
    multiplicity = sum(knot == u for knot in knots)
    if multiplicity >= degree:
        raise ValueError("KNOT_ALREADY_HAS_BEZIER_MULTIPLICITY")
    k = _find_span(knots, degree, n, u)
    out: list[Vector | None] = [None] * (n + 2)
    for i in range(k - degree + 1):
        out[i] = controls[i]
    for i in range(k - multiplicity, n + 1):
        out[i + 1] = controls[i]
    for i in range(k - degree + 1, k - multiplicity + 1):
        den = knots[i + degree] - knots[i]
        if den <= 0:
            raise ValueError("NONPOSITIVE_BOEHM_DENOMINATOR")
        out[i] = _blend(controls[i], controls[i - 1], (u - knots[i]) / den)
    if any(row is None for row in out):
        raise ValueError("BOEHM_INSERTION_LEFT_UNFILLED_CONTROL")
    return tuple(row for row in out if row is not None), tuple(knots[:k + 1]) + (u,) + tuple(knots[k + 1:])

def exact_bezier_extraction() -> tuple[Matrix, ...]:
    controls: tuple[Vector, ...] = tuple(tuple(F(i == j) for j in range(CONTROL_COUNT)) for i in range(CONTROL_COUNT))
    knots = KNOT_VECTOR
    for u in INTERNAL_KNOTS:
        while sum(value == u for value in knots) < DEGREE:
            controls, knots = boehm_insert_once(controls, knots, DEGREE, u)
    if len(controls) != 1 + (len(BREAKS) - 1) * DEGREE:
        raise ValueError("UNEXPECTED_BEZIER_EXTRACTION_CONTROL_COUNT")
    return tuple(tuple(controls[i * DEGREE:i * DEGREE + DEGREE + 1]) for i in range(len(BREAKS) - 1))

def _bernstein_product(a: Sequence[F], b: Sequence[F]) -> tuple[F, ...]:
    m, n = len(a) - 1, len(b) - 1
    return tuple(sum((F(comb(m, i) * comb(n, k - i), comb(m + n, k)) * a[i] * b[k - i]
                      for i in range(max(0, k - n), min(m, k) + 1)), F(0)) for k in range(m + n + 1))

def _bernstein_sum(a: Sequence[F], b: Sequence[F]) -> tuple[F, ...]:
    if len(a) != len(b):
        raise ValueError("BERNSTEIN_DEGREE_MISMATCH")
    return tuple(x + y for x, y in zip(a, b, strict=True))


def _elevate(a: Sequence[F], degree: int) -> tuple[F, ...]:
    out = tuple(a)
    while len(out) - 1 < degree:
        p = len(out) - 1
        out = tuple((F(i, p + 1) * out[i - 1] if i else F(0)) +
                    (F(p + 1 - i, p + 1) * out[i] if i <= p else F(0)) for i in range(p + 2))
    if len(out) - 1 != degree:
        raise ValueError("BERNSTEIN_ELEVATION_TARGET_TOO_SMALL")
    return out


def minimum_jerk_hessian(extraction: Sequence[Matrix]) -> Matrix:
    p, n = DEGREE, CONTROL_COUNT
    hessian = [[F(0) for _ in range(n)] for _ in range(n)]
    differences = tuple(tuple(F(-1 if j == i else 3 if j == i + 1 else -3 if j == i + 2 else 1 if j == i + 3 else 0)
                              for j in range(p + 1)) for i in range(p - 2))
    gram = tuple(tuple(F(comb(2, i) * comb(2, j), 5 * comb(4, i + j)) for j in range(3)) for i in range(3))
    for s, poles in enumerate(extraction):
        h = BREAKS[s + 1] - BREAKS[s]
        scale = F((p * (p - 1) * (p - 2)) ** 2) / h ** 5
        rows = tuple(tuple(sum((d[a] * poles[a][q] for a in range(p + 1)), F(0)) for q in range(n)) for d in differences)
        for i in range(n):
            for j in range(n):
                hessian[i][j] += scale * sum((gram[a][b] * rows[a][i] * rows[b][j]
                                                for a in range(3) for b in range(3)), F(0))
    return tuple(tuple(row) for row in hessian)


def _rank(rows: Sequence[Sequence[F]]) -> int:
    a = [list(row) for row in rows]
    if not a:
        return 0
    r = 0
    for c in range(len(a[0])):
        pivot = next((i for i in range(r, len(a)) if a[i][c]), None)
        if pivot is None:
            continue
        a[r], a[pivot] = a[pivot], a[r]
        v = a[r][c]
        a[r] = [x / v for x in a[r]]
        for i in range(r + 1, len(a)):
            if a[i][c]:
                q = a[i][c]
                a[i] = [x - q * y for x, y in zip(a[i], a[r], strict=True)]
        r += 1
        if r == len(a):
            break
    return r


def solve_fraction_square(matrix: Sequence[Sequence[F]], rhs: Sequence[F]) -> tuple[F, ...]:
    n = len(matrix)
    if not n or len(rhs) != n or any(len(row) != n for row in matrix):
        raise ValueError("FRACTION_SYSTEM_MUST_BE_NONEMPTY_AND_SQUARE")
    a = [list(row) + [value] for row, value in zip(matrix, rhs, strict=True)]
    for c in range(n):
        pivot = next((i for i in range(c, n) if a[i][c]), None)
        if pivot is None:
            raise ValueError("SINGULAR_KKT_NO_RIDGE_OR_PSEUDOINVERSE")
        a[c], a[pivot] = a[pivot], a[c]
        v = a[c][c]
        a[c] = [x / v for x in a[c]]
        for i in range(n):
            if i != c and a[i][c]:
                q = a[i][c]
                a[i] = [x - q * y for x, y in zip(a[i], a[c], strict=True)]
    return tuple(a[i][-1] for i in range(n))


def affine_minimum_jerk_kkt(hessian: Matrix, case: Mapping[str, Any], coordinate: str) -> tuple[Matrix, tuple[F, ...], tuple[int, ...], dict[int, F]]:
    fixed = {int(i): F(value) for i, value in case["fixed_poles"][coordinate].items()}
    free = tuple(i for i in range(CONTROL_COUNT) if i not in fixed)
    if set(free) | set(fixed) != set(range(CONTROL_COUNT)):
        raise ValueError("FIXED_FREE_PARTITION_INVALID")
    equations = exact_case_rows(case, coordinate)
    a_full = tuple(row for _, row, _ in equations)
    rhs_full = tuple(rhs for _, _, rhs in equations)
    a = tuple(tuple(row[i] for i in free) for row in a_full)
    m, n = len(a), len(free)
    expected_free = 10 if coordinate == "r" else 11 if coordinate == "z" else -1
    if n != expected_free or m != 3:
        raise ValueError("SEMANTIC_AFFINE_SYSTEM_DIMENSION_MISMATCH")
    if _rank(a) != m:
        raise ValueError("AFFINE_EQUALITY_ROWS_RANK_DEFICIENT")
    b = tuple(target - sum((row[i] * value for i, value in fixed.items()), F(0))
              for row, target in zip(a_full, rhs_full, strict=True))
    g = tuple(2 * sum((hessian[i][j] * value for j, value in fixed.items()), F(0)) for i in free)
    kkt = [[F(0) for _ in range(n + m)] for _ in range(n + m)]
    for i, gi in enumerate(free):
        for j, gj in enumerate(free):
            kkt[i][j] = 2 * hessian[gi][gj]
    for q, row in enumerate(a):
        for i, value in enumerate(row):
            kkt[i][n + q] = kkt[n + q][i] = value
    return tuple(tuple(row) for row in kkt), tuple(-v for v in g) + b, free, fixed


def solve_affine_coordinate(hessian: Matrix, case: Mapping[str, Any], coordinate: str) -> tuple[Vector, dict[str, Any]]:
    kkt, rhs, free, fixed = affine_minimum_jerk_kkt(hessian, case, coordinate)
    a_free = tuple(tuple(row[i] for i in free) for _, row, _ in exact_case_rows(case, coordinate))
    row_rank = _rank(a_free)
    solution = solve_fraction_square(kkt, rhs)
    controls = [F(0)] * CONTROL_COUNT
    for i, value in fixed.items():
        controls[i] = value
    for i, value in zip(free, solution[:len(free)], strict=True):
        controls[i] = value
    controls = tuple(controls)
    residuals = tuple(sum((row[i] * controls[i] for i in range(CONTROL_COUNT)), F(0)) - target
                      for _, row, target in exact_case_rows(case, coordinate))
    kkt_residuals = tuple(sum((a * b for a, b in zip(row, solution, strict=True)), F(0)) - target
                          for row, target in zip(kkt, rhs, strict=True))
    if any(residuals) or any(kkt_residuals):
        raise ValueError("EXACT_AFFINE_KKT_RESIDUAL_NONZERO")
    return controls, {"free_count": len(free), "equality_count": len(kkt) - len(free),
                      "equality_row_rank": row_rank, "kkt_dimension": len(kkt),
                      "equality_residuals_zero": True, "kkt_residuals_zero": True,
                      "kkt_matrix_rhs_sha256": _matrix_hash(kkt, rhs),
                      "multipliers": tuple(map(str, solution[len(free):]))}


def _dot(a: Sequence[F], b: Sequence[F]) -> F:
    return sum((x * y for x, y in zip(a, b, strict=True)), F(0))


def _matrix_hash(matrix: Sequence[Sequence[F]], rhs: Sequence[F]) -> str:
    text = "\n".join(",".join(map(str, row)) for row in matrix) + "\n|" + ",".join(map(str, rhs))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _derivative_poles(span: Span, h: F, order: int) -> tuple[Point, ...]:
    values = tuple(span)
    for _ in range(order):
        degree = len(values) - 1
        values = tuple(tuple(F(degree) * (values[i + 1][axis] - values[i][axis]) / h for axis in range(2))
                        for i in range(degree))
    return values


def _endpoint_jet(span: Span, h: F, order: int, end: bool) -> Point:
    values = _derivative_poles(span, h, order)
    return values[-1] if end else values[0]


def radius_polynomial(span: Span, h: F, radius: F) -> tuple[F, ...]:
    d1, d2 = _derivative_poles(span, h, 1), _derivative_poles(span, h, 2)
    r1, z1 = tuple(v[0] for v in d1), tuple(v[1] for v in d1)
    r2, z2 = tuple(v[0] for v in d2), tuple(v[1] for v in d2)
    speed2 = _bernstein_sum(_bernstein_product(r1, r1), _bernstein_product(z1, z1))
    left, right = _bernstein_product(r1, z2), _bernstein_product(z1, r2)
    det = tuple(a - b for a, b in zip(left, right, strict=True))
    speed6 = _bernstein_product(_bernstein_product(speed2, speed2), speed2)
    det2 = _elevate(_bernstein_product(det, det), 24)
    return tuple(a - radius * radius * b for a, b in zip(speed6, det2, strict=True))


def _controls_to_spans(extraction: Sequence[Matrix], controls: Sequence[Point]) -> tuple[Span, ...]:
    r, z = tuple(p[0] for p in controls), tuple(p[1] for p in controls)
    return tuple(tuple((_dot(row, r), _dot(row, z)) for row in span) for span in extraction)


def _strict_point_checks(case: Mapping[str, Any], controls: Sequence[Point], spans: Sequence[Span]) -> list[dict[str, str]]:
    apex_u = F(case["apex"]["u"])
    apex_d1 = basis_row(apex_u, 1)
    apex = tuple(sum((apex_d1[i] * controls[i][axis] for i in range(CONTROL_COUNT)), F(0)) for axis in range(2))
    apex2r = sum((basis_row(apex_u, 2)[i] * controls[i][0] for i in range(CONTROL_COUNT)), F(0))
    first = _derivative_poles(spans[0], BREAKS[1] - BREAKS[0], 1)[0]
    last = _derivative_poles(spans[-1], BREAKS[-1] - BREAKS[-2], 1)[-1]
    rows = (("axis_radial_tangent_positive", first[0], ">", F(0)),
            ("apex_vertical_tangent_positive", apex[1], ">", F(0)),
            ("apex_strict_radial_maximum", apex2r, "<", F(0)),
            ("mouth_vertical_tangent_positive", last[1], ">", F(0)))
    return [{"name": name, "value": str(value), "relation": relation,
             "status": "PASS" if (value > target if relation == ">" else value < target) else "FAIL"}
            for name, value, relation, target in rows]


def certify_controls(case: Mapping[str, Any], controls: Sequence[Point], extraction: Sequence[Matrix]) -> dict[str, Any]:
    spans = _controls_to_spans(extraction, controls)
    feature_rows = []
    for feature in case["features"]:
        row = basis_row(F(feature["u"]))
        value = tuple(_dot(row, tuple(point[axis] for point in controls)) for axis in range(2))
        expected = tuple(F(v) for v in feature["rz_mm"])
        feature_rows.append({"name": feature["name"], "exact": value == expected,
                             "value_rz_mm": tuple(map(str, value)), "expected_rz_mm": tuple(map(str, expected))})
    apex_span = BREAKS.index(F(case["apex"]["u"]))
    max_r, mouth_z = F(case["max_outer_radius_mm"]), F(case["mouth_z_mm"])
    target_spans = set(case["curvature_screen_span_indices_zero_based"])
    records = []
    for i, span in enumerate(spans):
        h = BREAKS[i + 1] - BREAKS[i]
        d1 = _derivative_poles(span, h, 1)
        hull = all(0 <= r <= max_r and 0 <= z <= mouth_z for r, z in span)
        z_nonnegative, z_positive = all(v[1] >= 0 for v in d1), any(v[1] > 0 for v in d1)
        r_direction = all(v[0] >= 0 for v in d1) if i < apex_span else all(v[0] <= 0 for v in d1)
        endpoint_regular = d1[0] != (F(0), F(0)) and d1[-1] != (F(0), F(0))
        base_flat = all(point[1] == 0 for point in span)
        neck_cylindrical = all(point[0] == F(case["mouth_r_mm"]) for point in span)
        regular_interior = (all(v[0] >= 0 for v in d1) and any(v[0] > 0 for v in d1)) if i == 0 else (
            all(v[1] >= 0 for v in d1) and any(v[1] > 0 for v in d1))
        screen = "EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK"
        coefficients = ()
        if i in target_spans:
            coefficients = radius_polynomial(span, h, F(9))
            if coefficients[0] < 0 or coefficients[-1] < 0:
                screen = "POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT"
            elif all(v >= 0 for v in coefficients) and regular_interior and endpoint_regular:
                screen = "PROVED_R9_ON_CLOSED_NONFLAT_SPAN"
            else:
                screen = "UNKNOWN_NOT_CERTIFIED"
        elif i == 0 and not base_flat:
            screen = "NOT_EXCLUDED_BASE_FLATNESS_NOT_PROVED"
        elif i == len(spans) - 1 and not neck_cylindrical:
            screen = "NOT_EXCLUDED_NECK_CYLINDER_NOT_PROVED"
        records.append({"span": i, "u": (str(BREAKS[i]), str(BREAKS[i + 1])),
                        "hull_poles_within_bbox": hull,
                        "hull_status": "PROVED_BY_CONVEX_HULL" if hull else "NOT_CERTIFIED_BY_HULL",
                        "z_derivative_poles_nonnegative": z_nonnegative,
                        "z_monotonicity_status": "PROVED_BY_POLE_SIGNS" if z_nonnegative else "NOT_CERTIFIED_BY_POLE_SIGNS",
                        "radial_direction_poles_match_apex": r_direction,
                        "radial_direction_status": "PROVED_BY_POLE_SIGNS" if r_direction else "NOT_CERTIFIED_BY_POLE_SIGNS",
                        "semantic_base_flat": base_flat, "semantic_neck_cylindrical": neck_cylindrical,
                        "open_span_regular": regular_interior,
                        "endpoint_tangents_nonzero": endpoint_regular,
                        "radius_9mm_status": screen,
                        "P_R_degree24_coefficients": tuple(map(str, coefficients))})
    joins = []
    for i, (left, right) in enumerate(zip(spans, spans[1:])):
        hl, hr = BREAKS[i + 1] - BREAKS[i], BREAKS[i + 2] - BREAKS[i + 1]
        matches = tuple(_endpoint_jet(left, hl, q, True) == _endpoint_jet(right, hr, q, False) for q in range(5))
        joins.append({"u": str(BREAKS[i + 1]), "derivative_orders_0_to_4_equal": matches, "exact_C4": all(matches)})
    inequalities = _strict_point_checks(case, controls, spans)
    return {"family": case["family"], "feature_checks": feature_rows,
            "all_features_exact": all(row["exact"] for row in feature_rows),
            "strict_point_checks": inequalities,
            "all_strict_point_checks_pass": all(row["status"] == "PASS" for row in inequalities),
            "joins": joins, "all_C4": all(row["exact_C4"] for row in joins), "spans": records,
            "straight_meridian_exclusions_proved": records[0]["semantic_base_flat"] and records[-1]["semantic_neck_cylindrical"],
            "curvature_scope": "meridian_curve_only; no claim about circumferential surface curvature",
            "all_hulls_proved": all(row["hull_poles_within_bbox"] for row in records),
            "all_spans_regular_proved": all(row["open_span_regular"] and row["endpoint_tangents_nonzero"] for row in records),
            "global_normal_wall": "UNKNOWN_NOT_COMPUTED", "inner_profile": "NOT_CONSTRUCTED"}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, F):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(x) for x in value]
    if isinstance(value, list):
        return [_jsonable(x) for x in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def run_fixed_candidates(*, root_ready: bool = False) -> dict[str, Any]:
    """Future one-shot exact call; do not invoke before explicit root READY."""
    if root_ready is not True:
        raise PermissionError("ROOT_READY_REQUIRED_FOR_SEMANTIC_BSPLINE_SOLVE")
    if OUTPUT_ROOT.exists():
        raise FileExistsError("OUTPUT_EXISTS_REFUSING_OVERWRITE")
    cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]
    extraction = exact_bezier_extraction()
    hessian = minimum_jerk_hessian(extraction)
    results = {}
    for family, case in cases.items():
        r, rsolve = solve_affine_coordinate(hessian, case, "r")
        z, zsolve = solve_affine_coordinate(hessian, case, "z")
        controls = tuple((r[i], z[i]) for i in range(CONTROL_COUNT))
        results[family] = {"control_points_rz_mm": controls,
                           "minimum_jerk_integral": sum((controls[i][a] * hessian[i][j] * controls[j][a]
                                                          for a in range(2) for i in range(CONTROL_COUNT)
                                                          for j in range(CONTROL_COUNT)), F(0)),
                           "affine_kkt": {"r": rsolve, "z": zsolve},
                           "geometry": certify_controls(case, controls, extraction)}
    receipt = {"status": "EXACT_CANDIDATE_REQUIRES_GEOMETRY_REVIEW",
               "objective": "integral ||C'''(u)||^2 du with exact Bernstein Gram matrix",
               "systems": "r 13x13 and z 14x14 per family; four Fraction KKT solves total",
               "source_sha256": {str(Path(__file__).resolve()): _hash(Path(__file__).resolve()), str(CASE_FILE): _hash(CASE_FILE)},
               "cases": results, "wall_and_material": "UNKNOWN_NOT_COMPUTED"}
    encoded = (json.dumps(_jsonable(receipt), indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError("EXACT_OUTPUT_EXCEEDS_8MIB")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    (OUTPUT_ROOT / "semantic_minimum_jerk_result.json").write_bytes(encoded)
    return receipt
