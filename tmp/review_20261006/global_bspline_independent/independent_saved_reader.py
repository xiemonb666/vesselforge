"""Independent reader for the saved VF minimum-jerk candidate; never solves it."""
from __future__ import annotations
import hashlib, io, json
from fractions import Fraction as F
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
VF = HERE.parents[2]
SRC = VF / "experiments" / "global_bspline_meridian_20261006"
CASES = SRC / "fixed_cases.json"
RESULT = VF / "tmp" / "review_20261006" / "global_bspline_meridian_20261006" / "minimum_jerk_candidate" / "minimum_jerk_exact_result.json"
MAX_BYTES, DEGREE = 8 * 1024 * 1024, 5
EXPECTED_RESULT_SHA256 = "06c714ff30e8f36c60e586e07670510d539b844ec434772a5d93b749612a6f65"
OUT = (HERE / "independent_saved_audit.json", HERE / "bowl_outer_only.png", HERE / "jar_outer_only.png")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def add(a, b): return tuple(x + y for x, y in zip(a, b, strict=True))
def sub(a, b): return tuple(x - y for x, y in zip(a, b, strict=True))
def mul(a, k): return tuple(x * k for x in a)
def vec(raw): return tuple(F(str(x)) for x in raw)
def pair(raw): return (F(str(raw[0])), F(str(raw[1])))

def de_boor(points, knots, degree, u):
    n = len(points) - 1
    if len(knots) != n + degree + 2: raise ValueError("KNOT_CONTROL_COUNT_MISMATCH")
    if u == knots[n + 1]: return points[-1]
    span = next((i for i in range(degree, n + 1) if knots[i] <= u < knots[i + 1]), None)
    if span is None: raise ValueError("PARAMETER_OUTSIDE_SPLINE_DOMAIN")
    work = list(points[span - degree:span + 1])
    for r in range(1, degree + 1):
        for j in range(degree, r - 1, -1):
            i = span - degree + j
            den = knots[i + degree - r + 1] - knots[i]
            if den <= 0: raise ValueError("NONPOSITIVE_DEBOOR_DENOMINATOR")
            alpha = (u - knots[i]) / den
            work[j] = add(mul(work[j - 1], 1 - alpha), mul(work[j], alpha))
    return work[degree]

def derivative_spline(points, knots, degree):
    if degree < 1: raise ValueError("DERIVATIVE_ORDER_TOO_HIGH")
    out = []
    for i in range(len(points) - 1):
        den = knots[i + degree + 1] - knots[i + 1]
        if den <= 0: raise ValueError("NONPOSITIVE_DERIVATIVE_DENOMINATOR")
        out.append(mul(sub(points[i + 1], points[i]), F(degree) / den))
    return tuple(out), tuple(knots[1:-1]), degree - 1

def spline_jet(points, knots, degree, u, order):
    for _ in range(order): points, knots, degree = derivative_spline(points, knots, degree)
    return de_boor(points, knots, degree, u)

def bezier_eval(poles, t):
    row = tuple(poles)
    while len(row) > 1: row = tuple(add(mul(row[i], 1 - t), mul(row[i + 1], t)) for i in range(len(row) - 1))
    return row[0]

def bezier_jet(poles, h, order, at_end):
    row, degree = tuple(poles), len(poles) - 1
    for _ in range(order):
        row = tuple(mul(sub(row[i + 1], row[i]), F(degree) / h) for i in range(degree))
        degree -= 1
    return row[-1] if at_end else row[0]

def radius_endpoint(poles, h, radius, at_end):
    d1, d2 = bezier_jet(poles, h, 1, at_end), bezier_jet(poles, h, 2, at_end)
    speed = d1[0] ** 2 + d1[1] ** 2
    det = d1[0] * d2[1] - d1[1] * d2[0]
    return speed ** 3 - radius ** 2 * det ** 2, speed

