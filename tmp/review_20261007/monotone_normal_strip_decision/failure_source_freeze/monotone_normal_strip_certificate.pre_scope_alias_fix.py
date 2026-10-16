"""Source-only exact verifier for a pinned jar normal-strip monotonicity proof."""
from __future__ import annotations

import hashlib
import json
import time
from fractions import Fraction
from math import comb
from pathlib import Path
from typing import Any

CASE_SHA256 = "9e7b9e7945a14b3dd45517c75a672607cf0923cdac5c723ab614fa0162fc127b"
MAX_SECONDS = 13.0
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_RUN_STARTED = False
INPUT_PINS = {
    "offset_result": ("vesselforge/tmp/review_20261006/normal_offset_meridian_20261006/retry01_after_zprime_fix/normal_offset_meridian_result.json", "96ea35c44d40d12acc4b57a932ebb5194dbccdfd516b1fc2338ec58c51a9956a"),
    "outer_result": ("vesselforge/tmp/review_20261006/curvature_constrained_meridian_20261006/curvature_constrained_meridian_result.json", "839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185"),
    "independent_audit": ("vesselforge/tmp/review_20261006/curvature_constrained_saved_independent/independent_audit.json", "fe0c7c0f1af9fda79d2f94b607b58629bf1e04317a3bd22b290ea92340bbdc0b"),
    "independent_stdout": ("vesselforge/tmp/review_20261006/normal_offset_saved_independent/once_capture_01/stdout.bin", "440f079df68473e5ec109e38912914e2295ebdd826b66a2e0a1d5d35a0549bd7"),
    "offset_receipt": ("vesselforge/tmp/review_20261006/normal_offset_meridian_20261006/retry01_after_zprime_fix/normal_offset_meridian_run_receipt.json", "768c771d1b4a4feea3d8290d63c003afa0d44435175d4b86f1277b9297fa029d"),
    "frozen_driver": ("vesselforge/experiments/semantic_base_neck_bspline_20261006/semantic_base_neck_driver.py", "038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3"),
    "normal_kernel": ("vesselforge/experiments/normal_offset_meridian_20261006/normal_offset_meridian_certificate.py", "48ee9fbc2c69ba97dbeb3f34de298a60571786aaf3359cc784b79d2fbfaa6114"),
    "constrained_source": ("vesselforge/experiments/curvature_constrained_meridian_20261006/curvature_constrained_meridian.py", "96875bb6592a6fd57ceef4dc326c35faeb3f96de16607faa816c7d3fed1e08ce"),
    "design_cases": ("vesselforge/experiments/curvature_constrained_meridian_20261006/design_cases.json", "d1bb74bfc90de5937884854fd4e5e62c4dbf01f33e2f1f7be5dbf931ee35c8eb"),
    "fixed_cases": ("vesselforge/experiments/semantic_base_neck_bspline_20261006/fixed_cases.json", "4e18dbeaecbf13a54a87b3f1409e1c0f7fe54c3606122a01880689d9e3a6a83c"),
}


class Unknown(Exception):
    """A missing or unproved premise; never interpreted as geometry failure."""


def _need(condition: bool, reason: str) -> None:
    if not condition:
        raise Unknown(reason)


def _q(value: Any) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(str(value))


def _sign(value: Fraction) -> str:
    return "+" if value > 0 else "-" if value < 0 else "0"


def _poles(values: list[Fraction]) -> list[Fraction]:
    degree = len(values) - 1
    return [Fraction(degree) * (values[i + 1] - values[i]) for i in range(degree)]


def _bprod(a: list[Fraction], b: list[Fraction]) -> list[Fraction]:
    m, n = len(a) - 1, len(b) - 1
    return [sum((a[i] * b[k - i] * Fraction(comb(m, i) * comb(n, k - i), comb(m + n, k))
                 for i in range(max(0, k - n), min(m, k) + 1)), Fraction(0))
            for k in range(m + n + 1)]


def _elevate(a: list[Fraction], target: int) -> list[Fraction]:
    out = list(a)
    while len(out) - 1 < target:
        n = len(out) - 1
        out = [out[0]] + [Fraction(i, n + 1) * out[i - 1] + Fraction(n + 1 - i, n + 1) * out[i]
                          for i in range(1, n + 1)] + [out[-1]]
    _need(len(out) - 1 == target, "Bernstein degree reduction is forbidden")
    return out


