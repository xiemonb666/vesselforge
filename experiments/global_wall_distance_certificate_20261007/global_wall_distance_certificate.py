"""SOURCE_ONLY exact proof for one pinned meridian curve pair; never run implicitly."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction as F
from math import comb
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CASE_FILE, PINS_FILE = HERE / "case.json", HERE / "source_pins.json"
CASE_SHA256 = "985b12a38a9996372a39afb700ecc413ecbb52c106f0594dc94350674b7c27d8"
PINS_SHA256 = "63be31ab8ea506dc77888ccba0865ddc85ac938cd97e822cd2e5b8006f16d32f"
MAX_INPUT_BYTES, MAX_TOTAL_INPUT_BYTES, MAX_OUTPUT_BYTES = 8_000_000, 24_000_000, 1_000_000
MAX_DISTANCE_DEPTH, MAX_DISTANCE_LEAVES = 8, 64
DEGREE, CONTROL_COUNT = 5, 17
BREAKS = tuple(F(i, 12) for i in range(13))
INTERNAL = BREAKS[1:-1]


class Unknown(Exception):
    pass


class GeometryFailure(Exception):
    pass


def _need(ok: bool, reason: str) -> None:
    if not ok:
        raise Unknown(reason)


def _q(value: Any) -> F:
    return value if isinstance(value, F) else F(str(value))


def _input(path: Path, digest: str, budget: list[int]) -> bytes:
    size = path.stat().st_size
    _need(size <= MAX_INPUT_BYTES and budget[0] + size <= MAX_TOTAL_INPUT_BYTES, "input byte cap")
    raw = path.read_bytes()
    _need(hashlib.sha256(raw).hexdigest() == digest.lower(), "input SHA-256 mismatch: " + str(path))
    budget[0] += size
    return raw


def _insert_once(points: Sequence[tuple[F, F]], knots: Sequence[F], u: F) -> tuple[list[tuple[F, F]], list[F]]:
    n, p = len(points) - 1, DEGREE
    mult = sum(x == u for x in knots)
    k = next((i for i in range(p, n + 1) if knots[i] <= u < knots[i + 1]), -1)
    _need(k >= 0 and mult < p, "invalid pinned knot insertion")
    out: list[tuple[F, F] | None] = [None] * (n + 2)
    for i in range(k - p + 1):
        out[i] = points[i]
    for i in range(k - mult, n + 1):
        out[i + 1] = points[i]
    for i in range(k - p + 1, k - mult + 1):
        den = knots[i + p] - knots[i]
        _need(den > 0, "nonpositive knot insertion denominator")
        a = (u - knots[i]) / den
        out[i] = tuple(a * points[i][j] + (1 - a) * points[i - 1][j] for j in range(2))
    _need(all(row is not None for row in out), "knot insertion left an empty control")
    return [row for row in out if row is not None], list(knots[:k + 1]) + [u] + list(knots[k + 1:])


def _extract_spans(points: Sequence[tuple[F, F]]) -> list[tuple[tuple[F, F], ...]]:
    knots = [F(0)] * 6 + list(INTERNAL) + [F(1)] * 6
    refined = list(points)
    for u in INTERNAL:
        while sum(x == u for x in knots) < DEGREE:
            refined, knots = _insert_once(refined, knots, u)
    _need(len(refined) == 61, "unexpected extracted Bezier control count")
    return [tuple(refined[i * DEGREE:i * DEGREE + DEGREE + 1]) for i in range(12)]


def _poles(a: Sequence[F], h: F = F(1)) -> tuple[F, ...]:
    n = len(a) - 1
    return tuple(F(n) * (a[i + 1] - a[i]) / h for i in range(n))


def _product(a: Sequence[F], b: Sequence[F]) -> tuple[F, ...]:
    m, n = len(a) - 1, len(b) - 1
    return tuple(sum((F(comb(m, i) * comb(n, k - i), comb(m + n, k)) * a[i] * b[k - i]
                      for i in range(max(0, k - n), min(m, k) + 1)), F(0)) for k in range(m + n + 1))


def _elevate(a: Sequence[F], target: int) -> tuple[F, ...]:
    out = tuple(a)
    while len(out) - 1 < target:
        n = len(out) - 1
        out = (out[0],) + tuple(F(i, n + 1) * out[i - 1] + F(n + 1 - i, n + 1) * out[i]
                                for i in range(1, n + 1)) + (out[-1],)
    _need(len(out) - 1 == target, "Bernstein degree reduction forbidden")
    return out


def _r9(span: Sequence[tuple[F, F]]) -> tuple[F, ...]:
    r, z = tuple(p[0] for p in span), tuple(p[1] for p in span)
    rp, zp = _poles(r), _poles(z)
    rpp, zpp = _poles(rp), _poles(zp)
    speed2 = tuple(a + b for a, b in zip(_product(rp, rp), _product(zp, zp)))
    det = tuple(a - b for a, b in zip(_product(rp, zpp), _product(zp, rpp)))
    speed6 = _product(_product(speed2, speed2), speed2)
    det2 = _elevate(_product(det, det), 24)
    return tuple(a - 81 * b for a, b in zip(speed6, det2))


def _signs(a: Sequence[F]) -> str:
    return "".join("+" if x > 0 else "-" if x < 0 else "0" for x in a)


def _jet(span: Sequence[tuple[F, F]], axis: int, h: F, order: int, end: bool) -> F:
    row = tuple(p[axis] for p in span)
    for _ in range(order):
        row = _poles(row, h)
    return row[-1] if end else row[0]


def _split_half(a: Sequence[F]) -> tuple[tuple[F, ...], tuple[F, ...]]:
    rows = [tuple(a)]
    while len(rows[-1]) > 1:
        row = rows[-1]
        rows.append(tuple((row[i] + row[i + 1]) / 2 for i in range(len(row) - 1)))
    return tuple(row[0] for row in rows), tuple(row[-1] for row in reversed(rows))


def _distance_poly(span: Sequence[tuple[F, F]], q: tuple[F, F]) -> tuple[F, ...]:
    dx = tuple(p[0] - q[0] for p in span)
    dz = tuple(p[1] - q[1] for p in span)
    return tuple(a + b - 9 for a, b in zip(_product(dx, dx), _product(dz, dz)))


def _prove_nonnegative(coeff: Sequence[F]) -> tuple[str, int]:
    stack, leaves = [(tuple(coeff), 0)], 0
    while stack:
        if leaves + len(stack) > MAX_DISTANCE_LEAVES:
            return "UNKNOWN", leaves
        row, depth = stack.pop()
        if all(x >= 0 for x in row):
            leaves += 1
            continue
        if all(x < 0 for x in row):
            return "FAIL", leaves
        if depth == MAX_DISTANCE_DEPTH or leaves + len(stack) + 2 > MAX_DISTANCE_LEAVES:
            return "UNKNOWN", leaves
        left, right = _split_half(row)
        stack.extend(((right, depth + 1), (left, depth + 1)))
    return "PASS", leaves


def _load_saved() -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any]]:
    case_raw = CASE_FILE.read_bytes()
    pins_raw = PINS_FILE.read_bytes()
    _need(hashlib.sha256(case_raw).hexdigest() == CASE_SHA256, "case SHA-256 mismatch")
    _need(hashlib.sha256(pins_raw).hexdigest() == PINS_SHA256, "pins SHA-256 mismatch")
    case, pins = json.loads(case_raw.decode()), json.loads(pins_raw.decode())
    _need(set(pins["inputs"]) == {"outer_result", "offset_result", "monostrip_result", "frozen_bspline_driver"}, "unexpected input pin set")
    for name, key in (("outer_result", "outer_sha256"), ("offset_result", "offset_sha256"), ("monostrip_result", "monostrip_sha256")):
        _need(pins["inputs"][name]["sha256"] == case[key], "case/pins mismatch: " + name)
    budget, data = [0], {}
    for name, pin in pins["inputs"].items():
        data[name] = _input(ROOT / pin["path"], pin["sha256"], budget)
    return case, data, pins


def _verify(case: dict[str, Any], data: dict[str, bytes]) -> dict[str, Any]:
    outer = json.loads(data["outer_result"].decode())
    offset = json.loads(data["offset_result"].decode())
    strip = json.loads(data["monostrip_result"].decode())
    _need(outer["status"] == "GEOMETRY_ENGINEERING_CANDIDATE_ONLY", "outer result scope/status mismatch")
    _need(offset["status"] == "INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE" and offset["scope"] == "jar_meridian_2d_only", "offset result scope/status mismatch")
    _need(offset["normal_strip_global_injectivity"] == "UNKNOWN" and offset["global_wall_status"] == "UNKNOWN", "offset source overclaims global geometry")
    _need(strip["status"] == "GLOBAL_MERIDIAN_STRIP_INJECTIVITY_PROVED_CONDITIONAL" and strip["global_minimum_euclidean_wall"] == "UNKNOWN", "retry02 scope/status mismatch")
    _need(strip["scope"] == "pinned actual 2D meridian map F over all 12 spans and 0<=s<=3 mm", "retry02 scope mismatch")
    jar, local = outer["families"]["jar"], outer["families"]["jar"]["exact_geometry_certificate"]
    _need(local["family"] == "jar" and local["all_spans_regular_proved"] and local["all_C4"] and local["all_hulls_proved"] and local["all_features_exact"] and local["straight_meridian_exclusions_proved"], "pinned outer proof flags missing")
    _need(local["global_normal_wall"] == "UNKNOWN_NOT_COMPUTED" and local["inner_profile"] == "NOT_CONSTRUCTED", "outer scope mismatch")
    prior_pins = strip["input_pins"]
    _need(prior_pins["outer_result"] == case["outer_sha256"] and prior_pins["offset_result"] == case["offset_sha256"], "retry02 does not bind pinned controls/results")
    _need(strip["case_sha256"] == case["monostrip_case_sha256"], "retry02 case hash mismatch")
    _need(len(local["spans"]) == len(offset["spans"]) == 12 and len(local["joins"]) == 11, "span/join count mismatch")
    points = [tuple(_q(x) for x in row) for row in jar["control_points_rz_mm"]]
    _need(len(points) == CONTROL_COUNT and all(len(row) == 2 for row in points), "actual B-spline controls malformed")
    spans = _extract_spans(points)
    kinds = case["span_kinds"]
    signs_expected = case["derivative_signs"]
    records, r9_rows = [], []
    for i, span in enumerate(spans):
        h = BREAKS[i + 1] - BREAKS[i]
        local_controls = tuple(tuple(_q(x) for x in p) for p in offset["spans"][i]["exact_bezier_controls_rz_mm"])
        _need(span == local_controls, "B-spline controls do not reconstruct pinned offset span")
        _need(offset["spans"][i]["span_index"] == i and offset["spans"][i]["kind"] == kinds[i], "local span identity mismatch")
        rp, zp = _poles(tuple(p[0] for p in span)), _poles(tuple(p[1] for p in span))
        rs, zs = _signs(rp), _signs(zp)
        _need((rs, zs) == (signs_expected["rprime"][i], signs_expected["zprime"][i]), "actual derivative sign table mismatch")
        _need(local["spans"][i]["span"] == i and local["spans"][i]["u"] == [str(BREAKS[i]), str(BREAKS[i + 1])], "outer span interval mismatch")
        if i == 0:
            _need(all(x == 0 for x in zp) and all(x > 0 for x in rp), "flat-base premise failed")
        else:
            _need(all(x >= 0 for x in zp) and any(x > 0 for x in zp), "side/neck z is not strictly increasing on open span")
        _need(all(any(_jet(span, ax, h, 1, end) != 0 for ax in (0, 1)) for end in (False, True)), "zero endpoint tangent")
        if kinds[i] == "side":
            _need(local["spans"][i]["radius_9mm_status"] == "PROVED_R9_ON_CLOSED_NONFLAT_SPAN", "side R9 status missing")
            p_global = tuple(_q(x) for x in local["spans"][i]["P_R_degree24_coefficients"])
            actual = _r9(span)
            _need(len(p_global) == len(actual) == 25 and all(x >= 0 for x in actual), "exact R9 coefficient proof failed")
            _need(actual == tuple(h ** 6 * x for x in p_global), "actual controls do not bind outer R9 polynomial")
            r9_rows.append(i)
        elif kinds[i] == "flat_base":
            _need(local["spans"][i]["semantic_base_flat"] is True, "flat-base metadata missing")
        else:
            _need(all(p[0] == F(26) for p in span) and local["spans"][i]["semantic_neck_cylindrical"] is True, "straight neck proof failed")
        records.append({"span": i, "kind": kinds[i], "rprime": rs, "zprime": zs})
    _need(r9_rows == list(range(1, 11)), "expected ten side R9 spans")
    for i, join in enumerate(local["joins"]):
        h0 = BREAKS[i + 1] - BREAKS[i]
        h1 = BREAKS[i + 2] - BREAKS[i + 1]
        _need(join["exact_C4"] and len(join["derivative_orders_0_to_4_equal"]) == 5 and all(join["derivative_orders_0_to_4_equal"]), "saved C4 join flag failed")
        _need(_q(join["u"]) == BREAKS[i + 1], "join parameter mismatch")
        for k in range(5):
            _need(all(_jet(spans[i], ax, h0, k, True) == _jet(spans[i + 1], ax, h1, k, False) for ax in (0, 1)), "actual global-u C4 jet mismatch")
    ep = case["endpoints_mm"]
    _need(spans[0][0] == (_q(ep["axis_r"]), _q(ep["base_z"])) and spans[0][-1] == spans[1][0] == (_q(ep["base_seam_r"]), _q(ep["base_z"])), "axis/base endpoints mismatch")
    _need(spans[5][-1] == spans[6][0] == (_q(ep["apex_r"]), _q(ep["apex_z"])), "apex endpoint mismatch")
    _need(spans[10][-1] == spans[11][0] == (_q(ep["neck_r"]), _q(ep["neck_z"])) and spans[11][-1] == (_q(ep["mouth_r"]), _q(ep["mouth_z"])), "neck/mouth endpoints mismatch")
    depth, extended_depth = _q(case["depth_mm"]), _q(case["extended_depth_mm"])
    _need(_q(ep["mouth_z"]) - _q(ep["base_z"]) > extended_depth and depth == 3 and extended_depth == 6, "depth-range premise failed")
    _need(strip["span_signs"] == records, "retry02 derivative evidence differs from reconstructed controls")
    fibers = strip["endpoint_fibers"]
    _need(fibers["axis"] == ["(0,0)", "(0,3)"] and fibers["base_side_seam"] == ["(18,0)", "(18,3)"] and fibers["mouth"] == ["(26,120)", "(23,120)"], "retry02 endpoint fibers mismatch")
    axis_q = (F(0), _q(ep["base_z"]) + depth)
    mouth_q = (_q(ep["mouth_r"]) - depth, _q(ep["mouth_z"]))
    endpoint_rows = {"axis": [], "mouth": []}
    for i, span in enumerate(spans):
        for label, q in (("axis", axis_q), ("mouth", mouth_q)):
            status, leaves = _prove_nonnegative(_distance_poly(span, q))
            if status == "FAIL":
                raise GeometryFailure(label + " endpoint is less than 3 mm from outer span " + str(i))
            _need(status == "PASS", label + " endpoint distance unresolved on span " + str(i))
            endpoint_rows[label].append({"span": i, "status": status, "leaves": leaves})
    _need(spans[0][0] == (F(0), F(0)) and spans[11][-1] == (F(26), F(120)), "endpoint equality binding failed")
    return {
        "status": "MERIDIAN_CURVE_PAIR_MINIMUM_EXACTLY_3_MM",
        "scope": "min over outer meridian c(u) and inner meridian F(v,3), pinned jar, exact 2D model only",
        "control_reconstruction": "PASS_EXACT_BOEHM_EXTRACTION_AND_OFFSET_SPAN_BINDING",
        "curvature": {"side_R9_spans": r9_rows, "lambda_lower_bound_for_0_to_6_mm": "1/3", "side_radius_lower_bound_at_depth6_mm": "12", "neck_radius_lower_bound_at_depth6_mm": "20"},
        "extended_meridian_strip": {"status": "PASS_INJECTIVE_0_TO_6_MM", "basis": "strict fixed-height z branch on side/neck; dR/ds=-v/zprime<0; flat base and joins handled separately"},
        "endpoint_minima_mm": {"axis_to_outer_curve": "EXACTLY_3", "mouth_to_outer_curve": "EXACTLY_3", "distance_certificates": endpoint_rows},
        "curve_pair_minimum_mm": "EXACTLY_3",
        "revolution_transfer": "PASS: squared distance adds 2*r*rho*(1-cos(delta_theta))>=0; equal azimuth attains meridian distance, including zero-radius axis points",
        "axis_topology": "axis quotient does not change set distance; CAD cap/vertex topology not checked",
        "actual_CAD_lip": "UNKNOWN", "native_B_rep": "UNKNOWN", "production_wall_qualification": "UNKNOWN"
    }


def run_saved_certificate(*, root_ready: bool = False) -> dict[str, Any]:
    if not root_ready:
        raise PermissionError("SOURCE_ONLY: separate root GO required before reading saved inputs")
    try:
        case, data, pins = _load_saved()
        result = _verify(case, data)
        result["input_pins"] = {name: pin["sha256"] for name, pin in pins["inputs"].items()}
        result["case_sha256"], result["pins_sha256"] = CASE_SHA256, PINS_SHA256
        raw = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        _need(len(raw) <= MAX_OUTPUT_BYTES, "output byte cap")
        return result
    except GeometryFailure as exc:
        return {"status": "FAIL_ENDPOINT_CLEARANCE", "reason": str(exc), "production_wall_qualification": "UNKNOWN"}
    except (Unknown, OSError, ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
        return {"status": "UNKNOWN", "reason": str(exc), "curve_pair_minimum_mm": "UNKNOWN", "production_wall_qualification": "UNKNOWN"}


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: do not execute without separate root GO")