def check_case(family, case, solved, breaks, knots):
    controls = tuple(pair(p) for p in solved["control_points_rz_mm"])
    records = solved["geometry"]["spans"]
    spans = tuple(tuple(pair(p) for p in s["bezier_poles_rz_mm"]) for s in records)
    if len(controls) != 11 or len(spans) != 6 or len(records) != 6 or any(len(s) != 6 for s in spans): raise ValueError("UNEXPECTED_SAVED_NET_SHAPE")
    equalities = []
    for feature in case["fixed_feature_constraints"]:
        u = F(feature["u"]); actual = de_boor(controls, knots, DEGREE, u)
        for axis, label in enumerate(("r", "z")):
            expected = F(feature["rz_mm"][axis]); equalities.append({"name": feature["name"] + "." + label, "pass": actual[axis] == expected})
    apex = next(x for x in case["fixed_feature_constraints"] if x["name"] == case["apex_feature"])
    apex_u = F(apex["u"]); axis_d = spline_jet(controls, knots, DEGREE, F(0), 1)
    mouth_d = spline_jet(controls, knots, DEGREE, F(1), 1); apex_d = spline_jet(controls, knots, DEGREE, apex_u, 1)
    tangent_eqs = (("axis_dz_zero", axis_d[1] == 0), ("mouth_dr_zero", mouth_d[0] == 0), ("apex_dr_zero", apex_d[0] == 0))
    equalities.extend({"name": n, "pass": ok} for n, ok in tangent_eqs)
    apex_r2 = spline_jet(controls, knots, DEGREE, apex_u, 2)[0]
    strict = {"axis_dr_positive": axis_d[0] > 0, "mouth_dz_positive": mouth_d[1] > 0,
              "apex_dz_positive": apex_d[1] > 0, "apex_r_second_negative": apex_r2 < 0}
    if len(equalities) != 9: raise ValueError("EXPECTED_NINE_EQUALITIES")
    apex_idx = breaks.index(apex_u); max_r = F(case["fixed_dimensions"]["max_outer_radius_mm"]); mouth_z = F(case["fixed_dimensions"]["mouth_datum_z_mm"])
    span_checks, comparisons, samples, curvature = [], [], [], []
    for si, (poles, rec) in enumerate(zip(spans, records, strict=True)):
        a, b = breaks[si], breaks[si + 1]; h = b - a
        hull = all(0 <= p[0] <= max_r and 0 <= p[1] <= mouth_z for p in poles)
        d = tuple(mul(sub(poles[i + 1], poles[i]), F(DEGREE) / h) for i in range(DEGREE))
        z_nonneg, z_positive = all(v[1] >= 0 for v in d), any(v[1] > 0 for v in d)
        radial = all(v[0] >= 0 for v in d) if si < apex_idx else all(v[0] <= 0 for v in d)
        end_nonzero = bezier_jet(poles, h, 1, False) != (0, 0) and bezier_jet(poles, h, 1, True) != (0, 0)
        open_regular = z_nonneg and z_positive
        hull_status = "PROVED_BY_CONTROL_HULL" if hull else "NOT_CERTIFIED_BY_CONTROL_HULL"
        z_status = "PROVED_BY_POLE_SIGNS" if z_nonneg else "NOT_CERTIFIED_BY_POLE_SIGNS"
        r_status = "PROVED_BY_POLE_SIGNS" if radial else "NOT_CERTIFIED_BY_POLE_SIGNS"
        endpoint_status = "PROVED" if end_nonzero else "FAIL_ZERO_ENDPOINT_TANGENT"
        if rec["hull_poles_in_fixed_bbox"] != hull or rec["hull_certificate_status"] != hull_status or rec["z_derivative_poles_nonnegative"] != z_nonneg or rec["vertical_monotonicity_status"] != z_status or rec["z_derivative_has_positive_pole"] != z_positive or rec["radial_derivative_poles_match_apex_side"] != radial or rec["radial_direction_status"] != r_status or rec["span_interior_regular"] != open_regular or rec["endpoint_tangents_nonzero"] != end_nonzero or rec["endpoint_regular_status"] != endpoint_status:
            raise ValueError("SAVED_SUFFICIENT_SCREEN_MISMATCH")
        span_checks.append({"span": si, "hull_poles_in_bbox": hull, "z_derivative_nonnegative": z_nonneg,
                            "z_derivative_positive_pole": z_positive, "radial_signs_match_apex_side": radial,
                            "interior_regular_by_z_projection": open_regular, "both_endpoint_tangents_nonzero": end_nonzero})
        for t in (F(1, 3), F(2, 3)):
            u = a + h * t; direct = de_boor(controls, knots, DEGREE, u); extracted = bezier_eval(poles, t)
            comparisons.append({"span": si, "u": str(u), "equal_exactly": direct == extracted})
        sampled = tuple(bezier_eval(poles, F(i, 32)) for i in range(33)); samples.extend(sampled)
        for side_key, case_key in (("body_shoulder", "body_and_shoulder_radius_mm"), ("base_turn_unassigned", "outer_base_turn_radius_mm")):
            rad = F(case["curvature_targets"][case_key]); saved = rec["radius_screens"][side_key]; coeff = tuple(F(x) for x in saved["coefficients"])
            if len(coeff) != 25 or F(saved["radius_mm"]) != rad: raise ValueError("SAVED_DEGREE24_SCREEN_MISMATCH")
            endpoints = (radius_endpoint(poles, h, rad, False), radius_endpoint(poles, h, rad, True))
            matches = (coeff[0] == endpoints[0][0], coeff[-1] == endpoints[1][0])
            nonnegative = all(x >= 0 for x in coeff)
            expected_status = ("PROVED_RADIUS_SCREEN_ON_CLOSED_SPAN" if open_regular and end_nonzero else "POLYNOMIAL_NONNEGATIVE_BUT_REGULARITY_NOT_CERTIFIED") if nonnegative else ("POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT" if coeff[0] < 0 or coeff[-1] < 0 else "UNKNOWN_MIXED_BERNSTEIN_COEFFICIENTS")
            curvature.append({"span": si, "screen": side_key, "start_P": str(endpoints[0][0]), "end_P": str(endpoints[1][0]), "endpoint_coefficients_match_independent_reevaluation": all(matches), "saved_status_matches_endpoint_and_sign_logic": saved["status"] == expected_status, "producer_status": saved["status"],
                             "start_P_negative_regular_point": endpoints[0][0] < 0 and endpoints[0][1] > 0,
                             "end_P_negative_regular_point": endpoints[1][0] < 0 and endpoints[1][1] > 0,
                             "saved_full_coefficient_list_nonnegative": nonnegative,
                             "interior_coefficients_rebuilt": False})
    joins = []
    for si, (left, right) in enumerate(zip(spans, spans[1:])):
        h0, h1 = breaks[si + 1] - breaks[si], breaks[si + 2] - breaks[si + 1]
        orders = [bezier_jet(left, h0, k, True) == bezier_jet(right, h1, k, False) for k in range(5)]
        saved_join = solved["geometry"]["joins"][si]
        if saved_join["derivative_orders_0_to_4_equal"] != orders: raise ValueError("SAVED_JOIN_CHECK_MISMATCH")
        joins.append({"u": str(breaks[si + 1]), "orders_0_to_4_equal": orders})
    all_c4 = all(all(j["orders_0_to_4_equal"]) for j in joins)
    all_endpoint_coeffs_match = all(x["endpoint_coefficients_match_independent_reevaluation"] and x["saved_status_matches_endpoint_and_sign_logic"] for x in curvature)
    all_extraction_checks = all(x["equal_exactly"] for x in comparisons)
    if len(comparisons) != 12 or len(samples) != 198: raise ValueError("UNEXPECTED_SPOTCHECK_OR_SAMPLE_COUNT")
    return {"family": family, "equalities_9_pass": equalities, "all_nine_equalities_pass": all(x["pass"] for x in equalities), "strict_endpoint_inequalities_pass": strict, "accepted_total_height_crest_target_mm": case["accepted_candidate_total_height_mm"], "total_height_status": case["total_height_status"],
            "joins_C4": joins, "all_joins_C4": all_c4, "span_sufficient_screens": span_checks, "direct_deboor_vs_bezier_checks": comparisons, "all_direct_extraction_checks_pass": all_extraction_checks,
            "curvature_endpoint_checks": curvature, "all_curvature_endpoint_coefficients_match": all_endpoint_coeffs_match, "sampled_RZ_mm": [[str(x), str(y)] for x, y in samples],
            "outer_only_label": "NOT_PHYSICS_READY", "lip_inner_offset_global_wall": "NOT_CONSTRUCTED_OR_VERIFIED",
            "offset_interpretation": "A failed radius screen P_R<0 is not an inward-offset cusp result; signed 1-3*kappa is not evaluated here."}, controls, spans, samples