def _local_r9(r: list[Fraction], z: list[Fraction]) -> list[Fraction]:
    rp, zp = _poles(r), _poles(z)
    rpp, zpp = _poles(rp), _poles(zp)
    speed2 = [a + b for a, b in zip(_bprod(rp, rp), _bprod(zp, zp))]
    det = [a - b for a, b in zip(_bprod(rp, zpp), _bprod(zp, rpp))]
    speed6 = _bprod(_bprod(speed2, speed2), speed2)
    det2 = _elevate(_bprod(det, det), 24)
    return [a - 81 * b for a, b in zip(speed6, det2)]


def _endpoint_jet(values: list[Fraction], h: Fraction, order: int, end: bool) -> Fraction:
    row, degree, factor = list(values), len(values) - 1, 1
    for _ in range(order):
        factor *= degree
        degree -= 1
        row = [row[i + 1] - row[i] for i in range(len(row) - 1)]
    return Fraction(factor) * (row[-1] if end else row[0]) / h ** order


def _verify_leaf(check: dict[str, Any], expected: list[Fraction]) -> None:
    _need(check.get("status") == "PASS", "saved Bernstein check is not PASS")
    leaves = check.get("leaves", [])
    _need(len(leaves) == 1, "candidate requires one direct full-span Bernstein leaf")
    leaf = leaves[0]
    _need(tuple(map(_q, leaf["interval"])) == (Fraction(0), Fraction(1)), "Bernstein leaf does not cover the full span")
    _need(int(leaf["degree"]) == len(expected) - 1, "Bernstein degree mismatch")
    actual = list(map(_q, leaf["coefficients"]))
    _need(actual == expected and all(x >= 0 for x in actual), "saved nonnegative coefficients do not match exact poles")


def _fixture_flags(case: dict[str, Any], depth: Fraction) -> dict[str, str]:
    positive = case["fixtures"]["positive_straight_vertical"]
    radius, height = _q(positive["radius_mm"]), _q(positive["height_per_global_u_mm"])
    _need(radius > depth and height > 0, "positive analytic fixture contract invalid")
    nonmono = case["fixtures"]["nonmonotone_z_gate"]
    poles = list(map(_q, nonmono["zprime_bernstein_coefficients"]))
    gate = "PASS_STRICT_OPEN" if all(x >= 0 for x in poles) and any(x > 0 for x in poles) else "UNKNOWN_GATE_ONLY"
    _need(gate == nonmono["expected"], "nonmonotone fixture must stop at UNKNOWN, not claim a collision")
    return {"positive_straight_vertical": "PASS_ANALYTIC", "nonmonotone_z_gate": gate}


