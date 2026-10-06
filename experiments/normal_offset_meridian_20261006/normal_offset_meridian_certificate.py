from __future__ import annotations
from decimal import Decimal
from fractions import Fraction
from math import comb, sqrt
from typing import Any, Mapping, Sequence

T_MM = Fraction(3)
DEGREE = 5
MAX_SUBDIVISION_NODES = 64
MAX_SUBDIVISION_DEPTH = 6
SUCCESS_STATUS = "INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE"


def q(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        return Fraction(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return Fraction(value)
    if isinstance(value, str):
        return Fraction(value)
    raise TypeError("exact Bernstein inputs must be decimal/rational strings, Decimal, int, or Fraction")


def qs(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def add(a: Sequence[Fraction], b: Sequence[Fraction]) -> list[Fraction]:
    if len(a) != len(b):
        raise ValueError("Bernstein degrees must match before addition")
    return [x + y for x, y in zip(a, b)]


def scale(a: Sequence[Fraction], s: Fraction) -> list[Fraction]:
    return [s * x for x in a]


def elevate(a: Sequence[Fraction], target_degree: int) -> list[Fraction]:
    out = list(a)
    while len(out) - 1 < target_degree:
        n = len(out) - 1
        out = [out[0]] + [Fraction(i, n + 1) * out[i - 1] + Fraction(n + 1 - i, n + 1) * out[i]
                          for i in range(1, n + 1)] + [out[-1]]
    if len(out) - 1 != target_degree:
        raise ValueError("cannot degree-reduce a Bernstein polynomial")
    return out


def product(a: Sequence[Fraction], b: Sequence[Fraction]) -> list[Fraction]:
    m, n = len(a) - 1, len(b) - 1
    out = []
    for k in range(m + n + 1):
        lo, hi = max(0, k - n), min(m, k)
        out.append(sum((a[i] * b[k - i] * Fraction(comb(m, i) * comb(n, k - i), comb(m + n, k))
                        for i in range(lo, hi + 1)), Fraction(0)))
    return out


def derivative(a: Sequence[Fraction]) -> list[Fraction]:
    n = len(a) - 1
    return [Fraction(n) * (a[i + 1] - a[i]) for i in range(n)] if n else [Fraction(0)]


def split_half(a: Sequence[Fraction]) -> tuple[list[Fraction], list[Fraction]]:
    row, left, right = list(a), [a[0]], [a[-1]]
    while len(row) > 1:
        row = [(row[i] + row[i + 1]) / 2 for i in range(len(row) - 1)]
        left.append(row[0])
        right.append(row[-1])
    return left, list(reversed(right))


def evaluate(a: Sequence[Fraction], u: Fraction) -> Fraction:
    row = list(a)
    while len(row) > 1:
        row = [(1 - u) * row[i] + u * row[i + 1] for i in range(len(row) - 1)]
    return row[0]


class StudyBudget:
    def __init__(self, node_limit: int = MAX_SUBDIVISION_NODES, depth_limit: int = MAX_SUBDIVISION_DEPTH):
        self.node_limit, self.depth_limit, self.nodes = node_limit, depth_limit, 0


def certify_nonnegative(coefficients: Sequence[Fraction], budget: StudyBudget,
                        u0: Fraction = Fraction(0), u1: Fraction = Fraction(1), depth: int = 0) -> dict:
    c = list(coefficients)
    if budget.nodes >= budget.node_limit:
        return {"status": "UNKNOWN_NODE_BUDGET", "interval": [qs(u0), qs(u1)], "depth": depth}
    budget.nodes += 1
    if c[0] < 0:
        return {"status": "EXACT_COUNTEREXAMPLE", "witness_u": qs(u0), "exact_value": qs(c[0])}
    if c[-1] < 0:
        return {"status": "EXACT_COUNTEREXAMPLE", "witness_u": qs(u1), "exact_value": qs(c[-1])}
    if all(x >= 0 for x in c):
        return {"status": "PASS", "leaves": [{"interval": [qs(u0), qs(u1)],
                "degree": len(c) - 1, "coefficients": [qs(x) for x in c]}]}
    if depth >= budget.depth_limit:
        return {"status": "UNKNOWN_DEPTH_LIMIT", "interval": [qs(u0), qs(u1)],
                "depth": depth, "coefficients": [qs(x) for x in c]}
    left, right = split_half(c)
    mid = (u0 + u1) / 2
    a = certify_nonnegative(left, budget, u0, mid, depth + 1)
    if a["status"] == "EXACT_COUNTEREXAMPLE":
        return a
    b = certify_nonnegative(right, budget, mid, u1, depth + 1)
    if b["status"] == "EXACT_COUNTEREXAMPLE":
        return b
    if a["status"] == b["status"] == "PASS":
        return {"status": "PASS", "leaves": a["leaves"] + b["leaves"]}
    return {"status": "UNKNOWN", "left": a, "right": b}


def radius_numerator(r: Sequence[Fraction], zp: Sequence[Fraction]) -> list[Fraction]:
    rp = derivative(r)
    speed2 = add(product(rp, rp), product(zp, zp))
    radial_term = product(product(r, r), speed2)
    axial_term = elevate(scale(product(zp, zp), T_MM * T_MM), len(radial_term) - 1)
    return [x - y for x, y in zip(radial_term, axial_term)]


def exact_controls(span: Mapping[str, Any]) -> tuple[list[Fraction], list[Fraction]]:
    r = [q(x) for x in span["r_bernstein_mm"]]
    z = [q(x) for x in span["z_bernstein_mm"]]
    if len(r) != DEGREE + 1 or len(z) != DEGREE + 1:
        raise ValueError("frozen study contract requires degree-5 Bezier spans")
    return r, z


def strict_from_original_bernstein(c: Sequence[Fraction]) -> bool:
    return all(x >= 0 for x in c) and any(x > 0 for x in c)


def certify_span(span: Mapping[str, Any], budget: StudyBudget,
                 upstream_r9_all_side_spans_pass: bool, upstream_regular_all_spans_pass: bool) -> dict:
    sid, kind = str(span["span_id"]), str(span["kind"])
    r, z = exact_controls(span)
    rp, zp = derivative(r), derivative(z)
    rproof = certify_nonnegative(r, budget)
    zproof = certify_nonnegative(zp, budget)
    qcoefficients = radius_numerator(r, zp)
    if len(qcoefficients) != 19:
        raise ValueError("degree-5 normal-radius numerator must have 19 degree-18 Bernstein coefficients")
    qproof = certify_nonnegative(qcoefficients, budget)
    checks = {"r_nonnegative": rproof, "zprime_nonnegative": zproof, "Q_nonnegative": qproof,
              "regular_tangent_v_positive": "PASS_FROM_PINNED_UPSTREAM" if upstream_regular_all_spans_pass else "UNKNOWN"}
    monotone = zproof["status"] == "PASS" and strict_from_original_bernstein(zp)
    curve_cross = [x - y for x, y in zip(product(rp, derivative(derivative(z))),
                                          product(zp, derivative(derivative(r))))]
    if kind == "side":
        checks["z_strictly_increasing"] = "PASS" if monotone else "UNKNOWN"
        checks["curvature_factor_lower_bound"] = "2/3_FROM_PINNED_R9" if upstream_r9_all_side_spans_pass else "UNKNOWN"
    elif kind == "flat_base":
        base_rp = certify_nonnegative(rp, budget)
        checks["flat_base_zprime_zero"] = "PASS" if all(x == 0 for x in zp) else "UNKNOWN"
        checks["flat_base_rprime_nonnegative"] = base_rp
        checks["flat_base_r_monotone"] = "PASS" if base_rp["status"] == "PASS" and strict_from_original_bernstein(rp) else "UNKNOWN"
        checks["straight_curvature_factor"] = "1" if all(x == 0 for x in curve_cross) else "UNKNOWN"
    elif kind == "straight_neck":
        checks["straight_neck_rprime_zero"] = "PASS" if all(x == 0 for x in rp) else "UNKNOWN"
        checks["straight_neck_z_monotone"] = "PASS" if monotone else "UNKNOWN"
        checks["straight_curvature_factor"] = "1" if all(x == 0 for x in curve_cross) else "UNKNOWN"
    else:
        checks["span_kind"] = "UNKNOWN_UNSUPPORTED_KIND"
    statuses = [v["status"] if isinstance(v, dict) else v for v in checks.values()]
    if "EXACT_COUNTEREXAMPLE" in statuses:
        status = "EXACT_COUNTEREXAMPLE"
    elif all(s == "PASS" or s in ("2/3_FROM_PINNED_R9", "1", "PASS_FROM_PINNED_UPSTREAM") for s in statuses):
        status = "PASS"
    else:
        status = "UNKNOWN"
    return {"span_id": sid, "kind": kind, "degree": DEGREE, "status": status, "checks": checks}


def certify_study(spans: Sequence[Mapping[str, Any]], *, upstream_r9_all_side_spans_pass: bool,
                  upstream_regular_all_spans_pass: bool) -> dict:
    budget, results = StudyBudget(), []
    for span in spans:
        results.append(certify_span(span, budget, upstream_r9_all_side_spans_pass,
                                    upstream_regular_all_spans_pass))
    has_counterexample = any(x["status"] == "EXACT_COUNTEREXAMPLE" for x in results)
    all_pass = bool(results) and all(x["status"] == "PASS" for x in results)
    status = ("EXACT_COUNTEREXAMPLE_NO_CANDIDATE" if has_counterexample else
              SUCCESS_STATUS if all_pass and upstream_r9_all_side_spans_pass else "UNKNOWN_NO_CANDIDATE")
    return {"status": status, "scope": "jar_meridian_2d_curve_only",
            "global_wall_status": "UNKNOWN", "normal_strip_global_injectivity": "UNKNOWN",
            "upstream_r9_all_side_spans_pass": upstream_r9_all_side_spans_pass,
            "upstream_regular_all_spans_pass": upstream_regular_all_spans_pass,
            "nodes_used": budget.nodes, "node_limit": budget.node_limit,
            "depth_limit": budget.depth_limit, "spans": results}


def true_offset_display_25(span: Mapping[str, Any]) -> list[dict]:
    r, z = exact_controls(span)
    rp, zp = derivative(r), derivative(z)
    out = []
    for j in range(25):
        u = Fraction(j, 24)
        rr, zz, dr, dz = evaluate(r, u), evaluate(z, u), evaluate(rp, u), evaluate(zp, u)
        speed2 = dr * dr + dz * dz
        row = {"u": qs(u), "display_only": True}
        if speed2 <= 0:
            row.update({"status": "UNKNOWN_TANGENT", "r_inner_mm": None, "z_inner_mm": None})
        else:
            v = sqrt(float(speed2))
            row.update({"status": "FINITE_TRUE_NORMAL_OFFSET_SAMPLE",
                        "r_inner_mm": float(rr) - float(T_MM) * float(dz) / v,
                        "z_inner_mm": float(zz) + float(T_MM) * float(dr) / v})
        out.append(row)
    return out


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: import pure functions only after a separate root GO; no input adapter or execution is enabled.")