def render(family, case, controls, spans, samples):
    width, height = 1040, 820; left, top, right, bottom = 85, 82, 40, 76
    max_r = F(case["fixed_dimensions"]["max_outer_radius_mm"]); mouth_z = F(case["fixed_dimensions"]["mouth_datum_z_mm"])
    rmin, rmax = min(F(0), *(p[0] for p in controls)), max(max_r, *(p[0] for p in controls))
    zmin, zmax = min(F(0), *(p[1] for p in controls)), max(mouth_z, *(p[1] for p in controls))
    pad = max(rmax - rmin, zmax - zmin) / 14; rmin -= pad; rmax += pad; zmin -= pad; zmax += pad
    scale = min((width - left - right) / float(rmax - rmin), (height - top - bottom) / float(zmax - zmin))
    ox = left + ((width - left - right) - float(rmax - rmin) * scale) / 2 - float(rmin) * scale
    oy = top + ((height - top - bottom) - float(zmax - zmin) * scale) / 2 + float(zmax) * scale
    xy = lambda p: (round(ox + float(p[0]) * scale), round(oy - float(p[1]) * scale))
    im = Image.new("RGB", (width, height), "white"); dr = ImageDraw.Draw(im); font = ImageFont.load_default()
    dr.text((left, 24), f"{family.upper()} | OUTER ONLY | NOT_PHYSICS_READY", fill="#18212b", font=font)
    dr.rectangle((left, top, width-right, height-bottom), outline="#9aa4ad", width=1)
    dr.text((left, height-52), "r (mm)  |  blue: control polygon  |  orange: outer profile", fill="#39434d", font=font)
    dr.text((left, height-34), "Open mouth datum; no rim, lip, inner wall, or physical qualification.", fill="#39434d", font=font)
    dr.text((left+4, top+6), "z (mm)", fill="#39434d", font=font)
    for r, z, label in ((F(0), F(0), "axis"), (max_r, F(0), "Rmax"), (F(0), mouth_z, "mouth z")):
        x0, y0 = xy((r, z)); dr.ellipse((x0-3, y0-3, x0+3, y0+3), fill="#65717c"); dr.text((x0+5, y0-12), label, fill="#59636d", font=font)
    net = [xy(p) for p in controls]; dr.line(net, fill="#6d91b3", width=2)
    for x, y in net: dr.ellipse((x-4, y-4, x+4, y+4), fill="#376f9f")
    line = [xy(p) for p in samples]; dr.line(line, fill="#d46a26", width=4)
    mouth = xy(samples[-1]); dr.ellipse((mouth[0]-6, mouth[1]-6, mouth[0]+6, mouth[1]+6), fill="#a33a2b")
    label_x = mouth[0]+8 if mouth[0]+120 < width-right else mouth[0]-118
    dr.text((label_x, mouth[1]+5), "open mouth endpoint", fill="#8d2d24", font=font)
    bio = io.BytesIO(); im.save(bio, format="PNG", optimize=True); return bio.getvalue()