def _verify_saved(data: dict[str, bytes], case: dict[str, Any]) -> dict[str, Any]:
    offset = json.loads(data["offset_result"].decode("utf-8"))
    outer = json.loads(data["outer_result"].decode("utf-8"))["families"]["jar"]["exact_geometry_certificate"]
    audit = json.loads(data["independent_audit"].decode("utf-8"))
    stdout = json.loads(data["independent_stdout"].decode("utf-8"))
    _need(offset["status"] == offset["study_certificate_status"] == offset["study"]["status"] == "INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE" and offset["scope"] == offset["study"]["scope"] == "jar_meridian_2d_only", "unexpected local-offset result scope")
    _need(offset["normal_strip_global_injectivity"] == "UNKNOWN" and offset["global_wall_status"] == "UNKNOWN", "saved local result has unexpected global claim")
    upstream = offset["upstream_evidence"]
    _need(upstream["sides_R9_pass"] == 10 and upstream["spans_regular_pass"] == 12 and upstream["C4_joins_pass"] == 11 and upstream["features_pass"] == 5, "pinned outer evidence counts mismatch")
    _need(upstream["upstream_r9_all_side_spans_pass"] is True and upstream["upstream_regular_all_spans_pass"] is True, "pinned R9/regularity attestations missing")
    _need(audit["status"] == "PASS_RECONSTRUCTION", "independent reconstruction audit did not pass")
    _need(stdout["status"] == "INDEPENDENT_SAVED_OFFSET_AUDIT_PASS" and stdout["inputs_unchanged"] is True and stdout["span_count"] == 12 and stdout["joins_checked"] == 11, "independent offset stdout is not a passing readback")
    _need(stdout["result_sha256"] == INPUT_PINS["offset_result"][1] and stdout["outer_result_sha256"] == INPUT_PINS["outer_result"][1], "independent stdout does not bind the saved results")
    _need(stdout["audit_sha256"] == INPUT_PINS["independent_audit"][1] and stdout["receipt_sha256"] == INPUT_PINS["offset_receipt"][1] and stdout["global_wall"] == stdout["normal_strip_global_injectivity"] == "UNKNOWN", "independent stdout scope/hash mismatch")
    for pin in ("outer_result", "frozen_driver", "constrained_source", "design_cases", "fixed_cases"):
        _need(INPUT_PINS[pin][1] in audit["input_sha256"].values(), "independent audit does not bind " + pin)
    _need(outer["family"] == "jar" and outer["all_spans_regular_proved"] and outer["all_C4"] and outer["all_hulls_proved"] and outer["all_features_exact"] and outer["all_strict_point_checks_pass"], "outer regularity/C4/hull/feature evidence missing")
    _need(outer["global_normal_wall"] == "UNKNOWN_NOT_COMPUTED" and outer["inner_profile"] == "NOT_CONSTRUCTED", "outer metadata scope mismatch")
    depth = _q(case["offset_t_mm"])
    _need(depth == 3, "offset depth is not the pinned 3 mm")
    contract = case["local_certificate_contract"]
    r9, lambda_min = _q(contract["side_radius_bound_mm"]), _q(contract["side_lambda_lower_bound"])
    _need(r9 == 9 and lambda_min == Fraction(2, 3) == 1 - depth / r9, "R9 does not imply the pinned lambda lower bound")
    _need(contract["normal_radius_polynomial_degree"] + 1 == contract["normal_radius_coefficient_count"] == 19 and contract["r9_polynomial_degree"] + 1 == contract["r9_coefficient_count"] == 25, "saved Bernstein degree contracts mismatch")
    spans, outer_spans = offset["spans"], outer["spans"]
    _need(len(spans) == len(outer_spans) == case["span_count"] == 12, "expected exactly 12 saved Bezier spans")
    breaks = list(map(_q, case["expected_breaks"]))
    _need(len(breaks) == 13, "case break count mismatch")
    signs_out, actual_controls, r9_bindings = [], [], []
    for i, (span, proof) in enumerate(zip(spans, outer_spans)):
        kind = case["expected_span_kinds"][i]
        _need(span["span_index"] == proof["span"] == i and span["kind"] == kind, "span identity/kind mismatch")
        u0, u1 = map(_q, proof["u"])
        _need((u0, u1) == (breaks[i], breaks[i + 1]) and u1 > u0, "span interval mismatch")
        h = u1 - u0
        controls = [[_q(x) for x in row] for row in span["exact_bezier_controls_rz_mm"]]
        r, z = list(map(_q, span["r_bernstein_mm"])), list(map(_q, span["z_bernstein_mm"]))
        _need(len(controls) == len(r) == len(z) == 6 and all(len(row) == 2 for row in controls), "degree-5 controls malformed")
        _need([row[0] for row in controls] == r and [row[1] for row in controls] == z, "saved coordinate/control mismatch")
        actual_controls.append(controls)
        rp, zp = _poles(r), _poles(z)
        rs, zs = "".join(map(_sign, rp)), "".join(map(_sign, zp))
        _need(rs == case["expected_derivative_pole_signs"]["rprime"][i] and zs == case["expected_derivative_pole_signs"]["zprime"][i], "exact derivative-pole sign pin mismatch")
        _need(outer_spans[i]["z_derivative_poles_nonnegative"] is True and outer_spans[i]["endpoint_tangents_nonzero"] is True, "saved regularity pole evidence missing")
        _need((rp[0], zp[0]) != (0, 0) and (rp[-1], zp[-1]) != (0, 0), "zero endpoint tangent")
        checks = span["certificate"]["checks"]
        _verify_leaf(checks["r_nonnegative"], r)
        _verify_leaf(checks["zprime_nonnegative"], zp)
        qcoeff = list(map(_q, span["Q_bernstein_degree18"]))
        _need(len(qcoeff) == case["local_certificate_contract"]["normal_radius_coefficient_count"], "Q degree-18 coefficient count mismatch")
        _verify_leaf(checks["Q_nonnegative"], qcoeff)
        _need(checks["regular_tangent_v_positive"] == "PASS_FROM_PINNED_UPSTREAM", "offset regularity premise not pinned")
        _need(outer_spans[i]["open_span_regular"] is True, "outer open-span regularity not proved")
        if kind == "side":
            _need(all(x >= 0 for x in zp) and any(x > 0 for x in zp), "side zprime poles do not prove strict increase on the open span")
            _need(checks["z_strictly_increasing"] == "PASS" and checks["curvature_factor_lower_bound"] == "2/3_FROM_PINNED_R9", "side monotonicity/R9 factor missing")
            _need(outer_spans[i]["radius_9mm_status"] == "PROVED_R9_ON_CLOSED_NONFLAT_SPAN", "side R9 status missing")
            p_global = list(map(_q, outer_spans[i]["P_R_degree24_coefficients"]))
            p_actual = _local_r9(r, z)
            _need(len(p_actual) == len(p_global) == contract["r9_coefficient_count"], "R9 degree-24 Bernstein coefficient count mismatch")
            for j, (actual, scaled_global) in enumerate(zip(p_actual, (h ** 6 * x for x in p_global))):
                _need(actual == scaled_global, f"actual-control R9 binding mismatch span {i} coefficient {j}: local={actual}, h6_outer={scaled_global}")
            _need(all(x >= 0 for x in p_actual), "actual-control R9 Bernstein coefficients are not all nonnegative")
            r9_bindings.append({"span": i, "h": str(h), "coefficient_count": len(p_actual),
                                "local_equals_h6_times_outer_global": True, "all_nonnegative": True})
        elif kind == "flat_base":
            _need(all(x == 0 for x in zp) and all(x > 0 for x in rp), "flat-base z/r signs invalid")
            _verify_leaf(checks["flat_base_rprime_nonnegative"], rp)
            _need(checks["flat_base_zprime_zero"] == "PASS" and checks["flat_base_r_monotone"] == "PASS" and checks["straight_curvature_factor"] == "1", "flat-base proof missing")
        else:
            _need(all(x == 0 for x in rp) and all(x > 0 for x in zp), "straight-neck signs invalid")
            _need(checks["straight_neck_rprime_zero"] == "PASS" and checks["straight_neck_z_monotone"] == "PASS" and checks["straight_curvature_factor"] == "1", "straight-neck proof missing")
            _need(outer_spans[i]["semantic_neck_cylindrical"] is True and outer_spans[i]["radius_9mm_status"] == "EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK", "straight-neck exclusion not bound")
        if kind == "flat_base":
            _need(outer_spans[i]["semantic_base_flat"] is True and outer_spans[i]["radius_9mm_status"] == "EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK", "flat-base exclusion not bound")
        signs_out.append({"span": i, "kind": kind, "rprime": rs, "zprime": zs})
    joins = outer["joins"]
    _need(len(joins) == 11 and all(j["exact_C4"] and len(j["derivative_orders_0_to_4_equal"]) == 5 and all(j["derivative_orders_0_to_4_equal"]) for j in joins), "all 11 exact C4 joins are required")
    _need(all(_q(j["u"]) == breaks[i + 1] for i, j in enumerate(joins)), "C4 join locations do not match the span breaks")
    actual_joins = []
    for i in range(11):
        hl, hr = breaks[i + 1] - breaks[i], breaks[i + 2] - breaks[i + 1]
        orders = []
        for k in range(5):
            equal = all(_endpoint_jet([row[axis] for row in actual_controls[i]], hl, k, True) ==
                        _endpoint_jet([row[axis] for row in actual_controls[i + 1]], hr, k, False)
                        for axis in range(2))
            _need(equal, f"actual-control global-u C4 jet mismatch join {i} order {k}")
            orders.append(k)
        actual_joins.append({"join": i, "global_u_derivative_orders_equal": orders})
    _need(outer["straight_meridian_exclusions_proved"] is True, "straight base/neck exclusions are not exact")
    req = {k: _q(v) for k, v in case["required_exact_endpoints_mm"].items()}
    base_r, base_z = list(map(_q, spans[0]["r_bernstein_mm"])), list(map(_q, spans[0]["z_bernstein_mm"]))
    _need(base_r[0] == req["outer_axis_start_r"] and base_z[0] == req["base_z"], "outer axis/base endpoint mismatch")
    _need(base_r[-1] == _q(spans[1]["r_bernstein_mm"][0]) == req["base_side_seam_r"], "base/side seam radius mismatch")
    _need(base_z[-1] == req["base_side_seam_z"] == _q(spans[1]["z_bernstein_mm"][0]), "base/side seam height mismatch")
    mouth_r, mouth_z = _q(spans[-1]["r_bernstein_mm"][-1]), _q(spans[-1]["z_bernstein_mm"][-1])
    _need(mouth_r == req["mouth_r"] and mouth_z == req["mouth_z"] and mouth_r - depth == req["inner_mouth_r_after_3mm_normal"], "mouth endpoint/normal fiber mismatch")
    _need(mouth_z - req["base_z"] > depth, "fixed-height depth range is not connected")
    fixture_status = _fixture_flags(case, depth)
    return {"status": "GLOBAL_MERIDIAN_STRIP_INJECTIVITY_PROVED_CONDITIONAL", "scope": "pinned actual 2D meridian map F over all 12 spans and 0<=s<=3 mm", "span_signs": signs_out, "shared_geometry_binding": {"actual_controls_reconstruct_outer_global_R9_polynomial": r9_bindings, "actual_controls_global_u_C4_joins": actual_joins}, "local_factor": "lambda>=2/3 on side; lambda=1 on straight base/neck", "fixed_height_identity": "dR/ds|Z=-v/zprime<0 where zprime>0", "endpoint_fibers": {"axis": ["(0,0)", "(0,3)"], "base_side_seam": ["(18,0)", "(18,3)"], "mouth": ["(26,120)", "(23,120)"], "lip_claim": "mathematical domain edge only; actual CAD lip not asserted"}, "fixtures": {"positive_straight_vertical": {"status": fixture_status["positive_straight_vertical"], "map": "F(u,s)=(R-s,H*u); equal r fixes s and equal z fixes u"}, "nonmonotone_z_gate": {"status": fixture_status["nonmonotone_z_gate"], "claim": "gate-only UNKNOWN; no full-profile collision inferred"}}, "global_minimum_euclidean_wall": "UNKNOWN", "native_brep": "UNKNOWN", "physics": "UNKNOWN"}


