"""Metadata-only schema audit; does not import or call the verifier."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_chain(node: ast.AST) -> list[Any] | None:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Subscript):
        base = path_chain(node.value)
        if base is None:
            return None
        part = node.slice
        if isinstance(part, ast.Constant) and isinstance(part.value, (str, int)):
            return base + [part.value]
        return base + ["*"]
    return None


def resolve(objects: list[Any], parts: list[Any]) -> tuple[bool, str]:
    current = objects
    for part in parts:
        next_values: list[Any] = []
        for value in current:
            if part == "*":
                if isinstance(value, list):
                    next_values.extend(value)
                elif isinstance(value, dict):
                    next_values.extend(value.values())
                else:
                    return False, "wildcard on non-container"
            elif isinstance(part, int):
                if isinstance(value, list) and -len(value) <= part < len(value):
                    next_values.append(value[part])
                else:
                    return False, f"index {part} missing"
            elif isinstance(value, dict) and part in value:
                next_values.append(value[part])
            else:
                return False, f"field {part!r} missing"
        current = next_values
    return bool(current), "present" if current else "empty selection"


def main() -> None:
    root = Path.cwd().resolve()
    review = root / "vesselforge/tmp/review_20261007/monotone_normal_strip_decision"
    freeze = review / "failure_source_freeze"
    source = freeze / "monotone_normal_strip_certificate.pre_scope_alias_fix.py"
    pins = json.loads((freeze / "source_pins.pre_scope_alias_fix.json").read_text(encoding="utf-8"))
    input_paths = {"offset_result": pins["bound_inputs"]["normal_offset_result"]["path"],
                   "outer_result": pins["bound_inputs"]["outer_candidate_result"]["path"],
                   "independent_audit": pins["bound_inputs"]["independent_audit"]["path"],
                   "independent_stdout": pins["bound_inputs"]["independent_saved_offset_stdout"]["path"],
                   "case": pins["files"]["case"]["path"]}
    raw = {name: (root / path).read_bytes() for name, path in input_paths.items()}
    data: dict[str, Any] = {}
    for name, blob in raw.items():
        data[name] = json.loads(blob.decode("utf-8"))
    offset, case, audit, stdout = data["offset_result"], data["case"], data["independent_audit"], data["independent_stdout"]
    outer = data["outer_result"]["families"]["jar"]["exact_geometry_certificate"]
    upstream = offset["upstream_evidence"]
    contract = case["local_certificate_contract"]
    req = case["required_exact_endpoints_mm"]
    spans, outer_spans = offset["spans"], outer["spans"]
    checks_maps = [span["certificate"]["checks"] for span in spans]
    check_dicts = [item for mapping in checks_maps for item in mapping.values() if isinstance(item, dict)]
    leaves = [leaf for check in check_dicts for leaf in check.get("leaves", [])]

    roots = {
        "offset": [offset], "outer": [outer], "audit": [audit], "stdout": [stdout],
        "upstream": [upstream], "case": [case], "contract": [contract], "req": [req],
        "positive": [case["fixtures"]["positive_straight_vertical"]],
        "nonmono": [case["fixtures"]["nonmonotone_z_gate"]],
        "spans": [spans], "outer_spans": [outer_spans], "span": spans,
        "proof": outer_spans, "checks": checks_maps, "check": check_dicts, "leaf": leaves,
        "joins": [outer["joins"]], "j": outer["joins"],
    }
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    access_rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        chain = path_chain(node)
        if chain and chain[0] in roots:
            key = tuple(chain)
            outcomes = [resolve([obj], chain[1:]) for obj in roots[chain[0]]]
            matching = [why for ok, why in outcomes if ok]
            conditional = chain[0] == "checks"
            ok = bool(matching) if conditional else len(matching) == len(outcomes)
            access_rows[key] = {"path": ".".join(map(str, chain)), "present": ok,
                                "conditional_by_span_kind": conditional,
                                "matching_objects": len(matching), "root_objects": len(outcomes),
                                "detail": "present in applicable check map(s)" if conditional and ok else ("present in all objects" if ok else "missing from one or more objects")}

    def static_value(node: ast.AST, env: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return env[node.id]
        if isinstance(node, ast.Subscript):
            return static_value(node.value, env)[static_value(node.slice, env)]
        if isinstance(node, ast.BoolOp):
            values = [static_value(value, env) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = static_value(node.left, env)
            for op, item in zip(node.ops, node.comparators):
                right = static_value(item, env)
                if isinstance(op, ast.Eq):
                    passed = left == right
                elif isinstance(op, ast.Is):
                    passed = left is right
                else:
                    raise ValueError("unsupported static comparison operator")
                if not passed:
                    return False
                left = right
            return True
        raise ValueError("non-static assertion expression")

    scope_assertion = next(node for node in ast.walk(tree)
                           if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_need"
                           and len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
                           and node.args[1].value == "unexpected local-offset result scope")
    old_scope_assertion_value = static_value(scope_assertion.args[0], {"offset": offset})

    literal_checks: list[dict[str, Any]] = []

    def eq(label: str, actual: Any, expected: Any) -> None:
        literal_checks.append({"label": label, "pass": actual == expected, "actual": actual, "expected": expected})

    for key in ("status", "study_certificate_status"):
        eq("offset." + key, offset[key], "INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE")
    eq("offset.study.status", offset["study"]["status"], "INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE")
    eq("offset.scope", offset["scope"], "jar_meridian_2d_only")
    eq("offset.study.scope", offset["study"]["scope"], "jar_meridian_2d_curve_only")
    eq("offset.normal_strip_global_injectivity", offset["normal_strip_global_injectivity"], "UNKNOWN")
    eq("offset.global_wall_status", offset["global_wall_status"], "UNKNOWN")
    for key, expected in {"sides_R9_pass": 10, "spans_regular_pass": 12, "C4_joins_pass": 11, "features_pass": 5}.items():
        eq("upstream." + key, upstream[key], expected)
    for key in ("upstream_r9_all_side_spans_pass", "upstream_regular_all_spans_pass"):
        eq("upstream." + key, upstream[key], True)
    eq("audit.status", audit["status"], "PASS_RECONSTRUCTION")
    for key, expected in {"status": "INDEPENDENT_SAVED_OFFSET_AUDIT_PASS", "inputs_unchanged": True,
                          "span_count": 12, "joins_checked": 11,
                          "result_sha256": pins["bound_inputs"]["normal_offset_result"]["sha256"],
                          "outer_result_sha256": pins["bound_inputs"]["outer_candidate_result"]["sha256"],
                          "audit_sha256": pins["bound_inputs"]["independent_audit"]["sha256"],
                          "receipt_sha256": pins["bound_inputs"]["normal_offset_run_receipt"]["sha256"],
                          "global_wall": "UNKNOWN", "normal_strip_global_injectivity": "UNKNOWN"}.items():
        eq("stdout." + key, stdout[key], expected)
    for pin in ("outer_candidate_result", "frozen_driver", "constrained_source", "design_cases", "fixed_cases"):
        eq("audit_binds." + pin, pins["bound_inputs"][pin]["sha256"] in audit["input_sha256"].values(), True)
    eq("outer.family", outer["family"], "jar")
    for key in ("all_spans_regular_proved", "all_C4", "all_hulls_proved", "all_features_exact", "all_strict_point_checks_pass"):
        eq("outer." + key, outer[key], True)
    eq("outer.global_normal_wall", outer["global_normal_wall"], "UNKNOWN_NOT_COMPUTED")
    eq("outer.inner_profile", outer["inner_profile"], "NOT_CONSTRUCTED")
    eq("outer.straight_meridian_exclusions_proved", outer["straight_meridian_exclusions_proved"], True)
    eq("case.offset_t_mm", case["offset_t_mm"], "3/1")
    eq("contract.side_radius_bound_mm", contract["side_radius_bound_mm"], "9/1")
    eq("contract.side_lambda_lower_bound", contract["side_lambda_lower_bound"], "2/3")
    for key, expected in {"normal_radius_polynomial_degree": 18, "normal_radius_coefficient_count": 19,
                          "r9_polynomial_degree": 24, "r9_coefficient_count": 25}.items():
        eq("contract." + key, contract[key], expected)
    eq("case.span_count", case["span_count"], 12)
    eq("case.break_count", len(case["expected_breaks"]), 13)
    eq("case.span_kind_count", len(case["expected_span_kinds"]), 12)
    eq("case.rprime_sign_span_count", len(case["expected_derivative_pole_signs"]["rprime"]), 12)
    eq("case.zprime_sign_span_count", len(case["expected_derivative_pole_signs"]["zprime"]), 12)
    eq("fixture.nonmonotone.expected", case["fixtures"]["nonmonotone_z_gate"]["expected"], "UNKNOWN_GATE_ONLY")
    eq("fixture.positive.expected", case["fixtures"]["positive_straight_vertical"]["expected"], "PASS_ANALYTIC")

    per_span: list[dict[str, Any]] = []
    for i, (span, proof) in enumerate(zip(spans, outer_spans)):
        kind = case["expected_span_kinds"][i]
        c = span["certificate"]["checks"]
        row = {"index": i, "offset_span_index_matches": span["span_index"] == i,
               "outer_span_index_matches": proof["span"] == i, "kind_matches_case": span["kind"] == kind,
               "controls_shape_6x2": len(span["exact_bezier_controls_rz_mm"]) == 6 and all(len(x) == 2 for x in span["exact_bezier_controls_rz_mm"]),
               "coordinate_pole_lengths_6": len(span["r_bernstein_mm"]) == len(span["z_bernstein_mm"]) == 6,
               "Q_coefficient_count_19": len(span["Q_bernstein_degree18"]) == 19,
               "offset_base_check_keys": all(k in c for k in ("r_nonnegative", "zprime_nonnegative", "Q_nonnegative", "regular_tangent_v_positive")),
               "leaf_statuses_pass": all(c[k]["status"] == "PASS" and len(c[k]["leaves"]) == 1 for k in ("r_nonnegative", "zprime_nonnegative", "Q_nonnegative")),
               "outer_regular_metadata": proof["open_span_regular"] is True and proof["endpoint_tangents_nonzero"] is True}
        if kind == "side":
            row.update({"side_status_literals": c["z_strictly_increasing"] == "PASS" and c["curvature_factor_lower_bound"] == "2/3_FROM_PINNED_R9" and proof["radius_9mm_status"] == "PROVED_R9_ON_CLOSED_NONFLAT_SPAN",
                        "P_R_coefficient_count_25": len(proof["P_R_degree24_coefficients"]) == 25,
                        "expected_pole_sign_entries_present": len(case["expected_derivative_pole_signs"]["rprime"][i]) == 5 and len(case["expected_derivative_pole_signs"]["zprime"][i]) == 5})
        elif kind == "flat_base":
            row.update({"base_status_literals": c["flat_base_zprime_zero"] == "PASS" and c["flat_base_r_monotone"] == "PASS" and c["straight_curvature_factor"] == "1",
                        "base_extra_leaf_pass": c["flat_base_rprime_nonnegative"]["status"] == "PASS",
                        "outer_base_exclusion": proof["semantic_base_flat"] is True and proof["radius_9mm_status"] == "EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK"})
        else:
            row.update({"neck_status_literals": c["straight_neck_rprime_zero"] == "PASS" and c["straight_neck_z_monotone"] == "PASS" and c["straight_curvature_factor"] == "1",
                        "outer_neck_exclusion": proof["semantic_neck_cylindrical"] is True and proof["radius_9mm_status"] == "EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK"})
        per_span.append(row)
    joins = outer["joins"]
    static_join = {"count_11": len(joins) == 11,
                   "all_saved_exact_C4": all(j["exact_C4"] is True and len(j["derivative_orders_0_to_4_equal"]) == 5 and all(j["derivative_orders_0_to_4_equal"]) for j in joins),
                   "case_break_locations_count": all(len(j["u"]) == 1 or isinstance(j["u"], str) for j in joins)}
    req_presence = {key: key in req for key in ("outer_axis_start_r", "base_z", "base_side_seam_r", "base_side_seam_z", "mouth_r", "mouth_z", "inner_mouth_r_after_3mm_normal")}
    raw_endpoints = {
        "outer_axis_start_r": spans[0]["r_bernstein_mm"][0],
        "base_z": spans[0]["z_bernstein_mm"][0],
        "base_side_seam_r": spans[0]["r_bernstein_mm"][-1],
        "base_side_seam_z": spans[0]["z_bernstein_mm"][-1],
        "mouth_r": spans[-1]["r_bernstein_mm"][-1],
        "mouth_z": spans[-1]["z_bernstein_mm"][-1],
    }
    raw_endpoint_text_matches = {key: str(raw_endpoints[key]) == str(req[key]) for key in raw_endpoints}
    result = {
        "schema": "vesselforge.monotone_normal_strip.static_schema_audit.v1",
        "source_hash": sha(source), "source_pins_snapshot_hash": sha(freeze / "source_pins.pre_scope_alias_fix.json"),
        "case_hash": sha(root / input_paths["case"]),
        "source_executed": False, "run_saved_certificate_called": False,
        "fraction_geometry_calculation_performed": False,
        "input_hashes_match_pins": {name: sha(root / pins["bound_inputs"][name]["path"]) == pins["bound_inputs"][name]["sha256"] for name in pins["bound_inputs"]},
        "ast_field_access_inventory": {"count": len(access_rows), "missing": [v for v in access_rows.values() if not v["present"]],
                                        "conditional_kind_specific_paths": [v for v in access_rows.values() if v["conditional_by_span_kind"]]},
        "pre_fix_scope_assertion_evaluated_from_ast": {"passed": old_scope_assertion_value,
            "actual_top_scope": offset["scope"], "actual_study_scope": offset["study"]["scope"],
            "reason": "one chained equality reused the curve-only literal for both distinct scope fields"},
        "literal_checks": literal_checks, "per_span_static_schema": per_span,
        "saved_join_static_schema": static_join, "required_endpoint_key_presence": req_presence,
        "raw_endpoint_values": raw_endpoints, "raw_endpoint_text_matches": raw_endpoint_text_matches,
        "failure_capture_status": json.loads((review / "once_capture_01/result.json").read_text(encoding="utf-8")),
        "not_checked_by_static_audit": ["exact pole signs", "exact local R9 coefficient equality", "actual-control C4 jet equality", "fixed-slice theorem"],
    }
    report_path = review / "failure_source_freeze/static_schema_audit.json"
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    missing_accesses = result["ast_field_access_inventory"]["missing"]
    literal_failures = [x for x in literal_checks if not x["pass"]]
    span_failures = [{"span": x["index"], "keys": [k for k,v in x.items() if isinstance(v, bool) and not v]} for x in per_span if any(isinstance(v, bool) and not v for v in x.values())]
    print(json.dumps({"field_access_count": len(access_rows), "missing_field_accesses": missing_accesses,
                      "literal_failures": literal_failures, "per_span_failures": span_failures,
                      "pre_fix_scope_assertion_passed": old_scope_assertion_value,
                      "raw_endpoint_text_matches": raw_endpoint_text_matches,
                      "join_static": static_join, "endpoint_key_presence": req_presence,
                      "audit_report_sha256": sha(report_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