def main():
    if not RESULT.is_file(): raise FileNotFoundError("SAVED_CANDIDATE_NOT_READY")
    if RESULT.stat().st_size > MAX_BYTES: raise ValueError("CANDIDATE_INPUT_EXCEEDS_8MIB")
    if any(p.exists() for p in OUT): raise FileExistsError("REFUSING_TO_OVERWRITE_REVIEW_OUTPUT")
    input_sha_before = sha(RESULT)
    if input_sha_before != EXPECTED_RESULT_SHA256: raise ValueError("CANDIDATE_SHA_DOES_NOT_MATCH_ROOT_PIN")
    data = json.loads(RESULT.read_text(encoding="utf-8")); cases = json.loads(CASES.read_text(encoding="utf-8"))
    if data.get("schema") != "vesselforge.global_bspline_meridian.minimum_jerk_result.v1": raise ValueError("UNEXPECTED_RESULT_SCHEMA")
    pins = {SRC / "bspline_minimum_jerk_driver.py", SRC / "bspline_constraint_source.py", CASES}
    actual = {str(p.resolve()): sha(p) for p in pins}; reported = {str(Path(k).resolve()): v for k, v in data["source_sha256"].items()}
    if actual != reported: raise ValueError("SAVED_RESULT_SOURCE_HASH_MISMATCH")
    knots = tuple(F(x) for x in cases["curve_model"]["full_knot_vector"]); breaks = (F(0), *(F(x) for x in cases["curve_model"]["internal_knots"]), F(1))
    audit, pngs = {}, []
    for family in ("bowl", "jar"):
        report, controls, spans, samples = check_case(family, cases["cases"][family], data["cases"][family], breaks, knots)
        audit[family] = report; pngs.append(render(family, cases["cases"][family], controls, spans, samples))
    input_sha_after = sha(RESULT)
    family_reports = tuple(audit.values())
    gates = {"all_nine_equalities": all(x["all_nine_equalities_pass"] for x in family_reports),
             "all_four_strict_endpoint_inequalities": all(all(x["strict_endpoint_inequalities_pass"].values()) for x in family_reports),
             "all_joins_C4": all(x["all_joins_C4"] for x in family_reports),
             "all_24_deboor_bezier_spotchecks": sum(len(x["direct_deboor_vs_bezier_checks"]) for x in family_reports) == 24 and all(x["all_direct_extraction_checks_pass"] for x in family_reports),
             "all_degree24_endpoint_coefficients_match": all(x["all_curvature_endpoint_coefficients_match"] for x in family_reports),
             "candidate_sha_unchanged_and_pinned": input_sha_before == input_sha_after == EXPECTED_RESULT_SHA256}
    reconstruction_status = "PASS_RECONSTRUCTION" if all(gates.values()) else "FAIL_RECONSTRUCTION"
    endpoint_failures = sum(c["start_P_negative_regular_point"] + c["end_P_negative_regular_point"]
                            for x in family_reports for c in x["curvature_endpoint_checks"])
    candidate_geometry_status = "ENDPOINT_RADIUS_COUNTEREXAMPLE_PRESENT" if endpoint_failures else "NO_ENDPOINT_COUNTEREXAMPLE; interior_certificate_not_rebuilt"
    audit_doc = {"schema": "vesselforge.independent_saved_candidate_review.v1", "source_sha256": actual,
                 "candidate_sha256_before": input_sha_before, "candidate_sha256_after": input_sha_after,
                 "review_sha256": sha(Path(__file__)), "reconstruction_gates": gates,
                 "reconstruction_status": reconstruction_status, "reconstruction_exit_code": 0 if reconstruction_status == "PASS_RECONSTRUCTION" else 1,
                 "candidate_geometry_screen_status": candidate_geometry_status, "radius_screen_endpoint_counterexample_count": endpoint_failures,
                 "full_degree24_bernstein_interior_coefficients_rebuilt": False, "families": audit}
    encoded = (json.dumps(audit_doc, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_BYTES or sum(map(len, pngs)) + len(encoded) > MAX_BYTES: raise ValueError("REVIEW_OUTPUTS_EXCEED_8MIB")
    for path, payload in zip(OUT, (encoded, *pngs), strict=True): path.write_bytes(payload)
    print(f"audit={reconstruction_status} exit={audit_doc['reconstruction_exit_code']} geometry={candidate_geometry_status} input_sha256={input_sha_before}")
    return audit_doc["reconstruction_exit_code"]

if __name__ == "__main__": raise SystemExit(main())