def run_saved_certificate(*, root_ready: bool = False) -> dict[str, Any]:
    """Read and verify pinned saved evidence once; default call is inert and refuses."""
    global _RUN_STARTED
    if not root_ready:
        raise PermissionError("SOURCE_ONLY: separate root GO required before reading saved inputs")
    if _RUN_STARTED:
        raise PermissionError("one saved-data verification call per process")
    _RUN_STARTED = True
    started = time.monotonic()
    try:
        source = Path(__file__).resolve()
        root = source.parents[3]
        case_bytes = source.with_name("case.json").read_bytes()
        if hashlib.sha256(case_bytes).hexdigest() != CASE_SHA256:
            raise Unknown("case pin mismatch")
        case = json.loads(case_bytes.decode("utf-8"))
        data: dict[str, bytes] = {}
        for name, (relative, expected) in INPUT_PINS.items():
            raw = (root / relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise Unknown("input pin mismatch: " + name)
            data[name] = raw
        result = _verify_saved(data, case)
        result["input_pins"] = {name: digest for name, (_, digest) in INPUT_PINS.items()}
        result["case_sha256"] = CASE_SHA256
        if time.monotonic() - started > MAX_SECONDS:
            raise Unknown("13-second execution budget exceeded")
        result["serialized_bytes"] = 0
        for _ in range(2):
            result["serialized_bytes"] = len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if result["serialized_bytes"] > MAX_OUTPUT_BYTES:
            raise Unknown("4 MiB serialized-output budget exceeded")
        return result
    except Unknown as exc:
        return {"status": "UNKNOWN", "reason": str(exc), "global_minimum_euclidean_wall": "UNKNOWN", "native_brep": "UNKNOWN"}
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        return {"status": "UNKNOWN", "reason": type(exc).__name__, "global_minimum_euclidean_wall": "UNKNOWN", "native_brep": "UNKNOWN"}


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: do not execute before separate root GO")
